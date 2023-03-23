.. BACpypes3 Samples

Samples
=======

.. toctree::
   :maxdepth: 2
   :caption: Contents:

The samples can be used as a jumping off point to build your own applications
or to incorporate BACnet communications into your existing project.

BACpypes3 applications are built in layers with a :term:`stack` consisting of
some kind of link layer, a common network layer, and a customized application
layer.  The layers communicate with each other using a **client/server** design
pattern, start with the :ref:`console.py` application to learn about this
pattern.

Console Samples
---------------

These samples are designed to be run in combination from different
terminal/shell windows with different combinations of initialization command
line parameters or configuration files.

.. toctree::
    :maxdepth: 1

    console.rst
    console-prompt.rst
    console-ini.rst
    console-json.rst
    console-yaml.rst

Command Samples
~~~~~~~~~~~~~~~

The BACpypes3 `Cmd` class ...

.. toctree::
    :maxdepth: 1

    cmd-address.rst
    cmd-debugging.rst
    cmd-samples.rst

VLAN Samples
~~~~~~~~~~~~

BACpypes3 has a Virtual Local Area Network (VLAN) concept which is for building
networks of devices within an application.  For example, a BACnet-to-MODBUS
gateway that is designed to present each of the other MODBUS devices as a
BACnet device on a virtual network, then the application will be seen as a
BACnet router to this virtual network.

It is also very handy in testing, for example different combinations of clients
and servers can be collected together to see how they behave all within one
application.

It is also useful for tutorials explaining how the BACnet network layer works.

.. toctree::
    :maxdepth: 1

    vlan-console-1.rst
    vlan-console-2.rst
    vlan-console-3.rst

Common Code
-----------

BACnet is a peer-to-peer protocol so devices can be clients (issue requests) and
servers (provide responses) and are often both at the same time.  The
:ref:`start-here.py` sample application has just enough code to make itself
known on the network and can be used as a starting point for predominantly
client-like applications (reading data from other devices) or server-like
applications (gateways).  The console samples in this group show different
options for configuring applications.

.. toctree::
    :maxdepth: 1

    start-here.rst

Client Samples
--------------

If you are building applications that browse around the BACnet network and
read or write property values of objects, these are good starting points.  Some
of these are stand-alone application versions of the shell commands.

.. toctree::
    :maxdepth: 1

    read-property.rst
    write-property.rst
    read-batch.rst
    read-bbmd.rst
    who-has.rst
    custom-client.rst
    cov-client.rst

Browsing around the network to initialize or synchronize a local database with
the BACnet network is so common that there are example applications for that.

.. toctree::
    :maxdepth: 1

    discover-devices.rst
    discover-objects.rst

Server Samples
--------------

.. toctree::
    :maxdepth: 1

    custom.rst
    custom-server.rst
    cov-server.rst
    router-json.rst

Docker Samples
--------------

These samples are examples of building and running docker images, these
applications and scripts are in a docker subfolder.

.. toctree::
    :maxdepth: 1

    docker/index.rst

Link Layer Samples
------------------

These samples were used during development of the IPv4, IPv6 and SC link layers.

.. toctree::
    :maxdepth: 1

    start-here.rst

Miscellaneous
-------------

These samples are interesting bits and pieces.

.. toctree::
    :maxdepth: 1

    apdu-hex-decode.rst
    console-ase-sap.rst
    custom-cache.rst
