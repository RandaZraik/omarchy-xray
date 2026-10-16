from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import ipaddress
from pathlib import Path
import socket
import time

from xray.config import LIMITS
from xray.network.capture import PacketCapture, interface_labels
from xray.network.diagnostics import TcpCounter, tcp_counters
from xray.network.names import DestinationNames
from xray.network.packets import PacketKey, normalized_address
from xray.system.commands import CommandRunner
from xray.system.procfs import ProcFs


def destination_scope(address: str) -> str:
    value = ipaddress.ip_address(normalized_address(address))
    if value.is_unspecified:
        return "listener"
    if value.is_loopback:
        return "loopback"
    if value.is_multicast:
        return "multicast"
    return "internet" if value.is_global else "local"


def socket_key(row: dict[str, object]) -> PacketKey:
    return PacketKey(
        str(row["protocol"])[:3],
        normalized_address(str(row["localAddress"])),
        int(row["localPort"]),
        normalized_address(str(row["remoteAddress"])),
        int(row["remotePort"]),
    )


def counter_matches(counter: TcpCounter, row: dict[str, object]) -> bool:
    return socket_key(row) == PacketKey(
        "TCP",
        normalized_address(counter.local_address),
        counter.local_port,
        normalized_address(counter.remote_address),
        counter.remote_port,
    )


def socket_identity(row: dict[str, object], owners: list[dict[str, object]]) -> str:
    endpoint = hashlib.sha256(repr(socket_key(row)).encode()).hexdigest()[:24]
    identities = ",".join(
        f"{owner['pid']}:{owner['startTime']}:{owner['uid']}" for owner in owners
    )
    return f"{row['networkNamespace']}/{row['inode']}/{endpoint}/{identities}"


@dataclass
class Flow:
    row: dict[str, object]
    counter: tuple[int, int] | None = None
    sampled_at: float = 0


