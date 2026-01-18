#!/usr/bin/env python

"""
BACnet Auto-Scan (Enhanced)
=======================================================
Scans a range of devices and builds a "Wide" CSV inventory.

COMPLIANCE UPDATE:
  - Implements ASHRAE 135 Annex CT style RDF values.
  - Maps EngineeringUnits and Reliability to semantic URIs (owl:NamedIndividual).
  - Uses s223 classes for the nodes, but standard BACnet URIs for the data.

Usage:
    python bacnet_autoscan.py --low-instance 1 --high-instance 3456999 --output-dir autoscan_csv --output-223p model.ttl
"""

import asyncio
import csv
import logging
import os
from typing import Any, List, Optional, Tuple, Dict, Union

import bacpypes3
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.apdu import AbortPDU, ErrorRejectAbortNack
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, BitString, Enumerated
from bacpypes3.basetypes import EngineeringUnits, Reliability
from bacpypes3.vendor import get_vendor_info

# Global application instance
app: Optional[Application] = None
log = logging.getLogger(__name__)

# -----------------------------
# RDF/223P Builder (Standard Compliant)
# -----------------------------

class Telemetry223PBuilder:
    """
    RDF builder that bridges ASHRAE 223P (Topology) with Annex CT (Values).
    """

    def __init__(self, model_base_uri: str):
        # Delay imports
        from rdflib import Graph, Namespace, Literal, URIRef
        from rdflib.namespace import RDF, RDFS, XSD, OWL

        self.Graph = Graph
        self.Namespace = Namespace
        self.Literal = Literal
        self.URIRef = URIRef
        self.RDF = RDF
        self.RDFS = RDFS
        self.XSD = XSD
        self.OWL = OWL

        self.g = Graph()

        # Namespaces
        self.S223 = Namespace("http://data.ashrae.org/standard223#")
        # Standard BACnet Namespace from Annex CT
        self.BACNET = Namespace("http://data.ashrae.org/bacnet/2020#") 
        self.EX = Namespace(model_base_uri.rstrip("/") + "/entity/")

        # Bind prefixes
        self.g.bind("s223", self.S223)
        self.g.bind("bacnet", self.BACNET)
        self.g.bind("ex", self.EX)

    def device_uri(self, device_instance: int) -> Any:
        return self.EX[f"device/{device_instance}"]

    def point_uri(self, device_instance: int, obj_type: str, obj_inst: int) -> Any:
        safe_type = str(obj_type).replace(" ", "_")
        return self.EX[f"point/{device_instance}/{safe_type}/{obj_inst}"]

    def get_enum_uri(self, enum_obj: Enumerated, class_name: str) -> Any:
        """
        Converts a BACnet Enum (like EngineeringUnits) into a semantic URI.
        Format: bacnet:EngineeringUnits.degrees-fahrenheit
        """
        # bacpypes3 str() of an enum usually gives the kebab-case keyword (e.g. 'degrees-fahrenheit')
        safe_key = str(enum_obj).replace(" ", "-")
        return self.BACNET[f"{class_name}.{safe_key}"]

    def add_device(self, device_instance: int, ip: str) -> None:
        dev = self.device_uri(device_instance)
        self.g.add((dev, self.RDF.type, self.BACNET.BACnetDevice))
        self.g.add((dev, self.RDFS.label, self.Literal(f"BACnet Device {device_instance}")))
        self.g.add((dev, self.BACNET.deviceInstance, self.Literal(device_instance, datatype=self.XSD.integer)))
        # IP is technically specific to the port, but keeping simple for this tool
        self.g.add((dev, self.BACNET.ipAddress, self.Literal(ip)))

    def add_point(
        self,
        device_instance: int,
        ip: str,
        obj_type: str,
        obj_inst: int,
        name: str,
        description: str,
        present_value: Any,
        units: Union[str, EngineeringUnits, None],
        reliability: Union[str, Reliability, None],
        supports_priority_array: bool,
    ) -> None:
        dev = self.device_uri(device_instance)
        pt = self.point_uri(device_instance, obj_type, obj_inst)

        # Ensure device exists
        self.add_device(device_instance, ip)

        # 1. Type the point (223P Class)
        if units is not None:
            self.g.add((pt, self.RDF.type, self.S223.QuantifiableObservableProperty))
        else:
            self.g.add((pt, self.RDF.type, self.S223.ObservableProperty))

        # 2. Link to Device
        self.g.add((dev, self.BACNET.hasPoint, pt))

        # 3. Basic Metadata
        if name:
            self.g.add((pt, self.RDFS.label, self.Literal(name)))
        if description:
            self.g.add((pt, self.BACNET.description, self.Literal(description)))

        # 4. Addressing
        self.g.add((pt, self.BACNET.objectType, self.Literal(str(obj_type))))
        self.g.add((pt, self.BACNET.objectInstance, self.Literal(int(obj_inst), datatype=self.XSD.integer)))
        self.g.add((pt, self.BACNET.deviceInstance, self.Literal(int(device_instance), datatype=self.XSD.integer)))

        # 5. Semantic Values (The "Joel Bender" Annex CT Compliance Step)
        
        # Reliability
        if isinstance(reliability, Enumerated):
            rel_uri = self.get_enum_uri(reliability, "Reliability")
            self.g.add((pt, self.BACNET.reliability, rel_uri))
        elif reliability:
            # Fallback for raw strings (though we try to avoid this now)
            self.g.add((pt, self.BACNET.reliability, self.Literal(str(reliability))))

        # Units
        if isinstance(units, Enumerated):
            # This creates: bacnet:EngineeringUnits.degrees-fahrenheit
            unit_uri = self.get_enum_uri(units, "EngineeringUnits")
            self.g.add((pt, self.BACNET.engineeringUnits, unit_uri))
        elif units:
             self.g.add((pt, self.BACNET.engineeringUnits, self.Literal(str(units))))

        # Present Value
        # (We keep PV as a string literal for now as 223P handles data differently than static RDF)
        if present_value != "":
            self.g.add((pt, self.BACNET.presentValue, self.Literal(str(present_value))))

        # Writability
        self.g.add(
            (pt, self.BACNET.supportsPriorityArray, self.Literal(bool(supports_priority_array), datatype=self.XSD.boolean))
        )

    def serialize(self, output_path: str) -> None:
        with open(output_path, "wb") as f:
            self.g.serialize(f, format="turtle")


