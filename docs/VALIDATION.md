# Validation and limits

## Unreleased password-manager guard — 23 October 2026

The guard candidate passes 50 isolated tests on each of the two test computers. It recognizes the KDE sensitive marker, the listed Chromium password-manager extensions and the Proton Pass desktop/web origin. A regression first demonstrated that the desktop origin was missed, then passed after adding the exact HTTPS origin. Similar-looking domains, URL userinfo/path tricks and HTTP do not match. Missing, empty and invalid advertised browser-source metadata are withheld.

Live synthetic copies pass ordinary text, PRIMARY and PNG in both directions. Marked and browser-source secrets remain local by default; the one-shot override sends a regular-clipboard copy with its sensitive marker restored on the receiver. A second secret is withheld after that allowance, PRIMARY never consumes it, reconnect seeding excludes secrets, and the real 60-second expiry passes. Desktop-origin fixtures verify withholding and explicit sharing both ways; ordinary and lookalike origins still transfer.

The owner confirmed a fresh Proton Pass extension copy was blocked and then pasted after the override. A fresh marked copy from the receiving computer also pasted after its override. The actual Proton Pass desktop app supplied recognizable source metadata without a KDE marker; the owner confirmed a fresh desktop copy pasted nothing with the override off. Its first deliberate override Ctrl+V check displayed nothing, although the receiver recorded a nonempty clipboard delivery. Without another copy or allowance, the owner then confirmed the correct desktop value pasted using the fresh test editor’s explicit paste button. Actual desktop blocking and deliberate sharing pass. The owner then clicked inside the same fresh editor and confirmed Ctrl+V appended a second copy. The earlier blank paste was not reproduced in the focused editor; its cause remains unproven. Tests use throwaway data; clipboard contents and keystrokes are not logged or saved.

Both computers run matching runtimes over LAN SSH with a 128 MiB pair limit. Backups and disposable restore checks cover the previous installation. Input receiver, portal routing and native Synergy processes were checked unchanged. This guard is experimental; it does not claim detection of unmarked managers or Firefox copies without source metadata. Already-transferred copies remain pasteable until replaced or cleared; cancelling an allowance does not recall them.

## Experimental 0.1.0 candidate — 23 October 2026

The native Omarchy plugin, receiver-first pairing wizard and independent clipboard service were installed and tested on two authorized computers. Both Direct LAN (OpenSSH) and Tailscale SSH pairing completed through the panel's own QML handlers. Installation, update, disable/enable, shell restart and receiver widget removal/reinstallation were exercised through native Omarchy commands. Manifest validation passes on both computers.

The 38 isolated companion/plugin tests pass on both computers. They cover transport construction and strict checking, bounded input, configuration validation, transaction restoration, endpoint identity/version checks, source-role refusal, job lifetime/locking, pause/status records, pair-limit acknowledgment and dynamic clipboard capture bounds. Native integration checks use the same QML actions as the buttons; they are not a claim of automated physical mouse clicks.

## Live transfer and lifecycle checks

For each transport, UTF-8 text of 9,437,205 bytes and a valid PNG of 16,784,432 bytes matched exactly in both directions. Independent PRIMARY transfer passed both ways without changing the regular clipboard. Prior supported selections were held only in memory and restored; clipboard contents were not logged or saved.

Receiver pause persisted through endpoint reconnect and blocked outgoing regular clipboard and incoming PRIMARY changes. Source pause persisted through service restart. Resume recovered transfer. Stopping/restarting the receiving Synergy service gated sharing and allowed a fresh transfer after recovery. Both shell restarts retained the coordinator connection. Disabling/enabling and removing/reinstalling the receiver widget retained the independent service.

Pair-wide limits synchronized from the source at 128 MiB, from the receiver at 32 MiB, and back to 128 MiB. With the source paused/offline, a receiver request remained pending and synchronized on reconnect. The owner confirmed that changing the size through the panels updates the other computer. This validates settings up to 128 MiB, not a full 128 MiB payload transfer.

Acceptance found and corrected a frozen 8 MiB clipboard-capture default, a native Omarchy button API mismatch and clicks dropped during status polling. Background polling subsequently received a visual fix to avoid dimming controls/showing a busy spinner on every refresh. Idle geometry remained constant during sampling on both computers, and the owner confirmed both panels stay steady after the fix.

The final working pair uses Direct LAN SSH with existing pinned trust. The Synergy input bridge, layout, account settings, SSH trust and router configuration were retained. The candidate uses the owner's established public Git identity. Publication remains pending review; no upstream submission has been made.

## Input bridge and historical acceptance

The three included patches reproduce accepted bridge tree 5ce1b22 from pinned upstream ea55f66c8238235983d60d381bf2abe1fed50043. Bridge code was unchanged during plugin development. See [the original report](ACCEPTANCE.md) for prior bridge tests and hardware acceptance.

The owner previously confirmed both receiving monitors, typing, scrolling, return crossing, middle-click paste and the Shift/Codex correction: normal digits/Enter after releasing Shift and working Shift+Enter. The stuck-modifier regression fails without duplicate-transition filtering and passes with it. This plugin test does not claim a new full physical-input acceptance run.

## Practical limits

Tested with Synergy 3.8.4, Omarchy 4.0.6, Hyprland 0.56.2, Python 3.14 and wl-clipboard 2.3. The receiver has two adjacent 1920×1080 monitors at scale 1. Python 3.11+ is the intended minimum; older Python releases were not exercised here.

Not validated: full 128 MiB payloads, reboot persistence, long soak, fractional/mixed scaling, rotation/hotplug, full physical AltGr/Super/keyboard-layout coverage or additional distributions. Restart the input bridge after geometry changes. The optional caller-verification override reduces filesystem isolation and remains a maintainer-review point.

The companion supports text and PNG/JPEG/WebP/BMP, including middle-click PRIMARY. File-manager transfers, folders, rich text, history and selection clearing are not implemented. Raw logs, actual configuration, network addresses, deployment/rollback helpers, keys and backups remain outside the public repository.
