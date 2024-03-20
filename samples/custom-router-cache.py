"""
This sample application provides a customized RouterInfoCache which is used for
resolving Who-Is-Router-To-Network queries without polling the network.  If the
cache entry is not found, the normal fallback of polling the network is used and
the response is cached.
"""

import asyncio

from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from bacpypes3.debugging import ModuleLogger, DebugContents, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind

from bacpypes3.pdu import Address
from bacpypes3.basetypes import PropertyReference
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.netservice import (
    ROUTER_AVAILABLE,
    RouterInfoCache,
    NetworkAdapter,
)
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.npdu import IAmRouterToNetwork
from bacpypes3.app import Application
from bacpypes3.vendor import get_vendor_info

from redis import asyncio as aioredis
from redis.asyncio import Redis


# some debugging
_debug = 0
_log = ModuleLogger(globals())


# settings
ROUTER_INFO_CACHE_EXPIRE = 120  # seconds

# globals
app: Application
redis: Redis


#
#   CustomRouterInfoCache
#


@bacpypes_debugging
class CustomRouterInfoCache(RouterInfoCache):
    """
    This class provides a Redis implementation of the network topology.
    """

    _debug: Callable[..., None]

    # (snet, Address) -> [ dnet ]
    # router_dnets: Dict[Tuple[Optional[int], Address], List[int]]

    # (snet, dnet) -> (Address, status)
    # path_info: Dict[Tuple[Optional[int], int], Tuple[Address, int]]

    async def cache_update_reader(self, channel: aioredis.client.PubSub) -> None:
        """
        This task gets cache update messages by listening for keyspace
        notifications.
        """
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                print(f"(Reader) Message Received: {message}")

    async def get_path_info(
        self, snet: Optional[int], dnet: int
    ) -> Optional[Tuple[Address, int]]:
        """
        Given a source network and a destination network, return a tuple of
        the router address and the status of the router to the destination
        network.
        """
        if _debug:
            CustomRouterInfoCache._debug("get_path_info %r %r", snet, dnet)

        # see if it's in the process cache
        path_info = await super().get_path_info(snet, dnet)
        if path_info:
            if _debug:
                CustomRouterInfoCache._debug("    - cache hit")
            return path_info

        # encode the key
        path_info_key = f"bacnet:path:{snet}:{dnet}"

        # ask redis for address and status
        p = redis.pipeline()
        p.get(path_info_key)
        p.expire(path_info_key, ROUTER_INFO_CACHE_EXPIRE)
        path_info_blob, cache_expire = await p.execute()

        if _debug:
            CustomRouterInfoCache._debug(
                "    - path_info_blob: %r, %r", path_info_blob, cache_expire
            )
        if not path_info_blob:
            if _debug:
                CustomRouterInfoCache._debug("    - redis cache miss")
            return None

        # decode the blob
        path_info = path_info_blob.decode().split(",")
        router_address = Address(path_info[0])
        router_status = int(path_info[1])

        # update in-process cache
        await super().set_path_info(snet, dnet, router_address, router_status)

        # return the tuple
        return (router_address, router_status)

    async def set_path_info(
        self, snet: Optional[int], dnet: int, address: Address, status: int
    ) -> bool:
        """
        Given a source network and a destination network, set the router
        address and the status of the router to the destination network.
        """
        if _debug:
            CustomRouterInfoCache._debug("set_path_info %r %r", snet, dnet)

        # check with the in-process cache
        if not await super().set_path_info(snet, dnet, address, status):
            return False

        # encode the key and value
        path_info_key = f"bacnet:path:{snet}:{dnet}"
        path_info_blob = f"{address},{status}".encode()

        # tell redis
        await redis.set(path_info_key, path_info_blob, ex=ROUTER_INFO_CACHE_EXPIRE)
        return True

    async def delete_path_info(self, snet: Optional[int], dnet: int) -> bool:
        """
        Given a source network and a destination network, delete the cache
        info.  Return false if the cache has not changed.
        """
        if _debug:
            RouterInfoCache._debug("delete_path_info %r %r", snet, dnet)

        # check with the in-process cache
        if not await super().delete_path_info(snet, dnet):
            return False

        # encode the key
        path_info_key = f"bacnet:path:{snet}:{dnet}"

        # tell redis
        await redis.delete(path_info_key)
        return True

    async def get_router_dnets(
        self,
        snet: Optional[int],
        address: Address,
    ) -> Optional[Set[int]]:
        if _debug:
            CustomRouterInfoCache._debug("get_router_dnets %r %r", snet, address)

        # check in-process cache
        router_dnets = await super().get_router_dnets(snet, address)
        if router_dnets is not None:
            if _debug:
                CustomRouterInfoCache._debug("    - cache hit")
            return router_dnets

        # encode the key
        router_dnets_key = f"bacnet:dnets:{snet}:{address}"

        # ask redis for address and status
        p = redis.pipeline()
        p.get(router_dnets_key)
        p.expire(router_dnets_key, ROUTER_INFO_CACHE_EXPIRE)
        router_dnets_blob, cache_expire = await p.execute()
        if _debug:
            CustomRouterInfoCache._debug(
                "    - router_dnets_blob: %r, %r", router_dnets_blob, cache_expire
            )

        if not router_dnets_blob:
            if _debug:
                CustomRouterInfoCache._debug("    - redis cache miss")
            return None

        # encode the dnets
        router_dnets = set(int(dnet) for dnet in router_dnets_blob.decode().split(","))

        # update in-process cache
        await super().set_router_dnets(snet, address, router_dnets)

        return router_dnets

    async def set_router_dnets(
        self,
        snet: Optional[int],
        address: Address,
        dnets: Set[int],
    ) -> bool:
        if _debug:
            CustomRouterInfoCache._debug(
                "set_router_dnets %r %r %r", snet, address, dnets
            )

        # check in in-process cache
        if not await super().set_router_dnets(snet, address, dnets):
            return False

        # encode the key
        router_dnets_key = f"bacnet:dnets:{snet}:{address}"
        router_dnets_blob = (",".join(str(dnet) for dnet in dnets)).encode()

        # tell redis
        await redis.set(
            router_dnets_key, router_dnets_blob, ex=ROUTER_INFO_CACHE_EXPIRE
        )
        return True

    async def delete_router_dnets(
        self,
        snet: Optional[int],
        address: Address,
    ) -> bool:
        """
        Given a source network and router address delete the cache entry.
        Return False if the cache value has not changed.
        """
        if _debug:
            CustomRouterInfoCache._debug("delete_router_dnets %r %r", snet, address)

        # check in in-process cache
        if not await super().delete_router_dnets(snet, address):
            return False

        # encode the key
        router_dnets_key = f"bacnet:dnets:{snet}:{address}"

        # tell redis
        await redis.delete(router_dnets_key)
        return True


