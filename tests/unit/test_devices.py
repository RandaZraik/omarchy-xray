import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from xray.devices.gpu import GpuSampler, collect_gpu_clients, parse_drm_fdinfo
from xray.devices.inhibitors import collect_inhibitors, parse_inhibitors
from xray.devices.pipewire import (
    collect_pipewire,
    owners_for_device,
    parse_pipewire_dump,
)
from xray.system.commands import CommandResult
from xray.system.procfs import ProcFs
from unittest.mock import MagicMock


PIPEWIRE = [
    {
        "id": 35,
        "type": "PipeWire:Interface:Node",
        "info": {
            "state": "running",
            "props": {
                "media.class": "Audio/Source",
                "node.description": "Built-in microphone",
                "node.name": "alsa_input.internal",
                "device.api": "alsa",
            },
        },
    },
    {
        "id": 40,
        "type": "PipeWire:Interface:Node",
        "info": {
            "state": "running",
            "props": {
                "application.process.id": "700",
                "application.name": "Browser",
                "media.class": "Stream/Input/Audio",
                "media.name": "WebRTC capture",
            },
        },
    },
    {
        "id": 90,
        "type": "PipeWire:Interface:Link",
        "info": {
            "state": "active",
            "props": {"link.output.node": 35, "link.input.node": 40},
        },
    },
    {
        "id": 41,
        "type": "PipeWire:Interface:Node",
        "info": {
            "state": "idle",
            "props": {
                "application.process.id": "701",
                "media.class": "Stream/Output/Audio",
                "media.name": "Music",
            },
        },
    },
]


