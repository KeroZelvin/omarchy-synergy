import asyncio
import base64
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import relay
import install


def frame(data=b"hello", selection="clipboard", mime=relay.TEXT):
    return {"kind": "clipboard", "selection": selection, "mime": mime,
            "payload": base64.b64encode(data).decode(), "digest": relay.digest(mime, data)}


class ProtocolTests(unittest.TestCase):
    def test_unicode_and_binary_round_trip(self):
        for data, mime in [("hello\n世界\n".encode(), relay.TEXT), (b"\x89PNG\x00\xff", "image/png")]:
            for selection in relay.SELECTIONS:
                message = relay.parse_message(json.dumps(frame(data, selection, mime)).encode())
                self.assertEqual(relay.decode_clipboard(message), (mime, data))

    def test_invalid_frames_are_rejected(self):
        bad = [b"[]", b"null", b"{", b'{"kind":"clipboard","selection":"other"}', b'{"kind":"execute"}']
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                relay.parse_message(value)

    def test_unsupported_mime_bad_base64_and_digest(self):
        for change in [{"mime": "text/html"}, {"payload": "%%%"}, {"digest": "bad"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                relay.decode_clipboard(frame() | change)

    def test_payload_limit_before_and_after_decode(self):
        with patch.object(relay, "MAX_LINE", 2048), patch.object(relay, "MAX_BYTES", 4):
            with self.assertRaises(ValueError):
                relay.decode_clipboard(frame(b"12345"))
            with self.assertRaises(ValueError):
                relay.decode_clipboard(frame() | {"payload": "x" * 2049})

    def test_synergy_gate_fails_closed(self):
        peer = "a" * 64
        data = {"coreRunning": True, "performance": {"allow_copy": True}, "screenStatus": {peer: {"core": "connected"}}}
        self.assertTrue(relay.connection_enabled(data, peer))
        self.assertFalse(relay.connection_enabled(data, "b" * 64))
        self.assertFalse(relay.connection_enabled(data | {"coreRunning": False}, peer))
        self.assertFalse(relay.connection_enabled(data | {"coreRunning": "false"}, peer))
        self.assertFalse(relay.connection_enabled(data | {"performance": {"allow_copy": False}}, peer))
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(relay.synergy_connected(peer))

    def test_remote_path_is_one_quoted_shell_argument(self):
        path = "/home/a user/clipboard;echo bad/relay.py"
        for transport in ("tailscale", "ssh"):
            with self.subTest(transport=transport):
                argv = relay.remote_command({"remote_host": "user@peer", "remote_script": path, "transport": transport})
                self.assertEqual(shlex.split(argv[-1]), ["/usr/bin/python3", path, "remote"])

    def test_openssh_uses_noninteractive_verified_connection(self):
        argv = relay.remote_command({"remote_host": "peer-alias", "remote_script": "/home/user/relay.py", "transport": "ssh"})
        self.assertEqual(argv[0], "/usr/bin/ssh")
        self.assertIn("-T", argv)
        self.assertIn("-oBatchMode=yes", argv)
        self.assertIn("-oStrictHostKeyChecking=yes", argv)
        self.assertIn("-oServerAliveInterval=15", argv)
        self.assertEqual(argv[-3:-1], ["--", "peer-alias"])

    def test_existing_config_keeps_tailscale_transport(self):
        sample = (Path(__file__).resolve().parents[1] / "config.example.toml").read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(sample.replace('transport = "ssh"\n', ''))
            config = relay.load_config(path)
            self.assertEqual(config["transport"], "tailscale")
            self.assertEqual(relay.remote_command(config)[:3], ["/usr/bin/tailscale", "ssh", "your-user@your-peer"])

    def test_invalid_transport_is_rejected(self):
        sample = (Path(__file__).resolve().parents[1] / "config.example.toml").read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            for value in ('"custom-command"', '[]', 'false'):
                path.write_text(sample.replace('transport = "ssh"', 'transport = ' + value))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    relay.load_config(path)
        with self.assertRaises(ValueError):
            relay.remote_command({"remote_host": "peer", "remote_script": "/relay.py", "transport": "other"})

    def test_config_rejects_unknown_fields_and_invalid_hosts(self):
        sample = (Path(__file__).resolve().parents[1] / "config.example.toml").read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(sample)
            self.assertEqual(relay.load_config(path)["initial_sync"], "none")
            self.assertEqual(relay.load_config(path)["transport"], "ssh")
            for content in [sample + '\nextra = true\n', sample.replace("your-user@your-peer", "-oProxyCommand=bad"), sample.replace('initial_sync = "none"', 'initial_sync = "yes"')]:
                path.write_text(content)
                with self.assertRaises(ValueError):
                    relay.load_config(path)


class ClipboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name})
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    async def test_apply_respects_pause_dedup_and_primary_selection(self):
        clipboard = relay.Clipboard("remote", AsyncMock(), "primary")
        write = AsyncMock(return_value=b"")
        with patch.object(relay, "command", write):
            await clipboard.apply(frame(selection="primary"))
            write.assert_not_awaited()
            clipboard.enabled = True
            await clipboard.apply(frame(selection="primary"))
            self.assertEqual(write.await_args.args[0], ["wl-copy", "--primary", "--type", relay.TEXT])
            self.assertEqual(write.await_args.kwargs["data"], b"hello")
            await clipboard.apply(frame(selection="primary"))
            self.assertEqual(write.await_count, 1)

    async def test_pause_while_waiting_for_lock_prevents_write(self):
        clipboard = relay.Clipboard("remote", AsyncMock())
        clipboard.enabled = True
        await clipboard.lock.acquire()
        with patch.object(relay, "command", AsyncMock()) as write:
            task = asyncio.create_task(clipboard.apply(frame()))
            await asyncio.sleep(0)
            clipboard.enabled = False
            clipboard.lock.release()
            await task
            write.assert_not_awaited()

    async def test_failed_start_closes_already_started_watchers(self):
        first, second = AsyncMock(), AsyncMock()
        second.start.side_effect = OSError("watcher failed")
        with self.assertRaises(OSError):
            await relay.start_clipboards({"clipboard": first, "primary": second})
        first.close.assert_awaited_once()
        second.close.assert_awaited_once()

    async def test_command_limit_and_timeout_kill_child(self):
        import sys
        with self.assertRaises(ValueError):
            await relay.command([sys.executable, "-c", "print('x' * 100)"], limit=5)
        with self.assertRaises(asyncio.TimeoutError):
            await relay.command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)

    async def test_handshake_allows_two_large_initial_captures(self):
        # Scale the handshake clock: a receiver can spend up to 24 seconds
        # capturing CLIPBOARD and PRIMARY before it sends its hello.
        accepted = asyncio.Event()
        never = asyncio.Event()
        process = MagicMock(returncode=None)
        process.wait = AsyncMock(return_value=0)
        process.stdin.drain = AsyncMock()
        async def read_hello():
            await asyncio.sleep(0.6)  # 30 seconds including SSH/startup overhead
            return json.dumps({"kind":"hello", "version":relay.WIRE_VERSION,
                               "max_bytes":8*1024*1024}).encode() + b"\n"
        process.stdout.readline = read_hello
        def clipboard(*args):
            item = MagicMock()
            item.start = AsyncMock()
            item.close = AsyncMock()
            item.monitor = never.wait
            return item
        wait_for = asyncio.wait_for
        async def scaled_wait(awaitable, timeout):
            return await wait_for(awaitable, timeout/50 if timeout in (20, 40) else timeout)
        negotiate = relay.negotiate_limit
        def ready(*args):
            negotiate(*args)
            accepted.set()
        with patch.object(relay, "Clipboard", clipboard), \
                patch.object(relay.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)), \
                patch.object(relay.asyncio, "wait_for", scaled_wait), \
                patch.object(relay, "negotiate_limit", ready), \
                patch.object(relay.sharing_state, "publish"), \
                patch.object(relay, "synergy_connected", return_value=False):
            task = asyncio.create_task(relay.coordinator({"transport":"ssh", "remote_host":"test",
                "remote_script":"/relay.py", "peer_id":"a"*64, "initial_sync":"none"}))
            try:
                await wait_for(accepted.wait(), 1.2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


class SecretTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name})
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def clipboard(self, selection="clipboard"):
        clipboard = relay.Clipboard("coordinator", AsyncMock(), selection)
        clipboard.enabled = True
        return clipboard

    async def test_secret_is_withheld_by_default(self):
        clipboard = self.clipboard()
        await clipboard.process((relay.TEXT, b"hunter2", True))
        clipboard.send.assert_not_awaited()
        self.assertTrue(relay.sharing_state.withheld_recent())
        await clipboard.process((relay.TEXT, b"plain", False))
        clipboard.send.assert_awaited_once()
        self.assertFalse(relay.sharing_state.withheld_recent())

    async def test_allowance_sends_one_marked_secret_then_expires(self):
        clipboard = self.clipboard()
        await clipboard.process((relay.TEXT, b"hunter2", True))
        relay.sharing_state.allow_secret()
        self.assertTrue(relay.sharing_state.secret_allowed())
        # The withheld copy goes out once allowed, without copying it again.
        await clipboard.process((relay.TEXT, b"hunter2", True))
        message = clipboard.send.await_args.args[0]
        self.assertIs(message["sensitive"], True)
        self.assertFalse(relay.sharing_state.secret_allowed())
        await clipboard.process((relay.TEXT, b"second-secret", True))
        self.assertEqual(clipboard.send.await_count, 1)

    async def test_highlighted_secret_never_uses_the_allowance(self):
        clipboard = self.clipboard("primary")
        relay.sharing_state.allow_secret()
        await clipboard.process((relay.TEXT, b"hunter2", True))
        clipboard.send.assert_not_awaited()
        self.assertTrue(relay.sharing_state.secret_allowed())

    async def test_paused_secret_does_not_consume_allowance(self):
        clipboard = self.clipboard()
        clipboard.enabled = False
        relay.sharing_state.allow_secret()
        await clipboard.process((relay.TEXT, b"hunter2", True))
        self.assertTrue(relay.sharing_state.secret_allowed())

    async def test_expired_or_far_future_allowance_is_refused(self):
        relay.sharing_state.allow_secret(-1)
        self.assertFalse(relay.sharing_state.secret_allowed())
        relay.sharing_state.allow_secret(3600)
        self.assertFalse(relay.sharing_state.secret_allowed())

    async def test_seed_never_sends_a_secret(self):
        clipboard = self.clipboard()
        with patch.object(clipboard, "snapshot", AsyncMock(return_value=(relay.TEXT, b"hunter2", True))):
            await clipboard.seed()
        clipboard.send.assert_not_awaited()

    async def test_received_secret_keeps_its_marker(self):
        clipboard = relay.Clipboard("remote", AsyncMock())
        clipboard.enabled = True
        write = AsyncMock(return_value=b"")
        with patch.object(relay, "command", write), patch.object(relay, "wl_copy_sensitive", return_value=True):
            await clipboard.apply({**frame(b"hunter2"), "sensitive": True})
            self.assertEqual(write.await_args.args[0], ["wl-copy", "--sensitive", "--type", relay.TEXT])
            await clipboard.apply(frame(b"plain"))
            self.assertEqual(write.await_args.args[0], ["wl-copy", "--type", relay.TEXT])


class SecretSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name}); self.env.start()

    async def asyncTearDown(self):
        self.env.stop(); self.temp.cleanup()

    async def snapshot(self, types, url):
        from test_clipboard_offer import CaptureServer
        values = {mime: (url if mime == relay.sharing_state.SOURCE_URL else b"fixture") for mime in types}
        with CaptureServer(values):
            clipboard = relay.Clipboard("coordinator", AsyncMock())
            return await clipboard.snapshot()

    async def test_proton_pass_extension_copy_is_secret_without_hint(self):
        url = b"chrome-extension://ghmbeldphafepmbegfdlkpapadhbakde/popup.html#/item/x"
        self.assertTrue((await self.snapshot([relay.TEXT, relay.sharing_state.SOURCE_URL], url))[2])

    async def test_proton_pass_desktop_origin_is_secret_without_hint(self):
        for url in (b"https://pass.proton.me/", b"https://pass.proton.me/u/0/"):
            with self.subTest(desktop_origin=True):
                self.assertTrue((await self.snapshot([relay.TEXT, relay.sharing_state.SOURCE_URL], url))[2])

    async def test_similar_origins_do_not_match_proton_pass(self):
        for url in (b"https://pass.proton.me.example.com/", b"https://example.com/pass.proton.me/",
                    b"https://pass.proton.me@evil.example/", b"http://pass.proton.me/"):
            with self.subTest(nonmatching_origin=True):
                self.assertFalse((await self.snapshot([relay.TEXT, relay.sharing_state.SOURCE_URL], url))[2])

    async def test_ordinary_browser_copy_is_not_secret(self):
        self.assertFalse((await self.snapshot([relay.TEXT, relay.sharing_state.SOURCE_URL], b"https://example.com/"))[2])
        self.assertFalse((await self.snapshot([relay.TEXT], None))[2])

    async def test_unreadable_browser_source_is_withheld(self):
        for url in (None, b"", b"\xff"):
            with self.subTest(source_unreadable=True):
                self.assertTrue((await self.snapshot([relay.TEXT, relay.sharing_state.SOURCE_URL], url))[2])


class InstallTests(unittest.TestCase):
    def test_install_is_private_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            targets = install.install(home)
            self.assertEqual(targets[1].stat().st_mode & 0o777, 0o600)
            targets[0].write_text("keep existing file")
            with self.assertRaises(FileExistsError):
                install.install(home)
            self.assertEqual(targets[0].read_text(), "keep existing file")

    def test_remote_install_has_no_service(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            self.assertEqual(len(install.install(home, True)), 3)
            self.assertFalse((home / ".config").exists())


if __name__ == "__main__":
    unittest.main()
