from dataclasses import replace
import random
import struct
import unittest
from unittest.mock import patch

from support.network import NAMESPACE, PROCESS, connection, counter, packet_bytes
from xray.evidence.redaction import redact_snapshot
from xray.network.diagnostics import parse_diagnostic
from xray.network.packets import PacketKey, PcapStream, normalized_address, parse_packet
from xray.network.traffic import TrafficHistory, destination_scope
from xray.network.sockets import collect_connections


class TrafficTests(unittest.TestCase):
    def setUp(self) -> None:
        self.history = TrafficHistory()

    def sample(
        self,
        sent=0,
        received=0,
        at=1,
        sockets=None,
        processes=None,
        counters=None,
        **kwargs,
    ):
        return self.history.update(
            [connection()] if sockets is None else sockets,
            [PROCESS] if processes is None else processes,
            {7: counter(sent, received)} if counters is None else counters,
            NAMESPACE,
            now=at,
            monotonic=at,
            **kwargs,
        )

    def test_payload_deltas_rates_and_shared_owners_are_counted_once(self):
        other = {**PROCESS, "pid": 43, "name": "worker"}
        shared = [connection(pids=[42, 43])]
        args = {"processes": [PROCESS, other], "sockets": shared}
        first = self.sample(1000, 3000, **args)
        self.assertIsNone(first["totals"]["sentRate"])
        second = self.sample(3000, 9000, at=3, **args)
        self.assertEqual(second["totals"]["sentRate"], 1000)
        self.assertEqual(second["totals"]["receivedRate"], 3000)
        self.assertEqual(second["totals"]["sentBytes"], 2000)
        self.assertEqual(len(second["flows"][0]["owners"]), 2)

    def test_identity_cookie_endpoint_and_namespace_do_not_inherit_bytes(self):
        cases = [
            {"processes": [{**PROCESS, "startTime": 101}]},
            {"counters": {7: counter(100000, 100000, cookie="new")}},
            {"sockets": [connection(remotePort=80)]},
            {"sockets": [connection(networkNamespace="net:[999]")]},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.history = TrafficHistory()
                self.sample(10, 20)
                result = self.sample(100000, 100000, at=2, **changes)
                self.assertEqual(result["totals"]["sentBytes"], 0)
                self.assertIsNone(result["totals"]["sentRate"])

    def test_counter_failure_and_reset_need_a_new_baseline(self):
        self.sample(100, 100)
        unavailable = self.sample(at=2, counters={})
        self.assertEqual(len(unavailable["flows"]), 1)
        self.assertEqual(unavailable["flows"][0]["sampleStatus"], "unavailable")
        baseline = self.sample(200, 200, at=3)
        self.assertIsNone(baseline["totals"]["sentRate"])
        reset = self.sample(0, 0, at=4)
        self.assertIsNone(reset["totals"]["sentRate"])
        measured = self.sample(100, 100, at=5)
        self.assertEqual(measured["totals"]["sentBytes"], 100)

    def test_history_closure_missing_data_retention_and_pause(self):
        self.sample()
        partial = self.sample(at=2, sockets=[], complete=False)
        self.assertEqual([row["kind"] for row in partial["events"]], ["opened"])
        self.assertEqual(partial["flows"][0]["sampleStatus"], "unknown")
        closed = self.sample(at=3, sockets=[])
        self.assertFalse(closed["flows"][0]["active"])
        self.assertEqual(closed["events"][0]["kind"], "closed")
        self.assertEqual(self.sample(at=400, sockets=[])["flows"], [])
        self.sample(100, 100, at=401)
        self.history.reset_rates()
        resumed = self.sample(10000, 10000, at=402)
        self.assertIsNone(resumed["totals"]["sentRate"])

    def test_udp_peers_capture_direction_history_and_idle_rates(self):
        sockets = [
            connection(
                protocol="UDP4", remoteAddress="0.0.0.0", remotePort=0, listening=True
            )
        ]
        self.sample(sockets=sockets, counters={}, packets={})
        packet = PacketKey("UDP", "10.0.0.2", 41000, "1.1.1.1", 53)
        result = self.sample(
            at=3,
            sockets=sockets,
            counters={},
            packets={packet: [128, 1], packet.reverse(): [228, 1]},
        )
        peer = next(row for row in result["flows"] if row["remotePort"] == 53)
        self.assertEqual(peer["sentRate"], 64)
        self.assertEqual(peer["receivedRate"], 114)
        self.assertEqual(result["totals"]["sentBytes"], 128)
        self.assertEqual(peer["remoteAddress"], "1.1.1.1")
        idle = self.sample(at=4, sockets=sockets, counters={}, packets={})
        peer = next(row for row in idle["flows"] if row["remotePort"] == 53)
        self.assertEqual(peer["sentRate"], 0)
        self.assertEqual(peer["receivedRate"], 0)
        self.assertNotIn("1.1.1.1", peer["id"])

    def test_ambiguous_reuseport_and_new_owners_are_not_guessed(self):
        sockets = [
            connection(
                protocol="UDP4", remoteAddress="0.0.0.0", remotePort=0, listening=True
            ),
            connection(
                protocol="UDP4",
                remoteAddress="0.0.0.0",
                remotePort=0,
                listening=True,
                inode=8,
            ),
        ]
        packet = PacketKey("UDP", "10.0.0.2", 41000, "1.1.1.1", 53)
        self.sample(sockets=sockets, counters={}, packets={})
        result = self.sample(
            at=2, sockets=sockets, counters={}, packets={packet: [128, 1]}
        )
        self.assertEqual(result["unattributedPackets"], 1)
        self.assertEqual(result["totals"]["sentBytes"], 0)
        self.history = TrafficHistory()
        result = self.sample(
            sockets=sockets[:1], counters={}, packets={packet: [128, 1]}
        )
        self.assertEqual(result["unattributedPackets"], 1)

    def test_loopback_counts_one_outgoing_and_one_incoming_owner(self):
        sockets = [
            connection(localAddress="127.0.0.1", remoteAddress="127.0.0.1"),
            connection(
                localAddress="127.0.0.1",
                remoteAddress="127.0.0.1",
                localPort=443,
                remotePort=41000,
                inode=8,
                pids=[43],
            ),
        ]
        processes = [PROCESS, {**PROCESS, "pid": 43}]
        self.sample(sockets=sockets, processes=processes, counters={}, packets={})
        key = PacketKey("TCP", "127.0.0.1", 41000, "127.0.0.1", 443)
        result = self.sample(
            at=2,
            sockets=sockets,
            processes=processes,
            counters={},
            packets={key: [140, 1]},
        )
        self.assertEqual(result["totals"]["sentBytes"], 140)
        self.assertEqual(result["totals"]["receivedBytes"], 140)

    def test_packet_attribution_matches_exhaustive_endpoint_matching(self):
        randomizer = random.Random(42)
        for case in range(80):
            sockets = [
                connection(
                    inode=index + 1,
                    protocol=randomizer.choice(("TCP4", "UDP4")),
                    localAddress=randomizer.choice(
                        ("10.0.0.2", "1.1.1.1", "0.0.0.0", "::")
                    ),
                    localPort=randomizer.choice((41000, 443)),
                    remoteAddress=randomizer.choice(("10.0.0.2", "1.1.1.1", "0.0.0.0")),
                    remotePort=randomizer.choice((0, 41000, 443)),
                    listening=randomizer.choice((True, False)),
                    networkNamespace=NAMESPACE if index % 5 else "net:[999]",
                    pids=[42] if index % 7 else [99],
                    packetAttributionLimited=index % 11 == 0,
                )
                for index in range(32)
            ]
            # Include connected, wildcard and IPv4-mapped bindings together.
            sockets[1]["localAddress"] = "::ffff:10.0.0.2"
            packet = PacketKey(
                randomizer.choice(("TCP", "UDP")), "10.0.0.2", 41000, "1.1.1.1", 443
            )
            expected = {}
            for direction, key in enumerate((packet, packet.reverse())):
                candidates = [
                    row
                    for row in sockets[:-4]
                    if row["pids"] == [42]
                    and row["networkNamespace"] == NAMESPACE
                    and not row["packetAttributionLimited"]
                    and row["protocol"][:3] == key.protocol
                    and row["localPort"] == key.source_port
                    and normalized_address(row["localAddress"])
                    in (key.source, "0.0.0.0", "::")
                    and (
                        not row["remotePort"]
                        or (row["remotePort"], normalized_address(row["remoteAddress"]))
                        == (key.destination_port, key.destination)
                    )
                    and (key.protocol == "UDP" or not row["listening"])
                ]
                candidates = [
                    row for row in candidates if row["remotePort"]
                ] or candidates
                if len(candidates) == 1:
                    expected.setdefault(candidates[0]["inode"], [0, 0])[direction] = 600
            with self.subTest(case=case):
                self.history = TrafficHistory()
                self.sample(sockets=sockets[:-4], counters={}, packets={})
                result = self.sample(
                    at=2, sockets=sockets, counters={}, packets={packet: [600, 3]}
                )
                actual = {}
                for flow in result["flows"]:
                    if flow["sentBytes"] or flow["receivedBytes"]:
                        totals = actual.setdefault(flow["inode"], [0, 0])
                        totals[0] += flow["sentBytes"]
                        totals[1] += flow["receivedBytes"]
                self.assertEqual(actual, expected)
                self.assertEqual(result["unattributedPackets"], 0 if expected else 3)

    def test_connected_udp_candidates_take_precedence_over_wildcard_ambiguity(self):
        wildcard = connection(
            protocol="UDP4",
            localAddress="::",
            remoteAddress="::",
            remotePort=0,
            listening=True,
        )
        connected = connection(
            protocol="UDP4", localAddress="10.0.0.2", remotePort=53, inode=8
        )
        packet = PacketKey("UDP", "10.0.0.2", 41000, "1.1.1.1", 53)
        cases = (
            ([wildcard, {**wildcard, "inode": 9}, connected], 140),
            ([wildcard, connected, {**connected, "inode": 9}], 0),
            ([wildcard, {**wildcard, "inode": 9}, {**wildcard, "inode": 10}], 0),
        )
        for sockets, expected in cases:
            with self.subTest(sockets=sockets):
                self.history = TrafficHistory()
                self.sample(sockets=sockets, counters={}, packets={})
                result = self.sample(
                    at=2, sockets=sockets, counters={}, packets={packet: [140, 1]}
                )
                self.assertEqual(result["totals"]["sentBytes"], expected)
                self.assertEqual(result["unattributedPackets"], 0 if expected else 1)

    def test_large_shared_tcp_port_attributes_each_peer_once(self):
        sockets = [
            connection(inode=index + 1, localPort=443, remotePort=10000 + index)
            for index in range(1024)
        ]
        packets = {}
        for index in range(2048):
            key = PacketKey("TCP", "10.0.0.2", 443, "1.1.1.1", 10000 + index)
            packets[key] = [1000, 1]
            packets[key.reverse()] = [2000, 1]
        self.sample(sockets=sockets, counters={}, packets={})
        result = self.sample(at=2, sockets=sockets, counters={}, packets=packets)
        self.assertEqual(len(result["flows"]), 1024)
        self.assertEqual(result["unattributedPackets"], 2048)
        self.assertEqual(result["totals"]["sentBytes"], 1024 * 1000)
        self.assertEqual(result["totals"]["receivedBytes"], 1024 * 2000)
        self.assertTrue(
            all(
                row["sentBytes"] == 1000 and row["receivedBytes"] == 2000
                for row in result["flows"]
            )
        )

    def test_socket_budget_does_not_report_a_live_socket_closed(self):
        with patch(
            "xray.network.traffic.LIMITS",
            replace(
                __import__("xray.config", fromlist=["LIMITS"]).LIMITS, network_flows=2
            ),
        ):
            a, b, c = (connection(inode=i) for i in (7, 8, 9))
            self.sample(sockets=[a, b], counters={})
            result = self.sample(at=2, sockets=[c, a, b], counters={})
            self.assertFalse(
                any(event["kind"] == "closed" for event in result["events"])
            )
            self.assertGreater(result["omittedFlows"], 0)

    def test_udp_ambiguity_checks_unselected_sockets_and_previous_sample(self):
        selected = connection(
            protocol="UDP4", remoteAddress="0.0.0.0", remotePort=0, listening=True
        )
        foreign = {**selected, "inode": 8, "pids": []}
        packet = PacketKey("UDP", "10.0.0.2", 41000, "1.1.1.1", 53)
        with patch(
            "xray.network.sockets.owned_socket_rows",
            return_value=([selected, foreign], []),
        ):
            rows, limited = collect_connections(None, [42])
        self.assertFalse(limited)
        self.assertTrue(rows[0]["packetAttributionLimited"])
        self.sample(sockets=rows, counters={}, packets={})
        result = self.sample(
            at=2, sockets=rows, counters={}, packets={packet: [128, 1]}
        )
        self.assertEqual(result["totals"]["sentBytes"], 0)
        self.assertEqual(result["unattributedPackets"], 1)
        clear = [{**selected, "packetAttributionLimited": False}]
        result = self.sample(
            at=3, sockets=clear, counters={}, packets={packet: [128, 1]}
        )
        self.assertEqual(result["totals"]["sentBytes"], 0)
        result = self.sample(
            at=4, sockets=clear, counters={}, packets={packet: [128, 1]}
        )
        self.assertEqual(result["totals"]["sentBytes"], 128)
        expired = self.sample(
            at=500, sockets=clear, counters={}, packets={}, history_seconds=60
        )
        self.assertFalse(any(row["remotePort"] == 53 for row in expired["flows"]))

    def test_mode_switch_resets_incompatible_totals_and_history(self):
        self.sample()
        self.sample(100, 200, at=2)
        result = self.sample(at=3, packets={})
        self.assertEqual(result["mode"], "packets")
        self.assertEqual(result["totals"]["sentBytes"], 0)
        self.assertEqual(len(result["samples"]), 1)

    def test_histories_are_bounded(self):
        with patch(
            "xray.network.traffic.LIMITS",
            replace(
                __import__("xray.config", fromlist=["LIMITS"]).LIMITS, network_flows=2
            ),
        ):
            for at in range(1, 8):
                self.sample(at=at, sockets=[connection(inode=at)], counters={})
            self.assertEqual(len(self.history.flows), 2)
            self.assertEqual(self.history.omitted, 5)


class PacketTests(unittest.TestCase):
    def test_tcp_udp_v4_v6_ethernet_vlan_and_truncated_payload(self):
        for protocol in ("TCP", "UDP"):
            for ipv6 in (False, True):
                for ethernet, vlan in ((False, False), (True, False), (True, True)):
                    with self.subTest(
                        protocol=protocol, ipv6=ipv6, ethernet=ethernet, vlan=vlan
                    ):
                        frame = packet_bytes(
                            protocol, 1000, ipv6, ethernet=ethernet, vlan=vlan
                        )
                        packet = parse_packet(frame[:128], 1 if ethernet else 101)
                        self.assertIsNotNone(packet)
                        self.assertEqual(packet.key.protocol, protocol)
                        self.assertEqual(
                            packet.ip_bytes,
                            (40 if ipv6 else 20)
                            + (20 if protocol == "TCP" else 8)
                            + 1000,
                        )
                        self.assertEqual(
                            packet.transport_bytes,
                            (20 if protocol == "TCP" else 8) + 1000,
                        )
                        self.assertEqual(
                            packet.link_bytes, 18 if vlan else 14 if ethernet else 0
                        )

    def test_ipv6_extensions_and_fragments(self):
        frame = bytearray(packet_bytes(ipv6=True))
        frame[6] = 0
        struct.pack_into("!H", frame, 4, 128)
        frame[40:40] = b"\x06\x00" + bytes(6)
        self.assertEqual(parse_packet(bytes(frame)).transport_bytes, 120)
        frame[6] = 44
        frame[42] = 1
        self.assertIsNone(parse_packet(bytes(frame)))
        frame4 = bytearray(packet_bytes())
        frame4[6] = 0x20
        self.assertIsNone(parse_packet(bytes(frame4)))

    def test_malformed_header_and_pcap_stream_boundaries(self):
        for size in range(40):
            self.assertIsNone(parse_packet(packet_bytes()[:size]))
        frame = packet_bytes(ethernet=True)
        raw = (
            struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 512, 1)
            + struct.pack("<IIII", 0, 0, len(frame), len(frame))
            + frame
        )
        parser = PcapStream()
        packets = []
        for byte in raw:
            packets += parser.feed(bytes([byte]))
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].ip_bytes, 140)
        with self.assertRaises(ValueError):
            PcapStream().feed(b"bad!" + bytes(20))

    def test_scope_and_export_redaction(self):
        self.assertEqual(destination_scope("127.0.0.1"), "loopback")
        self.assertEqual(destination_scope("192.168.1.4"), "local")
        self.assertEqual(destination_scope("1.1.1.1"), "internet")
        self.assertEqual(destination_scope("ff02::1"), "multicast")
        self.assertEqual(destination_scope("::ffff:127.0.0.1"), "loopback")
        result = redact_snapshot(
            {
                "network": {
                    "flows": [
                        {"hostname": "private.example", "remoteAddress": "1.1.1.1"}
                    ]
                }
            }
        )
        self.assertNotIn("private.example", str(result))
        self.assertNotIn("1.1.1.1", str(result))

    def test_tcp_info_uapi_offsets(self):
        message = bytearray(72)
        message[0] = 2
        struct.pack_into("!HH", message, 4, 41000, 443)
        message[8:12] = bytes([10, 0, 0, 2])
        message[24:28] = bytes([1, 1, 1, 1])
        struct.pack_into("=I", message, 68, 7)
        info = bytearray(136)
        struct.pack_into("=QQ", info, 120, 1000, 2000)
        struct.pack_into("=I", info, 68, 2500)
        struct.pack_into("=I", info, 100, 5)
        message += struct.pack("=HH", 140, 2) + info
        result = parse_diagnostic(bytes(message))
        self.assertEqual(
            (
                result.inode,
                result.sent,
                result.received,
                result.rtt_ms,
                result.retransmits,
            ),
            (7, 1000, 2000, 2.5, 5),
        )
