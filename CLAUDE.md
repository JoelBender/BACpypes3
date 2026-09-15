# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

BACpypes3 is a BACnet application and network layer library for Python 3.8+, rewritten from `bacpypes` (Python 2.5+) around `asyncio` and `async`/`await`. Package name: `bacpypes3`. Version is single-sourced in `bacpypes3/__init__.py` (`__version__`) and picked up by hatch via `pyproject.toml`.

## Commands

Install for development (choose one — the repo carries a `Pipfile`, `pyproject.toml` with a `dev` dependency group, and a `uv.lock`):

```bash
pip install -e ".[websockets,ifaddr,yaml,rdflib]"   # editable install with optional extras
uv sync                                              # or with uv: installs dev group per uv.lock
```

Run tests (config in `pytest.ini` sets `asyncio_mode = auto`, so async tests need no decorator):

```bash
pytest                                       # full suite
pytest tests/test_pdu                        # a subpackage
pytest tests/test_pdu/test_address.py        # a file
pytest tests/test_pdu/test_address.py::TestLocalStation::test_local_station   # a single test
pytest -k who_is                             # by keyword
```

Lint / format (declared in the dev group):

```bash
ruff check bacpypes3 tests
ruff format bacpypes3 tests
```

Run the built-in interactive shell (Read/Write/Who-Is/RPM/BBMD ops against a real network):

```bash
python -m bacpypes3 --help
python -m bacpypes3 --address 192.168.1.10/24 --instance 999
python -m bacpypes3 -v                       # version + which optional deps are loaded
```

Build a release (`bdist.sh`, `release_to_pypi.sh`, `release_to_testpypi.sh` are the scripts the author uses).

## Architecture

BACpypes3 is layered as a **stack of `asyncio`-based communication objects wired together with `bind()`**. Understanding the wiring model is the prerequisite for everything else.

### `bacpypes3/comm.py` — the client/server pattern

Every layer is one or more of:

- `Client[T]` — sends downstream via `request()`, receives upstream via `confirmation()`.
- `Server[T]` — receives downstream via `indication()`, sends upstream via `response()`.
- `ServiceAccessPoint` / `ApplicationServiceElement` — the "SAP/ASE" pair used to expose a service across a peer boundary (e.g. BVLL, application service).

`bind(*objs)` stitches adjacent objects together (`clientPeer` / `serverPeer`, and SAP↔ASE via `serviceElement` / `elementService`). Objects can register with string IDs (`cid` / `sid`) so `bind` can find them later. `ConfigurationError` is raised for double-binds or unbound requests. **When adding a new protocol layer, subclass `Client` and/or `Server`, override `indication`/`confirmation`, and `bind` it into the stack — do not call the peer directly.**

### Layer map (bottom → top)

- **Link layer:** `bacpypes3/ipv4/`, `bacpypes3/ipv6/`, `bacpypes3/vlan/`, `bacpypes3/sc/` (BACnet/SC over websockets, only imported if `websockets` is installed). `ipv4/link.py` provides `NormalLinkLayer`, `ForeignLinkLayer`, `BBMDLinkLayer`; `ipv4/bvll.py` defines the BVLL PDUs; `ipv4/service.py` has `BVLLServiceAccessPoint` and `BVLLServiceElement`.
- **Network layer:** `npdu.py` (NPDUs) and `netservice.py` (`NetworkServiceAccessPoint`, `NetworkAdapter`, routing). `app.py` owns an `nsap` and one `NetworkAdapter` per bound link layer.
- **Application layer:** `apdu.py` (APDUs, confirmed/unconfirmed service tables), `appservice.py` (`ApplicationServiceAccessPoint` — segmentation, transactions, timers), and `app.py` (`Application` — the top-level object; `Application.from_args(args)` is the standard entry point and builds the whole stack from parsed CLI/settings).
- **Object system:** `primitivedata.py` → `constructeddata.py` → `basetypes.py` → `object.py` form the BACnet type system (atomic types, sequences/arrays/choices, standard base types, then `Object` and standard object types). `vendor.py` handles vendor extensions and per-vendor object/property identifier parsing (used pervasively by `app.parse_object_property_reference` / `parse_property_reference`).
- **Local objects:** `bacpypes3/local/` — concrete implementations you register with an `Application` to *be* a BACnet device (`analog.py`, `binary.py`, `multistate.py`, `schedule.py`, `networkport.py`, `device.py`, `cov.py`, `event.py`, `fault.py`, `oos.py`).
- **Application services:** `bacpypes3/service/` — reusable service mixins (`cov.py`, `device.py`, `object.py`) that plug into `Application`.

### Cross-cutting modules

- `settings.py` — global `settings` dict merged from defaults, env, INI/JSON/YAML config, and CLI flags. `argparse.SimpleArgumentParser` (in `bacpypes3/argparse.py`) is the standard CLI entry: it wires logging, reads `BACpypes.{ini,json,yml}`, and pre-populates the args `Application.from_args` consumes.
- `debugging.py` — `ModuleLogger`, `bacpypes_debugging`, `DebugContents`. The idiom seen throughout the codebase:
  ```python
  _debug = 0
  _log = ModuleLogger(globals())

  @bacpypes_debugging
  class Foo:
      _debug: Callable[..., None]
      def bar(self):
          if _debug: Foo._debug("bar %r", ...)
  ```
  `_debug = 0` is a module-level toggle; `--debug bacpypes3.<module>` on the CLI flips it and routes `_log`/`Foo._debug` output. Follow this pattern in new modules rather than raw `logging.getLogger`.
- `console.py` + `cmd.py` — line-oriented async shell used by `__main__.py` and many `samples/`.
- `json/` and `rdf/` — bidirectional serialization of BACnet objects (`sequence_to_json`, `json_to_sequence`; `sequence_to_graph` for RDF). Used by `Application.from_args` to hydrate objects from config.
- `mcp.py` — Model Context Protocol integration (optional `mcp` extra). Exposes each `__main__` CLI command as an async function returning JSON-serializable data; can also run as a stand-alone MCP server (stdio) or be embedded in a long-running application via `mcp.serve_http(...)` as a concurrent asyncio task. Reference embedding pattern: `samples/mini-device-with-mcp.py`.
- `analysis.py` — pcap decoding helpers (`pylibpcap` extra).

### Tests

Layout mirrors the package (`tests/test_pdu`, `tests/test_app`, `tests/test_vlan`, …). `tests/conftest.py` calls `setup_package`/`teardown_package` from `tests/utilities.py`. `tests/state_machine.py` + `tests/clocked_test.py` provide a deterministic virtual clock and state-machine harness — use these instead of real time / real network when adding tests for stack behavior. `test__template.py` is a scaffold to copy from.

### Samples

`samples/` is a large, load-bearing part of the documentation — real programs demonstrating a specific stack shape (foreign device, BBMD, VLAN, multiple stacks, COV client/server, RDF/CSV discovery, `Application.from_args` variations, etc.). When implementing something non-obvious, check whether a `samples/*.py` file already demonstrates it before designing from scratch.

### Optional dependencies

Several modules only import when their extra is present (`websockets` → `bacpypes3.sc`, `rdflib` → `bacpypes3.rdf`, `ifaddr`, `PyYAML`, `python-libpcap`). Match this pattern for new optional integrations: import inside a `try/except ImportError` in `bacpypes3/__init__.py` and gate the feature behind the same guard elsewhere.
