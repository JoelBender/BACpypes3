#!/usr/bin/env python

"""
BACnet CSV & Brick Scanner (FIXED + CONSOLE TABLE)
==================================================
1. Simple Discovery (Who-Is only):
   python discover-objects-rdf.py --low 1 --high 3456799

2. Deep Scan (CSV + RDF + Live Table):
   python discover-objects-rdf.py --low 1 --high 3456799 --out-dir bacnet_to_223P --console-table
"""

import sys
import asyncio
import csv
import logging
from pathlib import Path
from typing import List

# --- RDF Imports ---
from rdflib import Graph  # type: ignore
from bacpypes3.rdf import BACnetGraph

# --- BACpypes3 Imports ---
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier, PriorityArray
from bacpypes3.apdu import AbortPDU, ErrorRejectAbortNack
from bacpypes3.vendor import get_vendor_info
from bacpypes3.constructeddata import AnyAtomic

# Setup basic logging
log = logging.getLogger(__name__)

def ensure_directory(path_str: str) -> Path:
    """Creates the directory if it doesn't exist."""
    p = Path(path_str)
    p.mkdir(parents=True, exist_ok=True)
    return p

def format_priority_array(pa: PriorityArray) -> str:
    """Formats the priority array into a compact string."""
    if not pa:
        return ""
    
    out_dict = {}
    for i, p_val in enumerate(pa):
        priority = i + 1
        if p_val is not None:
            choice_name = p_val._choice
            if choice_name:
                choice_val = getattr(p_val, choice_name)
                if isinstance(choice_val, AnyAtomic):
                    choice_val = choice_val.get_value()
                out_dict[priority] = str(choice_val)
        
    items = [f"{k}: {v}" for k, v in out_dict.items()]
    return "{" + ", ".join(items) + "}"

async def get_device_object_list_robust(
    app: Application, 
    device_address: Address, 
    device_identifier: ObjectIdentifier
) -> List[ObjectIdentifier]:
    """
    Robustly reads object list with visual feedback (dots).
    """
    # 1. Try reading entire array
    try:
        val = await app.read_property(device_address, device_identifier, "object-list")
        if isinstance(val, list): 
            # print(f" [Success: {len(val)} objects]", file=sys.stderr)
            return val
    except (AbortPDU, ErrorRejectAbortNack):
        pass 
    except Exception as e:
        print(f" [Array Read Error: {e}]", file=sys.stderr)

    # 2. Fallback: Read index by index
    print(f"\n    (Fallback: Reading index-by-index...)", end="", flush=True, file=sys.stderr)
    obj_list = []
    try:
        # Read the Length (Index 0)
        list_len = await app.read_property(device_address, device_identifier, "object-list", array_index=0)
        
        # Loop through indices
        for i in range(list_len):
            obj_id = await app.read_property(device_address, device_identifier, "object-list", array_index=i+1)
            obj_list.append(obj_id)
            if i % 10 == 0:
                print(".", end="", flush=True, file=sys.stderr)
        
        print(" Done)", file=sys.stderr)
        return obj_list
        
    except Exception as e:
        print(f" Failed: {e})", file=sys.stderr)
        return []

