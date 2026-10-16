import QtQuick
import QtQuick.Controls as Controls
import Quickshell.Io
import qs.Ui

TextField {
    id: root

    required property var theme
    property color accentColor: theme.accent
    property color idleSurface: theme.surfaceHigh
    property color focusSurface: theme.focusedSurface(accentColor)
    property color idleBorder: theme.cardBorder
    property color focusBorder: theme.focusedBorder(accentColor)
    // Keep model updates connected when local editing assigns native text.
    property string sourceText: ""
    onSourceTextChanged: if (text !== sourceText) text = sourceText

    // Qt's editable TextInput probes foreign clipboard data on dataChanged,
    // even when hidden. Keep this native guard permanent; key edits below
    // operate on local text and explicit pastes run in a bounded subprocess.
    readOnly: true
    cursorVisible: activeFocus
    maximumLength: 4096
    property string pasteError: ""
    readonly property bool pastePending: _pasteRequest !== null
    property var _undo: []
    property var _redo: []
    property bool _editing: false
    property int _revision: 0
    property var _pasteRequest: null
    property string _pasteReply: ""

    function editState() {
        return { text: text, cursor: cursorPosition, start: selectionStart, end: selectionEnd }
    }

    function applyEdit(value, cursor, start, end) {
        _editing = true
        text = value
        select(start, end)
        if (start === end) cursorPosition = cursor
        else if (cursor === start) select(end, start)
        _editing = false
        textEdited()
    }

    function replaceSelection(value, undoState) {
        var start = selectionStart, end = selectionEnd
        var room = Math.max(0, maximumLength - text.length + end - start)
        var inserted = String(value).replace(/[\r\n\t\u2028\u2029]/g, " ")
            .replace(/[\x00-\x1f\x7f]/g, "").slice(0, room)
        if (/[\uD800-\uDBFF]$/.test(inserted)) inserted = inserted.slice(0, -1)
        var next = text.slice(0, start) + inserted + text.slice(end)
        if (next === text) return
        _undo = _undo.concat([undoState || editState()]).slice(-32)
        _redo = []
        pasteError = ""
        var cursor = start + inserted.length
        applyEdit(next, cursor, cursor, cursor)
    }

    function restoreEdit(redo) {
        var history = redo ? _redo : _undo
        if (!history.length) return
        var previous = history[history.length - 1]
        if (redo) {
            _undo = _undo.concat([editState()]).slice(-32)
            _redo = history.slice(0, -1)
        } else {
            _redo = _redo.concat([editState()]).slice(-32)
            _undo = history.slice(0, -1)
        }
        applyEdit(previous.text, previous.cursor, previous.start, previous.end)
    }

    function deleteText(backwards, word) {
        var previous = editState()
        if (selectionStart === selectionEnd) {
            var start = cursorPosition, end = start
            if (backwards && start > 0) {
                if (word) {
                    cursorPosition = start - 1
                    selectWord()
                    start = selectionStart
                } else {
                    start--
                    if (start > 0 && /[\uDC00-\uDFFF]/.test(text.charAt(start))) start--
                }
            } else if (!backwards && end < text.length) {
                if (word) {
                    selectWord()
                    end = selectionEnd
                    // Qt consumes following spaces, including NEL but excluding BOM.
                    end += text.slice(end).match(/^(?:[^\S\uFEFF]|\u0085)*/)[0].length
                } else {
                    end++
                    if (end < text.length && /[\uD800-\uDBFF]/.test(text.charAt(end - 1))) end++
                }
            }
            select(start, end)
        }
        replaceSelection("", previous)
    }

    function requestPaste(primary) {
        if (!activeFocus || !visible || !enabled || pastePending) return
        pasteError = ""
        _pasteReply = ""
        _pasteRequest = { revision: _revision }
        var path = decodeURIComponent(Qt.resolvedUrl("../../backend/main.py").toString().replace(/^file:\/\//, ""))
        pasteProcess.command = ["python3", path, primary ? "--paste-primary" : "--paste-clipboard"]
        pasteProcess.running = true
    }

    // Do not apply an asynchronous paste after an edit, cursor move, hide,
    // disable, or focus change, even if the user returns to the same state.
    onTextChanged: {
        _revision++
        if (!_editing) { _undo = []; _redo = [] }
    }
    onCursorPositionChanged: _revision++
    onSelectionStartChanged: _revision++
    onSelectionEndChanged: _revision++
    onActiveFocusChanged: _revision++
    onVisibleChanged: _revision++
    onEnabledChanged: _revision++

    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
        if (event.matches(StandardKey.Paste)) requestPaste(false)
        else if (event.matches(StandardKey.Cut)) { copy(); replaceSelection("") }
        else if (event.matches(StandardKey.Undo)) restoreEdit(false)
        else if (event.matches(StandardKey.Redo)) restoreEdit(true)
        else if (event.key === Qt.Key_Backspace || event.key === Qt.Key_Delete)
            deleteText(event.key === Qt.Key_Backspace, !!(event.modifiers & Qt.ControlModifier))
        else if (!(event.modifiers & Qt.MetaModifier)
                 && (!(event.modifiers & Qt.ControlModifier) || (event.modifiers & Qt.AltModifier))
                 && event.text.length && !/[\x00-\x1f\x7f]/.test(event.text))
            replaceSelection(event.text)
        else {
            // Native navigation, selection, copy and Enter remain usable.
            // Native paste(), middle-click insertion and IME stay read-only.
            event.accepted = false
            return
        }
        event.accepted = true
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.MiddleButton
        cursorShape: Qt.IBeamCursor
        onClicked: function(mouse) {
            root.forceActiveFocus(Qt.MouseFocusReason)
            root.cursorPosition = root.positionAt(mouse.x, mouse.y)
            root.requestPaste(true)
        }
    }

    Process {
        id: pasteProcess
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root._pasteReply = text
        }
        // Failed starts emit runningChanged, but no exited signal.
        onRunningChanged: if (!running) Qt.callLater(function() {
            if (root.pastePending && !pasteProcess.running) pasteProcess.finishPaste(1)
        })
        onExited: function(code) { finishPaste(code) }
        function finishPaste(code) {
            var request = root._pasteRequest
            var reply = {}
            try { reply = JSON.parse(root._pasteReply) } catch (ignored) {}
            if (!reply || typeof reply !== "object" || Array.isArray(reply)) reply = {}
            root._pasteRequest = null
            root._pasteReply = ""
            if (!request || request.revision !== root._revision
                    || !root.activeFocus || !root.visible || !root.enabled) return
            if (code !== 0 || typeof reply.text !== "string") {
                root.pasteError = String(reply.error || "Paste failed. Try copying again.")
                return
            }
            root.replaceSelection(reply.text)
        }
    }

    Controls.ToolTip.visible: pasteError !== "" && activeFocus
    Controls.ToolTip.text: pasteError

    foreground: theme.text
    accent: accentColor
    selectionTint: theme.selected
    placeholderTextColor: theme.muted
    font.family: theme.dataFont
    background: Rectangle {
        radius: root.theme.controlRadius
        color: root.activeFocus ? root.focusSurface : root.idleSurface
        border.color: root.activeFocus ? root.focusBorder : root.idleBorder
        border.width: root.theme.borderWidth
    }
}
