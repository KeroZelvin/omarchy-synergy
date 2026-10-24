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

### Required on the keyboard/mouse computer: capture modifiers

On Hyprland 0.56, pressing Shift, Super, Ctrl or Alt while the pointer is on the other computer can make Hyprland replace the keyboard it captures for Synergy without forwarding keys on the replacement. Typing then stops (often right after the first Shift) while the mouse keeps working, until the pointer returns. Fcitx5's virtual keyboard makes this frequent and intermittent. Add this to `~/.config/hypr/input.lua` on the computer whose keyboard is shared, then `hyprctl reload`:

```lua
hl.config({ input_capture = { capture_modifiers = true } })
```

Run `hyprctl configerrors` after reloading, then check `hyprctl getoption input-capture:capture_modifiers` (expect `true`). This also sends captured modifiers to the receiving computer, so test your usual shortcuts and return crossing. The workaround targets the tested Hyprland 0.56.2 behavior; recheck it when upgrading Hyprland. Cause: `CEis::resetKeyboard()` recreates the captured keyboard but does not restart emulation; modifier changes reach it through `CSeatManager::setKeyboard()` unless `capture_modifiers` returns early during capture. Upstream report: [hyprwm/Hyprland discussion #15992](https://github.com/hyprwm/Hyprland/discussions/15992).

### Recommended on the keyboard/mouse computer: keep fcitx5's virtual keyboard

`capture_modifiers` does not cover a keyboard being added or recreated during capture, which can hit the same reset. If fcitx5 is running on the source, its Wayland input-method v2 backend normally recreates its virtual keyboard on activation/deactivation. The [upstream option](https://github.com/fcitx/fcitx5/blob/master/src/frontend/waylandim/waylandim.h) keeps that object alive. Back up `~/.config/fcitx5/conf/waylandim.conf` if it exists, create its parent directory if needed, and add or update this top-level setting while preserving other entries:

```ini
PersistentVirtualKeyboard=True
```

Return the pointer to the source and finish any input-method composition before restarting fcitx5 with `fcitx5 -rd`. Retest typing and modifier keys on the receiver. To undo, restore the previous value or remove only this setting, then restart fcitx5 again. Delete the file only if you created it for this setting and it contains nothing else. Hotplugging a real keyboard during capture can still drop typing until the pointer crosses back.

### Optional on the receiving computer: keep Synergy on the LAN

When both computers are also on Tailscale, Synergy's background service may rewrite the client's server address to the Tailscale one. Symless documents policy locks as a **Business Advanced/Enterprise** feature; check your edition against [the vendor's policy guide](https://support.symless.com/hc/en-us/articles/50464776117521-Locking-down-settings-so-users-cannot-change-them) before using this optional workaround. It pins Synergy's input connection, not the clipboard companion's separate SSH route.

During a planned pause in input sharing, back up any existing `/etc/synergy-3/policy.ini`. Create the directory and open the file with:

```bash
sudo install -d -o root -g root -m 755 /etc/synergy-3
sudoedit /etc/synergy-3/policy.ini
```

Add or update `remoteHost` in its `[client]` section, preserving every other section and key. Replace the example address below with the keyboard/mouse computer's reserved LAN address; do not paste it unchanged:

```ini
[client]
remoteHost=192.168.1.10
```

The file and its parent directories must be root-owned and not writable by other users. For the standard native-package path:

```bash
sudo chown root:root /etc/synergy-3/policy.ini
sudo chmod 644 /etc/synergy-3/policy.ini
systemctl --user restart synergy-3.service
```

Check `/opt/Synergy/synergy-core --locked-settings` for `client/remoteHost`, then check the peer address with `ss -tn state established '( dport = :24800 )'` (adjust the port if customized). If the lock is absent, do not assume the address is pinned. To undo, restore the previous `remoteHost` value or remove only that key, then restart the service. Delete the policy file only if it was created solely for this setting. Synergy's separate background link on port 24802 may still use both routes. If the reserved LAN address changes or the LAN is unavailable, the pinned input connection will fail until you update or remove the override.

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

Use [the experimental 0.2.1 plugin wizard](PLUGIN.md), preparing the receiver before pairing the source. Both computers need Python 3.11+, wl-clipboard and active Wayland sessions, with a working trusted OpenSSH or Tailscale SSH route from source to receiver. Install the same revision on both computers.

For a shell-independent installation, follow [the manual companion setup](clipboard.md). Configure the remote host, remote script path and Synergy peer ID only on the input source, then test in the foreground before enabling its user service.

The regular clipboard and primary selection are separate. Copy/paste normally uses the regular clipboard; in many terminals Ctrl+Shift+C/V does that. Highlighting text and middle-clicking uses the primary selection. Shift+Insert behavior depends on the application. Test both selections explicitly. This setup does not implement a native portal Clipboard interface and does not advertise one.

Supported copies are shared while the companion is active, except those recognized by the experimental password-manager guard. **Send one secret** allows one recognized regular-clipboard secret within 60 seconds; recognized PRIMARY secrets and automatic initial sync remain excluded. This is best-effort detection: unmarked or unrecognized sources can evade it. Both computers must be trusted. Read [the guard limitations](VALIDATION.md#020-review-findings) before relying on it. The default `initial_sync = "none"` shares future changes; `"source"` deliberately replaces the remote's supported non-secret selections once after a fresh connection. On the keyboard/mouse source, stop the coordinator when needed:

```bash
systemctl --user stop synergy-clipboard.service
```

For a pause that survives service restarts, use **Pause sharing** in either panel. The receiver endpoint is started over SSH by the source; stopping a receiver-local coordinator service does not stop that endpoint.

## Omarchy plugin status

The [Omarchy plugin and two-device pairing wizard](PLUGIN.md) provide receiver preparation, Direct LAN (SSH) or Tailscale (SSH) pairing, status, persistent pause and a transfer limit synchronized from either endpoint. Install the same plugin revision on both computers, prepare the receiver first and review the source pairing before enabling. The plugin does not install the input bridge or change portal routing.

## Validation and rollback

The accepted input bridge passed six checks on each computer. The owner confirmed mouse movement, typing, scrolling, both receiving monitors, return crossing, middle-click paste and the Shift/Codex correction. See [the historical acceptance report](ACCEPTANCE.md) for that baseline.

The current candidate passes 64 isolated tests on each computer. Its paired clipboard and guard checks passed over LAN SSH, including larger text/PNG and independent PRIMARY transfers in both directions. Earlier acceptance also covered Tailscale SSH, persistent pause, Synergy gating, reconnect and widget lifecycle checks; the owner confirmed pair-wide size changes and steady panels. See [current validation](VALIDATION.md) for actual payload sizes, two transient failed expectations in the candidate's earlier runs, and remaining limits. Full 128 MiB payloads, reboot persistence and long-running behavior have not been validated.

To roll back, disable the clipboard companion, remove only its installed user files, restore the backed-up portal configuration, remove the bridge's installed user-local binary/metadata and optional caller-verification override, then reload the user manager and restart the portal frontend. Do this during a planned pause in sharing; portal restarts can interrupt screen sharing or other portal sessions. Keep the keyboard and mouse physically available on each computer while changing the setup.

Prepared with OpenAI Codex (GPT-6), with hardware acceptance by the system owner. No account credentials, serial keys, private certificates, tailnet addresses or personal machine IDs are needed in a public guide.
