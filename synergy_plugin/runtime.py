"""Allowlisted local status and endpoint prerequisites; never reads clipboard data."""
import ctypes
import ctypes.util
import getpass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.request

import relay
import sharing_state
from . import VERSION
from . import storage


def run(args, *, timeout=12, input=None):
    result = subprocess.run(args, input=input, capture_output=True, timeout=timeout)
    if len(result.stdout) + len(result.stderr) > 262144:
        raise ValueError("Command output exceeded the setup limit.")
    return result


def service(action):
    if action not in {"start", "stop", "restart", "enable", "disable", "is-active", "is-enabled"}:
        raise ValueError("Unsupported service action.")
    result = run(["systemctl", "--user", action, "synergy-clipboard.service"])
    if action.startswith("is-"):
        return result.returncode == 0
    if result.returncode:
        raise ValueError("The clipboard user service could not be changed. Check its journal.")


def reload_manager():
    if run(["systemctl", "--user", "daemon-reload"]).returncode:
        raise ValueError("The user service manager is unavailable.")


def settings():
    with urllib.request.urlopen("http://127.0.0.1:24803/v1/settings", timeout=2) as response:
        raw = response.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:
        raise ValueError("Synergy settings exceeded the setup limit.")
    data = json.loads(raw)["data"]
    # The full vendor response can contain license data; return only this allowlist.
    mine = data.get("myId")
    computers = [{"id": c.get("id"), "name": str(c.get("name", ""))[:128],
                  "hostname": str(c.get("hostname", ""))[:128]}
                 for c in data.get("computers", []) if not c.get("isRemoved")]
    peers = [c for c in computers if c["id"] != mine]
    me = next((c for c in computers if c["id"] == mine), {})
    return {"my_id": mine, "name": me.get("name", socket.gethostname()), "peers": peers,
            "core_running": data.get("coreRunning") is True}


def data_control():
    """Inspect advertised Wayland globals without requesting a selection."""
    class Interface(ctypes.Structure):
        _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_int),
                    ("method_count", ctypes.c_int), ("methods", ctypes.c_void_p),
                    ("event_count", ctypes.c_int), ("events", ctypes.c_void_p)]
    lib = ctypes.CDLL(ctypes.util.find_library("wayland-client") or "libwayland-client.so.0")
    ptr = ctypes.c_void_p
    lib.wl_display_connect.argtypes = [ctypes.c_char_p]
    lib.wl_display_connect.restype = ptr
    lib.wl_proxy_marshal_flags.argtypes = [ptr, ctypes.c_uint32, ctypes.POINTER(Interface), ctypes.c_uint32, ctypes.c_uint32]
    lib.wl_proxy_marshal_flags.restype = ptr
    lib.wl_proxy_add_listener.argtypes = [ptr, ctypes.POINTER(ptr), ptr]
    lib.wl_display_roundtrip.argtypes = [ptr]
    lib.wl_proxy_destroy.argtypes = [ptr]
    lib.wl_display_disconnect.argtypes = [ptr]
    display = lib.wl_display_connect(None)
    if not display:
        return False
    registry = None
    found = []
    add_type = ctypes.CFUNCTYPE(None, ptr, ptr, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32)
    remove_type = ctypes.CFUNCTYPE(None, ptr, ptr, ctypes.c_uint32)
    add = add_type(lambda _data, _registry, _name, interface, _version: found.append(interface.decode()))
    remove = remove_type(lambda *_: None)
    callbacks = (ptr*2)(ctypes.cast(add, ptr).value, ctypes.cast(remove, ptr).value)
    try:
        interface = Interface.in_dll(lib, "wl_registry_interface")
        registry = lib.wl_proxy_marshal_flags(display, 1, ctypes.byref(interface), 1, 0, ptr())
        if not registry or lib.wl_proxy_add_listener(registry, callbacks, None) != 0:
            return False
        return lib.wl_display_roundtrip(display) >= 0 and "zwlr_data_control_manager_v1" in found
    finally:
        if registry:
            lib.wl_proxy_destroy(registry)
        lib.wl_display_disconnect(display)


def prerequisites():
    checks = {"python": sys.version_info >= (3, 11),
              "wl_clipboard": bool(shutil.which("wl-copy") and shutil.which("wl-paste"))}
    try:
        relay.configure_environment()
        checks["wayland"] = True
        checks["data_control"] = data_control()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        checks.update(wayland=False, data_control=False)
    return checks


def endpoint():
    checks = prerequisites()
    try:
        synergy = settings()
    except (OSError, ValueError, KeyError):
        synergy = {"my_id": None, "name": socket.gethostname()}
    return {"app": "omarchy-synergy", "version": VERSION, "wire_version": sharing_state.WIRE_VERSION,
            "bundle": storage.bundle_digest(), "role": storage.role(), "checks": checks,
            "max_mib": sharing_state.local_limit(),
            "synergy_id": synergy["my_id"], "name": synergy["name"],
            "user": getpass.getuser(), "hostname": socket.gethostname(),
            "remote_script": str(storage.install_dir()/"relay.py")}


def status():
    role = storage.role()
    record = sharing_state.read_status()
    config = {}
    if role == "source":
        try:
            config = relay.load_config(storage.config_path())
        except (OSError, ValueError):
            return {"role": role, "state": "configuration-error"}
    state = record.get("state") if record else "stopped"
    if sharing_state.paused():
        state = "manual-paused"
    elif role == "receiver" and not record:
        state = "receiver-ready"
    elif role == "source" and not record and service("is-active"):
        state = "starting"
    try:
        matches = storage.bundle_digest() == storage.bundle_digest(storage.install_dir())
    except OSError:
        matches = False
    return {"role": role, "state": state, "transport": config.get("transport", (record or {}).get("transport", "")),
            "source_name": (record or {}).get("source_name", ""), "config": config,
            "max_mib": (record or {}).get("max_mib", config.get("max_mib", sharing_state.local_limit())),
            "runtime_matches": matches,
            "version": VERSION}
