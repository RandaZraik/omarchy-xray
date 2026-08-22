from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from live_backend import LiveBackend

from xray.devices.gpu import collect_gpu_clients
from xray.system.procfs import ProcFs


class GpuTruthTests(unittest.TestCase):
    def test_every_reported_client_exists_in_the_kernel_fdinfo_oracle(self) -> None:
        proc = ProcFs()
        rows, _ = collect_gpu_clients(proc, proc.pids())
        if not rows:
            self.skipTest("No readable DRM clients are active")

        verified = 0
        for row in rows:
            pid = int(row["pid"])
            expected_device = str(row["device"])
            expected_client = str(row["clientId"])
            matches = []
            try:
                entries = list(Path(f"/proc/{pid}/fdinfo").iterdir())
            except FileNotFoundError:
                continue
            for fdinfo in entries:
                try:
                    target = (Path(f"/proc/{pid}/fd") / fdinfo.name).resolve()
                    content = fdinfo.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                client = re.search(r"^drm-client-id:\s*(\S+)$", content, re.MULTILINE)
                if (
                    str(target) == expected_device
                    and client
                    and client.group(1) == expected_client
                ):
                    matches.append(fdinfo.name)
            self.assertTrue(matches, row)
            verified += 1
        if not verified:
            self.skipTest("All sampled DRM clients exited before verification")

        selected = next(
            (row for row in rows if Path(f"/proc/{int(row['pid'])}").exists()), None
        )
        if not selected:
            self.skipTest("All sampled DRM clients exited before snapshot verification")
        with TemporaryDirectory() as directory, LiveBackend(Path(directory)) as backend:
            response = backend.request("inspect", query=f"pid:{selected['pid']}")
            self.assertTrue(response["ok"], response)
            snapshot_rows = response["data"]["devices"]["gpu"]
        self.assertTrue(
            any(
                row["pid"] == selected["pid"]
                and row["device"] == selected["device"]
                and row["clientId"] == selected["clientId"]
                for row in snapshot_rows
            ),
            snapshot_rows,
        )


if __name__ == "__main__":
    unittest.main()
