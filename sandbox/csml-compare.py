#!/usr/bin/env python
"""
Compare BACpypes3 with the CSML descriptions of the datatypes and objects.

    python sandbox/csml-compare.py ../bacnet-dm-wg/bacnet-data-types.xml
    python sandbox/csml-compare.py ../bacnet-dm-wg/bacnet-object-types.xml
    python sandbox/csml-compare.py --all ../bacnet-dm-wg/bacnet-*.xml

Datatypes (Clause 21): each top-level CSML definition (0-BACnetFoo,
0-Foo-Request, ...) is matched to a class in bacpypes3.primitivedata,
.constructeddata, .basetypes or .apdu and compared recursively: enumeration
values and names, bit positions and names, bit string length, element order,
context tags, OPTIONAL, element types, inline nested types, and the vendor
range.  Names are checked the way they are emitted: enumeration and bit names
through the class maps (_asn1_map, _bitstring_names), element names through
attr_to_asn1() (JSON keys) and attr_to_predicate() (RDF predicates).

Objects (Clause 12): each CSML object type (0-FooObject) is matched to a
class in bacpypes3.object and its properties are compared by property
identifier number: the object type value, missing and extra properties,
property names, property types (including array/list, member type and fixed
array length), and required properties against the class _required tuples.

The CSML is also checked for consistency with itself: references to
undefined datatypes (including across files when both are given), element
kinds that disagree with the referenced definition, bit strings with bits
beyond their length, duplicate enumeration values, properties without a
property identifier, and object-type values that do not match the object.

The kind of comparison is chosen by the content of each file.  Findings are
grouped as problems and, with --all, informational differences (sized
integers, value constraints, accepted equivalents, and definitions bacpypes3
keeps for older devices).
"""

import argparse
import inspect
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

from bacpypes3 import apdu, basetypes, constructeddata, primitivedata
from bacpypes3 import object as bacpypes_object
from bacpypes3.primitivedata import PropertyIdentifier, attr_to_asn1

try:
    from bacpypes3.rdf.util import attr_to_predicate
except ImportError:
    attr_to_predicate = None

NS = "{http://bacnet.org/csml/1.2}"

# CSML definitions that describe the APDU headers or the service choice
# wrappers, bacpypes3 handles these in the APCI and the service registries
SKIP = {
    "0-BACnetPDU",
    "0-BACnet-Confirmed-Request-PDU",
    "0-BACnet-Unconfirmed-Request-PDU",
    "0-BACnet-SimpleACK-PDU",
    "0-BACnet-ComplexACK-PDU",
    "0-BACnet-SegmentACK-PDU",
    "0-BACnet-Error-PDU",
    "0-BACnet-Reject-PDU",
    "0-BACnet-Abort-PDU",
    "0-BACnet-Confirmed-Service-Request",
    "0-BACnet-Confirmed-Service-ACK",
    "0-BACnet-Unconfirmed-Service-Request",
    "0-BACnet-Error",
}

# CSML names implemented by a bacpypes3 class with a different name
ALIASES = {
    "error": "errortype",
    "address": "deviceaddress",
    "confirmedeventnotificationrequest": "eventnotificationparameters",
    "datetimepattern": "datetime",
}

# CSML references that bacpypes3 implements with an equivalent structure
# as {CSML name: bacpypes3 class names}
EQUIVALENT = {
    "0-BACnetAddress": {"Address", "DeviceAddress"},
    "0-ConfirmedEventNotification-Request": {"EventNotificationParameters"},
    "0-I-Am-Request": {"DeviceAddressProxyTableEntryIAm"},
}

# elements bacpypes3 names differently on purpose, as
# {(CSML definition, CSML element name): bacpypes3 attribute}
RENAMED = {
    ("0-BACnetNetworkQualifier", "instance-low"): "networkNumberRangeLowLimit",
    ("0-BACnetNetworkQualifier", "instance-high"): "networkNumberRangeHighLimit",
}

