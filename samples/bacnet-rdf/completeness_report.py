#!/usr/bin/env python
"""
completeness_report.py - per-object completeness report for a site-scan Turtle file.

Read-only. This script never opens a BACnet socket and never writes to a device.
It parses a saved graph and writes one CSV row per BACnet object.

The default engine is a fast rdflib/SPARQL path; no SHACL library is required.
Pass --shacl to also run a SHACL engine: pyshifty if it is installed (optional,
usually faster), otherwise pyshacl if that is installed.

    python completeness_report.py
    python completeness_report.py --ttl site_scan.ttl --out site_scan_completeness.csv
    python completeness_report.py --partial-only
    python completeness_report.py --complete-only
    python completeness_report.py --search Priority
    python completeness_report.py --shapes object_basics_strict.ttl
    python completeness_report.py --shacl

Status values:
  pass       property is present and meets the shapes (non-blank, min length)
  blank      property is present but empty or whitespace-only
  missing    no triple for that property
  too-short  present and non-blank, but shorter than sh:minLength
  n/a        this check does not apply to this object (for example units on a
             binary object)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from rdflib import Graph, Literal, Namespace, RDF, URIRef

HERE = Path(__file__).resolve().parent
DEFAULT_TTL = HERE / "site_scan.ttl"
DEFAULT_SHAPES = HERE / "object_basics.ttl"

BACNET = Namespace("http://data.ashrae.org/bacnet/2024#")
SH = Namespace("http://www.w3.org/ns/shacl#")
REPORT = Namespace("urn:bacnet-site-scan:report:")
XS = "http://www.w3.org/2001/XMLSchema#"

NON_BLANK = re.compile(r"\S")


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- shapes
def load_requirements(shapes: Graph) -> List[Dict[str, Any]]:
    """Read property checks from a shapes graph (a practical SHACL subset).

    Honors sh:path, sh:name, sh:order, sh:minCount, sh:pattern, sh:minLength,
    and the optional report:appliesWhenObjectType hint used for analog units.
    Rule-only shapes (no sh:property) are ignored here.
    """
    reqs: List[Dict[str, Any]] = []
    seen_paths = set()
    for shape in shapes.subjects(RDF.type, SH.NodeShape):
        for ps in shapes.objects(shape, SH.property):
            path = shapes.value(ps, SH.path)
            if path is None:
                continue
            applies = [
                str(v).strip()
                for v in shapes.objects(ps, REPORT.appliesWhenObjectType)
                if str(v).strip()
            ]
            pattern = shapes.value(ps, SH.pattern)
            min_length = shapes.value(ps, SH.minLength)
            min_count = shapes.value(ps, SH.minCount)
            order = shapes.value(ps, SH.order)
            name = shapes.value(ps, SH.name)
            key = (str(path), tuple(sorted(applies)))
            if key in seen_paths:
                continue
            seen_paths.add(key)
            reqs.append(
                {
                    "path": path,
                    "key": str(name or _local_name(path)),
                    "order": int(order) if order is not None else 99,
                    "min_count": int(min_count) if min_count is not None else 0,
                    "pattern": str(pattern) if pattern is not None else "",
                    "min_length": int(min_length) if min_length is not None else 0,
                    "applies_to": applies,
                }
            )
    reqs.sort(key=lambda r: (r["order"], r["key"]))
    return reqs


def _local_name(term: Any) -> str:
    text = str(term)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rsplit("/", 1)[-1]
    if ":" in text:
        return text.rsplit(":", 1)[-1]
    return text


def object_type_name(term: Any) -> str:
    """'analog-value' from bacnet:ObjectType.analog-value or a plain string."""
    text = _local_name(term)
    if "ObjectType." in text:
        return text.split("ObjectType.", 1)[1]
    return text


# ---------------------------------------------------------------- graph helpers
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
    """Type anything a device (or other node) bacnet:contains as bacnet:Object.

    This is the fallback for older scans that have no rdf:type bacnet:Object
    triple. Returns how many type triples were added.
    """
    added = 0
    for obj in set(graph.objects(None, BACNET.contains)):
        if (obj, RDF.type, BACNET.Object) not in graph:
            graph.add((obj, RDF.type, BACNET.Object))
            added += 1
    return added


def literal_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Literal):
        return str(value)
    return str(value)


def first_value(graph: Graph, subject: Any, predicate: Any) -> Optional[Any]:
    return graph.value(subject, predicate)


def requirement_applies(req: Dict[str, Any], type_name: str) -> bool:
    if not req["applies_to"]:
        return True
    return type_name in req["applies_to"]


def property_status(graph: Graph, obj: Any, req: Dict[str, Any]) -> Tuple[str, str]:
    """Return (value, status) for one required property on one object."""
    values = list(graph.objects(obj, req["path"]))
    if not values:
        return "", "missing"
    text = literal_text(values[0])
    if not NON_BLANK.search(text):
        # present but empty / whitespace: blank, even if minLength is also set
        if req["pattern"] and not re.search(req["pattern"], text):
            return text, "blank"
        if req["min_count"] or req["pattern"] or req["min_length"]:
            return text, "blank"
        return text, "pass"
    if req["pattern"] and not re.search(req["pattern"], text):
        return text, "too-short"
    if req["min_length"] and len(text) < req["min_length"]:
        return text, "too-short"
    return text, "pass"


def device_instance(graph: Graph, device: Any) -> str:
    inst = graph.value(device, BACNET["device-instance"])
    if inst is not None:
        return str(inst)
    text = str(device)
    if text.startswith("bacnet://"):
        return text.split("bacnet://", 1)[1].split("/", 1)[0]
    return text


def object_identifier_parts(graph: Graph, obj: Any, type_name: str) -> Tuple[str, str, str]:
    oid = graph.value(obj, BACNET["object-identifier"])
    raw = literal_text(oid)
    if "," in raw:
        typ, _, inst = raw.partition(",")
        return typ or type_name, inst, raw
    inst = graph.value(obj, BACNET["object-instance"])
    if inst is not None:
        ident = f"{type_name},{inst}" if type_name else str(inst)
        return type_name, str(inst), ident
    return type_name, "", raw


def iter_objects(graph: Graph) -> List[Tuple[Any, Any]]:
    """(device, object) pairs, including the device object itself."""
    rows = list(graph.subject_objects(BACNET.contains))
    rows.sort(key=lambda pair: (str(pair[0]), str(pair[1])))
    return rows


# ---------------------------------------------------------------- report
def build_rows(
    graph: Graph, reqs: Sequence[Dict[str, Any]]
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for device, obj in iter_objects(graph):
        typ_term = first_value(graph, obj, BACNET["object-type"])
        type_name = object_type_name(typ_term) if typ_term is not None else ""
        typ, inst, ident = object_identifier_parts(graph, obj, type_name)
        row: Dict[str, str] = {
            "DeviceID": device_instance(graph, device),
            "ObjType": typ or type_name,
            "ObjInst": inst,
            "ObjectIdentifier": ident or f"{typ},{inst}".strip(","),
        }
        failed: List[str] = []
        for req in reqs:
            col = req["key"]
            status_col = _status_column(col)
            value_col = _value_column(col)
            if not requirement_applies(req, typ or type_name):
                row[value_col] = ""
                row[status_col] = "n/a"
                continue
            value, status = property_status(graph, obj, req)
            row[value_col] = value
            row[status_col] = status
            if status not in ("pass", "n/a"):
                failed.append(f"{col}:{status}")
        row["Failed"] = ";".join(failed)
        row["RowStatus"] = "complete" if not failed else "partial"
        rows.append(row)
    return rows


def _value_column(key: str) -> str:
    return {
        "object-name": "Name",
        "description": "Description",
        "units": "Units",
    }.get(key, key)


def _status_column(key: str) -> str:
    return _value_column(key) + "Status"


def csv_fields(reqs: Sequence[Dict[str, Any]]) -> List[str]:
    fields = ["DeviceID", "ObjType", "ObjInst", "ObjectIdentifier"]
    for req in reqs:
        fields.append(_value_column(req["key"]))
        fields.append(_status_column(req["key"]))
    fields.extend(["Failed", "RowStatus"])
    return fields


def filter_rows(
    rows: Sequence[Dict[str, str]],
    complete_only: bool,
    partial_only: bool,
    search: str,
) -> List[Dict[str, str]]:
    out = list(rows)
    if complete_only:
        out = [r for r in out if r["RowStatus"] == "complete"]
    if partial_only:
        out = [r for r in out if r["RowStatus"] == "partial"]
    if search:
        needle = search.casefold()
        keep: List[Dict[str, str]] = []
        for row in out:
            hay = " ".join(row.values()).casefold()
            if needle in hay:
                keep.append(row)
        out = keep
    return out


def summarize(rows: Sequence[Dict[str, str]], reqs: Sequence[Dict[str, Any]]) -> str:
    n = len(rows)
    n_complete = sum(1 for r in rows if r["RowStatus"] == "complete")
    n_partial = n - n_complete
    lines = [
        f"{n} objects: {n_complete} complete, {n_partial} partial",
    ]
    for req in reqs:
        status_col = _status_column(req["key"])
        counts: Counter[str] = Counter(
            r[status_col] for r in rows if r.get(status_col) and r[status_col] != "n/a"
        )
        applicable = sum(counts.values())
        parts = []
        for label in ("missing", "blank", "too-short"):
            if counts.get(label):
                parts.append(f"{counts[label]} {label}")
        n_pass = counts.get("pass", 0)
        extra = f" ({', '.join(parts)})" if parts else ""
        lines.append(
            f"  {req['key']}: {n_pass} pass / {applicable} applicable{extra}"
        )
    return "\n".join(lines)


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------- optional SHACL
def load_shacl_engine():
    """Prefer pyshifty when installed; otherwise pyshacl. Both are optional."""
    try:
        from pyshifty import validate as shacl_validate  # type: ignore

        return shacl_validate, "pyshifty"
    except ImportError:
        pass
    try:
        import pyshifty  # type: ignore

        fn = getattr(pyshifty, "validate", None)
        if callable(fn):
            return fn, "pyshifty"
    except ImportError:
        pass
    try:
        from pyshacl import validate as shacl_validate  # type: ignore

        return shacl_validate, "pyshacl"
    except ImportError:
        return None, None


def run_shacl(data: Graph, shapes: Graph) -> int:
    fn, name = load_shacl_engine()
    if fn is None:
        log("No SHACL engine installed; skip --shacl (pip install pyshacl, or pyshifty).")
        return 0
    log(f"SHACL engine: {name}")
    kwargs = {
        "shacl_graph": shapes,
        "inference": "rdfs",
        "abort_on_first": False,
        "meta_shacl": False,
        "advanced": True,
        "inplace": False,
    }
    try:
        conforms, results_graph, results_text = fn(data, **kwargs)
    except TypeError:
        # pyshifty's validate(data, shapes) positional form
        conforms, results_graph, results_text = fn(data, shapes)
    focus = {o for _, _, o in results_graph.triples((None, SH.focusNode, None))}
    log(f"SHACL conforms: {conforms}")
    log(f"SHACL focus nodes with violations: {len(focus)}")
    if results_text:
        lines = str(results_text).strip().splitlines()
        for line in lines[:40]:
            log(line)
        if len(lines) > 40:
            log(f"... ({len(lines) - 40} more lines)")
    return 0 if conforms else 1


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Write a per-object completeness CSV from a saved BACnet site-scan "
            "Turtle file. Does not contact the network or write to any device."
        )
    )
    p.add_argument("--ttl", type=Path, default=DEFAULT_TTL, help=f"Turtle file (default: {DEFAULT_TTL})")
    p.add_argument(
        "--shapes",
        type=Path,
        default=DEFAULT_SHAPES,
        help=f"SHACL shapes Turtle (default: {DEFAULT_SHAPES})",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="CSV path (default: <ttl stem>_completeness.csv next to the Turtle)",
    )
    filt = p.add_mutually_exclusive_group()
    filt.add_argument("--complete-only", action="store_true", help="write only complete rows")
    filt.add_argument("--partial-only", action="store_true", help="write only partial rows")
    p.add_argument("--search", default="", help="keep rows whose text contains this string (case-insensitive)")
    p.add_argument(
        "--shacl",
        action="store_true",
        help="also run a SHACL engine (pyshifty if installed, else pyshacl)",
    )
    p.add_argument(
        "--no-infer",
        action="store_true",
        help="do not add rdf:type bacnet:Object on bacnet:contains objects",
    )
    return p


def run(
    ttl_path: Path,
    shapes_path: Path,
    out_path: Optional[Path],
    complete_only: bool = False,
    partial_only: bool = False,
    search: str = "",
    do_shacl: bool = False,
    infer: bool = True,
) -> int:
    if not ttl_path.is_file():
        log(f"Turtle file not found: {ttl_path}")
        return 1
    if not shapes_path.is_file():
        log(f"Shapes file not found: {shapes_path}")
        return 1

    started = time.perf_counter()
    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")
    legacy = upgrade_legacy_namespace(graph)
    if legacy:
        log(f"Older scan: moved {legacy} triple(s) to {BACNET_2024}")
    shapes = Graph()
    shapes.parse(str(shapes_path), format="turtle")
    upgrade_legacy_namespace(shapes)
    inferred = infer_contained_object_types(graph) if infer else 0
    reqs = load_requirements(shapes)
    if not reqs:
        log(f"No property shapes found in {shapes_path}")
        return 1

    rows = build_rows(graph, reqs)
    summary_all = summarize(rows, reqs)
    filtered = filter_rows(rows, complete_only, partial_only, search)
    if out_path is None:
        out_path = ttl_path.with_name(ttl_path.stem + "_completeness.csv")
    write_csv(out_path, csv_fields(reqs), filtered)
    elapsed = time.perf_counter() - started

    log(f"Graph: {ttl_path}  ({len(graph)} triples)")
    log(f"Shapes: {shapes_path}")
    if infer:
        log(f"Inferred rdf:type bacnet:Object on {inferred} contained object(s)")
    log("Engine: rdflib/SPARQL (default, no SHACL library required)")
    log(summary_all)
    if complete_only or partial_only or search:
        log(f"Filter: wrote {len(filtered)} of {len(rows)} rows")
    log(f"Wrote {out_path}")
    log(f"Report time {elapsed:.3f}s")

    shacl_rc = 0
    if do_shacl:
        shacl_rc = run_shacl(graph, shapes)
    # CSV write succeeded even if the optional SHACL view does not conform
    # (non-conformance is expected on a real site). Still surface the code.
    return 0 if shacl_rc in (0, 1) else shacl_rc


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        ttl_path=args.ttl.resolve(),
        shapes_path=args.shapes.resolve(),
        out_path=args.out.resolve() if args.out else None,
        complete_only=args.complete_only,
        partial_only=args.partial_only,
        search=args.search,
        do_shacl=args.shacl,
        infer=not args.no_infer,
    )


if __name__ == "__main__":
    sys.exit(main())