# -----------------------------
# BACnet Logic
# -----------------------------

async def get_device_object_list(
    device_address: Address,
    device_identifier: ObjectIdentifier,
) -> List[ObjectIdentifier]:
    """
    Reads object-list with Fallback.
    """
    assert app is not None
    object_list: List[ObjectIdentifier] = []

    log.info("  - Reading object-list from %s...", device_identifier)
    try:
        object_list = await app.read_property(device_address, device_identifier, "object-list")
        return object_list
    except (AbortPDU, ErrorRejectAbortNack):
        pass

    try:
        list_len = await app.read_property(device_address, device_identifier, "object-list", array_index=0)
        log.info("    * Fallback: Reading %s objects one-by-one...", list_len)
        for i in range(list_len):
            obj_id = await app.read_property(device_address, device_identifier, "object-list", array_index=i + 1)
            object_list.append(obj_id)
            if i % 10 == 0:
                print(".", end="", flush=True)
        print("")
        return object_list
    except Exception as e:
        log.warning("    ! Failed to read object-list: %s", e)
        return []

async def read_prop_raw(
    dev_addr: Address,
    obj_id: ObjectIdentifier,
    prop_id: str
) -> Any:
    """
    Reads a property and returns the RAW bacpypes3 object (not stringified).
    This allows us to check for Enumerations later.
    """
    assert app is not None
    try:
        val = await app.read_property(dev_addr, obj_id, prop_id)
        if isinstance(val, AnyAtomic):
            return val.get_value()
        return val
    except:
        return None

async def read_priority_array_support(dev_addr: Address, obj_id: ObjectIdentifier) -> Tuple[bool, str]:
    """Check for priority array support."""
    assert app is not None
    try:
        pa = await app.read_property(dev_addr, obj_id, "priority-array")
        if not pa: return (True, "")
        
        # Build simple string for CSV
        active_slots = {}
        for idx, item in enumerate(pa):
            if item is not None:
                val_type = getattr(item, "_choice", None)
                val = getattr(item, val_type, None) if val_type else None
                if isinstance(val, AnyAtomic): val = val.get_value()
                if val is not None: active_slots[idx + 1] = val
        return (True, str(active_slots) if active_slots else "")
    except:
        return (False, "")

# -----------------------------
# Scanner
# -----------------------------

