#!/usr/bin/env python

"""
BACnet Auto-Scan 
=======================================================

Scans a range of devices and builds a "Wide" CSV inventory.
Each row is one BACnet Object, containing columns for common
properties useful for network documentation and troubleshooting.

Features:
  - Auto-discovery (Who-Is) with robust fallbacks.
  - Falls back to index-by-index reading if bulk object-list read fails.
  - Captures Present-Value, Description, Reliability, and Status-Flags.
  - Compacts Priority Arrays into a single readable column.

Usage:
    python bacnet-autoscan-network.py --low-instance 100 --high-instance 3456799 --output-dir ~/audit_reports
"""

import asyncio
import csv
import logging
import os
from typing import Any, List, Optional, Tuple, Dict

import bacpypes3
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.apdu import AbortPDU, AbortReason, ErrorRejectAbortNack
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, BitString
from bacpypes3.vendor import get_vendor_info

# Global application instance
app: Optional[Application] = None
log = logging.getLogger(__name__)

async def get_device_object_list(
    device_address: Address,
    device_identifier: ObjectIdentifier,
) -> List[ObjectIdentifier]:
    """
    Reads the object-list from a device. 
    INCLUDES FALLBACK: Handles standard arrays and index-by-index reading.
    """
    assert app is not None
    object_list: List[ObjectIdentifier] = []

    log.info("  - Reading object-list from %s...", device_identifier)

    # 1. Try reading entire array at once (Fastest)
    try:
        object_list = await app.read_property(
            device_address, device_identifier, "object-list"
        )
        return object_list
    except (AbortPDU, ErrorRejectAbortNack):
        pass 

    # 2. FALLBACK MECHANISM
    try:
        list_len = await app.read_property(
            device_address, device_identifier, "object-list", array_index=0
        )
        log.info("    * Fallback triggered: Reading %s objects one-by-one...", list_len)
        
        for i in range(list_len):
            obj_id = await app.read_property(
                device_address, device_identifier, "object-list", array_index=i + 1
            )
            object_list.append(obj_id)
            if i % 10 == 0:
                print(".", end="", flush=True)
        
        print("") 
        return object_list

    except Exception as e:
        log.warning("    ! Failed to read object-list even with fallback: %s", e)
        return []

async def read_prop_safe(
    dev_addr: Address, 
    obj_id: ObjectIdentifier, 
    prop_id: str
) -> str:
    """
    Reads a single property safely. Returns string representation or empty string if failed.
    """
    assert app is not None
    try:
        val = await app.read_property(dev_addr, obj_id, prop_id)
        
        if isinstance(val, AnyAtomic):
            val = val.get_value()
            
        if isinstance(val, BitString):
            return str(val)
        
        if hasattr(val, "attr"):
            return str(val.attr)
        
        return str(val)
    except (ErrorRejectAbortNack, AbortPDU, AttributeError, ValueError):
        # Property doesn't exist or isn't supported
        return ""
    except Exception as e:
        log.debug(f"Error reading {prop_id} on {obj_id}: {e}")
        return ""

async def get_priority_array_compact(
    dev_addr: Address, 
    obj_id: ObjectIdentifier
) -> str:
    """
    Reads priority array and returns a compact JSON-like string of ONLY active slots.
    Example: "{8: 72.0, 16: 70.0}"
    """
    assert app is not None
    try:
        pa = await app.read_property(dev_addr, obj_id, "priority-array")
    except (ErrorRejectAbortNack, AbortPDU):
        # Specific catch for "Unknown Property" (Error Class: Property, Code: Unknown)
        # This occurs on Devices, Binary Inputs, etc.
        return ""
    except Exception as e:
        # Catch-all to prevent script crash
        log.debug(f"Could not read priority-array: {e}")
        return ""

    if not pa: 
        return ""

    active_slots = {}
    for idx, item in enumerate(pa):
        if item is not None:
            val_type = getattr(item, "_choice", None)
            val = getattr(item, val_type, None) if val_type else None
            
            if isinstance(val, AnyAtomic):
                val = val.get_value()
            
            if val is not None: 
                active_slots[idx + 1] = val
    
    if not active_slots:
        return ""
        
    return str(active_slots)

async def scan_range(low: int, high: int, output_dir: Optional[str]):
    assert app is not None
    
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    log.info(f"Broadcasting Who-Is {low} - {high}...")
    i_ams = await app.who_is(low, high)
    
    if not i_ams:
        log.info("No devices found.")
        return

    headers = [
        "DeviceID", "IP", "ObjType", "ObjInst", 
        "Name", "Description", 
        "PresentValue", "Units/StateText", 
        "Reliability", "OutOfService", "StatusFlags", 
        "PriorityArray(Active)"
    ]

    for i_am in i_ams:
        dev_id_obj: ObjectIdentifier = i_am.iAmDeviceIdentifier
        dev_addr: Address = i_am.pduSource
        instance = dev_id_obj[1]

        if not (low <= instance <= high): 
            continue

        log.info(f"Scanning Device {instance} @ {dev_addr}...")
        
        obj_list = await get_device_object_list(dev_addr, dev_id_obj)
        if not obj_list:
            continue

        rows = []

        for obj_id in obj_list:
            obj_type, obj_inst = obj_id
            
            name = await read_prop_safe(dev_addr, obj_id, "object-name")
            desc = await read_prop_safe(dev_addr, obj_id, "description")
            pv = await read_prop_safe(dev_addr, obj_id, "present-value")
            
            units = await read_prop_safe(dev_addr, obj_id, "units")
            if not units:
                active_txt = await read_prop_safe(dev_addr, obj_id, "active-text")
                if active_txt:
                    units = f"Active: {active_txt}"

            rel = await read_prop_safe(dev_addr, obj_id, "reliability")
            oos = await read_prop_safe(dev_addr, obj_id, "out-of-service")
            flags = await read_prop_safe(dev_addr, obj_id, "status-flags")
            
            pa_str = await get_priority_array_compact(dev_addr, obj_id)

            row = [
                instance, str(dev_addr), str(obj_type), obj_inst,
                name, desc,
                pv, units,
                rel, oos, flags,
                pa_str
            ]
            rows.append(row)
            
            print(f"  > Found {obj_type}:{obj_inst} | {name} | {pv} {units}")

        if output_dir:
            fname = os.path.join(output_dir, f"audit_{instance}.csv")
            with open(fname, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            log.info(f"Saved audit report to {fname}")

async def main():
    global app
    parser = SimpleArgumentParser()
    parser.add_argument("--low-instance", type=int, required=True)
    parser.add_argument("--high-instance", type=int, required=True)
    parser.add_argument("--output-dir", type=str, default="bacnet_audit")
    args = parser.parse_args()

    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    
    app = Application.from_args(args)
    try:
        await scan_range(args.low_instance, args.high_instance, args.output_dir)
    finally:
        app.close()

if __name__ == "__main__":
    asyncio.run(main())