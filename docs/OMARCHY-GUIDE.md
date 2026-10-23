# Synergy 3 on Omarchy and Hyprland

This community setup shares one computer's keyboard and mouse with another Omarchy computer, with a separate clipboard companion. The tested configuration used Synergy 3.8.4, Omarchy 4.0.6, Hyprland 0.56.2 and xdg-desktop-portal-hyprland 1.4.1. It is an experimental compatibility setup, not a claim of official Hyprland support.

The input-source computer uses Hyprland's InputCapture portal. The receiving computer needs a RemoteDesktop backend that injects input into Hyprland. The included bridge patch series adds native Synergy caller verification and EIS input fixes to [iamnarayana/wayland-kdeconnect-fix](https://github.com/iamnarayana/wayland-kdeconnect-fix). It does not provide portal clipboard support. The supplied Python companion shares clipboard contents over a separate encrypted SSH connection.

This guide builds on the [existing Omarchy Synergy/Deskflow discussion](https://github.com/omacom/omarchy/discussions/10097). Keep that work and the bridge's original MIT attribution intact when sharing these additions.

## 1. Prepare both computers

Install the same licensed Synergy 3 version on both computers from the vendor's account/download page, and sign in privately in the app. No vendor package or license is included here. The tested native package installed `/opt/Synergy/synergy-core` and `synergy-3.service`; Flatpak or other paths are not covered by the bridge's exact-path verification.

Check installed versions:

```bash
omarchy version
pacman -Q synergy hyprland xdg-desktop-portal xdg-desktop-portal-hyprland libei
```

Use a trusted LAN or an existing Tailscale connection. For the clipboard companion, use an existing trusted SSH route: OpenSSH on the LAN/VPN or optional Tailscale SSH. Verify the expected host identity and noninteractive authentication first. Review changed host keys on the receiving computer rather than disabling checking. Setting up SSH permissions, account access or router reservations is outside this package's installer.

## 2. Build the receiving bridge

Only the receiving computer needs this bridge in the tested one-way input arrangement. Prepare the pinned upstream checkout and apply the three patches using [the patch-series instructions](../patches/input-bridge/README.md). An unmodified clone of the upstream fork does not contain these native Synergy fixes.

Install the build dependencies on the receiver using Omarchy's package helper:

```bash
omarchy pkg add cmake gcc pkgconf qt6-base wayland libxkbcommon libei xdg-desktop-portal
```

The EIS patch requires libeis 1.6 or later. From the omarchy-synergy repository root, after applying the series:

```bash
cmake -S build/input-bridge -B build/input-bridge-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$HOME/.local"
cmake --build build/input-bridge-build --parallel 2
ctest --test-dir build/input-bridge-build --output-on-failure
cmake --install build/input-bridge-build
```

The files install under `~/.local`; no Omarchy package files are edited. Review `docs/synergy.md` and `docs/input-compatibility.md` in `build/input-bridge/` before enabling it.

## 3. Route RemoteDesktop on the receiver

Back up any existing `~/.config/xdg-desktop-portal/hyprland-portals.conf`. Preserve its existing entries. On a stock tested system with no user file, the packaged `/usr/share/xdg-desktop-portal/hyprland-portals.conf` was copied to that user path and this one entry was added to its `[preferred]` section:

```ini
org.freedesktop.impl.portal.RemoteDesktop=hypr-kdeconnect
```

The tested result was:

```ini
[preferred]
default=hyprland;gtk
org.freedesktop.impl.portal.RemoteDesktop=hypr-kdeconnect
```

This preserves Hyprland's InputCapture, screenshot and screencast routing. Do not replace all portal defaults with the input bridge.

Native Synergy sessions also need verified executable access. On the tested system, the bridge's service sandbox prevented `/proc/<caller-pid>/exe` lookup. The optional `data/synergy-caller-verification.conf.example` removes three filesystem sandbox settings for this user service so the lookup succeeds. It reduces service isolation; read the explanation in `docs/synergy.md` before copying it to `~/.config/systemd/user/hypr-kdeconnect-portal.service.d/caller-verification.conf`. It is not installed automatically. Caller verification stays enabled.

After making a deliberate pause in input sharing, reload the user manager and restart the affected portal services:

```bash
systemctl --user daemon-reload
systemctl --user stop hypr-kdeconnect-portal.service
systemctl --user restart xdg-desktop-portal.service
```

The bridge activates when the frontend needs it. Check it with:

```bash
busctl --user introspect org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.portal.RemoteDesktop
systemctl --user status hypr-kdeconnect-portal.service
journalctl --user -u hypr-kdeconnect-portal.service -n 30 --no-pager
```

## 4. Pair and arrange Synergy

Set the computer with the physical keyboard and mouse as Synergy's input source. Add the other computer, accept only the expected peer identity and keep TLS and fingerprint checking enabled. Put the receiver to the left if that matches your desk.

Synergy 3.8.4 has a layout-generation bug in the tested geometry: two rectangles touching at a horizontal boundary generate zero-length links such as `up(100,100)`, and the core exits with code 4. Moving the second rectangle exactly one layout unit farther away avoids those links. In the reproduced example, the rectangles are width 200, height 110, top 150; the left rectangle starts at x=0 and the right starts at x=201. Gaps of two, three or ten produced no links in this example. These are Synergy layout coordinates, not physical monitor pixels.

This is a temporary workaround, not a reliable general rule for every layout. Check the generated config file shown in Synergy's Local settings. A correct two-computer left/right arrangement should contain only the intended `left(0,100)` and `right(0,100)` links. Editing the generated file directly is temporary because Synergy can regenerate it. A separate vendor report has been prepared from this geometry; no issue or ticket has been published. Record the generated links and geometry if reporting another case. Avoid forcing coordinates through the undocumented live settings API.

Test edge crossing, clicks, typing, modifier keys, scrolling, every receiving monitor and returning to the input source before adding clipboard sharing. The accepted hardware test used two receiving 1920×1080 monitors at scale 1. Fractional scaling, rotated displays, hotplug changes, AltGr/Super combinations and additional keyboard layouts remain outside that acceptance result. Restart the bridge after changing monitor geometry.

## 5. Add optional clipboard sharing

Use [the plugin wizard](PLUGIN.md) or follow [the manual companion setup](clipboard.md). It requires Python 3.11+, wl-clipboard, and a working trusted OpenSSH or Tailscale SSH route between the two active Wayland sessions. Install the same companion version on both computers, configure the remote host, remote script path and Synergy peer ID only on the input source, and test it in the foreground before enabling its user service.

The regular clipboard and primary selection are separate. Copy/paste normally uses the regular clipboard; in many terminals Ctrl+Shift+C/V does that. Highlighting text and middle-clicking uses the primary selection. Shift+Insert behavior depends on the application. Test both selections explicitly. This setup does not implement a native portal Clipboard interface and does not advertise one.

All supported copies are shared while the companion is active, including sensitive text. Both computers must be trusted. The default `initial_sync = "none"` shares future changes; `"source"` deliberately replaces the remote's supported selections once after a fresh connection. Pause the companion directly when needed:

```bash
systemctl --user stop synergy-clipboard.service
```

## Omarchy plugin status

The [Omarchy plugin and two-device pairing wizard](PLUGIN.md) provide receiver preparation, Direct LAN (SSH) or Tailscale (SSH) pairing, status, persistent pause and a transfer limit synchronized from either endpoint. Install the same plugin revision on both computers, prepare the receiver first and review the source pairing before enabling. The plugin does not install the input bridge or change portal routing.

## Validation and rollback

The installed prototype passed bidirectional text/PNG transfer, primary-selection isolation, Synergy pause gating and reconnect checks. The owner confirmed mouse, typing, scrolling, both receiving monitors, return crossing and middle-click paste. The cleaned bridge (including repeated-key/Shift correction) and configurable companion have since been activated on the test pair with rollback copies. Bridge checks pass 6/6 and clipboard checks 13/13 on each computer; cross-machine text/PNG, primary selection, pause/resume and reconnect checks pass. The owner has confirmed fresh input/Codex-Shift acceptance; see [the baseline acceptance report](ACCEPTANCE.md) and [current validation](VALIDATION.md) for the later OpenSSH transport addition. Reboot persistence and long-running behavior have not been validated.

To roll back, disable the clipboard companion, remove only its installed user files, restore the backed-up portal configuration, remove the bridge's installed user-local binary/metadata and optional caller-verification override, then reload the user manager and restart the portal frontend. Do this during a planned pause in sharing; portal restarts can interrupt screen sharing or other portal sessions. Keep the keyboard and mouse physically available on each computer while changing the setup.

Prepared with OpenAI Codex (GPT-6), with hardware acceptance by the system owner. No account credentials, serial keys, private certificates, tailnet addresses or personal machine IDs are needed in a public guide.