# elements the standard removed that bacpypes3 keeps to decode older traffic
KEPT = {
    ("0-BACnetPropertyStates", "securityLevel"),
}

# object properties and object types the standard removed (network security)
# that bacpypes3 keeps for older devices
KEPT_PROPERTIES = {
    ("0-DeviceObject", "listOfSessionKeys"),
}
KEPT_OBJECTS = {
    "NetworkSecurityObject",
}

PRIMITIVES = {
    "Unsigned": primitivedata.Unsigned,
    "Integer": primitivedata.Integer,
    "Real": primitivedata.Real,
    "Double": primitivedata.Double,
    "Boolean": primitivedata.Boolean,
    "String": primitivedata.CharacterString,
    "OctetString": primitivedata.OctetString,
    "Null": primitivedata.Null,
    "ObjectIdentifier": primitivedata.ObjectIdentifier,
    "Date": primitivedata.Date,
    "Time": primitivedata.Time,
    "DateTime": basetypes.DateTime,
    "DatePattern": primitivedata.Date,
    "TimePattern": primitivedata.Time,
    "DateTimePattern": basetypes.DateTime,
    "WeekNDay": basetypes.WeekNDay,
    "BitString": primitivedata.BitString,
    "Enumerated": primitivedata.Enumerated,
    "Any": constructeddata.Any,
}

# CSML element kinds that are encoded with opening and closing tags (or as
# more than one application tag) rather than as one primitive tag
CONSTRUCTED = {
    "Sequence",
    "Choice",
    "SequenceOf",
    "Array",
    "List",
    "DateTime",
    "DateTimePattern",
}

# sized application types, a plain Unsigned/Integer encodes the same way
SIZED = {
    "0-Unsigned8": primitivedata.Unsigned,
    "0-Unsigned16": primitivedata.Unsigned,
    "0-Unsigned32": primitivedata.Unsigned,
    "0-Unsigned64": primitivedata.Unsigned,
    "0-Integer16": primitivedata.Integer,
    "0-Integer32": primitivedata.Integer,
}


def tag_of(e):
    return e.tag[len(NS) :]


def children(e):
    return [c for c in e if isinstance(c.tag, str)]


def key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def normalize(name):
    if name.startswith("0-"):
        name = name[2:]
    if name.startswith("BACnet"):
        name = name[6:]
    k = key(name)
    return ALIASES.get(k, k)


