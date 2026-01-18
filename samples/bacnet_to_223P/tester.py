from pathlib import Path
from rdflib import Graph
import pyshacl
from ontoenv import OntoEnv

import aiohttp

import asyncio
import re
from typing import List, Optional, Tuple

from bacpypes3.pdu import Address
from bacpypes3.comm import bind
from bacpypes3.debugging import bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.primitivedata import Null, ObjectIdentifier
from bacpypes3.npdu import IAmRouterToNetwork
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.apdu import (
    ErrorRejectAbortNack,
    PropertyReference,
    PropertyIdentifier,
    ErrorType,
    AbortPDU,
    AbortReason
)
from bacpypes3.vendor import get_vendor_info
from bacpypes3.netservice import NetworkAdapter

import sys
import argparse


"""

Test Bench Hammers
> whois 1000 3456799
> read 192.168.204.13 analog-input,1 present-value
> read 192.168.204.14 schedule,1 present-value
> read 192.168.204.14 schedule,1 weekly-schedule
> priority 192.168.204.13 analog-output,1
> write 192.168.204.13 analog-output,1 present-value 999.8 9
> write 192.168.204.13 analog-output,1 present-value null 9
> priority 192.168.204.13 analog-output,1

Drill 1: The "Hello World" (Dump everything)
> sparql autoscan_223p.ttl "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"

Drill 2: Find all Devices
> sparql autoscan_223p.ttl "SELECT ?device ?name WHERE { ?device a bacnet:BACnetDevice ; rdfs:label ?name }"

Drill 3: Find "Temp" sensors and their values
> sparql autoscan_223p.ttl "SELECT ?point ?val WHERE { ?point a s223:QuantifiableObservableProperty ; rdfs:label ?name ; bacnet:presentValue ?val . FILTER regex(?name, 'Temp', 'i') }"
"""


# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

# globals
app: Optional[Application] = None


def load_graph(path: str) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g

def run_sparql(model_path: str, query_text: str) -> None:
    g = load_graph(model_path)
    res = g.query(query_text)

    # Correctly handle boolean (ASK) vs Table (SELECT) results
    if res.type == "ASK":
        print(res.askAnswer)
        return

    # Handle SELECT results (iterable rows)
    rows = list(res)
    if not rows:
        print("(no results)")
        return

    for row in rows:
        # Clean up output: remove huge URIs for readability if possible
        clean_row = []
        for v in row:
            s = str(v)
            # Optional: Shorten standard prefixes for cleaner shell output
            s = s.replace("http://data.ashrae.org/standard223#", "s223:")
            s = s.replace("urn:bacnet-autoscan/bacnet#", "bacnet:")
            s = s.replace("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:")
            s = s.replace("http://www.w3.org/2000/01/rdf-schema#", "rdfs:")
            clean_row.append(s)
        
        print(" | ".join(clean_row))

def run_shacl(model_path: str, shapes_path: str, inplace: bool = False) -> None:
    data_g = load_graph(model_path)

    env = OntoEnv(temporary=True, no_search=True)
    sid = env.add(shapes_path)
    shacl_g = env.get_graph(sid)
    env.import_dependencies(shacl_g)

    valid, report_graph, report_text = pyshacl.validate(
        data_graph=data_g,
        shacl_graph=shacl_g,
        ont_graph=shacl_g,
        advanced=True,
        inplace=inplace,
        js=True,
        allow_warnings=True,
    )

    print(report_text)
    print(f"Valid? {valid}")