class DeviceTests(unittest.TestCase):
    def test_malformed_device_inventories_are_unavailable_not_empty(self) -> None:
        runner = MagicMock()
        runner.run.return_value = CommandResult(("device-command",), 0, "not-json", "")

        pipewire, pipewire_error = collect_pipewire(runner)
        inhibitors, inhibitor_error = collect_inhibitors(runner, [41])

        self.assertEqual(pipewire, [])
        self.assertEqual(pipewire_error, "PipeWire activity is unavailable")
        self.assertEqual(inhibitors, [])
        self.assertEqual(inhibitor_error, "Sleep-inhibitor activity is unavailable")

    def test_pipewire_classifies_and_resolves_active_owner(self) -> None:
        rows = parse_pipewire_dump(PIPEWIRE)
        self.assertEqual(rows[0]["kind"], "microphone")
        self.assertEqual(owners_for_device(rows, "microphone"), [700])
        self.assertEqual(owners_for_device(rows, "audio"), [700])

    def test_pipewire_joins_nodes_to_their_owning_client(self) -> None:
        payload = [
            {
                "id": 105,
                "type": "PipeWire:Interface:Client",
                "info": {
                    "props": {
                        "application.process.id": 700,
                        "application.name": "Known player",
                    }
                },
            },
            {
                "id": 110,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "state": "running",
                    "props": {
                        "client.id": 105,
                        "object.serial": 90110,
                        "media.class": "Stream/Output/Audio",
                        "media.name": "Silent truth stream",
                    },
                },
            },
        ]
        self.assertEqual(
            parse_pipewire_dump(payload),
            [
                {
                    "id": 90110,
                    "pid": 700,
                    "kind": "audio",
                    "name": "Silent truth stream",
                    "application": "Known player",
                    "mediaClass": "Stream/Output/Audio",
                    "role": "",
                    "state": "Running",
                    "source": "",
                    "sourceIds": [],
                    "active": True,
                }
            ],
        )

    def test_pipewire_does_not_guess_between_screen_camera_and_generic_video(
        self,
    ) -> None:
        payload = [
            {
                "id": identifier,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "state": "running",
                    "props": {
                        "application.process.id": 700 + identifier,
                        "media.class": "Stream/Input/Video",
                        "media.name": name,
                    },
                },
            }
            for identifier, name in (
                (1, "Screen cast"),
                (2, "Webcam capture"),
                (3, "Unlabeled video"),
            )
        ]
        kinds = {row["name"]: row["kind"] for row in parse_pipewire_dump(payload)}
        self.assertEqual(
            kinds,
            {
                "Screen cast": "screen",
                "Webcam capture": "camera",
                "Unlabeled video": "video",
            },
        )

    def test_pipewire_endpoints_are_evidence_not_application_owners(self) -> None:
        rows = parse_pipewire_dump(PIPEWIRE)
        self.assertEqual({row["pid"] for row in rows}, {700, 701})
        self.assertNotIn(0, owners_for_device(rows, "microphone"))
        microphone = next(row for row in rows if row["kind"] == "microphone")
        self.assertEqual(microphone["source"], "Built-in microphone")

    def test_monitor_capture_is_not_claimed_as_a_microphone(self) -> None:
        payload = [
            {
                "id": 20,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "media.class": "Audio/Source",
                        "node.name": "speaker.monitor",
                    }
                },
            },
            {
                "id": 21,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "state": "running",
                    "props": {
                        "media.class": "Stream/Input/Audio",
                        "application.process.id": 700,
                    },
                },
            },
            {
                "id": 22,
                "type": "PipeWire:Interface:Link",
                "info": {
                    "state": "active",
                    "props": {"link.output.node": 20, "link.input.node": 21},
                },
            },
        ]
        rows = parse_pipewire_dump(payload)
        self.assertEqual(rows[0]["kind"], "audio-capture")
        self.assertEqual(owners_for_device(rows, "microphone"), [])

    def test_virtual_capture_chain_resolves_to_the_physical_microphone(self) -> None:
        payload = [
            {
                "id": 20,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "media.class": "Audio/Source",
                        "node.name": "alsa_input.internal",
                    }
                },
            },
            {
                "id": 21,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "media.class": "Audio/Source",
                        "node.name": "noise-suppression.virtual",
                    }
                },
            },
            {
                "id": 22,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "state": "running",
                    "props": {
                        "media.class": "Stream/Input/Audio",
                        "application.process.id": 700,
                    },
                },
            },
            *[
                {
                    "id": identifier,
                    "type": "PipeWire:Interface:Link",
                    "info": {
                        "state": "active",
                        "props": {
                            "link.output.node": output,
                            "link.input.node": input_node,
                        },
                    },
                }
                for identifier, output, input_node in (
                    (30, 20, 21),
                    (31, 21, 22),
                )
            ],
        ]

        row = parse_pipewire_dump(payload)[0]
        self.assertEqual(row["kind"], "microphone")
        self.assertEqual(row["sourceIds"], [20, 21])

    def test_pipewire_graph_limit_is_reported_instead_of_silently_truncating(
        self,
    ) -> None:
        nodes = [
            {
                "id": identifier,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "state": "running" if identifier == 1 else "idle",
                    "props": {
                        "media.class": (
                            "Stream/Input/Audio" if identifier == 1 else "Audio/Source"
                        ),
                        "application.process.id": 700 if identifier == 1 else 0,
                    },
                },
            }
            for identifier in range(1, 132)
        ]
        links = [
            {
                "id": 1000 + identifier,
                "type": "PipeWire:Interface:Link",
                "info": {
                    "state": "active",
                    "props": {
                        "link.output.node": identifier,
                        "link.input.node": identifier + 1,
                    },
                },
            }
            for identifier in range(1, 131)
        ]
        runner = MagicMock()
        runner.run.return_value = CommandResult(
            ("pw-dump",), 0, json.dumps([*nodes, *links]), ""
        )

        rows, limited = collect_pipewire(runner)

        self.assertEqual(len(rows), 1)
        self.assertIn("PipeWire source graph is limited", limited)

    def test_drm_parser_and_sampler_deduplicate_client_fds(self) -> None:
        text = "drm-client-id:\t8\ndrm-engine-render:\t1000000000 ns\ndrm-memory-vram:\t2 MiB\n"
        parsed = parse_drm_fdinfo(text)
        self.assertEqual(parsed["memory"]["vram"], 2 * 1024 * 1024)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "9/fdinfo").mkdir(parents=True)
            (root / "9/fd").mkdir()
            for fd in ("3", "4"):
                (root / f"9/fd/{fd}").symlink_to("/dev/dri/renderD128")
                (root / f"9/fdinfo/{fd}").write_text(text, encoding="utf-8")
            clients, limited = collect_gpu_clients(ProcFs(root), [9])
        self.assertEqual(len(clients), 1)
        self.assertEqual(limited, [])

        sampler = GpuSampler()
        sampler.sample(clients, now=1.0)
        clients[0]["engines"]["render"] = 1_500_000_000
        self.assertEqual(sampler.sample(clients, now=2.0), 50.0)

    def test_drm_standard_memory_and_engine_capacity_are_respected(self) -> None:
        parsed = parse_drm_fdinfo(
            "drm-client-id: 8\n"
            "drm-engine-video: 2000000000 ns\n"
            "drm-engine-capacity-video: 2\n"
            "drm-total-system0: 512 KiB\n"
            "drm-resident-system0: 128 KiB\n"
        )
        self.assertEqual(parsed["memory"], {"system0": 128 * 1024})
        self.assertEqual(parsed["memoryKind"], "resident")
        sampler = GpuSampler()
        client = {"pid": 1, "device": "/dev/dri/renderD128", **parsed}
        self.assertIsNone(sampler.sample([client], now=1.0))
        client["engines"]["video"] += 1_000_000_000
        self.assertEqual(sampler.sample([client], now=2.0), 50.0)
        self.assertLessEqual(client["utilizationPercent"], 100)

    def test_unreadable_gpu_fdinfo_is_reported_as_partial_coverage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "9/fd").mkdir(parents=True)
            (root / "9/fd/3").symlink_to("/dev/dri/renderD128")
            clients, limited = collect_gpu_clients(ProcFs(root), [9])

        self.assertEqual(clients, [])
        self.assertEqual(
            limited, ["GPU fdinfo for process 9 is unavailable: not found"]
        )

    def test_inhibitors_filter_selected_processes(self) -> None:
        rows = parse_inhibitors(
            [
                {"pid": 4, "what": "sleep", "why": "render", "mode": "block"},
                {"pid": 5, "what": "idle", "why": "music", "mode": "delay"},
            ],
            {5},
        )
        self.assertEqual(
            rows,
            [{"pid": 5, "what": "idle", "who": "", "why": "music", "mode": "delay"}],
        )


if __name__ == "__main__":
    unittest.main()
