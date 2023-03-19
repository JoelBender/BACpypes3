.. BACpypes glossary

Glossary
========

.. glossary::

    BACnet
        BACnet (Building Automation and Control Network) is the global data
        communications standard for building automation and control networks.
        It provides a vendor-independent networking solution to enable
        interoperability among equipment and control devices for a wide range
        of building automation applications. BACnet enables interoperability
        by defining communications messages, formats and rules for exchanging
        data, commands, and status information. BACnet provides the data
        communications infrastructure for intelligent buildings and is
        implemented in hundreds of thousands of buildings around the world.

        The BACnet standard was developed and is continuously maintained by the
        BACnet Committee, more formally known as SSPC 135 (a Standing Standards
        Project Committee) of the American Society of Heating, Refrigerating
        and Air-Conditioning Engineers (ASHRAE).
        
        BACnet is an ISO standard (EN ISO 16484-5), a European standard (DIN EN
        ISO 16484-5:2017-12) and a national standard in many countries.

    BACnet device
        Any device, real or virtual, that supports digital communication using
        the BACnet protocol.

    BACnet network
        A network of BACnet devices that share the MAC or VMAC address space
        under a particular BACnet network number.

    BACnet internetwork
        A set of two or more networks interconnected by BACnet routers. In a
        BACnet internetwork interconnected by BACnet routers, there exists
        exactly one message path between any two nodes.

    BACnet Device
        Any device, real or virtual, that supports digital communication using
        the BACnet protocol.

    ephemeral port
        An ephemeral port is a communications endpoint (port) of a transport
        layer protocol of the Internet protocol suite that is used for only a
        short period of time for the duration of a communication session.
        Such short-lived ports are allocated automatically within a predefined
        range of port numbers by the IP stack software of a computer operating
        system. `Wikipedia <https://en.wikipedia.org/wiki/Ephemeral_port>`_

    upstream
        Something going up a stack from a server to client.

    downstream
        Something going down a stack from a client to a server.

    stack
        A sequence of communication objects organized in a semi-linear sequence
        from the application layer at the top to the physical networking layer(s)
        at the bottom.

    discoverable
        Something that can be determined using a combination of BACnet objects,
        properties and services.  For example, discovering the network topology
        by using Who-Is-Router-To-Network, or knowing what objects are defined
        in a device by reading the *object-list* property.
