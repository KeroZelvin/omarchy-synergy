"""Private setup jobs survive a widget reload; service work is serialized."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import sharing_state


def directory():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local/state"))/"synergy-clipboard/jobs"


def path(job, suffix):
    if not isinstance(job, str) or len(job) != 32 or any(c not in "0123456789abcdef" for c in job):
        raise ValueError("Invalid setup job.")
    return directory()/(job+suffix)


def start(request, script):
    job = uuid.uuid4().hex
    sharing_state.atomic_write(path(job, ".request"), json.dumps({"created": time.time(), "request": request}).encode())
    try:
        subprocess.Popen([sys.executable, str(script), "job", job], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except BaseException:
        path(job, ".request").unlink(missing_ok=True)
        raise
    return {"job": job, "pending": True}


def result(job):
    output = path(job, ".result")
    if output.exists():
        if output.is_symlink() or output.stat().st_size > 65536:
            raise ValueError("Invalid setup job result.")
        return json.loads(output.read_text())
    request = path(job, ".request")
    if not request.exists() or time.time() - request.stat().st_mtime > 120:
        raise ValueError("The setup job did not complete. Check the service and saved backup before trying again.")
    return {"job": job, "pending": True}


def execute(job, handler):
    request_path = path(job, ".request")
    try:
        if request_path.is_symlink() or request_path.stat().st_size > 65536:
            raise ValueError("Invalid setup job request.")
        data = json.loads(request_path.read_text())
        if time.time()-data["created"] > 120:
            raise ValueError("The setup review expired. Run it again.")
        lock = sharing_state.config_dir()/"setup.lock"
        lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            output = {"ok": True, **handler(data["request"])}
    except BlockingIOError:
        output = {"ok": False, "error": "Another setup is running. Wait for it to finish."}
    except subprocess.TimeoutExpired:
        output = {"ok": False, "error": "The setup connection timed out; review the current service state before retrying."}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        output = {"ok": False, "error": str(error) if isinstance(error, ValueError) else "Setup failed; review the current service state and private backup."}
    sharing_state.atomic_write(path(job, ".result"), json.dumps(output).encode())
    request_path.unlink(missing_ok=True)
