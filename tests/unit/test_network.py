from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import ANY, patch

from xray.network.sockets import (
    collect_connections,
    decode_address,
    owners_for_port,
    parse_socket_table,
    socket_rows_for_namespaces,
)
from xray.config import LIMITS
from xray.system.procfs import ProcFs


TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1435 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000 0 555 1
   1: 00000000:1F90 08080808:01BB 01 00000000:00000000 00:00000000 00000000  1000 0 777 1
"""

UDP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:14E9 08080808:0035 01 00000000:00000000 00:00000000 00000000  1000 0 888 1
   1: 00000000:14EA 00000000:0000 07 00000000:00000000 00:00000000 00000000  1000 0 889 1
"""


class NetworkTests(unittest.TestCase):
    def test_decodes_kernel_addresses(self) -> None:
        self.assertEqual(decode_address("0100007F", False), "127.0.0.1")
        self.assertEqual(
            decode_address("00000000000000000000000001000000", True), "::1"
        )

    def test_parses_listener_and_public_binding(self) -> None:
        rows = parse_socket_table(TCP, "tcp")
        self.assertTrue(rows[0]["listening"])
        self.assertFalse(rows[0]["publicListener"])
        self.assertFalse(rows[0]["externallyReachable"])
        self.assertTrue(rows[1]["publicListener"] is False)
        self.assertEqual(rows[1]["remotePort"], 443)

    def test_connection_collection_joins_socket_inode_to_process(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "20/fd").mkdir(parents=True)
            (root / "20/net").mkdir()
            (root / "20/ns").mkdir()
            (root / "20/ns/net").symlink_to("net:[100]")
            (root / "20/fd/3").symlink_to("socket:[555]")
            (root / "20/net/tcp").write_text(TCP, encoding="utf-8")
            for name in ("tcp6", "udp", "udp6"):
                (root / f"20/net/{name}").write_text("header\n", encoding="utf-8")
            rows, limited = collect_connections(ProcFs(root), [20])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pids"], [20])
        self.assertEqual(limited, [])

    def test_connection_collection_reuses_each_process_namespace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "20/fd").mkdir(parents=True)
            (root / "20/net").mkdir()
            (root / "20/fd/3").symlink_to("socket:[555]")
            (root / "20/net/tcp").write_text(TCP, encoding="utf-8")
            for name in ("tcp6", "udp", "udp6"):
                (root / f"20/net/{name}").write_text("header\n", encoding="utf-8")
            with patch(
                "xray.network.sockets._network_namespace", return_value="net:[100]"
            ) as namespace:
                rows, limited = collect_connections(ProcFs(root), [20])

        self.assertEqual(len(rows), 1)
        self.assertEqual(limited, [])
        namespace.assert_called_once_with(ANY, 20)

    def test_connected_wildcard_udp_socket_is_not_reported_as_public_listener(
        self,
    ) -> None:
        connected, listener = parse_socket_table(UDP, "udp")

        self.assertFalse(connected["listening"])
        self.assertFalse(connected["publicListener"])
        self.assertTrue(listener["listening"])
        self.assertTrue(listener["publicListener"])
        self.assertTrue(listener["externallyReachable"])

    def test_port_owner_lookup_returns_its_evidence_limitations(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "20/fd").mkdir(parents=True)
            (root / "20/net").mkdir()
            (root / "20/ns").mkdir()
            (root / "20/ns/net").symlink_to("net:[100]")
            (root / "20/status").write_text(
                f"Uid:\t{os.getuid()} {os.getuid()} {os.getuid()} {os.getuid()}\n",
                encoding="utf-8",
            )
            (root / "20/fd/3").symlink_to("socket:[555]")
            (root / "20/net/tcp").write_text(TCP, encoding="utf-8")
            for name in ("tcp6", "udp", "udp6"):
                (root / f"20/net/{name}").write_text("header\n", encoding="utf-8")
            owners, limited = owners_for_port(ProcFs(root), 5173)

        self.assertEqual(owners, [20])
        self.assertEqual(limited, [])

    def test_port_owner_lookup_prefers_listener_over_connected_client(self) -> None:
        rows = [
            {
                "localPort": 41000,
                "remotePort": 9000,
                "listening": False,
                "pids": [10],
            },
            {
                "localPort": 9000,
                "remotePort": 0,
                "listening": True,
                "pids": [30],
            },
            {
                "localPort": 9000,
                "remotePort": 41000,
                "listening": False,
                "pids": [30],
            },
        ]
        with patch("xray.network.sockets.owned_socket_rows", return_value=(rows, [])):
            owners, limited = owners_for_port(
                ProcFs(Path("/missing")), 9000, pids=[10, 30]
            )

        self.assertEqual(owners, [30, 10])
        self.assertEqual(limited, [])

    def test_port_owner_lookup_ranks_shared_listeners_server_and_client(self) -> None:
        rows = [
            {
                "localPort": 41000,
                "remotePort": 9000,
                "listening": False,
                "pids": [10],
            },
            {
                "localPort": 9000,
                "remotePort": 41000,
                "listening": False,
                "pids": [20],
            },
            {
                "localPort": 9000,
                "remotePort": 0,
                "listening": True,
                "pids": [40, 30],
            },
        ]
        with patch("xray.network.sockets.owned_socket_rows", return_value=(rows, [])):
            owners, limited = owners_for_port(
                ProcFs(Path("/missing")), 9000, pids=[10, 20, 30, 40]
            )

        self.assertEqual(owners, [30, 40, 20, 10])
        self.assertEqual(limited, [])

    def test_missing_process_network_namespace_is_named_as_the_limitation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "9").mkdir()
            rows, limited = socket_rows_for_namespaces(ProcFs(root), [9])

        self.assertEqual(rows, [])
        self.assertEqual(limited, ["Network namespace is unavailable for process 9"])

    def test_identical_socket_inodes_in_other_network_namespaces_never_collide(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, namespace, table in (
                (20, "net:[100]", TCP),
                (21, "net:[200]", TCP.replace(":1435", ":1F90")),
            ):
                (root / f"{pid}/fd").mkdir(parents=True)
                (root / f"{pid}/net").mkdir()
                (root / f"{pid}/ns").mkdir()
                (root / f"{pid}/ns/net").symlink_to(namespace)
                (root / f"{pid}/fd/3").symlink_to("socket:[555]")
                (root / f"{pid}/status").write_text(
                    f"Uid:\t{os.getuid()} {os.getuid()} {os.getuid()} {os.getuid()}\n",
                    encoding="utf-8",
                )
                (root / f"{pid}/net/tcp").write_text(table, encoding="utf-8")
                for name in ("tcp6", "udp", "udp6"):
                    (root / f"{pid}/net/{name}").write_text(
                        "header\n", encoding="utf-8"
                    )

            owners, limited = owners_for_port(ProcFs(root), 5173)

        self.assertEqual(owners, [20])
        self.assertEqual(limited, [])

    def test_network_namespace_collection_is_bounded_and_explicit(self) -> None:
        namespaces = {
            pid: f"net:[{pid}]" for pid in range(1, LIMITS.network_namespaces + 5)
        }
        with patch(
            "xray.network.sockets.socket_rows", return_value=([], [])
        ) as collect:
            rows, limited = socket_rows_for_namespaces(
                ProcFs(Path("/missing")), list(namespaces), namespaces
            )

        self.assertEqual(rows, [])
        self.assertEqual(collect.call_count, LIMITS.network_namespaces)
        self.assertIn(
            f"Network sockets are limited to {LIMITS.network_namespaces} namespaces",
            limited,
        )


if __name__ == "__main__":
    unittest.main()
