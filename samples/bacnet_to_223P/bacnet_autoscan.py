#!/usr/bin/env python

"""
BACnet Auto-Scan
=======================================================
Scans a range of devices and builds a "Wide" CSV inventory.
Each row is one BACnet Object, containing columns for common
properties useful for network documentation and troubleshooting.

NEW (Optional):
  - Can also emit a lightweight "223P-ish" RDF/Turtle model containing:
      * One node per BACnet device
      * One node per BACnet object/point
      * BACnet addressing metadata (IP, device instance, object type/instance)
      * Writability flag (supports priority-array == commandable proxy)

pip install rdflib pyshacl ontoenv bacpypes3 ifaddr


This RDF output is intended as a *proto-model* for brownfield workflows:
it captures telemetry + addressing + commandability, and can be enriched later
with proper 223P equipment topology/templates and QUDT unit URIs.

Usage:
    python bacnet_autoscan.py --low-instance 1 --high-instance 3456999 --output-dir autoscan_csv
    python bacnet_autoscan.py --low-instance 1 --high-instance 3456999 --output-dir autoscan_csv --output-223p model.ttl
"""

import asyncio
import csv
import logging
import os
from typing import Any, List, Optional, Tuple, Dict

import bacpypes3
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.apdu import AbortPDU, ErrorRejectAbortNack
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, BitString

# Global application instance
app: Optional[Application] = None
log = logging.getLogger(__name__)

# -----------------------------
# Optional RDF/223P builder
# -----------------------------

class Telemetry223PBuilder:
    """
    Minimal RDF builder that writes a "223P-ish" telemetry inventory graph.
    This does NOT attempt to infer HVAC topology; it focuses on points + addressing
    and uses 223P classes where safe (QuantifiableObservableProperty / ObservableProperty).
    """

    def __init__(self, model_base_uri: str):
        # Delay imports so users don't need rdflib unless they enable --output-223p
        from rdflib import Graph, Namespace, Literal, URIRef
        from rdflib.namespace import RDF, RDFS, XSD

        self.Graph = Graph
        self.Namespace = Namespace
        self.Literal = Literal
        self.URIRef = URIRef
        self.RDF = RDF
        self.RDFS = RDFS
        self.XSD = XSD

        self.g = Graph()

        # Namespaces
        self.S223 = Namespace("http://data.ashrae.org/standard223#")
        self.QUDT = Namespace("http://qudt.org/schema/qudt/")
        self.BACNET = Namespace(model_base_uri.rstrip("/") + "/bacnet#")
        self.EX = Namespace(model_base_uri.rstrip("/") + "/entity/")

        # Bind prefixes for readable Turtle
        self.g.bind("s223", self.S223)
        self.g.bind("qudt", self.QUDT)
        self.g.bind("bacnet", self.BACNET)
        self.g.bind("ex", self.EX)

    def device_uri(self, device_instance: int) -> Any:
        return self.EX[f"device/{device_instance}"]

    def point_uri(self, device_instance: int, obj_type: str, obj_inst: int) -> Any:
        safe_type = str(obj_type).replace(" ", "_")
        return self.EX[f"point/{device_instance}/{safe_type}/{obj_inst}"]

    def add_device(self, device_instance: int, ip: str) -> None:
        dev = self.device_uri(device_instance)
        self.g.add((dev, self.RDF.type, self.BACNET.BACnetDevice))
        self.g.add((dev, self.RDFS.label, self.Literal(f"BACnet Device {device_instance}")))
        self.g.add((dev, self.BACNET.deviceInstance, self.Literal(device_instance, datatype=self.XSD.integer)))
        self.g.add((dev, self.BACNET.ipAddress, self.Literal(ip)))

    def add_point(
        self,
        device_instance: int,
        ip: str,
        obj_type: str,
        obj_inst: int,
        name: str,
        description: str,
        units: str,
        present_value: str,
        supports_priority_array: bool,
    ) -> None:
        dev = self.device_uri(device_instance)
        pt = self.point_uri(device_instance, obj_type, obj_inst)

        # Attach device if not already present
        self.add_device(device_instance, ip)

        # Type the point in a conservative 223P-friendly way.
        # If we have units, treat as QuantifiableObservableProperty; otherwise ObservableProperty.
        if units:
            self.g.add((pt, self.RDF.type, self.S223.QuantifiableObservableProperty))
        else:
            self.g.add((pt, self.RDF.type, self.S223.ObservableProperty))

        # Link point to device (custom relationship; later enrichment can map to true 223P topology)
        self.g.add((dev, self.BACNET.hasPoint, pt))

        # Human labels
        if name:
            self.g.add((pt, self.RDFS.label, self.Literal(name)))
        if description:
            self.g.add((pt, self.BACNET.description, self.Literal(description)))

        # BACnet addressing metadata
        self.g.add((pt, self.BACNET.objectType, self.Literal(str(obj_type))))
        self.g.add((pt, self.BACNET.objectInstance, self.Literal(int(obj_inst), datatype=self.XSD.integer)))
        self.g.add((pt, self.BACNET.deviceInstance, self.Literal(int(device_instance), datatype=self.XSD.integer)))
        self.g.add((pt, self.BACNET.ipAddress, self.Literal(ip)))

        # Telemetry metadata (strings because BACnet values can be complex / vendor-specific)
        if present_value != "":
            self.g.add((pt, self.BACNET.presentValue, self.Literal(str(present_value))))
        if units:
            # In a “real” 223P model, you'd map this to a QUDT unit URI.
            # Here we keep the raw BACnet EngineeringUnits text for downstream mapping.
            self.g.add((pt, self.BACNET.engineeringUnits, self.Literal(str(units))))

        # Writability/commandability proxy:
        # If the point supports priority-array, it is generally commandable.
        self.g.add(
            (pt, self.BACNET.supportsPriorityArray, self.Literal(bool(supports_priority_array), datatype=self.XSD.boolean))
        )
        self.g.add(
            (pt, self.BACNET.isWritable, self.Literal(bool(supports_priority_array), datatype=self.XSD.boolean))
        )

    def serialize(self, output_path: str) -> None:
        with open(output_path, "wb") as f:
            self.g.serialize(f, format="turtle")


