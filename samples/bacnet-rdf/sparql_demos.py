#!/usr/bin/env python
"""
sparql_demos.py - offline SPARQL demos against a saved site_scan.ttl

Read-only. This script never opens a BACnet socket and never writes, overrides,
or relinquishes a point. It only parses Turtle and runs rdflib graph.query().

    python sparql_demos.py
    python sparql_demos.py --ttl site_scan.ttl

What a row can and cannot mean:

* Device / firmware / network inventory: the device object and scan: topology
  as read. Nothing more.
* Commandable / writable capability: the object has a BACnet priority-array
  (and usually a relinquish-default). That is not evidence of an active write.
* Observed active slot: the lowest-numbered non-null priority-array slot, stored
  at scan time as scan:activePriority (BACnet Clause 19: lower number wins).
  The standard name for that slot (manual-operator, ...) is scan:activePriorityName
  when BACnet defines one; otherwise "available". Slot 8 is named
  "manual-operator" by the standard; that is a slot label, not an operator name.
* Effective command: present-value while a slot is held should match that slot's
  value; if no slot is held, present-value is the relinquish-default.
  A defaulted value is not a write.
* Writer identity: not in this graph unless the device returned value-source
  (protocol revision 21+). A priority number is not a person, tool, or controller.
  scan:refersTo is only added when a DeviceObjectPropertyReference (or similar)
  was actually read (schedules, trend logs, loops, address bindings).
* bacnet:value-source: writer attribution when the device returns it (rev 21+).
  Missing here: the FEC is revision 9 and answered unknown-property for
  value-source, current-command-priority, and last-command-time.

Source graph for the comments below: site_scan.ttl in this directory (2935 triples),
written by bacnet_site_scan.py as prov:Activity scan:scan/20261110T150953Z.
Scan start 2026-11-10T15:09:53+00:00 (9:09:53 AM America/Chicago),
per-device scan:readAt 15:09:58-15:09:59 UTC,
tool string "bacnet_site_scan.py, bacpypes3 0.0.110".
The Turtle was then re-encoded offline with upgrade_ttl_2024.py using the
BACpypes3 #193 branch (no BACnet rescan): namespace
http://data.ashrae.org/bacnet/2024#, the rdf:type class chain on all 72
objects, "type,instance" object identifiers, and string dates/times.
Ran python sparql_demos.py on 2026-11-10 against that file.
Optional: python sparql_demos.py --shacl runs the object-basics shapes
(object_basics.ttl) with pyshifty if installed, otherwise pyshacl.
python sparql_demos.py --csml bacnet.ttl validates against the csml2rdf
ontology shapes (see the csml2rdf note in NOTES.md for this file's result).
Older scans in the http://data.ashrae.org/bacnet/ namespace still load: the
terms are moved to 2024# in memory before the queries run.
For a per-object completeness CSV (blank vs missing), use completeness_report.py.

The Turtle does not contain a supervisory-write observation (controller X wrote
value Y at priority Z). A later model could, if a real source provided each
field (value-source, an operator log, a controller reference). Sketch only:

    [] a ex:WriteObservation ;
        ex:controller <bacnet://SUPERVISOR> ;   # only if actually known
        ex:target <bacnet://5007/analog-output,10032> ;
        ex:value 12.0 ;
        ex:priority 8 ;
        ex:at "2026-11-06T17:20:54+00:00"^^xsd:dateTime ;
        ex:observationSource "value-source | operator-log | controller-reference" .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import Graph


HERE = Path(__file__).resolve().parent
DEFAULT_TTL = HERE / "site_scan.ttl"

# Prefixes used both in the SPARQL text and when printing terms.
PREFIX = """\
PREFIX bacnet: <http://data.ashrae.org/bacnet/2024#>
PREFIX scan:   <urn:bacnet-site-scan:>
PREFIX prov:   <http://www.w3.org/ns/prov#>
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>
"""

QUERIES = [
    # q1_inventory asks: list every bacnet:Device with firmware, model, protocol
    # revision, address, network, and the router that reaches it.
    # Bench return: 3 rows (every bacnet:Device). Vendor ids 245, 5, 1417.
    # readAt 2026-11-10T15:09:58+00:00 to 15:09:59+00:00 (9:09 AM America/Chicago).
    #
    #   bacnet://0      BASRT-B00d6c2        BASRT-B            fw 2.7.2     app 2.7.2     protocol rev 4
    #                   address 28271:0x0050db00d6c2   network scan:network/28271
    #                   reached via scan:router/192.168.204.200
    #   bacnet://5007   BENS BENCHTEST BOX   MS-FEC2611-0       fw 6.2.2.6   app 10.2      protocol rev 9
    #                   address 2000:7                 network scan:network/2000
    #                   reached via scan:router/192.168.204.200
    #   bacnet://54545  BensBenchNF          Normal Framework   fw 3.10.9-1  app 3.10.9-1  protocol rev 24
    #                   address 192.168.204.12         reachedVia unbound; onNetwork scan:network/local
    #
    {
        "id": "q1_inventory",
        "title": "Device / firmware / network inventory",
        "about": (
            "Each bacnet:Device joined to its device object (firmware, model, "
            "protocol revision) and to scan: topology (address, network, router)."
        ),
        "sparql": PREFIX
        + """