@bacpypes_debugging
class InteractiveCmd(Cmd):
    """
    Interactive BACnet Console with added RDF/SHACL capabilities.
    """

    async def do_download_standards(self) -> None:
        """
        Downloads the official ASHRAE 223P and BACnet 2020 ontologies.
        usage: download_standards
        """
        import aiohttp
        
        # We target two files: 223p.ttl and bacnet-2020.ttl.
        # This dictionary defines a list of potential URLs for EACH file.
        targets = {
            "223p.ttl": [
                "https://data.ashrae.org/BACnet/223p/223p.ttl",           # Official (Case Sensitive)
            ],
            "bacnet-2020.ttl": [
                # This is the "Magic Bullet" Link - The Raw GitHub file from the Open223 project
                "https://raw.githubusercontent.com/open223/open223-defs/main/lib/bacnet.ttl",
                
                # Backup: NREL's new location (they moved the folder structure recently)
                "https://raw.githubusercontent.com/NREL/BuildingMOTIF/develop/libraries/bacnet/2020/bacnet.ttl",
                
                # Official sites (Keep as last resort since they are failing)
                "https://data.ashrae.org/BACnet/2020/BACnet.ttl"
            ]
        }
        
        print("Downloading standards...")
        async with aiohttp.ClientSession() as session:
            for filename, urls in targets.items():
                print(f"  Target: {filename}")
                downloaded = False
                
                for url in urls:
                    print(f"    Fetching from {url} ...", end=" ")
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                content = await resp.text()
                                # Verify we didn't just download a 404 HTML page
                                if "<!DOCTYPE html>" in content[:50]:
                                    print("Failed (Got HTML, expected Turtle)")
                                    continue
                                    
                                with open(filename, "w", encoding="utf-8") as f:
                                    f.write(content)
                                print("✓ Success!")
                                downloaded = True
                                break # Move to next file
                            else:
                                print(f"Failed ({resp.status})")
                    except Exception as e:
                        print(f"Error ({e})")
                
                if not downloaded:
                    print(f"  ! CRITICAL: Could not download {filename} from any source.")
        
        print("\nDone. You can now use these files in validation.")

    async def do_sparql(self, model_path: str, query: str) -> None:
        """
        Run a SPARQL query on a Turtle model file.
        NOTE: Enclose the query in quotes!
        
        usage: sparql <model.ttl> <query_string>
        example: sparql model.ttl "SELECT ?s WHERE { ?s rdf:type s223:QuantifiableObservableProperty }"
        """
        # Inject standard prefixes if the user was lazy
        if "PREFIX" not in query.upper():
            query = (
                "PREFIX s223: <http://data.ashrae.org/standard223#>\n"
                "PREFIX bacnet: <urn:bacnet-autoscan/bacnet#>\n"
                "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
                "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
                + query
            )
        
        print(f"Running SPARQL on {model_path}...")
        
        # Run in a separate thread to avoid blocking BACnet traffic
        try:
            await asyncio.to_thread(run_sparql, model_path, query)
        except Exception as e:
            print(f"SPARQL Error: {e}")

    def run_shacl(model_path: str, shapes_path: str, ontology_path: str = None, inplace: bool = False) -> None:
        data_g = load_graph(model_path)
        
        # Load the Shapes (Your Rules)
        env = OntoEnv(temporary=True, no_search=True)
        sid = env.add(shapes_path)
        shacl_g = env.get_graph(sid)
        
        # Load the Ontology (The Dictionary - e.g., 223p.ttl)
        ont_g = None
        if ontology_path:
            print(f"Loading background ontology from {ontology_path}...")
            oid = env.add(ontology_path)
            ont_g = env.get_graph(oid)
            # Merge shapes and ontology for the "knowledge" graph
            shacl_g = shacl_g + ont_g

        valid, report_graph, report_text = pyshacl.validate(
            data_graph=data_g,
            shacl_graph=shacl_g,
            ont_graph=shacl_g, # Now includes your standard definitions!
            advanced=True,
            inplace=inplace,
            js=True,
            allow_warnings=True,
        )

        print(report_text)
        print(f"Valid? {valid}")

    async def do_shacl(self, model_path: str, shapes_path: str, ontology_path: str = None) -> None:
            """
            Validate a model against a SHACL shapes file, optionally using a standard ontology.
            
            usage: shacl <model.ttl> <shapes.ttl> [ontology.ttl]
            """
            print(f"Validating {model_path} against {shapes_path}...")
            if ontology_path:
                print(f"(Using {ontology_path} for inference)")
            
            try:
                await asyncio.to_thread(run_shacl, model_path, shapes_path, ontology_path)
            except Exception as e:
                print(f"SHACL Error: {e}")

    async def do_whois(
        self, low_limit: Optional[int] = None, high_limit: Optional[int] = None
    ) -> None:
        """
        Send a Who-Is request and print responses.
        usage: whois [ low_limit high_limit ]
        """
        print(f"Broadcasting Who-Is {low_limit if low_limit else ''} {high_limit if high_limit else ''}...")
        i_ams = await app.who_is(low_limit, high_limit)

        if not i_ams:
            print("No response(s) received")
        else:
            for i_am in i_ams:
                dev_addr: Address = i_am.pduSource
                dev_id: ObjectIdentifier = i_am.iAmDeviceIdentifier
                vendor_id = i_am.vendorID
                print(f"Device {dev_id} @ {dev_addr} (Vendor: {vendor_id})")

    async def do_objects(self, address: Address, instance_id: int) -> None:
        """
        List all objects in a specific device. 
        Includes fallback logic if the device does not support bulk object-list reads.
        
        usage: objects <ip_address> <device_instance_id>
        example: objects 192.168.1.10 1001
        """
        device_identifier = ObjectIdentifier(f"device,{instance_id}")
        
        print(f"Reading object-list from {device_identifier} @ {address}...")

        object_list = []
        
        # 1. Try reading entire array at once (Fastest)
        try:
            object_list = await app.read_property(
                address, device_identifier, "object-list"
            )
        except (AbortPDU, ErrorRejectAbortNack) as e:
            print(f"Standard read failed ({e}), attempting fallback method...")
            
            # 2. FALLBACK: Read Length, then read index-by-index
            try:
                list_len = await app.read_property(
                    address, device_identifier, "object-list", array_index=0
                )
                print(f"Device contains {list_len} objects. Reading one by one...")
                
                for i in range(list_len):
                    obj_id = await app.read_property(
                        address, device_identifier, "object-list", array_index=i + 1
                    )
                    object_list.append(obj_id)
                    if i % 10 == 0:
                        print(".", end="", flush=True)
                print() # Newline
            except Exception as err:
                print(f"Failed to read object list: {err}")
                return

        print(f"Found {len(object_list)} objects:")
        for obj in object_list:
            # Optional: Try to get the name for a nicer display
            try:
                name = await app.read_property(address, obj, "object-name")
            except:
                name = "???"
            print(f"  - {obj} : {name}")

    async def do_read(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
    ) -> None:
        """
        Read a single property.
        usage: read <address> <objid> <prop>
        example: read 192.168.1.10 analog-value,1 present-value
        """
        # Split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            print("Property specification incorrect")
            return

        prop_id, array_index = property_index_match.groups()
        if array_index is not None:
            array_index = int(array_index)

        print(f"Reading {object_identifier} {property_identifier} from {address}...")

        try:
            value = await app.read_property(
                address, object_identifier, prop_id, array_index
            )
            if isinstance(value, AnyAtomic):
                value = value.get_value()
            print(f"  = {value}")

        except ErrorRejectAbortNack as err:
            print(f"  ! Error: {err}")

    async def do_write(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value: str,
        priority: int = -1,
    ) -> None:
        """
        Write a property value.
        usage: write <address> <objid> <prop> <value> [priority]
        example: write 192.168.1.10 analog-value,1 present-value 50.0 8
        """
        # Parse property index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            print("Property specification incorrect")
            return

        prop_id, array_index = property_index_match.groups()
        if array_index is not None:
            array_index = int(array_index)

        # Handle 'null' for releasing overrides
        if value.lower() == "null":
            if priority == -1:
                print("Error: 'null' can only be used with a specific priority level.")
                return
            value = Null(())

        try:
            print(f"Writing to {object_identifier}...")
            await app.write_property(
                address,
                object_identifier,
                prop_id,
                value,
                array_index,
                priority,
            )
            print("  Write successful (Ack received).")

        except ErrorRejectAbortNack as err:
            print(f"  ! Write failed: {err}")

    async def do_priority(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """
        Display the Priority Array of an object.
        usage: priority <address> <objid>
        """
        try:
            response = await app.read_property(
                address, object_identifier, "priority-array"
            )
            
            if not response:
                print("Priority array is empty or None.")
                return

            print(f"Priority Array for {object_identifier}:")
            has_entries = False
            for index, priority_value in enumerate(response):
                val_type = priority_value._choice
                val = getattr(priority_value, val_type, None)

                # Only print slots that are NOT null
                if val_type != "null":
                    has_entries = True
                    if isinstance(val, AnyAtomic):
                        val = val.get_value()
                    print(f"  [{index + 1}] : {val} ({val_type})")
            
            if not has_entries:
                print("  (All slots are NULL/Relinquished)")

        except ErrorRejectAbortNack as err:
            print(f"Error reading priority-array: {err}")

    async def do_rpm(self, address: Address, *args: str) -> None:
        """
        Read Property Multiple (Advanced Debugging).
        usage: rpm <address> ( <objid> ( <prop[indx]> )... )...
        """
        args_list = list(args)
        
        # Get device info for correct datatype parsing
        device_info = await app.device_info_cache.get_device_info(address)
        vendor_info = get_vendor_info(
            device_info.vendor_identifier if device_info else 0
        )

        parameter_list = []
        while args_list:
            obj_id = vendor_info.object_identifier(args_list.pop(0))
            obj_class = vendor_info.get_object_class(obj_id[0])
            if not obj_class:
                print(f"Unknown object type: {obj_id}")
                return

            parameter_list.append(obj_id)
            property_reference_list = []
            
            while args_list:
                prop_ref = PropertyReference(args_list.pop(0), vendor_info=vendor_info)
                property_reference_list.append(prop_ref)
                if args_list and ((":" in args_list[0]) or ("," in args_list[0])):
                    break
            
            parameter_list.append(property_reference_list)

        if not parameter_list:
            print("Object identifier expected")
            return

        try:
            response = await app.read_property_multiple(address, parameter_list)
            for (obj_id, prop_id, arr_index, prop_value) in response:
                print(f"{obj_id} {prop_id}{f'[{arr_index}]' if arr_index is not None else ''} = {prop_value}")
                if isinstance(prop_value, ErrorType):
                    print(f"    Error: {prop_value}")
        except ErrorRejectAbortNack as err:
            print(f"RPM Failed: {err}")

    async def do_whohas(self, *args: str) -> None:
        """
        Find devices containing a specific object ID or Name.
        usage: whohas [ low_limit high_limit ] [ objid ] [ objname ]
        """
        args_list = list(args)
        low_limit = int(args_list.pop(0)) if args_list and args_list[0].isdigit() else None
        high_limit = int(args_list.pop(0)) if args_list and args_list[0].isdigit() else None

        obj_id = None
        obj_name = None

        if args_list:
            try:
                obj_id = ObjectIdentifier(args_list[0])
                args_list.pop(0)
            except ValueError:
                pass
        
        if args_list:
            obj_name = args_list[0]

        if obj_id is None and obj_name is None:
            print("Usage: whohas [limits] <objid> OR <objname>")
            return

        print(f"Searching for {obj_id if obj_id else ''} {obj_name if obj_name else ''}...")
        i_haves = await app.who_has(low_limit, high_limit, obj_id, obj_name)

        if not i_haves:
            print("No response(s)")
        else:
            for i_have in i_haves:
                print(f"Device {i_have.deviceIdentifier} @ {i_have.pduSource} has {i_have.objectIdentifier} '{i_have.objectName}'")

    async def do_router(self, address: Optional[Address] = None, network: Optional[int] = None) -> None:
        """
        Discover BACnet routers.
        usage: router [address] [network]
        """
        print(f"Sending Who-Is-Router-To-Network...")
        if not app.nse:
            print("Network Service Element not enabled.")
            return

        result = await app.nse.who_is_router_to_network(destination=address, network=network)
        if not result:
            print("No routers found.")
            return

        for adapter, i_am_router in result:
             # Logic to display router info
             print(f"Router @ {i_am_router.pduSource} serves networks: {i_am_router.iartnNetworkList}")




def build_model_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tester.py model")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sparql")
    sp.add_argument("--model", required=True)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="SPARQL query string")
    g.add_argument("--query-file", help="Path to .rq file")

    va = sub.add_parser("validate")
    va.add_argument("--model", required=True)
    va.add_argument("--shapes", required=True)
    va.add_argument("--inplace", action="store_true")

    return p


