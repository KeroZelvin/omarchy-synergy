# Validation and limits

## Plugin candidate — 23 October 2026

The native Omarchy plugin, receiver-first pairing wizard and independent clipboard service were installed and tested on two authorized computers. Both Direct LAN (OpenSSH) and Tailscale SSH pairing completed through the panel's own QML handlers. Installation, update, disable/enable, shell restart and receiver widget removal/reinstallation were exercised through native Omarchy commands. Manifest validation passes on both computers.

The 38 isolated companion/plugin tests pass on both computers. They cover transport construction and strict checking, bounded input, configuration validation, transaction restoration, endpoint identity/version checks, source-role refusal, job lifetime/locking, pause/status records, pair-limit acknowledgment and dynamic clipboard capture bounds. Native integration checks use the same QML actions as the buttons; they are not a claim of automated physical mouse clicks.

## Live transfer and lifecycle checks

For each transport, UTF-8 text of 9,437,205 bytes and a valid PNG of 16,784,432 bytes matched exactly in both directions. Independent PRIMARY transfer passed both ways without changing the regular clipboard. Prior supported selections were held only in memory and restored; clipboard contents were not logged or saved.

Receiver pause persisted through endpoint reconnect and blocked outgoing regular clipboard and incoming PRIMARY changes. Source pause persisted through service restart. Resume recovered transfer. Stopping/restarting the receiving Synergy service gated sharing and allowed a fresh transfer after recovery. Both shell restarts retained the coordinator connection. Disabling/enabling and removing/reinstalling the receiver widget retained the independent service.

Pair-wide limits synchronized from the source at 128 MiB, from the receiver at 32 MiB, and back to 128 MiB. With the source paused/offline, a receiver request remained pending and synchronized on reconnect. The owner confirmed that changing the size through the panels updates the other computer. This validates settings up to 128 MiB, not a full 128 MiB payload transfer.

Acceptance found and corrected a frozen 8 MiB clipboard-capture default, a native Omarchy button API mismatch and clicks dropped during status polling. Background polling subsequently received a visual fix to avoid dimming controls/showing a busy spinner on every refresh. Idle geometry remained constant during sampling on both computers, and the owner confirmed both panels stay steady after the fix.

The final working pair uses Direct LAN SSH with existing pinned trust. The Synergy input bridge, layout, account settings, SSH trust and router configuration were retained. Public authorship and publication remain pending review; no upstream submission has been made.

## Input bridge and historical acceptance

The three included patches reproduce accepted bridge tree 5ce1b22 from pinned upstream ea55f66c8238235983d60d381bf2abe1fed50043. Bridge code was unchanged during plugin development. See [the original report](ACCEPTANCE.md) for prior bridge tests and hardware acceptance.

The owner previously confirmed both receiving monitors, typing, scrolling, return crossing, middle-click paste and the Shift/Codex correction: normal digits/Enter after releasing Shift and working Shift+Enter. The stuck-modifier regression fails without duplicate-transition filtering and passes with it. This plugin test does not claim a new full physical-input acceptance run.

## Practical limits

Tested with Synergy 3.8.4, Omarchy 4.0.6, Hyprland 0.56.2, Python 3.14 and wl-clipboard 2.3. The receiver has two adjacent 1920×1080 monitors at scale 1. Python 3.11+ is the intended minimum; older Python releases were not exercised here.

Not validated: full 128 MiB payloads, reboot persistence, long soak, fractional/mixed scaling, rotation/hotplug, full physical AltGr/Super/keyboard-layout coverage or additional distributions. Restart the input bridge after geometry changes. The optional caller-verification override reduces filesystem isolation and remains a maintainer-review point.

The companion supports text and PNG/JPEG/WebP/BMP, including middle-click PRIMARY. File-manager transfers, folders, rich text, history and selection clearing are not implemented. Raw logs, actual configuration, network addresses, deployment/rollback helpers, keys and backups remain outside the public repository.
