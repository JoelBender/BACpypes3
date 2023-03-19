.. start-here.py sample application

.. _start-here.py:

start-here.py
=============

This is a good place to start.

BACnet is a peer-to-peer protocol so devices can be clients (issue requests) and
servers (provide responses) and are often both at the same time.  This sample
has just enough code to make itself known on the network and can be used as
a starting point for predominantly client-like applications (reading data from
other devices) or server-like applications (gateways).

The `SimpleArgumentParser` is the same one the module uses, see :ref:`running`::

    args = SimpleArgumentParser().parse_args()
    if _debug:
        _log.debug("args: %r", args)

The `Application` class has different class methods for building an application
stack, the `from_args()` method is looks for the options from the simple
argument parser.  Custom applications can add additional options and/or use
their own subclass::

    # build an application
    app = Application.from_args(args)
    if _debug:
        _log.debug("app: %r", app)

Server-like applications just run::

    # like running forever
    await asyncio.Future()

.. note::

    The `ReinitializeDevice` service can be used to quit the current application
    which is in turn wrapped by some supervisory service that automatically
    restarts it such as
    `systemd <https://manpages.ubuntu.com/manpages/kinetic/man5/systemd.service.5.html>`_
    or `docker <https://docs.docker.com/config/containers/start-containers-automatically/>`_.
