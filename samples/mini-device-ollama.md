# Driving `mini-device-with-mcp.py` from a local Ollama model

`bacpypes3.mcp` speaks the Model Context Protocol over HTTP, so any MCP-aware
LLM host can drive it — including a fully local one. This walkthrough runs
three processes on the same laptop:

1. **`mini-device-with-mcp.py`** — the BACpypes3 mini-device sample, with an
   embedded MCP HTTP server on `http://127.0.0.1:8765/mcp`.
2. **Ollama** — serving a local model that supports tool calling.
3. **`ollmcp`** — a small MCP host that connects the two: it pulls the tool
   list from BACpypes3, hands it to the Ollama model, and executes any tool
   calls the model decides to make.

The result: you type an English request into the terminal, the local model
plans and executes BACnet operations against the embedded device, and you
see the read/write results come back.

```
  You  ──►  ollmcp  ──►  Ollama (local model, decides which tools to call)
                 │
                 └──►  bacpypes3.mcp HTTP server  ──►  Application  ──►  BACnet network
                       (mini-device-with-mcp.py)
```

---

## Prerequisites

- Python 3.10+ (the `mcp` package requires it).
- The BACpypes3 checkout with the `mcp` extra installed:

      pip install -e ".[mcp]"

- **[Ollama](https://ollama.com/download).** After install, confirm the
  daemon is running:

      ollama --version
      curl -s http://127.0.0.1:11434/api/tags

- **A tool-capable Ollama model.** Ollama's model library flags each entry
  that supports tool calling; browse
  <https://ollama.com/search?c=tools> and pick one that fits your RAM. The
  examples below use `qwen3.5:9b` (a good starting point at ~5 GB); if your
  machine is tight on RAM try `gemma4:2b`, and if you have a workstation-class
  GPU `qwen3.5:22b` or larger will follow instructions more reliably.
  Whichever you pick, the model page must show a **Tools** badge — models
  without tool support cannot drive MCP servers.

      ollama pull qwen3.5:9b

- **[`ollmcp`](https://github.com/jonigl/mcp-client-for-ollama).** A tiny
  Ollama-native MCP client — no config file, no compilation, no daemon; the
  Ollama host URL, MCP server URL, and model name are all passed on the
  command line. If you have `uv` installed there is nothing to install
  separately — `uvx ollmcp` fetches and runs it on demand.

---

## Step 1 — start the BACpypes3 mini-device + MCP server

In terminal 1:

```
python samples/mini-device-with-mcp.py --name Demo --instance 3456
```

The sample builds an `Application`, adds four points (two read-only, two
commandable), and starts an MCP HTTP server on `127.0.0.1:8765`. The log
line to look for is:

```
MCP server listening on http://127.0.0.1:8765/mcp
```

Leave this terminal running for the rest of the walkthrough. The embedded
BACnet server is fully live — it will respond to Who-Is, ReadProperty, and
WriteProperty from any other BACnet client on the network, and the MCP host
you'll connect below drives it through the same in-process `Application`.

*Sanity check:* from a third terminal, `samples/mini-device-mcp.sh` will
handshake with the MCP server via `curl` and confirm tools are reachable
before you bring the LLM into the picture.

## Step 2 — start Ollama and confirm the model runs

Ollama is normally installed as a system service; if it isn't already
running, start it:

```
ollama serve
```

Confirm the model responds:

```
ollama run qwen3.5:9b "hello"
```

The first prompt loads the model into memory (10–60 seconds depending on
size); subsequent prompts are fast.

## Step 3 — run `ollmcp` against both endpoints

In terminal 2:

```
uvx ollmcp \
    --host http://localhost:11434/ \
    --mcp-server-url http://127.0.0.1:8765/mcp \
    --model qwen3.5:9b
```

Flag breakdown:

- `--host` is the Ollama daemon's HTTP endpoint. `http://localhost:11434/`
  is the Ollama default; point it elsewhere if the daemon is on another
  machine.
- `--mcp-server-url` is BACpypes3's Streamable-HTTP MCP endpoint — `ollmcp`
  handles the `initialize` handshake, `Mcp-Session-Id` header, and
  `notifications/initialized` automatically, so the details
  `mini-device-mcp.sh` performs by hand are done for you.
- `--model` picks the Ollama model to drive. Any model on Ollama's
  tool-calling list works; swap `qwen3.5:9b` for the model you pulled.

`bacpypes3.mcp` has no authentication (do not expose it beyond loopback
without an auth proxy), so no additional headers or credentials are needed.

`ollmcp` starts an interactive REPL, connects to
`http://127.0.0.1:8765/mcp`, lists the BACpypes3 tools (`who_is`,
`read_property`, `write_property`, `read_property_multiple`, `get_config`,
…), and passes them to the model.

## Step 4 — talk to your BACnet device

Try prompts like these — `ollmcp` prints each tool invocation and its
result so you can see the model's plan unfold:

```
> Discover BACnet devices on this network.

> Discover every BACnet device on the entire intranet, including any that
  sit behind BACnet routers on other networks.

> Find every BACnet device with an instance number between 1000 and 1999.

> Find the BACnet device with instance number 3456 and tell me its address.

> Read the present value of analog-value,1 on device 3456.

> Show me the configuration of the local BACpypes3 server.

> Set commandable-av to 42 with priority 8.

> Compare the present values of analog-value,1 and analog-value,2 across the
  next three polls and tell me which is higher on average.
```

The last one is where hosting a small local model shines: the model plans
the sequence of `read_property` calls itself, without you writing a client.

Everything the model does is visible in the mini-device-with-mcp.py logs
too — you can watch it enumerate objects, read points, and write to the
commandable ones.

---

## Tips and troubleshooting

**Model won't call tools.** Small models occasionally refuse to invoke
tools even when they're listed. Try a larger tool-calling model
(`qwen3.5:22b`, `minimax-m3`, `nemotron3`) or raise the model's context
window with `OLLAMA_CONTEXT_LENGTH=8192` before starting Ollama. Verify the
model's Ollama page shows the **Tools** badge.

**"connection refused" from `ollmcp`.** Check that `mini-device-with-mcp.py`
is still running and that its logs show the MCP server listening. `curl
http://127.0.0.1:8765/mcp` should respond (not connect-refused). If the
error mentions the Ollama endpoint instead, confirm `ollama serve` is up
and that `--host` matches the port it's listening on.

**Tool call succeeds but returns an error dict.** BACpypes3 wraps protocol
errors as `{"error": "...", "errorClass": "...", "errorCode": "..."}`
rather than raising, so the model sees the failure and can adapt. That is
expected behavior — the `read_property` docstring for the target device
may be helpful context, and the model will usually retry with a corrected
`object_identifier` or `property_identifier` on its own.

**Discovering other devices.** `mini-device-with-mcp.py` is a full BACnet
device on the local network. If other BACnet devices are reachable, the
`who_is` tool will find them — the LLM can then read their properties too,
using the returned `pduSource` addresses.

**Exposing beyond localhost.** The `mcp.serve_http(host="127.0.0.1", ...)`
default is loopback for a reason: FastMCP has no built-in authentication.
If you need remote access, put an authenticating reverse proxy in front,
or run the Ollama host on the same machine as the BACnet application and
tunnel over SSH.

---

## Related

- [`mini-device-with-mcp.py`](mini-device-with-mcp.py) — the BACpypes3
  server used above (BACnet server + embedded MCP server, one process).
- [`mini-device-mcp.sh`](mini-device-mcp.sh) — minimal `curl`-based client
  that exercises the MCP wire protocol by hand; useful for debugging when
  the LLM path isn't working as expected.
- `bacpypes3/mcp.py` — the module and its full tool list.
