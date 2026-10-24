"""Bounded, read-only capture of one Wayland data offer.

Metadata and payload are requested from the SAME zwlr_data_control_offer_v1.
Selection replacement invalidates the capture instead of mixing two offers.
Only registry/seat/data-control read requests are implemented; this client never
sets a selection, injects input, or logs clipboard data. It uses the documented
Wayland wire format directly, with no native extension or build dependency.

Protocol references:
https://wayland.freedesktop.org/docs/book/Protocol.html
https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml
"""
import array
import os
from pathlib import Path
import select
import socket
import struct
import time

import sharing_state

UINT = struct.Struct("=I")
HEADER = struct.Struct("=II")
MANAGER = "zwlr_data_control_manager_v1"
TEXT = "text/plain;charset=utf-8"
PREFERENCES = (TEXT, "text/plain;charset=UTF-8", "text/plain", "UTF8_STRING",
               "image/png", "image/jpeg", "image/webp", "image/bmp")
# Total seconds allowed once a payload grows past each size; largest first.
LARGE_DEADLINES = ((64 * 1024 * 1024, 12), (32 * 1024 * 1024, 8))


def allowed_seconds(size, timeout):
    """A large copy earns more time only after it has delivered that many bytes."""
    return max(timeout, next((seconds for limit, seconds in LARGE_DEADLINES if size > limit), 0))


def _string(value):
    data = value.encode() + b"\0"
    return UINT.pack(len(data)) + data + b"\0" * (-len(data) % 4)


def _read_string(data, offset=0):
    if len(data) < offset + 4:
        raise ValueError("Invalid Wayland string")
    size = UINT.unpack_from(data, offset)[0]
    end = offset + 4 + size
    if not size or end > len(data) or data[end-1] != 0 or b"\0" in data[offset+4:end-1]:
        raise ValueError("Invalid Wayland string")
    return data[offset+4:end-1].decode(), offset + 4 + ((size + 3) & ~3)


def secret_source(data):
    """Unreadable advertised source metadata is treated as sensitive."""
    if not data:
        return True
    try:
        return data.decode().startswith(sharing_state.SECRET_SOURCES)
    except UnicodeDecodeError:
        return True


