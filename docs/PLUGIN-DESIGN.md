# Omarchy plugin and pairing design

Design for review, not an implemented plugin. The repository currently has no root manifest or QML entry point and must not be advertised as installable through `omarchy plugin add` yet.

Omarchy supports Git-installed shell plugins, including bar widgets and headless services. Its [shell documentation](https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md) describes manifests and lifecycle; the [official manual](https://omarchy.org/manual/shell-plugins/) covers installation. A small front end fits here, while clipboard transfer remains in the independently managed systemd service. Shell reloads should not interrupt a clipboard connection.

## Pair two devices

Install the same plugin/companion version on both devices. The first-run flow would:

1. Choose this device's role: **Keyboard and mouse source** or **Receiving computer**. Only the source starts a coordinator; both endpoints share clipboard contents in both directions.
2. Choose the connection: **Direct LAN (SSH)** or **Tailscale (SSH)**. Both encrypt clipboard traffic. Tailscale is optional; a normal SSH alias can also reach a VPN or other network.
3. On the receiver, show the current user's endpoint details and companion location. On the source, enter the receiver's SSH address/alias and select the intended Synergy peer by name. Keep addresses and peer IDs in private local configuration.
4. Check noninteractive SSH authentication, expected host identity, companion protocol version, active Wayland session, data-control support and remote requirements. Only the source needs SSH access to the receiver. Do not infer SSH identity from a matching display name.
5. Show the proposed roles, transport and whether existing selections would be replaced. Default to future changes only. Enable sharing explicitly after the checks pass.

This pairs an existing Synergy connection with the companion; it does not replace Synergy's account, licensing or device-pairing interface. Do not automatically change SSH trust, copy private keys, enable an SSH server, alter router/firewall settings, install the receiving input bridge, or replace portal configuration. Provide the relevant guide steps and explain missing requirements.

## Controls and lifecycle

Show distinct states: companion stopped, SSH connecting/disconnected, Synergy unavailable/paused, and sharing active. A running process alone must not be labeled as active sharing. The backend needs a small local status interface exposing state/reason and peer display information without clipboard contents or full vendor settings. That status interface is not implemented yet.

Offer explicit **Pause clipboard sharing**, **Resume**, **Reconnect**, **Open Synergy** and **Setup guide** actions. Stopping the companion is the current reliable way to pause all its transfer. A later persistent-pause API must enforce both directions and remain paused across service/shell restarts. Do not make the monitor merely appear paused while the daemon continues transferring.

Keep the transport service independent of shell enable/disable. Disabling the widget must clearly say that it hides controls and does not stop an independently enabled service; offer a separate stop-sharing action. Removing plugin files must not silently leave executable service paths pointing into a deleted checkout. Use the existing stable user-local installation paths and a deliberate upgrade/uninstall flow.

No automatic fallback between transports: show failures and let the owner choose another configured route. Preserve host verification and avoid creating two coordinators for the same pair. Plugin updates must not silently deploy mismatched endpoints or replace private configuration.

## Acceptance before release as a plugin

Validate the manifest with the target Omarchy version, test disabled/enable/reload/update/remove behavior, and exercise the whole pairing flow on two devices. Test both transport choices, host-key/authentication failure, unavailable Wayland, protocol mismatch, existing installs and duplicate-source attempts. Verify real text/image/PRIMARY transfers, Synergy pause/reconnect, explicit pause and removal semantics. Neither a design document nor isolated companion tests count as plugin acceptance.
