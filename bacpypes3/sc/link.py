#!/usr/bin/python

"""
BACnet/SC Node Link Layer

Composes the BACnet/SC node stack: the BVLL entity (service access point)
stacked on a BVLLCodec and a hub connector.  This is the SC analogue of the
IPv4 NormalLinkLayer and is the object the NetworkServiceAccessPoint binds to.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from ..debugging import bacpypes_debugging, ModuleLogger

from ..comm import bind
from ..pdu import SecureConnectAddress

from .bvll import BVLLCodec
from .service import SCBVLLServiceAccessPoint, SCHubConnector

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class SCNodeLinkLayer(SCBVLLServiceAccessPoint):
    """
    Create a BACnet/SC node link layer mini-stack: the SC BVLL entity (parent
    class) down through the codec to the hub connector that maintains the
    (TLS-secured) WebSocket connection to the hub function.

    The client of an instance of this object (next up the stack) is a
    NetworkAdapter instance which references a NetworkServiceAccessPoint.
    """

    _debug: Any

    codec: BVLLCodec
    connector: SCHubConnector

    def __init__(
        self,
        vmac: SecureConnectAddress,
        device_uuid: uuid.UUID,
        primary_hub_uri: str,
        failover_hub_uri: Optional[str] = None,
        *,
        ssl_context: Any = None,
        **kwargs: Any,
    ) -> None:
        if _debug:
            SCNodeLinkLayer._debug(
                "__init__ %r %r %r %r",
                vmac,
                device_uuid,
                primary_hub_uri,
                failover_hub_uri,
            )
        SCBVLLServiceAccessPoint.__init__(self, vmac)

        # create the codec and hub connector
        self.codec = BVLLCodec()
        self.connector = SCHubConnector(
            vmac,
            device_uuid,
            primary_hub_uri,
            failover_hub_uri,
            ssl_context=ssl_context,
            on_vmac_change=self._vmac_changed,
            **kwargs,
        )

        # stack the entity on the codec on the connector
        bind(self, self.codec, self.connector)  # type: ignore[arg-type]

    def _vmac_changed(self, vmac: SecureConnectAddress) -> None:
        """The connector regenerated the VMAC after a collision; keep the BVLL
        entity's address in sync."""
        if _debug:
            SCNodeLinkLayer._debug("_vmac_changed %r", vmac)
        self.local_vmac = vmac

    def start(self) -> None:
        """Start maintaining the hub connection."""
        if _debug:
            SCNodeLinkLayer._debug("start")
        self.connector.start()

    async def close(self) -> None:
        if _debug:
            SCNodeLinkLayer._debug("close")
        await self.connector.close()
