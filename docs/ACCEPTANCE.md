# Baseline acceptance — 23 October 2026

The owner confirmed the cleaned setup works, including the previously broken Shift behavior. The cleaned receiver bridge and both clipboard endpoints remain activated. Publication is still pending review. This report records the original Tailscale transport before the optional OpenSSH addition; see [current validation](VALIDATION.md) for the later candidate.

## Revisions

The bridge is based on upstream `ea55f66c8238235983d60d381bf2abe1fed50043`, with three local commits in two proposed PRs:

1. `d718a9a` — verify native Synergy callers.
2. `dc91c15` — EIS input, modifier propagation and static output bounds.
3. `5ce1b22` — integrate the receiving-machine duplicate-key correction to prevent stuck Shift.

The Shift correction tracks pressed evdev codes and updates xkb/emits virtual-key events only on real transitions. One release now clears one held modifier even if duplicate downs were received. It preserves a second independently held Shift key and lock state. Existing modifier serialization reads that updated state without updating it a second time.

Installed clipboard source SHA256 on both computers: `3905dce8fa230bef5800accd4f86174e2d87d131baba44ceff132ecffeba0472`. This is the configurable protocol-v3 source from the companion candidate; documentation commits do not change this code hash. The running receiving binary also matches the candidate built on that computer.

## Automated acceptance

- Release builds and six bridge checks pass on both computers.
- The duplicate-key regression fails with the old behavior and passes with transition filtering.
- Thirteen isolated clipboard tests pass on each computer.
- Real UTF-8/Unicode/multiline text and PNG transfer passes in both directions, with byte comparison and stable source checks.
- Primary-selection transfer passes in both directions without changing the regular clipboard.
- Source-authoritative seeding replaces stale remote selections after reconnect, as configured for the test pair.
- Transfers pause when the receiving Synergy service disconnects, and fresh copies transfer after it reconnects.
- Coordinator restart and receiving-endpoint termination both recover automatically over the established encrypted SSH route; reverse primary transfer works afterward.
- Both Hyprland sessions report no configuration errors. The coordinator and receiving services are active after the checks.

Clipboard snapshots were retained in memory, not written or logged, and supported values were restored. The tests did not change SSH identities/trust, firewall rules, Synergy account settings or the working layout.

## Owner acceptance

Using the input-source keyboard and mouse, the owner confirmed traversal of both receiving monitors, typing, scrolling, return to the input source, middle-click paste, and the formerly broken Shift/Codex sequence. Releasing Shift restores ordinary digits/Enter behavior; Shift+Enter still works.

## Scope and rollback

The tested receiver has two adjacent 1920×1080 monitors at scale 1. The source uses its stock Hyprland InputCapture backend; only the receiver needs the RemoteDesktop bridge. The clipboard companion runs on both computers, coordinated from the input source.

The previous bridge, both clipboard scripts, coordinator unit and prior config state are preserved in private local/remote rollback directories. A local rollback command verifies the installed candidate hashes before restoring those files. These private backups/configuration are excluded from this package.

No reboot, long soak, general fractional-scale/rotation/hotplug test or broader distribution/layout acceptance is claimed. The optional service sandbox override remains a documented maintainer-review point. No PR, issue, support ticket, repository or release has been published.
