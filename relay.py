#!/usr/bin/env python3
"""Clipboard and primary-selection sharing for one Synergy pair over SSH.

Clipboard payloads stay in memory. stdout is the remote wire protocol; diagnostics
go to stderr and never include clipboard contents. Both Wayland selections share.
"""
import asyncio
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import shlex
import socket
import subprocess
import sys
import tomllib
import re
import time
import sharing_state

WIRE_VERSION = sharing_state.WIRE_VERSION

MAX_BYTES = 8 * 1024 * 1024
MAX_LINE = 12 * 1024 * 1024
TEXT = "text/plain;charset=utf-8"
PREFERENCES = (TEXT, "text/plain;charset=UTF-8", "text/plain", "UTF8_STRING",
               "image/png", "image/jpeg", "image/webp", "image/bmp")
ALLOWED = {TEXT, "image/png", "image/jpeg", "image/webp", "image/bmp"}
SELECTIONS = ("clipboard", "primary")
SCRIPT = Path(__file__).resolve()
LOG = logging.getLogger("synergy-clipboard")


def load_config(path):
    with open(path, "rb") as source:
        config = tomllib.load(source)
    expected = {"remote_host", "remote_script", "peer_id", "initial_sync"}
    if not expected.issubset(config) or set(config) - expected - {"transport", "max_mib"}:
        raise ValueError("config requires remote_host, remote_script, peer_id and initial_sync; transport and max_mib are optional")
    config.setdefault("max_mib", 8)
    sharing_state.validate_limit(config["max_mib"])
    # Preserve the tested transport for existing configurations.
    config.setdefault("transport", "tailscale")
    if config["transport"] not in ("ssh", "tailscale"):
        raise ValueError("transport must be ssh or tailscale")
    if not isinstance(config["remote_host"], str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*", config["remote_host"]):
        raise ValueError("invalid remote_host")
    remote_script = config["remote_script"]
    if not isinstance(remote_script, str) or not remote_script.startswith("/") or any(c in remote_script for c in "\x00\r\n"):
        raise ValueError("remote_script must be an absolute path")
    if not isinstance(config["peer_id"], str) or not re.fullmatch(r"[a-f0-9]{64}", config["peer_id"]):
        raise ValueError("peer_id must be the 64-character Synergy computer ID")
    if config["initial_sync"] not in ("none", "source"):
        raise ValueError("initial_sync must be none or source")
    return config


def remote_command(config):
    # Both transports invoke a remote shell: quote every remote argument as well
    # as using an argv list locally. Installation paths may contain spaces.
    remote = shlex.join(["/usr/bin/python3", config["remote_script"], "remote"])
    transport = config.get("transport", "tailscale")
    if transport == "tailscale":
        return ["/usr/bin/tailscale", "ssh", config["remote_host"], remote]
    if transport == "ssh":
        return ["/usr/bin/ssh", "-T", "-oBatchMode=yes",
                "-oStrictHostKeyChecking=yes", "-oPasswordAuthentication=no",
                "-oKbdInteractiveAuthentication=no", "-oConnectTimeout=10",
                "-oServerAliveInterval=15", "-oServerAliveCountMax=3",
                "--", config["remote_host"], remote]
    raise ValueError("transport must be ssh or tailscale")


def set_limit(max_bytes):
    global MAX_BYTES, MAX_LINE
    if type(max_bytes) is not int or not 1024*1024 <= max_bytes <= sharing_state.MAX_MIB*1024*1024:
        raise ValueError("Invalid negotiated clipboard limit")
    MAX_BYTES = max_bytes
    MAX_LINE = 4*((max_bytes + 2)//3) + 8192


def negotiate_limit(offered, local):
    set_limit(min(offered, local) if type(offered) is int else 0)
    return MAX_BYTES


def parse_message(line):
    if len(line) > MAX_LINE:
        raise ValueError("wire message too large")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("wire message must be an object")
    if message.get("kind") not in {"hello", "ack", "state", "clipboard"}:
        raise ValueError("unsupported message kind")
    if message.get("kind") == "clipboard" and message.get("selection") not in SELECTIONS:
        raise ValueError("unsupported selection")
    return message


def configure_environment():
    os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
    if not os.environ.get("WAYLAND_DISPLAY"):
        result = subprocess.run(["systemctl", "--user", "show-environment"],
                                capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            key, _, value = line.partition("=")
            if key in {"WAYLAND_DISPLAY", "DISPLAY"}:
                os.environ[key] = value
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("Wayland session is unavailable")


async def command(args, data=None, limit=MAX_BYTES, timeout=4):
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)

    async def collect():
        if data is not None:
            process.stdin.write(data)
            await process.stdin.drain()
            process.stdin.close()
        chunks, total = [], 0
        while chunk := await process.stdout.read(65536):
            total += len(chunk)
            if total > limit:
                raise ValueError("clipboard exceeds transfer limit")
            chunks.append(chunk)
        await process.wait()
        if process.returncode:
            return None
        return b"".join(chunks)

    try:
        return await asyncio.wait_for(collect(), timeout)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def digest(mime, data):
    return hashlib.sha256(mime.encode() + b"\0" + data).hexdigest()


def decode_clipboard(message):
    mime = message.get("mime")
    encoded = message.get("payload")
    if mime not in ALLOWED or not isinstance(encoded, str) or len(encoded) > MAX_LINE - 1024:
        raise ValueError("unsupported clipboard message")
    data = base64.b64decode(encoded, validate=True)
    if len(data) > MAX_BYTES or digest(mime, data) != message.get("digest"):
        raise ValueError("invalid clipboard size or digest")
    return mime, data


class Clipboard:
    def __init__(self, role, send, selection="clipboard"):
        if selection not in SELECTIONS:
            raise ValueError("unsupported selection")
        self.role, self.send = role, send
        self.selection = selection
        self.flags = ["--primary"] if selection == "primary" else []
        self.enabled = False
        self.last_digest = None
        self.lock = asyncio.Lock()
        self.changed = asyncio.Event()
        self.socket_path = Path(os.environ["XDG_RUNTIME_DIR"]) / f"synergy-clipboard-{role}-{selection}.sock"
        self.singleton = None
        self.sock = None
        self.watcher = None

    async def snapshot(self):
        types = await command(["wl-paste", *self.flags, "--list-types"], limit=65536)
        if types is None:
            return None
        offered = types.decode(errors="replace").splitlines()
        selected = next((mime for mime in PREFERENCES if mime in offered), None)
        if not selected:
            return None
        data = await command(["wl-paste", *self.flags, "--no-newline", "--type", selected])
        if data is None:
            return None
        mime = TEXT if selected in PREFERENCES[:4] else selected
        return mime, data

    async def start(self):
        self.singleton = open(self.socket_path.with_suffix(".lock"), "w")
        fcntl.flock(self.singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with contextlib.suppress(FileNotFoundError):
            self.socket_path.unlink()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self.sock.setblocking(False)
        try:
            initial = await self.snapshot()
        except (ValueError, asyncio.TimeoutError):
            initial = None
        if initial:
            self.last_digest = digest(*initial)
        loop = asyncio.get_running_loop()

        def notified():
            with contextlib.suppress(BlockingIOError):
                self.sock.recv(64)
            self.changed.set()

        loop.add_reader(self.sock.fileno(), notified)
        self.watcher = await asyncio.create_subprocess_exec(
            "wl-paste", *self.flags, "--no-newline", "--watch", "/usr/bin/python3", str(SCRIPT),
            "notify", str(self.socket_path), stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)

    async def monitor(self):
        while True:
            try:
                await asyncio.wait_for(self.changed.wait(), 3)
            except asyncio.TimeoutError:
                if self.watcher.returncode is not None:
                    raise RuntimeError("clipboard watcher stopped")
                continue
            self.changed.clear()
            await asyncio.sleep(0.025)
            try:
                async with self.lock:
                    snapshot = await self.snapshot()
                    if not snapshot:
                        self.last_digest = None
                        continue
                    mime, data = snapshot
                    current_digest = digest(mime, data)
                    if current_digest == self.last_digest:
                        continue
                    self.last_digest = current_digest
                    if not self.enabled:
                        continue
                    await self.send({"kind": "clipboard", "selection": self.selection, "mime": mime,
                                     "digest": current_digest,
                                     "payload": base64.b64encode(data).decode("ascii")})
            except (ValueError, OSError, asyncio.TimeoutError):
                LOG.warning("Clipboard format, size or read timeout prevented a transfer")

    async def seed(self):
        """Optionally seed the receiver from the coordinator after reconnecting."""
        async with self.lock:
            try:
                snapshot = await self.snapshot()
                if not snapshot or not self.enabled:
                    return
                mime, data = snapshot
                self.last_digest = digest(mime, data)
                await self.send({"kind": "clipboard", "selection": self.selection,
                                 "mime": mime, "digest": self.last_digest,
                                 "payload": base64.b64encode(data).decode("ascii")})
            except (ValueError, OSError, asyncio.TimeoutError):
                LOG.warning("Initial clipboard synchronization unavailable")

    async def apply(self, message):
        mime, data = decode_clipboard(message)
        value_digest = digest(mime, data)
        async with self.lock:
            if not self.enabled:
                return
            if value_digest == self.last_digest:
                return
            result = await command(["wl-copy", *self.flags, "--type", mime], data=data, limit=1024)
            if result is None:
                raise RuntimeError("clipboard write failed")
            self.last_digest = value_digest
        LOG.info("Received %s selection, %s (%d bytes)", self.selection, mime, len(data))

    async def close(self):
        if self.watcher and self.watcher.returncode is None:
            self.watcher.terminate()
            await self.watcher.wait()
        if self.sock:
            asyncio.get_running_loop().remove_reader(self.sock.fileno())
            self.sock.close()
            with contextlib.suppress(FileNotFoundError):
                self.socket_path.unlink()
        if self.singleton:
            self.singleton.close()


async def stdin_reader():
    reader = asyncio.StreamReader(limit=MAX_LINE)
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
    return reader


async def start_clipboards(clipboards):
    try:
        for clipboard in clipboards.values():
            await clipboard.start()
    except BaseException:
        for clipboard in clipboards.values():
            await clipboard.close()
        raise


async def remote():
    write_lock = asyncio.Lock()
    source_enabled = False
    source_name = ""
    transport = ""
    local_max = MAX_BYTES

    async def send(message):
        wire = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        async with write_lock:
            await asyncio.to_thread(write_stdout, wire)

    clipboards = {name: Clipboard("remote", send, name) for name in SELECTIONS}
    await start_clipboards(clipboards)
    monitors = [asyncio.create_task(clipboard.monitor()) for clipboard in clipboards.values()]

    async def update_gate():
        enabled = source_enabled and not sharing_state.paused()
        for clipboard in clipboards.values():
            clipboard.enabled = enabled
        state = "manual-paused" if sharing_state.paused() else ("sharing" if enabled else "synergy-paused")
        sharing_state.publish("receiver", state, source_name=source_name, transport=transport, max_mib=MAX_BYTES//(1024*1024))
        await send({"kind": "ack", "enabled": enabled, "paused": sharing_state.paused()})
        return enabled

    async def watch_pause():
        previous = None
        while True:
            current = sharing_state.paused()
            if current != previous:
                await update_gate()
                previous = current
            await asyncio.sleep(0.25)

    pause_task = None
    try:
        reader = await stdin_reader()
        await send({"kind": "hello", "version": WIRE_VERSION, "max_bytes": local_max})
        pause_task = asyncio.create_task(watch_pause())
        while True:
            line = await asyncio.wait_for(reader.readline(), 30)
            if not line:
                break
            message = parse_message(line)
            if message.get("kind") == "state":
                negotiate_limit(message.get("max_bytes"), local_max)
                source_enabled = message.get("enabled") is True
                source_name = str(message.get("source_name", ""))[:128]
                transport = str(message.get("transport", ""))[:16]
                await update_gate()
            elif message.get("kind") == "clipboard":
                # Recheck the local pause before each incoming write as well.
                clipboards[message["selection"]].enabled = source_enabled and not sharing_state.paused()
                await clipboards[message["selection"]].apply(message)
            for monitor in [*monitors, pause_task]:
                if monitor.done():
                    await monitor
    finally:
        tasks = [*monitors, *([pause_task] if pause_task else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for clipboard in clipboards.values():
            await clipboard.close()
        sharing_state.publish("receiver", "stopped")


def write_stdout(wire):
    sys.stdout.buffer.write(wire)
    sys.stdout.buffer.flush()


def connection_enabled(data, peer_id):
    return bool(data.get("coreRunning") is True and
                data.get("performance", {}).get("allow_copy") is True and
                data.get("screenStatus", {}).get(peer_id, {}).get("core") == "connected")


def synergy_connected(peer_id):
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:24803/v1/settings", timeout=2) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            return False
        data = json.loads(raw)["data"]
        return connection_enabled(data, peer_id)
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return False


async def coordinator(config):
    process = None
    remote_enabled = False
    remote_paused = False
    local_max = MAX_BYTES
    write_lock = asyncio.Lock()

    async def send(message):
        if process is None or process.returncode is not None:
            return
        wire = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        async with write_lock:
            process.stdin.write(wire)
            await asyncio.wait_for(process.stdin.drain(), 10)

    clipboards = {name: Clipboard("coordinator", send, name) for name in SELECTIONS}
    await start_clipboards(clipboards)
    monitors = [asyncio.create_task(clipboard.monitor()) for clipboard in clipboards.values()]
    backoff = 1

    async def gate():
        previous = None
        seeded = False
        synergy_enabled = False
        next_check = 0
        next_heartbeat = 0
        while True:
            now = time.monotonic()
            if now >= next_check:
                synergy_enabled = await asyncio.to_thread(synergy_connected, config["peer_id"])
                next_check = now + 2
            intent = synergy_enabled and not sharing_state.paused()
            enabled = intent and remote_enabled
            for clipboard in clipboards.values():
                clipboard.enabled = enabled
            if now >= next_heartbeat or intent != previous:
                await send({"kind": "state", "enabled": intent,
                            "source_name": socket.gethostname(), "transport": config.get("transport", "tailscale"), "max_bytes": MAX_BYTES})
                next_heartbeat = now + 2
            if enabled and not seeded and config["initial_sync"] == "source":
                for clipboard in clipboards.values():
                    await clipboard.seed()
                seeded = True
            state = ("manual-paused" if sharing_state.paused() else
                     "peer-paused" if remote_paused else
                     "sharing" if enabled else "synergy-paused" if not synergy_enabled else "connecting")
            sharing_state.publish("source", state, transport=config.get("transport", "tailscale"), max_mib=MAX_BYTES//(1024*1024))
            previous = intent
            await asyncio.sleep(0.25)

    try:
        while True:
            gate_task = None
            remote_enabled = False
            remote_paused = False
            sharing_state.publish("source", "connecting", transport=config.get("transport", "tailscale"))
            try:
                set_limit(local_max)
                process = await asyncio.create_subprocess_exec(
                    *remote_command(config), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=None, limit=MAX_LINE)
                first = await asyncio.wait_for(process.stdout.readline(), 20)
                hello = parse_message(first)
                if hello.get("kind") != "hello" or hello.get("version") != WIRE_VERSION:
                    raise RuntimeError("remote handshake failed")
                negotiate_limit(hello.get("max_bytes"), local_max)
                LOG.info("Encrypted clipboard connection established")
                backoff = 1
                gate_task = asyncio.create_task(gate())
                while True:
                    line = await asyncio.wait_for(process.stdout.readline(), 30)
                    if not line:
                        break
                    message = parse_message(line)
                    if message.get("kind") == "ack":
                        remote_enabled = message.get("enabled") is True
                        remote_paused = message.get("paused") is True
                        if not remote_enabled:
                            for clipboard in clipboards.values():
                                clipboard.enabled = False
                    elif message.get("kind") == "clipboard":
                        if sharing_state.paused():
                            clipboards[message["selection"]].enabled = False
                        await clipboards[message["selection"]].apply(message)
                    for monitor in monitors:
                        if monitor.done():
                            await monitor
                    if gate_task.done():
                        await gate_task
            except (OSError, ValueError, KeyError, RuntimeError, asyncio.TimeoutError):
                LOG.warning("Clipboard connection unavailable; reconnecting")
            finally:
                for clipboard in clipboards.values():
                    clipboard.enabled = False
                if gate_task:
                    gate_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, OSError):
                        await gate_task
                if process and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                process = None
                sharing_state.publish("source", "disconnected", transport=config.get("transport", "tailscale"))
            for monitor in monitors:
                if monitor.done():
                    await monitor
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)
    finally:
        for monitor in monitors:
            monitor.cancel()
        await asyncio.gather(*monitors, return_exceptions=True)
        for clipboard in clipboards.values():
            await clipboard.close()
        sharing_state.publish("source", "stopped")


def notify(path):
    # wl-paste supplies the selection on stdin. Drain it without storing or logging.
    while sys.stdin.buffer.read(65536):
        pass
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        with contextlib.suppress(OSError):
            client.sendto(b"changed", path)


async def main(mode, config=None):
    configure_environment()
    set_limit((config.get("max_mib", 8) if mode == "coordinator" else sharing_state.local_limit())*1024*1024)
    task = asyncio.create_task(remote() if mode == "remote" else coordinator(config))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    with contextlib.suppress(asyncio.CancelledError):
        await task


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    source = commands.add_parser("coordinator")
    source.add_argument("--config", type=Path, required=True)
    commands.add_parser("remote")
    notification = commands.add_parser("notify")
    notification.add_argument("socket")
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == "notify":
        notify(args.socket)
    else:
        config = load_config(args.config) if args.mode == "coordinator" else None
        asyncio.run(main(args.mode, config))
