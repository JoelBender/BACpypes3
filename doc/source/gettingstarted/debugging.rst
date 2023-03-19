.. BACpypes Getting Started 1

.. _debugging:

Debugging BACpypes3
===================

The **bacpypes3** module and most BACpypes3 applications use a subclass of
the built-in `ArgumentParser` which includes options for debugging.  The library
creates loggers for each module and class and the application can attach
different log handlers to the loggers.

List of Loggers
---------------

The `\-\-loggers` option is used to list the available loggers::

    $ python3 -m bacpypes3 --loggers

This list also contains loggers for other modules and packages.

Debugging a Module
------------------

Telling the application to debug a module is simple:

.. code-block:: text

    $ python3 -m bacpypes3 --debug
    DEBUG:__main__:args: Namespace(loggers=False, debug=[], ...)
    DEBUG:__main__:app: <bacpypes3.app.Application object at 0x7f35a4dff880>
    DEBUG:__main__:local_adapter: <bacpypes3.netservice.NetworkAdapter object at 0x7f35a4dfe3b0>
        <bacpypes3.netservice.NetworkAdapter object at 0x7f35a4dfe3b0>
            adapterSAP = <bacpypes3.netservice.NetworkServiceAccessPoint object at 0x7f35a4dfeb00>
            adapterAddr = <IPv4Address 10.0.1.90>
            adapterNetConfigured = 0
    DEBUG:__main__:bvll_sap: <bacpypes3.ipv4.link.NormalLinkLayer object at 0x7f35a4dfe860>
    DEBUG:__main__:bvll_ase: <bacpypes3.ipv4.service.BVLLServiceElement object at 0x7f35a4dfe8f0>
    >

The output is the severity code of the logger (almost always DEBUG), the name
of the module, class, or function, then some message about the progress of the
application.  From the output above you can see the application has printed
out the `Namespace` instance resulting from parsing the arguments, an
`Application` instance was created, a `NetworkAdapter` was created which
contians some interesting attributes like a reference to a
`NetworkServiceAccessPoint`, and others.

Debugging a Class
-----------------

Debugging classes and functions can generate a lot of output, so it is useful
to focus on a specific function or class:

.. code-block:: text

    $ python3 -m bacpypes3 --debug bacpypes3.netservice.NetworkAdapter
    DEBUG:bacpypes3.netservice.NetworkAdapter:__init__ ...
        <bacpypes3.netservice.NetworkServiceAccessPoint object at 0x7f72ebc52b00>
            adapters = {}
            router_info_cache = <bacpypes3.netservice.RouterInfoCache object at 0x7f72ebc53fd0>
    >

This same method can be used to debug the activity of a an object:

.. code-block:: text

    $ python3 -m bacpypes3 --debug bacpypes3.ipv4.IPv4DatagramServer
    DEBUG:bacpypes3.ipv4.IPv4DatagramServer:__init__ <IPv4Address 10.0.1.90> no_broadcast=False
    DEBUG:bacpypes3.ipv4.IPv4DatagramServer:    - local_address: ('10.0.1.90', 47808)
    DEBUG:bacpypes3.ipv4.IPv4DatagramServer:    - local_endpoint_task: ...
    DEBUG:bacpypes3.ipv4.IPv4DatagramServer:set_local_transport_protocol ...
    ...
    > whois
    DEBUG:bacpypes3.ipv4.IPv4DatagramServer:indication <bacpypes3.pdu.PDU object at 0x7f04fbbe7490>
        <bacpypes3.pdu.PDU object at 0x7f04fbbe7490>
            pduDestination = <LocalBroadcast *>
            pduExpectingReply = False
            pduNetworkPriority = 0
            pduData = x'81.0b.00.0c.01.20.ff.ff.00.ff.10.08'
    ...

In this sample a low level object has had its `indication()` function called
with a message to be sent to all of the devices on the local network (the
destination of the UDP message is a localbroadcast) and some more decoding
shows that this is an original broadcast BVLL message that is a global
broadcast request.

Sending Debug Log to a file
----------------------------

The `\-\-debug` takes a list of loggers and attaches a `StreamHandler` which
sends the output to `stderr` be default.  With many applications it is useful
to redirect that output to a file for later analysis.  For example, this
will redirect the debugging output of the `__main__` module to the
**test-001.log** file::

    $ python3 -m bacpypes3 --debug __main__:test-001.log

These log files can become quite large, so you can redirect the debugging to
a `RotatingFileHandler` by providing a file name, and optionally maximum size and
backup count. For example, this invocation sends the main application debugging
to standard error and the debugging output of the bacpypes.udp module to the
**test-002.log** file::

    $ python3 -m bacpypes3 --debug bacpypes3.app.Application:test-002.log:1048576

If `maxBytes` is provided, then by default the `backupCount` is 10, but it can also
be specified, so this limits the output to one hundred files::

    $ python3 -m bacpypes3 --debug bacpypes3.app.Application:test-003.log:1048576:100

.. caution::

    The traffic.txt file will be saved in the local directory (pwd)

Turning on Color
----------------

The world is not always black and white, with the output of multiple handlers
being displayed it can be difficult to see patterns of activity between loggers,
the `\-\-color` option outputs each logger in a different color.

