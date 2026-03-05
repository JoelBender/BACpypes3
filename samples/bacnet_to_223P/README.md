# BACnet Diagnostic Tools

Two scripts for discovering, auditing, and manually testing BACnet networks.

## 1\. Install Requirements

Run this once to get the required libraries:

```bash
pip install bacpypes3 ifaddr rdflib
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

## 3. Interactive Shell (`tester.py`)

A command-line shell for manually reading, writing, and overriding BACnet points. It also includes integrated RDF tools for querying (SPARQL) and validating (SHACL) your generated ASHRAE 223P models without leaving the console.

**Start the shell:**

```bash
python tester.py

```

*(If you need to bind to a specific IP, add `--address 192.168.1.X/24`)*

### **Shell Command Cheat Sheet**

Once inside the shell (`>`), type these commands:

**Discovery**

```text
> whois                     # Find all devices
> whois 1000 2000           # Find devices in range 1000-2000
> objects 192.168.1.20 123  # List all points on device 123 (auto-fallbacks to single read if needed)

```

**Reading & Writing Data**
*Format: `write <IP> <Object> <Property> <Value> <Priority>*`

```text
> read 192.168.1.20 analog-input,1 present-value
> write 192.168.1.20 binary-output,1 present-value active 8    # Turn ON (Priority 8)
> write 192.168.1.20 binary-output,1 present-value null 8      # Release Override

```

**Checking Priorities**
*Always check who is controlling a point before you override it.*

```text
> priority 192.168.1.20 binary-output,1

```

**Model Tools (RDF / 223P)**
*Run queries and validation against your generated `model.ttl` file.*

```text
# Run a SHACL validation report (Pass/Fail)
> shacl model.ttl shapes.ttl

# Run a SPARQL query (Dump first 10 items)
> sparql model.ttl "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"

# Find all Devices in the model
> sparql model.ttl "SELECT ?device ?name WHERE { ?device a bacnet:BACnetDevice ; rdfs:label ?name }"

# Find all 'Temp' sensors and their values
> sparql model.ttl "SELECT ?point ?val WHERE { ?point a s223:QuantifiableObservableProperty ; rdfs:label ?name ; bacnet:presentValue ?val . FILTER regex(?name, 'Temp', 'i') }"

```

### **Test Bench Hammers (Drills)**

Use these sequences to test real hardware response and model accuracy.

**Hardware Drill**

```text
> whois 1000 3456799
> read 192.168.204.13 analog-input,1 present-value
> priority 192.168.204.14 analog-output,1
> write 192.168.204.14 analog-output,1 present-value 999.8 9
> write 192.168.204.14 analog-output,1 present-value null 9
> priority 192.168.204.14 analog-output,1

```

**Data Drill**

```text
> sparql model.ttl "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"
> sparql model.ttl "SELECT ?point ?val WHERE { ?point a s223:QuantifiableObservableProperty ; bacnet:presentValue ?val }"

```
 
**Exit**

```text
> exit
```

### **Under the Hood**

The `tester.py` script runs a single Python process that manages distinct workloads to keep the system responsive:

1. **The BACnet Stack:** It maintains an active UDP socket listener on port 47808 using `bacpypes3`. This runs on the main event loop, allowing it to receive `I-Am` and `COV` notifications asynchronously while you type.
2. **The RDF Engine:** When you run `sparql` or `shacl`, the script offloads these CPU-intensive tasks to a separate thread using `asyncio.to_thread`. This prevents the heavy graph processing (loading thousands of triples) from blocking the network socket. You can validate a massive model without causing BACnet timeouts or dropping packets.
3. **The SHACL Validator:** This tool applies the logic defined in `shapes.ttl` to your data graph. Think of `shapes.ttl` as a **Pydantic Model** for your graph. Just as Pydantic enforces that a Python dictionary has the correct keys and value types (e.g., `ip: str`), SHACL enforces that your graph nodes possess the required RDF properties (e.g., `bacnet:deviceInstance`). It transforms the graph from a simple collection of data points into a validated, compliant model.