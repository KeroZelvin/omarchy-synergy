# Validation and limits

## 0.2.1 guard-fix candidate — 24 October 2026

The candidate reads MIME types, content and any browser-source metadata through one read-only Wayland data-control connection, using the same offer ID for every representation. Selection replacement during capture aborts the operation. Received secrets are refused if sensitive marking is unavailable. This addresses the two 0.2.0 findings below; unrecognized/unmarked sources remain outside detection.

The current isolated suite passes 69 tests on the review checkout. The earlier code commit `2fc31d1` passed its then-current 64 tests on each computer. A private fake compositor supplies real Wayland messages and pipe file descriptors, replaces selections during payload and source-URL requests, and verifies that neither normal transfer nor initial sync sends unclassified data. Tests also cover content/source bounds, deadlines, fragmented messages, larger pipe transfers, descriptor cleanup, empty/unsupported selections, single-seat/v2 requirements and refusal when `wl-copy --sensitive` is absent.

Native capture checks passed on both test computers: ordinary text and valid PNG, marked copies on both regular clipboard and PRIMARY, ordinary/lookalike browser origins, recognized extension/desktop origins, and empty/invalid source metadata. Twelve cases passed per computer.

The candidate was installed receiver-first on the live LAN SSH pair, with matching runtime bundles and the existing 128 MiB limit. A complete 27-case paired run passed; a subsequent 31-case run also passed, adding exact 9,437,205-byte text and 16,784,432-byte PNG transfers in both directions. These runs cover regular clipboard/PRIMARY/PNG, default withholding, panel one-shot overrides, sensitive markers on receipt, second-secret refusal, PRIMARY exclusion without consuming an allowance, browser/desktop-source behavior and exclusion of marked copies from reconnect seeding. The input bridge, portal configuration and native Synergy processes were unchanged.

Two earlier combined runs had transient failed expectations: one reverse-direction default-block check and one reverse desktop-origin override check. The first did not record whether the unexpected clipboard was the secret or a different value; no leak is established. The isolated reverse run and both subsequent complete runs passed. Their cause remains unproven, so these passes do not establish long-soak reliability. Supported original selections were held in memory and restored before restarting the coordinator with the existing initial-sync policy; no values were logged or saved. No new physical-input acceptance is claimed. The candidate is not yet a published release.

### Startup/deadline follow-up review

Commit `d2b47fe` adds initial-snapshot `OSError` handling, converts a missing runtime-directory variable to a reader connection error, and extends total capture deadlines after actual payload delivery: four seconds initially, eight past 32 MiB, twelve past 64 MiB, all measured from capture start. Its 68 tests passed on the review checkout. This does not establish recovery from a permanently unavailable compositor: session initialization and the `wl-paste` watcher still have to succeed.

Review found a related handshake-budget regression: the receiver takes two initial snapshots before sending hello, so two permitted twelve-second captures can exceed the source's previous twenty-second handshake timeout. A scaled-clock asynchronous regression failed against that timeout and passes with a forty-second startup handshake budget. The complete suite now passes 69 tests locally; manifest validation and whitespace checks pass. The new startup/deadline changes have not been deployed or tested as a live pair in this follow-up. The 0.2.1 native/paired results recorded here apply to earlier code `2fc31d1`, not this revised runtime. These changes do not establish a cause for the two historical transient failures.

### Follow-up review of the transient failures

The earlier review at `4b77d5a` covered the complete PR #1 diff: offer identity and protocol framing, selection replacement, deadlines and descriptor cleanup, relay locking and echo suppression, sensitive-marker refusal, installation/bundle inclusion, prerequisite checks and guide changes. The then-current 64 isolated tests passed again on the review checkout. No additional release-blocking defect was identified in that diff.

The complete 27-case LAN run passed again. A separate bounded reverse-direction run then passed 40 cycles: 20 marked copies and 20 desktop-origin copies. Each cycle installed a fresh ordinary baseline, checked default withholding, confirmed that the copying computer still held the intended synthetic value before the panel override, checked the received sensitive marker, and checked that the allowance was consumed. These checks exercise both previously failing paths; they are not a long soak. Both installed runtimes remain matching at code commit `2fc31d1`, sharing at 128 MiB with no pending limit or allowance. Protected input configuration and native Synergy processes remain unchanged.

The original two failures cannot be assigned a cause retrospectively: their diagnostics did not identify the unexpected value or establish whether the intended source copy was still present. Concurrent clipboard writes can overwrite one another under the existing protocol, but no evidence establishes that as the cause here. The new harness identifies only known synthetic fixture labels on a mismatch, alongside availability, sensitivity and pair state; it never prints arbitrary clipboard values. No mismatch recurred in these follow-up runs. The review is complete, but the historical failures remain unresolved evidence, not fixed bugs or proof of a leak. Publication remains held; any experimental release decision must retain this limitation.

## 0.2.0 review findings

The tagged 0.2.0 guard is best-effort and is not a reliable secret-transfer boundary. `Clipboard.snapshot()` invokes `wl-paste` separately for advertised MIME types, content and optional browser source. An isolated review test reproduced a clipboard change between type discovery and content retrieval: the new marked payload was classified using the earlier ordinary offer and sent without an allowance. This test simulates the timing deterministically; it does not claim a live secret leak. Its 50-test suite does not cover this interleaving. The 0.2.1 candidate fixes the association by using a single Wayland offer; simply repeating type checks would not guarantee it.

Received secrets are re-marked only when the installed `wl-copy` supports `--sensitive`. With an older binary, 0.2.0 logs a warning and still writes the value without the marker. Check `wl-copy --help` on both computers before testing secret sharing. Unmarked managers and Firefox copies without recognizable source metadata remain outside detection. Pause sharing before copying sensitive information when withholding must be assured.

## 0.2.0 password-manager guard — 23 October 2026

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
