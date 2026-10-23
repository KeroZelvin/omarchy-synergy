# Synergy Wayland clipboard companion

An experimental companion for one pair of Linux Wayland computers running Synergy 3. It shares the regular clipboard and the primary selection (highlight text, then middle-click), independently and in both directions, over Tailscale SSH. It was developed alongside a RemoteDesktop input bridge on Omarchy/Hyprland. It is a separate program, not a Synergy or Deskflow plugin.

## Status and requirements

Requires Python 3.11+, `wl-clipboard` with data-control support in the active compositor, systemd user sessions, Tailscale, and already working, verified, noninteractive `tailscale ssh USER@PEER`. Install the same companion version on both computers. The input-source computer runs the coordinator; it starts the other endpoint over SSH. Only one pair per user session is supported. The remote endpoint needs an active Wayland session and `WAYLAND_DISPLAY` in its systemd user environment.

Tested with Synergy 3.8.4, Omarchy 4.0.6, Hyprland 0.56.2, Python 3.14 and wl-clipboard 2.3. The configurable version passes 13 isolated tests on each test computer and real cross-machine Unicode/multiline text, PNG, primary-selection isolation, pause/resume, coordinator restart and receiving-endpoint restart checks. It is running on the accepted test pair with rollback copies retained. The owner also confirmed input and Shift/Codex behavior with the accompanying bridge. Reboot persistence and a long soak have not been tested.

## What gets shared

One supported representation per clipboard change: UTF-8 text preferred, otherwise PNG, JPEG, WebP or BMP. The limit is 8 MiB decoded per transfer. HTML, rich text, file lists, drag-and-drop, unsupported selections and clearing a selection are not synchronized. This is not a clipboard history database. Concurrent writes on both computers can overwrite one another; there is no conflict-resolution protocol.

Transfers are encrypted and authenticated by the existing SSH transport. Payloads are handled in memory; this program does not log or write clipboard contents to files. The compositor, receiving application, OS swap, core dumps and any installed clipboard-history tools have their own retention behavior. All supported changes are shared while the connection is active, including sensitive text copied during that time. Treat both computers as trusted. The gate follows Synergy core/peer connection state and its allow-copy setting; it does not detect which computer currently has pointer focus or whether the screen is locked.

## Install without starting anything

From this directory, on both computers:

```bash
python3 -m unittest discover -s tests -v
```

On the receiving computer:

```bash
python3 install.py --remote-only
```

On the input-source computer:

```bash
python3 install.py
```

The installer writes user files only, refuses existing destinations (including symlinks), and does not start services, change SSH trust or modify Synergy. If a prototype is already installed, review a manual migration instead of overwriting it.

Edit `~/.config/synergy-clipboard/config.toml` on the input source:

```toml
remote_host = "your-user@your-tailscale-peer"
remote_script = "/home/your-user/.local/lib/synergy-clipboard/relay.py"
peer_id = "REPLACE_WITH_THE_PEER_COMPUTER_ID"
initial_sync = "none"
```

The remote script path belongs to the remote user and need not match the local path. The peer ID is a 64-character lowercase hex Synergy computer ID, not a serial key. This allowlist-only command displays names and IDs from the local service without dumping account settings:

```bash
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:24803/v1/settings', timeout=2) as response:
    data = json.load(response)['data']
for computer in data.get('computers', []):
    print(computer.get('id', ''), computer.get('name', ''))
PY
```

Choose the remote computer, and keep that local configuration out of public reports. If a later Synergy version changes this undocumented API, review the response shape privately and update the adapter. Do not post the full settings response: it can include license information and trusted-computer details.

With `initial_sync = "none"`, each connection starts by observing the current selections and shares future changes. Use `"source"` to copy both supported selections from the coordinator to the remote computer once each SSH connection becomes active. That option replaces the remote contents and helps avoid stale primary selections after reconnecting. It does not seed again on every Synergy pause/resume.

## Run, pause and remove

First test in the foreground:

```bash
python3 ~/.local/lib/synergy-clipboard/relay.py coordinator --config ~/.config/synergy-clipboard/config.toml
```

Then enable it if desired:

```bash
systemctl --user daemon-reload
systemctl --user enable --now synergy-clipboard.service
journalctl --user -u synergy-clipboard.service -n 30 --no-pager
```

Stop all sharing provided by this companion:

```bash
systemctl --user stop synergy-clipboard.service
```

To remove it, disable the coordinator service, then remove only the files installed by this package. The remote endpoint exits when SSH closes or after its 30-second state timeout; a hung transport can delay that shutdown. Stop it on the receiving computer too before removing its script. This does not clear clipboard data already delivered to another computer.

```bash
systemctl --user disable --now synergy-clipboard.service
rm ~/.config/systemd/user/synergy-clipboard.service
rm ~/.config/synergy-clipboard/config.toml
rm ~/.local/lib/synergy-clipboard/relay.py
systemctl --user daemon-reload
```

On the remote computer, remove its installed `~/.local/lib/synergy-clipboard/relay.py` after the endpoint has exited.

## Design and limitations

`wl-paste --watch` generates selection-change events; bounded snapshots choose a supported MIME type. Per-selection digests suppress echoes. Transfer messages are bounded JSON/base64 frames over a single persistent SSH process. Unix notification sockets use the user's runtime directory and mode 0600. Protocol version 3 intentionally refuses the earlier private prototype's version 2 handshake.

Only the Synergy connection gate polls, every two seconds, because this small adapter has no supported subscription interface for Synergy 3 state. API failures pause transfers. The remote endpoint requires regular state heartbeats and exits on loss of the coordinator. This gate is a convenience rather than a security boundary; there can be a delay before a pause is observed. This package neither starts Synergy nor enables Tailscale SSH on a device.

## Contributing and attribution

Run `python3 -m unittest discover -s tests -v`. The tests do not read or alter the real desktop clipboard. They cover frame validation, payload limits, connection gating, selection-specific apply/dedup behavior, pause races, subprocess limits, remote-command quoting and safe installation. They do not substitute for real Wayland, SSH or multi-machine tests. Additional language layouts, fractional scaling, reboot persistence and long-running behavior need acceptance testing.

Prepared with OpenAI Codex (GPT-6), with interactive validation by the system owner. The companion code is offered under the MIT license in `LICENSE`. The bridge and existing community guide are credited separately in the accompanying Omarchy guide.
