# Validation and limits

## Current repository candidate — 23 October 2026

The companion now offers explicit OpenSSH or Tailscale SSH transport. New examples select OpenSSH. Existing configurations without a transport field retain the tested Tailscale behavior. No automatic transport fallback is implemented.

The companion's 16 isolated checks pass on each of the two test computers, including SSH command construction, strict host checking, remote path quoting, legacy configuration compatibility and invalid transports. Protocol version 3, clipboard handling and Synergy gating are unchanged from the accepted baseline. Installation paths remain at their original stable user-local locations.

The owner authorized moving the running pair to direct LAN SSH. Both installed scripts now match this candidate; the coordinator uses its existing pinned LAN alias and a live OpenSSH child. Previous scripts/configuration and a hash-guarded rollback command remain private. This migration changes only clipboard code/configuration; input bridge, Synergy layout/account settings and SSH trust are retained.

Live LAN acceptance: exact Unicode/multiline text and PNG transfer in both directions; independent PRIMARY in both directions without changing the regular clipboard; no regular/PRIMARY transfer while the receiving Synergy service is disconnected; fresh transfer after resume; coordinator restart and reverse PRIMARY recovery. Prior supported selections were held only in memory and restored before resuming source-authoritative sharing. Existing clipboard data was not logged or saved.

The three included bridge patches reproduce the accepted bridge tree at local commit 5ce1b22 from pinned upstream ea55f66c8238235983d60d381bf2abe1fed50043. Their upstream license is preserved. This packaging/transport change does not modify the bridge source, so its build result remains the prior two-machine acceptance described below.

## Original hardware acceptance

See [the baseline report](ACCEPTANCE.md) for the earlier Tailscale run, source hash and input tests. Both computers passed six bridge checks and 13 original isolated companion checks, plus real text/PNG, independent PRIMARY, source seeding, Synergy pause and coordinator/endpoint reconnect. The owner confirmed both receiving monitors, typing, scrolling, return crossing, middle-click paste and the Shift/Codex correction, including normal digits/Enter after releasing Shift and working Shift+Enter.

The original stuck-modifier regression fails without duplicate-transition filtering and passes with it. The accepted input bridge remains running; no new physical input acceptance is claimed for this clipboard-only change.

## Practical limits

Tested with Synergy 3.8.4, Omarchy 4.0.6, Hyprland 0.56.2, Python 3.14 and wl-clipboard 2.3. Receiver: two adjacent 1920×1080 monitors at scale 1. Python 3.11+ is the intended minimum, but older Python releases have not been exercised here.

Not validated: reboot persistence, long soak, fractional/mixed scaling, rotation/hotplug, full physical AltGr/Super/keyboard-layout coverage or additional distributions. Restart the input bridge after geometry changes. The optional caller-verification override reduces filesystem isolation and remains a maintainer-review point.

The plugin and pairing wizard are a design only: no plugin manifest, QML implementation or plugin acceptance is included. See [the design](PLUGIN-DESIGN.md). Public commit authorship and publication remain pending review.

Raw logs, private network addresses, actual peer configuration, deployment/rollback helpers, keys and backups are excluded from this repository. The Synergy layout report and two bridge PR drafts are separately prepared for review; no upstream submission has been made.
