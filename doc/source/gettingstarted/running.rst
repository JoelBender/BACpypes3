.. BACpypes Getting Started 1

.. _running:

Running BACpypes3
=================

The **bacpypes3** module can be run directly.  It will create a small
:term:`stack` of communications objects that are bound together as a
:term:`BACnet device` and present a shell-like prompt::

    $ python3 -m bacpypes3
    >

For these examples assume that the workstation is running on a device with
an IPv4 address **192.168.0.10** and its subnet mask is **255.255.255.0**.
Without extra help, the module will only open the unicast socket and attempts
to broadcast traffic will result in a run time error "no broadcast".

Communications Configuration
----------------------------

The default stack is for a "normal" IPv4 device.  In addition to a unicast
communication socket, if it is provided the size of the subnet then it will
also open a listen-only broadcast socket using the same port number and shared
by all of the devices on the subnet.

Normal Device
~~~~~~~~~~~~~

The **bacpypes3** module can be provided with an `--address` option which not
only provides the IPv4 address to use, but also the subnet mask.  For example
this uses the CIDR notation::

    $ python3 -m bacpypes3 --address 192.168.0.10/24

And this uses the subnet mask notation::

    $ python3 -m bacpypes3 --address 192.168.0.10/255.255.255.0

.. note::

    The most of the examples in this documentation and sample code will use
    the CIDR notation.

If there is already a BACnet application running on the workstation and the
standard port is being used, the address can also specify an alternate port
number::

    $ python3 -m bacpypes3 --address 192.168.0.10/24:47809

If `ifaddr <https://pypi.org/project/ifaddr/>`_ is installed then the user
can provide the interface name::

    $ python3 -m bacpypes3 --address enp0s25

The interface names can be listed with the `ip link show` command in Linux.

Foreign Device
~~~~~~~~~~~~~~

If the workstation is not on the same IP network as other devices, it can
register as a :term:`foreign device` with a time-to-live option::

    $ python3 -m bacpypes3 --foreign 192.168.1.11 --ttl 30

It will use an :term:`ephemeral port` for unicast messages to the other devices
and reject/drop IPv4 broadcast messages it receives.  It will still receive
BACnet broadcast messages that have been forwarded by the BBMD, these are IPv4
unicast messages.

BACnet Broadcast Management Device
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The workstation can also be a BBMD when it is provided a Broadcast Distribution
Table (BDT)::

    $ python3 -m bacpypes3 --address 192.168.0.10/24 --bbmd 192.168.0.10 192.168.1.11

Device Configuration
--------------------

BACnet devices require that they have a *device object* with some properties
that uniquely identify on the network such as a name and a device instance
number.  These options are also available::

    $ python3 -m bacpypes3 --name Intrepid --instance 998

The default name is **Excelsior** and the default instance number is **999**.

The device object also has a *vendor-identifier* property which is used to
understand what proprietary objects and/or properties are available::

    $ python3 -m bacpypes3 --vendor-identifier 888

The default vendor identifier is **999**, the vendor identifier used for
sample applications is **888**.  Vendor identifiers are free and assigned by
`ASHRAE <https://www.ashrae.org/file%20library/technical%20resources/standards%20and%20guidelines/procedures-vendor-id-rev3-15-2012.pdf>`_.


Shell Commands
--------------

Who-Is
~~~~~~

Usage::

    > whois [ address [ low_limit high_limit ] ]

This command sends a Who-Is Request (Clause 16.10.1) and waits for one
or more responses.  It will wait up to three seconds for responses, and if the
high limit and low limit are identical it will complete as soon as the device
responds, if at all.

The *address* can be any of the five types of addresses; local station, local
broadcast, remote station, remote broadcast, or global broadcast.  For address
syntax patterns see :doc:`addresses`.

The *low_limit* and *high_limit* are both unsigned integers less than or equal
to 4194303.  Note that 4194303 is a special device identifier reserved for
devices that have not been configured.

.. note:: Clause 12.1.1

    Object properties that contain values whose datatype is
    BACnetObjectIdentifier may use 4194303 as the instance number to indicate
    that the property is uninitialized, disabled, or unused, except where noted
    in individual clauses.

.. note:: Clause 19.7.1

    A Device in a BACnet network might have a network MAC address, but require
    a Device Identifier, and still be connected to the network. Discovering
    these unconfigured devices may be performed by using the Who-Is service
    parameters Device Instance Range Low Limit with a value of 4194303, and
    Device Instance Range High Limit with a value of 4194303. These
    unconfigured devices respond with Who-Am-I service. The discovered devices
    can then be assigned a valid Device Identifier using the You-Are service.


I-Am
~~~~

Usage::

    > iam [ address ]

This command sends an I-Am Request (Clause 16.10.2) with the contents of the
appropriate properties of the device object.

The *address* can be any of the five types of addresses; local station, local
broadcast, remote station, remote broadcast, or global broadcast.  For address
syntax patterns see :doc:`addresses`.

Who-Has
~~~~~~~

Usage::

    > whohas [ low_limit high_limit ] [ objid ] [ objname ] [ address ]

This is a long line of text.

I-Have
~~~~~~

Usage::

    > ihave objid objname [ address ]

This command sends an I-Have Request (Clause 16.9.3)

