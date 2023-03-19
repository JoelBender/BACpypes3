.. BACpypes3 Addresses

BACpypes3 Addresses
===================

BACpypes3 addresses are used to communicate between BACnet devices directly
(one local station to another) or through a router (a local station through one
or more routers to another local station).

There are also special addresses to send a message to all of the stations on
the local network (called a "local broadcast"), all of the stations on a 
specific network through one of more routers (called a "remote broadcast") or
to all of the stations on all of the networks (called a "global broadcast").

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
     - IPv4, alternate port
   * -
     - 192.168.0.14/24:47809
     - IPv4 CIDR, alternate port
   * -
     - 192.168.0.15/255.255.255.0:47809
     - IPv4 subnet mask, alternate port 47809
   * -
     - 01:02:03:04:05:06
     - Ethernet address
   * -
     - 0x010203
     - VLAN address
   * -
     - [fe80::9873:c319]
     - IPv6
   * -
     - [fe80::9873:c319]:47809
     - IPv6, alternate port 47809
   * -
     - [fe80::9873:c319/64]
     - IPv6 network mask, standard port 47808
   * -
     - enp0s25
     - Interface name (ifaddr)
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
     - VLAN address
   * - Remote Broadcast
     - 100:\*
     -
   * - Global Broadcast
     - \*:\*
     -

BACpypes3 has a special addressing mode called **route aware** that allows
applications to bypass the router-to-network discovery and resolution process
and send a message to a specific router.

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
     - 200:192.168.0.19\@192.168.0.20
     - IPv4 via IPv4
   * -
     - 200:0x030405\@192.168.0.20
     - VLAN via IPv4
   * - Remote Broadcast
     - 200:\*\@192.168.0.21
     - ARCNET, MS/TP via IPv4
   * - Global Broadcast
     - \*:\*\@192.168.0.22
     - all devices via IPv4

