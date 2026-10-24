"""Wire-level tests against a private fake compositor; no desktop access."""
import array
import asyncio
import collections
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

import clipboard_offer
import relay
import sharing_state


def word(value):
    return struct.pack("=I", value)


def string(value):
    data = value.encode() + b"\0"
    return word(len(data)) + data + b"\0" * (-len(data) % 4)


def decode_string(data, offset=0):
    size = struct.unpack_from("=I", data, offset)[0]
    return data[offset+4:offset+3+size].decode(), offset+4+((size+3)&~3)


class CaptureServer:
    """Serve metadata and pipe payloads using the public data-control protocol."""
    OFFER = 0xff000001

    def __init__(self, values=None, *, selection="clipboard", replace_on=None,
                 delay=0, seats=1, manager_version=2, fragmented=False, pause_after=None):
        self.values = {relay.TEXT: b"ordinary fixture"} if values is None else values
        self.selection, self.replace_on, self.delay = selection, replace_on, delay
        self.seats, self.manager_version = seats, manager_version
        self.fragmented = fragmented
        self.pause_after = pause_after  # (bytes, seconds): stall mid-payload
        self.requests = []
        self.error = None

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        path = str(Path(self.temp.name)/"wayland-test")
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(path)
        self.listener.listen(1)
        self.listener.settimeout(2)
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name, "WAYLAND_DISPLAY": path})
        self.env.start()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.thread.join(3)
        self.listener.close()
        self.env.stop()
        self.temp.cleanup()
        if self.thread.is_alive():
            raise AssertionError("Fake compositor did not terminate")
        if self.error:
            raise self.error

    def run(self):
        descriptors = collections.deque()
        try:
            with self.listener.accept()[0] as connection:
                connection.settimeout(2)
                buffer = bytearray()
                registry = manager = device = None

                def event(object_id, opcode, data=b""):
                    message = struct.pack("=II", object_id, ((len(data)+8)<<16)|opcode)+data
                    if self.fragmented:
                        connection.sendall(message[:5])
                        time.sleep(0.001)
                        connection.sendall(message[5:])
                    else:
                        connection.sendall(message)

                def offer(identifier, types):
                    event(device, 0, word(identifier))
                    for mime in types:
                        event(identifier, 0, string(mime))
                    event(device, 1 if self.selection == "clipboard" else 3, word(identifier))

                while True:
                    data, ancillary, flags, _ = connection.recvmsg(65536, socket.CMSG_SPACE(16))
                    if not data:
                        return
                    assert not flags & socket.MSG_CTRUNC
                    buffer.extend(data)
                    for level, kind, raw in ancillary:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                            fds = array.array("i")
                            fds.frombytes(raw[:len(raw)-(len(raw)%fds.itemsize)])
                            descriptors.extend(fds)
                    while len(buffer) >= 8:
                        sender, header = struct.unpack_from("=II", buffer)
                        size, opcode = header>>16, header&0xffff
                        assert size >= 8 and size % 4 == 0
                        if len(buffer) < size:
                            break
                        payload = bytes(buffer[8:size])
                        del buffer[:size]
                        if sender == 1 and opcode == 1:
                            registry = struct.unpack("=I", payload)[0]
                            event(registry, 0, word(10)+string(clipboard_offer.MANAGER)+word(self.manager_version))
                            for seat in range(self.seats):
                                event(registry, 0, word(20+seat)+string("wl_seat")+word(9))
                        elif sender == 1 and opcode == 0:
                            callback = struct.unpack("=I", payload)[0]
                            event(callback, 0, word(0))
                            event(1, 1, word(callback))
                        elif sender == registry and opcode == 0:
                            interface, offset = decode_string(payload, 4)
                            _, object_id = struct.unpack_from("=II", payload, offset)
                            if interface == clipboard_offer.MANAGER:
                                manager = object_id
                        elif sender == manager and opcode == 1:
                            device, _ = struct.unpack("=II", payload)
                            if self.values:
                                offer(self.OFFER, self.values)
                            else:
                                event(device, 1 if self.selection == "clipboard" else 3, word(0))
                        elif sender >= 0xff000000 and opcode == 0:
                            mime, _ = decode_string(payload)
                            fd = descriptors.popleft()
                            try:
                                self.requests.append((sender, mime))
                                if mime == self.replace_on:
                                    # Replace the selection while the old offer's
                                    # receive request is in flight. Never retarget
                                    # that old object to the new source.
                                    offer(self.OFFER+1, [relay.TEXT, sharing_state.SECRET_HINT])
                                if self.delay:
                                    time.sleep(self.delay)
                                value = self.values[mime]
                                if value is not None:
                                    view = memoryview(value)
                                    paused = self.pause_after is None
                                    while view:
                                        if not paused and len(value) - len(view) >= self.pause_after[0]:
                                            time.sleep(self.pause_after[1])
                                            paused = True
                                        chunk = view if paused else view[:self.pause_after[0]-(len(value)-len(view))]
                                        view = view[os.write(fd, chunk):]
                            finally:
                                os.close(fd)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected on bounded reads, cancellation and invalidated offers.
        except BaseException as error:
            self.error = error
        finally:
            for fd in descriptors:
                os.close(fd)