class Compare:
    def __init__(self, definitions):
        self.definitions = {e.get("name"): e for e in children(definitions)}
        self.problems = defaultdict(list)
        self.info = defaultdict(list)
        self.seen = set()

        self.classes = {}
        for module in (primitivedata, constructeddata, basetypes, apdu):
            for name, obj in vars(module).items():
                if inspect.isclass(obj) and obj.__module__ == module.__name__:
                    self.classes.setdefault(key(name), obj)

    def lookup(self, xml_name):
        return self.classes.get(normalize(xml_name))

    def problem(self, path, msg):
        self.problems[path[0]].append(f"{'.'.join(path[1:]) or '<top>'}: {msg}")

    def note(self, path, msg):
        self.info[path[0]].append(f"{'.'.join(path[1:]) or '<top>'}: {msg}")

    @staticmethod
    def name_of(klass):
        for c in klass.__mro__:
            if "_signature" in c.__dict__ and c.__mro__[1].__name__ == c.__name__:
                continue
            return f"{c.__module__.split('.')[-1]}.{c.__name__}"
        return klass.__name__

    # -----

    def check_name(self, path, attr, xml_name, cls):
        """Check an element name the way JSON and RDF emit it."""
        standard_name = getattr(cls, "_element_names", {}).get(attr)
        emitted = standard_name or attr_to_asn1(attr)
        if emitted != xml_name:
            self.problem(path, f"NAME json key {emitted!r} should be {xml_name!r}")
        if attr_to_predicate is not None:
            predicate = standard_name or str(attr_to_predicate(attr)).rsplit("/", 1)[1]
            if predicate != xml_name and emitted == xml_name:
                self.problem(
                    path, f"NAME rdf predicate {predicate!r} should be {xml_name!r}"
                )

    def check_references(self, path, e, kinds):
        """The CSML references definitions that exist, with the same kind."""
        for attr in ("type", "memberType"):
            reference = e.get(attr)
            if not reference or reference in PRIMITIVES:
                continue
            if (path[0], reference) in self.seen:
                continue
            self.seen.add((path[0], reference))

            if reference not in kinds:
                self.problem(
                    path, f"CSML ERROR {e.get('name')} uses {reference!r}, not defined"
                )
            elif attr == "type":
                kind, definition_kind = tag_of(e), kinds[reference]
                if (kind in CONSTRUCTED) != (definition_kind in CONSTRUCTED):
                    self.problem(
                        path,
                        f"CSML ERROR {e.get('name')} is {kind} "
                        f"but {reference} is {definition_kind}",
                    )

    def enumerated(self, x, cls, path):
        if not (inspect.isclass(cls) and issubclass(cls, primitivedata.Enumerated)):
            self.problem(path, f"expected Enumerated, got {self.name_of(cls)}")
            return
        if (cls, "enum") in self.seen:
            return
        self.seen.add((cls, "enum"))

        named_values = [
            (int(c.get("value")), c.get("name"))
            for c in children(x.find(NS + "NamedValues"))
        ]
        xml_values = {}
        duplicates = set()
        for value, name in named_values:
            if value in xml_values:
                duplicates.add(value)
                self.problem(
                    path,
                    f"CSML ERROR value {value} is both {xml_values[value]!r} and {name!r}",
                )
            else:
                xml_values[value] = name
        for value, name in sorted(xml_values.items()):
            if value in duplicates:
                continue
            if value not in cls._asn1_map:
                self.problem(path, f"MISSING value {name}={value}")
            elif cls._asn1_map[value] != name:
                self.problem(
                    path,
                    f"NAME value {value} is {cls._asn1_map[value]!r} "
                    f"({cls._attr_map[value]}) should be {name!r}",
                )
        for value, attr in sorted(cls._attr_map.items()):
            if value not in xml_values:
                self.note(path, f"EXTRA value {attr}={value}")

        low, high = x.get("minimum"), x.get("maximum")
        vendor_range = getattr(cls, "_vendor_range", None)
        if low is not None and vendor_range != (int(low), int(high)):
            self.note(
                path, f"VENDOR RANGE csml=({low}, {high}) bacpypes3={vendor_range}"
            )

    def bitstring(self, x, cls, path):
        if not (inspect.isclass(cls) and issubclass(cls, primitivedata.BitString)):
            self.problem(path, f"expected BitString, got {self.name_of(cls)}")
            return
        if (cls, "bits") in self.seen:
            return
        self.seen.add((cls, "bits"))

        xml_bits = {
            int(c.get("bit")): c.get("name") for c in children(x.find(NS + "NamedBits"))
        }
        names = {v: k for k, v in cls._bitstring_names.items()}
        for bit, name in sorted(xml_bits.items()):
            if bit not in names:
                self.problem(path, f"MISSING bit {name}={bit}")
            elif names[bit] != name:
                self.problem(
                    path, f"NAME bit {bit} is {names[bit]!r} should be {name!r}"
                )
        for bit, name in sorted(names.items()):
            if bit not in xml_bits:
                self.note(path, f"EXTRA bit {name}={bit}")
        length = x.get("length")
        if length is not None and xml_bits and max(xml_bits) >= int(length):
            self.problem(
                path,
                f"CSML ERROR length {length} but bit {max(xml_bits)} is defined",
            )
        elif length is not None and int(length) != cls._bitstring_length:
            self.problem(path, f"LENGTH {cls._bitstring_length} should be {length}")

    @staticmethod
    def fields_of(x):
        if tag_of(x) == "Choice":
            choices = x.find(NS + "Choices")
            return children(choices) if choices is not None else []
        return [
            c
            for c in children(x)
            if tag_of(c)
            not in ("NamedValues", "NamedBits", "Choices", "MemberTypeDefinition")
        ]

    @staticmethod
    def is_inline(x):
        kind = tag_of(x)
        kinds = [tag_of(c) for c in children(x)]
        return (
            (kind == "Enumerated" and "NamedValues" in kinds)
            or (kind == "BitString" and "NamedBits" in kinds)
            or (kind == "Choice" and "Choices" in kinds)
            or (kind == "Sequence" and bool(kinds))
            or (kind == "SequenceOf" and "MemberTypeDefinition" in kinds)
        )

    def structure(self, x, cls, path):
        kind = tag_of(x)
        if not (inspect.isclass(cls) and issubclass(cls, constructeddata.Sequence)):
            self.problem(path, f"expected {kind}, got {self.name_of(cls)}")
            return

        xml_fields = self.fields_of(x)
        bp3_names = list(cls._order) if cls._order else list(cls._elements)
        by_key = {key(n): n for n in bp3_names}
        matched = []
        for f in xml_fields:
            name = f.get("name")
            attr = by_key.get(key(name)) or by_key.get(key(re.sub(r"-", "", name)))
            renamed = RENAMED.get((path[0], name))
            if renamed in cls._elements:
                attr = renamed
                self.note(path, f"RENAMED element {name} is {attr}")
            if attr is None:
                desc = f"{tag_of(f)} [{f.get('contextTag')}]"
                if f.get("type"):
                    desc += f" {f.get('type')}"
                if f.get("optional") == "true":
                    desc += " OPTIONAL"
                self.problem(path, f"MISSING element {name} {desc}")
                continue
            matched.append(attr)
            if not renamed:
                self.check_name(path + [attr], attr, name, cls)
            self.element(f, cls._elements[attr], path + [attr])

        xml_keys = {key(f.get("name")) for f in xml_fields} | {key(a) for a in matched}
        for attr in bp3_names:
            if key(attr) not in xml_keys:
                msg = f"EXTRA element {attr} ({self.name_of(cls._elements[attr])})"
                if (path[0], attr) in KEPT:
                    self.note(path, msg)
                else:
                    self.problem(path, msg)

        if kind == "Sequence" and cls._order:
            order = [a for a in cls._order if a in matched]
            if order != matched:
                self.problem(path, f"ORDER {order} should be {matched}")

    def element(self, f, cls, path):
        context = f.get("contextTag")
        context = int(context) if context is not None else None
        bp3_context = getattr(cls, "_context", None)
        if context != bp3_context:
            if context is not None and context > 254 and bp3_context == context:
                pass
            else:
                self.problem(path, f"CONTEXT {bp3_context} should be {context}")

        optional = f.get("optional") == "true"
        if optional != bool(getattr(cls, "_optional", False)):
            self.problem(path, f"OPTIONAL {not optional} should be {optional}")

        self.element_type(f, cls, path)

    def element_type(self, f, cls, path):
        kind = tag_of(f)
        type_name = f.get("type")

        if kind == "SequenceOf":
            if not (
                inspect.isclass(cls) and issubclass(cls, constructeddata.ExtendedList)
            ):
                if inspect.isclass(cls) and issubclass(cls, constructeddata.Any):
                    self.note(path, "ACCEPTED SEQUENCE OF decoded later as Any")
                else:
                    self.problem(path, f"expected SEQUENCE OF, got {self.name_of(cls)}")
                return
            member = f.get("memberType")
            if member in PRIMITIVES:
                if not issubclass(cls._subtype, PRIMITIVES[member]):
                    self.problem(
                        path, f"MEMBER {self.name_of(cls._subtype)} should be {member}"
                    )
            elif member:
                self.named_type(member, cls._subtype, path, "MEMBER")
            else:
                definition = children(f.find(NS + "MemberTypeDefinition"))[0]
                self.element_type(definition, cls._subtype, path + ["[]"])
            if f.get("minimumSize") or f.get("maximumSize"):
                self.note(path, f"SIZE {f.get('minimumSize')}..{f.get('maximumSize')}")
            return

        if self.is_inline(f):
            if kind == "Enumerated":
                self.enumerated(f, cls, path)
            elif kind == "BitString":
                self.bitstring(f, cls, path)
            else:
                self.structure(f, cls, path)
            return

        if type_name:
            self.named_type(type_name, cls, path, "TYPE")
            return

        if kind not in PRIMITIVES:
            self.problem(path, f"unknown CSML element {kind}")
        elif not issubclass(cls, PRIMITIVES[kind]):
            self.problem(path, f"TYPE {self.name_of(cls)} should be {kind}")

        for attr in ("minimum", "maximum", "minimumLength", "maximumLength"):
            if f.get(attr) is not None:
                self.note(path, f"CONSTRAINT {attr}={f.get(attr)}")

    def named_type(self, type_name, cls, path, label):
        expected = self.lookup(type_name)
        if type_name in SIZED:
            if expected is not None and issubclass(cls, expected):
                return
            if issubclass(cls, SIZED[type_name]):
                self.note(path, f"SIZED {self.name_of(cls)} could be {type_name[2:]}")
                return
        if expected is None:
            self.problem(path, f"{label} {type_name} is not implemented")
            return
        if not (
            (inspect.isclass(cls) and issubclass(cls, expected))
            or (
                inspect.isclass(cls)
                and any(
                    c.__name__ in EQUIVALENT.get(type_name, ()) for c in cls.__mro__
                )
            )
        ):
            self.problem(path, f"{label} {self.name_of(cls)} should be {type_name}")
            return

        # follow named enumerations and bit strings so their values are checked
        definition = self.definitions.get(type_name)
        if definition is not None and tag_of(definition) == "Enumerated":
            self.enumerated(definition, expected, [type_name])
        elif definition is not None and tag_of(definition) == "BitString":
            self.bitstring(definition, expected, [type_name])

    # -----

    def run(self):
        kinds = {name: tag_of(x) for name, x in self.definitions.items()}
        for name, x in self.definitions.items():
            for e in x.iter():
                if isinstance(e.tag, str):
                    self.check_references([name], e, kinds)

        not_implemented = []
        for name, x in self.definitions.items():
            if name in SKIP:
                continue
            kind = tag_of(x)
            cls = self.lookup(name)
            path = [name]
            if cls is None:
                not_implemented.append(f"{kind} {name}")
                continue

            if kind == "Enumerated":
                self.enumerated(x, cls, path)
            elif kind == "BitString":
                self.bitstring(x, cls, path)
            elif kind in ("Sequence", "Choice"):
                if (
                    kind == "Choice"
                    and issubclass(cls, apdu.APCISequence)
                    and not issubclass(cls, constructeddata.Choice)
                ):
                    # a CHOICE result implemented as optional APDU elements
                    self.note(path, "ACCEPTED CHOICE as an APDU with optional elements")
                    by_key = {key(a): a for a in cls._elements}
                    for f in self.fields_of(x):
                        attr = by_key.get(key(f.get("name")))
                        if attr is None:
                            self.problem(path, f"MISSING choice {f.get('name')}")
                        else:
                            self.element_type(f, cls._elements[attr], path + [attr])
                    continue
                self.structure(x, cls, path)
            elif kind == "SequenceOf":
                if (
                    issubclass(cls, constructeddata.Sequence)
                    and len(cls._elements) == 1
                ):
                    ((attr, element),) = cls._elements.items()
                    self.note(
                        path,
                        f"ACCEPTED SEQUENCE OF wrapped in {self.name_of(cls)}.{attr}",
                    )
                    self.element_type(x, element, path + [attr])
                else:
                    self.element_type(x, cls, path)
        return not_implemented


