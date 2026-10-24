# Omarchy plugin architecture

The experimental implementation is a native Omarchy bar widget plus a Python backend. User instructions are in [the plugin guide](PLUGIN.md); tested behavior and limits are in [validation](VALIDATION.md).

## Shell and backend

`manifest.json` registers `community.omarchy-synergy` with `Panel.qml`. The panel uses native Omarchy controls. A bounded JSON request on stdin invokes `plugin.py rpc`; responses contain allowlisted status and review data, never clipboard contents or the complete Synergy settings response. Background status polling leaves controls and the spinner unchanged. Foreground requests queue behind a running status request.

`synergy_plugin/runtime.py` checks the local Synergy API, Wayland data-control globals and user-service state. Runtime status records are private, short-lived and tied to the worker PID/start time. A running process alone is not reported as active sharing. The display distinguishes SSH connection state, local/peer pause and Synergy gating.

## Pairing transaction

The receiver must be prepared first. Only the source runs a coordinator. Both endpoints use the same wire protocol and exact runtime bundle digest; a widget update does not silently replace the installed runtime.

The source checks noninteractive SSH, the authenticated endpoint, receiver role, runtime compatibility, Wayland requirements and the receiver's Synergy ID against the selected peer. It does not equate a display name with host identity. Direct LAN uses existing OpenSSH configuration with strict host checking; the optional Tailscale mode uses existing Tailscale SSH authorization. No automatic transport fallback is attempted.

Review tokens bind confirmation to the proposed files/settings and endpoint. Confirmation rechecks them. `synergy_plugin/storage.py` backs up existing user-local files and replaces them atomically. Failed source activation restores the previous local files/service state. Preparing a receiver refuses an existing source configuration/service, avoiding duplicate coordinators.

`synergy_plugin/jobs.py` runs durable setup jobs separately from the shell, under a setup lock. Requests expire, private results survive a shell reload, and request files are removed after consumption. Closing the panel does not cancel a setup transaction already started.

## Independent service and policy

Stable runtime files live in `~/.local/lib/synergy-clipboard/`; private configuration and policy live in `~/.config/synergy-clipboard/`. The source coordinator is a systemd user service. Plugin disabling, removal or shell restart does not delete that runtime or terminate an enabled service. The UI and guide explain how to pause/stop sharing before removal.

`relay.py` watches independent CLIPBOARD and PRIMARY selections and sends bounded, validated text/image frames over one encrypted connection. It retains Synergy core, peer-connected and allow-copy gates. Persistent manual pause applies to both directions; the receiver advertises pause to the source. Reconnect does not clear pause. This is not a pointer-focus or screen-lock gate.

`clipboard_offer.py` captures metadata and payload from one `zwlr_data_control_offer_v1` object using a read-only connection and standard-library Unix sockets/FD passing. It binds data-control v2 and exactly one seat, then uses the selected offer ID for content and browser-source reads. Selection replacement aborts capture. The worker-thread reader has one total four-second deadline (extended to 8 seconds past 32 MiB and 12 seconds past 64 MiB of payload, measured from capture start), bounded payload/source buffers and bounded protocol events, and closes its connection/pipes on success or failure. It never sets a selection. `wl-paste --watch` remains a notification source only. Recognized secrets require a one-shot allowance for regular clipboard, are excluded from PRIMARY and initial sync, and are refused at the receiver if `wl-copy --sensitive` is unavailable.

`sharing_state.py` persists a pair-wide 1–128 MiB policy with request IDs and acknowledgments. Either endpoint can request a change. The source arbitrates, distributes and persists the accepted limit; pending receiver edits survive disconnection and cannot be overwritten by an older acknowledgment. Concurrent edits resolve in source acceptance order. Wire protocol 5 carries the control messages. Earlier protocol versions are rejected. Stream buffers accommodate the hard maximum, while payload parsing and clipboard capture use the active limit.

## Deliberate boundaries

The wizard does not install the input bridge, alter portal routing, sign into Synergy, create SSH keys, approve changed hosts, start an SSH server, or change network/router/firewall settings. The receiving input bridge remains a separate, documented installation.

Payloads, private addresses, actual peer IDs, keys and backups are excluded from the repository. File-manager files, folders, rich text, clipboard history and selection clearing are not implemented. Larger items require encoded buffers in memory; see validation for actual transfer sizes exercised.
