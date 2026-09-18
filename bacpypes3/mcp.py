"""
MCP (Model Context Protocol) server exposing the BACpypes3 command-line
operations as tools.

This module has three personalities:

1. **Importable library.** Each CLI command in ``bacpypes3.__main__`` has a
   plain ``async`` counterpart here that returns JSON-serializable Python
   values (dicts, lists, primitives). Callers can inject an already-built
   :class:`Application` via :func:`set_application` and then call
   :func:`who_is`, :func:`read_property`, and friends directly::

       from bacpypes3.app import Application
       from bacpypes3 import mcp

       mcp.set_application(app)
       result = await mcp.read_property("10.0.0.5", "analog-input,1", "present-value")

2. **Runnable stand-alone MCP server.** ``python -m bacpypes3.mcp
   <BACpypes flags>`` builds an :class:`Application` from
   :class:`SimpleArgumentParser` and serves the same tools over stdio
   using FastMCP.

3. **Embedded in a larger application.** A user application that already
   builds its own :class:`Application` (for example a BACnet server with
   local objects — see ``samples/mini-device-revisited.py``) can add MCP
   at runtime by injecting its app and starting a transport as a
   concurrent task. The HTTP transport is preferred here because stdio
   would clash with the host application's own stdout::

       from bacpypes3 import mcp

       # after building self.app and adding objects
       mcp.set_application(self.app)
       asyncio.create_task(mcp.serve_http(host="127.0.0.1", port=8765))

   Advanced callers who already have their own FastMCP instance can call
   :func:`register_tools(server)` to add the BACpypes3 tools to it.

The ``mcp`` and ``pydantic`` packages are optional; they are only
imported when a server is actually built. The tool functions themselves
can be called without either installed.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from .apdu import ErrorRejectAbortNack
from .app import Application
from .argparse import SimpleArgumentParser
from .basetypes import ErrorType
from .comm import bind
from .constructeddata import AnyAtomic, Array, Sequence
from .constructeddata import List as BACnetList
from .debugging import ModuleLogger, bacpypes_debugging
from .ipv4.bvll import Result as IPv4BVLLResult
from .ipv4.service import BVLLServiceAccessPoint, BVLLServiceElement
from .json.util import atomic_encode, extendedlist_to_json_list, sequence_to_json
from .pdu import Address, IPv4Address
from .primitivedata import Atomic, CharacterString, Null, ObjectIdentifier
from .settings import settings

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# module-level state
_application: Optional[Application] = None
_bvll_ase: Optional[BVLLServiceElement] = None


def set_application(app: Application) -> None:
    """
    Inject the Application instance the tool functions will drive.
    """
    global _application, _bvll_ase
    _application = app
    _bvll_ase = None  # invalidate any cached BVLL element


def get_application() -> Application:
    """
    Return the Application previously injected via :func:`set_application`.
    Raises RuntimeError if none has been set.
    """
    if _application is None:
        raise RuntimeError(
            "no Application: call bacpypes3.mcp.set_application(app) first"
        )
    return _application


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _address(arg: Optional[str]) -> Optional[Address]:
    """Coerce an optional string to an Address (None passes through)."""
    if arg is None:
        return None
    return Address(arg)


def _encode_property_value(value: Any) -> Any:
    """
    Turn a decoded BACnet property value into JSON-serializable Python.

    Mirrors ``samples/rpc-server.py``: unwrap ``AnyAtomic``, then dispatch
    on ``Atomic`` / ``Sequence`` / (``Array``, ``List``). Errors are wrapped
    as ``{"error": ...}`` dicts.
    """
    if isinstance(value, ErrorRejectAbortNack):
        return _encode_error(value)
    if isinstance(value, ErrorType):
        return {
            "error": str(value),
            "errorClass": str(value.errorClass),
            "errorCode": str(value.errorCode),
        }
    if isinstance(value, AnyAtomic):
        value = value.get_value()
    if isinstance(value, Atomic):
        return atomic_encode(value)
    if isinstance(value, Sequence):
        return sequence_to_json(value)
    if isinstance(value, (Array, BACnetList)):
        return extendedlist_to_json_list(value)
    # sentinel strings from read_property (e.g. "-no object class-"), plain
    # ints/floats/None, or anything else — return as-is if json-safe.
    return value


def _encode_error(err: Exception) -> Dict[str, Any]:
    """Encode an ErrorRejectAbortNack (or other exception) as a dict."""
    out: Dict[str, Any] = {"error": str(err), "type": type(err).__name__}
    for attr in ("errorClass", "errorCode", "reason", "abortReason", "rejectReason"):
        val = getattr(err, attr, None)
        if val is not None:
            out[attr] = str(val)
    return out


def _get_bvll_service_element() -> BVLLServiceElement:
    """
    Locate (or lazily create and bind) the BVLL service element for the
    application's local IPv4 adapter. Raises RuntimeError if the local
    adapter is not IPv4.
    """
    global _bvll_ase

    if _bvll_ase is not None:
        return _bvll_ase

    app = get_application()
    local_adapter = app.nsap.local_adapter
    if local_adapter is None:
        raise RuntimeError("no local adapter")
    bvll_sap = local_adapter.clientPeer
    if not isinstance(bvll_sap, BVLLServiceAccessPoint):
        raise RuntimeError("IPv4 only")

    # reuse an already-bound service element if present
    existing = getattr(bvll_sap, "serviceElement", None)
    if isinstance(existing, BVLLServiceElement):
        _bvll_ase = existing
        return _bvll_ase

    ase = BVLLServiceElement()
    bind(ase, bvll_sap)
    _bvll_ase = ase
    return _bvll_ase


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


@bacpypes_debugging
async def who_is(
    low_limit: Optional[int] = None,
    high_limit: Optional[int] = None,
    address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Discover BACnet devices on the network by broadcasting a Who-Is service
    request and collecting the I-Am responses that come back within the
    default timeout (~3 seconds).

    This is the primary way to find out what devices exist, learn their
    device instance numbers, and discover their network addresses before
    issuing directed reads or writes.

    Parameters
    ----------
    low_limit, high_limit : int, optional
        Restrict responses to devices whose instance number falls in
        ``[low_limit, high_limit]`` (inclusive). Instance numbers are
        0..4194302. As a convenience, if ``low_limit`` is given but
        ``high_limit`` is omitted, ``high_limit`` defaults to
        ``low_limit`` — so passing ``low_limit=1234`` alone targets the
        single device with instance 1234.
    address : str, optional
        Destination address. Omit (or ``None``) to broadcast on the local
        network — the usual case. If a device instance range is given
        (``low_limit``/``high_limit``) and ``address`` is omitted, this
        tool defaults to the BACnet global broadcast ``"*:*"`` so the
        search reaches devices behind BACnet routers on other networks;
        pass ``address`` explicitly to override. Examples:
        ``"192.168.1.10"`` (single unicast host),
        ``"192.168.1.255"`` (local broadcast),
        ``"2:5"`` (remote network 2, station 5),
        ``"3:*"`` (remote-network broadcast to network 3),
        ``"*:*"`` (BACnet global broadcast — forwarded by BACnet routers
        to every reachable network; use when devices may live behind
        routers and you don't know which network they're on).

    Returns
    -------
    list of dict
        One dict per responding device. Fields:
        ``iAmDeviceIdentifier`` (str, e.g. ``"device,1234"``),
        ``maxAPDULengthAccepted`` (int),
        ``segmentationSupported`` (str: ``"segmented-both"``, ``"no-segmentation"``, etc.),
        ``vendorID`` (int),
        ``pduSource`` (str: the responder's address — pass this to
        :func:`read_property` / :func:`write_property`).
        Empty list if no devices responded.
    """
    if _debug:
        who_is._debug("who_is %r %r %r", low_limit, high_limit, address)
    app = get_application()

    # Novice-friendly defaults: a lone low_limit targets a single device,
    # and a bounded instance range with no address falls back to global
    # broadcast so devices behind BACnet routers are reachable.
    if low_limit is not None and high_limit is None:
        high_limit = low_limit
    if address is None and (low_limit is not None or high_limit is not None):
        address = "*:*"

    i_ams = await app.who_is(low_limit, high_limit, _address(address))
    return [_i_am_to_json(i_am) for i_am in i_ams]