class ObjectCompare(Compare):
    """Compare the object type classes with the CSML object definitions."""

    def __init__(self, definitions, datatypes=None):
        super().__init__(definitions)

        # names defined in the datatypes file, when it was given
        self.datatypes = (
            {e.get("name"): tag_of(e) for e in children(datatypes)}
            if datatypes is not None
            else None
        )

        self.objects = {}
        for name, obj in vars(bacpypes_object).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, bacpypes_object.Object)
                and obj.__module__ == bacpypes_object.__name__
                and "objectType" in obj.__dict__
            ):
                self.objects[key(name)] = obj

    def lookup(self, xml_name):
        if xml_name.startswith("0-") and xml_name.endswith("Object"):
            return self.objects.get(key(xml_name[2:]))
        return super().lookup(xml_name)

    @staticmethod
    def required(klass):
        names = set()
        for c in klass.__mro__:
            names |= set(c.__dict__.get("_required", ()))
        return names

    def member_type(self, member, cls, path):
        if member in PRIMITIVES:
            if not issubclass(cls, PRIMITIVES[member]):
                self.problem(path, f"MEMBER {self.name_of(cls)} should be {member}")
        else:
            self.named_type(member, cls, path, "MEMBER")

    def property_type(self, p, cls, path):
        kind = tag_of(p)
        if kind in ("Array", "List"):
            want = constructeddata.Array if kind == "Array" else constructeddata.List
            member = p.get("memberType")
            if not (inspect.isclass(cls) and issubclass(cls, want)):
                self.problem(path, f"{self.name_of(cls)} should be {kind} of {member}")
                return

            if (
                path[-1] == "priorityArray"
                and member.startswith("0-BACnetOptional")
                and cls._subtype is basetypes.PriorityValue
            ):
                self.note(path, f"ACCEPTED BACnetPriorityValue for {member}")
            else:
                self.member_type(member, cls._subtype, path)

            if kind == "Array":
                low, high = p.get("minimumSize"), p.get("maximumSize")
                length = getattr(cls, "_length", None)
                if low and low == high:
                    if length != int(low):
                        self.problem(path, f"LENGTH {length} should be {low}")
                elif length is not None:
                    self.problem(path, f"LENGTH {length} should be variable")
            return

        if inspect.isclass(cls) and issubclass(cls, constructeddata.ExtendedList):
            self.problem(path, f"{self.name_of(cls)} should be {kind}")
        elif p.get("type"):
            self.named_type(p.get("type"), cls, path, "TYPE")
        elif kind not in PRIMITIVES:
            self.problem(path, f"unknown CSML element {kind}")
        elif not issubclass(cls, PRIMITIVES[kind]):
            self.problem(path, f"TYPE {self.name_of(cls)} should be {kind}")

        for attr in ("minimum", "maximum"):
            if p.get(attr) is not None:
                self.note(path, f"CONSTRAINT {attr}={p.get(attr)}")

    def object_type_value(self, name, x):
        """The object-type value matches the object it is defined in."""
        for p in children(x):
            if p.get("name") == "object-type":
                value = p.get("value")
                if key(value or "") != key(name[2:-6]):
                    self.problem([name], f"CSML ERROR object-type value is {value!r}")

    def object_type(self, x, cls):
        name = x.get("name")
        required = self.required(cls)

        for attr in sorted(required - set(cls._elements)):
            self.problem([name], f"_required lists {attr!r}, not a property")

        csml_identifiers = set()
        for p in children(x):
            property_name = p.get("name")
            if p.get("propertyIdentifier") is None:
                # find it by name so the rest of the property can be checked
                standard_name = property_name.replace("_", "-")
                self.problem(
                    [name],
                    f"CSML ERROR property {property_name!r} has no propertyIdentifier",
                )
                try:
                    identifier = int(PropertyIdentifier(standard_name))
                except ValueError:
                    continue
                property_name = standard_name
            else:
                identifier = int(p.get("propertyIdentifier"))
            csml_identifiers.add(identifier)

            if property_name == "object-type":
                value = p.get("value")
                if key(value) != key(name[2:-6]):
                    pass  # reported by object_type_value()
                elif cls.objectType.asn1 != value:
                    self.problem(
                        [name],
                        f"objectType {cls.objectType.asn1!r} should be {value!r}",
                    )

            # the object definitions should only use defined datatypes
            if self.datatypes is not None:
                self.check_references([name], p, self.datatypes)

            if identifier not in PropertyIdentifier._attr_map:
                self.problem(
                    [name],
                    f"MISSING property {property_name} ({identifier}), "
                    "not in PropertyIdentifier",
                )
                continue
            property_identifier = PropertyIdentifier(identifier)
            if property_identifier.asn1 != property_name:
                self.problem(
                    [name],
                    f"NAME property {identifier} is {property_identifier.asn1!r} "
                    f"should be {property_name!r}",
                )

            attr = property_identifier.attr
            optional = p.get("optional") == "true"
            if attr not in cls._elements:
                desc = tag_of(p)
                if p.get("type") or p.get("memberType"):
                    desc += f" {p.get('type') or p.get('memberType')}"
                if not optional:
                    desc += " REQUIRED"
                self.problem(
                    [name], f"MISSING property {property_name} ({identifier}) {desc}"
                )
                continue

            path = [name, attr]
            if not optional and attr not in required:
                self.problem(path, "REQUIRED, not in _required")
            elif optional and attr in required:
                self.problem(path, "OPTIONAL, listed in _required")

            self.property_type(p, cls._elements[attr], path)

        for attr in cls._elements:
            identifier = int(PropertyIdentifier(attr))
            if identifier not in csml_identifiers:
                msg = f"EXTRA property {attr} ({identifier})"
                if (name, attr) in KEPT_PROPERTIES:
                    self.note([name], msg)
                else:
                    self.problem([name], msg)

    def run(self):
        not_implemented = []
        csml_objects = set()
        for name, x in self.definitions.items():
            if tag_of(x) != "Object":
                continue
            csml_objects.add(key(name[2:]))
            self.object_type_value(name, x)
            cls = self.lookup(name)
            if cls is None:
                not_implemented.append(f"Object {name}")
                continue
            self.object_type(x, cls)

        for k, cls in sorted(self.objects.items()):
            if k not in csml_objects:
                msg = f"EXTRA object type {cls.__name__} ({cls.objectType.asn1})"
                if cls.__name__ in KEPT_OBJECTS:
                    self.note(["bacpypes3.object"], msg)
                else:
                    self.problem(["bacpypes3.object"], msg)
        return not_implemented


