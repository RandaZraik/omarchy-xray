import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC
import QtTest
import Quickshell
import Quickshell.Io
import XRayClipboardTest 1.0
import "ui" as XRay
import "ui/views" as Views
import "ui/drawers" as Drawers

ShellRoot {
    id: root
    property int stage: 0
    property int ticks: 0
    property int startedAt: 0
    property int unguardedReads: 0
    property int pasteStarts: 0
    property var fields: []
    property var field: null
    XRay.XRayTheme { id: theme }
    ClipboardProbe { id: clipboard }
    TestCase { id: driver; when: false }
    FileView { id: mode; path: Quickshell.env("XRAY_CLIPBOARD_MODE"); blockWrites: true }
    Connections {
        target: root.field
        function onPastePendingChanged() { if (root.field.pastePending) root.pasteStarts++ }
    }

    function require(value, message) {
        if (value) return
        poll.stop()
        console.log("XRAY_CLIPBOARD_ERROR " + message + " at stage " + stage)
        Qt.exit(1)
        throw new Error(message)
    }
    function descendants(item) {
        var result = [item]
        for (var child of item.children || []) result = result.concat(descendants(child))
        return result
    }
    function guardFields() {
        return descendants(window.contentItem).filter(function(item) { return item.pastePending !== undefined })
    }
    function focusField(index) {
        browser.visible = index === 0
        drawer.visible = index === 1 || index === 2
        capsule.visible = index === 3
        drawer.domain = index === 2 ? "connections" : "files"
        var visibleFields = guardFields().filter(function(item) { return item.visible })
        require(visibleFields.length === 1, "expected one visible input")
        field = visibleFields[0]
        field.forceActiveFocus()
        require(field.activeFocus, "input did not take focus")
    }
    function checkEditing(index) {
        focusField(index)
        clipboard.offer()
        require(clipboard.reads === 0 && field.readOnly && !field.canPaste, "focused native clipboard access")
        field.paste()
        require(clipboard.reads === 0 && field.text === "", "native paste was not inert")
        driver.keyClick(Qt.Key_A)
        driver.keyClick(Qt.Key_B)
        require(field.text === "ab", "typing failed")
        driver.keyClick(Qt.Key_A, Qt.ControlModifier)
        driver.keyClick(Qt.Key_X)
        require(field.text === "x", "selection replacement failed")
        driver.keyClick(Qt.Key_Z, Qt.ControlModifier)
        require(field.text === "ab", "undo failed")
        driver.keyClick(Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        require(field.text === "x", "redo failed")
        field.selectAll()
        field.replaceSelection("abc")
        driver.keyClick(Qt.Key_Backspace)
        driver.keyClick(Qt.Key_Z, Qt.ControlModifier)
        driver.keyClick(Qt.Key_X)
        require(field.text === "abcx", "undo restored a deletion selection instead of the caret")
        field.selectAll()
        field.replaceSelection("a🌍b")
        field.cursorPosition = 3
        driver.keyClick(Qt.Key_Backspace)
        require(field.text === "ab", "backspace split a surrogate pair")
        field.selectAll()
        field.replaceSelection("a🌍b")
        field.cursorPosition = 1
        driver.keyClick(Qt.Key_Delete)
        require(field.text === "ab", "delete split a surrogate pair")
        field.selectAll()
        field.replaceSelection("alpha beta")
        driver.keyClick(Qt.Key_Backspace, Qt.ControlModifier)
        require(field.text === "alpha ", "word deletion failed")
        driver.keyClick(Qt.Key_A, Qt.ControlModifier)
        driver.keyClick(Qt.Key_X, Qt.ControlModifier)
        require(field.text === "" && Quickshell.clipboardText === "alpha ", "cut failed")
        field.replaceSelection("/home/user/file")
        driver.keyClick(Qt.Key_Backspace, Qt.ControlModifier)
        require(field.text === "/home/user/", "word deletion removed the whole path")
        field.selectAll()
        field.replaceSelection("")
        var limit = field.maximumLength
        field.maximumLength = 2
        field.replaceSelection("a🌍")
        require(field.text === "a", "length limit split a surrogate pair")
        field.maximumLength = limit
        field.selectAll()
        field.replaceSelection("")
        clipboard.offer()
        require(clipboard.reads === 0, "editing weakened the native guard")
    }
    function beginPaste(kind, primary) {
        mode.setText(kind)
        var previous = pasteStarts
        startedAt = ticks
        if (primary) driver.mouseClick(field, field.width / 2, field.height / 2, Qt.MiddleButton)
        else driver.keyClick(Qt.Key_V, Qt.ControlModifier)
        // QtTest can process a quick helper's exit before the input call returns.
        require(pasteStarts === previous + 1, "explicit paste did not start")
    }

    Window {
        id: window
        width: 820
        height: 900
        visible: true
        Views.TargetBrowser { id: browser; anchors.fill: parent; visible: false; theme: theme }
        Drawers.DetailDrawer { id: drawer; anchors.fill: parent; visible: false; theme: theme; domain: "files" }
        Drawers.CapsuleDrawer { id: capsule; anchors.fill: parent; visible: false; theme: theme }
        Loader { id: unguarded; active: true; sourceComponent: QQC.TextField {} }
    }

    Timer {
        id: poll
        interval: 30
        running: true
        repeat: true
        property bool advancing: false
        onTriggered: {
            if (advancing) return
            advancing = true
            try { advance() } finally { advancing = false }
        }
        function advance() {
            root.ticks++
            root.require(ticks < 500, "oracle timed out")
            if (stage === 0) {
                clipboard.offer()
                root.unguardedReads = clipboard.reads
                root.require(unguardedReads > 0, "probe did not detect the vulnerable native control")
                unguarded.active = false
                stage++
            } else if (stage === 1) {
                root.fields = root.guardFields()
                root.require(fields.length === 4, "did not instantiate all four production inputs")
                clipboard.offer()
                root.require(clipboard.reads === 0, "hidden fields read the clipboard")
                stage++
            } else if (stage >= 2 && stage <= 5) {
                root.checkEditing(stage - 2)
                stage++
            } else if (stage === 6) {
                root.focusField(2)
                field.replaceSelection("tcp")
                var view = root.descendants(drawer).find(function(item) { return item.objectName === "xrayNetworkView" })
                root.require(view.search === "tcp", "network search did not receive typed text")
                view.search = "udp"
                root.require(field.text === "udp", "network model stopped updating after editing")
                drawer.visible = false
                root.require(field.text === "", "hidden search did not reset")
                drawer.visible = true
                field.forceActiveFocus()
                root.beginPaste("normal", false)
                stage++
            } else if (stage === 7 && !field.pastePending) {
                root.require(field.text === "مرحبا 🌍" && !field.pasteError, "bounded Unicode paste failed")
                field.selectAll()
                root.beginPaste("large", false)
                stage++
            } else if (stage === 8 && !field.pastePending) {
                root.require(field.text === "مرحبا 🌍" && field.pasteError.indexOf("too large") >= 0, "oversized paste was accepted")
                field.selectAll()
                field.replaceSelection("")
                stage = 80
            } else if (stage === 80) {
                // Let the error tooltip close before sending a mouse event.
                root.beginPaste("normal", true)
                stage = 9
            } else if (stage === 9 && !field.pastePending) {
                root.require(field.text === "مرحبا 🌍", "primary selection paste failed")
                field.selectAll()
                field.replaceSelection("before")
                root.beginPaste("slow", false)
                driver.keyClick(Qt.Key_X)
                stage++
            } else if (stage === 10 && !field.pastePending) {
                root.require(field.text === "beforex", "late paste overwrote typing")
                root.beginPaste("slow", false)
                browser.visible = true
                browser.focusSearch(false)
                field.forceActiveFocus()
                stage++
            } else if (stage === 11 && !field.pastePending) {
                root.require(field.text === "beforex", "late paste survived losing and regaining focus")
                browser.visible = false
                root.beginPaste("slow", false)
                field.cursorPosition = 0
                field.cursorPosition = field.text.length
                stage++
            } else if (stage === 12 && !field.pastePending) {
                root.require(field.text === "beforex", "late paste survived cursor movement")
                root.beginPaste("stall", false)
                stage++
            } else if (stage === 13 && !field.pastePending) {
                root.require(ticks - startedAt > 10, "event loop did not stay responsive while paste stalled")
                root.require(field.text === "beforex" && field.pasteError.indexOf("did not respond") >= 0, "trickling paste was accepted")
                field.enabled = false
                clipboard.offer()
                root.require(clipboard.reads === 0, "disabled input read the clipboard")
                poll.stop()
                console.log("XRAY_CLIPBOARD " + JSON.stringify({
                    unguardedReads: unguardedReads, guardedReads: clipboard.reads,
                    fields: fields.length, editing: true, undo: true, paste: true,
                    primary: true, oversized: true, deadline: true, stalePaste: true, modelSync: true
                }))
                Qt.quit()
            }
        }
    }
}
