from dataclasses import replace
import math
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from support.slowdown import SlowdownFixture
from xray.config import LIMITS
from xray.evidence.slowdown import diagnose
from xray.processes.slowdown import SlowdownSampler, counters, pressure
from xray.system.cgroupfs import cgroup_mounts, collect_scopes, unified_path
from xray.system.procfs import ReadResult


class SlowdownTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = SlowdownFixture(Path(temporary.name))
        self.sampler = SlowdownSampler()

    def sample(self, now: float = 1, *pids: int) -> dict[str, object]:
        return self.sampler.sample(self.fixture.proc, self.fixture.rows(*pids), now=now)

    def check(self, data: dict[str, object], identifier: str) -> dict[str, object]:
        return next(
            check
            for check in diagnose(data)["checks"]
            if check["id"] == "performance-" + identifier
        )


class SlowdownTests(SlowdownTestCase):
    def test_pressure_parser_accepts_cpu_without_full_and_extra_fields(self) -> None:
        self.assertEqual(
            pressure("some avg10=1.25 avg60=0 avg300=0 total=123 extra=4\n"),
            {"someAvg10": 1.25, "some": 123},
        )

    def test_invalid_pressure_never_becomes_zero(self) -> None:
        for value in (
            "",
            "full avg10=0 total=0",
            "some avg10=nan total=0",
            "some avg10=inf total=0",
            "some avg10=-1 total=0",
            "some avg10=101 total=0",
            "some avg10=0 total=-1",
            "some avg10=0",
            "some total=0",
            "some avg10=no total=0",
            "some avg10=0 total=x",
        ):
            with self.subTest(value=value):
                self.fixture.write_proc("pressure/io", value)
                data = self.sample()
                self.assertEqual(data["host"]["io"]["status"], "unavailable")
                self.assertIsNone(
                    self.check(data, "pressure-io-Host")["measurements"]["somePercent"]
                )

    def test_first_sample_does_not_alert_on_lifetime_counters(self) -> None:
        data = self.sample()
        self.assertEqual(diagnose(data)["observed"], 0)
        self.assertEqual(self.check(data, "throttle-/apps/demo")["status"], "Baseline")
        self.assertEqual(
            self.check(data, "memory-events-/apps/demo")["status"], "Baseline"
        )
        self.assertEqual(self.check(data, "cpu-wait")["status"], "Baseline")

    def test_second_unchanged_sample_is_quiet(self) -> None:
        self.sample()
        result = diagnose(self.sample(3))
        self.assertEqual(result["observed"], 0)
        self.assertEqual(result["status"], "available")
        self.assertTrue(all(check["status"] == "Quiet" for check in result["checks"]))

    def test_pressure_uses_interval_delta_and_labels_scope(self) -> None:
        self.sample()
        self.fixture.write_group(
            "/apps/demo", "memory.pressure", self.fixture.psi(1_300_000, 600_000, 75)
        )
        data = self.sample(3)
        check = self.check(data, "pressure-memory-Cgroup /apps/demo")
        self.assertEqual(check["status"], "Observed")
        self.assertEqual(
            check["measurements"],
            {
                "somePercent": 15,
                "fullPercent": 5,
                "seconds": 2,
                "someMicroseconds": 300_000,
                "fullMicroseconds": 100_000,
                "someAvg10": 75,
                "fullAvg10": 0,
            },
        )
        self.assertIn("other processes", check["why"])
        self.assertIn("75.00%", " ".join(check["evidence"]))

    def test_cpu_measurement_reads_fresh_counters_instead_of_stale_tree_rows(
        self,
    ) -> None:
        self.sample()
        stale_rows = self.fixture.rows()
        self.fixture.process(ticks=110)
        result = self.sampler.sample(self.fixture.proc, stale_rows, now=3)
        check = self.check(result, "cpu-work")
        self.assertAlmostEqual(
            check["measurements"]["cores"], 50 / os.sysconf("SC_CLK_TCK")
        )
        self.assertEqual(check["measurements"]["secondsMin"], 2)

    def test_each_counter_is_timed_at_its_read(self) -> None:
        with patch(
            "xray.processes.slowdown.time.monotonic", side_effect=range(1, 1000)
        ):
            self.sampler.sample(self.fixture.proc, self.fixture.rows())
        times = [value[0] for value in self.sampler.previous.values()]
        self.assertEqual(len(times), len(set(times)))

    def test_unreadable_cpu_is_unavailable_with_a_source_reason(self) -> None:
        rows = self.fixture.rows()
        original = self.fixture.proc.read
        reads = 0

        def denied_once(*parts, **kwargs):
            nonlocal reads
            if parts == (7, "stat"):
                reads += 1
                if reads == 1:
                    return ReadResult("", "permission denied")
            return original(*parts, **kwargs)

        with patch.object(self.fixture.proc, "read", side_effect=denied_once):
            raw = self.sampler.sample(self.fixture.proc, rows, now=1)
        work = self.check(raw, "cpu-work")
        self.assertEqual(work["status"], "Unavailable")
        self.assertIn("permission denied", " ".join(work["evidence"]))
        self.assertNotIn("second", " ".join(work["evidence"]))

    def test_host_activity_is_not_attributed_to_selected_process(self) -> None:
        self.sample()
        self.fixture.write_proc("pressure/io", self.fixture.psi(400_000, 200_000))
        data = self.sample(3)
        host = self.check(data, "pressure-io-Host")
        self.assertEqual(host["status"], "Observed")
        self.assertIn("unrelated applications", host["why"])
        self.assertEqual(
            self.check(data, "pressure-io-Cgroup /apps/demo")["status"], "Quiet"
        )

    def test_host_cpu_full_is_not_a_supported_measurement(self) -> None:
        self.sample()
        self.fixture.write_proc("pressure/cpu", self.fixture.psi(300_000, 200_000))
        check = self.check(self.sample(3), "pressure-cpu-Host")
        self.assertIsNone(check["measurements"]["fullPercent"])

    def test_pressure_threshold_and_rounding_do_not_change_classification(self) -> None:
        for delta, status in ((19_999, "Quiet"), (20_000, "Observed")):
            with self.subTest(delta=delta):
                self.sampler = SlowdownSampler()
                self.fixture.write_proc("pressure/io", self.fixture.psi())
                self.sample()
                self.fixture.write_proc("pressure/io", self.fixture.psi(delta))
                self.assertEqual(
                    self.check(self.sample(3), "pressure-io-Host")["status"], status
                )

    def test_configured_quota_without_throttling_is_not_a_slowdown(self) -> None:
        self.fixture.write_group("/apps/demo", "cpu.max", "50000 100000")
        self.sample()
        check = self.check(self.sample(3), "throttle-/apps/demo")
        self.assertEqual(check["status"], "Quiet")
        self.assertEqual(check["measurements"]["quotaCores"], 0.5)

    def test_parent_throttling_is_visible_even_with_unlimited_leaf(self) -> None:
        self.fixture.write_group("/apps", "cpu.max", "100000 100000")
        self.sample()
        self.fixture.write_group(
            "/apps",
            "cpu.stat",
            "nr_periods 120\nnr_throttled 100\nthrottled_usec 9000000\n",
        )
        data = self.sample(3)
        check = self.check(data, "throttle-/apps")
        self.assertEqual(check["status"], "Observed")
        self.assertEqual(check["measurements"]["nr_throttled"], 10)
        self.assertEqual(check["measurements"]["throttled_usec"], 4_000_000)
        self.assertIn("ancestor", check["why"])
        self.assertIn("may exceed wall time", " ".join(check["evidence"]))
        self.assertEqual(self.check(data, "throttle-/apps/demo")["status"], "Quiet")

    def test_memory_events_report_new_events_not_high_rss(self) -> None:
        self.sample()
        self.fixture.write_group(
            "/apps/demo", "memory.events", "high 103\nmax 102\noom 11\noom_kill 11\n"
        )
        check = self.check(self.sample(3), "memory-events-/apps/demo")
        self.assertEqual(check["status"], "Observed")
        self.assertEqual(
            [check["measurements"][key] for key in ("high", "max", "oom", "oom_kill")],
            [3, 2, 1, 1],
        )
        self.assertIn("do not identify", check["why"])

    def test_memory_limits_display_bytes_unlimited_and_missing(self) -> None:
        self.fixture.write_group("/apps/demo", "memory.high", "2097152")
        self.fixture.write_group("/apps/demo", "memory.max", "max")
        self.fixture.write_group("/apps/demo", "memory.current", "invalid")
        check = self.check(self.sample(), "memory-events-/apps/demo")
        self.assertIn("memory.high: 2.0 MiB", check["evidence"])
        self.assertIn("memory.max: unlimited", check["evidence"])
        self.assertIn("memory.current: unavailable", check["evidence"])

    def test_invalid_memory_usage_never_becomes_unlimited(self) -> None:
        for value in ("max", "-1", str(2**64), ""):
            with self.subTest(value=value):
                self.fixture.write_group("/apps/demo", "memory.current", value)
                check = self.check(self.sample(), "memory-events-/apps/demo")
                self.assertIn("memory.current: unavailable", check["evidence"])

    def test_cpu_work_uses_core_capacity_and_is_not_an_alert(self) -> None:
        self.sample()
        self.fixture.process(ticks=10 + 2 * os.sysconf("SC_CLK_TCK"))
        check = self.check(self.sample(3), "cpu-work")
        self.assertEqual(check["measurements"]["cores"], 1)
        self.assertEqual(check["status"], "Observed")
        self.assertEqual(check["tone"], "info")

    def test_cpu_wait_uses_runnable_thread_time_and_surfaces_hot_thread(self) -> None:
        self.fixture.thread(tid=8, start=11)
        self.sample()
        self.fixture.thread(run=1_300_000_000, wait=700_000_000)
        self.fixture.thread(tid=8, start=11, run=3_000_000_000)
        check = self.check(self.sample(3), "cpu-wait")
        self.assertEqual(check["status"], "Observed")
        self.assertEqual(check["measurements"]["waitMilliseconds"], 200)
        self.assertEqual(check["measurements"]["sampledThreads"], 2)
        self.assertEqual(check["measurements"]["delayedThreads"], 1)
        self.assertIn("PID 7 / TID 7", check["evidence"][0])

    def test_small_scheduler_wait_is_quiet_but_preserves_measurement(self) -> None:
        self.sample()
        self.fixture.thread(run=1_100_000_000, wait=500_001_000)
        check = self.check(self.sample(3), "cpu-wait")
        self.assertEqual(check["status"], "Quiet")
        self.assertEqual(check["measurements"]["waitMilliseconds"], 0.001)

    def test_disabled_or_missing_schedstats_never_reports_zero_wait(self) -> None:
        for value in ("0", "invalid", ""):
            with self.subTest(value=value):
                self.fixture.write_proc("sys/kernel/sched_schedstats", value)
                self.sample()
                check = self.check(self.sample(3), "cpu-wait")
                self.assertEqual(check["status"], "Unavailable")
                self.assertIsNone(check["measurements"]["waitMilliseconds"])
        (self.fixture.proc_root / "sys/kernel/sched_schedstats").unlink()
        self.assertEqual(
            self.check(self.sample(4), "cpu-wait")["status"], "Unavailable"
        )

    def test_reenabling_schedstats_collects_a_fresh_baseline(self) -> None:
        self.sample()
        self.fixture.write_proc("sys/kernel/sched_schedstats", "0")
        self.sample(2)
        self.fixture.write_proc("sys/kernel/sched_schedstats", "1")
        self.assertEqual(self.check(self.sample(3), "cpu-wait")["status"], "Baseline")

    def test_uninterruptible_sleep_is_an_observation_not_a_disk_diagnosis(self) -> None:
        self.fixture.thread(state="D")
        check = self.check(self.sample(), "blocked")
        self.assertEqual(check["status"], "Observed")
        self.assertIn("io_schedule", check["evidence"][0])
        self.assertIn("does not prove", check["why"])
        self.fixture.write_proc("7/task/7/wchan", "0")
        self.assertIn(
            "wait channel unavailable",
            self.check(self.sample(2), "blocked")["evidence"][0],
        )

    def test_sleeping_on_timer_does_not_create_blocked_finding(self) -> None:
        self.fixture.thread(state="S")
        self.assertEqual(self.check(self.sample(), "blocked")["status"], "Quiet")

    def test_counter_reset_and_nonincreasing_time_restart_baseline(self) -> None:
        self.sample(5)
        for now in (5, 4):
            with self.subTest(now=now):
                self.assertEqual(
                    self.check(self.sample(now), "cpu-wait")["status"], "Baseline"
                )
        self.fixture.thread(run=1, wait=1)
        self.fixture.write_group(
            "/apps/demo", "cpu.stat", "nr_periods 1\nnr_throttled 0\nthrottled_usec 0\n"
        )
        data = self.sample(6)
        self.assertEqual(self.check(data, "cpu-wait")["status"], "Baseline")
        self.assertEqual(self.check(data, "throttle-/apps/demo")["status"], "Baseline")

    def test_unavailable_counter_does_not_bridge_a_gap(self) -> None:
        self.sample()
        path = self.fixture.cgroup_root / "apps/demo/cpu.pressure"
        path.unlink()
        self.assertEqual(
            self.check(self.sample(2), "pressure-cpu-Cgroup /apps/demo")["status"],
            "Unavailable",
        )
        self.fixture.write_group(
            "/apps/demo", "cpu.pressure", self.fixture.psi(99_000_000)
        )
        self.assertEqual(
            self.check(self.sample(3), "pressure-cpu-Cgroup /apps/demo")["status"],
            "Baseline",
        )

    def test_pid_and_tid_reuse_do_not_reuse_sampling_baselines(self) -> None:
        self.sample()
        self.fixture.thread(start=20, run=8_000_000_000, wait=9_000_000_000)
        self.assertEqual(self.check(self.sample(2), "cpu-wait")["status"], "Baseline")
        self.fixture.process(start=30, ticks=999)
        data = self.sample(3)
        self.assertEqual(self.check(data, "cpu-work")["status"], "Baseline")
        self.assertEqual(self.check(data, "throttle-/apps/demo")["status"], "Baseline")

    def test_worker_churn_preserves_shared_group_and_ancestor_intervals(self) -> None:
        self.sample()
        self.fixture.process(8)
        for now, pids, throttled in ((2, (7, 8), 100), (3, (7,), 110)):
            for group in ("/apps/demo", "/apps"):
                self.fixture.write_group(
                    group,
                    "cpu.stat",
                    f"nr_periods 200\nnr_throttled {throttled}\nthrottled_usec 6000000\n",
                )
            data = self.sample(now, *pids)
            for group in ("/apps/demo", "/apps"):
                check = self.check(data, "throttle-" + group)
                self.assertEqual(check["status"], "Observed")
                self.assertEqual(check["measurements"]["nr_throttled"], 10)

    def test_fully_replaced_cgroup_members_need_a_new_baseline(self) -> None:
        self.sample()
        self.fixture.process(8)
        self.assertEqual(
            self.check(self.sample(2, 8), "throttle-/apps/demo")["status"], "Baseline"
        )

    def test_membership_migration_resets_shared_ancestor_baseline(self) -> None:
        self.fixture.group("/apps/other")
        self.sample()
        self.fixture.write_proc("7/cgroup", "0::/apps/other\n")
        data = self.sample(3)
        self.assertEqual(self.check(data, "throttle-/apps")["status"], "Baseline")
        self.assertNotIn("/apps/demo", [group["path"] for group in data["groups"]])

    def test_recreated_cgroup_does_not_reuse_counters(self) -> None:
        self.sample()
        path = self.fixture.cgroup_root / "apps/demo"
        path.rename(path.with_name("previous"))
        self.fixture.group("/apps/demo")
        self.assertEqual(
            self.check(self.sample(3), "throttle-/apps/demo")["status"], "Baseline"
        )

    def test_mid_sample_process_change_discards_attributed_evidence(self) -> None:
        rows = self.fixture.rows()
        self.fixture.process(start=20)
        data = self.sampler.sample(self.fixture.proc, rows, now=1)
        self.assertEqual(data["threads"], [])
        self.assertEqual(data["groups"], [])
        self.assertEqual(data["cpu"], [])
        self.assertTrue(data["limited"])
        self.assertTrue(all(key[0] == "host" for key in self.sampler.previous))

    def test_unverified_thread_does_not_seed_a_later_interval(self) -> None:
        original = self.fixture.proc.read
        reads = 0

        def disappearing(*parts, **kwargs):
            nonlocal reads
            if parts == (7, "task", 7, "stat"):
                reads += 1
                if reads == 2:
                    return ReadResult("", "not found")
            return original(*parts, **kwargs)

        with patch.object(self.fixture.proc, "read", side_effect=disappearing):
            self.assertEqual(self.sample()["threads"], [])
        self.assertFalse(any(key[0] == "thread" for key in self.sampler.previous))
        self.assertEqual(self.check(self.sample(2), "cpu-wait")["status"], "Baseline")

    def test_missing_and_invalid_scheduler_fields_are_unavailable(self) -> None:
        for value in ("", "1 2", "1 2 3 4", "1 x 3", "-1 2 3"):
            with self.subTest(value=value):
                self.fixture.write_proc("7/task/7/schedstat", value)
                data = self.sample()
                self.assertTrue(data["limited"])
                self.assertEqual(data["threads"][0]["status"], "unavailable")

    def test_denied_sources_are_explicit_and_preserve_other_evidence(self) -> None:
        original = self.fixture.proc.read

        def denied(*parts, **kwargs):
            return (
                ReadResult("", "permission denied")
                if parts == ("pressure", "memory")
                else original(*parts, **kwargs)
            )

        with patch.object(self.fixture.proc, "read", side_effect=denied):
            data = self.sample()
        self.assertEqual(data["host"]["memory"]["reason"], "permission denied")
        self.assertTrue(data["threads"])
        self.assertTrue(data["groups"])

    def test_thread_budget_marks_partial_coverage(self) -> None:
        self.fixture.thread(tid=8, start=11)
        with patch(
            "xray.processes.slowdown.LIMITS", replace(LIMITS, slowdown_threads=1)
        ):
            data = self.sample()
        self.assertEqual(len(data["threads"]), 1)
        self.assertTrue(any("limited to 1" in reason for reason in data["limited"]))
        self.assertEqual(diagnose(data)["status"], "limited")

    def test_history_is_bounded_to_current_sources(self) -> None:
        self.fixture.thread(tid=8, start=11)
        self.sample()
        shutil.rmtree(self.fixture.proc_root / "7/task/8")
        self.sample(3)
        self.assertFalse(
            any(key[0] == "thread" and key[2] == 8 for key in self.sampler.previous)
        )

    def test_quota_parser_distinguishes_unknown_unlimited_and_finite(self) -> None:
        for text, known, quota in (
            ("max 100000", True, None),
            ("25000 100000", True, 0.25),
            ("max 0", False, None),
            ("-1 100000", False, None),
            ("0 100000", False, None),
            ("bad", False, None),
            (f"{2**64} 100000", False, None),
        ):
            with self.subTest(text=text):
                self.fixture.write_group("/apps/demo", "cpu.max", text)
                group = self.sample()["groups"][0]
                self.assertEqual(
                    (group["cpuQuotaKnown"], group["cpuQuotaCores"]), (known, quota)
                )

    def test_nonfinite_values_never_escape_as_measurements(self) -> None:
        self.sample()
        data = diagnose(self.sample(3))
        for check in data["checks"]:
            for value in check["measurements"].values():
                if isinstance(value, float):
                    self.assertTrue(math.isfinite(value))

    def test_flat_counters_reject_invalid_values(self) -> None:
        for value in ("", "high nope", "high -1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                counters(value)


class CgroupScopeTests(SlowdownTestCase):
    def test_unified_membership_rejects_unsafe_paths_and_v1(self) -> None:
        for text in (
            "",
            "3:cpu:/demo",
            "0::relative",
            "0::/a/../b",
            "0::/a/./b",
            "0::/a\0b",
        ):
            with self.subTest(text=text):
                self.assertIsNone(unified_path(text))
        self.assertEqual(unified_path("3:cpu:/old\n0::/apps/demo\n"), "/apps/demo")

    def test_shared_groups_and_ancestors_are_collected_once(self) -> None:
        self.fixture.process(8)
        scopes, limited, _ = collect_scopes(self.fixture.proc, self.fixture.rows(7, 8))
        self.assertFalse(limited)
        self.assertEqual([scope.path for scope in scopes], ["/apps/demo", "/apps", "/"])
        self.assertTrue(all(scope.pids == (7, 8) for scope in scopes))

    def test_mount_subtree_maps_membership_and_marks_hidden_ancestors(self) -> None:
        self.fixture.write_proc(
            "self/mountinfo",
            f"36 27 0:34 /apps {self.fixture.cgroup_root / 'apps'} rw - cgroup2 cgroup2 rw\n",
        )
        scopes, limited, _ = collect_scopes(self.fixture.proc, self.fixture.rows())
        self.assertEqual([scope.path for scope in scopes], ["/apps/demo", "/apps"])
        self.assertTrue(any("not visible" in reason for reason in limited))

    def test_subtree_mount_does_not_hide_ancestors_visible_in_another_mount(
        self,
    ) -> None:
        root = self.fixture.cgroup_root
        self.fixture.write_proc(
            "self/mountinfo",
            f"36 27 0:34 /apps/demo {root / 'apps/demo'} rw - cgroup2 cgroup2 rw\n"
            f"37 27 0:34 / {root} rw - cgroup2 cgroup2 rw\n",
        )
        scopes, limited, _ = collect_scopes(self.fixture.proc, self.fixture.rows())
        self.assertEqual([scope.path for scope in scopes], ["/apps/demo", "/apps", "/"])
        self.assertFalse(limited)
        self.sample()
        self.fixture.write_group(
            "/apps",
            "cpu.stat",
            "nr_periods 120\nnr_throttled 100\nthrottled_usec 6000000\n",
        )
        self.assertEqual(
            self.check(self.sample(3), "throttle-/apps")["status"], "Observed"
        )

    def test_escaped_mountpoint_and_nonmatching_mount_are_handled(self) -> None:
        root = self.fixture.cgroup_root
        spaced = root.with_name("cgroup space")
        root.rename(spaced)
        escaped = str(spaced).replace(" ", "\\040")
        self.fixture.write_proc(
            "self/mountinfo", f"36 27 0:34 / {escaped} rw - cgroup2 cgroup2 rw\n"
        )
        mounts, error = cgroup_mounts(self.fixture.proc)
        self.assertFalse(error)
        self.assertEqual(mounts[0].mountpoint, spaced)
        self.fixture.write_proc(
            "self/mountinfo",
            f"36 27 0:34 /unrelated {spaced} rw - cgroup2 cgroup2 rw\n",
        )
        scopes, limited, _ = collect_scopes(self.fixture.proc, self.fixture.rows())
        self.assertEqual(scopes, [])
        self.assertTrue(limited)

    def test_no_cgroup_v2_keeps_host_and_thread_checks(self) -> None:
        self.fixture.write_proc(
            "self/mountinfo", "36 27 0:34 / /sys/fs/cgroup rw - cgroup cgroup rw\n"
        )
        data = self.sample()
        self.assertEqual(data["groups"], [])
        self.assertTrue(data["limited"])
        self.assertTrue(data["threads"])
        self.assertEqual(set(data["host"]), {"cpu", "memory", "io"})

    def test_symlink_cgroup_is_not_followed(self) -> None:
        path = self.fixture.cgroup_root / "apps/demo"
        moved = path.with_name("moved")
        path.rename(moved)
        path.symlink_to(moved)
        scopes, limited, _ = collect_scopes(self.fixture.proc, self.fixture.rows())
        self.assertEqual(scopes, [])
        self.assertTrue(limited)

    def test_cgroup_and_depth_budgets_are_explicit(self) -> None:
        for limits in (
            replace(LIMITS, slowdown_cgroups=1),
            replace(LIMITS, slowdown_cgroup_depth=1),
        ):
            with (
                self.subTest(limits=limits),
                patch("xray.system.cgroupfs.LIMITS", limits),
            ):
                scopes, limited, _ = collect_scopes(
                    self.fixture.proc, self.fixture.rows()
                )
                self.assertEqual(len(scopes), 1)
                self.assertTrue(limited)
