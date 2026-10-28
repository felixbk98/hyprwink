import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

// Hyprwink: hand symbol, always shown. White = active, dim = paused
// or not running. Left click switches it on/off, right click opens the
// window. State comes from `hyprwink watch`. With "Blickpunkt anzeigen"
// the gaze point is drawn as a dot on this bar's screen (click-through).
BarWidget {
  id: root
  moduleName: "hyprwink"

  readonly property string cli: "hyprwink"
  property var state: ({ offline: true })
  readonly property bool online: !state.offline

  // Always shown; dim while paused or while the service is not running.
  implicitWidth: vertical ? barSize : Style.bar.iconSlot
  implicitHeight: vertical ? Style.bar.iconSlot : barSize

  Process {
    id: watcher
    running: true
    command: [root.cli, "watch"]
    stdout: SplitParser {
      onRead: line => {
        try { root.state = JSON.parse(line) } catch (e) {}
      }
    }
    onExited: restart.start()
  }

  Timer {
    id: restart
    interval: 3000
    onTriggered: watcher.running = true
  }

  Process { id: run }

  readonly property var screenOf: root.QsWindow.window ? root.QsWindow.window.screen : null
  readonly property var gaze: root.state.gaze || null

  PanelWindow {
    screen: root.screenOf
    visible: root.gaze !== null && root.screenOf !== null
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "hyprwink-gaze"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    Rectangle {
      readonly property bool here: root.gaze !== null && root.screenOf !== null
        && root.gaze[0] >= root.screenOf.x && root.gaze[0] < root.screenOf.x + root.screenOf.width
        && root.gaze[1] >= root.screenOf.y && root.gaze[1] < root.screenOf.y + root.screenOf.height
      visible: here
      width: 28; height: 28; radius: 14
      x: here ? root.gaze[0] - root.screenOf.x - width / 2 : 0
      y: here ? root.gaze[1] - root.screenOf.y - height / 2 : 0
      color: Qt.rgba(1, 0.2, 0.2, 0.35)
      border.color: "white"
      border.width: 2
      Behavior on x { NumberAnimation { duration: 60 } }
      Behavior on y { NumberAnimation { duration: 60 } }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Text {
        anchors.centerIn: parent
        text: ""
        textFormat: Text.PlainText
        font.family: root.bar ? root.bar.iconFontFamily : "JetBrainsMono Nerd Font Propo"
        font.pixelSize: Style.bar.iconFont
        opacity: root.state.paused || !root.online ? 0.45 : 1
        color: button.foreground
      }
    }
    onPressed: function(mouseButton) {
      run.command = mouseButton === Qt.RightButton ? [root.cli, "ui"] : [root.cli, "toggle"]
      run.running = true
    }
  }
}
