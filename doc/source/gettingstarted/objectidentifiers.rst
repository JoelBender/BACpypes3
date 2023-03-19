.. BACpypes3 Addresses

Object and Property Identifiers
===============================

Object Identifiers
------------------

Every object in a BACnet device has an object identifier consisting of two
parts, an object type and an instance number:

.. code-block:: text

    object-type,instance

The *object-type* is the enumeration name in the ANS.1 definition of the
**BACnetObjectType** in Clause 21 such as `binary-input`, `calendar`, or
`device`.  The object type may also be an unsigned integer in the range 0..1023.

.. note::

    Enumerated values 0-127 are reserved for definition by ASHRAE. Enumerated
    values 128-1023 may be used by others subject to the procedures and
    constraints described in Clause 23.

The *instance* is an unsigned integer in the range 0..4194303, note that 4194303
is reserved for "uninitialized."

.. caution::

    BACpypes3 also supports the legacy BACpypes format where the object type
    and instance are separated by a colon ':' and the object type names are
    lower-camel-case such as `binaryInput`.  This format is discouraged and may
    be deprecated in a future version of BACpypes3.

Property Identifiers
--------------------

Every property of a BACnet object has a property identifier:

.. code-block:: text

    property-identifier

The *property-identifier* is the enumeration name in the ASN.1 definition of the
**BACnetPropertyIdentifier** in Clause 21 such as `object-name`, `description`,
or `present-value`.  The property identifier may also be an unsigned integer in
the range 

.. note::

    Enumerated values 0-511 and enumerated values 4194304 and up are reserved
    for definition by ASHRAE. Enumerated values 512-4194303 may be used by
    others subject to the procedures and constraints described in Clause 23.

