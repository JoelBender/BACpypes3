#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RouterInfoCache concurrency
--------------------------------

Regression tests for a race in ``RouterInfoCache.update_path_info`` that
was hit in the field when two ``I-Am-Router-To-Network`` messages arrived
close together.  The mutator does a read/modify/write on both
``router_dnets`` and ``path_info`` and awaits between the reads and the
writes; two coroutines processing concurrent I-Am-RtN updates for the
same source network could interleave and leave ``path_info`` pointing at
a router whose ``router_dnets`` no longer contained that dnet.  The next
update that tried to move the dnet raised::

    RuntimeError: routing cache: dnet 32768 not in {16384, 3073, ...}

The fix serializes the mutators with an ``asyncio.Lock``.  The default
in-memory cache doesn't actually yield between its ``get_*`` and
``set_*`` calls, so ``asyncio.gather`` on the built-in cache runs each
call to completion sequentially and the race can't be observed there --
even without the lock.  It shows up in the field only because a real
async cache (e.g. a Redis-backed subclass) *does* yield between the read
and the write.

To reproduce the field failure deterministically we do two things:

* ``BarrieredCache`` forces a two-reader rendezvous inside
  ``get_router_dnets`` so two concurrent updaters snapshot the same
  pre-write state -- exactly what happens with a real network
  round-trip.  ``test_race_reproduces_without_lock`` shows that with
  the class's lock replaced by a no-op, that interleave corrupts the
  cache or raises the ``dnet X not in {...}`` error -- proving the
  race is real (not just a story about what could happen).

* ``test_lock_serializes_yielding_cache`` uses a plainer subclass whose
  ``get_*`` methods just yield with ``asyncio.sleep(0)``, modeling a
  real network-backed store without any custom scheduling.  Without
  the lock, ``asyncio.gather`` on those coroutines interleaves the
  read/modify/write and the final ``router_dnets`` loses entries;
  with the lock, each ``update_path_info`` runs to completion before
  the next starts and the final state is consistent.
"""

import asyncio
from typing import Callable, Optional, Set

import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.netservice import RouterInfoCache

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class BarrieredCache(RouterInfoCache):
    """A cache whose ``get_router_dnets`` reads for a specified address
    force a two-reader rendezvous: both coroutines snapshot the value
    (as any real network-backed cache would, before the GET reply comes
    back) and only then wait for each other before returning.  This
    deterministically produces the "both readers saw the same pre-write
    value" interleave that was corrupting the field cache."""

    _debug: Callable[..., None]

    def __init__(self) -> None:
        super().__init__()
        self._rendezvous_address: Optional[Address] = None
        self._first_reader: Optional[asyncio.Future[None]] = None

    def arm_rendezvous(self, address: Address) -> None:
        """Arm a two-reader rendezvous on the next two
        ``get_router_dnets`` calls that ask for ``address``."""
        self._rendezvous_address = address
        self._first_reader = None

    async def get_router_dnets(
        self, snet: Optional[int], address: Address
    ) -> Optional[Set[int]]:
        if _debug:
            BarrieredCache._debug("get_router_dnets %r %r", snet, address)

        # snapshot BEFORE waiting so both readers see the same pre-write
        # value (a real Redis GET would return this once its round-trip
        # is in flight, regardless of what other clients then write)
        snapshot = await super().get_router_dnets(snet, address)

        rendezvous = self._rendezvous_address
        if rendezvous is not None and address == rendezvous:
            loop = asyncio.get_event_loop()
            if self._first_reader is None:
                # first reader parks; second reader will wake it
                self._first_reader = loop.create_future()
                await self._first_reader
            else:
                # second reader releases the first and disarms so a
                # third call (if any) doesn't try to park again
                self._first_reader.set_result(None)
                self._rendezvous_address = None
        return snapshot


class _NullLock:
    async def __aenter__(self) -> "_NullLock":
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass


class UnlockedBarrieredCache(BarrieredCache):
    """Same rendezvous behavior but with the cache's serialization lock
    replaced by a no-op -- used only by the sanity-check test that
    proves the barrier is exercising the bug."""

    def _get_lock(self) -> _NullLock:  # type: ignore[override]
        return _NullLock()


