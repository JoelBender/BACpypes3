# BACnet Diagnostic Tools

Two scripts for discovering, auditing, and manually testing BACnet networks.

## 1\. Install Requirements

Run this once to get the required libraries:

```bash
pip install bacpypes3 ifaddr rdflib pyshacl ontoenv aiohttp
```

-----

## 2\. Auto-Scan (`bacnet_autoscan.py`)

Scans a range of device IDs and saves a CSV inventory for *each* device found. Captures names, values, units, and priority arrays.

**Run the scan to output CSV file only:**

```bash
python bacnet_autoscan.py --low-instance 1 --high-instance 3456999 --output-dir autoscan_csv
```

**Output:**

  * Check the `autoscan_csv/` folder.
  * You will see files like `audit_3456789.csv`.

**Run the scan to output CSV and ASHRAE 223P model:**
```bash
python bacnet_autoscan.py \
  --low-instance 1 \
  --high-instance 3456999 \
  --output-dir autoscan_csv \
  --output-223p autoscan_223p.ttl \
  --model-base-uri urn:my-building
```

**Output:**

* Write per-device CSVs into autoscan_csv/ (e.g., audit_<device>.csv)
* Write one combined Turtle file autoscan_223p.ttl for the same Who-Is range

TODO:
* validate or enrich the 223P model afterward (BuildingMOTIF, SHACL, inference)

```
pip install pyshacl ontoenv buildingmotif
```

---


## 3. Interactive bacpypes Shell (`tester.py`)

A command-line shell for manually reading, writing, and overriding BACnet points. It also includes integrated RDF tools for querying (SPARQL) and validating (SHACL) your generated ASHRAE 223P models without leaving the console.

**Start the shell:**

```bash
python tester.py

```

*(Optional: Bind to a specific interface using `--address 192.168.1.X/24`)*

#### **Shell Command Cheat Sheet**

**Discovery**

```text
> whois                     # Find all devices
> whois 1000 2000           # Find devices in range 1000-2000
> objects 192.168.1.20 123  # List all points on device 123

```

**Reading & Writing Data**

```text
> read 192.168.1.20 analog-input,1 present-value
> write 192.168.1.20 binary-output,1 present-value active 8    # Override ON (Priority 8)
> write 192.168.1.20 binary-output,1 present-value null 8      # Release Override

```

**Model Tools (RDF / 223P)**
*Run queries and validation against your generated `model.ttl` file.*

```text
# 1. Download Official Standards (Run once)
# Fetches the 223P and BACnet dictionaries needed for validation
> download_standards

# 2. Run a SHACL validation report
# Validates your model against your Shapes + the Official Standards
> shacl model.ttl shapes.ttl 223p.ttl bacnet-2020.ttl

# 3. The "Hello World" Dump
# Prints the first 20 raw items to prove the graph is loaded
> sparql model.ttl "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 20"

# 4. Find all Devices
# Lists every BACnet Controller found in the file
> sparql model.ttl "SELECT ?device ?name WHERE { ?device a bacnet:BACnetDevice ; rdfs:label ?name }"

# 5. Find "Temp" sensors and their live values
# Searches the full 'Description' for the word "Temp" and returns the value
> sparql model.ttl "SELECT ?point ?val WHERE { ?point a s223:QuantifiableObservableProperty ; bacnet:description ?desc ; bacnet:presentValue ?val . FILTER regex(?desc, 'Temp', 'i') }"

```

---

## 4. Validation & Compliance

After scanning, you can "grade" your digital twin against the official ASHRAE 223P standard to check for compliance and missing data.

**Run the Validator (Save to File):**

```bash
python tester.py model validate --model model.ttl --shapes shapes.ttl --ontology 223p.ttl bacnet-2020.ttl > report.txt

```

### Understanding the Report (`report.txt`)

* **`Conforms: True`**: Your model is fully valid.
* **`Conforms: False`**: Issues were found. Check the details below:

| Severity | Type | Meaning | Action Required |
| --- | --- | --- | --- |
| **Violation** 🛑 | **CRITICAL** | Broken data (e.g., missing values). | **Fix Now.** Check scanner logic or device connection. |
| **Warning** ⚠️ | **INFO** | Missing physical context. | **Fix Later.** Example: "Point exists but isn't linked to a specific pipe." This is expected for raw scans. |

---

## Under the Hood

The `tester.py` script runs a single Python process that manages distinct workloads to keep the system responsive:

1. **The BACnet Stack:** It maintains an active UDP socket listener on port 47808 using `bacpypes3`. This runs on the main event loop, allowing it to receive `I-Am` and `COV` notifications asynchronously.
2. **The RDF Engine:** When you run `sparql` or `shacl`, the script offloads these CPU-intensive tasks to a separate thread. This prevents heavy graph processing (loading thousands of triples) from blocking the network socket.
3. **The SHACL Validator:** This tool applies the logic defined in `shapes.ttl` to your data graph. It transforms the graph from a simple collection of data points into a validated, compliant model by checking against the official ASHRAE ontologies.