class TrafficHistory:
    """One source of truth for flow identity, rates, retained history and totals."""

    def __init__(self) -> None:
        self.flows: dict[str, Flow] = {}
        self.events: deque[dict[str, object]] = deque(maxlen=LIMITS.network_events)
        self.samples: deque[dict[str, object]] = deque(maxlen=LIMITS.network_samples)
        self.sent = 0
        self.received = 0
        self.previous: dict[str, dict[str, object]] = {}
        self.sampled_at = 0.0
        self.mode = "tcp"
        self.omitted = 0

    def reset_rates(self) -> None:
        for flow in self.flows.values():
            flow.counter = None
            flow.sampled_at = 0
        self.previous = {}
        self.sampled_at = 0

    def _event(self, kind: str, row: dict[str, object], now: float) -> None:
        self.events.append(
            {
                "kind": kind,
                "at": now,
                "flowId": row["id"],
                "protocol": row["protocol"],
                "address": row["remoteAddress"],
                "port": row["remotePort"],
                "owners": row["owners"],
            }
        )

    def update(
        self,
        sockets: list[dict[str, object]],
        processes: list[dict[str, object]],
        counters: dict[int, TcpCounter],
        namespace: str,
        packets: dict[PacketKey, list[int]] | None = None,
        *,
        complete: bool = True,
        history_seconds: int = 300,
        now: float | None = None,
        monotonic: float | None = None,
    ) -> dict[str, object]:
        now = time.time() if now is None else now
        monotonic = time.monotonic() if monotonic is None else monotonic
        complete = complete and len(sockets) <= LIMITS.network_flows
        mode = "packets" if packets is not None else "tcp"
        if mode != self.mode:
            # Counters with different byte definitions must never be added together.
            self.__init__()
            self.mode = mode
        for flow in self.flows.values():
            flow.row.update({"sentRate": None, "receivedRate": None})
        owners = {
            int(row["pid"]): {
                "pid": int(row["pid"]),
                "name": str(row.get("name", "Process")),
                "startTime": int(row["startTime"]),
                "uid": int(row["uid"]),
            }
            for row in processes
        }
        current: dict[str, dict[str, object]] = {}
        previous_ids = {
            socket_identity(row, row["owners"]): identifier
            for identifier, row in self.previous.items()
        }
        for source in sockets[: LIMITS.network_flows]:
            selected = [
                owners[pid] for pid in sorted(source.get("pids", [])) if pid in owners
            ]
            if not selected:
                continue
            counter = (
                counters.get(int(source["inode"]))
                if source["networkNamespace"] == namespace
                else None
            )
            if counter and not counter_matches(counter, source):
                counter = None
            base = socket_identity(source, selected)
            identifier = (
                base + "/" + counter.cookie if counter else previous_ids.get(base, base)
            )
            row = {**source, "id": identifier, "owners": selected}
            current[identifier] = row
            self._touch(row, now)
            flow = self.flows[identifier]
            flow.row.update(
                {
                    "active": True,
                    "lastSeen": now,
                    "state": source["state"],
                    "sentRate": None,
                    "receivedRate": None,
                    "sampleStatus": "unavailable",
                }
            )
            if mode == "tcp" and not source["listening"] and counter:
                values = (counter.sent, counter.received)
                elapsed = monotonic - flow.sampled_at
                valid = (
                    flow.counter is not None
                    and elapsed > 0
                    and all(a >= b for a, b in zip(values, flow.counter))
                )
                if valid:
                    self._add(
                        flow,
                        values[0] - flow.counter[0],
                        values[1] - flow.counter[1],
                        elapsed,
                    )
                else:
                    flow.row["sampleStatus"] = "baseline"
                flow.counter = values
                flow.sampled_at = monotonic
                flow.row.update(
                    {"rttMs": counter.rtt_ms, "retransmits": counter.retransmits}
                )
            elif mode == "tcp":
                flow.counter = None
                flow.sampled_at = 0
        unmatched = 0
        stable: dict[str, dict[str, object]] = {}
        if packets is not None:
            elapsed = monotonic - self.sampled_at
            stable = {
                key: row
                for key, row in current.items()
                if key in self.previous
                and elapsed > 0
                and row["networkNamespace"] == namespace
                and not row.get("packetAttributionLimited")
                and not self.previous[key].get("packetAttributionLimited")
            }
            by_endpoint: dict[PacketKey, list[str]] = defaultdict(list)
            for identifier, row in stable.items():
                if row["protocol"].startswith("TCP") and row["listening"]:
                    continue
                key = socket_key(row)
                if not key.destination_port:
                    key = PacketKey(key.protocol, key.source, key.source_port, "", 0)
                # Two owners already prove ambiguity; retaining more cannot
                # change attribution and would make each packet scan them all.
                bucket = by_endpoint[key]
                if len(bucket) < 2:
                    bucket.append(identifier)
                if not row["listening"]:
                    self.flows[identifier].row.update(
                        {
                            "sentRate": 0.0,
                            "receivedRate": 0.0,
                            "sampleStatus": "measured",
                        }
                    )
            for packet, (byte_count, packet_count) in packets.items():
                matched = False
                for outgoing, key in ((True, packet), (False, packet.reverse())):
                    candidates = self._packet_candidates(by_endpoint, key)
                    if len(candidates) != 1:
                        continue
                    identifier = candidates[0]
                    row = stable[identifier]
                    if (
                        row["protocol"].startswith("UDP")
                        and int(row["remotePort"]) == 0
                    ):
                        peer = f"{key.destination}:{key.destination_port}".encode()
                        identifier += "/" + hashlib.sha256(peer).hexdigest()[:24]
                        row = {
                            **row,
                            "id": identifier,
                            "localAddress": key.source,
                            "socketId": row["id"],
                            "remoteAddress": key.destination,
                            "remotePort": key.destination_port,
                            "listening": False,
                            "publicListener": False,
                            "externallyReachable": False,
                            "state": "Observed",
                        }
                        self._touch(row, now)
                    flow = self.flows[identifier]
                    flow.row.update({"active": True, "lastSeen": now})
                    self._add(
                        flow,
                        byte_count if outgoing else 0,
                        0 if outgoing else byte_count,
                        elapsed,
                        accumulate=True,
                    )
                    field = "sentPackets" if outgoing else "receivedPackets"
                    flow.row[field] = int(flow.row.get(field, 0)) + packet_count
                    matched = True
                if not matched:
                    unmatched += packet_count
        active_socket_ids = set(current)
        cutoff = now - history_seconds
        for identifier, flow in self.flows.items():
            parent = flow.row.get("socketId", identifier)
            retained_udp = parent != identifier and parent in active_socket_ids
            if retained_udp and float(flow.row["lastSeen"]) < cutoff:
                flow.row["active"] = False
                continue
            if retained_udp and flow.row["sentRate"] is None:
                flow.row.update(
                    {
                        "sentRate": 0.0 if parent in stable else None,
                        "receivedRate": 0.0 if parent in stable else None,
                        "sampleStatus": "measured"
                        if parent in stable
                        else "unavailable",
                    }
                )
            if identifier in active_socket_ids or retained_udp:
                continue
            if flow.row["active"] and complete:
                self._event("closed", flow.row, now)
                flow.row["active"] = False
            flow.row.update(
                {
                    "sentRate": None,
                    "receivedRate": None,
                    "sampleStatus": "closed" if complete else "unknown",
                }
            )
            flow.counter = None
        self.flows = {
            key: flow
            for key, flow in self.flows.items()
            if flow.row["active"] or float(flow.row["lastSeen"]) >= cutoff
        }
        if len(self.flows) > LIMITS.network_flows:
            ordered = sorted(
                self.flows,
                key=lambda key: (
                    self.flows[key].row["active"],
                    self.flows[key].row["lastSeen"],
                ),
                reverse=True,
            )
            self.omitted += len(ordered) - LIMITS.network_flows
            self.flows = {
                key: self.flows[key] for key in ordered[: LIMITS.network_flows]
            }
        rows = [dict(flow.row) for flow in self.flows.values()]
        measured = [
            row for row in rows if row["active"] and row["sampleStatus"] == "measured"
        ]
        sent_rate = (
            sum(float(row["sentRate"] or 0) for row in measured) if measured else None
        )
        received_rate = (
            sum(float(row["receivedRate"] or 0) for row in measured)
            if measured
            else None
        )
        self.samples.append(
            {"at": now, "sentRate": sent_rate, "receivedRate": received_rate}
        )
        self.previous = current
        self.sampled_at = monotonic
        return {
            "mode": mode,
            "flows": rows,
            "events": [
                event for event in reversed(self.events) if float(event["at"]) >= cutoff
            ],
            "samples": [
                sample for sample in self.samples if float(sample["at"]) >= cutoff
            ],
            "omittedFlows": self.omitted + max(0, len(sockets) - LIMITS.network_flows),
            "unattributedPackets": unmatched,
            "totals": {
                "sentBytes": self.sent,
                "receivedBytes": self.received,
                "sentRate": sent_rate,
                "receivedRate": received_rate,
                "measuredFlows": len(measured),
                "activeFlows": sum(
                    row["active"] and not row["listening"] for row in rows
                ),
            },
        }

    def _touch(self, row: dict[str, object], now: float) -> None:
        identifier = str(row["id"])
        if identifier not in self.flows:
            initial = {
                **row,
                "scope": destination_scope(str(row["remoteAddress"])),
                "firstSeen": now,
                "lastSeen": now,
                "active": True,
                "sentBytes": 0,
                "receivedBytes": 0,
                "sentRate": None,
                "receivedRate": None,
                "sampleStatus": "baseline",
            }
            self.flows[identifier] = Flow(initial)
            if not row["listening"]:
                self._event("opened", initial, now)
        else:
            self.flows[identifier].row.update(row)

    def _add(
        self,
        flow: Flow,
        sent: int,
        received: int,
        elapsed: float,
        accumulate: bool = False,
    ) -> None:
        flow.row["sentBytes"] += sent
        flow.row["receivedBytes"] += received
        self.sent += sent
        self.received += received
        for key, value in (("sentRate", sent), ("receivedRate", received)):
            previous = (flow.row.get(key) or 0) if accumulate else 0
            flow.row[key] = round(previous + value / elapsed, 2)
        flow.row["sampleStatus"] = "measured"
        flow.row["sampleSeconds"] = elapsed

    @staticmethod
    def _packet_candidates(
        by_endpoint: dict[PacketKey, list[str]], packet: PacketKey
    ) -> list[str]:
        local_addresses = dict.fromkeys((packet.source, "0.0.0.0", "::"))
        # Prefer connected peers even when they are ambiguous. Only fall back
        # to unconnected sockets when no connected peer matches.
        for remote, port in ((packet.destination, packet.destination_port), ("", 0)):
            candidates: list[str] = []
            for local in local_addresses:
                candidates.extend(
                    by_endpoint.get(
                        PacketKey(
                            packet.protocol, local, packet.source_port, remote, port
                        ),
                        (),
                    )
                )
            if candidates:
                return candidates
        return []


