"""Versioned user-local installation, previews and reversible file updates."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

import sharing_state

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = ("relay.py", "sharing_state.py", "plugin.py", "synergy_plugin/__init__.py",
                 "synergy_plugin/storage.py", "synergy_plugin/runtime.py", "synergy_plugin/pairing.py", "synergy_plugin/jobs.py",
                 "synergy-clipboard.service")


def install_dir():
    return Path.home() / ".local/lib/synergy-clipboard"


def config_path():
    return sharing_state.config_dir() / "config.toml"


def role_path():
    return sharing_state.config_dir() / "role.json"


def unit_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config")) / "systemd/user/synergy-clipboard.service"


def bundle_digest(root=ROOT):
    digest = hashlib.sha256()
    for name in RUNTIME_FILES:
        digest.update(name.encode() + b"\0" + (root/name).read_bytes())
    return digest.hexdigest()


def destinations():
    return [install_dir()/name for name in RUNTIME_FILES] + [config_path(), role_path(), unit_path(), sharing_state.config_dir()/"limits.json"]


def fingerprint():
    digest = hashlib.sha256()
    for path in destinations():
        if path.is_symlink():
            raise ValueError("An installation destination is a symlink; resolve it before setup.")
        value = path.read_bytes() if path.exists() else b"<absent>"
        digest.update(str(path).encode() + b"\0" + value)
    return digest.hexdigest()


class Transaction:
    def __init__(self, expected):
        if fingerprint() != expected:
            raise ValueError("The existing setup changed. Run the connection check again.")
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local/state"))
        parent = state_home/"synergy-clipboard/backups"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-"), dir=parent))
        self.before = {}
        for index, path in enumerate(destinations()):
            data = path.read_bytes() if path.exists() else None
            mode = path.stat().st_mode & 0o777 if data is not None else 0o600
            self.before[path] = (data, mode)
            if data is not None:
                sharing_state.atomic_write(self.backup/str(index), data, mode)
        sharing_state.atomic_write(self.backup/"manifest.json", json.dumps({str(path): {"file": str(i) if data is not None else None, "mode": mode} for i, (path, (data, mode)) in enumerate(self.before.items())}).encode())

    def install(self):
        for name in RUNTIME_FILES:
            sharing_state.atomic_write(install_dir()/name, (ROOT/name).read_bytes(), 0o700 if name in {"relay.py", "plugin.py"} else 0o600)

    def restore(self):
        for path, (data, mode) in self.before.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                sharing_state.atomic_write(path, data, mode)


def role():
    if config_path().exists():
        return "source"
    try:
        data = json.loads(role_path().read_text())
        return "receiver" if data.get("role") == "receiver" else "unconfigured"
    except (OSError, ValueError, AttributeError):
        return "unconfigured"