SELECT ?device ?name ?model ?firmware ?appSoftware ?protocolRev
       ?address ?network ?reachedVia ?vendorId ?readAt
WHERE {
  ?device a bacnet:Device ;
          bacnet:contains ?devObj ;
          scan:address ?address ;
          scan:vendorId ?vendorId .
  ?devObj bacnet:object-type bacnet:ObjectType.device ;
          bacnet:object-name ?name .
  OPTIONAL { ?devObj bacnet:model-name ?model }
  OPTIONAL { ?devObj bacnet:firmware-revision ?firmware }
  OPTIONAL { ?devObj bacnet:application-software-version ?appSoftware }
  OPTIONAL { ?devObj bacnet:protocol-revision ?protocolRev }
  OPTIONAL { ?device scan:onNetwork ?network }
  OPTIONAL { ?device scan:reachedVia ?reachedVia }
  OPTIONAL { ?device scan:readAt ?readAt }
}
ORDER BY ?device
""",
    },
    # q2_commandable asks: which objects have a priority-array (writable
    # capability), and which of those currently bind scan:activePriority?
    # A priority-array is capability. An active slot is an observed hold.
    # Neither is writer identity.
    #
    # Bench return: 30 rows, all on device 5007. The NF server and the router
    # have none. 3 of the 30 bind scan:activePriority; the other 27 have
    # capability but no occupied slot.
    #
    #   bacnet://5007/analog-output,10032  C06-0-10VDC-O   pv 12.0   default 0.0   active 8   manual-operator
    #   bacnet://5007/analog-output,2466   ACTUATOR-0      pv 88.0   default 0.0   active 8   manual-operator
    #   bacnet://5007/analog-value,10011   STAT ZN WC-ADJ  pv 67.58999633789062  default 0.0  active 16  available
    #   bacnet://5007/analog-output,10035  C07-0-10VDC-O   pv 0.0    default 0.0   (unbound)
    #   bacnet://5007/analog-value,10007   Priority        pv 16.0   default 16.0  (unbound)
    #   bacnet://5007/binary-output,10005  RIBRELAY1- C    pv inactive  default inactive  (unbound)
    #
    # C07 matching its relinquish-default with no active slot is a relinquished
    # commandable object, not evidence of a write.
    #
    {
        "id": "q2_commandable",
        "title": "Commandable objects (writable capability + relinquish metadata)",
        "about": (
            "Objects that have a priority-array are commandable in the BACnet "
            "sense. scan:activePriority is bound only when at least one slot is "
            "occupied. That is capability vs. an observed slot, not who wrote it."
        ),
        "sparql": PREFIX
        + """
SELECT ?obj ?name ?type ?presentValue ?relinquishDefault
       ?activePriority ?activePriorityName
