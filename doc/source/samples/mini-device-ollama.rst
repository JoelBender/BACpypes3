.. mini-device-ollama.md walkthrough

.. _mini-device-ollama:

Driving mini-device-with-mcp.py from a local Ollama model
=========================================================

Since :mod:`bacpypes3.mcp` speaks the Model Context Protocol over HTTP, any
MCP-aware LLM host can drive it — including a fully local one. This
walkthrough runs three processes on the same laptop:

1. :ref:`mini-device-with-mcp.py` — the BACpypes3 mini-device sample,
   with an embedded MCP HTTP server on ``http://127.0.0.1:8765/mcp``.
2. `Ollama <https://ollama.com>`_ — serving a local model that supports
   tool calling.
3. An MCP host such as
   `mcphost <https://github.com/mark3labs/mcphost>`_ (or its actively-
   maintained successor `kit <https://github.com/mark3labs/kit>`_) that
   connects the two: it pulls the tool list from BACpypes3, hands it to
   the Ollama model, and executes any tool calls the model decides to
   make.

The result: you type an English request into the terminal, the local
model plans and executes BACnet operations against the embedded device,
and you see the read/write results come back.

The full walkthrough — prerequisites, model selection guidance,
``~/.mcphost.yml`` configuration, example prompts, and troubleshooting —
lives alongside the sample as
`samples/mini-device-ollama.md
<https://github.com/JoelBender/BACpypes3/blob/main/samples/mini-device-ollama.md>`_.

Related samples:

* :ref:`mini-device-with-mcp.py` — the BACnet + MCP server used above.
* :ref:`mini-device-mcp.sh` — a ``curl``-based MCP client, useful for
  debugging the wire protocol when the LLM path isn't working.
* :ref:`bacpypes3.mcp` — the module reference and full tool list.
