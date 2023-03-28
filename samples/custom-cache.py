"""
Simple example.
"""

import asyncio
from typing import Callable, List, Optional

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind

from bacpypes3.pdu import Address
from bacpypes3.apdu import IAmRequest
from bacpypes3.app import Application, DeviceInfo, DeviceInfoCache
from bacpypes3.netservice import ROUTER_AVAILABLE, RouterInfo, RouterInfoCache


# some debugging
_debug = 0
_log = ModuleLogger(globals())


# globals
app: Application


@bacpypes_debugging
class CustomDeviceInfoCache(DeviceInfoCache):
    _debug: Callable[..., None]

    def iam_device_info(self, apdu: IAmRequest):
        """
        Create a device information record based on the contents of an
        IAmRequest and put it in the cache.
        """
        if _debug:
            CustomDeviceInfoCache._debug("iam_device_info %r", apdu)
        return super().iam_device_info(apdu)

    def get_device_info(self, key):
        if _debug:
            CustomDeviceInfoCache._debug("get_device_info %r", key)
        return super().get_device_info(key)

    def update_device_info(self, device_info):
        """
        The application has updated one or more fields in the device
        information record and the cache needs to be updated to reflect the
        changes.  If this is a cached version of a persistent record then this
        is the opportunity to update the database.
        """
        if _debug:
            CustomDeviceInfoCache._debug("update_device_info %r", device_info)
        return super().update_device_info(device_info)

    def acquire(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        will be using the device information.
        """
        if _debug:
            CustomDeviceInfoCache._debug("acquire %r", device_info)
        return super().acquire(device_info)

    def release(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        has finished with the device information.
        """
        if _debug:
            CustomDeviceInfoCache._debug("release %r", device_info)
        return super().release(device_info)


@bacpypes_debugging
class CustomRouterInfoCache(RouterInfoCache):
    _debug: Callable[..., None]

    def get_router_info(self, snet: Optional[int], dnet: int) -> Optional[RouterInfo]:
        if _debug:
            CustomRouterInfoCache._debug("get_router_info ...")
        return None

    def update_router_info(
        self,
        snet: Optional[int],
        address: Address,
        dnets: List[int],
        status: int = ROUTER_AVAILABLE,
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_router_info ...")
        return

    def update_router_status(self, snet: int, address: Address, status: int) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_router_status ...")
        return

    def delete_router_info(
        self,
        snet: int,
        address: Optional[Address] = None,
        dnets: Optional[List[int]] = None,
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug("delete_router_info ...")
        return

    def update_source_network(self, old_snet: int, new_snet: int) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_source_network ...")
        return


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

    async def do_show(
        self,
        thing: str,
    ) -> None:
        """
        Show internal data structures for device and routing information.

        usage: show ( dinfo | rinfo )
        """
        if _debug:
            CmdShell._debug("do_show %r", thing)
        global app

        if thing == "dinfo":
            app.device_info_cache.debug_contents()
        elif thing == "rinfo":
            app.nsap.router_info_cache.debug_contents()


async def main() -> None:
    global app

    app = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = CmdShell()
        bind(console, cmd)

        # build an application
        app = Application.from_args(
            args,
            device_info_cache=CustomDeviceInfoCache(),
            # router_info_cache=CustomRouterInfoCache(),
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