The *objid* is an object identifier. For object identifier syntax see
:doc:`objectidentifiers`.

The *objname* is an object name.

The *address* can be any of the five types of addresses; local station, local
broadcast, remote station, remote broadcast, or global broadcast.  For address
syntax patterns see :doc:`addresses`.

Read-Property
~~~~~~~~~~~~~

Usage::

    > read address objid prop[indx]

The *address* is a local station or remote station. For address syntax patterns
see :doc:`addresses`.

The *objid* is the object identifier of the object in the device. For object
identifier syntax see :doc:`objectidentifiers`.

The *prop[indx]* is the property identifier optionally followed by an array
index enclosed in square brackets following BACnet rules for arrays.  For
example, this will read the *present-value* of the Analog Value Object
(Clause 12.4.4)::

    > read 192.168.0.18 analog-value,2 present-value

This will read the entire *priority-array*::

    > read 192.168.0.19 analog-output,3 priority-array

This will read the length of the *object-list*::

    > read 192.168.0.20 device,1001 object-list[0]

This will read the third element of the *object-list*::

    > read 192.168.0.21 device,1002 object-list[3]

Write-Property
~~~~~~~~~~~~~~

Usage::

    > write address objid prop[indx] value [ priority ]

This command sends a Write Property Request (Clause 15.9) and waits for the
response.

The *address* is a local station or remote station. For address syntax patterns
see :doc:`addresses`.

The *objid* is the object identifier of the object in the device. For object
identifier syntax see :doc:`objectidentifiers`.

The *prop[indx]* is the property identifier optionally followed by an array
index enclosed in square brackets following BACnet rules for arrays.

The *value* is the value to write to the property.  The syntax of the value
depends on the datatype of the property being written.

The optional *priority* is an unsigned integer in the range 1..16.

For example, this will write to the *present-value* of the Analog Value Object
(Clause 12.4.4)::

    > write 192.168.0.18 analog-value,2 present-value 75.3

This will command the Analog Output present value to 81.2 at priority level
10::

    > write 192.168.0.19 analog-output,3 present-value 80.2 10

This will release the command from the previous command::

    > write 192.168.0.19 analog-output,3 present-value null 10

.. note::

    Primitive values can be written from the module but the shell commands
    are simple.  Writing arrays and structures (sequences) can be written
    through code.

Read-Property-Multiple
~~~~~~~~~~~~~~~~~~~~~~

Usage::

    > rpm address ( objid ( prop[indx] )... )...

This command sends a Read Property Multiple Request (Clause 15.7) to the
device and decodes the response.

The *address* is a local station or remote station. For address syntax patterns
see :doc:`addresses`.

The *objid* is the object identifier of the object in the device. For object
identifier syntax see :doc:`objectidentifiers`.

The *prop[indx]* is the property identifier optionally followed by an array
index enclosed in square brackets following BACnet rules for arrays.

The property name may also be *all*, *required*, or *optional*.

For example, this command will read the values of all of the required properties
of the Binary Value Object::

    > rpm 192.168.0.20 binary-value,12 all

Who-Is-Router-To-Network
~~~~~~~~~~~~~~~~~~~~~~~~

Usage::

    > wirtn [ address [ network ] ]

This command sends a Who-Is-Router-To-Network (Clause 6.4.1) to another device
requesting it to respond with an I-Am-Router-To-Network (Clause 6.4.2).

The *address* is typically a local broadcast address used for determining the
network topology relative to the requesting device.  This command supports
sending it to any of the five address types; local station, local broadcast,
remote station, remote broadcast, or global broadcast. For address syntax
patterns see :doc:`addresses`.

The optional *network* is a unsigned integer in the range 0..65534.

Initialize-Routing-Table
~~~~~~~~~~~~~~~~~~~~~~~~

Usage::

    > irt [ address ]

This commands sends an Initialize-Routing-Table message to a router with no
supplimental routing table information, requesting the router to response with
its current routing table.

The *address* is typically a local station address used for determining the
network topology relative to the requesting device.  For address syntax
patterns see :doc:`addresses`.

Read-Broadcast-Distribution-Table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Usage::

    > rbdt ip-address

This command sends a Read-Broadcast-Distribution-Table Request (Clause X.Y.Z) to
a BBMD which will respond with its broadcast distribution table.

The *ip-address* is an IPv4 or IPv6 address.

Read-Foreign-Device-Table
~~~~~~~~~~~~~~~~~~~~~~~~~

Usage::

    > rfdt ip-address

This command sends a Read-Foreign-Device-Table Request (Clause X.Y.Z) to
a BBMD which will respond with its foreign device table which includes the
addresses and the time-to-live of the registered devices.

The *ip-address* is an IPv4 or IPv6 address.

Configuration
~~~~~~~~~~~~~

It is convenient to use the BACpypes3 module with the command line parameters
to let the module build the appropriate objects and properties, then save that
configuration to be used by other applications.  The configuration command
dumps out the configuration in a variety of formats; JSON, YAML and RDF.

    > config json

    > config yaml

    > config rdf

The output of the BACpypes3 shell can be redirected to a file, so it is quite
handy to say this::

    $ echo "config json" | python3 -m bacpypes3 > sample-config.json