WHERE {
  ?device a bacnet:Device ;
          bacnet:contains ?obj .
  ?obj bacnet:priority-array ?pa .
  OPTIONAL { ?obj bacnet:object-name ?name }
  OPTIONAL { ?obj bacnet:object-type ?type }
  OPTIONAL { ?obj bacnet:present-value ?presentValue }
  OPTIONAL { ?obj bacnet:relinquish-default ?relinquishDefault }
  OPTIONAL { ?obj scan:activePriority ?activePriority }
  OPTIONAL { ?obj scan:activePriorityName ?activePriorityName }
}
ORDER BY ?obj
""",
    },
    # q3_winning_slot asks: for objects that currently hold at least one slot
    # (scan:activePriority), what is the Clause 19 winner and does present-value
    # match that held slot? The slot number is the scan-time index into the RDF
    # list (SPARQL cannot cheaply recover list position). heldSlotValue is any
    # non-null list element: the commanded value, not a writer.
    # Effective command != writer identity.
    #
    # Bench return: 3 rows. heldSlotValue walked from the RDF list matches
    # present-value on each row.
    #
    #   C06-0-10VDC-O   analog-output,10032  winning slot 8   manual-operator  pv 12.0   default 0.0   held 12.0
    #   ACTUATOR-0      analog-output,2466   winning slot 8   manual-operator  pv 88.0   default 0.0   held 88.0
    #   STAT ZN WC-ADJ  analog-value,10011   winning slot 16  available        pv 67.58999633789062  default 0.0  held 67.58999633789062
    #
    {
        "id": "q3_winning_slot",
        "title": "Active priority slot / effective command (BACnet winner)",
        "about": (
            "BACnet present-value is the lowest-numbered non-null priority slot; "
            "if every slot is Null, it is the relinquish-default. This query "
            "returns objects that currently hold at least one slot "
            "(scan:activePriority). The slot number is the scan-time index into "
            "the RDF list (SPARQL cannot cheaply recover list position). "
            "heldSlotValue is any non-null list element; it is the commanded "
            "value, not a writer."
        ),
        "sparql": PREFIX
        + """
SELECT ?obj ?name ?activePriority ?activePriorityName
       ?presentValue ?relinquishDefault ?heldSlotValue
WHERE {
  ?device a bacnet:Device ;
          bacnet:contains ?obj .
  ?obj scan:activePriority ?activePriority ;
       bacnet:object-name ?name .
  OPTIONAL { ?obj scan:activePriorityName ?activePriorityName }
  OPTIONAL { ?obj bacnet:present-value ?presentValue }
  OPTIONAL { ?obj bacnet:relinquish-default ?relinquishDefault }
  OPTIONAL {
    ?obj bacnet:priority-array/rdf:rest*/rdf:first ?slotNode .
    ?slotNode ?slotPred ?heldSlotValue .
    FILTER(?slotPred != rdf:type)
    FILTER(?slotPred != bacnet:null)
    FILTER(?heldSlotValue != bacnet:Null)
  }
}
ORDER BY ?obj
""",
    },
    # q4_refs_and_provenance asks honestly for scan:refersTo and
    # bacnet:value-source (empty is a real result) plus the prov:Activity and
    # how each device was reached. Network reachability is not a supervisory write.
    #
    # Bench return: 4 rows. The refersTo and value-source unions matched nothing
    # (no extra empty rows; SPARQL UNION only emits when the pattern matches).
    #   scan:refersTo         0   this bench has no schedule, calendar, trend-log,
    #                            loop, notification-class, or event-enrollment
    #                            objects, and every device-address-binding is rdf:nil
    #   bacnet:value-source   0   no writer-attribution triples; FEC rev 9 lacks
    #                            value-source and last-command-time
    #
    # What did return:
    #   scan-activity      scan:scan/20261110T150953Z  started 2026-11-10T15:09:53+00:00
    #                      tool "bacnet_site_scan.py, bacpypes3 0.0.110"
    #   device-reachedVia  bacnet://0      via scan:router/192.168.204.200  net 28271
    #   device-reachedVia  bacnet://5007   via scan:router/192.168.204.200  net 2000
    #   device-local       bacnet://54545  address 192.168.204.12  (no reachedVia)
    #
    {
        "id": "q4_refs_and_provenance",
        "title": "Supervisory references and scan provenance",
        "about": (
            "scan:refersTo and bacnet:value-source are the properties that would "
            "link a supervisory object (schedule, trend log, loop) or name a "
            "writer. They are queried honestly: empty results mean the saved "
            "graph does not contain them. The other unions are what this scan "
            "does have: the prov:Activity and how each device was reached."
        ),
        "sparql": PREFIX
        + """
