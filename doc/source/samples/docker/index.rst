.. docker samples

Docker Samples
==============

Running BACnet applications in docker is a challenge because the
environment that is normally presented to applications is not the
one that the host has because the intent is to protect containers
(running images) from interfering with or being interfered with
by other devices than the host.

Docker has a `\-\-network host <https://docs.docker.com/network/host/>`_
option so the container does not get its own IP address allocated,
which is helpful, but only for unicast traffic.  Attempts to "bind" to
broadcast addresses of the host fail.

The solution is to have BACpypes3 applications be configured as
a foreign device and register with a BBMD on the network.  To allow
more than one application running on the same host, the application
uses an :term:`ephemeral port` and the operating system will proved
provide an unused socket.

A side effect is that subsequent runs of the same image will present
most likely not have the same port number, so they will have different
BACnet/IPv4 addresses each time they are run.  During debugging it
might be beneficial to assign a fixed socket number.

This also means that the container can register as a foreign device
with some BBMD in the BACnet intranet.

Setting Up
----------

The docker samples are often used with unpublished versions of
BACpypes3, so the build scripts include a local build of the
package as a wheel.

The root folder of the BACpypes3 project has a `bdist.sh` script
which builds Python eggs and a wheel.