class OfferTests(unittest.TestCase):
    def test_fragmented_protocol_messages_are_reassembled(self):
        with CaptureServer(fragmented=True):
            self.assertEqual(clipboard_offer.capture("clipboard", 1024), (relay.TEXT,b"ordinary fixture",False))

    def test_large_payload_is_drained_without_pipe_deadlock(self):
        value = b"synthetic large fixture " * 50000
        with CaptureServer({relay.TEXT:value}):
            self.assertEqual(clipboard_offer.capture("clipboard", len(value))[1], value)

    def test_capture_failure_closes_received_pipe_resources(self):
        before = len(os.listdir('/proc/self/fd'))
        for _ in range(3):
            with CaptureServer({relay.TEXT:b"x"*2048}), self.assertRaises(ValueError):
                clipboard_offer.capture("clipboard", 1024)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_text_image_and_primary_use_the_advertised_offer(self):
        for selection, mime, value in [("clipboard", relay.TEXT, "text 世界".encode()),
                                       ("primary", "text/plain", b"highlight"),
                                       ("clipboard", "image/png", b"\x89PNG\x00\xff")]:
            with self.subTest(selection=selection, mime=mime), CaptureServer({mime:value}, selection=selection) as server:
                captured = clipboard_offer.capture(selection, 1024)
                self.assertEqual(captured, ("image/png" if mime == "image/png" else relay.TEXT, value, False))
                self.assertEqual(server.requests, [(server.OFFER, mime)])

    def test_sensitive_marker_is_bound_to_payload(self):
        with CaptureServer({relay.TEXT:b"marked fixture", sharing_state.SECRET_HINT:b"secret"}) as server:
            self.assertTrue(clipboard_offer.capture("clipboard", 1024)[2])
            self.assertEqual(server.requests, [(server.OFFER, relay.TEXT)])

    def test_source_metadata_and_content_use_identical_offer_ids(self):
        values = {relay.TEXT:b"browser fixture", sharing_state.SOURCE_URL:b"https://pass.proton.me/"}
        with CaptureServer(values) as server:
            self.assertTrue(clipboard_offer.capture("clipboard", 1024)[2])
            self.assertEqual(server.requests, [(server.OFFER, relay.TEXT), (server.OFFER, sharing_state.SOURCE_URL)])

    def test_replacement_during_payload_or_browser_source_aborts(self):
        values = {relay.TEXT:b"old ordinary fixture", sharing_state.SOURCE_URL:b"https://example.com/"}
        for when in values:
            for selection in ("clipboard", "primary"):
                with self.subTest(when=when, selection=selection), CaptureServer(values, selection=selection, replace_on=when) as server:
                    with self.assertRaisesRegex(ValueError, "offer changed"):
                        clipboard_offer.capture(selection, 1024)
                    self.assertTrue(all(identifier == server.OFFER for identifier, _ in server.requests))

    def test_unsupported_or_empty_selection_does_not_request_content(self):
        for values in ({}, {"text/html":b"<p>unsupported</p>"}):
            with CaptureServer(values) as server:
                self.assertIsNone(clipboard_offer.capture("clipboard", 1024))
                self.assertEqual(server.requests, [])

    def test_payload_and_source_metadata_are_independently_bounded(self):
        for values in ({relay.TEXT:b"x"*1025},
                       {relay.TEXT:b"ok", sharing_state.SOURCE_URL:b"x"*4097}):
            with CaptureServer(values), self.assertRaisesRegex(ValueError, "exceeds limit"):
                clipboard_offer.capture("clipboard", 1024)

    def test_stalled_source_has_a_total_deadline(self):
        with CaptureServer(delay=0.15), self.assertRaises(TimeoutError):
            clipboard_offer.capture("clipboard", 1024, timeout=0.05)

    def test_large_payload_deadlines_follow_delivered_size(self):
        mib = 1024 * 1024
        for size, seconds in ((0, 4), (32*mib, 4), (32*mib+1, 8), (64*mib, 8), (64*mib+1, 12), (128*mib, 12)):
            self.assertEqual(clipboard_offer.allowed_seconds(size, 4), seconds)
        self.assertEqual(clipboard_offer.allowed_seconds(1, 20), 20)

    def test_payload_past_a_size_threshold_gets_more_time(self):
        value = b"y" * 4096
        with patch.object(clipboard_offer, "LARGE_DEADLINES", ((2048, 1.0),)):
            # Stalls after crossing the threshold: the longer deadline applies.
            with CaptureServer({relay.TEXT:value}, pause_after=(3000, 0.3)):
                self.assertEqual(clipboard_offer.capture("clipboard", len(value), timeout=0.15)[1], value)
            # Stalls before crossing it: the base deadline still applies.
            with CaptureServer({relay.TEXT:value}, pause_after=(1000, 0.3)), self.assertRaises(TimeoutError):
                clipboard_offer.capture("clipboard", len(value), timeout=0.15)

    def test_missing_runtime_directory_is_a_connection_error(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY":"wayland-test"}):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            with self.assertRaisesRegex(OSError, "runtime directory"):
                clipboard_offer.capture("clipboard", 1024)

    def test_ambiguous_seat_and_missing_v2_fail_closed(self):
        for options in ({"seats":2}, {"manager_version":1}):
            with CaptureServer(**options) as server, self.assertRaisesRegex(ValueError, "exactly one"):
                clipboard_offer.capture("clipboard", 1024)
            self.assertEqual(server.requests, [])


class RelayOfferTests(unittest.IsolatedAsyncioTestCase):
    async def test_replacement_cannot_send_or_seed_unclassified_data(self):
        for seed in (False, True):
            with self.subTest(seed=seed), CaptureServer(replace_on=relay.TEXT):
                clipboard = relay.Clipboard("coordinator", AsyncMock())
                clipboard.enabled = True
                if seed:
                    await clipboard.seed()
                else:
                    with self.assertRaises(ValueError):
                        await clipboard.process(await clipboard.snapshot())
                clipboard.send.assert_not_awaited()

    async def test_wire_captured_secret_is_withheld_then_explicitly_sent(self):
        with CaptureServer({relay.TEXT:b"synthetic marked fixture", sharing_state.SECRET_HINT:b"secret"}):
            clipboard = relay.Clipboard("coordinator", AsyncMock())
            clipboard.enabled = True
            snapshot = await clipboard.snapshot()
            await clipboard.process(snapshot)
            clipboard.send.assert_not_awaited()
            sharing_state.allow_secret()
            await clipboard.process(snapshot)
            clipboard.send.assert_awaited_once()
            self.assertIs(clipboard.send.await_args.args[0]["sensitive"], True)

    async def test_start_survives_an_unreachable_compositor(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_RUNTIME_DIR":temp, "WAYLAND_DISPLAY":"missing-display"}):
            clipboard = relay.Clipboard("coordinator", AsyncMock())
            watcher = AsyncMock(returncode=0)
            with patch.object(relay.asyncio, "create_subprocess_exec", AsyncMock(return_value=watcher)):
                await clipboard.start()
            try:
                self.assertIsNone(clipboard.last_digest)
                self.assertIs(clipboard.watcher, watcher)
            finally:
                await clipboard.close()

    async def test_receiver_without_sensitive_flag_support_never_writes_secret(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_RUNTIME_DIR":temp}):
            clipboard = relay.Clipboard("remote", AsyncMock())
            clipboard.enabled = True
            data = b"synthetic marked fixture"
            import base64
            message = {"mime":relay.TEXT, "payload":base64.b64encode(data).decode(),
                       "digest":relay.digest(relay.TEXT,data), "sensitive":True}
            with patch.object(relay,"wl_copy_sensitive",return_value=False), patch.object(relay,"command",AsyncMock()) as write:
                await clipboard.apply(message)
                write.assert_not_awaited()
                self.assertIsNone(clipboard.last_digest)
