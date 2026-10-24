"""Private metadata and persistent user pause; never stores clipboard payloads."""
import json
import fcntl
import os
from pathlib import Path
import tempfile
import time
import uuid

WIRE_VERSION = 5
MAX_MIB = 128


def validate_limit(value):
    if type(value) is not int or not 1 <= value <= MAX_MIB:
        raise ValueError("Image/text limit must be a whole number from 1 to 128 MiB.")
    return value


def validate_limit_id(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid transfer-limit request.")
    return value


def limit_record(default=8):
    path = config_dir() / "limits.json"
    if not path.exists():
        return {"max_mib": validate_limit(default), "request_id": "0"*32, "pending": False}
    value = json.loads(path.read_text())
    validate_limit(value["max_mib"])
    identifier = value.get("request_id", "0"*32)
    validate_limit_id(identifier)
    return {"max_mib": value["max_mib"], "request_id": identifier, "pending": value.get("pending") is True}


def local_limit(default=8):
    return limit_record(default)["max_mib"]


def save_limit(value, identifier=None, *, pending=False, adopt=False, acknowledge=False):
    validate_limit(value)
    identifier = uuid.uuid4().hex if identifier is None else validate_limit_id(identifier)
    config_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(config_dir()/"limits.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = limit_record()
        if acknowledge and previous["request_id"] != identifier:
            return False
        if adopt and previous["pending"] and previous["request_id"] != identifier:
            return False
        new = {"max_mib": value, "request_id": identifier, "pending": pending}
        if new != previous:
            atomic_write(config_dir()/"limits.json", json.dumps(new).encode())
    return True


def config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "synergy-clipboard"


def status_path():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "synergy-clipboard-status.json"


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("refusing a symlink destination")
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def paused():
    path = config_dir() / "paused"
    # A broken link is a pause too; do not turn an ambiguous request into resume.
    return path.exists() or path.is_symlink()


def set_paused(value):
    path = config_dir() / "paused"
    if value:
        atomic_write(path, b"paused\n")
    else:
        if path.is_symlink():
            raise ValueError("refusing a symlink pause flag")
        path.unlink(missing_ok=True)


# Password managers mark copies with this KDE convention; wl-copy --sensitive sets it.
SECRET_HINT = "x-kde-passwordManagerHint"
SECRET_WINDOW = 60


def runtime_dir():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


def secret_allowance_path():
    return runtime_dir() / "synergy-clipboard-secret-allow"


def withheld_path():
    return runtime_dir() / "synergy-clipboard-secret-withheld"


def _read_time(path):
    # Runtime-only flags: a reboot or logout always clears them.
    try:
        if path.is_symlink() or path.stat().st_uid != os.getuid():
            return None
        return float(path.read_bytes()[:64])
    except (OSError, ValueError):
        return None


def allow_secret(seconds=SECRET_WINDOW):
    atomic_write(secret_allowance_path(), str(time.time() + seconds).encode())


def secret_allowed():
    until = _read_time(secret_allowance_path())
    return until is not None and time.time() < until <= time.time() + SECRET_WINDOW


def consume_secret_allowance():
    """One-shot: the allowance covers exactly one secret transfer."""
    allowed = secret_allowed()
    cancel_secret()
    return allowed


def cancel_secret():
    path = secret_allowance_path()
    if not path.is_symlink():
        path.unlink(missing_ok=True)


def note_withheld():
    atomic_write(withheld_path(), str(time.time()).encode())


def clear_withheld():
    path = withheld_path()
    if not path.is_symlink():
        path.unlink(missing_ok=True)


def withheld_recent(seconds=120):
    at = _read_time(withheld_path())
    return at is not None and 0 <= time.time() - at < seconds


def process_start(pid):
    # comm can contain spaces; fields after the final ')' start at field 3.
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def publish(role, state, **metadata):
    data = {"version": 1, "wire_version": WIRE_VERSION, "role": role,
            "state": state, "pid": os.getpid(), "process_start": process_start(os.getpid()),
            "updated": time.time(), **metadata}
    atomic_write(status_path(), json.dumps(data).encode())


def read_status():
    path = status_path()
    try:
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_size > 4096:
            return None
        data = json.loads(path.read_text())
        pid = data["pid"]
        if not isinstance(pid, int) or pid <= 0 or time.time() - data["updated"] > 6:
            return None
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid() or process_start(pid) != data["process_start"]:
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