SELECT ?kind ?subject ?related ?detail
WHERE {
  {
    BIND("refersTo" AS ?kind)
    ?subject scan:refersTo ?related .
    BIND("" AS ?detail)
  }
  UNION {
    BIND("value-source" AS ?kind)
    ?subject bacnet:value-source ?related .
    BIND("" AS ?detail)
  }
  UNION {
    BIND("scan-activity" AS ?kind)
    ?subject a prov:Activity ;
             scan:tool ?detail ;
             prov:startedAtTime ?related .
  }
  UNION {
    BIND("device-reachedVia" AS ?kind)
    ?subject a bacnet:Device ;
             scan:reachedVia ?related ;
             scan:onNetwork ?detail .
  }
  UNION {
    BIND("device-local" AS ?kind)
    ?subject a bacnet:Device ;
             scan:address ?detail .
    FILTER NOT EXISTS { ?subject scan:reachedVia ?any }
    OPTIONAL { ?subject scan:onNetwork ?related }
  }
}
ORDER BY ?kind ?subject
""",
    },
    # q5_nonstandard_terms asks: every predicate or rdf:type used in the graph
    # whose namespace is not bacnet / rdf / rdfs / xsd. Those are the scan's own
    # extensions (scan:, prov:) or anything unexpected. Useful for reviewing what
    # a downstream consumer must understand beyond the BACnet ontology.
    # Bench return: scan: and prov: terms only (activePriority, linkLayer,
    # onNetwork, reachedVia, propertyNotRead, tool, readAt, Network, Router, ...).
    #
    {
        "id": "q5_nonstandard_terms",
        "title": "Terms outside the standard BACnet / RDF / RDFS / XSD namespaces",
        "about": (
            "Lists each predicate or class IRI that is not under the BACnet "
            "ontology, rdf, rdfs, or xsd. The scan namespace (urn:bacnet-site-scan:) "
            "and prov: are expected here; anything else deserves a closer look."
        ),
        "sparql": PREFIX
        + """