def report(compare, not_implemented, show_all):
    """Print the findings, return the number of problems."""
    count = 0
    for name in sorted(
        set(compare.problems) | (set(compare.info) if show_all else set())
    ):
        lines = compare.problems.get(name, [])
        if show_all:
            lines = lines + [f"(info) {line}" for line in compare.info.get(name, [])]
        if not lines:
            continue
        cls = compare.lookup(name)
        print(f"## {name} -> {compare.name_of(cls) if cls else '?'}")
        for line in lines:
            print(f"    {line}")
        count += len(compare.problems.get(name, []))

    if not_implemented:
        print("## not implemented")
        for line in not_implemented:
            print(f"    {line}")
        count += len(not_implemented)

    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "xml", nargs="+", help="bacnet-data-types.xml and/or bacnet-object-types.xml"
    )
    parser.add_argument(
        "--all", action="store_true", help="include informational notes"
    )
    args = parser.parse_args()

    files = []
    for path in args.xml:
        definitions = ET.parse(path).getroot().find(NS + "Definitions")
        is_objects = any(tag_of(e) == "Object" for e in children(definitions))
        files.append((path, definitions, is_objects))

    # with both files the object definitions are checked against the datatypes
    datatypes = next((d for _, d, is_objects in files if not is_objects), None)

    total = 0
    for path, definitions, is_objects in files:
        if is_objects:
            compare = ObjectCompare(definitions, datatypes)
        else:
            compare = Compare(definitions)

        if len(args.xml) > 1:
            print(f"# {path}")
        count = report(compare, compare.run(), args.all)
        print(
            f"\n{count} problem(s)\n" if len(args.xml) > 1 else f"\n{count} problem(s)"
        )
        total += count

    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
