import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

// Dictation pill (Ctrl + Space), bottom centre on the focused screen: a red
// microphone and seven level bars that follow the voice while recording, a
// yellow spinner while transcribing. A badge (`hyprwink dictate --badge`)
// marks recordings of other programs. State, badge and microphone level
// come from `hyprwink watch`.
Item {
  id: root

  readonly property string cli: "hyprwink"
  readonly property int barCount: 7
  readonly property int pad: Style.space(16)
  readonly property color yellow: "#e0af68"

  property string vstate: "idle"
  property string badge: ""
  property real level: 0
  property var levels: [0, 0, 0, 0, 0, 0, 0]

  readonly property bool active: vstate === "recording" || vstate === "transcribing"
  readonly property bool recording: vstate === "recording"

  Process {
    id: watcher
    running: true
    command: [root.cli, "watch"]
    stdout: SplitParser {
      onRead: line => {
        try {
          var s = JSON.parse(line)
          root.vstate = s.dictation || "idle"
          root.badge = s.badge || ""
          root.level = Math.min(1, Math.pow((s.level || 0) * 4, 0.7))
        } catch (e) {}
      }
    }
    onExited: restart.start()
  }

  Timer {
    id: restart
    interval: 3000
    onTriggered: watcher.running = true
  }

  // The bars show the latest levels.
  Timer {
    interval: 60
    repeat: true
    running: root.recording
    onTriggered: {
      var next = root.levels.slice(1)
      next.push(root.level)
      root.levels = next
    }
    onRunningChanged: if (!running) { root.levels = [0, 0, 0, 0, 0, 0, 0]; root.level = 0 }
  }

  PanelWindow {
    visible: root.active
    // On the focused screen
    screen: Quickshell.screens.find(s => Hyprland.focusedMonitor && s.name === Hyprland.focusedMonitor.name) || Quickshell.screens[0]
    anchors.bottom: true
    margins.bottom: Style.space(67)
    // Fixed surface size: resizing the layer lags a frame behind and would
    // leave traces when switching to the spinner.
    implicitWidth: Style.space(240)
    implicitHeight: pill.height
    color: "transparent"
    WlrLayershell.namespace: "hyprwink-dictation"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    BorderSurface {
      id: pill
      anchors.horizontalCenter: parent.horizontalCenter
      width: pill.borderLeft + root.pad + (root.recording ? row.implicitWidth : spinner.width) + root.pad + pill.borderRight
      height: pill.borderTop + root.pad + Style.font.displayLarge + root.pad + pill.borderBottom
      Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
      color: Util.alpha(ShellColor.background, 0.97)
      borderSpec: Border.surfaceSpec("popups", "border", ShellColor.popups.border, Math.max(1, Style.space(2)))
      radius: 0

      Row {
        id: row
        anchors.centerIn: parent
        spacing: Style.space(14)
        visible: root.recording

        Text {
          visible: root.badge !== ""
          anchors.verticalCenter: parent.verticalCenter
          text: root.badge
          textFormat: Text.PlainText
          font.family: "JetBrainsMono Nerd Font Propo"
          font.pixelSize: Style.space(26)
          color: ShellColor.accent
        }

        Text {
          anchors.verticalCenter: parent.verticalCenter
          text: "󰍬"
          textFormat: Text.PlainText
          font.family: "JetBrainsMono Nerd Font Propo"
          font.pixelSize: Style.space(26)
          color: ShellColor.urgent
        }

        Row {
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(4)
          height: Style.space(28)

          Repeater {
            model: root.barCount
            Rectangle {
              required property int index
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(4)
              height: Style.space(5) + root.levels[index] * Style.space(23)
              color: ShellColor.popups.text
              Behavior on height { NumberAnimation { duration: 60 } }
            }
          }
        }
      }

      // Spinner with a growing and shrinking arc, flat ends. Outside the row
      // and only faded, so it is already drawn when it appears.
      Canvas {
        id: spinner
        anchors.centerIn: parent
        opacity: root.recording ? 0 : 1
        width: Style.space(26)
        height: width
        property real sweep: 0.1
        onSweepChanged: requestPaint()
        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          var r = width / 2 - Style.space(2)
          ctx.lineWidth = Style.space(3)
          ctx.lineCap = "butt"
          ctx.strokeStyle = root.yellow
          ctx.beginPath()
          ctx.arc(width / 2, height / 2, r, 0, Math.PI * 2 * sweep)
          ctx.stroke()
        }
        RotationAnimation on rotation {
          running: root.vstate === "transcribing"
          from: 0; to: 360; duration: 1100; loops: Animation.Infinite
        }
        SequentialAnimation on sweep {
          running: root.vstate === "transcribing"
          loops: Animation.Infinite
          NumberAnimation { from: 0.08; to: 0.75; duration: 650; easing.type: Easing.InOutCubic }
          NumberAnimation { from: 0.75; to: 0.08; duration: 650; easing.type: Easing.InOutCubic }
        }
      }
    }
  }
}