async def main() -> None:
    # 1. Parse Arguments
    parser = SimpleArgumentParser()
    parser.add_argument("--low", type=int, required=True, help="Low Device Instance Limit")
    parser.add_argument("--high", type=int, required=True, help="High Device Instance Limit")
    parser.add_argument("--verbose", action="store_true", help="Print detailed property reads errors")
    
    # NEW ARG: Console Table
    parser.add_argument("--console-table", action="store_true", help="Print a nice table of points to console while scanning")

    parser.add_argument(
        "--out-dir", 
        nargs='?', 
        const="BACpypes3/samples/bacnet_to_223P", 
        help="If set, performs Deep Scan and saves to dir."
    )
    
    parser.add_argument("--filename", default="site_scan", help="Base filename for outputs")

    args = parser.parse_args()

    # Detect Mode
    simple_mode = args.out_dir is None
    verbose = args.verbose
    show_table = args.console_table

    # 2. Setup App
    app = Application.from_args(args)

    try:
        print(f"--- Broadcasting Who-Is {args.low} - {args.high} ---", file=sys.stderr)
        i_ams = await app.who_is(args.low, args.high)
        
        if not i_ams:
            print("No devices found.", file=sys.stderr)
            return

        # --- SIMPLE MODE ---
        if simple_mode:
            print(f"\nFound {len(i_ams)} Device(s) (Run with --out-dir to Deep Scan):")
            print("-" * 60)
            for i_am in i_ams:
                dev_id = i_am.iAmDeviceIdentifier
                vendor = get_vendor_info(i_am.vendorID)
                vendor_name = getattr(vendor, "vendor_name", f"Vendor {i_am.vendorID}")
                print(f"  Device {dev_id[1]:<10} | {str(i_am.pduSource):<20} | {vendor_name}")
            print("-" * 60)
            return

        # --- DEEP SCAN MODE ---
        out_dir = ensure_directory(args.out_dir)
        csv_path = out_dir / f"{args.filename}.csv"
        ttl_path = out_dir / f"{args.filename}.ttl"

        print(f"Found {len(i_ams)} devices. Starting Deep Scan -> {out_dir} ...", file=sys.stderr)

        # Init CSV
        csv_file = open(csv_path, 'w', newline='', encoding='utf-8')
        fieldnames = [
            "DeviceID", "IP", "ObjType", "ObjInst", "Name", "Description", 
            "PresentValue", "Units", "Reliability", "OutOfService", "PriorityArray"
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        # Init RDF
        g = Graph()
        bacnet_graph = BACnetGraph(g)

        for i_am in i_ams:
            dev_addr = i_am.pduSource
            dev_id = i_am.iAmDeviceIdentifier
            dev_inst = dev_id[1]
            vendor_info = get_vendor_info(i_am.vendorID)
            
            print(f"\n-> Processing Device {dev_inst} @ {dev_addr}", file=sys.stderr)

            # RDF Device Node
            dev_graph = bacnet_graph.create_device(dev_addr, dev_id)

            # --- Process Device Object (Row 1) ---
            dev_name = ""
            dev_desc = ""
            try:
                dev_name = await app.read_property(dev_addr, dev_id, "object-name")
                dev_desc = await app.read_property(dev_addr, dev_id, "description")
                setattr(dev_graph, "object-name", dev_name)
                setattr(dev_graph, "description", dev_desc)
            except: pass

            writer.writerow({
                "DeviceID": dev_inst, "IP": str(dev_addr), "ObjType": "device", "ObjInst": dev_inst,
                "Name": dev_name, "Description": dev_desc,
                "PresentValue": "", "Units": "", "Reliability": "", "OutOfService": "", "PriorityArray": ""
            })

            # --- Process Sub-Objects ---
            obj_list = await get_device_object_list_robust(app, dev_addr, dev_id)

            if not obj_list:
                print(f"    ! No objects found or read failed.", file=sys.stderr)
                continue
            
            # Print Table Header if requested
            if show_table:
                print(f"    {'Type':<20} {'Inst':<8} {'Name':<30} {'Value':<15} {'Priorities'}")
                print(f"    {'-'*20} {'-'*8} {'-'*30} {'-'*15} {'-'*20}")

            for obj_id in obj_list:
                obj_proxy = dev_graph.create_object(obj_id)
                obj_class = vendor_info.get_object_class(obj_id[0])
                if not obj_class: continue

                row_data = {
                    "DeviceID": dev_inst, "IP": str(dev_addr), "ObjType": str(obj_id[0]), "ObjInst": obj_id[1],
                    "Name": "", "Description": "", "PresentValue": "",
                    "Units": "", "Reliability": "", "OutOfService": "", "PriorityArray": ""
                }

                props = ["object-name", "description", "present-value", "units", "reliability", "out-of-service", "priority-array"]

                for prop_name in props:
                    prop_id = PropertyIdentifier(prop_name)
                    if not obj_class.get_property_type(prop_id): continue

                    try:
                        val = await app.read_property(dev_addr, obj_id, prop_id)
                        
                        # Add to RDF
                        setattr(obj_proxy, prop_name, val) 

                        # Add to CSV
                        if prop_name == "object-name": row_data["Name"] = val
                        elif prop_name == "description": row_data["Description"] = val
                        elif prop_name == "present-value":
                            if isinstance(val, AnyAtomic): val = val.get_value()
                            row_data["PresentValue"] = str(val)
                        elif prop_name == "units": row_data["Units"] = str(val)
                        elif prop_name == "reliability": row_data["Reliability"] = str(val)
                        elif prop_name == "out-of-service": row_data["OutOfService"] = 1 if val else 0
                        elif prop_name == "priority-array": row_data["PriorityArray"] = format_priority_array(val)
                        
                    except (ErrorRejectAbortNack, AttributeError): 
                        continue
                    except Exception as e:
                        if verbose: print(f"      Err reading {prop_name}: {e}", file=sys.stderr)
                
                # Write to CSV
                writer.writerow(row_data)

                # Print to Console Table
                if show_table:
                    # Truncate for cleaner output
                    d_name = str(row_data['Name'])
                    d_val = str(row_data['PresentValue'])
                    display_name = (d_name[:28] + '..') if len(d_name) > 28 else d_name
                    display_val = (d_val[:13] + '..') if len(d_val) > 13 else d_val
                    
                    print(f"    {str(obj_id[0]):<20} {str(obj_id[1]):<8} {display_name:<30} {display_val:<15} {row_data['PriorityArray']}")

        # Save Files
        print(f"\nSaving RDF to {ttl_path}...", file=sys.stderr)
        with open(ttl_path, "wb") as f:
            g.serialize(f, format="turtle")
        
        print(f"Saving CSV to {csv_path}...", file=sys.stderr)
        print("Done.", file=sys.stderr)

    finally:
        if not simple_mode and 'csv_file' in locals():
            csv_file.close()
        if app:
            app.close()

if __name__ == "__main__":
    asyncio.run(main())