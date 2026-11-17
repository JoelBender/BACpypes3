#!/usr/bin/env python
"""Fixture tests for completeness_report.py.

A synthetic blank description is injected in an in-memory graph. Nothing is
written to a live BACnet device.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef

import completeness_report as cr

BACNET = Namespace("http://data.ashrae.org/bacnet/2024#")
HERE = Path(__file__).resolve().parent


def _object(graph: Graph, device: URIRef, typ: str, inst: int, name: str | None, desc, units=None, typed=True):
    """Add one contained object. desc=None means missing; desc='' means blank."""
    obj = URIRef(f"{device}/{typ},{inst}")
    graph.add((device, BACNET.contains, obj))
    if typed:
        graph.add((obj, RDF.type, BACNET.Object))
    graph.add((obj, BACNET["object-type"], BACNET[f"ObjectType.{typ}"]))
    graph.add((obj, BACNET["object-identifier"], Literal(f"{typ},{inst}")))
    if name is not None:
        graph.add((obj, BACNET["object-name"], Literal(name)))
    if desc is not None:
        graph.add((obj, BACNET.description, Literal(desc)))
    if units is not None:
        graph.add((obj, BACNET.units, BACNET[f"EngineeringUnits.{units}"]))
    return obj


def fixture_graph() -> Graph:
    g = Graph()
    dev = URIRef("bacnet://1")
    g.add((dev, RDF.type, BACNET.Device))
    g.add((dev, BACNET["device-instance"], Literal(1)))
    # complete analog
    _object(g, dev, "analog-input", 1, "OA-T-SENSOR-1", "Outdoor air dry-bulb temperature", "degrees-fahrenheit")
    # present but blank description (the case this test exists for)
    _object(g, dev, "analog-value", 2, "Priority", "", "no-units")
    # whitespace-only name and description
    _object(g, dev, "analog-value", 3, "   ", "  \t  ", "no-units")
    # missing description triple entirely
    _object(g, dev, "analog-input", 4, "OA-H", None, "percent-relative-humidity")
    # missing object-name
    _object(g, dev, "binary-input", 5, None, "Current sensing")
    # older scan: contained, but no rdf:type bacnet:Object
    _object(g, dev, "analog-output", 6, "DAMPER-CMD-01", "Damper command output", "percent", typed=False)
    return g


class CompletenessReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = Graph().parse(str(HERE / "object_basics.ttl"), format="turtle")
        cls.strict = Graph().parse(str(HERE / "object_basics_strict.ttl"), format="turtle")
        cls.reqs = cr.load_requirements(cls.shapes)
        cls.strict_reqs = cr.load_requirements(cls.strict)

    def setUp(self):
        self.graph = fixture_graph()
        cr.infer_contained_object_types(self.graph)
        self.rows = {r["ObjectIdentifier"]: r for r in cr.build_rows(self.graph, self.reqs)}

    def test_shapes_load_name_description_units(self):
        keys = [r["key"] for r in self.reqs]
        self.assertEqual(keys, ["object-name", "description", "units"])
        name = next(r for r in self.reqs if r["key"] == "object-name")
        self.assertEqual(name["pattern"], r"\S")
        units = next(r for r in self.reqs if r["key"] == "units")
        self.assertEqual(units["applies_to"], ["analog-input", "analog-output", "analog-value"])

    def test_complete_analog_passes(self):
        row = self.rows["analog-input,1"]
        self.assertEqual(row["NameStatus"], "pass")
        self.assertEqual(row["DescriptionStatus"], "pass")
        self.assertEqual(row["UnitsStatus"], "pass")
        self.assertEqual(row["RowStatus"], "complete")
        self.assertEqual(row["Failed"], "")

    def test_synthetic_blank_description_is_blank_not_missing(self):
        row = self.rows["analog-value,2"]
        self.assertEqual(row["Name"], "Priority")
        self.assertEqual(row["NameStatus"], "pass")
        self.assertEqual(row["Description"], "")
        self.assertEqual(row["DescriptionStatus"], "blank")
        self.assertNotEqual(row["DescriptionStatus"], "missing")
        self.assertIn("description:blank", row["Failed"])
        self.assertEqual(row["RowStatus"], "partial")

    def test_whitespace_only_is_blank(self):
        row = self.rows["analog-value,3"]
        self.assertEqual(row["NameStatus"], "blank")
        self.assertEqual(row["DescriptionStatus"], "blank")
        self.assertIn("object-name:blank", row["Failed"])
        self.assertIn("description:blank", row["Failed"])

    def test_missing_description_is_missing_not_blank(self):
        row = self.rows["analog-input,4"]
        self.assertEqual(row["NameStatus"], "pass")
        self.assertEqual(row["Description"], "")
        self.assertEqual(row["DescriptionStatus"], "missing")
        self.assertNotEqual(row["DescriptionStatus"], "blank")
        self.assertIn("description:missing", row["Failed"])

    def test_missing_object_name(self):
        row = self.rows["binary-input,5"]
        self.assertEqual(row["NameStatus"], "missing")
        self.assertEqual(row["DescriptionStatus"], "pass")
        self.assertEqual(row["UnitsStatus"], "n/a")
        self.assertIn("object-name:missing", row["Failed"])

    def test_inference_types_contained_objects_without_rdf_type(self):
        g = fixture_graph()
        obj = URIRef("bacnet://1/analog-output,6")
        self.assertNotIn((obj, RDF.type, BACNET.Object), g)
        added = cr.infer_contained_object_types(g)
        self.assertGreaterEqual(added, 1)
        self.assertIn((obj, RDF.type, BACNET.Object), g)
        rows = {r["ObjectIdentifier"]: r for r in cr.build_rows(g, self.reqs)}
        self.assertIn("analog-output,6", rows)
        self.assertEqual(rows["analog-output,6"]["RowStatus"], "complete")

    def test_without_inference_untyped_object_is_still_in_contains_walk(self):
        # iter_objects walks bacnet:contains, so the row is present either way;
        # inference is what makes sh:targetClass work for a SHACL engine.
        g = fixture_graph()
        rows = {r["ObjectIdentifier"]: r for r in cr.build_rows(g, self.reqs)}
        self.assertIn("analog-output,6", rows)

    def test_units_not_applied_to_binary(self):
        self.assertEqual(self.rows["binary-input,5"]["UnitsStatus"], "n/a")

    def test_filters_complete_partial_and_search(self):
        all_rows = list(self.rows.values())
        complete = cr.filter_rows(all_rows, True, False, "")
        partial = cr.filter_rows(all_rows, False, True, "")
        self.assertTrue(complete)
        self.assertTrue(partial)
        self.assertTrue(all(r["RowStatus"] == "complete" for r in complete))
        self.assertTrue(all(r["RowStatus"] == "partial" for r in partial))
        self.assertEqual(len(complete) + len(partial), len(all_rows))
        searched = cr.filter_rows(all_rows, False, False, "Priority")
        self.assertEqual([r["ObjectIdentifier"] for r in searched], ["analog-value,2"])

    def test_strict_shapes_flag_too_short(self):
        rows = {r["ObjectIdentifier"]: r for r in cr.build_rows(self.graph, self.strict_reqs)}
        # "OA-H" is 4 chars; description missing
        short = rows["analog-input,4"]
        self.assertEqual(short["NameStatus"], "too-short")
        self.assertIn("object-name:too-short", short["Failed"])
        # complete long name/description still passes
        ok = rows["analog-input,1"]
        self.assertEqual(ok["NameStatus"], "pass")
        self.assertEqual(ok["DescriptionStatus"], "pass")
        # blank stays blank (not too-short) for the synthetic empty description
        blank = rows["analog-value,2"]
        self.assertEqual(blank["DescriptionStatus"], "blank")

    def test_summary_counts_blank_and_missing(self):
        text = cr.summarize(list(self.rows.values()), self.reqs)
        self.assertIn("complete", text)
        self.assertIn("partial", text)
        self.assertIn("blank", text)
        self.assertIn("missing", text)

    def test_run_writes_csv_from_temp_ttl(self):
        g = fixture_graph()
        with tempfile.TemporaryDirectory() as tmp:
            ttl = Path(tmp) / "fixture.ttl"
            out = Path(tmp) / "fixture_completeness.csv"
            g.serialize(str(ttl), format="turtle")
            rc = cr.run(
                ttl_path=ttl,
                shapes_path=HERE / "object_basics.ttl",
                out_path=out,
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.is_file())
            body = out.read_text(encoding="utf-8")
            self.assertIn("DescriptionStatus", body)
            self.assertIn("blank", body)
            self.assertIn("missing", body)


if __name__ == "__main__":
    unittest.main()
