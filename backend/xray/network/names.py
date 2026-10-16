from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
import time

from xray.config import LIMITS, TIMING
from xray.system.commands import CommandRunner


class DestinationNames:
    """Opt-in, bounded reverse lookups that never block snapshot collection."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner
        self.enabled = False
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._pending: dict[str, Future[str]] = {}
        self._pool: ThreadPoolExecutor | None = None

    def _lookup(self, address: str) -> str:
        result = self.runner.run(
            ["getent", "hosts", address], timeout_seconds=TIMING.network_name_seconds
        )
        if result.returncode == 0 and not result.output_limited:
            fields = result.stdout.split()
            if len(fields) >= 2:
                return fields[1][:253]
        return ""

    def resolve(self, addresses: list[str]) -> dict[str, str]:
        if not self.enabled:
            return {}
        addresses = list(dict.fromkeys(addresses))[: LIMITS.network_name_cache]
        now = time.monotonic()
        for address, future in list(self._pending.items()):
            if future.done():
                try:
                    name = future.result()
                except (OSError, ValueError):
                    name = ""
                self._cache[address] = (now, name)
                del self._pending[address]
        for address in addresses:
            cached = self._cache.get(address)
            if cached and now - cached[0] < TIMING.network_name_ttl_seconds:
                self._cache.move_to_end(address)
            elif address not in self._pending and len(self._pending) < 2:
                if self._pool is None:
                    self._pool = ThreadPoolExecutor(
                        max_workers=2, thread_name_prefix="xray-dns"
                    )
                self._pending[address] = self._pool.submit(self._lookup, address)
        while len(self._cache) > LIMITS.network_name_cache:
            self._cache.popitem(last=False)
        return {
            address: self._cache[address][1]
            for address in addresses
            if address in self._cache
        }

    def close(self) -> None:
        self.enabled = False
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        self._pending = {}
        self._cache.clear()
