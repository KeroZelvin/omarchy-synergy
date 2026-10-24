# Changelog

## Unreleased — 0.2.1 candidate

- Fix a clipboard capture race in the 0.2.0 password-manager guard. MIME types, browser-source metadata and payload now come from one Wayland data offer. Selection replacement aborts the capture instead of mixing ordinary metadata with a later secret. This applies to regular clipboard, PRIMARY and initial synchronization.
- Refuse received secrets when `wl-copy --sensitive` is unavailable, instead of writing them without the marker.
- Add a bounded, read-only Python data-control reader, installed by both the manual installer and plugin. Requires data-control protocol v2 and exactly one Wayland seat; no additional package or build step. Install matching updated runtimes on both computers.
- Add private-compositor regression tests for offer replacement, source association, byte limits, timeout, unsupported selections and marker support. Guide edits preserve existing fcitx5/Synergy policy settings, qualify policy licensing and explain receiver-first upgrades.

The existing `v0.2.0` tag is unchanged. Its release remains unpublished while the replacement candidate is reviewed.

## 0.2.0 — experimental

- Password-manager copies marked with `x-kde-passwordManagerHint` stay on the computer where they were copied. **Send one secret** in the panel (or the `allowSecret` IPC call) shares exactly one regular-clipboard secret within 60 seconds, including one copied just before. Highlighted secrets and automatic initial sync never carry secrets. Received secrets are re-marked with `wl-copy --sensitive`. Copies from the Proton Pass, Bitwarden and 1Password Chromium extensions, and the Proton Pass desktop/web origin, count as secrets even without the marker.
- Guide: set `input_capture.capture_modifiers = true` on the keyboard/mouse computer. Without it, Hyprland 0.56 stops forwarding keys after a modifier press during capture (keyboard-only loss, intermittent). Upstream: hyprwm/Hyprland discussion #15992.
- Guide: recommend fcitx5 `PersistentVirtualKeyboard=True` on the keyboard/mouse computer, which avoids the virtual-keyboard recreation that hits the same Hyprland reset.
- Guide: optional `/etc/synergy-3/policy.ini` to keep the Synergy client on the LAN when Tailscale is also present.
- Updating from 0.1.0 changes the runtime bundle: install the same revision on both computers.

## 0.1.0 — experimental

Initial community integration for one pair of Omarchy/Hyprland computers running Synergy 3.

- Native Omarchy bar panel and receiver-first pairing wizard, with reviewed activation and user-local backups.
- Direct LAN (OpenSSH) and optional Tailscale SSH transport using existing authentication and trust.
- Independent regular clipboard and middle-click PRIMARY sharing, in both directions, for supported text/images.
- Persistent pause/resume, reconnect and Synergy connection/allow-copy gating.
- Pair-wide 1–128 MiB item limits, synchronized from either endpoint, including pending offline changes.
- Visible button styling and silent background status refreshes.
- Full setup guide and attributed upstream bridge patches, including the repeated-key/stuck-Shift correction.

See [validation](docs/VALIDATION.md) for tested software, actual payload sizes and hardware limits. Full 128 MiB payloads, reboot persistence and a long soak remain untested. File-manager files/folders, rich text, history and selection clearing are not supported. The widget does not install the receiving input bridge or configure SSH. Both endpoints must use matching runtime code/protocol.
