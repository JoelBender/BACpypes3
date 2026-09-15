.. bacpypes3.mcp module and samples

.. _bacpypes3.mcp:

bacpypes3.mcp — Model Context Protocol integration
==================================================

The :mod:`bacpypes3.mcp` module exposes the BACpypes3 command-line operations
(``whois``, ``read``, ``write``, ``rpm``, ``wirtn``, BBMD ops, ...) as MCP
tools with natural names (``who_is``, ``read_property``, ``write_property``,
``read_property_multiple``, ``who_is_router_to_network``, ...). Each tool
returns JSON-serializable Python values, so an LLM agent can call them
directly.

The module has three personalities:

1. **Importable library.** Each tool is a plain ``async`` function you can
   call from your own code once an :class:`~bacpypes3.app.Application` has
   been injected.
2. **Stand-alone MCP server.** ``python -m bacpypes3.mcp <BACpypes flags>``
   builds an ``Application`` via :class:`~bacpypes3.argparse.SimpleArgumentParser`
   and serves the tools over stdio using FastMCP.
3. **Embedded server.** A long-running BACnet server can inject its own
   ``Application`` and start ``mcp.serve_http(...)`` as a concurrent
   asyncio task so it coexists with the host application's own stdout.

The ``mcp`` and ``pydantic`` packages are declared as an optional extra and
are only imported when a server is actually built. Install the extra to run
the server::

    pip install -e ".[mcp]"

The tool functions themselves are importable without either package
installed.

Tools
-----

======================================  =============================================
Tool                                    Underlying operation
======================================  =============================================
``who_is``                              Who-Is broadcast; returns list of I-Am dicts
``i_am``                                Unconfirmed I-Am
``who_has``                             Who-Has broadcast; returns list of I-Have dicts
``i_have``                              Unconfirmed I-Have
``read_property``                       ReadProperty on a remote object
``write_property``                      WriteProperty on a remote object
``read_property_multiple``              ReadPropertyMultiple on one device
``who_is_router_to_network``            Who-Is-Router-To-Network NPDU
``initialize_routing_table``            Initialize-Routing-Table NPDU (empty body)
``read_broadcast_distribution_table``   Read the BDT of a BACnet/IPv4 BBMD
``write_broadcast_distribution_table``  Write the BDT of a BACnet/IPv4 BBMD
``read_foreign_device_table``           Read the FDT of a BACnet/IPv4 BBMD
``get_config``                          Return this application's settings + objects
======================================  =============================================

Public API
----------

The importable surface is:

* ``set_application(app)`` / ``get_application()`` — inject/retrieve the
  ``Application`` the tools should drive.
* ``serve_http(host="127.0.0.1", port=8765, app=None)`` — HTTP transport,
  recommended for embedded use. Client connects to
  ``http://<host>:<port>/mcp``.
* ``serve_stdio(app=None)`` — stdio transport, for stand-alone use only.
  Do **not** use from an embedded application whose own stdout carries
  other output.
* ``register_tools(server)`` — register the BACpypes3 tools on an existing
  ``FastMCP`` instance you already own.
* ``build_server(name="bacpypes3", **fastmcp_kwargs)`` — build a fresh
  ``FastMCP`` server with every tool registered. Additional kwargs
  (``host``, ``port``, ``streamable_http_path``, ``stateless_http``,
  ``log_level``, ...) are forwarded to ``FastMCP(...)``.
* ``main()`` — the ``python -m bacpypes3.mcp`` entry point.
* ``TOOLS`` — tuple of the tool functions in registration order.

Direct invocation (importable library)
--------------------------------------

Build an ``Application``, inject it, and call the tools directly::

    import asyncio
    from bacpypes3.app import Application
    from bacpypes3.argparse import SimpleArgumentParser
    from bacpypes3 import mcp

    async def main() -> None:
        args = SimpleArgumentParser().parse_args()
        app = Application.from_args(args)
        try:
            mcp.set_application(app)
            result = await mcp.read_property(
                "10.0.0.5", "analog-input,1", "present-value"
            )
            print(result)  # JSON-serializable dict
        finally:
            app.close()

    asyncio.run(main())

Stand-alone MCP server (stdio)
------------------------------

Install the extra and run the module::

    pip install -e ".[mcp]"
    python -m bacpypes3.mcp --address 192.168.1.10/24 --instance 999

The process serves FastMCP over stdio, so it is intended to be launched by an
MCP client (e.g. an LLM agent) that owns the stdio streams.

Embedded server (HTTP)
----------------------

A long-running BACnet server (such as :ref:`mini-device-with-mcp.py`) can
add MCP at runtime by injecting its already-running ``Application`` and
starting the HTTP transport as a concurrent asyncio task. HTTP is preferred
here because stdio would clash with the host application's own stdout::

    from bacpypes3 import mcp

    class SampleApplication:
        def __init__(self, args):
            self.app = Application.from_args(args)
            # ... add local BACnet objects ...

            # 1. Point the mcp tools at THIS application
            mcp.set_application(self.app)

            # 2. Start MCP over HTTP as a concurrent task
            self.mcp_task = asyncio.create_task(
                mcp.serve_http(host="127.0.0.1", port=8765)
            )

An MCP client connects to ``http://127.0.0.1:8765/mcp`` and can call
``who_is``, ``read_property``, ``write_property``, ``get_config``, and the
other tools. Because the injected app is this device, ``get_config``
returns *this* server's identity and object list; reads and writes use this
server's network stack to talk to remote devices, while remote BACnet
clients can independently poll and command the local objects the host
registered.

The ``host`` defaults to loopback. Only bind to ``0.0.0.0`` behind an
authenticating proxy — FastMCP has no built-in authentication.

Reference: :ref:`mini-device-with-mcp.py`. For a shell-only client that
drives the same server with ``curl``, see :ref:`mini-device-mcp.sh`. To
drive it from a fully local LLM (Ollama + ``mcphost``/``kit``), see
:ref:`mini-device-ollama`.
