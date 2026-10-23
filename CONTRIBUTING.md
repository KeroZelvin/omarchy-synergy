# Contributing

Keep the companion usable independently of an Omarchy shell plugin. Preserve selection isolation, bounded frames, fail-closed Synergy gating, remote-shell argument quoting, SSH host verification and the installer's refusal to replace existing files.

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

The isolated tests use temporary directories and mocked clipboard writes; they do not access your desktop clipboard. Test transport construction and invalid configuration as well as the default and optional paths when changing connection setup. Native clipboard tests need two consenting Wayland sessions and must preserve supported existing selections without logging their contents.

Keep input-bridge fixes scoped for the existing upstream project. The included series is pinned and documented under [patches/input-bridge](patches/input-bridge/README.md). Do not change the caller policy to unconditional empty-app-ID acceptance or advertise a Clipboard portal that is not implemented.

Public reports should include software versions, reproducible steps and sanitized diagnostics. Do not include full Synergy settings/diagnostic archives, personal config, peer IDs, license data, SSH keys or clipboard payloads. Describe the transport and test environment without publishing private addresses.

The proposed plugin needs implementation and lifecycle/pairing acceptance before being listed as supported; see [the design](docs/PLUGIN-DESIGN.md).