async def scan_range(
    low: int,
    high: int,
    output_dir: Optional[str],
    output_223p: Optional[str],
    model_base_uri: str,
):
    assert app is not None
    if output_dir: os.makedirs(output_dir, exist_ok=True)
    
    builder: Optional[Telemetry223PBuilder] = None
    if output_223p:
        builder = Telemetry223PBuilder(model_base_uri=model_base_uri)

    log.info(f"Broadcasting Who-Is {low} - {high}...")
    i_ams = await app.who_is(low, high)

    if not i_ams:
        log.info("No devices found.")
        return

    csv_headers = [
        "DeviceID", "IP", "ObjType", "ObjInst", "Name", "Description",
        "PresentValue", "Units", "Reliability", "OutOfService", "PriorityArray"
    ]

    for i_am in i_ams:
        dev_id_obj: ObjectIdentifier = i_am.iAmDeviceIdentifier
        dev_addr: Address = i_am.pduSource
        instance = dev_id_obj[1]
        
        # Vendor Info allows us to decode proprietary tags correctly if needed
        vendor_info = get_vendor_info(i_am.vendorID)

        if not (low <= instance <= high): continue
        log.info(f"Scanning Device {instance} @ {dev_addr} (Vendor {i_am.vendorID})...")

        obj_list = await get_device_object_list(dev_addr, dev_id_obj)
        if not obj_list: continue

        rows = []
        for obj_id in obj_list:
            obj_type, obj_inst = obj_id

            # READ PROPERTIES (RAW)
            name_obj = await read_prop_raw(dev_addr, obj_id, "object-name")
            desc_obj = await read_prop_raw(dev_addr, obj_id, "description")
            pv_obj = await read_prop_raw(dev_addr, obj_id, "present-value")
            units_obj = await read_prop_raw(dev_addr, obj_id, "units")
            rel_obj = await read_prop_raw(dev_addr, obj_id, "reliability")
            oos_obj = await read_prop_raw(dev_addr, obj_id, "out-of-service")
            
            # Priority Array
            supports_pa, pa_str = await read_priority_array_support(dev_addr, obj_id)

            # Convert to strings for CSV
            name_str = str(name_obj) if name_obj is not None else ""
            desc_str = str(desc_obj) if desc_obj is not None else ""
            pv_str = str(pv_obj) if pv_obj is not None else ""
            units_str = str(units_obj) if units_obj is not None else ""
            rel_str = str(rel_obj) if rel_obj is not None else ""
            oos_str = str(oos_obj) if oos_obj is not None else ""

            # CSV Row
            rows.append([
                instance, str(dev_addr), str(obj_type), obj_inst,
                name_str, desc_str, pv_str, units_str, rel_str, oos_str, pa_str
            ])

            # RDF Builder (Pass RAW objects for semantic mapping)
            if builder:
                builder.add_point(
                    device_instance=instance,
                    ip=str(dev_addr),
                    obj_type=str(obj_type),
                    obj_inst=int(obj_inst),
                    name=name_str,
                    description=desc_str,
                    present_value=pv_str,
                    units=units_obj,          # Pass the raw object!
                    reliability=rel_obj,      # Pass the raw object!
                    supports_priority_array=supports_pa
                )
            
            print(f"  > {obj_type}:{obj_inst} | {name_str} | {pv_str} {units_str}")

        if output_dir:
            fname = os.path.join(output_dir, f"audit_{instance}.csv")
            with open(fname, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(csv_headers)
                writer.writerows(rows)
            log.info(f"Saved audit report to {fname}")

    if builder and output_223p:
        builder.serialize(output_223p)
        log.info(f"Saved 223P/Annex-CT model to {output_223p}")

async def main():
    global app
    parser = SimpleArgumentParser()
    parser.add_argument("--low-instance", type=int, required=True)
    parser.add_argument("--high-instance", type=int, required=True)
    parser.add_argument("--output-dir", type=str, default="bacnet_audit")
    parser.add_argument("--output-223p", type=str, default=None)
    parser.add_argument("--model-base-uri", type=str, default="urn:bacnet-autoscan")

    args = parser.parse_args()
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

    app = Application.from_args(args)
    try:
        await scan_range(args.low_instance, args.high_instance, args.output_dir, args.output_223p, args.model_base_uri)
    finally:
        app.close()

if __name__ == "__main__":
    asyncio.run(main())