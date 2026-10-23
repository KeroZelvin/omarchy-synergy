# omarchy-synergy

A community integration for Synergy 3 on Omarchy/Hyprland: an Omarchy bar plugin and pairing wizard, setup instructions, reviewed input-bridge patches, and a clipboard companion for one pair of Wayland computers.

The companion shares the regular clipboard and the primary selection (highlight text, then middle-click) independently and in both directions. It follows Synergy's core/peer connection state and allow-copy setting, with a short polling delay. Transfers use an existing trusted OpenSSH connection over your LAN or VPN; Tailscale SSH is an optional transport.

## Start here

- [Omarchy setup guide](docs/OMARCHY-GUIDE.md): Synergy, the receiving input bridge, layout workaround and clipboard setup.
- [Clipboard installation and configuration](docs/clipboard.md): requirements, SSH choice, startup, pause and removal.
- [Input bridge patch series](patches/input-bridge/README.md): pinned upstream base, provenance and application instructions.
- [Validation and limits](docs/VALIDATION.md), including [the original two-computer acceptance](docs/ACCEPTANCE.md).
- [Plugin and pairing wizard](docs/PLUGIN.md): Direct LAN (SSH), Tailscale (SSH), status, persistent pause and pair-wide size controls.
- [Plugin architecture](docs/PLUGIN-DESIGN.md): runtime, pairing and lifecycle contracts.
- [Credits](docs/CREDITS.md) and [contributing](CONTRIBUTING.md).

## Status

Experimental. The accepted setup used Synergy 3.8.4, Omarchy 4.0.6 and Hyprland 0.56.2, with two receiving 1920×1080 monitors at scale 1. Input, middle-click sharing, clipboard pause/reconnect and the stuck-Shift correction passed owner acceptance. See the validation notes for which transport/revision has been tested and the limits of that result.

The Python companion and example configuration are at the repository root. Run its isolated checks there:

```bash
python3 -m unittest discover -s tests -v
```

The manual installer writes user files only, refuses existing destinations and starts nothing. The plugin wizard offers a separate reviewed setup/update flow with backups and explicit activation. No Synergy package, license, account credentials, SSH identity or personal machine configuration is included.

The input bridge comes from the existing wayland-kdeconnect-fix project; its patches remain candidates for upstream contribution. This repository is an independent community project, with no claimed endorsement from Omarchy, Symless or Deskflow. The plugin supplies its own manifest and QML panel. Clipboard runtime files use stable user-local paths and stay independent of the widget lifecycle.

## Clipboard scope

Supports one UTF-8 text or PNG/JPEG/WebP/BMP representation per change, with a default 8 MiB limit. The plugin supports a pair-wide limit from 1–128 MiB, synchronized from either endpoint. It does not synchronize rich text, file lists, drag-and-drop, clipboard history or selection clearing. Both computers must be trusted: supported copied contents are shared while enabled. The Synergy gate does not track pointer focus or lock-screen state and is not a security boundary.

The clipboard code and documentation use the [MIT license](LICENSE). The bridge patches retain their own [upstream MIT notice](patches/input-bridge/UPSTREAM-LICENSE).
