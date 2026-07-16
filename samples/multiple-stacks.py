"""
This application is given a JSON configuration file which contains an array
of applications, each of which is an array of objects.  All of the applications
run simultaneously.  The sample JSON file `multiple-stacks.json` has IPv4
network port objects with the same address but different ports.

It also presents a Cmd prompt with the CmdDebugging mixin class to provide
support for additional debugging commands that will be "attached" to the
first application in the array.
"""

import sys
import asyncio
import io

from typing import Callable, List, Optional, Tuple

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import JSONArgumentParser

from bacpypes3.console import Console
from bacpypes3.cmd import Cmd, CmdDebugging
from bacpypes3.comm import bind

from bacpypes3.pdu import Address
from bacpypes3.npdu import IAmRouterToNetwork
from bacpypes3.netservice import NetworkAdapter
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
applications: List[Application] = []
app: Application


@bacpypes_debugging
class CmdShell(Cmd, CmdDebugging):
    _debug: Callable[..., None]

    async def do_app(self, app_index: Optional[int] = None) -> None:
        """
        usage: app [ n ]
        """
        global app

        if app_index is None:
            for i, some_app in enumerate(applications):
                star = "*" if app is some_app else " "
                print(f"{star} {i}: {some_app.device_object.objectIdentifier}")
        else:
            app = applications[app_index]
            if _debug:
                CmdShell._debug("app: %r", app)

    async def do_nsap(self) -> None:
        """
        usage: nsap
        """
        if _debug:
            CmdShell._debug("nsap")

        report = io.StringIO()
        app.nsap.debug_contents(file=report)

        for k, v in app.nsap.router_info_cache.routers.items():
            report.write(f"        {k}: {{\n")
            for k2, v2 in v.items():
                report.write(f"            {k2}: {v2}\n")
                v2.debug_contents(indent=4, file=report)
            report.write("        }\n")

        await self.response(report.getvalue())

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

    async def do_iartn(self, address: Address = None, network: int = None) -> None:
        """
        I Am Router To Network

        usage: iartn [ address [ network ] ]
        """
        if _debug:
            CmdShell._debug("do_iartn %r %r", address, network)
        assert app.nse

        await app.nse.i_am_router_to_network(destination=address, network=network)

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


async def main() -> None:
    global applications, app, iut

    try:
        console = None
        args = JSONArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        for app_settings in settings.json["applications"]:
            # build an application
            app = Application.from_json(app_settings)
            if _debug:
                _log.debug("app: %r", app)
            applications.append(app)
        app = applications[0]

        # build a very small stack
        console = Console()
        cmd = CmdShell()
        bind(console, cmd)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
