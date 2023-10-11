"""
This example uses a prepared query to find all of the BACnet
devices in a graph, optionally with an address.  By specifying
different initial bindings then different collections of
devices can be found.
"""
import sys
from rdflib import Graph

from bacpypes3.pdu import Address
from bacpypes3.rdf.core import find_device_by_address
from bacpypes3.rdf.util import unsigned_encode, octetstring_encode

g = Graph()
g.parse(sys.argv[1])

init_bindings = {}
if len(sys.argv) > 2:
    device_address = Address(sys.argv[2])

    if device_address.is_localbroadcast:
        init_bindings["net"] = unsigned_encode(g, 0)
    elif device_address.is_remotestation or device_address.is_remotebroadcast:
        init_bindings["net"] = unsigned_encode(g, device_address.addrNet)
    if device_address.is_localstation or device_address.is_remotestation:
        init_bindings["addr"] = octetstring_encode(g, device_address.addrAddr)

for row in g.query(find_device_by_address, initBindings=init_bindings):
    print(row[0])
