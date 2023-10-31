"""
Check to see what versions of modules are installed.
"""
import sys

try:
    import bacpypes3

    print("bacpypes3:", bacpypes3.__version__, bacpypes3.__file__)
except:
    print("bacpypes3: not installed")

try:
    import websockets

    print("websockets:", websockets.__version__, websockets.__file__)
except:
    print("websockets: not installed")

try:
    import ifaddr

    print("ifaddr:", ifaddr.__file__)
except:
    print("ifaddr: not installed")

try:
    import yaml

    print("pyyaml:", yaml.__version__, yaml.__file__)
except:
    print("pyyaml: not installed")

try:
    import rdflib

    print("rdflib:", rdflib.__version__, rdflib.__file__)
except:
    print("rdflib: not installed")
