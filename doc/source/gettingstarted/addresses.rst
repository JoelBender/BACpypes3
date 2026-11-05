.. BACpypes3 Addresses

BACpypes3 Addresses
===================

BACpypes3 addresses are used to communicate between BACnet devices directly
(one local station to another) or through a router (a local station through one
or more routers to another local station).

There are also special addresses to send a message to all of the stations on
the local network (called a "local broadcast"), all of the stations on a
specific network through one or more routers (called a "remote broadcast") or
to all of the stations on all of the networks (called a "global broadcast").

Addresses are usually written as strings and parsed by the ``Address`` class,
which returns an object of the appropriate subclass:

.. code-block:: python

    >>> from bacpypes3.pdu import Address
    >>> Address("100:[fe80::9873:c319]:47809")
    <RemoteStation 100:[fe80::9873:c319]:47809>

.. list-table:: Address Patterns
   :widths: 25 25 50
   :header-rows: 1

   * - Type
     - Example
     - Context
   * - Local Station
     - 12
     - ARCNET, MS/TP
   * -
     - 192.168.0.10
     - IPv4, standard port 47808
   * -
     - 192.168.0.11/24
     - IPv4 CIDR, standard port 47808
   * -
     - 192.168.0.12/255.255.255.0
     - IPv4 subnet mask, standard port 47808
   * -
     - 192.168.0.13:47809
     - IPv4, alternate port 47809
   * -
     - 192.168.0.14/24:47809
     - IPv4 CIDR, alternate port 47809
   * -
     - 192.168.0.15/255.255.255.0:47809
     - IPv4 subnet mask, alternate port 47809
   * -
     - 01:02:03:04:05:06
     - Ethernet address
   * -
     - 0x010203
     - VLAN address, or any other address as hex bytes
   * -
     - [fe80::9873:c319]
     - IPv6, standard port 47808
   * -
     - [fe80::9873:c319]:47809
     - IPv6, alternate port 47809
   * -
     - [fe80::9873:c319/64]
     - IPv6 network mask, standard port 47808
   * -
     - [fe80::9873:c319/64]:47809
     - IPv6 network mask, alternate port 47809
   * -
     - enp0s25
     - IPv4 address of an interface, standard port 47808
   * -
     - enp0s25:47809
     - IPv4 address of an interface, alternate port 47809
   * -
     - host
     - IPv4 address of this host, standard port 47808
   * -
     - bacnet.example.com:47809
     - IPv4 address of a host name, alternate port 47809
   * - Local Broadcast
     - \*
     -
   * - Remote Station
     - 100:12
     - ARCNET, MS/TP
   * -
     - 100:192.168.0.16
     - IPv4, standard port 47808
   * -
     - 100:192.168.0.17:47809
     - IPv4, alternate port 47809
   * -
     - 100:0x010203
     - VLAN address, or any other address as hex bytes
   * -
     - 100:[fe80::9873:c319]
     - IPv6, standard port 47808
   * -
     - 100:[fe80::9873:c319]:47809
     - IPv6, alternate port 47809
   * - Remote Broadcast
     - 100:\*
     -
   * - Global Broadcast
     - \*:\*
     -

Network numbers are 0 to 65534 and numeric station addresses are 0 to 255;
longer station addresses are written as hex bytes, such as ``0x0102``.
IPv6 addresses must be in square brackets.

Interface names are resolved with the optional ``ifaddr`` or ``netifaces``
packages when one is installed, and any other name is resolved as a host name
with DNS. The interface or host must have exactly one IPv4 address. The name
``host`` is the IPv4 address this host uses to reach other networks.

``Address`` also accepts some values that are not strings:

* an ``int`` from 0 to 255, for an ARCNET or MS/TP station
* ``bytes`` of length 1 (ARCNET, MS/TP), 3 (VLAN), 6 (IPv4) or 18 (IPv6), in
  the same format as BACnet uses for the station address
* an ``(address, port)`` tuple, such as ``("192.168.0.10", 47809)`` or
  ``("fe80::9873:c319", 47809)``
* an ``ipaddress.IPv4Address`` or ``ipaddress.IPv6Address``

Route Aware Addresses
---------------------

BACpypes3 has a special addressing mode called **route aware** that allows
applications to bypass the router-to-network discovery and resolution process
and send a message to a specific router. The address of the router follows
an ``@``.

Route aware mode is off by default. Turn it on with the ``--route-aware``
command line option, by setting the environment variable
``BACPYPES_ROUTE_AWARE=true``, or in code:

.. code-block:: python

    from bacpypes3.settings import settings

    settings.route_aware = True

When it is off, an address with a route is still parsed but a warning is
logged.

.. list-table:: Route Aware Address Patterns
   :widths: 25 25 50
   :header-rows: 1

   * - Type
     - Example
     - Context
   * - Remote Station
     - 200:12\@192.168.0.18
     - ARCNET, MS/TP via IPv4
   * -
     - 200:12\@192.168.0.18:47809
     - ARCNET, MS/TP via IPv4, alternate port 47809
   * -
     - 200:192.168.0.19\@192.168.0.20
     - IPv4 via IPv4
   * -
     - 200:0x030405\@192.168.0.20
     - VLAN via IPv4
   * -
     - 200:12\@[fe81::1]
     - ARCNET, MS/TP via IPv6
   * -
     - 200:12\@[fe81::1]:47809
     - ARCNET, MS/TP via IPv6, alternate port 47809
   * -
     - 200:[fe80::67a9]\@[fe81::1]
     - IPv6 via IPv6
   * -
     - 200:192.168.0.19\@[fe81::1]
     - IPv4 via IPv6
   * -
     - 200:12\@5
     - ARCNET, MS/TP via ARCNET, MS/TP
   * -
     - 200:12\@0x030405
     - ARCNET, MS/TP via VLAN
   * - Remote Broadcast
     - 200:\*\@192.168.0.21
     - all devices on network 200 via IPv4
   * -
     - 200:\*\@[fe81::1]
     - all devices on network 200 via IPv6
   * - Global Broadcast
     - \*:\*\@192.168.0.22
     - all devices via IPv4
   * -
     - \*:\*\@[fe81::1]
     - all devices via IPv6