class NetworkMonitor:
    def __init__(self, proc: ProcFs, runner: CommandRunner) -> None:
        self.proc = proc
        self.capture = PacketCapture()
        self.names = DestinationNames(runner)
        self.history = TrafficHistory()
        self._paused_interface = ""

    def pause(self, paused: bool) -> None:
        if paused:
            self._paused_interface = (
                self.capture.interface
                if self.capture.active or self.capture.starting
                else ""
            )
            self.capture.close()
        elif self._paused_interface:
            interface, self._paused_interface = self._paused_interface, ""
            try:
                self.capture.start(interface)
            except ValueError:
                self.capture.error = f"{interface} is no longer available. Choose another interface."
                self.capture.error_kind = "interface-unavailable"

    def sample(
        self,
        sockets: list[dict[str, object]],
        processes: list[dict[str, object]],
        limited: tuple[str, ...],
        history_seconds: int,
    ) -> dict[str, object]:
        namespace = self.proc.readlink("self", "ns", "net").value
        families = tuple(
            sorted(
                {
                    socket.AF_INET6 if row["protocol"] == "TCP6" else socket.AF_INET
                    for row in sockets
                    if str(row["protocol"]).startswith("TCP")
                    and row["networkNamespace"] == namespace
                    and not row["listening"]
                }
            )
        )
        if self.proc.root != Path("/proc"):
            counters, errors = (
                {},
                ["TCP counters are unavailable for this procfs source"],
            )
        elif families:
            counters, errors = tcp_counters(families)
        else:
            counters, errors = {}, []
        packets, capture_status = self.capture.drain()
        result = self.history.update(
            sockets,
            processes,
            counters,
            namespace,
            packets if capture_status["active"] else None,
            complete=not limited,
            history_seconds=history_seconds,
        )
        addresses = list(
            dict.fromkeys(
                [
                    str(row["remoteAddress"])
                    for row in result["flows"]
                    if row["active"] and not row["listening"]
                ]
            )
        )
        names = self.names.resolve(addresses)
        for row in result["flows"]:
            row["hostname"] = names.get(str(row["remoteAddress"]), "")
        missing_namespaces = any(
            row["networkNamespace"] != namespace for row in sockets
        )
        available_interfaces = interface_labels()
        result.update(
            {
                "capture": {
                    **capture_status,
                    "interfaces": list(available_interfaces),
                    "interfaceLabels": available_interfaces,
                },
                "resolveNames": self.names.enabled,
                "limited": list(
                    dict.fromkeys(
                        [
                            *limited,
                            *errors,
                            *(
                                [
                                    f"Name lookups are limited to {LIMITS.network_name_cache} active destination addresses"
                                ]
                                if self.names.enabled
                                and len(addresses) > LIMITS.network_name_cache
                                else []
                            ),
                            *(
                                [
                                    "Some UDP sockets share a port or have incomplete ownership; their packet rates cannot be attributed"
                                ]
                                if any(
                                    row.get("packetAttributionLimited")
                                    for row in sockets
                                )
                                else []
                            ),
                            *(
                                [
                                    "Traffic rates are unavailable in other network namespaces"
                                ]
                                if missing_namespaces
                                else []
                            ),
                            *(
                                ["UDP traffic rates need packet capture"]
                                if not capture_status["active"]
                                and any(
                                    str(row["protocol"]).startswith("UDP")
                                    for row in sockets
                                )
                                else []
                            ),
                            *(
                                ["Some sockets were omitted by the history limit"]
                                if result["omittedFlows"]
                                else []
                            ),
                        ]
                    )
                ),
            }
        )
        return result

    def configure(
        self,
        capture: bool | None = None,
        interface: str = "",
        resolve_names: bool | None = None,
    ) -> None:
        if capture is not None:
            if capture:
                self.capture.start(interface)
            else:
                self.capture.close()
            self.history.reset_rates()
        if resolve_names is not None:
            if resolve_names:
                self.names.enabled = True
            else:
                self.names.close()

    def close(self) -> None:
        self.capture.close()
        self.names.close()
        self._paused_interface = ""
