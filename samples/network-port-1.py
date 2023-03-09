"""
Create a network port object from an address, print some interesting stuff,
convert it to JSON and YAML.  Variations of this sample are used to check the
results of various patterns of addresses.
"""
from pprint import pprint
import yaml

# from bacpypes3.argparse import create_log_handler
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.json import sequence_to_json

# create_log_handler("bacpypes3.object")
# create_log_handler("bacpypes3.local.networkport")

npo = NetworkPortObject(
    "5:192.168.0.99/24",
    objectName="Network Port 1",
    objectIdentifier=("network-port", 1),
)

print("npo:", npo)
npo.debug_contents()
print("")

npo_address = npo.address
print(f"{npo_address = }")
print(f"{npo_address.network = }")
print("")

npo_json = sequence_to_json(npo)
pprint(npo_json)
print("")

print(yaml.dump({"application": [npo_json]}))
