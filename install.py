#!/usr/bin/env python3
"""Install user files without overwriting anything or starting services."""
import argparse
import os
from pathlib import Path


def install(home, remote_only=False):
    source = Path(__file__).resolve().parent
    files = [(source / "relay.py", home / ".local/lib/synergy-clipboard/relay.py", 0o700)]
    if not remote_only:
        files += [
            (source / "config.example.toml", home / ".config/synergy-clipboard/config.toml", 0o600),
            (source / "synergy-clipboard.service", home / ".config/systemd/user/synergy-clipboard.service", 0o600),
        ]
    for src, target, _ in files:
        if not src.is_file() or target.exists() or target.is_symlink():
            raise FileExistsError(f"missing source or existing destination: {target}")
    created = []
    try:
        for src, target, mode in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL also refuses a dangling symlink or a competing installation.
            with open(target, "xb") as output:
                created.append(target)
                os.chmod(target, mode)
                output.write(src.read_bytes())
    except BaseException:
        for target in reversed(created):
            target.unlink()
        raise
    return [target for _, target, _ in files]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-only", action="store_true")
    args = parser.parse_args()
    for target in install(Path.home(), args.remote_only):
        print(target)
    print("Installed only. Configure the coordinator before starting its user service.")
