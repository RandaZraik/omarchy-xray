from __future__ import annotations

from xray.evidence.findings import explanation


def _check(
    identifier: str,
    section: str,
    title: str,
    why: str,
    evidence: list[str],
    next_step: str,
    *,
    status: str,
    scope: str,
    measurements: dict[str, object],
) -> dict[str, object]:
    return {
        **explanation(
            identifier="performance-" + identifier,
            tone="attention" if status == "Observed" else "neutral",
            title=title,
            why=why,
            evidence=evidence,
            next_step=next_step,
            domain="performance",
            status=status,
        ),
        "section": section,
        "scope": scope,
        "measurements": measurements,
    }


def _status(sample: dict[str, object], observed: bool) -> str:
    if sample.get("status") == "unavailable":
        return "Unavailable"
    if sample.get("status") != "available":
        return "Baseline"
    return "Observed" if observed else "Quiet"


def _pressure_check(
    resource: str, sample: dict[str, object], scope: str
) -> dict[str, object]:
    ready = sample.get("status") == "available"
    seconds = float(sample.get("seconds", 0))
    some = (
        min(100.0, int(sample.get("some", 0)) / (seconds * 10_000))
        if ready and seconds > 0
        else None
    )
    full = (
        min(100.0, int(sample["full"]) / (seconds * 10_000))
        if ready and seconds > 0 and "full" in sample
        else None
    )
    # CPU full is undefined for the host and reports a compatibility zero.
    if scope == "Host" and resource == "cpu":
        full = None
    name = {"cpu": "CPU", "memory": "Memory", "io": "I/O"}[resource]
    status = _status(sample, some is not None and some >= 1.0)
    evidence = [str(sample["source"])]
    if some is not None:
        evidence.append(
            f"Some tasks stalled: estimated {some:.2f}% of {seconds:.2f}s; highlight threshold 1%"
        )
        if full is not None:
            evidence.append(
                f"All non-idle tasks stalled together: estimated {full:.2f}%"
            )
        evidence.append(
            "Interval estimates are capped at 100%; kernel updates and source reads are not simultaneous."
        )
    if "someAvg10" in sample:
        evidence.append(f"Kernel 10-second average: {sample['someAvg10']:.2f}%")
    if sample.get("reason"):
        evidence.append(str(sample["reason"]))
    return _check(
        f"pressure-{resource}-{scope}",
        resource,
        f"{name} pressure · {scope}",
        "Pressure measures time tasks stalled for this resource. "
        + (
            "Host activity may come from unrelated applications."
            if scope == "Host"
            else "This cgroup can include other processes; it does not identify which task stalled."
        ),
        evidence,
        {
            "cpu": "Compare thread CPU waits and cgroup throttling below.",
            "memory": "Compare memory-limit events and other workloads sharing this scope.",
            "io": "Compare blocked threads and file activity; pressure alone cannot identify a slow disk.",
        }[resource],
        status=status,
        scope=scope,
        measurements={
            "somePercent": some,
            "fullPercent": full,
            "seconds": seconds if ready else None,
            "someMicroseconds": sample.get("some") if ready else None,
            "fullMicroseconds": sample.get("full")
            if ready and not (scope == "Host" and resource == "cpu")
            else None,
            "someAvg10": sample.get("someAvg10"),
            "fullAvg10": sample.get("fullAvg10")
            if not (scope == "Host" and resource == "cpu")
            else None,
        },
    )


