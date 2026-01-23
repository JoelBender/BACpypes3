# BACnet Diagnostic Tools

> WORK IN PROGRESS NOT COMPLETE YET!!!

---


## Interactive bacpypes Shell (`tester.py`)

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

> WHERE TO DOWNLOAD 223p.ttl and bacnet-2020.ttl ??? THIS NEEDS REVISION!!!

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

