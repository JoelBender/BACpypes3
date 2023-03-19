.. BACpypes3 Addresses

UDP Communications
==================

BACnet devices communicate using UDP rather than TCP.  This is so
devices do not need to implement a full IP stack (although
many of them do because they support multiple protocols, including
having embedded web servers).

There are two types of UDP messages; *unicast* which is a message
from one specific IP address (and port) to another device's IP address
(and port); and *broadcast* messages which are sent by one device
and received and processed by all other devices that are listening
on that port.  BACnet uses both types of messages and your workstation
will need to receive both types.

To receive both unicast and broadcast addresses, BACpypes3
opens two sockets, one for unicast traffic and one that only listens
for broadcast messages.  The operating system will not allow two applications
to open the same socket at the same time so to run two BACnet applications at
the same time they need to be configured with different ports.

.. note::

    The BACnet protocol has been assigned port 47808 (hex 0xBAC0) by
    by the `Internet Assigned Numbers Authority <https://www.iana.org/>`_, and sequentially
    higher numbers are used in many applications (i.e. 47809, 47810,...).
    There are some BACnet routing and networking issues related to using these higher unoffical
    ports, but that is a topic for another tutorial.