@bacpypes_debugging
class CmdShell(Cmd):
    """
    Command Shell
    """

    _debug: Callable[..., None]

    async def do_whois(
        self,
        address: Address = None,
        low_limit: int = None,
        high_limit: int = None,
    ) -> None:
        """
        Send a Who-Is request and wait for the response(s).

        usage: whois [ address [ low_limit high_limit ] ]
        """
        if _debug:
            CmdShell._debug("do_whois %r %r %r", address, low_limit, high_limit)

        i_ams = await app.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response("No response(s)")
        else:
            for i_am in i_ams:
                if _debug:
                    CmdShell._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    async def do_read(
        self,
        address: Address,
        object_identifier: str,
        property_identifier: Union[int, str],
    ) -> None:
        """
        Send a Read Property Request and wait for the response.

        usage: read address objid prop[indx]
        """
        if _debug:
            CmdShell._debug(
                "do_read %r %r %r", address, object_identifier, property_identifier
            )
        global app

        # get information about the device from the cache
        device_info = await app.device_info_cache.get_device_info(address)
        if _debug:
            CmdShell._debug("    - device_info: %r", device_info)

        # using the device info, look up the vendor information
        if device_info:
            vendor_info = get_vendor_info(device_info.vendor_identifier)
        else:
            vendor_info = get_vendor_info(0)
        if _debug:
            CmdShell._debug("    - vendor_info: %r", vendor_info)

        # use the vendor info to parse the object identifier
        object_identifier = vendor_info.object_identifier(object_identifier)
        if _debug:
            CmdShell._debug("    - object_identifier: %r", object_identifier)

        # use the vendor info to parse the property reference
        property_reference = PropertyReference(
            property_identifier, vendor_identifier=vendor_info.vendor_identifier
        )
        if _debug:
            CmdShell._debug("    - property_reference: %r", property_reference)

        try:
            property_value = await app.read_property(
                address,
                object_identifier,
                property_reference.propertyIdentifier,
                property_reference.propertyArrayIndex,
            )
            if _debug:
                CmdShell._debug("    - property_value: %r", property_value)
        except ErrorRejectAbortNack as err:
            if _debug:
                CmdShell._debug("    - exception: %r", err)
            property_value = err

        if isinstance(property_value, AnyAtomic):
            if _debug:
                CmdShell._debug("    - schedule objects")
            property_value = property_value.get_value()

        await self.response(str(property_value))

    async def do_wirtn(self, address: Address = None, network: int = None) -> None:
        """
        Who Is Router To Network

        usage: wirtn [ address [ network ] ]
        """
        if _debug:
            CmdShell._debug("do_wirtn %r %r", address, network)
        assert app.nse

        result_list: List[
            Tuple[NetworkAdapter, IAmRouterToNetwork]
        ] = await app.nse.who_is_router_to_network(destination=address, network=network)
        if _debug:
            CmdShell._debug("    - result_list: %r", result_list)
        if not result_list:
            raise RuntimeError("no response")

        report = []
        previous_source = None
        for adapter, i_am_router_to_network in result_list:
            if _debug:
                CmdShell._debug("    - adapter: %r", adapter)
                CmdShell._debug(
                    "    - i_am_router_to_network: %r", i_am_router_to_network
                )

            if i_am_router_to_network.npduSADR:
                npdu_source = i_am_router_to_network.npduSADR
                npdu_source.addrRoute = i_am_router_to_network.pduSource
            else:
                npdu_source = i_am_router_to_network.pduSource

            if (not previous_source) or (npdu_source != previous_source):
                report.append(str(npdu_source))
                previous_source = npdu_source

            report.append(
                "    "
                + ", ".join(
                    str(dnet) for dnet in i_am_router_to_network.iartnNetworkList
                )
            )

        await self.response("\n".join(report))

    def do_debug(
        self,
        expr: str,
    ) -> None:
        value = eval(expr)  # , globals())
        print(value)
        if hasattr(value, "debug_contents"):
            value.debug_contents()


async def main() -> None:
    global app, redis

    app = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # connect to Redis
        redis = aioredis.from_url("redis://localhost:6379/0")
        await redis.ping()

        # check for keyspace events
        notify_keyspace_events = (await redis.config_get("notify-keyspace-events"))[
            "notify-keyspace-events"
        ]
        if not all(ch in notify_keyspace_events for ch in "$sK"):
            raise RuntimeError("notify-keyspace-events")

        # build a very small stack
        console = Console()
        cmd = CmdShell()
        bind(console, cmd)

        # build an application
        app = Application.from_args(
            args,
            router_info_cache=CustomRouterInfoCache(),
        )
        if _debug:
            _log.debug("app: %r", app)

        async with redis.pubsub() as pubsub:
            if _debug:
                _log.debug("pubsub: %r", pubsub)

            await pubsub.psubscribe(
                "__keyspace@0__:bacnet:path:*", "__keyspace@0__:bacnet:dnets:*"
            )

            # task for updates
            cache_update_task = asyncio.create_task(
                app.nsap.router_info_cache.cache_update_reader(pubsub)
            )

            # run until the console is done, canceled or EOF
            await console.fini.wait()

            # all done
            cache_update_task.cancel()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
