# BACpypes3 - Python library for BACnet applications

BACpypes provides a BACnet application layer and network layer written in
Python for daemons, scripting, and graphical interfaces.  This version is the
next generation for Python3.8+, completely overhauled from the Python2.5+
version using async/await methods and asyncio for communications.

## MCP (Model Context Protocol) integration

The `bacpypes3.mcp` module exposes the BACpypes3 CLI commands (`whois`,
`read`, `write`, `rpm`, `wirtn`, BBMD ops, …) as MCP tools with natural names
(`who_is`, `read_property`, `write_property`, `read_property_multiple`,
`who_is_router_to_network`, …). It has three personalities:

1. **Importable library.** Each tool is a plain `async` function returning
   JSON-serializable Python values. Inject an `Application` and call the
   tools directly.
2. **Stand-alone MCP server.** `python -m bacpypes3.mcp <BACpypes flags>`
   builds an `Application` via `SimpleArgumentParser` and serves the tools
   over stdio using FastMCP.
3. **Embedded server.** A long-running BACnet server can inject its own
   `Application` and start `mcp.serve_http(...)` as a concurrent asyncio
   task, so an LLM agent can drive it over HTTP without fighting the host
   application's stdout. See `samples/mini-device-with-mcp.py` for the
   reference pattern.

The `mcp` and `pydantic` packages are declared as an optional extra and are
only imported when a server is actually built; the tool functions are usable
without them:

    pip install -e ".[mcp]"      # to run the server
