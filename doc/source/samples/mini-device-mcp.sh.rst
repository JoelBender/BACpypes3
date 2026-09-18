.. mini-device-mcp.sh sample script

.. _mini-device-mcp.sh:

mini-device-mcp.sh
==================

Companion shell script for :ref:`mini-device-with-mcp.py`. Drives the
embedded MCP HTTP server with ``curl`` — no Python client required. Useful
for smoke-testing the server, seeing exactly what the MCP wire protocol
looks like, and scripting BACpypes3 operations from any shell.

Run ``mini-device-with-mcp.py`` in one terminal (it exposes an MCP server
on ``http://127.0.0.1:8765/mcp``), then in another terminal::

    ./samples/mini-device-mcp.sh                       # demo: who_is + i_am + read_property
    ./samples/mini-device-mcp.sh who_is                # one tool
    ./samples/mini-device-mcp.sh i_am
    ./samples/mini-device-mcp.sh read_property 192.168.1.10 analog-input,1 present-value

    MCP_URL=http://host:port/mcp ./samples/mini-device-mcp.sh …

Requires ``bash`` and ``curl``. If ``jq`` is installed, JSON output is
pretty-printed; otherwise the raw body is echoed.

What it demonstrates
--------------------

MCP over Streamable HTTP is JSON-RPC 2.0 with a specific handshake and
transport shape that isn't obvious from the tool list. This script is a
minimal, working example of that wire protocol:

1. **Handshake.** The first request is a JSON-RPC ``initialize`` call.
   The server picks a session ID and returns it in the ``Mcp-Session-Id``
   response header. Every subsequent request must echo that header back.
2. **``notifications/initialized``.** A required fire-and-forget
   notification (no ``id`` field, HTTP 202 Accepted, empty body) sent
   after ``initialize`` and before any tool call.
3. **``Accept: application/json, text/event-stream``.** Both media types
   must appear on every request — the server framing depends on it.
4. **SSE-framed responses.** Even single-shot request/reply pairs come
   back as a ``text/event-stream`` payload (``event: message\ndata:
   <json>\n\n``). The script strips the SSE framing before printing.
5. **``tools/call``.** Invokes a tool by name; the tool's typed return is
   at ``result.structuredContent.result`` in the reply.

See :ref:`bacpypes3.mcp` for the full tool list and the Python client
patterns.
