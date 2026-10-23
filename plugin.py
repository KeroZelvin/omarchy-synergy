#!/usr/bin/env python3
"""Bounded JSON backend for the Omarchy panel; credentials stay in SSH/Synergy."""
import json
import os
from pathlib import Path
import subprocess
import sys

from synergy_plugin import pairing, runtime, jobs


def dispatch(request):
    if not isinstance(request, dict):
        raise ValueError("Invalid setup request.")
    action = request.get("action")
    if action == "status":
        return runtime.status()
    if action == "job":
        return jobs.result(request.get("job"))
    if action == "bootstrap":
        return pairing.bootstrap()
    if action == "receiver_preview":
        return pairing.receiver_preview(request)
    if action == "prepare_receiver":
        return pairing.prepare_receiver(request)
    if action == "check_source":
        return pairing.check_source(request)
    if action == "apply_source":
        return pairing.apply_source(request)
    if action in {"pause", "resume", "reconnect"}:
        return pairing.control(action)
    raise ValueError("Unsupported setup action.")


def main():
    os.umask(0o077)
    try:
        if sys.argv[1:] == ["endpoint"]:
            result = runtime.endpoint()
        elif len(sys.argv) == 3 and sys.argv[1] == "job":
            jobs.execute(sys.argv[2], dispatch)
            return
        elif sys.argv[1:] == ["rpc"]:
            line = sys.stdin.buffer.readline(65537)
            if len(line) > 65536:
                raise ValueError("Setup request exceeded the limit.")
            request = json.loads(line)
            value = (jobs.start(request, Path(__file__).resolve()) if isinstance(request, dict) and request.get("action") in {"prepare_receiver", "apply_source"} else dispatch(request))
            result = {"ok": True, **value}
        else:
            raise ValueError("Use rpc or endpoint.")
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": "The connection check timed out. Verify the selected SSH route and receiver setup."}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Never echo a raw vendor response or captured command output.
        result = {"ok": False, "error": str(error) if isinstance(error, ValueError) else "Setup failed. Check the prerequisites and user service journal."}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