def diagnose(evidence: dict[str, object]) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    cpu = evidence["cpu"]
    ready_cpu = [row for row in cpu if row.get("status") == "available"]
    cores = sum(
        row["ticks"] / row["seconds"] / evidence["clockTicks"] for row in ready_cpu
    )
    cpu_status = (
        "Unavailable"
        if not cpu or any(row.get("status") == "unavailable" for row in cpu)
        else "Baseline"
        if len(ready_cpu) != len(cpu)
        else "Observed"
        if cores >= 0.8
        else "Quiet"
    )
    checks.append(
        _check(
            "cpu-work",
            "cpu",
            "CPU work in the selected process tree",
            "CPU time shows work being done, not proof that CPU is the bottleneck. One busy thread can use a full core while the dashboard's total-capacity CPU percentage stays low.",
            (
                [
                    f"{cores:.2f} CPU cores used across {len(ready_cpu)} sampled processes",
                    "Source: /proc/PID/stat CPU ticks; highlight threshold 0.8 cores",
                ]
                if ready_cpu
                else ["CPU counters could not be read for the selected processes"]
                if cpu_status == "Unavailable"
                else ["Collecting a second CPU sample"]
            )
            + [
                f"PID {row['pid']}: {row['reason']}" for row in cpu if row.get("reason")
            ][:4],
            "Compare CPU waits and throttling; sustained CPU work may need a code profiler to explain it.",
            status=cpu_status,
            scope="Selected tree",
            measurements={
                "cores": cores if ready_cpu else None,
                "sampledProcesses": len(ready_cpu),
                "processes": len(cpu),
                "secondsMin": min((row["seconds"] for row in ready_cpu), default=None),
                "secondsMax": max((row["seconds"] for row in ready_cpu), default=None),
            },
        )
    )
    # Active CPU is useful context, but should not be presented as an alert.
    checks[-1]["tone"] = "info" if cpu_status == "Observed" else "neutral"

    threads = evidence["threads"]
    ready_threads = [thread for thread in threads if thread["status"] == "available"]
    waiting = sorted(ready_threads, key=lambda thread: thread["waitNs"], reverse=True)
    delayed = [
        thread
        for thread in waiting
        if thread["waitNs"] >= 10_000_000
        and thread["waitNs"] >= (thread["runNs"] + thread["waitNs"]) * 0.1
    ]
    scheduler_status = (
        "Unavailable"
        if not evidence["schedulerEnabled"] or not threads
        else (
            "Observed"
            if delayed
            else "Baseline"
            if any(thread["status"] == "baseline" for thread in threads)
            else "Limited"
            if len(ready_threads) != len(threads) or evidence["threadCoverageLimited"]
            else "Quiet"
        )
    )
    checks.append(
        _check(
            "cpu-wait",
            "cpu",
            "Threads waiting for CPU",
            "Runnable threads waited on a CPU run queue. This excludes sleeping on locks, timers or I/O; totals add thread time and can exceed elapsed wall time.",
            [str(evidence["schedulerReason"])]
            if evidence["schedulerReason"]
            else [
                f"PID {thread['pid']} / TID {thread['tid']}: {thread['waitNs'] / 1e6:.2f} ms waiting, {thread['runNs'] / 1e6:.2f} ms running over {thread['seconds']:.2f}s"
                for thread in waiting[:4]
            ]
            + [
                f"/proc/PID/task/TID/schedstat · {len(ready_threads)}/{len(threads)} threads sampled; highlight ≥10 ms and ≥10% of runnable time"
            ],
            "Check CPU pressure and limits. Scheduler wait accounting must be enabled externally to measure this; X-Ray does not change it.",
            status=scheduler_status,
            scope="Selected threads",
            measurements={
                "waitMilliseconds": sum(thread["waitNs"] for thread in ready_threads)
                / 1e6
                if ready_threads
                else None,
                "sampledThreads": len(ready_threads),
                "threads": len(threads),
                "delayedThreads": len(delayed),
            },
        )
    )
    blocked = [thread for thread in threads if thread["state"] == "D"]
    checks.append(
        _check(
            "blocked",
            "io",
            "Threads in uninterruptible sleep",
            "A D-state thread is waiting in the kernel, often for I/O. A momentary wait is normal and does not prove a disk problem; wait-channel names are hints, not call stacks.",
            [
                f"PID {thread['pid']} / TID {thread['tid']}: D · {thread['waitChannel'] or 'wait channel unavailable'}"
                for thread in blocked[:4]
            ]
            + [f"/proc/PID/task/TID/stat and wchan · {len(threads)} inspected threads"],
            "Refresh to check whether the same thread stays blocked, then compare I/O pressure and open files.",
            status="Observed"
            if blocked
            else "Unavailable"
            if not threads
            else "Limited"
            if evidence["threadCoverageLimited"]
            else "Quiet",
            scope="Selected threads",
            measurements={"blockedThreads": len(blocked), "threads": len(threads)},
        )
    )
    for group in evidence["groups"]:
        scope = "Cgroup " + str(group["path"])
        if not group["ancestor"]:
            for resource, sample in group["pressure"].items():
                checks.append(_pressure_check(resource, sample, scope))
        sample = group["cpu.stat"]
        quota = group["cpuQuotaCores"]
        quota_text = (
            f"CPU limit: {quota:.2f} cores"
            if quota is not None
            else "CPU limit: unlimited at this level"
            if group["cpuQuotaKnown"]
            else "CPU limit: unavailable"
        )
        ready = sample.get("status") == "available"
        details = [str(group["source"]) + "/cpu.stat and cpu.max", quota_text]
        if ready:
            details.append(
                f"{sample['nr_throttled']} throttled periods / {sample['nr_periods']} elapsed periods over {sample['seconds']:.2f}s"
            )
            details.append(
                f"Accumulated run-queue throttle time: {sample['throttled_usec'] / 1000:.2f} ms (may exceed wall time)"
            )
        elif sample.get("reason"):
            details.append(str(sample["reason"]))
        checks.append(
            _check(
                "throttle-" + str(group["path"]),
                "cpu",
                "CPU-limit throttling · " + scope,
                "Increasing throttle counters show runnable work stopped by this group's fair-class CPU bandwidth limit. "
                + (
                    "It is an ancestor shared by the selected workload and possibly other apps."
                    if group["ancestor"]
                    else "These counters cover the cgroup, which may also contain other processes."
                )
                + " Configuring a limit alone is not evidence of throttling.",
                details,
                "Compare the group's CPU budget with competing workloads; inspect parent limits as well.",
                status=_status(
                    sample,
                    ready
                    and (sample["nr_throttled"] > 0 or sample["throttled_usec"] > 0),
                ),
                scope=scope,
                measurements={
                    "quotaCores": quota,
                    "quotaKnown": group["cpuQuotaKnown"],
                    **sample,
                },
            )
        )
        sample = group["memory.events"]
        ready = sample.get("status") == "available"
        details = [str(group["source"]) + "/memory.events (includes descendants)"]
        for filename in ("memory.current", "memory.high", "memory.max"):
            value = group[filename]
            rendered = (
                "unavailable"
                if not value["available"]
                else "unlimited"
                if value["bytes"] is None
                else f"{value['bytes'] / (1024 * 1024):.1f} MiB"
            )
            details.append(f"{filename}: {rendered}")
        if ready:
            details.append(
                f"Over {sample['seconds']:.2f}s: high {sample['high']}, max {sample['max']}, OOM {sample['oom']}, OOM kills {sample['oom_kill']}"
            )
        elif sample.get("reason"):
            details.append(str(sample["reason"]))
        checks.append(
            _check(
                "memory-events-" + str(group["path"]),
                "memory",
                "Memory-limit events · " + scope,
                "High events record reclaim throttling; max/OOM events record allocation pressure or kills. These are cgroup events, including descendants, and do not identify a particular affected process.",
                details,
                "Compare memory pressure with the group's limits and other processes sharing them; high RSS alone does not prove a leak.",
                status=_status(
                    sample,
                    ready
                    and any(
                        sample[name] > 0 for name in ("high", "max", "oom", "oom_kill")
                    ),
                ),
                scope=scope,
                measurements=dict(sample),
            )
        )
    for resource, sample in evidence["host"].items():
        checks.append(_pressure_check(resource, sample, "Host"))
    limited = list(evidence["limited"])
    if limited:
        checks.append(
            _check(
                "coverage",
                "coverage",
                "Some performance evidence is missing",
                "Collection is bounded and processes can change while being inspected. Quiet checks only describe the evidence that was readable.",
                limited[:8],
                "Refresh for another sample and inspect data availability; missing data is never treated as zero.",
                status="Limited",
                scope="Collection",
                measurements={"limitations": len(limited)},
            )
        )
        checks[-1]["evidenceCount"] = len(limited)
    checks.sort(
        key=lambda check: (check["status"] != "Observed", check["tone"] != "attention")
    )
    observed = sum(
        check["status"] == "Observed" and check["tone"] == "attention"
        for check in checks
    )
    unavailable = sum(check["status"] in {"Unavailable", "Limited"} for check in checks)
    baseline = any(check["status"] == "Baseline" for check in checks)
    return {
        "checks": checks,
        "observed": observed,
        "status": "limited" if unavailable else "baseline" if baseline else "available",
        "summary": f"{observed} performance signals observed"
        if observed
        else "Collecting a second sample"
        if baseline
        else "No cause identified in the available checks",
        "limited": limited,
    }