# -----------------------------
# BACnet read helpers
# -----------------------------

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
        return ""
    except Exception as e:
        log.debug(f"Error reading {prop_id} on {obj_id}: {e}")
        return ""


async def read_priority_array_support(
    dev_addr: Address,
    obj_id: ObjectIdentifier
) -> Tuple[bool, str]:
    """
    Returns:
      (supports_priority_array, active_slots_str)

    - supports_priority_array is True if reading 'priority-array' succeeds (even if all NULL).
    - active_slots_str is a compact "{8: 72.0, 16: 70.0}"-style string of non-NULL slots, else "".
    """
    assert app is not None
    try:
        pa = await app.read_property(dev_addr, obj_id, "priority-array")
    except (ErrorRejectAbortNack, AbortPDU):
        return (False, "")
    except Exception as e:
        log.debug(f"Could not read priority-array: {e}")
        return (False, "")

    # If we got here, the property exists/succeeds => treat as "supports"
    if not pa:
        return (True, "")

    active_slots: Dict[int, Any] = {}
    for idx, item in enumerate(pa):
        if item is not None:
            val_type = getattr(item, "_choice", None)
            val = getattr(item, val_type, None) if val_type else None

            if isinstance(val, AnyAtomic):
                val = val.get_value()

            if val is not None:
                active_slots[idx + 1] = val

    if not active_slots:
        return (True, "")

    return (True, str(active_slots))


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

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    builder: Optional[Telemetry223PBuilder] = None
    if output_223p:
        builder = Telemetry223PBuilder(model_base_uri=model_base_uri)

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

            supports_pa, pa_str = await read_priority_array_support(dev_addr, obj_id)

            row = [
                instance, str(dev_addr), str(obj_type), obj_inst,
                name, desc,
                pv, units,
                rel, oos, flags,
                pa_str
            ]
            rows.append(row)

            # Add point to optional RDF model
            if builder:
                builder.add_point(
                    device_instance=instance,
                    ip=str(dev_addr),
                    obj_type=str(obj_type),
                    obj_inst=int(obj_inst),
                    name=name,
                    description=desc,
                    units=units,
                    present_value=pv,
                    supports_priority_array=supports_pa,
                )

            print(f"  > Found {obj_type}:{obj_inst} | {name} | {pv} {units}")

        if output_dir:
            fname = os.path.join(output_dir, f"audit_{instance}.csv")
            with open(fname, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            log.info(f"Saved audit report to {fname}")

    # Write 223P-ish model at end (single combined model)
    if builder and output_223p:
        builder.serialize(output_223p)
        log.info(f"Saved 223P telemetry model to {output_223p}")


async def main():
    global app
    parser = SimpleArgumentParser()
    parser.add_argument("--low-instance", type=int, required=True)
    parser.add_argument("--high-instance", type=int, required=True)
    parser.add_argument("--output-dir", type=str, default="bacnet_audit")

    # NEW:
    parser.add_argument(
        "--output-223p",
        type=str,
        default=None,
        help="Optional: write a Turtle (.ttl) file containing a 223P-ish telemetry inventory graph",
    )
    parser.add_argument(
        "--model-base-uri",
        type=str,
        default="urn:bacnet-autoscan",
        help="Base URI used for generated RDF entities (default: urn:bacnet-autoscan)",
    )

    args = parser.parse_args()

    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

    app = Application.from_args(args)
    try:
        await scan_range(
            args.low_instance,
            args.high_instance,
            args.output_dir,
            args.output_223p,
            args.model_base_uri,
        )
    finally:
        app.close()


if __name__ == "__main__":
    asyncio.run(main())