def check_invariant(cache: RouterInfoCache) -> None:
    """Every path_info entry must be backed by a matching router_dnets
    entry, and vice versa -- otherwise a later update_path_info will
    raise `dnet X not in {...}` when it tries to move a dnet off a
    router that no longer claims it."""
    for (snet, dnet), (router_address, _status) in cache.path_info.items():
        router_dnets = cache.router_dnets.get((snet, router_address))
        assert router_dnets is not None, (
            f"path_info[({snet}, {dnet})] points at router {router_address}"
            f" but that router has no router_dnets entry"
        )
        assert dnet in router_dnets, (
            f"path_info[({snet}, {dnet})] points at router {router_address}"
            f" whose router_dnets is {router_dnets} (missing {dnet})"
        )

    for (snet, router_address), dnets in cache.router_dnets.items():
        for dnet in dnets:
            path_info = cache.path_info.get((snet, dnet))
            assert path_info is not None, (
                f"router_dnets[({snet}, {router_address})] claims dnet"
                f" {dnet} but there is no path_info for it"
            )
            assert path_info[0] == router_address, (
                f"router_dnets[({snet}, {router_address})] claims dnet"
                f" {dnet} but path_info points at {path_info[0]}"
            )


@bacpypes_debugging
class TestRouterInfoCacheRace:
    _debug: Callable[..., None]

    async def test_race_reproduces_without_lock(self) -> None:
        """Sanity check that the barrier reproduces the field bug:
        without the class's serialization lock (a no-op stand-in), the
        forced interleave must either corrupt the cache or raise the
        ``dnet X not in {...}`` error.  If this passed silently, the
        other two tests wouldn't be proving anything about the lock."""
        if _debug:
            TestRouterInfoCacheRace._debug("test_race_reproduces_without_lock")

        cache = UnlockedBarrieredCache()
        snet = 1
        r1 = Address("1:1")
        r2 = Address("1:2")
        r3 = Address("1:3")

        await cache.update_path_info(snet, r1, {10, 20})
        cache.arm_rendezvous(r1)

        raised: Optional[BaseException] = None
        try:
            await asyncio.gather(
                cache.update_path_info(snet, r2, {10}),
                cache.update_path_info(snet, r3, {20}),
            )
        except RuntimeError as exc:
            raised = exc

        if raised is not None:
            assert "not in" in str(raised)
        else:
            with pytest.raises(AssertionError):
                check_invariant(cache)

    async def test_lock_serializes_yielding_cache(self) -> None:
        """A cache subclass whose ``get_*`` methods yield -- modeling a
        real network-backed store -- must still produce a consistent
        final state under concurrent updates.  This is the scenario that
        fails in the field: an in-memory cache doesn't yield, so the
        built-in one runs each ``update_path_info`` to completion before
        the next starts even under ``asyncio.gather`` and the race
        can't be observed there; a subclass that awaits a real
        round-trip exposes it.

        Without the lock, the interleaved reads of ``router_dnets`` all
        see the same pre-write snapshot and the last write wins -- the
        final ``router_dnets`` set holds only one of the announced dnets
        and the ``path_info`` entries for the rest dangle.  With the
        lock, each ``update_path_info`` runs to completion before the
        next starts."""
        if _debug:
            TestRouterInfoCacheRace._debug("test_lock_serializes_yielding_cache")

        class YieldingCache(RouterInfoCache):
            async def get_router_dnets(self, snet, address):
                await asyncio.sleep(0)
                return await super().get_router_dnets(snet, address)

            async def get_path_info(self, snet, dnet):
                await asyncio.sleep(0)
                return await super().get_path_info(snet, dnet)

        cache = YieldingCache()
        snet = 1
        r = Address("1:1")

        # ten concurrent I-Am-RtN messages from the same router, each
        # announcing a different dnet.  The final state must include
        # every announced dnet.
        await asyncio.gather(
            *[cache.update_path_info(snet, r, {n}) for n in range(1, 11)]
        )

        check_invariant(cache)
        assert cache.router_dnets[(snet, r)] == set(range(1, 11))
        for n in range(1, 11):
            assert cache.path_info[(snet, n)][0] == r