class OfferReader:
    def __init__(self, selection, timeout):
        if selection not in {"clipboard", "primary"}:
            raise ValueError("Unsupported selection")
        self.selection = selection
        self.timeout = timeout
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.buffer = bytearray()
        self.next_id = 2
        self.registry = self.manager = self.device = None
        self.globals = []
        self.offers = {}
        self.current = {"clipboard": None, "primary": None}
        self.frozen = None
        self.callbacks = set()
        self.events = 0
        self.event_bytes = 0

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Clipboard offer timed out")
        return seconds

    def new_id(self):
        value = self.next_id
        self.next_id += 1
        return value

    def send(self, object_id, opcode, payload=b"", fd=None):
        message = HEADER.pack(object_id, ((len(payload) + 8) << 16) | opcode) + payload
        self.sock.settimeout(self.remaining())
        if fd is None:
            self.sock.sendall(message)
        else:
            sent = self.sock.sendmsg([message], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
            self.sock.sendall(message[sent:])

    def receive_events(self):
        self.sock.settimeout(self.remaining())
        data = self.sock.recv(65536)
        if not data:
            raise OSError("Wayland connection closed")
        self.buffer.extend(data)
        while len(self.buffer) >= 8:
            object_id, word = HEADER.unpack_from(self.buffer)
            size, opcode = word >> 16, word & 0xffff
            if size < 8 or size % 4:
                raise ValueError("Invalid Wayland frame")
            if len(self.buffer) < size:
                break
            payload = bytes(self.buffer[8:size])
            del self.buffer[:size]
            self.events += 1
            self.event_bytes += size
            if self.events > 8192 or self.event_bytes > 1024 * 1024:
                raise ValueError("Wayland event limit exceeded")
            self.event(object_id, opcode, payload)

    def event(self, object_id, opcode, payload):
        if object_id == 1 and opcode == 0:
            # Do not echo compositor error text, which can contain application data.
            raise OSError("Wayland protocol error")
        if object_id in self.callbacks and opcode == 0:
            self.callbacks.remove(object_id)
        elif object_id == self.registry and opcode == 0:
            name = UINT.unpack_from(payload)[0]
            interface, offset = _read_string(payload, 4)
            version = UINT.unpack_from(payload, offset)[0]
            self.globals.append((name, interface, version))
        elif object_id == self.registry and opcode == 1:
            name = UINT.unpack_from(payload)[0]
            self.globals = [item for item in self.globals if item[0] != name]
        elif object_id == self.device:
            if opcode == 0:
                offer = UINT.unpack_from(payload)[0]
                if offer < 0xff000000 or offer in self.offers:
                    raise ValueError("Invalid Wayland offer identity")
                self.offers[offer] = []
            elif opcode in (1, 3):
                selection = "clipboard" if opcode == 1 else "primary"
                offer = UINT.unpack_from(payload)[0] or None
                if offer is not None and offer not in self.offers:
                    raise ValueError("Unknown Wayland offer")
                previous = self.current[selection]
                self.current[selection] = offer
                if self.frozen is not None and selection == self.selection and offer != self.frozen:
                    raise ValueError("Clipboard offer changed during capture")
                if previous is not None and previous != offer:
                    self.send(previous, 1)  # zwlr_data_control_offer_v1.destroy
                    self.offers.pop(previous, None)
            elif opcode == 2:
                raise OSError("Wayland data control finished")
        elif object_id in self.offers and opcode == 0:
            if object_id == self.frozen:
                raise ValueError("Clipboard metadata changed during capture")
            mime, _ = _read_string(payload)
            offered = self.offers[object_id]
            if sum(len(value) + 1 for value in offered) + len(mime) + 1 > 65536:
                raise ValueError("Clipboard MIME list exceeds limit")
            offered.append(mime)

    def sync(self):
        callback = self.new_id()
        self.callbacks.add(callback)
        self.send(1, 0, UINT.pack(callback))  # wl_display.sync
        while callback in self.callbacks:
            self.receive_events()

    def bind(self, item, version):
        name, interface, _ = item
        object_id = self.new_id()
        self.send(self.registry, 0, UINT.pack(name) + _string(interface) + UINT.pack(version) + UINT.pack(object_id))
        return object_id

    def connect(self):
        display = os.environ.get("WAYLAND_DISPLAY")
        if not display:
            raise OSError("Wayland display is unavailable")
        path = Path(display)
        if not path.is_absolute():
            runtime = os.environ.get("XDG_RUNTIME_DIR")
            if not runtime:
                raise OSError("Wayland runtime directory is unavailable")
            path = Path(runtime) / path
        self.sock.settimeout(self.remaining())
        self.sock.connect(str(path))
        self.registry = self.new_id()
        self.send(1, 1, UINT.pack(self.registry))  # wl_display.get_registry
        self.sync()
        managers = [item for item in self.globals if item[1] == MANAGER and item[2] >= 2]
        seats = [item for item in self.globals if item[1] == "wl_seat"]
        if len(managers) != 1 or len(seats) != 1:
            raise ValueError("Clipboard capture requires data-control v2 and exactly one Wayland seat")
        self.manager = self.bind(managers[0], 2)
        seat = self.bind(seats[0], 1)
        self.device = self.new_id()
        self.send(self.manager, 1, UINT.pack(self.device) + UINT.pack(seat))
        self.sync()

    def read_offer(self, requests):
        """Request all representations on the frozen offer; bound each pipe."""
        pipes, result = {}, {}
        try:
            for mime, limit in requests.items():
                read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
                os.set_blocking(read_fd, False)
                pipes[read_fd] = (mime, limit, bytearray())
                try:
                    self.send(self.frozen, 0, _string(mime), write_fd)
                finally:
                    os.close(write_fd)
            while pipes:
                readable, _, _ = select.select([self.sock, *pipes], [], [], self.remaining())
                if not readable:
                    raise TimeoutError("Clipboard offer timed out")
                if self.sock in readable:
                    self.receive_events()
                for fd in readable:
                    if fd is self.sock:
                        continue
                    mime, limit, data = pipes[fd]
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        result[mime] = bytes(data)
                        os.close(fd)
                        del pipes[fd]
                    else:
                        if len(data) + len(chunk) > limit:
                            raise ValueError("Clipboard representation exceeds limit")
                        data.extend(chunk)
                        self.deadline = max(self.deadline, self.started + allowed_seconds(len(data), self.timeout))
            # Observe replacements already queued by the compositor before returning.
            self.sync()
            return result
        finally:
            for fd in pipes:
                os.close(fd)


def capture(selection, max_bytes, timeout=4):
    """Return (normalized MIME, bytes, sensitive), or None for no supported offer.

    Called in a worker thread; every socket/pipe wait shares one finite deadline,
    extended to 8 or 12 seconds once the payload passes 32 or 64 MiB.
    Closing the connection releases all server-side offer/device resources.
    """
    reader = OfferReader(selection, timeout)
    try:
        reader.connect()
        reader.frozen = reader.current[selection]
        if reader.frozen is None:
            return None
        offered = tuple(reader.offers[reader.frozen])
        selected = next((mime for mime in PREFERENCES if mime in offered), None)
        if selected is None:
            return None
        requests = {selected: max_bytes}
        marked = sharing_state.SECRET_HINT in offered
        if not marked and sharing_state.SOURCE_URL in offered:
            requests[sharing_state.SOURCE_URL] = 4096
        values = reader.read_offer(requests)
        sensitive = marked or (sharing_state.SOURCE_URL in requests and secret_source(values[sharing_state.SOURCE_URL]))
        mime = TEXT if selected in PREFERENCES[:4] else selected
        return mime, values[selected], sensitive
    except (struct.error, UnicodeError) as error:
        raise ValueError("Invalid Wayland clipboard metadata") from error
    finally:
        reader.sock.close()
