# Changelog

## Unreleased

- Password-manager copies marked with `x-kde-passwordManagerHint` stay on the computer where they were copied. **Send one secret** in the panel (or the `allowSecret` IPC call) shares exactly one regular-clipboard secret within 60 seconds, including one copied just before. Highlighted secrets and automatic initial sync never carry secrets. Received secrets are re-marked with `wl-copy --sensitive`. Copies from the Proton Pass, Bitwarden and 1Password Chromium extensions count as secrets even without the marker.

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
