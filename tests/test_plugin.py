import asyncio
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import plugin
import relay
import sharing_state
from synergy_plugin import jobs, pairing, runtime, storage

PEER = "a"*64
MINE = "b"*64
CHECKS = dict(python=True, wl_clipboard=True, wayland=True, data_control=True)


class PrivateHome(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        home = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home/"config"),
          "XDG_STATE_HOME": str(home/"state"), "XDG_RUNTIME_DIR": str(home/"runtime")})
        self.environment.start()
        (home/"runtime").mkdir()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()


class StateTests(PrivateHome):
    def test_pause_persists_across_processes(self):
        sharing_state.set_paused(True)
        result = subprocess.run(["/usr/bin/python3", "-c", "import sharing_state; assert sharing_state.paused()"], check=True)
        self.assertEqual(result.returncode, 0)
        sharing_state.set_paused(False)
        self.assertFalse(sharing_state.paused())

    def test_metadata_is_private_and_stale_or_reused_pid_is_rejected(self):
        sharing_state.publish("source", "sharing")
        self.assertEqual(sharing_state.status_path().stat().st_mode & 0o777, 0o600)
        self.assertEqual(sharing_state.read_status()["state"], "sharing")
        value = json.loads(sharing_state.status_path().read_text())
        for change in ({"updated": time.time()-20}, {"process_start": "wrong"}, {"pid": -1}):
            sharing_state.atomic_write(sharing_state.status_path(), json.dumps(value | change).encode())
            self.assertIsNone(sharing_state.read_status())

    def test_transaction_restores_files_after_partial_install(self):
        target = storage.install_dir()/"relay.py"
        sharing_state.atomic_write(target, b"previous source", 0o700)
        transaction = storage.Transaction(storage.fingerprint())
        transaction.install()
        self.assertNotEqual(target.read_bytes(), b"previous source")
        transaction.restore()
        self.assertEqual(target.read_bytes(), b"previous source")
        self.assertFalse((storage.install_dir()/"plugin.py").exists())
        self.assertTrue((transaction.backup/"manifest.json").is_file())

    def test_changed_installation_invalidates_transaction(self):
        fingerprint = storage.fingerprint()
        sharing_state.atomic_write(storage.role_path(), b'{"role":"receiver"}')
        with self.assertRaises(ValueError):
            storage.Transaction(fingerprint)

    def test_pause_symlink_never_resumes(self):
        sharing_state.config_dir().mkdir(parents=True)
        (sharing_state.config_dir()/"paused").symlink_to("missing")
        self.assertTrue(sharing_state.paused())
        with self.assertRaises(ValueError):
            sharing_state.set_paused(False)

    def test_limit_pending_request_survives_old_ack_then_converges(self):
        sharing_state.save_limit(128, "a"*32, pending=True)
        self.assertFalse(sharing_state.save_limit(64, "b"*32, adopt=True))
        self.assertFalse(sharing_state.save_limit(64, "b"*32, acknowledge=True))
        self.assertEqual(sharing_state.limit_record()["max_mib"], 128)
        self.assertTrue(sharing_state.save_limit(128, "a"*32, acknowledge=True))
        self.assertFalse(sharing_state.limit_record()["pending"])
        self.assertTrue(sharing_state.save_limit(32, "c"*32, adopt=True))
        self.assertEqual(sharing_state.local_limit(), 32)


