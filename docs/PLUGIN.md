# Omarchy plugin and pairing wizard

The experimental plugin adds a Synergy button to the Omarchy bar. It shows actual companion state, offers persistent pause/resume and reconnect, pairs one source with one receiver, and changes the image/text limit for both computers.

## Before pairing

Install the same plugin revision on both computers. Synergy 3 must already be licensed, signed in and paired, with input working. The receiving input bridge is a separate step in [the Omarchy guide](OMARCHY-GUIDE.md); the wizard does not install it or change portal routing.

Both sessions need Python 3.11+, wl-clipboard and Wayland data-control. On the source, establish trusted, noninteractive SSH access to the receiver first. Choose:

- **Direct LAN (SSH)**: a normal OpenSSH alias or `USER@LAN-ADDRESS`. Put custom ports, identity files and hostnames in your own SSH config. Strict host checking and batch authentication remain enabled.
- **Tailscale (SSH)**: `USER@TAILSCALE-PEER` using an existing authorized Tailscale SSH connection. Tailscale is optional when using OpenSSH.

Both modes encrypt clipboard traffic. Only the source needs SSH access to the receiver; clipboard contents travel both ways on that connection. The wizard does not create keys, approve a changed host key, set up accounts/SSH servers, change firewall/router rules or sign into Synergy.

## Install the plugin

After a public repository exists, add its Git URL through **Setup → Plugins → Add**, review it, and enable it. The equivalent is `omarchy plugin add REPOSITORY_URL --enable`, replacing the URL with the reviewed project location. No public URL has been assigned to this review candidate.

For a local Git checkout, run this from its root on each computer:

```bash
omarchy plugin validate .
omarchy plugin add "file://$PWD" --enable
```

The plugin ID is `community.omarchy-synergy`. Its files live under `~/.config/omarchy/plugins/`. Installation adds the widget; clipboard setup still requires explicit review in the wizard. A user-owned local checkout is enough; no vendor binaries or credentials belong in it.

## Prepare the receiver, then pair the source

1. On the receiving computer, open the Synergy bar button and choose **Pair / Setup → Receiving computer**. Review the proposed user-local installation and click **Prepare receiver**. Existing companion files are backed up. No coordinator is started there. The wizard refuses to turn a configured source into a receiver.
2. On the computer with the physical keyboard/mouse, choose **Pair / Setup → Keyboard and mouse source**. Select Direct LAN or Tailscale, enter the receiver's SSH address/alias, then choose that same computer from Synergy's device list.
3. Choose an image/text limit. Default selection seeding is off for a new pair. The replacement checkbox deliberately copies the source's supported selections to the receiver once after each new SSH connection; it is not repeated on every Synergy pause/resume.
4. Click **Check connection and review**. Checks cover the authenticated SSH endpoint, matching companion code/protocol, selected Synergy identity, active Wayland session and data-control support. Checking does not replace your pairing.
5. Review the receiver, limit, selection policy and file/service changes, then click **Save pairing and enable**. Confirmation rechecks the endpoint and existing files. If they changed, review again. A failed activation restores the previous local files/service state.

The coordinator runs as a systemd user service from stable `~/.local/lib/synergy-clipboard/` paths. Setup jobs are separate from the shell process, so closing/reloading the widget does not kill an already started setup transaction. Private job results and backups stay under the user's state directory, not in the plugin Git checkout.

## Change larger image/text transfers

On either computer, set **Transfer limit for both computers**, then click **Apply to both computers**. Values are whole MiB from 1 to 128, measured as decoded data per item. The change is sent over the existing encrypted connection and acknowledged by the other endpoint. No re-pairing or second manual setting is needed.

The panel shows a pending message until synchronization completes. An offline change is saved and delivered after reconnection. If both people edit simultaneously, the last change accepted by the source wins; wait for acknowledgment before making another change. Limit policy is persisted privately in `~/.config/synergy-clipboard/limits.json`; the source TOML limit supplies the initial default before a pair policy exists.

Increasing the limit allows larger text/images; it does not add file-manager copy/paste. The companion still supports one UTF-8 text or PNG/JPEG/WebP/BMP representation, without rich text, file lists, folders, drag-and-drop, history or selection clearing. Larger items use more memory for their encoded transfer buffers. See [validation](VALIDATION.md) for the sizes actually tested.

## Pause and reconnect

**Pause sharing** works from either endpoint and persists across service restarts and reconnections. Source pause stops its coordinator; receiver pause tells the source to pause both directions while retaining the control connection. **Resume** clears that computer's pause. If the other computer remains paused, the panel says so. A short polling/transport delay applies; this is a convenience control, not a lock-screen security boundary.

**Reconnect** restarts the coordinator on the source, or requests a fresh endpoint connection from the receiver. It does not clear a saved pause. Synergy's own core/peer/allow-copy gate remains enforced independently. The panel distinguishes stopped, connecting, disconnected, Synergy-waiting, locally paused, peer-paused and active sharing states.

The service follows Synergy connection state, not pointer focus or screen-lock state. Supported copied content is shared while enabled, so both devices must be trusted.

## Update or remove

Use `omarchy plugin update community.omarchy-synergy` to review and update the plugin checkout. To update companion runtime code, repeat receiver preparation and source pairing with the matching plugin revision. The wizard backs up files and checks compatibility; merely updating or reloading a widget does not silently overwrite the running companion. Some QML changes on the tested Omarchy 4.0.6 shell required `omarchy restart shell` to load fully; this does not restart the clipboard service.

Disabling/removing the widget hides its controls and leaves the separately installed companion running. To stop sharing first, use **Pause sharing** on the source, or:

```bash
systemctl --user disable --now synergy-clipboard.service
```

Then remove the widget with `omarchy plugin remove community.omarchy-synergy`. The source's SSH closure stops its receiver endpoint. Keep the companion files/configuration if you want to resume later; remove them only after both endpoints have stopped. User-local backups remain private for recovery. No Omarchy package files need modification.

For test scope, source revisions and current limitations, read [validation](VALIDATION.md). For implementation contracts, see [the architecture notes](PLUGIN-DESIGN.md).
