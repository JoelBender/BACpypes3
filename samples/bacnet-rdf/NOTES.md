# Install notes and RDF background

This file is the longer reference for installing bacpypes3 and for changes
that could go upstream. Day-to-day use is in [README.md](README.md).

## Get the latest BACpypes3

The RDF fixes this scanner relies on,
[JoelBender/BACpypes3#181](https://github.com/JoelBender/BACpypes3/pull/181)
(merged 2026-11-04), [JoelBender/BACpypes3#183](https://github.com/JoelBender/BACpypes3/pull/183)
(merged 2026-11-06), and [JoelBender/BACpypes3#193](https://github.com/JoelBender/BACpypes3/pull/193)
(merged 2026-11-11 8:55 AM CT as
[`0af7992`](https://github.com/JoelBender/BACpypes3/commit/0af7992192d5ae46bb953c65262273fbcba08df5)),
shipped in **bacpypes3 0.1.0** on PyPI (2026-11-17), along with Protocol
Revision 31. That is the release to install:

```bash
pip install "bacpypes3>=0.1.0" ifaddr rdflib
```

Linux / macOS from a fresh virtual environment:

```bash
python3 -m venv env
env/bin/pip install "bacpypes3>=0.1.0" ifaddr rdflib
env/bin/python bacnet_site_scan.py --check-fix
```

Windows (PowerShell):

```powershell
py -3.14 -m venv env
env\Scripts\pip install "bacpypes3>=0.1.0" ifaddr rdflib
env\Scripts\python bacnet_site_scan.py --check-fix
```

`--check-fix` is a sanity check: it prints whether the #181 / #183 fixes are
present and exits 0 only if they are. Every scan prints the same lines at the
start (including whether the #193 class chain is present). `pip show bacpypes3`
should report 0.1.0 or later. PyPI 0.0.110 (2026-09-24) predates the fixes;
upgrade if that is what you have.

The scanner still unwraps AnyAtomic itself as a fallback, so object
present-values stay clean on older builds, but Schedule / Trend Log objects
need #183 (included in 0.1.0).

## What the RDF fixes change

bacpypes3 0.0.110 and earlier from PyPI has two bugs in `bacpypes3.rdf`'s
`ObjectProxy`, the code that writes the Turtle:

| Property | bacpypes3 0.0.110 and earlier | With the fix (0.1.0) |
|---|---|---|
| `priority-array`, `state-text` (any ArrayOf / ListOf) | Python text: `"[<bacpypes3.basetypes.PriorityValue object at 0x…>, …]"`, `"['Off', 'On']"` | Real RDF lists: 16 slots, `[ bacnet:real "12.0"^^xsd:float ]`, empty slots `[ bacnet:null bacnet:Null ]` |
| `status-flags` with any bit set (overridden, fault, …) | `AttributeError: 'BACnetGraph' object has no attribute 'add'` | `( bacnet:StatusFlags.fault bacnet:StatusFlags.overridden )` |

#183 also encodes "any value" properties such as `schedule-default` and
`relinquish-default` (when read as AnyAtomic), trend-log `any-value` records,
and `PropertyValue` values as real RDF instead of Python text.

## BACpypes3 #193: csml2rdf alignment (merged)

[JoelBender/BACpypes3#193](https://github.com/JoelBender/BACpypes3/pull/193)
was squash-merged into upstream `main` on 2026-11-11 at 8:55 AM CT as
[`0af7992`](https://github.com/JoelBender/BACpypes3/commit/0af7992192d5ae46bb953c65262273fbcba08df5)
(PR head was `69315e3`). It lines the RDF output up with the csml2rdf ontology
([JoelBender/csml2rdf `bacnet.ttl`](https://github.com/JoelBender/csml2rdf/blob/main/bacnet.ttl)).
It changes only the RDF output:

| | Before (`main`, 0.0.110) | With #193 (now in 0.1.0) |
|---|---|---|
| Namespace | `http://data.ashrae.org/bacnet/` | `http://data.ashrae.org/bacnet/2024#` |
| Object typing | none (this sample added `bacnet:Object`) | every class in the chain: `bacnet:AnalogInputObject` + `bacnet:Object`; `bacnet:ProprietaryObject` + `bacnet:Object` for object types with no standard class; a vendor class passed to `create_object(oid, object_class)` gives e.g. `ProprietaryAnalogInputObject` → `AnalogInputObject` → `Object` |
| Class names | n/a | csml2rdf names in RDF only: `MultistateValueObject`, `BitstringValueObject`, `CharacterstringValueObject`, `OctetstringValueObject`, `DatetimeValueObject`. The Python classes keep `MultiStateValueObject` etc. |
| `object-identifier` | `"analog-input,1"^^bacnet:objectIdentifier` | plain string `"analog-input,1"`, always `type,instance` (`"128,5"` for an unnamed proprietary type) |
| `local-date` / Date | `"1970-02-23"^^xsd:date` | `"1970-02-23 1"` (`YYYY-MM-DD D`, D = day of week, 1 = Monday; `*` for unspecified fields) |
| `local-time` / Time | `"18:37:29.850000"^^xsd:time` | `"18:37:29.85"` (`HH:MM:SS.hh`; `"*:*:*.*"` for a wildcard time) |
| DateTime | `xsd:dateTime` | unchanged |

Queries work without an RDFS reasoner: `?o a bacnet:Object` and
`?o a bacnet:AnalogInputObject` both match directly. The decoders still read
the older typed literals. Vendor-aware proprietary class lookup is planned
as a separate PR.

Install bacpypes3 0.1.0 or later (see above). `--check-fix` prints
`#193 class chain present` when the merged encoding is installed.

The scripts here still work with older builds. `bacnet_site_scan.py` takes the
namespace from the installed bacpypes3 and only adds `bacnet:Object` when
the library did not. `sparql_demos.py` and `completeness_report.py` use the
2024# namespace and move an older scan's terms to 2024# in memory when they
load it. To rewrite an older Turtle file the way 0.1.0 writes the #193
encoding, run (with bacpypes3 0.1.0 or later installed):

```bash
python upgrade_ttl_2024.py --ttl old_scan.ttl --out old_scan_2024.ttl
```

The `site_scan.ttl` in this directory started as the 2026-11-10 bench scan
and was re-encoded with the #193 / `main` encoders: 1499 triples moved to
2024#, 74 literals re-encoded (72 object identifiers, one local-date, one
local-time), and 72 class triples added (2863 → 2935 triples). Re-running
`upgrade_ttl_2024.py` against merged `main` (`0af7992`) on 2026-11-11
confirmed the file already matches that encoding (2935 triples in and out,
0 renamed, 0 re-encoded, 0 types added) and was written again in place so
the sample data was produced with the released code. The object / device /
topology CSVs are the original 2026-11-10 live scan (no new BACnet traffic);
the completeness CSV was regenerated from the Turtle.

### csml2rdf SHACL result for this scan

`python sparql_demos.py --csml bacnet.ttl` re-run 2026-11-11 against
merged BACpypes3 `main` (`0af7992`) and csml2rdf `main` `bacnet.ttl`
(`ed3351d`, pyshacl 0.40.2; ontology merged into the data so enumeration
classes resolve): 146 results on scan nodes, none of them a datatype
result. All 72 object identifiers and the local-date / local-time strings
pass their datatypes, and only one fails a pattern (instance 0, below).

| Count | Constraint | Path | Why |
|---:|---|---|---|
| 72 | MinCount | `property-list` | the scanner does not read `property-list` |
| 9 | MinCount | `number-of-states` | not in the scanner's object property list |
| 9 | MinCount | `current-command-priority` | rev 9 device answered unknown-property |
| 7 | MinCount | `polarity` | not read |
| 36 | MinCount | file-object properties (6 × 6) | file objects are not read in detail |
| 3 | MinCount | `object-list` | stored as `bacnet:contains`, not read as a list |
| 3 | MinCount | `out-of-service` | not in the scan for those objects |
| 3 | MinCount | network-port `protocol-level`, `changes-pending`, `network-type` | not read |
| 2 | Class | `reliability` | proprietary value `Reliability.74` is not in the ontology |
| 1 | Class | `time-of-device-restart` | the TimeStamp blank node has no `rdf:type` |
| 1 | Pattern | `object-identifier` | `device,0`, see below |

**Instance 0.** csml2rdf's published `bacnet.ttl` still uses
`^[A-Za-z0-9-]+,[1-9][0-9]*$`. Instance 0 is legal in BACnet (routers
often use device 0) and #193 writes `"device,0"`, but `[1-9]` rejects it.
On #193 (comment 5, 2026-11-11 8:54 AM CT) Joel agreed that
`(0|[1-9][0-9]*)` would keep the pattern strict enough (Clause Y.20.2, no
leading zeros) and said he fixed csml2rdf. That fix is
[JoelBender/csml2rdf@1a7b9ba](https://github.com/JoelBender/csml2rdf/commit/1a7b9ba5c3585b31adf5b3dd04a2015c20c58ffb)
("fix: object identifier allows instance 0", 8:29 AM CT): the generator
and test fixtures now use `^[A-Za-z0-9-]+,(0|[1-9][0-9]*)$`. The published
`bacnet.ttl` on csml2rdf `main` was not regenerated in that commit (or in
the follow-up `ed3351d`), so it still has the old pattern 159 times.
`python sparql_demos.py --csml bacnet.ttl` against current `bacnet.ttl`
therefore still reports one `PatternConstraintComponent` on `device,0`.
Once `bacnet.ttl` is regenerated from the updated generator, that result
should go away. The encoder cannot work around a stale shape file.

### Protocol revision 31 status

Protocol Revision 31 shipped in **bacpypes3 0.1.0** (GitHub release
[Protocol Revision 31 and RDF](https://github.com/JoelBender/BACpypes3/releases/tag/v0.1.0),
2026-11-17; PyPI `bacpypes3==0.1.0`). The `protocol-revision-31` work was
merged into `main` as part of that release, along with the RDF fixes in
#181, #183, and #193.

Among the rev-31 follow-ups: the test fix offered on #193 (`rsplit("#")` and
`endswith("#signing-key-1")` instead of assuming a `/` namespace) and the
rename of `TimeStamp.as_dateTime()` / `.dateTime` to `as_datetime()` /
`.datetime`. This sample does not call those TimeStamp methods. A fresh
scan with 0.1.0 also types `device-instance` as `xsd:nonNegativeInteger`,
encodes WeekNDay as a `bacnet:weekNDay` `"month,week,day"` literal, and
writes `PropertyValue` with `bacnet:property-value` rather than
`bacnet:value`.

The checked-in `site_scan.ttl` is still the #193 encoding from 2026-11-11
(plain integer `device-instance`; no WeekNDay / `property-value` refresh).
Regenerating it to match 0.1.0 exactly would need a live BACnet rescan;
`upgrade_ttl_2024.py` only applies the #193 namespace, class-chain, and
date/time upgrades, so the sample Turtle was left unchanged. Vendor-aware
proprietary class lookup remains a separate, not-yet-filed PR.

## Notes for a future BACpypes3 PR

These changes are implemented in **this sample** so the scan graph is useful
end-to-end. They are also candidates to land upstream in
[JoelBender/BACpypes3](https://github.com/JoelBender/BACpypes3) so every RDF
consumer gets them without a post-pass. Do not treat this section as a filed
PR — open one on bacpypes3 separately if you want the library to emit them.

### 1. `rdf:type bacnet:Object` on every object (now in #193)

Done upstream-side in #193 (see above), with the full class chain. The table
below is kept for builds without it.

| | |
|---|---|
| **Where** | `bacpypes3/rdf/core.py` → `DeviceGraph.create_object` |
| **Today** | `create_device` already adds `(device_iri, RDF.type, BACNET.Device)`. `create_object` writes `bacnet:object-type` and `bacnet:object-identifier` and `bacnet:contains`, but **no** `rdf:type`. |
| **Should emit** | `(object_iri, RDF.type, BACNET.Object)` (the `BACNET.Object` term already resolves). Optionally also a more specific class if/when the ontology defines per-type classes. |
| **Why** | Downstream SPARQL / SHACL expect `?obj a bacnet:Object`. Without the type triple, `sh:targetClass bacnet:Object` and simple `a bacnet:Object` queries miss every object even though `object-type` is present. |
| **Sample workaround** | `type_as_object()` in `bacnet_site_scan.py` adds the triple after every `create_object` call when the library did not. |

### 2. Richer network / topology modeling in the library graph

| | |
|---|---|
| **Where** | `bacpypes3/rdf/core.py` (`BACnetGraph.create_device` address blank node) and/or a small topology helper next to the RDF apps |
| **Today** | Device nodes get `bacnet:device-address` with `network-number` + `mac-address` + `rdfs:label`. There is no first-class Network or Router node, no link-layer tag, and no reachability / last-seen from a scan. |
| **Should emit (proposal)** | Optional, clearly-named predicates (library namespace or bacnet:) for: the network a device is on; the router that reaches it; link layer (`bacnet-ip` vs `bacnet-mstp`); and scan-time reachability / error status when the graph is built from a live discovery. |
| **Why** | Root-cause analysis needs to tell **network reachability failures** apart from **controller failures** and **physical/point problems**. Address blank nodes alone are hard to query consistently across tools. |
| **Sample workaround** | `scan:Network`, `scan:Router`, `scan:onNetwork`, `scan:reachedVia`, `scan:linkLayer`, `scan:reachable`, `scan:discoveryStatus`, `scan:propertyNotRead`, `scan:readAt` in this script's own `urn:bacnet-site-scan:` namespace. |

### 3. Out of scope for bacpypes3 (stay in this sample)

- CSV output, PriorityArray P1–P16 columns, and the Command note
- Completeness report, shapes files, SPARQL demos, and optional SHACL
- Provenance (`prov:Activity`) and scan tool string
- Scan-side speed controls (concurrency, timeouts, RPM chunk size)
- Any site- or vendor-specific heuristics beyond address-form link-layer inference
