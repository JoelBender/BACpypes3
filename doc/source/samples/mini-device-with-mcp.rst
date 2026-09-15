.. mini-device-with-mcp.py sample application

.. _mini-device-with-mcp.py:

mini-device-with-mcp.py
=======================

A minimal BACnet server (the same four points as ``mini-device-revisited.py``)
that also exposes an MCP (Model Context Protocol) server on HTTP so an LLM
agent can drive it from outside the process.

This is the reference pattern for embedding :mod:`bacpypes3.mcp` in a
long-running application that owns its own :class:`~bacpypes3.app.Application`.
Two things make it work:

1. Inject the running app: ``mcp.set_application(self.app)``.
2. Start MCP as a concurrent asyncio task on a transport that does not
   touch stdio: ``mcp.serve_http(...)``. Do **not** use ``serve_stdio``
   here — it would fight this process's own stdout.

Install the ``mcp`` extra first, then run::

    pip install -e ".[mcp]"
    python samples/mini-device-with-mcp.py --name Demo --instance 3456

The MCP client connects to ``http://127.0.0.1:8765/mcp`` and can call
tools like ``who_is``, ``read_property``, ``write_property``, and
``get_config``. Because the injected app is this device, ``get_config``
returns *this* server's identity and object list; ``read_property`` and
``write_property`` use this server's network stack to talk to remote
devices, and remote BACnet clients can independently poll and command the
four local objects hosted here.

See :ref:`bacpypes3.mcp` for the full tool list and public API. For a
minimal shell-only client that drives this server with ``curl``, see
:ref:`mini-device-mcp.sh`. To drive it from a local LLM instead, see
:ref:`mini-device-ollama`.
