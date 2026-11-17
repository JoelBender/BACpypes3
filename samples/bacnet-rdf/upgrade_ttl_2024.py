#!/usr/bin/env python
"""
upgrade_ttl_2024.py - re-encode a saved site_scan.ttl the way BACpypes3 #193 writes it

Offline and read-only: it parses Turtle and writes Turtle. No BACnet traffic.

Older bacpypes3 builds wrote the http://data.ashrae.org/bacnet/ namespace, no
class typing on objects, bacnet:objectIdentifier literals and xsd:date /
xsd:time values. BACpypes3 #193 (aligned with csml2rdf bacnet.ttl) writes:

* namespace http://data.ashrae.org/bacnet/2024#
* rdf:type for every class in the chain, e.g. bacnet:AnalogInputObject and
  bacnet:Object, bacnet:ProprietaryObject and bacnet:Object for object types
  with no standard class, using the csml2rdf names (MultistateValueObject,
  BitstringValueObject, ...)
* object-identifier as a plain "type,instance" string ("analog-input,0")
* dates and times as strings that match the csml2rdf patterns
  ("1970-02-23 1", "18:37:29.85", "*:*:*.*")
* device-instance as an xsd:nonNegativeInteger, the encoding used in
  bacpypes3 0.1.0 (unsigned_encode)

This script uses the encoders from the installed bacpypes3 (0.1.0 or later), so
the output is what a fresh scan with that build would write for the same
#193 / 0.1.0 literal forms. xsd:dateTime values (scan:readAt, prov times,
DateTime properties) are left alone; #193 does not change them. WeekNDay and
PropertyValue (bacnet:property-value) encodings are not rewritten here; this
bench graph does not contain those terms.

    python upgrade_ttl_2024.py                       # site_scan.ttl in place
    python upgrade_ttl_2024.py --ttl old.ttl --out new.ttl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef  # type: ignore
from rdflib.namespace import RDF, XSD  # type: ignore

from bacpypes3.primitivedata import Date, ObjectIdentifier, Time
from bacpypes3.rdf.core import BACNET, object_class_nodes
from bacpypes3.rdf.util import date_encode, objectidentifier_encode, time_encode, unsigned_encode

LEGACY = "http://data.ashrae.org/bacnet/"
NEW = "http://data.ashrae.org/bacnet/2024#"
HERE = Path(__file__).resolve().parent


def rename(term):
    """Move a legacy bacnet: IRI (or literal datatype) to the 2024# namespace."""
    if isinstance(term, URIRef):
        text = str(term)
        if text.startswith(LEGACY) and not text.startswith(NEW):
            return URIRef(NEW + text[len(LEGACY):])
        return term
    if isinstance(term, Literal) and term.datatype is not None:
        text = str(term.datatype)
        if text.startswith(LEGACY) and not text.startswith(NEW):
            return Literal(str(term), datatype=URIRef(NEW + text[len(LEGACY):]))
    return term


def reencode(g: Graph, term):
    """Re-encode literals with the installed (#193) encoders."""
    if not isinstance(term, Literal):
        return term
    if term.datatype == BACNET.objectIdentifier:
        return objectidentifier_encode(g, ObjectIdentifier(str(term)))
    if term.datatype == XSD.date:
        return date_encode(g, Date(term.value.isoformat()))
    if term.datatype == XSD.time:
        value = term.value
        return time_encode(
            g, Time((value.hour, value.minute, value.second, value.microsecond // 10000))
        )
    if term.datatype in (BACNET.datePattern, BACNET.timePattern):
        cls = Date if term.datatype == BACNET.datePattern else Time
        encode = date_encode if cls is Date else time_encode
        return encode(g, cls(str(term)))
    return term


def upgrade(old: Graph) -> tuple[Graph, dict]:
    if str(BACNET) != NEW:
        raise SystemExit(
            f"installed bacpypes3 writes {BACNET}, need {NEW} (BACpypes3 #193 or later)"
        )
    new = Graph()
    for prefix, ns in old.namespaces():
        if str(ns) == LEGACY:
            continue
        new.bind(prefix, ns)
    new.bind("bacnet", URIRef(NEW))

    stats = {"triples_in": len(old), "renamed": 0, "reencoded": 0, "types_added": 0}
    for s, p, o in old:
        s2, p2, o2 = rename(s), rename(p), rename(o)
        if (s2, p2, o2) != (s, p, o):
            stats["renamed"] += 1
        o3 = reencode(new, o2)
        if p2 == BACNET["device-instance"] and isinstance(o3, Literal):
            typed = unsigned_encode(new, int(o3))
            if typed != o3:
                o3 = typed
        if o3 != o2:
            stats["reencoded"] += 1
        new.add((s2, p2, o3))

    # class chain for everything a device contains, from its object-identifier
    for obj in set(new.objects(None, BACNET.contains)):
        oid = new.value(obj, BACNET["object-identifier"])
        if oid is None:
            continue
        for class_iri in object_class_nodes(ObjectIdentifier(str(oid))):
            if (obj, RDF.type, class_iri) not in new:
                new.add((obj, RDF.type, class_iri))
                stats["types_added"] += 1
    stats["triples_out"] = len(new)
    return new, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ttl", type=Path, default=HERE / "site_scan.ttl")
    parser.add_argument("--out", type=Path, default=None, help="default: overwrite --ttl")
    args = parser.parse_args(argv)

    old = Graph().parse(str(args.ttl), format="turtle")
    new, stats = upgrade(old)
    out = args.out or args.ttl
    new.serialize(str(out), format="turtle")
    print(f"wrote {out}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
