"""
This example uses a prepared query to find all of the BACnet
devices in a graph, optionally with a specific device instance
number.
"""
import sys
from rdflib import Graph, Literal
from rdflib.namespace import XSD
from bacpypes3.rdf.core import find_device_by_instance


g = Graph()
g.parse(sys.argv[1])

init_bindings = {}
if len(sys.argv) > 2:
    # device instances are encoded as xsd:nonNegativeInteger
    init_bindings["device_instance"] = Literal(
        int(sys.argv[2]), datatype=XSD.nonNegativeInteger
    )

for row in g.query(find_device_by_instance, initBindings=init_bindings):
    print(row[0])