class PairingTests(PrivateHome):
    def setUp(self):
        super().setUp()
        self.local = patch.object(runtime, "settings", return_value={"my_id": MINE, "name": "Source", "peers": [{"id": PEER, "name": "Receiver", "hostname": "receiver"}]})
        self.requirements = patch.object(runtime, "prerequisites", return_value=CHECKS)
        self.services = patch.object(runtime, "service", return_value=False)
        self.manager = patch.object(runtime, "reload_manager")
        self.local.start(); self.requirements.start()
        self.service = self.services.start(); self.manager.start()
        self.peer = {"app": "omarchy-synergy", "wire_version": sharing_state.WIRE_VERSION,
                     "bundle": storage.bundle_digest(), "role": "receiver", "checks": CHECKS,
                     "synergy_id": PEER, "name": "Receiver", "user": "peer-user",
                     "remote_script": "/home/peer-user/.local/lib/synergy-clipboard/relay.py", "max_mib": 32, "max_supported_mib": 128}
        self.remote = patch.object(pairing, "remote_endpoint", return_value=self.peer)
        self.remote.start()
        self.request = {"transport": "ssh", "remote_host": "receiver-alias", "peer_id": PEER, "initial_sync": "none", "max_mib": 64}

    def tearDown(self):
        self.remote.stop(); self.manager.stop(); self.services.stop(); self.requirements.stop(); self.local.stop()
        super().tearDown()

    def test_check_is_read_only_and_selects_pair_limit_without_matching_presets(self):
        preview = pairing.check_source(self.request)
        self.assertEqual(preview["max_mib"], 64)
        self.assertFalse(storage.config_path().exists())
        self.assertFalse(storage.install_dir().exists())
        self.service.assert_not_called()

    def test_wrong_peer_version_role_and_capabilities_are_rejected(self):
        for change in ({"synergy_id": MINE}, {"wire_version": 3}, {"bundle": "different"}, {"role": "source"}, {"checks": CHECKS | {"data_control": False}}):
            with self.subTest(change=change), patch.object(pairing, "remote_endpoint", return_value=self.peer | change):
                with self.assertRaises(ValueError): pairing.check_source(self.request)
        self.assertFalse(storage.config_path().exists())

    def test_changed_or_unconfirmed_review_never_stops_service(self):
        preview = pairing.check_source(self.request)
        for request in (self.request | {"token": preview["token"]}, self.request | {"confirm": True, "token": "wrong"}, self.request | {"confirm": True, "token": preview["token"], "max_mib": 16}):
            with self.assertRaises(ValueError): pairing.apply_source(request)
        self.service.assert_not_called()

    def test_successful_pair_installs_stable_paths_and_preserves_pause(self):
        sharing_state.set_paused(True)
        preview = pairing.check_source(self.request)
        pairing.apply_source(self.request | {"confirm": True, "token": preview["token"]})
        self.assertEqual(relay.load_config(storage.config_path())["remote_host"], "receiver-alias")
        self.assertEqual(storage.role(), "source")
        self.assertTrue(sharing_state.paused())
        self.assertTrue((storage.install_dir()/"sharing_state.py").exists())
        self.assertIn("%h/.local/lib/synergy-clipboard/relay.py", storage.unit_path().read_text())

    def test_failed_enable_restores_previous_source_configuration(self):
        old = b'old private configuration'
        sharing_state.atomic_write(storage.config_path(), old)
        preview = pairing.check_source(self.request)
        def service(action):
            if action == "enable": raise ValueError("enable failed")
            return False
        with patch.object(runtime, "service", side_effect=service), self.assertRaises(ValueError):
            pairing.apply_source(self.request | {"confirm": True, "token": preview["token"]})
        self.assertEqual(storage.config_path().read_bytes(), old)
        self.assertFalse((storage.install_dir()/"relay.py").exists())

    def test_receiver_requires_review_and_refuses_source_role(self):
        preview = pairing.receiver_preview({"max_mib": 64})
        with self.assertRaises(ValueError): pairing.prepare_receiver({"confirm": True, "token": "wrong"})
        pairing.prepare_receiver({"confirm": True, "token": preview["token"], "max_mib": 64})
        self.assertEqual(storage.role(), "receiver")
        self.assertEqual(sharing_state.local_limit(), 64)
        sharing_state.atomic_write(storage.config_path(), b"existing source")
        with self.assertRaises(ValueError): pairing.receiver_preview()

    def test_receiver_pause_does_not_start_a_coordinator(self):
        sharing_state.atomic_write(storage.role_path(), b'{"role":"receiver"}')
        pairing.control("pause")
        self.assertTrue(sharing_state.paused())
        self.service.assert_not_called()

    def test_limit_change_is_a_pair_request_without_repair_or_service_restart(self):
        sharing_state.atomic_write(storage.role_path(), b'{"role":"receiver"}')
        with patch.object(runtime, "status", return_value={"runtime_matches": True}):
            pairing.control("set_limit", {"max_mib": 128})
        self.assertTrue(sharing_state.limit_record()["pending"])
        self.assertEqual(sharing_state.local_limit(), 128)
        self.assertFalse(storage.config_path().exists())
        self.service.assert_not_called()


