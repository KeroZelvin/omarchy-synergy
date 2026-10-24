"""Explicit receiver preparation, verified pair review and source activation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import time

import relay
import sharing_state
from . import runtime, storage


def token(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def require_checks(checks):
    missing = [name for name in ("python", "wl_clipboard", "wayland", "data_control") if checks.get(name) is not True]
    if missing:
        raise ValueError("Missing requirements: " + ", ".join(missing) + ". See the setup guide.")


def bootstrap():
    status = runtime.status()
    try:
        synergy = runtime.settings()
    except (OSError, ValueError, KeyError):
        synergy = {"peers": [], "name": "This computer", "my_id": None}
    return {**status, "peers": synergy["peers"], "name": synergy["name"],
            "user": __import__("getpass").getuser(), "hostname": __import__("socket").gethostname(),
            "remote_script": str(storage.install_dir()/"relay.py")}


def receiver_preview(request=None):
    if storage.config_path().exists() or runtime.service("is-active") or runtime.service("is-enabled"):
        raise ValueError("This computer is configured as a source. Pause and remove that pairing before making it a receiver.")
    checks = runtime.prerequisites()
    require_checks(checks)
    mine = runtime.settings()
    if not isinstance(mine["my_id"], str) or not re.fullmatch("[a-f0-9]{64}", mine["my_id"]):
        raise ValueError("Sign into Synergy on this computer before preparing it.")
    current = storage.fingerprint()
    limit = sharing_state.validate_limit((request or {}).get("max_mib", 8))
    return {"role": "receiver", "checks": checks, "name": mine["name"],
            "changes": "Install or update the user-local companion. Keep SSH trust and portal settings. No coordinator is started.",
            "max_mib": limit, "fingerprint": current, "token": token({"files": current, "bundle": storage.bundle_digest(), "max_mib": limit})}


def prepare_receiver(request):
    preview = receiver_preview(request)
    if request.get("confirm") is not True or request.get("token") != preview["token"]:
        raise ValueError("Review receiver preparation again before applying it.")
    transaction = storage.Transaction(preview["fingerprint"])
    try:
        transaction.install()
        sharing_state.atomic_write(storage.role_path(), b'{"role":"receiver"}\n')
        sharing_state.save_limit(preview["max_mib"])
    except BaseException:
        transaction.restore()
        raise
    return {"message": "Receiver ready. Run Pair on the keyboard/mouse source using this computer's SSH address.",
            "backup": str(transaction.backup), **bootstrap()}


def remote_endpoint(transport, host):
    if transport not in {"ssh", "tailscale"}:
        raise ValueError("Choose Direct LAN (SSH) or Tailscale (SSH).")
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*", host):
        raise ValueError("Enter an SSH alias or USER@HOST, without command options.")
    if not shutil.which("ssh" if transport == "ssh" else "tailscale"):
        raise ValueError("The selected SSH transport is not installed.")
    args = relay.remote_command({"transport": transport, "remote_host": host, "remote_script": "/unused"})
    code = "import runpy,sys;from pathlib import Path;p=Path.home()/'.local/lib/synergy-clipboard/plugin.py';sys.path.insert(0,str(p.parent));sys.argv=['plugin.py','endpoint'];runpy.run_path(str(p),run_name='__main__')"
    args[-1] = shlex.join(["/usr/bin/python3", "-c", code])
    result = runtime.run(args, timeout=25)
    if result.returncode:
        error = result.stderr.decode(errors="replace").lower()
        if "host key" in error or "host identification" in error:
            raise ValueError("SSH host verification failed. Verify the fingerprint in a terminal; this wizard never changes trust.")
        if "permission denied" in error or "authentication" in error:
            raise ValueError("SSH authentication failed. Establish noninteractive SSH access first.")
        raise ValueError("SSH or receiver check failed. Prepare the receiver with the same plugin version and test SSH in a terminal.")
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError("The receiver returned an invalid setup response.") from None
    if not isinstance(value, dict) or value.get("app") != "omarchy-synergy":
        raise ValueError("This SSH endpoint is not a prepared omarchy-synergy receiver.")
    return value


def check_source(request):
    require_checks(runtime.prerequisites())
    synergy = runtime.settings()
    selected = next((p for p in synergy["peers"] if p["id"] == request.get("peer_id")), None)
    if selected is None:
        raise ValueError("Choose the receiving computer from Synergy's paired devices. Pair it in Synergy first.")
    mode = request.get("transport")
    host = request.get("remote_host")
    remote = remote_endpoint(mode, host)
    if remote.get("wire_version") != sharing_state.WIRE_VERSION or remote.get("bundle") != storage.bundle_digest():
        raise ValueError("The receiver version differs. Prepare it with the same plugin checkout before pairing.")
    if remote.get("role") != "receiver":
        raise ValueError("The other computer must be prepared as a receiver, not a second source.")
    require_checks(remote.get("checks", {}))
    if remote.get("synergy_id") != selected["id"] or remote.get("synergy_id") == synergy["my_id"]:
        raise ValueError("The SSH endpoint does not match the selected Synergy computer.")
    initial = request.get("initial_sync", "none")
    if initial not in {"none", "source"}:
        raise ValueError("Invalid initial selection policy.")
    config = {"transport": mode, "remote_host": host, "remote_script": remote.get("remote_script"),
              "peer_id": selected["id"], "initial_sync": initial,
              "max_mib": sharing_state.validate_limit(request.get("max_mib", 8))}
    supported = sharing_state.validate_limit(remote.get("max_supported_mib"))
    if config["max_mib"] > supported:
        raise ValueError("The receiver does not support this transfer limit.")
    effective_limit = config["max_mib"]
    script = config["remote_script"]
    if not isinstance(script, str) or not script.startswith("/") or any(c in script for c in "\x00\r\n"):
        raise ValueError("The receiver supplied an invalid companion path.")
    fingerprint = storage.fingerprint()
    review = {"config": config, "fingerprint": fingerprint, "remote_bundle": remote["bundle"],
              "receiver": str(remote.get("name", ""))[:128], "receiver_user": str(remote.get("user", ""))[:128], "max_mib": effective_limit}
    return {**review, "token": token(review), "checks": remote["checks"],
            "changes": "Save this pairing, install or update the user-local companion and enable its source service. Existing files are backed up. " +
            ("Replace the receiver's supported selections once on each new SSH connection." if initial == "source" else "Share future changes only; keep existing selections on connection.")}


def apply_source(request):
    preview = check_source(request)  # Reverify endpoint identity and files at confirmation.
    if request.get("confirm") is not True or request.get("token") != preview["token"]:
        raise ValueError("The pairing changed. Run the connection check and review it again.")
    was_active = runtime.service("is-active")
    was_enabled = runtime.service("is-enabled")
    transaction = storage.Transaction(preview["fingerprint"])
    try:
        runtime.service("stop")
        transaction.install()
        sharing_state.atomic_write(storage.config_path(), ("\n".join(f"{key} = {json.dumps(value)}" for key, value in preview["config"].items()) + "\n").encode())
        sharing_state.atomic_write(storage.role_path(), b'{"role":"source"}\n')
        sharing_state.save_limit(preview["config"]["max_mib"], pending=True)
        sharing_state.atomic_write(storage.unit_path(), (storage.ROOT/"synergy-clipboard.service").read_bytes())
        runtime.reload_manager()
        runtime.service("enable")
        runtime.service("start")
    except BaseException:
        runtime.service("stop")
        transaction.restore()
        runtime.reload_manager()
        runtime.service("enable" if was_enabled else "disable")
        if was_active:
            runtime.service("start")
        raise
    return {"message": "Pairing saved. Sharing starts when SSH and Synergy are connected and neither endpoint is paused.",
            "backup": str(transaction.backup), **bootstrap()}


def control(action, request=None):
    role = storage.role()
    if role == "unconfigured":
        raise ValueError("Prepare or pair this computer first.")
    if action == "set_limit":
        if not runtime.status().get("runtime_matches"):
            raise ValueError("Update this companion using Setup before changing the pair limit.")
        sharing_state.save_limit((request or {}).get("max_mib"), pending=True)
    elif action == "pause":
        sharing_state.set_paused(True)
        if role == "source":
            runtime.service("stop")
    elif action == "resume":
        if not runtime.status().get("runtime_matches"):
            raise ValueError("Update this companion using Setup before resuming.")
        sharing_state.set_paused(False)
        if role == "source":
            runtime.service("start")
    elif action == "allow_secret":
        sharing_state.allow_secret()
    elif action == "cancel_secret":
        sharing_state.cancel_secret()
    elif action == "reconnect":
        if role == "source":
            runtime.service("restart")
        else:
            status = sharing_state.read_status()
            if status and status["role"] == "receiver":
                os.kill(status["pid"], signal.SIGTERM)
    else:
        raise ValueError("Unsupported sharing action.")
    return {"message": {"pause": "Clipboard sharing paused. The pause survives restarts.",
                        "set_limit": "Transfer limit saved for both computers. It synchronizes when the encrypted connection is available.",
                        "resume": "Resume requested; waiting for the connection and Synergy.",
                        "reconnect": "Reconnect requested.",
                        "allow_secret": f"The next password-manager copy on this computer is shared within {sharing_state.SECRET_WINDOW} seconds — or the one you just copied.",
                        "cancel_secret": "Secret sharing cancelled."}[action], **runtime.status()}
