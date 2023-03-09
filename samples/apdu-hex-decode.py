"""
Given a hex-binary encoded string from the variable portion of an APDU, decode
it into into a tag list and dump out the result.
"""

import sys
from bacpypes3.debugging import xtob
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import TagList

b = xtob(sys.argv[1])
d = PDUData(b)

tl = TagList.decode(d)
for i, t in enumerate(tl):
    print(f"[{i}]")
    t.debug_contents()
