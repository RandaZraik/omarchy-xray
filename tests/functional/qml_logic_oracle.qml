import QtQuick
import "../../ui/DeviceSummary.js" as DeviceSummary
import "../../ui/TargetSearch.js" as TargetSearch
import "../../ui/DetailDomains.js" as DetailDomains
import "../../ui/Format.js" as Format
import "../../ui/ProcessEvidence.js" as ProcessEvidence

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
            "quickTargets": [{"label": "Microphone", "query": "microphone"}],
            "windows": [{"class": "Chromium", "title": "Docs", "pid": 10, "address": "0xa", "focused": true, "query": "window:0xa"}],
            "processes": [{"name": "chromium", "pid": 11, "query": "pid:11"}],
            "services": [{"id": "demo.service", "description": "Demo worker", "scope": "user", "query": "service:user:demo.service"}],
            "containers": [{"id": "abcdef", "name": "postgres", "image": "postgres:16", "runtime": "docker", "query": "container:docker:abcdef"}],
            "devices": [{"kind": "microphone", "application": "Recorder", "pid": 12, "query": "pid:12"}],
            "gpu": [{"application": "Game", "pid": 13, "device": "/dev/dri/renderD128", "query": "pid:13"}],
            "ports": [{"localPort": 5173, "protocol": "TCP4", "state": "Listen", "query": ":5173"}]
        }
        var catalogEntries = TargetSearch.entries(catalog)
        var partitionCount = TargetSearch.Filters.filter(function(filter) {
            return filter.id !== "all"
        })
            .reduce(function(total, filter) {
                return total + TargetSearch.browse(catalogEntries, filter.id).length
            }, 0)
        var manyProcesses = []
        for (var processIndex = 0; processIndex < 100; processIndex++) {
            var pid = 1000 + processIndex
            manyProcesses.push({"name": "worker", "pid": pid, "query": "pid:" + pid})
        }
        var largeCatalogEntries = TargetSearch.entries({"processes": manyProcesses})
        var snapshot = {
            "target": {
                "ownerPid": 10,
                "alternatives": [{"pid": 10, "label": "Owner"}, {"pid": 11, "label": "Worker"}]
            },
            "processes": [{"pid": 10, "name": "owner", "command": ["owner"], "cpuPercent": 2, "memoryBytes": 1024}],
            "connections": [{"protocol": "TCP4", "state": "Established", "localAddress": "127.0.0.1", "localPort": 5173, "remoteAddress": "10.0.0.2", "remotePort": 443, "pids": [10], "inode": 77, "networkNamespace": "net:[1]", "listening": false}],
            "files": [{"pid": 10, "fd": 4, "target": "/tmp/example", "kind": "file", "mode": "read/write", "position": 12, "flags": "0100002", "mountId": 29}],
            "locks": [{"id": "3", "pid": 10, "owner": "PID 10", "inode": "08:01:9", "type": "POSIX", "scope": "ADVISORY", "mode": "Write", "start": "0", "end": "EOF"}],
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
        var processEvidenceRows = [
            {"pid": 10, "name": "root", "user": "demo-user", "uid": 1000,
             "state": "S", "depth": 0, "threads": 3, "memoryBytes": 2048,
             "cpuPercent": 2, "readBytesPerSecond": 10,
             "writeBytesPerSecond": 20, "command": ["root", "--safe"]},
            {"pid": 11, "name": "worker", "user": "demo-user", "uid": 1000,
             "state": "R", "depth": 1, "threads": 5, "memoryBytes": 4096,
             "cpuPercent": 12, "readBytesPerSecond": 40,
             "writeBytesPerSecond": 80, "command": ["worker", "--serve"]},
            {"pid": 12, "name": "idle", "uid": 4242, "state": "I", "depth": 1,
             "threads": 1, "memoryBytes": 1024, "cpuPercent": null,
             "readBytesPerSecond": null, "writeBytesPerSecond": null,
             "command": []}
        ]
        var largeFileRows = []
        for (var fileIndex = 0; fileIndex < 2500; fileIndex++) {
            largeFileRows.push({
                "rowType": "file",
                "section": "files",
                "title": "/tmp/resource-" + (fileIndex % 1250),
                "target": "/tmp/resource-" + (fileIndex % 1250),
                "kind": "file",
                "mode": "read/write",
                "deleted": false,
                "pid": 100 + (fileIndex % 8),
                "fd": fileIndex,
                "position": fileIndex,
                "flags": "0100002",
                "mountId": 29,
                "searchText": "resource " + fileIndex
            })
        }
        var prepareStartedAt = Date.now()
        var preparedLargeFiles = DetailDomains.preparePresentation(
            DetailDomains.Files, largeFileRows
        )
        var prepareElapsedMs = Date.now() - prepareStartedAt
        var expandedLargeFiles = DetailDomains.presentationRowsFromPrepared(
            DetailDomains.Files, preparedLargeFiles, {}, false
        )
        var collapsedLargeFiles = DetailDomains.presentationRowsFromPrepared(
            DetailDomains.Files, preparedLargeFiles,
            {"files:files": true}, false
        )
        var toggleStartedAt = Date.now()
        for (var toggleIndex = 0; toggleIndex < 100; toggleIndex++) {
            DetailDomains.presentationRowsFromPrepared(
                DetailDomains.Files, preparedLargeFiles,
                toggleIndex % 2 ? {} : {"files:files": true}, false
            )
        }
        var toggleElapsedMs = Date.now() - toggleStartedAt
        console.log("XRAY_QML " + JSON.stringify({
            "empty": empty,
            "active": active,
            "mixed": mixed,
            "overflow": overflow,
            "limited": limited,
            "windowSearch": TargetSearch.matches("chro", catalogEntries, 7),
            "windowOnlySearch": TargetSearch.matches("chro", catalogEntries, 7, "apps"),
            "processOnlySearch": TargetSearch.matches("chro", catalogEntries, 7, "processes"),
            "serviceSearch": TargetSearch.matches("demo", catalogEntries, 7),
            "containerSearch": TargetSearch.matches("postgres", catalogEntries, 7),
            "deviceSearch": TargetSearch.matches("recorder", catalogEntries, 7),
            "gpuSearch": TargetSearch.matches("game", catalogEntries, 7),
            "gpuFallbackLabelSearch": TargetSearch.matches("GPU client",
                TargetSearch.entries({
                    "gpu": [{"pid": 14, "device": "/dev/dri/card1", "query": "pid:14"}]
                }), 7),
            "portSearch": TargetSearch.matches("5173", catalogEntries, 7),
            "exactPortSearch": TargetSearch.matches(":5173", catalogEntries, 7),
            "boundedSearch": TargetSearch.matches("", catalogEntries, 7),
            "browseKinds": TargetSearch.browse(catalogEntries, "all").map(function(entry) {
                return entry.kind
            }),
            "filters": TargetSearch.Filters,
            "targetCount": TargetSearch.targetCount(catalogEntries),
            "shortcutCount": TargetSearch.shortcutCount(catalogEntries),
            "partitionCount": partitionCount,
            "completeSearchCount": TargetSearch.matches(
                "worker", largeCatalogEntries,
                TargetSearch.targetCount(largeCatalogEntries), "all"
            ).length,
            "portBrowse": TargetSearch.browse(catalogEntries, "ports"),
            "ownerMatches": TargetSearch.ownerMatches(snapshot.target),
            "ipv4Endpoint": Format.addressPort("127.0.0.1", 443),
            "ipv6Endpoint": Format.addressPort("2001:db8::1", 443),
            "defaultMemory": Format.bytes(651788288),
            "deviceIcons": [
                Format.icon("audio"),
                Format.icon("gpu"),
                Format.icon("microphone"),
                Format.icon("camera")
            ],
            "detailCounts": detailCounts,
            "detailRowCounts": detailRowCounts,
            "connectionRows": DetailDomains.rows(DetailDomains.Connections, snapshot),
            "fileRows": DetailDomains.rows(DetailDomains.Files, snapshot),
            "deviceDetailRows": DetailDomains.rows(DetailDomains.Devices, snapshot),
            "runtimeRows": DetailDomains.rows(DetailDomains.Runtime, snapshot),
            "explanationRows": DetailDomains.rows(DetailDomains.Explanations, snapshot),
            "fileSummary": DetailDomains.summary(
                DetailDomains.Files, snapshot,
                DetailDomains.rows(DetailDomains.Files, snapshot)
            ),
            "connectionPresentation": DetailDomains.presentationRows(
                DetailDomains.Connections,
                DetailDomains.rows(DetailDomains.Connections, snapshot), {}, false
            ),
            "unknownSectionPresentation": DetailDomains.presentationRows(
                DetailDomains.Connections,
                [{"section": "future", "title": "Future evidence"}], {}, false
            ),
            "largeFilePresentation": {
                "sourceCount": largeFileRows.length,
                "resourceCount": preparedLargeFiles.rows.length,
                "flatCount": preparedLargeFiles.flatRows.length,
                "sectionCountLabel": preparedLargeFiles.sections[0].countLabel,
                "expandedCount": expandedLargeFiles.length,
                "collapsedCount": collapsedLargeFiles.length,
                "rowIdentityPreserved": expandedLargeFiles[1]
                    === preparedLargeFiles.sections[0].rows[0],
                "prepareElapsedMs": prepareElapsedMs,
                "toggleElapsedMs": toggleElapsedMs
            },
            "processUserFilter": ProcessEvidence.filter(
                processEvidenceRows, "demo-user"
            ).map(function(row) { return row.pid }),
            "processPidFilter": ProcessEvidence.filter(
                processEvidenceRows, "11"
            ).map(function(row) { return row.pid }),
            "processNameFilter": ProcessEvidence.filter(
                processEvidenceRows, "WORKER"
            ).map(function(row) { return row.pid }),
            "processCommandFilter": ProcessEvidence.filter(
                processEvidenceRows, "--serve"
            ).map(function(row) { return row.pid }),
            "processFallbackUidFilter": ProcessEvidence.filter(
                processEvidenceRows, "4242"
            ).map(function(row) { return row.pid }),
            "processNonBtopFieldFilter": ProcessEvidence.filter(
                processEvidenceRows, "running"
            ).map(function(row) { return row.pid }),
            "processCpuSort": ProcessEvidence.sort(
                processEvidenceRows, "cpu", true
            ).map(function(row) { return row.pid }),
            "processCommandSort": ProcessEvidence.sort(
                processEvidenceRows, "command", false
            ).map(function(row) { return row.pid }),
            "processTreeOrder": ProcessEvidence.sort(
                processEvidenceRows, "tree", false
            ).map(function(row) { return row.pid }),
            "processSummary": ProcessEvidence.summary(processEvidenceRows),
            "processFallbackUser": ProcessEvidence.user(processEvidenceRows[2]),
            "processState": ProcessEvidence.state(processEvidenceRows[1]),
            "processCommand": ProcessEvidence.command(processEvidenceRows[0]),
            "processConciseCommand": ProcessEvidence.conciseCommand({
                "command": [
                    "/workspace/.venv/bin/python3",
                    "/workspace/.venv/bin/adw",
                    "dashboard", "--port", "9000"
                ]
            }),
            "processCommandLauncher": ProcessEvidence.commandLauncher({
                "command": [
                    "/workspace/.venv/bin/python3",
                    "/workspace/.venv/bin/adw",
                    "dashboard", "--port", "9000"
                ]
            }),
            "embeddedArgvConciseCommand": ProcessEvidence.conciseCommand({
                "command": [
                    "/usr/lib/chromium/chromium --load-extension=/usr/share/omarchy/extensions/whatsapp-slim --oauth2-client-id=demo"
                ]
            }),
            "variantStyleProcessCommand": ProcessEvidence.command({
                "command": {
                    "0": "/workspace/.venv/bin/python3",
                    "1": "/workspace/.venv/bin/adw",
                    "2": "dashboard",
                    "3": "--port",
                    "4": "9000",
                    "length": 5
                }
            })
        }))
        Qt.quit()
    }
}
