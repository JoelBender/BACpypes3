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
#   CustomRouterInfo
#


class CustomRouterInfo(DebugContents):
    """
    These objects are routing information records that map router
    addresses with destination networks.
    """

    _debug_contents: Tuple[str, ...] = ("snet", "address", "dnets")

    snet: Optional[int]
    address: Address
    dnets: Dict[int, int]

    def __init__(self, snet: Optional[int], address: Address) -> None:
        self.snet = snet  # source network
        self.address = address  # address of the router
        self.dnets = {}  # {dnet: status}

    def set_status(self, dnets, status) -> None:
        """Change the status of each of the DNETS."""
        for dnet in dnets:
            self.dnets[dnet] = status

    def encode(self) -> bytes:
        if _debug:
            CustomRouterInfo._debug("encode")

        contents = ",".join(
            [
                str(self.snet),
                str(self.address),
                ".".join(f"{k}:{v}" for k, v in self.dnets.items()),
            ]
        )
        if _debug:
            CustomRouterInfo._debug("    - contents: %r", contents)

        return contents.encode()

    @classmethod
    def decode(cls, blob: bytes) -> "CustomRouterInfo":
        if _debug:
            CustomRouterInfo._debug("decode %r", blob)

        contents = blob.decode().split(",", 2)
        if _debug:
            CustomRouterInfo._debug("    - contents: %r", contents)

        snet = int(contents[0])
        address = Address(contents[1])
        dnets = {}
        for kv in contents[2].split(","):
            k, v = kv.split(":")
            dnets[int(k)] = int(v)

        router_info = cls(snet, address)
        router_info.dnets = dnets

        return router_info


#
#   CustomRouterInfoCache
#