async def main() -> None:
    # NEW: if first arg is "model", run offline tooling and exit
    if len(sys.argv) > 1 and sys.argv[1] == "model":
        p = build_model_cli_parser()
        args = p.parse_args(sys.argv[2:])

        if args.cmd == "sparql":
            if args.query_file:
                query_text = Path(args.query_file).read_text(encoding="utf-8")
            else:
                query_text = args.query

            # optional convenience prefixes if user didn't include them
            if "PREFIX" not in query_text.upper():
                query_text = (
                    "PREFIX s223: <http://data.ashrae.org/standard223#>\n"
                    "PREFIX bacnet: <urn:bacnet-autoscan/bacnet#>\n"
                    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
                    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
                    + query_text
                )

            run_sparql(args.model, query_text)
            return

        if args.cmd == "validate":
            run_shacl(args.model, args.shapes, inplace=args.inplace)
            return

    # otherwise: EXISTING interactive shell behavior (unchanged)
    global app
    parser = SimpleArgumentParser()
    args = parser.parse_args()

    console = Console()
    cmd = InteractiveCmd()
    bind(console, cmd)

    app = Application.from_args(args)

    print("\n--- Interactive BACnet Shell ---")
    print("Type 'help' for commands (whois, read, write, objects, priority, etc.)")
    print("--------------------------------\n")

    try:
        await console.fini.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())