class TransportTests(PrivateHome):
    def test_probe_uses_selected_transport_and_quotes_remote_program(self):
        response = {"app": "omarchy-synergy"}
        for transport in ("ssh", "tailscale"):
            with patch.object(runtime, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(response).encode(), b"")) as run, patch("shutil.which", return_value="present"):
                self.assertEqual(pairing.remote_endpoint(transport, "peer-alias"), response)
                argv = run.call_args.args[0]
                self.assertEqual(argv[0], "/usr/bin/ssh" if transport == "ssh" else "/usr/bin/tailscale")
                self.assertIn("peer-alias", argv)
        for host in ("-oProxyCommand=bad", "peer; echo bad", "peer\nother"):
            with self.assertRaises(ValueError): pairing.remote_endpoint("ssh", host)

    def test_auth_and_host_trust_failures_are_distinct_and_sanitized(self):
        for stderr, expected in [(b"Host key verification failed. private details", "host verification"), (b"Permission denied (publickey).", "authentication"), (b"no route private-address", "SSH or receiver")]:
            with patch.object(runtime, "run", return_value=subprocess.CompletedProcess([], 255, b"", stderr)), patch("shutil.which", return_value="present"), self.assertRaisesRegex(ValueError, expected) as error:
                pairing.remote_endpoint("ssh", "peer")
            self.assertNotIn("private", str(error.exception))

    def test_vendor_response_is_allowlisted(self):
        data = {"data": {"myId": MINE, "computers": [{"id": MINE, "name": "source", "serial": "SECRET"}, {"id": PEER, "name": "peer"}], "serial": "SECRET", "coreRunning": True}}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            result = runtime.settings()
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(len(result["peers"]), 1)


class LimitTests(unittest.TestCase):
    def test_larger_text_and_wire_limit_and_smaller_endpoint(self):
        with patch.object(relay, "MAX_BYTES"), patch.object(relay, "MAX_LINE"):
            relay.set_limit(16*1024*1024)
            data = b"x"*(9*1024*1024)
            message = {"kind": "clipboard", "selection": "clipboard", "mime": relay.TEXT,
                       "payload": base64.b64encode(data).decode(), "digest": relay.digest(relay.TEXT, data)}
            self.assertEqual(relay.decode_clipboard(relay.parse_message(json.dumps(message).encode()))[1], data)
            self.assertEqual(relay.negotiate_limit(8*1024*1024, 64*1024*1024), 8*1024*1024)
            with self.assertRaises(ValueError): relay.decode_clipboard(message)

    def test_limits_reject_invalid_types_and_bounds(self):
        for value in (0, 129, True, "64", [], -1):
            with self.assertRaises(ValueError): sharing_state.validate_limit(value)
        with patch.object(relay, "MAX_BYTES"), patch.object(relay, "MAX_LINE"):
            for value in (None, True, 0, -1):
                with self.assertRaises(ValueError): relay.negotiate_limit(value, 8*1024*1024)


class JobTests(PrivateHome):
    def test_durable_job_result_and_private_request_cleanup(self):
        with patch("subprocess.Popen") as spawn:
            job = jobs.start({"action": "prepare_receiver", "confirm": True}, Path("plugin.py"))["job"]
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertTrue(jobs.result(job)["pending"])
        jobs.execute(job, lambda request: {"message": "completed"})
        self.assertEqual(jobs.result(job)["message"], "completed")
        self.assertFalse(jobs.path(job, ".request").exists())
        self.assertEqual(jobs.path(job, ".result").stat().st_mode & 0o777, 0o600)

    def test_job_ids_and_unknown_actions_are_rejected(self):
        for value in ("../file", "0"*31, None):
            with self.assertRaises(ValueError): jobs.result(value)
        with self.assertRaises(ValueError): plugin.dispatch({"action": "execute", "command": "anything"})


class CaptureLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_default_follows_the_updated_pair_limit(self):
        command = ["/usr/bin/python3", "-c", "import sys;sys.stdout.buffer.write(b'x'*(9*1024*1024))"]
        with patch.object(relay, "MAX_BYTES"), patch.object(relay, "MAX_LINE"):
            relay.set_limit(16*1024*1024)
            self.assertEqual(len(await relay.command(command)), 9*1024*1024)
            relay.set_limit(8*1024*1024)
            with self.assertRaises(ValueError): await relay.command(command)


if __name__ == "__main__":
    unittest.main()
