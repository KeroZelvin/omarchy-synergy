pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "community.omarchy-synergy"
  ipcTarget: "community.omarchy-synergy"
  manageIpc: false

  property string step: "home"
  property bool busy: false
  property string pending: ""
  property string payload: ""
  property string activeJob: ""
  property string jobAction: ""
  property var queuedRequest: null
  readonly property bool actionBusy: activeJob !== "" || queuedRequest !== null || (busy && pending !== "status")
  property string errorText: ""
  property string message: ""
  property var summary: ({ role: "unconfigured", state: "loading" })
  property var peers: []
  property var preview: ({})
  readonly property string backendPath: decodeURIComponent(String(Qt.resolvedUrl("plugin.py")).replace(/^file:\/\//, ""))
  readonly property string statusText: stateLabel(String(summary.state || "loading"))
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function stateLabel(state) {
    var labels = { sharing: "Sharing active", "manual-paused": "Clipboard sharing paused",
      "peer-paused": "Paused on the other computer", "synergy-paused": "Waiting for Synergy",
      connecting: "Connecting over SSH", disconnected: "SSH disconnected — retrying",
      stopped: "Clipboard service stopped", "receiver-ready": "Receiver ready — waiting for source",
      starting: "Starting or update needed", "configuration-error": "Configuration needs attention",
      loading: "Reading status" }
    return labels[state] || "Not paired yet"
  }

  function request(action, values) {
    if (activeJob && action !== "job") return false
    if (rpc.running) {
      if (action === "status") return false
      queuedRequest = { action: action, values: values }
      busy = true
      return true
    }
    pending = action
    var data = values || {}
    data.action = action
    payload = JSON.stringify(data)
    busy = true
    if (action !== "status") errorText = ""
    rpc.command = ["/usr/bin/python3", backendPath, "rpc"]
    rpc.running = true
    return true
  }

  function sourceValues() {
    return { transport: transport.currentIndex === 0 ? "ssh" : "tailscale",
      remote_host: host.text.trim(), peer_id: peer.currentValue || "",
      initial_sync: seed.checked ? "source" : "none", max_mib: limit.value }
  }

  function beginSetup() {
    preview = ({})
    message = ""
    step = "role"
    open()
    request("bootstrap")
  }

  function checkSource() { preview = ({}); request("check_source", sourceValues()) }
  function reviewReceiver() { preview = ({}); request("receiver_preview", { max_mib: limit.value }) }
  function confirmReview() {
    if (!preview.token || actionBusy) return
    var values = step === "source-review" ? sourceValues() : { max_mib: limit.value }
    values.token = preview.token
    values.confirm = true
    request(step === "source-review" ? "apply_source" : "prepare_receiver", values)
  }

  function handleResult(text) {
    var result
    try { result = JSON.parse(text) }
    catch (_) { errorText = "The companion did not return a valid response."; busy = false; return }
    if (result.pending && result.job) {
      if (!activeJob) jobAction = pending
      activeJob = result.job
      return
    }
    var action = activeJob ? jobAction : pending
    activeJob = ""
    busy = queuedRequest !== null
    if (result.ok !== true) { errorText = result.error || "Setup could not complete."; preview = ({}); return }
    if (action === "receiver_preview" || action === "check_source") {
      preview = result
      step = action === "receiver_preview" ? "receiver-review" : "source-review"
    } else {
      var previousLimit = root.summary.requested_max_mib || 8
      summary = result
      if (result.requested_max_mib && (action === "bootstrap" || result.requested_max_mib !== previousLimit) && !pairLimit.activeFocus)
        pairLimit.value = result.requested_max_mib
      if (action === "bootstrap") {
        peers = result.peers || []
        var c = result.config || {}
        transport.currentIndex = c.transport === "tailscale" ? 1 : 0
        host.text = c.remote_host || ""
        seed.checked = c.initial_sync === "source"
        limit.value = result.requested_max_mib || c.max_mib || result.max_mib || 8
        for (var i = 0; i < peers.length; ++i) if (peers[i].id === c.peer_id) peer.currentIndex = i
      }
      if (result.message) message = result.message
      if (action === "prepare_receiver" || action === "apply_source") { step = "home"; preview = ({}) }
    }
  }

  Component.onCompleted: request("bootstrap")

  Process {
    id: rpc
    stdinEnabled: true
    onStarted: write(root.payload + "\n")
    stdout: StdioCollector { onStreamFinished: root.handleResult(text) }
    stderr: StdioCollector { }
    onExited: function(code, status) {
      if (code !== 0) { root.busy = false; root.activeJob = ""; root.errorText = "The companion could not run. Open Setup to check the installation." }
      if (root.queuedRequest) Qt.callLater(function() {
        var next = root.queuedRequest
        root.queuedRequest = null
        root.request(next.action, next.values)
      })
    }
  }

  Timer {
    interval: 1000
    running: true
    repeat: true
    property int ticks: 0
    onTriggered: {
      if (rpc.running) return
      if (root.activeJob) root.request("job", { job: root.activeJob })
      else if (!root.busy && root.step === "home" && ++ticks % 3 === 0) root.request("status")
    }
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function setup(): void { root.beginSetup() }
    function receiver(maxMiB: int): void { limit.value = maxMiB; root.reviewReceiver(); root.open() }
    function form(json: string): string {
      if (root.busy) return "busy"
      var value = JSON.parse(json)
      root.preview = ({})
      root.step = "connection"
      transport.currentIndex = value.transport === "tailscale" ? 1 : 0
      host.text = value.host || ""
      limit.value = value.max_mib || 8
      seed.checked = value.initial_sync === "source"
      for (var i = 0; i < root.peers.length; ++i) if (root.peers[i].name === value.peer) peer.currentIndex = i
      root.open()
      return "ok"
    }
    function check(): void { root.checkSource() }
    function confirm(): void { root.confirmReview() }
    function pause(): void { root.request("pause") }
    function resume(): void { root.request("resume") }
    function reconnect(): void { root.request("reconnect") }
    function allowSecret(): void { root.request("allow_secret") }
    function setLimit(maxMiB: int): void { pairLimit.value = maxMiB; root.request("set_limit", { max_mib: maxMiB }) }
    function state(): string { return JSON.stringify({ step: root.step, busy: root.busy, state: root.summary.state || "", role: root.summary.role || "", error: root.errorText, review: !!root.preview.token, max_mib: root.preview.max_mib || root.summary.max_mib || 8, requested_max_mib: root.summary.requested_max_mib || 8, limit_pending: !!root.summary.limit_pending, secret_allowed: !!root.summary.secret_allowed, secret_withheld: !!root.summary.secret_withheld }) }
    function geometry(): string { return JSON.stringify({ screen: popup.screen ? popup.screen.name : "", x: popup.cardOrigin.x, y: popup.cardOrigin.y, width: popup.contentWidth, height: popup.contentHeight }) }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰍹"
    active: root.summary.state === "sharing"
    activeColor: Commons.Color.accent
    tooltipText: "Synergy · " + root.statusText
    onPressed: root.toggle()
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: content
    contentWidth: fittedContentWidth(Style.space(490))
    contentHeight: fittedContentHeight(formColumn.implicitHeight, Style.space(720))

    FocusScope {
      id: content
      anchors.fill: parent
      Keys.onEscapePressed: root.close()
      ScrollView {
        id: scroller
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
          id: formColumn
          width: scroller.availableWidth
          spacing: Style.space(12)
          Copy {
            text: "Synergy"
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Copy { text: root.statusText; color: root.summary.state === "sharing" ? Commons.Color.accent : Commons.Color.foreground }
          Copy {
            visible: root.summary.role !== "unconfigured"
            text: (root.summary.role === "source" ? "Keyboard/mouse source" : "Receiving computer") +
              (root.summary.transport ? " · " + (root.summary.transport === "ssh" ? "Direct LAN (SSH)" : "Tailscale (SSH)") : "") +
              " · " + (root.summary.max_mib || 8) + " MiB image/text limit"
          }
          Copy { visible: root.errorText !== ""; text: root.errorText; color: Commons.Color.urgent }
          Copy { visible: root.message !== ""; text: root.message }
          BusyIndicator { visible: root.actionBusy; running: root.actionBusy; Layout.alignment: Qt.AlignHCenter }

          ColumnLayout {
            visible: root.step === "home"
            Layout.fillWidth: true
            spacing: Style.space(10)
            RowLayout {
              Action { text: "Pair / Setup"; onClicked: root.beginSetup() }
              Action { text: "Open Synergy"; onClicked: Quickshell.execDetached(["/opt/Synergy/synergy"]) }
            }
            RowLayout {
              visible: root.summary.role !== "unconfigured"
              Action { text: "Pause sharing"; onClicked: root.request("pause") }
              Action { text: "Resume"; onClicked: root.request("resume") }
              Action { text: "Reconnect"; onClicked: root.request("reconnect") }
            }
            Copy { visible: !!root.summary.secret_withheld && !root.summary.secret_allowed; text: "A password-manager copy was kept on this computer."; color: Commons.Color.urgent }
            RowLayout {
              visible: root.summary.role !== "unconfigured"
              Action {
                text: root.summary.secret_allowed ? "Cancel secret sharing" : "Send one secret"
                onClicked: root.request(root.summary.secret_allowed ? "cancel_secret" : "allow_secret")
              }
              Copy { text: "Password-manager copies stay local unless you allow one. Applies to Ctrl+C copies, never highlights."; font.pixelSize: Style.font.bodySmall }
            }
            Copy { visible: root.summary.role !== "unconfigured"; text: "Transfer limit for both computers"; font.bold: true }
            RowLayout {
              visible: root.summary.role !== "unconfigured"
              SpinBox { id: pairLimit; objectName: "pairLimit"; from: 1; to: 128; value: 8; editable: true }
              Copy { text: "MiB"; Layout.fillWidth: false }
              Action { text: "Apply to both computers"; primary: true; onClicked: root.request("set_limit", { max_mib: pairLimit.value }) }
            }
            Copy { visible: !!root.summary.limit_pending; text: "Limit change pending — synchronizes when connected." }
            Action { text: "Setup guide"; onClicked: Quickshell.execDetached(["xdg-open", decodeURIComponent(String(Qt.resolvedUrl("docs/OMARCHY-GUIDE.md")).replace(/^file:\/\//, ""))]) }
            Copy { text: "Hiding or removing this widget leaves the independent companion service installed. Pause sharing here before removing it."; font.pixelSize: Style.font.bodySmall }
          }

          ColumnLayout {
            visible: root.step === "role"
            Layout.fillWidth: true
            Copy { text: "What does this computer do?"; font.bold: true }
            Copy { text: "Prepare the receiver first. Then pair from the computer with the physical keyboard and mouse. Pair the devices in Synergy itself before using this wizard." }
            Action { text: "Keyboard and mouse source"; onClicked: root.step = "connection" }
            Action { text: "Receiving computer"; onClicked: root.reviewReceiver() }
          }

          ColumnLayout {
            visible: root.step === "connection"
            Layout.fillWidth: true
            Copy { text: "Connect to the receiving computer"; font.bold: true }
            ComboBox {
              id: transport
              objectName: "transport"
              Layout.fillWidth: true
              model: ["Direct LAN (SSH)", "Tailscale (SSH)"]
            }
            TextField {
              id: host
              objectName: "host"
              Layout.fillWidth: true
              placeholderText: transport.currentIndex === 0 ? "SSH alias or user@LAN-address" : "user@tailscale-peer"
              selectByMouse: true
            }
            Copy { text: "Both modes encrypt clipboard traffic. SSH access and host trust must already work; this wizard does not change keys, accounts or network settings."; font.pixelSize: Style.font.bodySmall }
            Copy { text: "Receiving device in Synergy" }
            ComboBox {
              id: peer
              objectName: "peer"
              Layout.fillWidth: true
              model: root.peers
              textRole: "name"
              valueRole: "id"
            }
            CheckBox {
              id: seed
              Layout.fillWidth: true
              text: "Replace the receiver's selections on each new connection"
              checked: false
            }
            Action { text: "Check connection and review"; primary: true; enabled: !root.actionBusy && host.text.trim() !== "" && peer.currentIndex >= 0; onClicked: root.checkSource() }
          }

          RowLayout {
            visible: root.step === "role" || root.step === "connection"
            Copy { text: "Image/text limit (MiB)" }
            SpinBox { id: limit; objectName: "limit"; from: 1; to: 128; value: 8; editable: true }
          }

          ColumnLayout {
            visible: root.step === "receiver-review" || root.step === "source-review"
            Layout.fillWidth: true
            Copy { text: "Review before enabling"; font.bold: true }
            Copy { text: root.step === "receiver-review" ? "Prepare this computer as receiver" : "Pair with " + (root.preview.receiver || "receiver") }
            Copy { text: root.preview.changes || "" }
            Copy { text: "Image/text limit for the pair: " + (root.preview.max_mib || 8) + " MiB. The receiving setting synchronizes automatically." }
            Copy { text: "SSH, host identity, companion version, Synergy peer identity and Wayland data-control checks must pass. No input-bridge or portal settings are changed by this wizard."; font.pixelSize: Style.font.bodySmall }
            Action { text: root.step === "receiver-review" ? "Prepare receiver" : "Save pairing and enable"; primary: true; enabled: !root.actionBusy && !!root.preview.token; onClicked: root.confirmReview() }
          }
          Action { visible: root.step !== "home"; text: "Cancel / Back"; onClicked: { root.step = "home"; root.preview = ({}) } }
        }
      }
    }
  }

  component Copy: Label {
    Layout.fillWidth: true
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    color: Commons.Color.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.body
  }
  component Action: Button {
    property bool primary: false
    enabled: !root.actionBusy
    bordered: true
    focusable: true
    horizontalPadding: Style.space(12)
    verticalPadding: Style.space(8)
    fontFamily: Style.font.family
    fontSize: Style.font.body
    foreground: Commons.Color.foreground
    readonly property color tint: primary ? Commons.Color.accent : Commons.Color.foreground
    background: Qt.rgba(tint.r, tint.g, tint.b, primary ? 0.14 : 0.09)
    opacity: enabled ? 1 : 0.45
  }
}
