"""
Client/Server Design Pattern
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union, TypeVar, Generic

T = TypeVar("T")

# maps of named clients and servers
client_map: Dict[str, Client[Any]] = {}
server_map: Dict[str, Server[Any]] = {}
element_map: Dict[str, ApplicationServiceElement] = {}
service_map: Dict[str, ServiceAccessPoint] = {}


class ConfigurationError(ValueError):
    """
    This error is raised when there is a configuration problem such as
    bindings between layers or required parameters that are missing.
    """

    def __init__(self, *args: str) -> None:
        self.args = args


class Client(Generic[T]):
    """
    A client is a communications object that makes requests by sending
    packets "downstream" to a server and responds to confirmation messages
    coming "upstream".
    """

    clientID: Optional[str]
    clientPeer: Optional[Server[T]]

    def __init__(self, cid: Optional[str] = None) -> None:
        global client_map, server_map

        self.clientID = cid
        self.clientPeer = None
        if cid is not None:
            if cid in client_map:
                raise ConfigurationError("already a client {!r}".format(cid))
            client_map[cid] = self

            # automatically bind
            if cid in server_map:
                server = server_map[cid]
                if server.serverPeer:
                    raise ConfigurationError("server {!r} already bound".format(cid))

                bind(self, server)

    async def request(self, pdu: T) -> None:
        if not self.clientPeer:
            raise ConfigurationError("unbound client")
        await self.clientPeer.indication(pdu)

    async def confirmation(self, pdu: T) -> None:
        raise NotImplementedError("confirmation must be overridden")


class Server(Generic[T]):
    """
    A server is a communications object that receives requests "downstream"
    via the indication() function) and sends responses back "upstream".
    """

    serverID: Optional[str]
    serverPeer: Optional["Client[T]"]

    def __init__(self, sid: Optional[str] = None) -> None:
        global client_map, server_map

        self.serverID = sid
        self.serverPeer = None
        if sid is not None:
            if sid in server_map:
                raise RuntimeError("already a server {!r}".format(sid))
            server_map[sid] = self

            # automatically bind
            if sid in client_map:
                client = client_map[sid]
                if client.clientPeer:
                    raise ConfigurationError("client {!r} already bound".format(sid))

                bind(client, self)

    async def indication(self, pdu: T) -> None:
        raise NotImplementedError("indication must be overridden")

    async def response(self, pdu: T) -> None:
        if not self.serverPeer:
            raise ConfigurationError("unbound server")
        await self.serverPeer.confirmation(pdu)


class ApplicationServiceElement:
    """
    An Application Service Element (ASE) is client is a communications object
    that makes requests to a Service Access Point by sending
    packets "downstream" (by calling request) and responds to confirmation
    messages coming "upstream".
    """

    elementID: Optional[str]
    elementService: Optional[ServiceAccessPoint]

    def __init__(self, *args, aseID: Optional[str] = None, **kwargs) -> None:
        global element_map, service_map

        self.elementID = aseID
        self.elementService = None
        if aseID is not None:
            if aseID in element_map:
                raise ConfigurationError("already an element {!r}".format(aseID))
            element_map[aseID] = self

            # automatically bind
            if aseID in service_map:
                service = service_map[aseID]
                if service.serviceElement:
                    raise ConfigurationError(
                        "service access point {!r} already bound".format(aseID)
                    )

                bind(self, service)

    async def request(self, *args: Any) -> None:
        if not self.elementService:
            raise ConfigurationError("unbound element")
        await self.elementService.sap_indication(*args)

    async def indication(self, *args: Any) -> None:
        raise NotImplementedError("indication must be overridden")

    async def response(self, *args: Any) -> None:
        if not self.elementService:
            raise ConfigurationError("unbound element")
        await self.elementService.sap_confirmation(*args)

    async def confirmation(self, *args: Any) -> None:
        raise NotImplementedError("confirmation must be overridden")


class ServiceAccessPoint:
    """
    A server is a communications object that receives requests "downstream"
    via the indication() function and sends responses back "upstream".
    """

    serviceID: Optional[str]
    serviceElement: Optional[ApplicationServiceElement]

    def __init__(self, sapID: Optional[str] = None) -> None:
        global element_map, service_map

        self.serviceID = sapID
        self.serviceElement = None
        if sapID is not None:
            if sapID in service_map:
                raise RuntimeError("already a service {!r}".format(sapID))
            service_map[sapID] = self

            # automatically bind
            if sapID in element_map:
                element = element_map[sapID]
                if element.elementService:
                    raise ConfigurationError("element {!r} already bound".format(sapID))

                bind(element, self)

    async def sap_request(self, *args: Any) -> None:
        if not self.serviceElement:
            raise ConfigurationError("unbound service access point")
        await self.serviceElement.indication(*args)

    async def sap_indication(self, *args: Any) -> None:
        raise NotImplementedError("sap_indication must be overridden")

    async def sap_response(self, *args: Any) -> None:
        if not self.serviceElement:
            raise ConfigurationError("unbound service access point")
        await self.serviceElement.confirmation(*args)

    async def sap_confirmation(self, *args: Any) -> None:
        raise NotImplementedError("sap_confirmation must be overridden")


def bind(
    *args: Union[Client[T], Server[T], ApplicationServiceElement, ServiceAccessPoint]
) -> None:
    """
    Bind a list of clients and servers together, top down.
    """
    global client_map, server_map

    # generic bind is pairs of names
    if not args:
        # find unbound clients and bind them
        for cid, client in client_map.items():
            # skip those that are already bound
            if client.clientPeer:
                continue

            if cid not in server_map:
                raise RuntimeError("unmatched server {!r}".format(cid))
            server = server_map[cid]

            if server.serverPeer:
                raise RuntimeError("server already bound {!r}".format(cid))

            bind(client, server)

        # see if there are any unbound servers
        for sid, server in server_map.items():
            if server.serverPeer:
                continue

            if sid not in client_map:
                raise RuntimeError("unmatched client {!r}".format(sid))
            else:
                raise RuntimeError("unbound server {!r}".format(sid))

    # go through the argument pairs
    for a, b in zip(args[:-1], args[1:]):  # type: ignore
        # make sure we're binding clients and servers
        if isinstance(a, Client) and isinstance(b, Server):
            a.clientPeer = b
            b.serverPeer = a

        elif isinstance(a, ApplicationServiceElement) and isinstance(
            b, ServiceAccessPoint
        ):
            a.elementService = b
            b.serviceElement = a

        else:
            raise TypeError(f"bind: {a} {b}")