SELECT DISTINCT ?kind ?term
WHERE {
  {
    BIND("predicate" AS ?kind)
    ?s ?term ?o .
  }
  UNION {
    BIND("type" AS ?kind)
    ?s a ?term .
  }
  FILTER(
    !STRSTARTS(STR(?term), "http://data.ashrae.org/bacnet/2024#")
    && !STRSTARTS(STR(?term), "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    && !STRSTARTS(STR(?term), "http://www.w3.org/2000/01/rdf-schema#")
    && !STRSTARTS(STR(?term), "http://www.w3.org/2001/XMLSchema#")
  )
}
ORDER BY ?kind ?term
""",
    },
    # q6_class_chain asks: how many objects of each class, straight from rdf:type
    # (no RDFS reasoner). BACpypes3 #193 types every class in the chain, so an
    # analog input is both bacnet:AnalogInputObject and bacnet:Object, and the
    # class names follow csml2rdf (MultistateValueObject, not MultiState...).
    # Bench return: 11 rows, no reasoner.
    #
    #   bacnet:Object                 72   bacnet:FileObject             6
    #   bacnet:AnalogValueObject      33   bacnet:BinaryOutputObject     5
    #   bacnet:MultistateValueObject   9   bacnet:AnalogOutputObject     4
    #   bacnet:AnalogInputObject       7   bacnet:DeviceObject           3
    #   bacnet:BinaryInputObject       2   bacnet:BinaryValueObject      2
    #   bacnet:NetworkPortObject       1
    #
    # No bacnet:ProprietaryObject rows: every object type on this bench is standard.
    #
    {
        "id": "q6_class_chain",
        "title": "Objects per class from rdf:type, no reasoner",
        "about": (
            "Counts objects per rdf:type. Every object is also a bacnet:Object, so "
            "the Object row equals the sum of the specific classes. Object types "
            "with no standard class show up as bacnet:ProprietaryObject."
        ),
        "sparql": PREFIX
        + """
SELECT ?class (COUNT(DISTINCT ?obj) AS ?objects)
WHERE {
  ?device a bacnet:Device ;
          bacnet:contains ?obj .
  ?obj a ?class .
}
GROUP BY ?class
ORDER BY DESC(?objects) ?class
""",
    },
    # q7_value_strings asks: the device clock and identifiers in the csml2rdf
    # string forms. local-date is "YYYY-MM-DD D" (D = day of week, 1 = Monday),
    # local-time is "HH:MM:SS.hh", object-identifier is "type,instance".
    # A device that does not support local-date / local-time has no row values.
    #
    # Bench return: 3 rows. Only device 5007 answered local-date / local-time
    # (its clock is unset, hence 1970).
    #
    #   bacnet://0      device,0
    #   bacnet://5007   device,5007    1970-02-23 1   18:37:29.85   1 (Monday)
    #   bacnet://54545  device,54545
    #
    {
        "id": "q7_value_strings",
        "title": "Device clock and object identifiers as csml2rdf strings",
        "about": (
            "local-date, local-time and object-identifier are plain strings that match "
            "the csml2rdf shape patterns. STRLEN / SUBSTR work on them without casts."
        ),
        "sparql": PREFIX
        + """
SELECT ?device ?objectIdentifier ?localDate ?localTime ?dayOfWeek
WHERE {
  ?device a bacnet:Device ;
          bacnet:contains ?devObj .
  ?devObj a bacnet:DeviceObject ;
          bacnet:object-identifier ?objectIdentifier .
  OPTIONAL { ?devObj bacnet:local-date ?localDate .
             BIND(SUBSTR(STR(?localDate), 12, 1) AS ?dayOfWeek) }
  OPTIONAL { ?devObj bacnet:local-time ?localTime }
}
ORDER BY ?device
""",
    },
]


def compact(value) -> str:
    """Shorten IRIs for console output. None / unbound -> empty string."""
    if value is None:
        return ""
    text = str(value)
    replacements = (
        ("http://data.ashrae.org/bacnet/2024#", "bacnet:"),
        ("urn:bacnet-site-scan:", "scan:"),
        ("http://www.w3.org/ns/prov#", "prov:"),
        ("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:"),
        ("http://www.w3.org/2001/XMLSchema#", "xsd:"),
        ("bacnet://", "bacnet://"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def print_table(columns, rows) -> None:
    rendered = [[compact(row[c]) for c in columns] for row in rows]
    widths = [len(c) for c in columns]
    for rendered_row in rendered:
        for i, cell in enumerate(rendered_row):
            widths[i] = min(max(widths[i], len(cell)), 56)
    header = "  ".join(name.ljust(widths[i]) for i, name in enumerate(columns))
    print(header)
    print("  ".join("-" * w for w in widths))
    for rendered_row in rendered:
        print(
            "  ".join(
                cell[: widths[i]].ljust(widths[i]) for i, cell in enumerate(rendered_row)
            )
        )



DEFAULT_SHAPES = HERE / "object_basics.ttl"


LEGACY_BACNET = "http://data.ashrae.org/bacnet/"
BACNET_2024 = "http://data.ashrae.org/bacnet/2024#"


def upgrade_legacy_namespace(graph: Graph) -> int:
    """Move terms in the pre-#193 http://data.ashrae.org/bacnet/ namespace to
    http://data.ashrae.org/bacnet/2024# so older scans still answer the
    queries. Only IRIs and literal datatypes are renamed; values are not
    re-encoded (upgrade_ttl_2024.py does that). Returns triples changed."""
    from rdflib import Literal, URIRef

    def move(term):
        if isinstance(term, URIRef):
            text = str(term)
            if text.startswith(LEGACY_BACNET) and not text.startswith(BACNET_2024):
                return URIRef(BACNET_2024 + text[len(LEGACY_BACNET):])
        elif isinstance(term, Literal) and term.datatype is not None:
            text = str(term.datatype)
            if text.startswith(LEGACY_BACNET) and not text.startswith(BACNET_2024):
                return Literal(str(term), datatype=URIRef(BACNET_2024 + text[len(LEGACY_BACNET):]))
        return term

    changed = []
    for triple in graph:
        moved = tuple(move(t) for t in triple)
        if moved != triple:
            changed.append((triple, moved))
    for old, new in changed:
        graph.remove(old)
        graph.add(new)
    if changed:
        graph.bind("bacnet", BACNET_2024, replace=True)
    return len(changed)




def infer_contained_object_types(graph: Graph) -> int:
    """Type anything bacnet:contains as bacnet:Object (older-scan fallback)."""
    from rdflib import Namespace, RDF

    bacnet = Namespace("http://data.ashrae.org/bacnet/2024#")
    added = 0
    for obj in set(graph.objects(None, bacnet.contains)):
        if (obj, RDF.type, bacnet.Object) not in graph:
            graph.add((obj, RDF.type, bacnet.Object))
            added += 1
    return added


def load_shacl_engine():
    """Prefer pyshifty when installed; otherwise pyshacl. Both are optional."""
    try:
        from pyshifty import validate as shacl_validate  # type: ignore

        return shacl_validate, "pyshifty"
    except ImportError:
        pass
    try:
        from pyshacl import validate as shacl_validate  # type: ignore

        return shacl_validate, "pyshacl"
    except ImportError:
        return None, None


def run_shacl(graph: Graph, shapes_path: Path) -> int:
    """Run object-basics shapes. Returns 0 on conformant, 1 otherwise.
    If no SHACL engine is installed, prints a skip note and returns 0.
    """
    print()
    print("=" * 78)
    print("shacl_object_basics: object-name, description (non-blank), analog units")
    print(
        "Optional check. A blank string is not the same as a missing property; "
        "the shapes require a non-whitespace value (sh:pattern \\S). "
        "For a per-object CSV and counts by cause, use completeness_report.py."
    )
    if not shapes_path.is_file():
        print(f"Shapes file not found: {shapes_path}")
        return 1
    fn, engine_name = load_shacl_engine()
    if fn is None:
        print("No SHACL engine installed; skip with: pip install pyshacl")
        print("(pyshifty is optional and usually faster, if you have it)")
        return 0

    added = infer_contained_object_types(graph)
    if added:
        print(f"Inferred rdf:type bacnet:Object on {added} contained object(s)")
    shapes = Graph().parse(str(shapes_path), format="turtle")
    print(f"SHACL engine: {engine_name}  shapes: {shapes_path}")
    kwargs = dict(
        shacl_graph=shapes,
        inference="rdfs",
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
        inplace=False,
    )
    try:
        conforms, results_graph, results_text = fn(graph, **kwargs)
    except TypeError:
        conforms, results_graph, results_text = fn(graph, shapes)
    from rdflib.namespace import SH
    focus = {o for s, p, o in results_graph.triples((None, SH.focusNode, None))}
    print(f"Conforms: {conforms}")
    print(f"Focus nodes with violations: {len(focus)}")
    if results_text:
        lines = str(results_text).strip().splitlines()
        for line in lines[:40]:
            print(line)
        if len(lines) > 40:
            print(f"... ({len(lines) - 40} more lines)")
    return 0 if conforms else 1


def run_csml(graph: Graph, csml_path: Path) -> int:
    """Validate against the csml2rdf ontology shapes (bacnet.ttl from
    https://github.com/JoelBender/csml2rdf). The ontology is merged into the
    data so enumeration values (bacnet:EngineeringUnits.*) resolve their
    classes. Prints a count per constraint and path. Returns 0 on conformant."""
    from collections import Counter
    from rdflib.namespace import RDF, SH

    print()
    print("=" * 78)
    print(f"csml2rdf shapes: {csml_path}")
    if not csml_path.is_file():
        print("Not found. Download it with:")
        print("  curl -LO https://raw.githubusercontent.com/JoelBender/csml2rdf/main/bacnet.ttl")
        return 1
    fn, engine_name = load_shacl_engine()
    if fn is None:
        print("No SHACL engine installed; skip with: pip install pyshacl")
        return 0
    shapes = Graph().parse(str(csml_path), format="turtle")
    conforms, results_graph, _ = fn(graph + shapes, shacl_graph=shapes, inference="none")
    counts = Counter()
    examples = {}
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        focus = str(results_graph.value(result, SH.focusNode))
        if not focus.startswith("bacnet://"):
            continue  # ontology nodes, not scan data
        key = (
            str(results_graph.value(result, SH.sourceConstraintComponent)).rsplit("#", 1)[-1],
            compact(results_graph.value(result, SH.resultPath)),
        )
        counts[key] += 1
        examples.setdefault(key, (focus, compact(results_graph.value(result, SH.value))))
    print(f"SHACL engine: {engine_name}  conforms: {conforms}  results on scan nodes: {sum(counts.values())}")
    for (constraint, path), count in counts.most_common():
        focus, value = examples[(constraint, path)]
        print(f"  {count:4d}  {constraint:32s} {path:40s} e.g. {focus} {value}")
    return 0 if conforms else 1


def run_demos(ttl_path: Path, do_shacl: bool = False, shapes_path: Path | None = None,
              csml_path: Path | None = None) -> int:
    if not ttl_path.is_file():
        print(f"Turtle file not found: {ttl_path}", file=sys.stderr)
        return 1

    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")
    legacy = upgrade_legacy_namespace(graph)
    print(f"Graph: {ttl_path}  ({len(graph)} triples)")
    if legacy:
        print(f"Older scan: moved {legacy} triple(s) to {BACNET_2024} (run upgrade_ttl_2024.py to re-encode)")
    print(
        "Read-only SPARQL demo. A held priority slot is not writer identity; "
        "scan:refersTo / value-source are reported only when present in the graph."
    )

    for query in QUERIES:
        print()
        print("=" * 78)
        print(f"{query['id']}: {query['title']}")
        print(query["about"])
        print()
        print(query["sparql"].rstrip())
        print()
        print("Python:")
        print("    rows = list(graph.query(query_text))")
        rows = list(graph.query(query["sparql"]))
        print()
        print(f"Returned {len(rows)} row(s)")
        if not rows:
            print(
                "(empty: this graph has no matching triples; "
                "that is a real result, not a failed query)"
            )
            continue
        columns = [str(var) for var in rows[0].labels]
        print_table(columns, rows)

    rc = 0
    if do_shacl:
        rc = run_shacl(graph, shapes_path or DEFAULT_SHAPES)
    if csml_path is not None:
        rc = run_csml(graph, csml_path) or rc
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run offline SPARQL demos (and optional SHACL) against a saved "
            "BACnet site-scan Turtle file. Does not contact the network or "
            "write to any device."
        )
    )
    parser.add_argument(
        "--ttl",
        type=Path,
        default=DEFAULT_TTL,
        help=f"Turtle file to query (default: {DEFAULT_TTL})",
    )
    parser.add_argument(
        "--shacl",
        action="store_true",
        help="also run object_basics.ttl with pyshifty if installed, else pyshacl",
    )
    parser.add_argument(
        "--shapes",
        type=Path,
        default=DEFAULT_SHAPES,
        help=f"shapes Turtle for --shacl (default: {DEFAULT_SHAPES})",
    )
    parser.add_argument(
        "--csml",
        type=Path,
        default=None,
        help="also validate against csml2rdf bacnet.ttl (path to a downloaded copy)",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run_demos(
        args.ttl.resolve(),
        do_shacl=args.shacl,
        shapes_path=args.shapes.resolve(),
        csml_path=args.csml.resolve() if args.csml else None,
    )


if __name__ == "__main__":
    sys.exit(main())
