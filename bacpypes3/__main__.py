"""
Command Shell
"""

import sys
import asyncio
import re
import json

from typing import Callable, List, Optional, Tuple

import bacpypes3
from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address, IPv4Address
from bacpypes3.comm import bind

from bacpypes3.primitivedata import Null, CharacterString, ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.npdu import IAmRouterToNetwork, InitializeRoutingTableAck
from bacpypes3.object import get_vendor_info
from bacpypes3.app import Application
from bacpypes3.netservice import NetworkAdapter

# for BVLL services
from bacpypes3.ipv4.bvll import Result as IPv4BVLLResult
from bacpypes3.ipv4.service import BVLLServiceAccessPoint, BVLLServiceElement

# for serializing the configuration
from bacpypes3.json import sequence_to_json

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# globals
app: Application
bvll_ase: BVLLServiceElement

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")


@bacpypes_debugging
class CmdShell(Cmd):
    """
    Basic command shell when executing the module.
    """

    _debug: Callable[..., None]

    async def do_read(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
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

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        try:
            property_value = await app.read_property(
                address, object_identifier, property_identifier, property_array_index
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

    async def do_write(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value: str,
        priority: Optional[int] = None,
    ) -> None:
        """
        Send a Write Property Request and wait for the acknowledgement.

        usage: write address objid prop[indx] value [ priority ]
        """
        if _debug:
            CmdShell._debug(
                "do_write %r %r %r %r %r",
                address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )
        global app

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        if value == "null":
            if priority is None:
                raise ValueError("null only for overrides")
            value = Null(())

        try:
            response = await app.write_property(
                address,
                object_identifier,
                property_identifier,
                value,
                property_array_index,
                priority,
            )
            if _debug:
                CmdShell._debug("    - response: %r", response)
            assert response is None

        except ErrorRejectAbortNack as err:
            if _debug:
                CmdShell._debug("    - error/reject/abort: %r", err)
            await self.response(str(err))
        except Exception as err:
            if _debug:
                CmdShell._debug("    - exception: %r", err)
            await self.response(str(err))

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

    async def do_iam(
        self,
        address: Address = None,
    ) -> None:
        """
        Send an I-Am request, no response.

        usage: iam [ address ]
        """
        if _debug:
            CmdShell._debug("do_iam %r", address)

        app.i_am(address)

    async def do_whohas(
        self,
        *args: str,
    ) -> None:
        """
        Send a Who-Has request, an objid or objname (or both) is required.

        usage: whohas [ low_limit high_limit ] [ objid ] [ objname ] [ address ]
        """
        if _debug:
            CmdShell._debug("do_whohas %r", args)

        if not args:
            raise RuntimeError("object-identifier or object-name expected")
        args = list(args)

        if args[0].isdigit():
            low_limit = int(args.pop(0))
        else:
            low_limit = None
        if args[0].isdigit():
            high_limit = int(args.pop(0))
        else:
            high_limit = None
        if _debug:
            CmdShell._debug(
                "    - low_limit, high_limit: %r, %r", low_limit, high_limit
            )

        if not args:
            raise RuntimeError("object-identifier expected")
        try:
            object_identifier = ObjectIdentifier(args[0])
            del args[0]
        except ValueError:
            object_identifier = None
        if _debug:
            CmdShell._debug("    - object_identifier: %r", object_identifier)

        if len(args) == 0:
            object_name = address = None
        elif len(args) == 2:
            object_name = args[0]
            address = Address(args[1])
        elif len(args) == 1:
            try:
                address = Address(args[0])
                object_name = None
            except ValueError:
                object_name = args[0]
                address = None
        else:
            raise RuntimeError("unrecognized arguments")
        if _debug:
            CmdShell._debug("    - object_name: %r", object_name)
            CmdShell._debug("    - address: %r", address)

        i_haves = await app.who_has(
            low_limit, high_limit, object_identifier, object_name, address
        )
        if not i_haves:
            await self.response("No response(s)")
        else:
            for i_have in i_haves:
                if _debug:
                    CmdShell._debug("    - i_have: %r", i_have)
                await self.response(
                    f"{i_have.deviceIdentifier[1]} {i_have.objectIdentifier} {i_have.objectName!r}"
                )

    async def do_ihave(
        self,
        object_identifier: ObjectIdentifier,
        object_name: CharacterString,
        address: Address = None,
    ) -> None:
        """
        Send an I-Have request.

        usage: ihave objid objname [ address ]
        """
        if _debug:
            CmdShell._debug(
                "do_ihave %r %r %r", object_identifier, object_name, address
            )

        app.i_have(object_identifier, object_name, address)

    async def do_rpm(
        self,
        address: Address,
        *args: str,
    ) -> None:
        """
        Read Property Multiple

        usage: rpm address ( objid ( prop [ indx ] )... )...
        """
        if _debug:
            CmdShell._debug("do_rpm %r %r", address, args)
        args = list(args)

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

        parameter_list = []
        while args:
            # get the object identifier and using the vendor information, look
            # up the class
            object_identifier = vendor_info.object_identifier(args.pop(0))
            object_class = vendor_info.get_object_class(object_identifier[0])
            if not object_class:
                await self.response(f"unrecognized object type: {object_identifier}")
                return

            # save this as a parameter
            parameter_list.append(object_identifier)

            while args:
                # now get the property type from the class
                property_identifier = vendor_info.property_identifier(args.pop(0))
                if _debug:
                    CmdShell._debug(
                        "    - property_identifier: %r", property_identifier
                    )
                if property_identifier not in (
                    PropertyIdentifier.all,
                    PropertyIdentifier.required,
                    PropertyIdentifier.optional,
                ):
                    property_type = object_class.get_property_type(property_identifier)
                    if _debug:
                        CmdShell._debug("    - property_type: %r", property_type)
                    if not property_type:
                        await self.response(
                            f"unrecognized property: {property_identifier}"
                        )
                        return

                # save this as a parameter
                parameter_list.append(property_identifier)

                # check for a property array index
                if args and args[0].isdigit():
                    property_array_index = int(args.pop(0))
                    # save this as a parameter
                    parameter_list.append(property_array_index)

                # crude check to see if the next thing is an object identifier
                if args and ((":" in args[0]) or ("," in args[0])):
                    break

        if not parameter_list:
            await self.response("object identifier expected")
            return

        try:
            response = await app.read_property_multiple(address, parameter_list)
            if _debug:
                CmdShell._debug("    - response: %r", response)
        except ErrorRejectAbortNack as err:
            if _debug:
                CmdShell._debug("    - exception: %r", err)
            await self.response(str(err))
            return

        # dump out the results
        for (
            object_identifier,
            property_identifier,
            property_array_index,
            property_value,
        ) in response:
            if property_array_index is not None:
                await self.response(
                    f"{object_identifier} {property_identifier}[{property_array_index}] {property_value}"
                )
            else:
                await self.response(
                    f"{object_identifier} {property_identifier} {property_value}"
                )

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

    async def do_irt(self, address: Address = None) -> None:
        """
        Initialize Routing Table

        usage: irt [ address ]
        """
        if _debug:
            CmdShell._debug("do_irt %r", address)
        assert app.nse

        result_list: List[
            Tuple[NetworkAdapter, InitializeRoutingTableAck]
        ] = await app.nse.initialize_routing_table(destination=address)
        if _debug:
            CmdShell._debug("    - result_list: %r", result_list)
        if not result_list:
            raise RuntimeError("no response")

        report = []
        previous_source = None
        for adapter, initialize_routing_table_ack in result_list:
            if _debug:
                CmdShell._debug("    - adapter: %r", adapter)
                CmdShell._debug(
                    "    - initialize_routing_table_ack: %r",
                    initialize_routing_table_ack,
                )

            if (not previous_source) or (
                initialize_routing_table_ack.pduSource != previous_source
            ):
                report.append(str(initialize_routing_table_ack.pduSource))
                previous_source = initialize_routing_table_ack.pduSource

            for routing_table_entry in initialize_routing_table_ack.irtaTable:
                report.append(
                    f"    {routing_table_entry.rtDNET:-5} {routing_table_entry.rtPortID}"
                )

        await self.response("\n".join(report))

    async def do_rbdt(
        self,
        address: IPv4Address,
    ) -> None:
        """
        Read Broadcast Distribution Table

        usage: rbdt address
        """
        if _debug:
            CmdShell._debug("do_rbdt %r", address)
        if not bvll_ase:
            raise NotImplementedError("IPv4 only")

        try:
            result_list: Optional[
                List[IPv4Address]
            ] = await bvll_ase.read_broadcast_distribution_table(address)
            if result_list is None:
                await self.response("No response")
            else:
                report = []
                for bdt_entry in result_list:
                    if _debug:
                        CmdShell._debug(
                            "    - bdt_entry: %r",
                            bdt_entry,
                        )
                    report.append(f"    {bdt_entry}/{bdt_entry.netmask}")

                await self.response("\n".join(report))
        except IPv4BVLLResult as err:
            await self.response(f"bvll error: {err.bvlciResultCode}")

    async def do_wbdt(
        self,
        address: IPv4Address,
        *args: IPv4Address,
    ) -> None:
        """
        Write Broadcast Distribution Table

        usage: wbdt address [ address ... ]
        """
        if _debug:
            CmdShell._debug("do_wbdt %r %r", address, args)
        if not bvll_ase:
            raise NotImplementedError("IPv4 only")

        try:
            await bvll_ase.write_broadcast_distribution_table(address, args)
        except IPv4BVLLResult as err:
            await self.response(f"bvll error: {err.bvlciResultCode}")

    async def do_rfdt(
        self,
        address: IPv4Address,
    ) -> None:
        """
        Read Foreign Device Table

        usage: rfdt address
        """
        if _debug:
            CmdShell._debug("do_rfdt %r", address)
        if not bvll_ase:
            raise NotImplementedError("IPv4 only")

        try:
            result_list = await bvll_ase.read_foreign_device_table(address)
            if result_list is None:
                await self.response("No response")
            else:
                report = []
                for fdt_entry in result_list:
                    if _debug:
                        CmdShell._debug(
                            "    - fdt_entry: %r",
                            fdt_entry,
                        )
                    report.append(
                        f"    {fdt_entry.fdAddress} {fdt_entry.fdTTL}s, {fdt_entry.fdRemain}s remain"
                    )

                await self.response("\n".join(report))
        except IPv4BVLLResult as err:
            await self.response(f"bvll error: {err.bvlciResultCode}")

    async def do_config(
        self,
        format: str,
    ) -> None:
        """
        Display the configuration as JSON, YAML, or RDF

        usage: config ( json | yaml | rdf )
        """
        if _debug:
            CmdShell._debug("do_config %r", format)

        object_list = []
        for obj in app.objectIdentifier.values():
            if _debug:
                CmdShell._debug("    - obj: %r", obj)
            object_list.append(sequence_to_json(obj))

        # make a config dict
        config_dict = {"BACpypes": dict(settings), "application": object_list}

        if format == "json":
            json.dump(config_dict, sys.stdout, sort_keys=True, indent=4)

        elif format == "yaml":
            try:
                import yaml  # type: ignore[import]

                yaml.dump(config_dict, sys.stdout)
            except ImportError as err:
                if _debug:
                    CmdShell._debug("    - yaml error: %r", err)
                sys.stderr.write("no yaml\n")

        elif format == "rdf":
            try:
                from rdflib import Graph, BNode, Namespace, RDF, Literal
                from bacpypes3.rdf.util import BACnetNS, sequence_to_graph

                g = Graph()
                g.bind("bacnet", BACnetNS)

                BACpypesNS = Namespace("https://github.com/JoelBender/bacpypes3/")
                g.bind("bacpypes", BACpypesNS)

                app_node = BNode()
                g.add((app_node, RDF.type, BACpypesNS.Application))
                g.add((app_node, RDF.type, BACnetNS.Device))

                # add the settings
                for k, v in settings.items():
                    if v:
                        if isinstance(v, list):
                            for vv in v:
                                g.add((app_node, BACpypesNS[k], Literal(vv)))
                        else:
                            g.add((app_node, BACpypesNS[k], Literal(v)))

                # serialize it as a blank node
                for obj in app.objectIdentifier.values():
                    if _debug:
                        CmdShell._debug("    - obj: %r", obj)

                    obj_node = BNode()
                    g.add((app_node, BACnetNS.hasObject, obj_node))

                    sequence_to_graph(obj, obj_node, graph=g)

                sys.stderr.write(g.serialize(format="turtle"))

            except ImportError as err:
                if _debug:
                    CmdShell._debug("    - rdflib error: %r", err)
                sys.stderr.write("no rdf\n")

        else:
            raise ValueError("format")


async def main() -> None:
    global app, bvll_ase

    app = None
    bvll_ase = None
    try:
        parser = SimpleArgumentParser(prog="bacpypes3")
        parser.add_argument(
            "-v",
            "--version",
            help="print the version and exit",
            action="store_true",
            default=None,
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        if args.version:
            print(f"bacpypes3 {bacpypes3.__version__} {bacpypes3.__file__}")

            try:
                import ifaddr

                print(f"ifaddr {ifaddr.__file__}")
            except ImportError:
                print("ifaddr not installed")

            try:
                import rdflib

                print(f"rdflib {rdflib.__version__} {rdflib.__file__}")
            except ImportError:
                print("yaml not installed")

            try:
                import websockets

                print(f"websockets {websockets.__version__} {websockets.__file__}")
            except ImportError:
                print("websockets not installed")

            try:
                import yaml

                print(f"pyyaml {yaml.__version__} {yaml.__file__}")
            except ImportError:
                print("yaml not installed")

            return

        # build a very small stack
        console = Console()
        cmd = CmdShell()
        bind(console, cmd)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # pick out the BVLL service access point from the local adapter
        local_adapter = app.nsap.local_adapter
        if _debug:
            _log.debug("local_adapter: %r", local_adapter)
        bvll_sap = local_adapter.clientPeer

        # only IPv4 for now
        if isinstance(bvll_sap, BVLLServiceAccessPoint):
            if _debug:
                _log.debug("bvll_sap: %r", bvll_sap)

            # create a BVLL application service element
            bvll_ase = BVLLServiceElement()
            if _debug:
                _log.debug("bvll_ase: %r", bvll_ase)

            bind(bvll_ase, bvll_sap)

        # wait until the user is done
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
