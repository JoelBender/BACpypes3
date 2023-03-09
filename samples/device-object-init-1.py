"""
Create a local device object instance, convert it to JSON and print the result,
then round-trip the JSON into another device object.
"""
from pprint import pprint

from bacpypes3.debugging import ModuleLogger

# from bacpypes3.argparse import create_log_handler

from bacpypes3.local.device import DeviceObject
from bacpypes3.json import sequence_to_json, json_to_sequence

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# create_log_handler("__main__")
# create_log_handler("bacpypes3.constructeddata", color=4)
# create_log_handler("bacpypes3.object", color=5)
# create_log_handler("bacpypes3.local.object", color=6)
# create_log_handler("bacpypes3.local.device", color=6)

do1 = DeviceObject(objectIdentifier="device,1", objectName="Excelsior")
print("do1")
do1.debug_contents()
print("")

json_content = sequence_to_json(do1)
pprint(json_content)
print("")

do2 = json_to_sequence(json_content, DeviceObject)
print("do2")
do2.debug_contents()
print("")