def _i_am_to_json(i_am: Any) -> Dict[str, Any]:
    result = sequence_to_json(i_am)
    # sequence_to_json only covers the APDU body; add the source address so
    # callers can identify who responded.
    result["pduSource"] = str(i_am.pduSource)
    return result


@bacpypes_debugging
async def i_am(address: Optional[str] = None) -> Dict[str, Any]:
    """
    Announce this application's own device identity on the network by
    sending an unconfirmed I-Am service request. Fire-and-forget: no
    response is expected or awaited.

    Typical use is to advertise presence after startup, or to reply to a
    directed Who-Is. Most callers will not need this — the underlying
    :class:`Application` sends I-Ams automatically in response to Who-Is.

    Parameters
    ----------
    address : str, optional
        Destination for the I-Am. Omit for a local broadcast (the standard
        behavior). See :func:`who_is` for address string formats.

    Returns
    -------
    dict
        ``{"ok": true}`` once the request has been queued for transmission.
    """
    if _debug:
        i_am._debug("i_am %r", address)
    app = get_application()
    app.i_am(_address(address))
    return {"ok": True}


@bacpypes_debugging
async def who_has(
    object_identifier: Optional[str] = None,
    object_name: Optional[str] = None,
    low_limit: Optional[int] = None,
    high_limit: Optional[int] = None,
    address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Locate which device(s) own a specific BACnet object by broadcasting a
    Who-Has service request and collecting the I-Have responses.

    Use this when you know an object's identifier or name and need to find
    the device that hosts it — for example, finding which device owns
    ``analog-input,1`` without knowing its device instance in advance.

    Either ``object_identifier`` or ``object_name`` must be provided
    (both are permitted; devices matching either respond).

    Parameters
    ----------
    object_identifier : str, optional
        Object identifier as ``"<type>,<instance>"``, e.g.
        ``"analog-input,1"``, ``"binary-value,7"``, ``"device,1234"``. The
        type is the ASN.1 kebab-case name.
    object_name : str, optional
        Exact object name (case-sensitive) to look up, e.g.
        ``"Room 101 Temperature"``.
    low_limit, high_limit : int, optional
        Restrict responses to devices in this instance range, same as
        :func:`who_is`.
    address : str, optional
        Destination address. Omit for a local broadcast.

    Returns
    -------
    list of dict
        One entry per responding device holding a matching object. Fields:
        ``deviceIdentifier`` (str), ``objectIdentifier`` (str),
        ``objectName`` (str), and ``pduSource`` (str: the responder's
        address, suitable for follow-up reads/writes). Empty list if
        nothing matched.
    """
    if _debug:
        who_has._debug(
            "who_has %r %r %r %r %r",
            object_identifier,
            object_name,
            low_limit,
            high_limit,
            address,
        )
    app = get_application()
    if object_identifier is None and object_name is None:
        raise ValueError("object_identifier or object_name required")

    oid = ObjectIdentifier(object_identifier) if object_identifier else None
    oname = CharacterString(object_name) if object_name else None

    i_haves = await app.who_has(low_limit, high_limit, oid, oname, _address(address))
    result = []
    for ih in i_haves:
        entry = sequence_to_json(ih)
        entry["pduSource"] = str(ih.pduSource)
        result.append(entry)
    return result


@bacpypes_debugging
async def i_have(
    object_identifier: str,
    object_name: str,
    address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Advertise that this application hosts a specific object by sending an
    unconfirmed I-Have service request. Fire-and-forget: no response is
    awaited.

    Typically used to reply to a Who-Has, or to announce a new object at
    startup. Most callers will not need this directly.

    Parameters
    ----------
    object_identifier : str
        The object being advertised, as ``"<type>,<instance>"``
        (e.g. ``"analog-input,1"``).
    object_name : str
        The object's name.
    address : str, optional
        Destination for the I-Have. Omit for a local broadcast.

    Returns
    -------
    dict
        ``{"ok": true}`` once the request has been queued for transmission.
    """
    if _debug:
        i_have._debug("i_have %r %r %r", object_identifier, object_name, address)
    app = get_application()
    app.i_have(
        ObjectIdentifier(object_identifier),
        CharacterString(object_name),
        _address(address),
    )
    return {"ok": True}


@bacpypes_debugging
async def read_property(
    address: str,
    object_identifier: str,
    property_identifier: str,
) -> Dict[str, Any]:
    """
    Read one property from one object on a remote BACnet device using the
    confirmed ReadProperty service.

    Most common uses: read the current sensor value (``present-value``),
    the object's name (``object-name``), its units (``units``), its
    description, an alarm state, etc.

    Parameters
    ----------
    address : str
        The device's network address. Usually the ``pduSource`` returned
        from :func:`who_is`. Examples: ``"192.168.1.10"``,
        ``"192.168.1.10:47808"``, ``"2:5"`` (remote network 2, station 5).
    object_identifier : str
        The object to read from, as ``"<type>,<instance>"``. Examples:
        ``"analog-input,1"``, ``"binary-value,7"``, ``"device,1234"``,
        ``"multi-state-input,3"``, ``"schedule,1"``. The type is the
        BACnet ASN.1 name in kebab-case.
    property_identifier : str
        Property name in kebab-case. Common values: ``"present-value"``,
        ``"object-name"``, ``"description"``, ``"units"``, ``"status-flags"``,
        ``"object-list"``, ``"priority-array"``. May include an array
        index for array/list-valued properties:
        ``"priority-array[8]"`` reads element 8; ``"object-list[0]"``
        reads the array length.

    Returns
    -------
    dict
        On success:
        ``{"objectIdentifier": str, "propertyIdentifier": str,
        "propertyArrayIndex": int|null, "value": <encoded>}``.
        ``value`` is a JSON-serializable form of the decoded property:
        a scalar for atomic types (number, string, bool),
        a dict for a Sequence,
        a list for an Array/List,
        or a per-element dict/list recursively.
        On protocol error (device rejected, aborted, or timed out) the
        dict instead has ``error``, ``errorClass``, ``errorCode`` (all
        strings) alongside the identifier fields.
    """
    if _debug:
        read_property._debug(
            "read_property %r %r %r", address, object_identifier, property_identifier
        )
    app = get_application()
    addr = Address(address)

    opr = await app.parse_object_property_reference(
        object_identifier,
        property_identifier,
        device_address=addr,
    )

    try:
        value = await app.read_property(
            addr,
            opr.objectIdentifier,
            opr.propertyIdentifier,
            opr.propertyArrayIndex,
        )
    except ErrorRejectAbortNack as err:
        return {
            "objectIdentifier": str(opr.objectIdentifier),
            "propertyIdentifier": str(opr.propertyIdentifier),
            "propertyArrayIndex": opr.propertyArrayIndex,
            **_encode_error(err),
        }

    return {
        "objectIdentifier": str(opr.objectIdentifier),
        "propertyIdentifier": str(opr.propertyIdentifier),
        "propertyArrayIndex": opr.propertyArrayIndex,
        "value": _encode_property_value(value),
    }


@bacpypes_debugging
async def write_property(
    address: str,
    object_identifier: str,
    property_identifier: str,
    value: Any,
    priority: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Write one property on one object on a remote BACnet device using the
    confirmed WriteProperty service.

    Typical uses: set a commandable output (``present-value`` on an
    ``analog-output`` / ``binary-output`` / ``multi-state-output``,
    almost always at a specific ``priority``), rename an object, change
    a setpoint, clear an override.

    Parameters
    ----------
    address : str
        Device network address (see :func:`read_property` for the format).
    object_identifier : str
        Object identifier as ``"<type>,<instance>"`` (e.g.
        ``"analog-output,1"``).
    property_identifier : str
        Property name, kebab-case, optionally with array index (e.g.
        ``"present-value"``, ``"priority-array[8]"``).
    value : any
        The new value, in native JSON form. Pass a number for numeric
        types, a string for character strings and enumerated values
        (use the ASN.1 kebab-case name for enums, e.g. ``"active"`` for a
        BinaryPV), a list for array/list properties, or a dict for
        structured (Sequence) properties. To **release** a priority-array
        override, pass the special string ``"null"`` and specify a
        ``priority`` — this writes a BACnet Null at that priority level.
    priority : int, optional
        Priority slot 1..16 for commandable objects (1 is highest).
        Required when ``value == "null"``. Omit for non-commandable
        properties; some servers require a priority for commandable
        writes and will error otherwise.

    Returns
    -------
    dict
        ``{"ok": true}`` on success. On protocol error, a dict with
        ``error``, ``errorClass``, ``errorCode`` describing the failure.
    """
    if _debug:
        write_property._debug(
            "write_property %r %r %r %r %r",
            address,
            object_identifier,
            property_identifier,
            value,
            priority,
        )
    app = get_application()
    addr = Address(address)

    vendor_info = await app.get_vendor_info(device_address=addr)
    opr = await app.parse_object_property_reference(
        object_identifier,
        property_identifier,
        vendor_info=vendor_info,
    )

    if isinstance(value, str) and value == "null":
        if priority is None:
            raise ValueError("null only for overrides (priority required)")
        value = Null(())

    try:
        response = await app.write_property(
            addr,
            opr.objectIdentifier,
            opr.propertyIdentifier,
            value,
            opr.propertyArrayIndex,
            priority,
        )
    except ErrorRejectAbortNack as err:
        return _encode_error(err)

    assert response is None
    return {"ok": True}


def _parse_rpm_args(vendor_info: Any, args: List[str]) -> List[Any]:
    """
    Parse the RPM shell-style argument list into the parameter list
    ``app.read_property_multiple`` expects. Extracted from
    ``__main__.CmdShell.do_rpm``.

    Note: this is a synchronous helper that uses ``parse_property_reference``
    via an awaited call from the caller; here we only handle the object
    identifier split. Property references are parsed by the caller so the
    async parse can happen naturally.
    """
    # returns raw split into groups: [ (objid_str, [propref_str, ...]), ... ]
    groups: List[Tuple[str, List[str]]] = []
    args = list(args)
    while args:
        objid = args.pop(0)
        props: List[str] = []
        while args:
            props.append(args.pop(0))
            # crude check to see if the next thing is an object identifier
            if args and ((":" in args[0]) or ("," in args[0])):
                break
        groups.append((objid, props))
    return groups


@bacpypes_debugging
async def read_property_multiple(
    address: str,
    args: List[str],
) -> List[Dict[str, Any]]:
    """
    Read many properties from many objects on one device in a single
    round-trip using the confirmed ReadPropertyMultiple service. Much more
    efficient than calling :func:`read_property` in a loop when polling a
    device.

    Parameters
    ----------
    address : str
        Device network address.
    args : list of str
        A flat token list matching the ``rpm`` CLI grammar: an object
        identifier followed by one or more property references, repeated
        for additional objects. Because an object identifier contains
        ``,`` (or ``:`` for vendor-qualified types), a token is treated
        as a new object identifier when it contains either character.

        Examples:

        - ``["analog-input,1", "present-value"]``
          — one property on one object.
        - ``["analog-input,1", "present-value", "units", "object-name"]``
          — three properties on one object.
        - ``["analog-input,1", "present-value",
          "analog-input,2", "present-value"]``
          — one property on two objects.
        - ``["device,1234", "object-list",
          "analog-input,1", "present-value", "units"]``
          — mixed.

        Property tokens may include array indices
        (``"present-value[3]"``). The pseudo-property ``"all"``,
        ``"required"``, or ``"optional"`` is accepted where the target
        device supports it (returns every matching property).

    Returns
    -------
    list of dict
        One entry per (object, property, array-index) triple in the
        response. Each entry has ``objectIdentifier``,
        ``propertyIdentifier``, ``propertyArrayIndex`` (int or null), and
        either ``value`` (encoded like :func:`read_property`) or
        ``error``/``errorClass``/``errorCode`` for that specific
        property. If the whole request fails, a single-element list with
        an error dict is returned.
    """
    if _debug:
        read_property_multiple._debug("read_property_multiple %r %r", address, args)
    app = get_application()
    addr = Address(address)

    vendor_info = await app.get_vendor_info(device_address=addr)

    parameter_list: List[Any] = []
    for objid_str, prop_strs in _parse_rpm_args(vendor_info, args):
        object_identifier = vendor_info.object_identifier(objid_str)
        parameter_list.append(object_identifier)
        property_reference_list = []
        for prop_str in prop_strs:
            property_reference_list.append(
                await app.parse_property_reference(prop_str, vendor_info=vendor_info)
            )
        parameter_list.append(property_reference_list)

    if not parameter_list:
        raise ValueError("object identifier expected")

    try:
        response = await app.read_property_multiple(addr, parameter_list)
    except ErrorRejectAbortNack as err:
        return [_encode_error(err)]

    results = []
    for object_identifier, property_identifier, array_index, property_value in response:
        entry: Dict[str, Any] = {
            "objectIdentifier": str(object_identifier),
            "propertyIdentifier": str(property_identifier),
            "propertyArrayIndex": array_index,
        }
        if isinstance(property_value, ErrorType):
            entry["error"] = str(property_value)
            entry["errorClass"] = str(property_value.errorClass)
            entry["errorCode"] = str(property_value.errorCode)
        else:
            entry["value"] = _encode_property_value(property_value)
        results.append(entry)
    return results


@bacpypes_debugging
async def who_is_router_to_network(
    address: Optional[str] = None,
    network: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Discover BACnet routers by sending a Who-Is-Router-To-Network NPDU
    and collecting the I-Am-Router-To-Network responses.

    Use this to map the BACnet internetwork: find which routers exist and
    which remote network numbers each of them can reach. Helpful when
    reads/writes to a remote-network address are failing and you need to
    verify a route exists.

    Parameters
    ----------
    address : str, optional
        Destination for the query. Omit for a local broadcast (asks every
        router on the local network). Give a specific address to ask one
        router directly.
    network : int, optional
        Restrict the question to a specific remote network number
        (1..65534). Omit to ask "what networks do you know about?".

    Returns
    -------
    list of dict
        One entry per responding router, grouped by source address.
        Fields: ``source`` (str: the router's address) and ``networks``
        (list of int: the DNETs the router advertises reachability to).
    """
    if _debug:
        who_is_router_to_network._debug(
            "who_is_router_to_network %r %r", address, network
        )
    app = get_application()
    if not app.nse:
        raise RuntimeError("no network service element")

    result_list = await app.nse.who_is_router_to_network(
        destination=_address(address), network=network
    )

    grouped: Dict[str, List[int]] = {}
    order: List[str] = []
    for _adapter, i_am_router in result_list:
        if i_am_router.npduSADR:
            npdu_source = i_am_router.npduSADR
            npdu_source.addrRoute = i_am_router.pduSource
        else:
            npdu_source = i_am_router.pduSource
        key = str(npdu_source)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].extend(int(dnet) for dnet in i_am_router.iartnNetworkList)

    return [{"source": key, "networks": grouped[key]} for key in order]


@bacpypes_debugging
async def initialize_routing_table(
    address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query a router (or all routers) for its full routing table by sending
    an Initialize-Routing-Table NPDU with an empty table body. Returns
    the routing entries the router replies with.

    Despite the "initialize" name, sending an empty table is the standard
    read operation for a router's routing table. Only use it against
    routers — most end devices will not respond.

    Parameters
    ----------
    address : str, optional
        Router to query. Omit for a local broadcast (all routers on the
        local network respond).

    Returns
    -------
    list of dict
        One entry per responding router, grouped by source address:
        ``source`` (str), ``entries`` (list of ``{"dnet": int,
        "portId": int}``, one per routing-table entry the router
        advertises).
    """
    if _debug:
        initialize_routing_table._debug("initialize_routing_table %r", address)
    app = get_application()
    if not app.nse:
        raise RuntimeError("no network service element")

    result_list = await app.nse.initialize_routing_table(destination=_address(address))

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for _adapter, ack in result_list:
        key = str(ack.pduSource)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        for entry in ack.irtaTable:
            grouped[key].append(
                {
                    "dnet": int(entry.rtDNET),
                    "portId": int(entry.rtPortID),
                }
            )
    return [{"source": key, "entries": grouped[key]} for key in order]


def _ipv4(arg: str) -> IPv4Address:
    """Accept a plain IPv4 string or a bacpypes IPv4Address literal."""
    return IPv4Address(arg)


@bacpypes_debugging
async def read_broadcast_distribution_table(address: str) -> List[str]:
    """
    Read the Broadcast Distribution Table from a BACnet/IPv4 BBMD (BACnet
    Broadcast Management Device) using the Read-Broadcast-Distribution-
    Table BVLL request. The BDT lists the peer BBMDs a BBMD will forward
    broadcasts to.

    Use this to audit BBMD configuration across a multi-subnet BACnet/IP
    network — every BBMD's BDT should list every other BBMD.

    Only works when this application's local link layer is IPv4;
    otherwise raises ``RuntimeError("IPv4 only")``.

    Parameters
    ----------
    address : str
        IPv4 address (with optional ``:port``) of the target BBMD, e.g.
        ``"192.168.1.10"`` or ``"192.168.1.10:47808"``.

    Returns
    -------
    list of str
        One string per BDT entry, formatted ``"addr/netmask"`` (e.g.
        ``"192.168.1.10/255.255.255.0"``). Empty list if the BBMD replied
        with no entries. A single-element list starting with
        ``"bvll error: ..."`` on a BVLL-level protocol error.
    """
    if _debug:
        read_broadcast_distribution_table._debug(
            "read_broadcast_distribution_table %r", address
        )
    ase = _get_bvll_service_element()
    try:
        result = await ase.read_broadcast_distribution_table(_ipv4(address))
    except IPv4BVLLResult as err:
        return [f"bvll error: {err.bvlciResultCode}"]
    if result is None:
        return []
    return [f"{entry}/{entry.netmask}" for entry in result]


@bacpypes_debugging
async def write_broadcast_distribution_table(
    address: str,
    entries: List[str],
) -> Dict[str, Any]:
    """
    Replace the Broadcast Distribution Table on a BACnet/IPv4 BBMD via
    the Write-Broadcast-Distribution-Table BVLL request. This overwrites
    the BBMD's entire BDT with the given list — it is not incremental.

    Include an entry for **every** BBMD you want to participate in the
    broadcast domain, including (by convention) the target BBMD itself.
    Missing entries silently drop those peers from broadcast forwarding.

    Only works when the local link layer is IPv4; otherwise raises
    ``RuntimeError("IPv4 only")``.

    Parameters
    ----------
    address : str
        IPv4 address of the BBMD whose BDT is being written.
    entries : list of str
        IPv4 addresses (with optional ``/mask`` or ``:port``) that make
        up the new BDT, e.g.
        ``["192.168.1.10/24", "192.168.2.10/24", "192.168.3.10/24"]``.

    Returns
    -------
    dict
        ``{"ok": true}`` on success, or ``{"error": "bvll error: <code>"}``
        on a BVLL protocol error.
    """
    if _debug:
        write_broadcast_distribution_table._debug(
            "write_broadcast_distribution_table %r %r", address, entries
        )
    ase = _get_bvll_service_element()
    try:
        await ase.write_broadcast_distribution_table(
            _ipv4(address), [_ipv4(e) for e in entries]
        )
    except IPv4BVLLResult as err:
        return {"error": f"bvll error: {err.bvlciResultCode}"}
    return {"ok": True}


@bacpypes_debugging
async def read_foreign_device_table(address: str) -> List[Dict[str, Any]]:
    """
    Read the Foreign Device Table from a BACnet/IPv4 BBMD using the
    Read-Foreign-Device-Table BVLL request. The FDT lists devices that
    have registered as "foreign" — devices on remote IP subnets that
    receive forwarded broadcasts from this BBMD via unicast.

    Use this to see which remote clients are currently registered with a
    BBMD and how long they have left before their registration expires.

    Only works when the local link layer is IPv4; otherwise raises
    ``RuntimeError("IPv4 only")``.

    Parameters
    ----------
    address : str
        IPv4 address of the target BBMD.

    Returns
    -------
    list of dict
        One entry per registered foreign device. Fields:
        ``address`` (str: the foreign device's IPv4 address),
        ``ttl`` (int: seconds the registration was granted for),
        ``remain`` (int: seconds until it expires unless renewed).
        Empty list if no foreign devices are registered. A single-element
        list with an ``error`` field on a BVLL protocol error.
    """
    if _debug:
        read_foreign_device_table._debug("read_foreign_device_table %r", address)
    ase = _get_bvll_service_element()
    try:
        result = await ase.read_foreign_device_table(_ipv4(address))
    except IPv4BVLLResult as err:
        return [{"error": f"bvll error: {err.bvlciResultCode}"}]
    if result is None:
        return []
    return [
        {
            "address": str(entry.fdAddress),
            "ttl": int(entry.fdTTL),
            "remain": int(entry.fdRemain),
        }
        for entry in result
    ]


@bacpypes_debugging
async def get_config() -> Dict[str, Any]:
    """
    Return the configuration of the local BACpypes application itself —
    not a remote device. This describes the identity of the running
    application: its address, device instance, and every local BACnet
    object it hosts (device object, network-port objects, and any
    application-level objects).

    Useful for introspecting the state of the running MCP server and
    understanding what identity it presents on the wire.

    Returns
    -------
    dict
        ``{"BACpypes": {...}, "application": [...]}``.
        - ``BACpypes`` is a dict of runtime settings (address, name,
          instance, vendoridentifier, foreign/bbmd config, etc.).
        - ``application`` is a list of every locally-registered BACnet
          object, each serialized to JSON (object identifier, name, type,
          plus every readable property).
    """
    if _debug:
        get_config._debug("get_config")
    app = get_application()

    object_list = [sequence_to_json(obj) for obj in app.objectIdentifier.values()]
    return {"BACpypes": dict(settings), "application": object_list}


# ---------------------------------------------------------------------------
# MCP server entry point (optional; requires the `mcp` extra)
# ---------------------------------------------------------------------------


TOOLS: Tuple[Callable[..., Any], ...] = (
    who_is,
    i_am,
    who_has,
    i_have,
    read_property,
    write_property,
    read_property_multiple,
    who_is_router_to_network,
    initialize_routing_table,
    read_broadcast_distribution_table,
    write_broadcast_distribution_table,
    read_foreign_device_table,
    get_config,
)


def register_tools(server: Any) -> Any:
    """
    Register every BACpypes3 tool on an existing FastMCP server instance.

    Use this from an embedding application that already owns a FastMCP
    server (perhaps hosting other tools of its own): call
    :func:`register_tools` to add the BACpypes3 tools alongside them.

    Parameters
    ----------
    server : mcp.server.fastmcp.FastMCP
        The FastMCP server to register tools on.

    Returns
    -------
    The same server instance, for chaining.
    """
    for fn in TOOLS:
        server.tool()(fn)
    return server


def build_server(name: str = "bacpypes3", **fastmcp_kwargs: Any) -> Any:
    """
    Build a fresh FastMCP server with every BACpypes3 tool registered.

    Prefer :func:`serve_stdio` or :func:`serve_http` if you just want to
    run a server; use :func:`build_server` only when you need to
    customize the FastMCP instance before serving. Any additional keyword
    arguments are forwarded to ``FastMCP(...)`` — useful for setting
    ``host``, ``port``, ``streamable_http_path``, ``stateless_http``,
    ``log_level``, etc.

    The ``mcp`` package (and ``pydantic``) must be installed — the import
    happens here, not at module import time, so the tool functions remain
    usable without the extra.
    """
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

    server = FastMCP(name, **fastmcp_kwargs)
    return register_tools(server)


async def serve_stdio(app: Optional[Application] = None) -> None:
    """
    Run an MCP server over stdio, blocking until the client disconnects.

    Suitable when this process exists only to be an MCP server (the
    standard case for ``python -m bacpypes3.mcp``). Do **not** use this
    from an embedded application whose own stdout carries other output —
    call :func:`serve_http` instead.

    Parameters
    ----------
    app : Application, optional
        The BACpypes application the tools should drive. If given, it is
        installed via :func:`set_application` before serving. If omitted,
        an Application must already have been injected — otherwise the
        first tool call will raise ``RuntimeError``.
    """
    if app is not None:
        set_application(app)
    server = build_server()
    await server.run_stdio_async()


async def serve_http(
    host: str = "127.0.0.1",
    port: int = 8765,
    app: Optional[Application] = None,
) -> None:
    """
    Run an MCP server over Streamable HTTP, blocking until cancelled.

    This is the transport to use when embedding MCP inside a larger
    BACpypes application: HTTP does not touch stdio and so coexists with
    the host application's logging, prompts, or CLI. Start it as a
    concurrent task::

        mcp.set_application(self.app)
        asyncio.create_task(
            mcp.serve_http(host="127.0.0.1", port=8765)
        )

    A client (e.g. an LLM agent) then connects to
    ``http://127.0.0.1:8765/mcp``.

    Parameters
    ----------
    host : str
        Interface to bind. Defaults to loopback; set to ``"0.0.0.0"`` to
        accept remote connections (only do this behind an auth proxy —
        FastMCP has no built-in authentication).
    port : int
        TCP port to listen on. Default ``8765``.
    app : Application, optional
        The BACpypes application to drive, injected before serving. If
        omitted, an Application must already have been injected via
        :func:`set_application`.
    """
    if app is not None:
        set_application(app)
    server = build_server(host=host, port=port)
    await server.run_streamable_http_async()


async def _serve_cli() -> None:
    """CLI entry point: parse args, build an Application, serve on stdio."""
    parser = SimpleArgumentParser(prog="bacpypes3.mcp")
    args = parser.parse_args()
    if _debug:
        _log.debug("args: %r", args)

    app = Application.from_args(args)
    try:
        await serve_stdio(app=app)
    finally:
        app.close()


def main() -> None:
    try:
        asyncio.run(_serve_cli())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
