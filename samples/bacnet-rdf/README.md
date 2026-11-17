# BACnet site scan to CSV + RDF Turtle

Read-only scan of a BACnet/IP site (Who-Is, Who-Is-Router-To-Network,
ReadProperty, ReadPropertyMultiple). It never writes to a device.

The scripts write one CSV row per object, a device inventory, an RDF Turtle
graph, a topology table, and a name/description completeness report.

The sample `site_scan.*` files in this directory are a live scan of a small
test bench (3 devices, 72 objects). `site_scan.ttl` is in the csml2rdf
`http://data.ashrae.org/bacnet/2024#` namespace written by
[BACpypes3 #193](https://github.com/JoelBender/BACpypes3/pull/193), now
in **bacpypes3 0.1.0** on PyPI (and on `main`) as of 2026-11-17: every object
carries its class chain (`bacnet:AnalogInputObject`, `bacnet:Object`), object
identifiers are `"type,instance"` strings, and dates and times are strings
that match the csml2rdf patterns. See
[NOTES.md](NOTES.md#bacpypes3-193-csml2rdf-alignment-merged).

## Install

The RDF encoding used here needs the fixes in
[#181](https://github.com/JoelBender/BACpypes3/pull/181),
[#183](https://github.com/JoelBender/BACpypes3/pull/183), and
[#193](https://github.com/JoelBender/BACpypes3/pull/193). Those shipped in
**bacpypes3 0.1.0** on PyPI (2026-11-17), along with Protocol Revision 31.
Install from PyPI:

```bash
pip install "bacpypes3>=0.1.0" ifaddr rdflib
```

Windows (PowerShell):

```powershell
py -3.14 -m venv env
env\Scripts\pip install "bacpypes3>=0.1.0" ifaddr rdflib
```

You do not need to clone BACpypes3 just to get the library. `--check-fix` is
a sanity check: it prints whether the RDF fixes are present and exits 0 only
if they are. Optional extras: `pyshacl` (or `pyshifty`) for `--shacl`.

PyPI 0.0.110 (2026-09-24) predates the fixes; do not use it for this sample.

## Related samples

This directory is a fuller site-scan toolkit (CSV, Turtle, topology,
completeness report, SPARQL demos). For smaller examples already in 0.1.0,
see [`samples/discover-devices-rdf.py`](../discover-devices-rdf.py) (Who-Is
to Device nodes in Turtle) and
[`samples/discover-objects-rdf.py`](../discover-objects-rdf.py) (per-device
object discovery to Turtle).

## Quick start

Run the scripts from this directory (`samples/bacnet-rdf`). Defaults such as
`site_scan.ttl` are resolved relative to the script file, so they also work
if you invoke the scripts from the repo root.

UDP **47808 must be free** on the scanning machine (close YABE, Workbench, and
similar tools first). `--address` is your NIC as `ip/prefix`.

```bash
cd samples/bacnet-rdf
python bacnet_site_scan.py --check-fix
python bacnet_site_scan.py --address 192.168.1.50/24 --discover-only
python bacnet_site_scan.py --address 192.168.1.50/24
python completeness_report.py
python sparql_demos.py
python sparql_demos.py --shacl
python sparql_demos.py --csml bacnet.ttl      # csml2rdf ontology shapes
python upgrade_ttl_2024.py --ttl old.ttl --out old_2024.ttl   # needs bacpypes3 >= 0.1.0 (includes #193)
python test_completeness_report.py
```

## Files

| File | What it is |
|---|---|
| `bacnet_site_scan.py` | Read-only BACnet/IP scanner; writes the CSV, Turtle, and topology files |
| `completeness_report.py` | Offline name/description/units completeness report from a Turtle file |
| `sparql_demos.py` | Seven read-only SPARQL demos against a saved Turtle file |
| `upgrade_ttl_2024.py` | Rewrite an older Turtle file to the `bacnet/2024#` encoding used in bacpypes3 0.1.0 |
| `test_completeness_report.py` | Fixture tests for the completeness report |
| `object_basics.ttl` | Default SHACL/SPARQL requirements (non-blank name and description; units on analog objects) |
| `object_basics_strict.ttl` | Example shapes with minimum name and description lengths |
| `site_scan.csv` | Sample bench scan: one row per object |
| `site_scan_devices.csv` | Sample bench scan: one row per device |
| `site_scan.ttl` | Sample bench scan as RDF Turtle |
| `site_scan_topology.csv` | Sample bench routers, networks, and device placement |
| `site_scan_completeness.csv` | Completeness report for the sample Turtle file |
| `NOTES.md` | Install details, RDF fix background, and ideas that could go upstream |

## Outputs

| File | Contents |
|---|---|
| `site_scan.csv` | One row per object: name, description, present value, units, status flags, the live 16-slot priority array (P1–P16), relinquish default, active priority, and a Command note |
| `site_scan_devices.csv` | One row per device: vendor, model, firmware, segmentation, services, and which properties were not present |
| `site_scan.ttl` | RDF Turtle of the same data in the `bacnet/2024#` namespace, with the `rdf:type` class chain on every object, network layout (`scan:linkLayer`, reachability, routers), reference links, and scan provenance |
| `site_scan_topology.csv` | Routers, networks, and which device sits where |
| `site_scan_completeness.csv` | Per-object completeness report (see below) |

Each run overwrites the last scan unless you pass `--stamp` (timestamped
copies) or `--out-dir`. After writing, the scanner re-reads its files and
exits 0 on PASS or 2 on FAIL (`--no-validate` skips this).

The Command column reports what the priority array shows (`P8 manual-operator`,
`relinquished`, and similar). That is not writer identity; writer identity
needs `value-source` (protocol revision 21+).

## Completeness report

`completeness_report.py` reads a saved Turtle file (no BACnet traffic) and
writes one row per object:

| Column | Meaning |
|---|---|
| DeviceID, ObjType, ObjInst, ObjectIdentifier | Which object |
| Name, Description, Units | Value as scanned (Units is empty when the check does not apply) |
| NameStatus, DescriptionStatus, UnitsStatus | `pass`, `blank`, `missing`, `too-short`, or `n/a` |
| Failed | Semicolon-separated `property:status` that did not pass; empty if complete |
| RowStatus | `complete` or `partial` |

`blank` means the property is present but empty or whitespace. `missing` means
the triple is not in the graph (the device did not return it). Those are
different problems.

```bash
python completeness_report.py --partial-only
python completeness_report.py --complete-only
python completeness_report.py --search Priority
python completeness_report.py --shapes object_basics_strict.ttl
python completeness_report.py --shacl
```

Default requirements live in `object_basics.ttl` (non-blank object-name and
description; units on analog objects). Pass `--shapes` to use another Turtle
file without editing code. `object_basics_strict.ttl` is a labeled **example**
with minimum lengths (name ≥ 12 characters, description ≥ 24).

The default report path is pure rdflib/SPARQL and needs no SHACL library.
`--shacl` is optional: it uses **pyshifty** when that package is installed
(usually faster), otherwise **pyshacl**. Both are optional. Older scans that
lack `rdf:type bacnet:Object` still validate: the report types anything a
device `bacnet:contains` before checking, and the shapes file also has a
SHACL-AF rule for engines that support it.

`python test_completeness_report.py` runs the fixture tests, including a
synthetic blank description. Nothing is written to a live device.

## Speed and large-site use

The scanner is read-only. Stay polite on real networks, especially MS/TP:

| Option | Default | Notes |
|---|---|---|
| `--device-concurrency` | 1 | How many devices to read at once. Leave at 1 when devices share an MS/TP trunk. |
| `--object-concurrency` | 1 | Parallel object reads on one device. Leave at 1 on MS/TP. |
| `--timeout` | 10 | Seconds for a property read before it is skipped and recorded as not read. |
| `--rpm-chunk` | auto | Properties per ReadPropertyMultiple. Auto is 16 on BACnet/IP and 8 on MS/TP. |
| `--pace` | 0 | Optional delay in seconds after each read. Use a small value (for example `0.05`) to ease a busy trunk. |

Start a new site with `--discover-only`, then a full scan at the defaults.
Raise concurrency only for BACnet/IP devices that are not behind a shared
MS/TP link. The script prints a wall-clock elapsed time when it finishes.

The completeness report’s default engine is the faster path for a large
Turtle file. Add `--shacl` only when you also want a SHACL engine report.

## SPARQL demos

`sparql_demos.py` runs seven read-only queries against the saved Turtle
(inventory, commandable objects, active slots, references and provenance,
non-standard terms, objects per class from `rdf:type` with no reasoner, and
the device clock / object identifiers as csml2rdf strings). The queries use
`PREFIX bacnet: <http://data.ashrae.org/bacnet/2024#>`; an older scan in
`http://data.ashrae.org/bacnet/` is moved to 2024# in memory on load. See
the comments in that file for real returns and what a row does and does not
mean. `--csml bacnet.ttl` also validates against the csml2rdf ontology
shapes (download `bacnet.ttl` from
[JoelBender/csml2rdf](https://github.com/JoelBender/csml2rdf)).

## More detail

Install notes for bacpypes3 0.1.0 (which includes #181, #183 and #193),
the RDF fixes this scanner depends on, and ideas that could go upstream,
are in [NOTES.md](NOTES.md).