@bacpypes_debugging
class CustomRouterInfoCache(DebugContents):
    """
    This class provides a Redis implementation of the network topology.
    """

    _debug: Callable[..., None]

    # (snet, Address) -> [ dnet ]
    # router_dnets: Dict[Tuple[Optional[int], Address], List[int]]

    # (snet, dnet) -> (Address, status)
    # path_info: Dict[Tuple[Optional[int], int], Tuple[Address, int]]

    def __init__(self):
        if _debug:
            CustomRouterInfoCache._debug("__init__")

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
            return None

        # decode the blob
        path_info = path_info_blob.decode().split(",")
        router_address = Address(path_info[0])
        router_status = int(path_info[1])

        # return the tuple
        return (router_address, router_status)

    async def set_path_info(
        self, snet: Optional[int], dnet: int, address: Address, status: int
    ) -> None:
        """
        Given a source network and a destination network, set the router
        address and the status of the router to the destination network.
        """
        if _debug:
            CustomRouterInfoCache._debug("get_path_info %r %r", snet, dnet)

        # encode the key and value
        path_info_key = f"bacnet:path:{snet}:{dnet}"
        path_info_blob = f"{address},{status}".encode()

        # tell redis
        await redis.set(path_info_key, path_info_blob, ex=ROUTER_INFO_CACHE_EXPIRE)

    async def get_router_dnets(
        self,
        snet: Optional[int],
        address: Address,
    ) -> Optional[List[int]]:
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
            return None

        return list(int(dnet) for dnet in router_dnets_blob.decode.split(","))

    async def set_router_dnets(
        self,
        snet: Optional[int],
        address: Address,
        dnets: List[int],
    ) -> Optional[List[int]]:
        # encode the key
        router_dnets_key = f"bacnet:dnets:{snet}:{address}"
        router_dnets_blob = (",".join(str(dnet) for dnet in dnets)).encode()

        # tell redis
        await redis.set(
            router_dnets_key, router_dnets_blob, ex=ROUTER_INFO_CACHE_EXPIRE
        )

    async def update_path_info(
        self,
        snet: Optional[int],
        address: Address,
        dnets: List[int],
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug(
                "update_path_info %r %r %r", snet, address, dnets
            )

        # ask redis for list of dnets
        router_dnets = await self.get_router_dnets(snet, address)
        if _debug:
            CustomRouterInfoCache._debug("    - router_dnets: %r", router_dnets)

        # create/update the list of dnets for this router
        new_dnets: Set[int] = set(dnets)
        if not router_dnets:
            if _debug:
                CustomRouterInfoCache._debug("    - new router: %r", address)
            router_dnets = list()
        else:
            # just look for new dnets related to this router
            new_dnets -= set(router_dnets)
            if not new_dnets:
                # if there are no new dnets then the router_address is already
                # correct and there are no others that need updating
                if _debug:
                    CustomRouterInfoCache._debug("    - no changes")
                return
        if _debug:
            CustomRouterInfoCache._debug("    - router_dnets: %r", router_dnets)
            CustomRouterInfoCache._debug("    - new_dnets: %r", new_dnets)

        # start a pipeline
        # p: redis.client.Pipeline = redis.pipeline()

        # get the addresses of the routers that used to be the router to
        # any of the dnets
        for dnet in new_dnets:
            path_info = self.get_path_info(snet, dnet)
            if not path_info:
                continue
            if _debug:
                CustomRouterInfoCache._debug("    - old path: %r", path_info)

            old_router_address = path_info[0]
            old_router_dnets = await self.get_router_dnets(snet, old_router_address)
            if old_router_dnets is None:
                raise RuntimeError(f"routing cache: no router {old_router_address}")
            if dnet not in old_router_dnets:
                raise RuntimeError(
                    f"routing cache: dnet {dnet} not in {old_router_dnets}"
                )

            # no longer a path through old router
            old_router_dnets.remove(dnet)
            await self.set_router_dnets(snet, old_router_address, old_router_dnets)

            # if there are no more dnets remove the router reference
            if not old_router_dnets:
                if _debug:
                    CustomRouterInfoCache._debug(
                        "    - router abandoned: %r", old_router_address
                    )
                old_router_dnets_key = f"bacnet:dnets:{snet}:{old_router_address}"
                await redis.delete(old_router_dnets_key)

        # extend the existing list with the new ones and set the path
        router_dnets.extend(list(new_dnets))

        await self.set_router_dnets(snet, address, router_dnets)
        for dnet in new_dnets:
            await self.set_path_info(snet, dnet, address, ROUTER_AVAILABLE)

        # run the pipeline
        # await p.execute()

    async def delete_path_info(
        self,
        snet: int,
        address: Optional[Address] = None,
        dnets: Optional[List[int]] = None,
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug(
                "delete_path_info %r %r %r", snet, address, dnets
            )

        if address is not None:
            # get the list of dnets for this router
            router_dnets = await self.get_router_dnets(snet, address)
            if router_dnets is None:
                if _debug:
                    CustomRouterInfoCache._debug("    - no known dnets")
                return

            # remove the path info and the dnet from the router dnets
            for dnet in dnets or router_dnets:
                path_info_key = f"bacnet:path:{snet}:{dnet}"
                await redis.delete(path_info_key)
                router_dnets.remove(dnet)

            # if there are no more dnets remove the router reference
            if not router_dnets:
                if _debug:
                    CustomRouterInfoCache._debug("    - router abandoned: %r", address)

                router_dnets_key = f"bacnet:dnets:{snet}:{address}"
                await redis.delete(router_dnets_key)
            else:
                await self.set_router_dnets(snet, address, router_dnets)

        else:
            if dnets is None:
                raise RuntimeError("inconsistent parameters")

            # start a pipeline
            # p = redis.pipeline()
            # router_dnets_cache: Dict[Address, List[int]] = {}

            for dnet in dnets:
                path_info = await self.get_path_info(snet, dnet)
                if not path_info:
                    continue

                router_address, _ = path_info

                # get the list of dnets for this router
                router_dnets = await self.get_router_dnets(snet, router_address)
                if router_dnets is None:
                    raise RuntimeError("routing cache conflict")
                if dnet not in router_dnets:
                    raise RuntimeError("routing cache conflict")

                # delete the path information
                path_info_key = f"bacnet:path:{snet}:{dnet}"
                await redis.delete(path_info_key)
                router_dnets.remove(dnet)

                # if there are no more dnets remove the router reference
                if not router_dnets:
                    if _debug:
                        CustomRouterInfoCache._debug(
                            "    - router abandoned: %r", address
                        )
                    router_dnets_key = f"bacnet:dnets:{snet}:{address}"
                    await redis.delete(router_dnets_key)
                else:
                    await self.set_router_dnets(snet, router_address, router_dnets)

            # flush the cache and execute the pipeline
            # await p.execute()

    async def update_router_status(
        self, snet: int, address: Address, status: int
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug(
                "update_router_status %r %r %r", snet, address, status
            )

        # get the list of dnets for this router
        router_dnets = await self.get_router_dnets(snet, address)
        if router_dnets is None:
            if _debug:
                CustomRouterInfoCache._debug("    - no known dnets")
            return

        # save the status
        for dnet in router_dnets:
            await self.set_path_info(snet, dnet, address, status)

    async def update_source_network(
        self, old_snet: Optional[int], new_snet: int
    ) -> None:
        """
        This method is called when the network number for an adapter becomes
        known, the Network-Number-Is service.
        """
        if _debug:
            CustomRouterInfoCache._debug(
                "update_source_network %r %r", old_snet, new_snet
            )

        router_dnets_items = list(self.router_dnets.items())
        for (snet, router_address), router_dnets in router_dnets_items:
            if snet == old_snet:
                # out with the old, in with the new
                del self.router_dnets[(old_snet, router_address)]
                self.router_dnets[(new_snet, router_address)] = router_dnets

                for dnet in router_dnets:
                    path_info = self.path_info[(old_snet, dnet)]
                    del self.path_info[(old_snet, dnet)]
                    self.path_info[(new_snet, dnet)] = path_info


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

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
