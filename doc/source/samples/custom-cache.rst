.. custom-cache.py sample application

.. _custom-cache.py:

custom-cache.py
===============

This application *is a start* of a custom device information cache implementation
that uses Redis as a shared cache for DeviceInfo records.

The Redis keys will be `bacnet:dev:address` where `address` is the address of
the device and may include the network like `10:1.2.3.4` for an IPv4 device
on network 10.

This application is also *a start* of a custom routing information cache
implementation that also uses Redis as a shared cache for Who-Is-Router-To-Network
content.  When a request is sent to a remote station or remote broadcast, the
cache is used to return the address of the router to the destination network.

The Redis keys will be `bacnet:rtn:snet:dnet` and the key value is the address
of the router on the `snet` that is the router to the `dnet`.

