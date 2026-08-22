import QtQuick
import "../../ui/DeviceSummary.js" as DeviceSummary
import "../../ui/TargetSearch.js" as TargetSearch
import "../../ui/DetailDomains.js" as DetailDomains
import "../../ui/Format.js" as Format

QtObject {
    Component.onCompleted: {
        var empty = DeviceSummary.summarize({"pipewire": [], "gpu": [], "inhibitors": []})
        var activeDevices = {
            "pipewire": [
                {"kind": "microphone", "active": true, "application": "Recorder"},
                {"kind": "audio-capture", "active": true, "application": "Recorder"},
                {"kind": "audio", "active": false, "application": "Paused player"}
            ],
            "gpu": [{"device": "/dev/dri/renderD128"}],
            "inhibitors": [{"who": "Video player"}]
        }
        var active = DeviceSummary.summarize(activeDevices)
        var mixed = DeviceSummary.summarize({
            "pipewire": [
                {"kind": "camera", "active": true, "application": "Meet"},
                {"kind": "camera", "active": true, "application": "Studio"},
                {"kind": "audio", "active": true, "application": "Player"}
            ],
            "gpu": [],
            "inhibitors": []
        })
        var overflow = DeviceSummary.summarize({
            "pipewire": [
                {"kind": "microphone", "active": true, "application": "One"},
                {"kind": "microphone", "active": true, "application": "Two"},
                {"kind": "microphone", "active": true, "application": "Three"},
                {"kind": "audio", "active": true, "application": "Four"}
            ],
            "gpu": [{"device": "/dev/dri/a"}, {"device": "/dev/dri/b"}],
            "inhibitors": [{"who": "Five"}, {"who": "Six"}]
        })
        var limited = DeviceSummary.summarize({
            "pipewire": [], "gpu": [], "inhibitors": [],
            "availability": {"pipewire": "unavailable", "gpu": "partial", "inhibitors": "unavailable"}
        })
        var catalog = {
            "windows": [{"class": "Chromium", "title": "Docs", "pid": 10, "address": "0xa", "focused": true}],
            "processes": [{"name": "chromium", "pid": 11}],
            "services": [{"id": "demo.service", "description": "Demo worker", "scope": "user"}],
            "containers": [{"id": "abcdef", "name": "postgres", "image": "postgres:16", "runtime": "docker"}],
            "devices": [{"kind": "microphone", "application": "Recorder", "pid": 12}],
            "gpu": [{"application": "Game", "pid": 13, "device": "/dev/dri/renderD128"}],
            "ports": [{"localPort": 5173, "protocol": "TCP4", "state": "Listen"}]
        }
        var snapshot = {
            "target": {
                "ownerPid": 10,
                "alternatives": [{"pid": 10, "label": "Owner"}, {"pid": 11, "label": "Worker"}]
            },
            "processes": [{"pid": 10, "name": "owner", "command": ["owner"], "cpuPercent": 2, "memoryBytes": 1024}],
            "connections": [{"protocol": "TCP4", "state": "Established", "localAddress": "127.0.0.1", "localPort": 5173}],
            "files": [{"pid": 10, "fd": 4, "target": "/tmp/example", "kind": "file", "mode": "rw"}],
            "locks": [{"pid": 10, "inode": 9, "type": "POSIX", "mode": "WRITE"}],
            "devices": activeDevices,
            "context": {
                "executable": "/usr/bin/owner",
                "workingDirectory": "/tmp",
                "package": {"name": "demo", "version": "1.2.3"},
                "git": {"root": "/tmp/demo", "branch": "master"},
                "service": {"id": "demo.service", "description": "Demo", "scope": "user", "activeState": "active", "subState": "running", "unitFileState": "enabled", "triggeredBy": ["demo.socket"]},
                "container": {"id": "abcdef", "name": "demo", "runtime": "podman", "ports": [{"hostPort": 8080, "containerPort": 80, "protocol": "tcp"}]},
                "cause": {"nodes": [{"title": "user session", "kind": "session", "proof": "login session"}]}
            },
            "security": {"uid": 1000, "gid": 1000, "groups": [1000, 10], "seccomp": "filter", "noNewPrivileges": true, "apparmor": "unconfined", "oomScore": 12, "oomAdjustment": 0, "namespaces": {"mnt": "mnt:[1]"}, "capabilities": ["CAP_NET_BIND_SERVICE"], "limits": [{"name": "open files", "soft": "1024", "hard": "4096"}], "libraries": ["/usr/lib/libc.so"]},
            "logs": [{"message": "ready", "unit": "demo.service", "priority": "6"}],
            "explanations": [{"title": "Listener", "why": "Port is open", "status": "observed", "evidence": ["socket inode 7"], "nextStep": "Inspect owner"}],
            "timeline": [{"label": "Socket opened", "timestamp": "now", "domain": "connections"}],
            "coverage": {"available": ["processes"], "limited": ["camera"]}
        }
        var detailCounts = {}
        var detailRowCounts = {}
        ;[DetailDomains.Processes, DetailDomains.Connections, DetailDomains.Files,
          DetailDomains.Devices, DetailDomains.Runtime, DetailDomains.Cause,
          DetailDomains.Explanations,
          DetailDomains.Coverage, DetailDomains.Alternatives].forEach(function(domain) {
            detailCounts[domain] = DetailDomains.count(domain, snapshot)
            detailRowCounts[domain] = DetailDomains.rows(domain, snapshot).length
        })
        console.log("XRAY_QML " + JSON.stringify({
            "empty": empty,
            "active": active,
            "mixed": mixed,
            "overflow": overflow,
            "limited": limited,
            "windowSearch": TargetSearch.matches("chro", catalog, 7),
            "serviceSearch": TargetSearch.matches("demo", catalog, 7),
            "containerSearch": TargetSearch.matches("postgres", catalog, 7),
            "deviceSearch": TargetSearch.matches("recorder", catalog, 7),
            "gpuSearch": TargetSearch.matches("game", catalog, 7),
            "portSearch": TargetSearch.matches("5173", catalog, 7),
            "boundedSearch": TargetSearch.matches("", catalog, 7),
            "ipv4Endpoint": Format.addressPort("127.0.0.1", 443),
            "ipv6Endpoint": Format.addressPort("2001:db8::1", 443),
            "detailCounts": detailCounts,
            "detailRowCounts": detailRowCounts,
            "runtimeRows": DetailDomains.rows(DetailDomains.Runtime, snapshot),
            "explanationRows": DetailDomains.rows(DetailDomains.Explanations, snapshot)
        }))
        Qt.quit()
    }
}
