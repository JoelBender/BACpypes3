"""
BACnet IPv4 Virtual Link Layer Service
"""

from __future__ import annotations

import asyncio
from asyncio.exceptions import TimeoutError
from typing import Callable, Dict, List, Optional, cast

from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging
from ..comm import Client, Server, ServiceAccessPoint, ApplicationServiceElement
from ..pdu import Address, LocalBroadcast, IPv4Address, PDU

from .bvll import (
    LPDU,
    DeleteForeignDeviceTableEntry,
    DistributeBroadcastToNetwork,
    FDTEntry,
    ForwardedNPDU,
    OriginalBroadcastNPDU,
    OriginalUnicastNPDU,
    ReadBroadcastDistributionTable,
    ReadBroadcastDistributionTableAck,
    ReadForeignDeviceTable,
    ReadForeignDeviceTableAck,
    RegisterForeignDevice,
    Result,
    WriteBroadcastDistributionTable,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
REGISTRATION_TIMEOUT = 2.0
READ_BDT_TIMEOUT = 3.0
READ_FDT_TIMEOUT = 3.0
WRITE_BDT_TIMEOUT = 3.0


#
#   _Multiplex Client and Server
#


class _MultiplexClient(Client[PDU]):
    def __init__(self, mux):
        Client.__init__(self)
        self.multiplexer = mux

    async def confirmation(self, pdu: PDU) -> None:
        await self.multiplexer.confirmation(self, pdu)


class _MultiplexServer(Server[PDU]):
    def __init__(self, mux):
        Server.__init__(self)
        self.multiplexer = mux

    async def indication(self, pdu: PDU) -> None:
        await self.multiplexer.indication(self, pdu)


#
#   UDPMultiplexer
#


@bacpypes_debugging
class UDPMultiplexer(Client[PDU]):
    """
    An instance of this class sits above an IPv4DatagramServer and checks the
    upstream packets for Annex H style BACnet Tunneling Router functionality
    or Annex J BACnet/IPv4 functionality.
    """

    _debug: Callable[..., None]
    _warning: Callable[..., None]

    def __init__(self):
        if _debug:
            UDPMultiplexer._debug("__init__")

        # create and bind the Annex H and J servers
        self.annexH = _MultiplexServer(self)
        self.annexJ = _MultiplexServer(self)

    async def indication(self, server, pdu):
        if _debug:
            UDPMultiplexer._debug("indication %r %r", server, pdu)

        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            UDPMultiplexer._debug("confirmation %r", pdu)

        # must have at least one octet
        if not pdu.pduData:
            if _debug:
                UDPMultiplexer._debug("    - no data")
            return

        # extract the first octet
        msg_type = pdu.pduData[0]

        # check for the message type
        if msg_type == 0x01:
            if self.annexH.serverPeer:
                await self.annexH.response(pdu)
        elif msg_type == 0x81:
            if self.annexJ.serverPeer:
                await self.annexJ.response(pdu)
        else:
            UDPMultiplexer._warning("unsupported message")


#
#   BTR
#


@bacpypes_debugging
class BTR(Client[PDU], Server[PDU], DebugContents):
    """
    BACnet Annex H Tunneling Router
    """

    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = ("peers+",)

    peers: Dict[IPv4Address, List[int]]

    def __init__(self, *, cid=None, sid=None) -> None:
        if _debug:
            BTR._debug("__init__ cid=%r sid=%r", cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

        # initialize a dicitonary of peers
        self.peers = {}

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BTR._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make sure it is going to a peer
            if pdu.pduDestination not in self.peers:
                ###TODO log this
                return

            # send it downstream
            await self.request(pdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # if route_aware and pdu.pduDestination.addrRoute:
            #     xpdu = PDU(pdu.pduData, destination=pdu.pduDestination.addrRoute)
            #     await self.request(xpdu)
            #     return

            # loop through the peers
            for peerAddr in self.peers.keys():
                xpdu = PDU(pdu.pduData, destination=peerAddr)

                # send it downstream
                await self.request(xpdu)

        else:
            raise RuntimeError("invalid destination address type (2)")

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            BTR._debug("confirmation %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        # make sure it came from a peer
        if pdu.pduSource not in self.peers:
            BTR._warning("not a peer: %r", pdu.pduSource)
            return

        # send it upstream
        await self.response(pdu)

    def add_peer(self, peerAddr: IPv4Address, networks: List[int] = []) -> None:
        """Add a peer and optionally provide a list of the reachable networks."""
        if _debug:
            BTR._debug("add_peer %r networks=%r", peerAddr, networks)

        # see if this is already a peer
        if peerAddr in self.peers:
            # add the (new?) reachable networks
            self.peers[peerAddr].extend(networks)
        else:
            # save the networks
            self.peers[peerAddr] = networks

        ###TODO send a control message upstream that these are reachable

    def delete_peer(self, peerAddr: IPv4Address) -> None:
        """Delete a peer."""
        if _debug:
            BTR._debug("delete_peer %r", peerAddr)

        ###TODO send a control message upstream that these are no longer reachable

        # now delete the peer
        del self.peers[peerAddr]


#
#   BVLLServiceAccessPoint
#


@bacpypes_debugging
class BVLLServiceAccessPoint(Client[LPDU], Server[PDU], ServiceAccessPoint):
    """
    BACnet IPv4 Service Access Point

    An instance of this is stacked on a BVLLCodec, as a server it presents
    PDUs.
    """

    _debug: Callable[..., None]

    def __init__(
        self,
        *,
        sapID: Optional[str] = None,
        cid: Optional[str] = None,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            BVLLServiceAccessPoint._debug("__init__")
        Client.__init__(self, cid=cid)
        Server.__init__(self, sid=sid)
        ServiceAccessPoint.__init__(self, sapID=sapID)

    async def sap_indication(self, lpdu: LPDU) -> None:
        if _debug:
            BVLLServiceAccessPoint._debug("sap_indication %r", lpdu)

        # this is a request initiated by the ASE, send this downstream
        await self.request(lpdu)

    async def sap_confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BVLLServiceAccessPoint._debug("sap_confirmation %r", lpdu)

        # this is a response from the ASE, send this downstream
        await self.request(lpdu)


#
#   BIPNormal
#


@bacpypes_debugging
class BIPNormal(BVLLServiceAccessPoint):
    _debug: Callable[..., None]
    _warning: Callable[..., None]

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPNormal._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        lpdu: LPDU

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            lpdu = OriginalUnicastNPDU(
                pdu, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPNormal._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            lpdu = OriginalBroadcastNPDU(
                pdu, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPNormal._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        else:
            BIPNormal._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPNormal._debug("confirmation %r", lpdu)

        # some kind of response to a request
        if isinstance(lpdu, Result):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, OriginalUnicastNPDU):
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.pduSource,
                destination=lpdu.pduDestination,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            # build a PDU with a local broadcast address
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.pduSource,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # build a PDU with the source from the real source
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, WriteBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0010, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0020, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            # build a response
            xpdu = Result(code=0x0030, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTable):
            # build a response
            xpdu = Result(code=0x0040, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # build a response
            xpdu = Result(code=0x0050, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # build a response
            xpdu = Result(code=0x0060, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        else:
            BIPNormal._warning("invalid pdu type: %s", type(pdu))


#
#   BIPForeign
#


@bacpypes_debugging
class BIPForeign(BVLLServiceAccessPoint, DebugContents):
    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = ("bbmdAddress", "bbmdTimeToLive", "bbmdRegistrationStatus")

    bbmdAddress: Optional[IPv4Address]
    bbmdTimeToLive: Optional[int]
    bbmdRegistrationStatus: int

    _registration_event: asyncio.Event
    _registration_handle: Optional[asyncio.Handle]
    _registration_task: Optional[asyncio.Task]
    _registration_timeout_task: Optional[asyncio.Task]
    _reregistration_timeout_handle: Optional[asyncio.TimerHandle]

    def __init__(self, **kwargs) -> None:
        if _debug:
            BIPForeign._debug("__init__")
        BVLLServiceAccessPoint.__init__(self, **kwargs)

        # clear the BBMD address and time-to-live
        self.bbmdAddress = None
        self.bbmdTimeToLive = None

        # -2=unregistered, -1=in process, 0=OK, >0 error
        self.bbmdRegistrationStatus = -2

        # used in tracking the active registration
        self._registration_event = asyncio.Event()
        self._registration_handle = None
        self._registration_timeout_handle = None
        self._reregistration_timeout_handle = None

        # unregistered
        self._registration_event.clear()

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPForeign._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        lpdu: LPDU

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            lpdu = OriginalUnicastNPDU(
                pdu.pduData, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPForeign._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # check the BBMD registration status
            if self.bbmdRegistrationStatus == -2:
                if _debug:
                    BIPForeign._debug("    - packet dropped, unregistered")
                return

            elif self.bbmdRegistrationStatus == -1:
                try:
                    if _debug:
                        BIPForeign._debug("    - wait for registration response")

                    await asyncio.wait_for(
                        self._registration_event.wait(),
                        timeout=REGISTRATION_TIMEOUT,
                    )
                except TimeoutError:
                    if _debug:
                        BIPForeign._debug("    - packet dropped, unregistered")
                    return

            elif self.bbmdRegistrationStatus == 0:
                pass

            else:
                if _debug:
                    BIPForeign._debug(
                        "    - registration error: %r", self.bbmdRegistrationStatus
                    )
                return  ###TODO raise RuntimeError?

            # make a broadcast PDU
            lpdu = DistributeBroadcastToNetwork(
                pdu, destination=self.bbmdAddress, user_data=pdu.pduUserData
            )
            if _debug:
                BIPForeign._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        else:
            BIPForeign._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPForeign._debug("confirmation %r", lpdu)

        xpdu: LPDU

        # check for a registration request result
        if isinstance(lpdu, Result):
            # if we have no registration, do nothing
            if self.bbmdRegistrationStatus == -2:
                return

            if _debug:
                BIPForeign._debug("    - registration: %r", self._registration_handle)
            if not self._registration_handle:
                # we received this ack but we haven't requested one
                return
            self._registration_handle = None

            # make sure the result is from the bbmd
            if lpdu.pduSource != self.bbmdAddress:
                if _debug:
                    BIPForeign._debug("    - packet dropped, not from the BBMD")
                return

            # save the result code as the status
            self.bbmdRegistrationStatus = cast(int, lpdu.bvlciResultCode)

            # if successful, start tracking the registration
            if self.bbmdRegistrationStatus == 0:
                self._registration_event.set()
                self._start_tracking_registration()

        elif isinstance(lpdu, OriginalUnicastNPDU):
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.pduSource,
                destination=lpdu.pduDestination,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # check the BBMD registration status, we may not be registered
            if not self._registration_event.is_set():
                if _debug:
                    BIPForeign._debug("    - packet dropped, unregistered")
                return

            # make sure the forwarded PDU from the bbmd
            if lpdu.pduSource != self.bbmdAddress:
                if _debug:
                    BIPForeign._debug("    - packet dropped, not from the BBMD")
                return

            # build a PDU with the source from the real source
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, WriteBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0010, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0020, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            # build a response
            xpdu = Result(code=0x0030, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTable):
            # build a response
            xpdu = Result(code=0x0040, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # build a response
            xpdu = Result(code=0x0050, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # build a response
            xpdu = Result(code=0x0060, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            if _debug:
                BIPForeign._debug("    - packet dropped")

        else:
            BIPForeign._warning("invalid pdu type: %s", type(lpdu))

    def register(self, addr: IPv4Address, ttl: int) -> None:
        """Start the foreign device registration process with the given BBMD.

        Registration will be renewed periodically according to the ttl value
        until explicitly stopped by a call to `unregister`.
        """
        if _debug:
            BIPForeign._debug("register %r %r", addr, ttl)

        # a little error checking
        if not isinstance(addr, IPv4Address):
            raise TypeError("addr must be an IPv4Address")
        if ttl <= 0:
            raise ValueError("time-to-live must be greater than zero")
        if self._registration_handle:
            if _debug:
                BIPForeign._debug("    - registration already scheduled")
            return

        # save the BBMD address and time-to-live
        self.bbmdAddress = addr
        self.bbmdTimeToLive = ttl

        # start the registration process when you get a chance
        loop = asyncio.get_event_loop()
        self._registration_handle = loop.call_soon(self._start_registration)

    def unregister(self):
        """Stop the foreign device registration process.

        Immediately drops active foreign device registration and stops further
        registration renewals.
        """
        if _debug:
            BIPForeign._debug("unregister")

        # if we are already doing nothing, skip the rest
        if self.bbmdRegistrationStatus == -2:
            if _debug:
                BIPForeign._debug("    - nothing to do")
            return

        # stop tracking the registration
        self._stop_tracking_registration()

        # if the event loop is still running, stop the registration
        if asyncio.get_event_loop().is_running():
            asyncio.ensure_future(self._stop_registration(self.bbmdAddress))

        # change the status to unregistered
        self.bbmdRegistrationStatus = -2
        self._registration_event.clear()

        # clear the BBMD address and time-to-live
        self.bbmdAddress = None
        self.bbmdTimeToLive = None

    def _start_registration(self) -> None:
        """Scheduled when the registration request is being initiated or
        renewed, task saved in self._registration_task."""
        if _debug:
            BIPForeign._debug("_start_registration")
            BIPForeign._debug(
                "    - registration status: %r", self.bbmdRegistrationStatus
            )

        if self.bbmdRegistrationStatus == -2:
            self.bbmdRegistrationStatus = -1  # in process

        # form a registration request
        pdu = RegisterForeignDevice(self.bbmdTimeToLive, destination=self.bbmdAddress)
        if _debug:
            BIPForeign._debug("    - pdu: %r", pdu)

        # send it downstream
        registration_task = asyncio.create_task(self.request(pdu))
        if _debug:
            BIPForeign._debug("    - registration request: %r", registration_task)

        # get the loop to schedule another attempt
        loop = asyncio.get_event_loop()
        if _debug:
            BIPForeign._debug("    - loop time: %r", loop.time())

        # schedule another (faster) registration attempt
        self._reregistration_timeout_handle = loop.call_later(
            min(5, cast(int, self.bbmdTimeToLive)), self._start_registration
        )
        if _debug:
            BIPForeign._debug(
                "    - re-registration timeout: %r", self._reregistration_timeout_handle
            )

    async def _stop_registration(self, bbmdAddress: IPv4Address) -> None:
        """Scheduled when the registration is being canceled."""
        if _debug:
            BIPForeign._debug("_stop_registration")

        pdu = RegisterForeignDevice(0, destination=bbmdAddress)

        # send it downstream
        await self.request(pdu)

    def _start_tracking_registration(self):
        # From J.5.2.3 Foreign Device Table Operation (paraphrasing): if a
        # foreign device does not renew its registration 30 seconds after its
        # TTL expired then it will be removed from the BBMD's FDT.
        #
        # Thus, if we're registered and don't get a response to a subsequent
        # renewal request 30 seconds after our TTL expired then we're
        # definitely not registered anymore.
        # self._registration_timeout_task.install_task(delta=self.bbmdTimeToLive + 30)
        if _debug:
            BIPForeign._debug("_start_tracking_registration")
            BIPForeign._debug(
                "    - _registration_handle: %r", self._registration_handle
            )
            BIPForeign._debug(
                "    - _registration_timeout_handle: %r",
                self._registration_timeout_handle,
            )

        # stop any current tracking
        self._stop_tracking_registration()

        # get the loop for call_later()
        loop = asyncio.get_event_loop()

        # schedule a registration to refresh it
        self._registration_handle = loop.call_later(
            self.bbmdTimeToLive, self._start_registration
        )
        if _debug:
            BIPForeign._debug(
                "    - new _registration_handle: %r", self._registration_handle
            )

        # schedule the registration timeout
        self._registration_timeout_handle = loop.call_later(
            self.bbmdTimeToLive + 30, self._registration_expired
        )
        if _debug:
            BIPForeign._debug(
                "    - new _registration_timeout_handle: %r",
                self._registration_timeout_handle,
            )

    def _stop_tracking_registration(self):
        if _debug:
            BIPForeign._debug("_stop_tracking_registration")

        if self._registration_handle:
            if _debug:
                BIPForeign._debug("        - canceling %r", self._registration_handle)
            self._registration_handle.cancel()
            self._registration_handle = None

        if self._registration_timeout_handle:
            if _debug:
                BIPForeign._debug(
                    "        - canceling %r", self._registration_timeout_handle
                )
            self._registration_timeout_handle.cancel()
            self._registration_timeout_handle = None

        if self._reregistration_timeout_handle:
            if _debug:
                BIPForeign._debug(
                    "        - canceling %r", self._reregistration_timeout_handle
                )
            self._reregistration_timeout_handle.cancel()
            self._reregistration_timeout_handle = None

    def _registration_expired(self):
        """Called when detecting that foreign device registration has
        definitely expired.
        """
        if _debug:
            BIPForeign._debug("_registration_expired")

        self.bbmdRegistrationStatus = -2  # unregistered
        self._registration_event.clear()
        self._stop_tracking_registration()


#
#   BIPBBMD
#


@bacpypes_debugging
class BIPBBMD(BVLLServiceAccessPoint, DebugContents):
    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = ("bbmdAddress", "bbmdBDT+", "bbmdFDT+")

    bbmdAddress: IPv4Address
    bbmdBDT: List[IPv4Address]
    bbmdFDT: List[FDTEntry]

    _fdt_clock_handle: asyncio.Handle

    def __init__(self, addr: IPv4Address, **kwargs):
        if _debug:
            BIPBBMD._debug("__init__ %r", addr)
        BVLLServiceAccessPoint.__init__(self, **kwargs)

        self.bbmdAddress = addr
        self.bbmdBDT = []
        self.bbmdFDT = []

        # schedule the clock to run
        self._fdt_clock_handle = asyncio.get_event_loop().call_soon(self.fdt_clock)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPBBMD._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        lpdu: LPDU

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            lpdu = OriginalUnicastNPDU(
                pdu.pduData, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            lpdu = OriginalBroadcastNPDU(
                pdu.pduData, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

            # make a forwarded PDU
            lpdu = ForwardedNPDU(
                self.bbmdAddress, pdu.pduData, user_data=pdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - forwarded lpdu: %r", lpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    lpdu.pduDestination = IPv4Address(bdte.addrBroadcastTuple)
                    BIPBBMD._debug("    - sending to peer: %r", lpdu.pduDestination)
                    await self.request(lpdu)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                lpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPBBMD._debug(
                        "    - sending to foreign device: %r", lpdu.pduDestination
                    )
                await self.request(lpdu)

        else:
            BIPBBMD._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPBBMD._debug("confirmation %r", lpdu)

        xpdu: LPDU

        # some kind of response to a request
        if isinstance(lpdu, Result):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, WriteBroadcastDistributionTable):
            # build a response
            xpdu = Result(
                code=0x0010, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTable):
            # build a response
            xpdu = ReadBroadcastDistributionTableAck(
                self.bbmdBDT, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # send it upstream if there is a network layer
            if self.serverPeer:
                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.bvlciAddress,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - upstream pdu: %r", pdu)

                await self.response(pdu)

            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(
                lpdu.bvlciAddress,
                lpdu.pduData,
                destination=None,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # if this was unicast to us, do next hop
            assert isinstance(lpdu.pduDestination, Address)
            if lpdu.pduDestination.addrType == Address.localStationAddr:
                if _debug:
                    BIPBBMD._debug("    - unicast message")

                # if this BBMD is listed in its BDT, send a local broadcast
                if self.bbmdAddress in self.bbmdBDT:
                    xpdu.pduDestination = LocalBroadcast()
                    if _debug:
                        BIPBBMD._debug("    - local broadcast")
                    await self.request(xpdu)

            elif lpdu.pduDestination.addrType == Address.localBroadcastAddr:
                if _debug:
                    BIPBBMD._debug("    - directed broadcast message")

            else:
                BIPBBMD._warning("invalid destination address: %r", lpdu.pduDestination)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPBBMD._debug(
                        "    - sending to foreign device: %r", xpdu.pduDestination
                    )
                await self.request(xpdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            assert isinstance(lpdu.pduSource, IPv4Address)

            # process the request
            if lpdu.bvlciTimeToLive == 0:
                stat = self.delete_foreign_device_table_entry(lpdu.pduSource)
            else:
                stat = self.register_foreign_device(
                    lpdu.pduSource, lpdu.bvlciTimeToLive
                )

            # build a response
            xpdu = Result(
                code=stat, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTable):
            # build a response
            xpdu = ReadForeignDeviceTableAck(
                self.bbmdFDT, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # process the request
            stat = self.delete_foreign_device_table_entry(lpdu.bvlciAddress)

            # build a response
            xpdu = Result(
                code=stat, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # send it upstream if there is a network layer
            if self.serverPeer:
                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.pduSource,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - upstream pdu: %r", pdu)

                await self.response(pdu)

            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(lpdu.pduSource, lpdu, user_data=lpdu.pduUserData)
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte == self.bbmdAddress:
                    xpdu.pduDestination = LocalBroadcast()
                    if _debug:
                        BIPBBMD._debug("    - local broadcast")
                    await self.request(xpdu)
                else:
                    xpdu.pduDestination = IPv4Address(bdte.addrBroadcastTuple)
                    if _debug:
                        BIPBBMD._debug("    - sending to peer: %r", xpdu.pduDestination)
                    await self.request(xpdu)

            # send it to the other registered foreign devices
            for fdte in self.bbmdFDT:
                if fdte.fdAddress != pdu.pduSource:
                    xpdu.pduDestination = fdte.fdAddress
                    if _debug:
                        BIPBBMD._debug(
                            "    - sending to foreign device: %r", xpdu.pduDestination
                        )
                    await self.request(xpdu)

        elif isinstance(lpdu, OriginalUnicastNPDU):
            # send it upstream if there is a network layer
            if self.serverPeer:
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.pduSource,
                    destination=lpdu.pduDestination,
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - upstream pdu: %r", pdu)

                await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            # send it upstream if there is a network layer
            if self.serverPeer:
                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.pduSource,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - upstream pdu: %r", pdu)

                await self.response(pdu)

            # make a forwarded PDU
            xpdu = ForwardedNPDU(lpdu.pduSource, lpdu, user_data=lpdu.pduUserData)
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = IPv4Address(bdte.addrBroadcastTuple)
                    if _debug:
                        BIPBBMD._debug("    - sending to peer: %r", xpdu.pduDestination)
                    await self.request(xpdu)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPBBMD._debug(
                        "    - sending to foreign device: %r", xpdu.pduDestination
                    )
                await self.request(xpdu)

        else:
            BIPBBMD._warning("invalid pdu type: %s", type(lpdu))

    def register_foreign_device(self, addr: IPv4Address, ttl: int) -> int:
        """Add a foreign device to the FDT."""
        if _debug:
            BIPBBMD._debug("register_foreign_device %r %r", addr, ttl)

        for fdte in self.bbmdFDT:
            if addr == fdte.fdAddress:
                break
        else:
            fdte = FDTEntry()
            fdte.fdAddress = addr
            self.bbmdFDT.append(fdte)

        fdte.fdTTL = ttl
        fdte.fdRemain = ttl + 5

        # return success
        return 0

    def delete_foreign_device_table_entry(self, addr: IPv4Address) -> int:
        if _debug:
            BIPBBMD._debug("delete_foreign_device_table_entry %r", addr)

        # find it and delete it
        stat = 0
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            if addr == self.bbmdFDT[i].fdAddress:
                del self.bbmdFDT[i]
                break
        else:
            stat = 0x0050  ### entry not found

        # return status
        return stat

    def fdt_clock(self) -> None:
        # look for foreign device registrations that have expired
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            fdte = self.bbmdFDT[i]
            fdte.fdRemain -= 1

            # delete it if it expired
            if fdte.fdRemain <= 0:
                if _debug:
                    BIPBBMD._debug("foreign device expired: %r", fdte.fdAddress)
                del self.bbmdFDT[i]

        # again, again!
        self._fdt_clock_handle = asyncio.get_event_loop().call_later(1, self.fdt_clock)

    def add_peer(self, addr: IPv4Address) -> None:
        if _debug:
            BIPBBMD._debug("add_peer %r", addr)

        # see if it's already there
        for bdte in self.bbmdBDT:
            if addr == bdte:
                break
        else:
            self.bbmdBDT.append(addr)

    def delete_peer(self, addr: IPv4Address) -> None:
        if _debug:
            BIPBBMD._debug("delete_peer %r", addr)

        # look for the peer address
        for i in range(len(self.bbmdBDT) - 1, -1, -1):
            if addr == self.bbmdBDT[i]:
                del self.bbmdBDT[i]
                break
        else:
            pass


#
#   BIPNAT
#


@bacpypes_debugging
class BIPNAT(BVLLServiceAccessPoint, DebugContents):
    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = ("bbmdAddress", "bbmdBDT+", "bbmdFDT+")

    bbmdAddress: IPv4Address
    bbmdBDT: List[IPv4Address]
    bbmdFDT: List[FDTEntry]

    def __init__(self, addr, **kwargs):
        """A BBMD node that is the destination for NATed traffic."""
        if _debug:
            BIPNAT._debug("__init__ %r", addr)
        BVLLServiceAccessPoint.__init__(self, **kwargs)

        raise NotImplementedError()

        # RecurringTask.__init__(self, 1000.0)

        self.bbmdAddress = addr
        self.bbmdBDT = []
        self.bbmdFDT = []

        # install so process_task runs
        self.install_task()

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPNAT._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, Address)

        lpdu: LPDU

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            ###TODO the destination should be a peer or a registered foreign device

            # make an original unicast PDU
            lpdu = OriginalUnicastNPDU(
                pdu, destination=pdu.pduDestination, user_data=pdu.pduUserData
            )
            if _debug:
                BIPNAT._debug("    - lpdu: %r", lpdu)

            # send it downstream
            await self.request(lpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make a forwarded PDU
            lpdu = ForwardedNPDU(self.bbmdAddress, pdu, user_data=pdu.pduUserData)
            if _debug:
                BIPNAT._debug("    - forwarded lpdu: %r", lpdu)

            # send it to the peers, all of them have all F's mask
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    lpdu.pduDestination = Address(bdte.addrTuple)
                    if _debug:
                        BIPNAT._debug(
                            "        - sending to peer: %r", lpdu.pduDestination
                        )
                    self.request(lpdu)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                lpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPNAT._debug(
                        "        - sending to foreign device: %r", lpdu.pduDestination
                    )
                self.request(lpdu)

        else:
            BIPNAT._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPNAT._debug("confirmation %r", lpdu)

        xpdu: LPDU

        # some kind of response to a request
        if isinstance(lpdu, Result):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, WriteBroadcastDistributionTable):
            ###TODO verify this is from a management network/address

            # build a response
            xpdu = Result(code=99, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTable):
            ###TODO verify this is from a management network/address

            # build a response
            xpdu = ReadBroadcastDistributionTableAck(
                self.bbmdBDT, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource
            if _debug:
                BIPNAT._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ForwardedNPDU):
            ###TODO verify this is from a peer

            # build a PDU with the source from the real source
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNAT._debug("    - upstream pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(
                lpdu.bvlciAddress, lpdu, destination=None, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPNAT._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPNAT._debug(
                        "        - sending to foreign device: %r", xpdu.pduDestination
                    )
                await self.request(xpdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            ###TODO verify this is from an acceptable address

            # process the request
            stat = self.register_foreign_device(lpdu.pduSource, lpdu.bvlciTimeToLive)

            # build a response
            xpdu = Result(
                code=stat, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPNAT._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTable):
            ###TODO verify this is from a management network/address

            # build a response
            xpdu = ReadForeignDeviceTableAck(
                self.bbmdFDT, destination=lpdu.pduSource, user_data=lpdu.pduUserData
            )
            if _debug:
                BIPNAT._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            ###TODO verify this is from a management network/address

            # process the request
            stat = self.delete_foreign_device_table_entry(lpdu.bvlciAddress)

            # build a response
            xpdu = Result(code=stat, user_data=lpdu.pduUserData)
            xpdu.pduDestination = lpdu.pduSource
            if _debug:
                BIPNAT._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            ###TODO verify this is from a registered foreign device

            # build a PDU with a local broadcast address
            pdu = PDU(
                pdu.pduData,
                source=pdu.pduSource,
                destination=LocalBroadcast(),
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPNAT._debug("    - upstream pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(lpdu.pduSource, lpdu, user_data=lpdu.pduUserData)
            if _debug:
                BIPNAT._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte == self.bbmdAddress:
                    if _debug:
                        BIPNAT._debug("        - no local broadcast")
                else:
                    xpdu.pduDestination = Address(bdte.addrTuple)
                    if _debug:
                        BIPNAT._debug(
                            "        - sending to peer: %r", xpdu.pduDestination
                        )
                    await self.request(xpdu)

            # send it to the other registered foreign devices
            for fdte in self.bbmdFDT:
                if fdte.fdAddress != pdu.pduSource:
                    xpdu.pduDestination = fdte.fdAddress
                    if _debug:
                        BIPNAT._debug(
                            "        - sending to foreign device: %r",
                            xpdu.pduDestination,
                        )
                    await self.request(xpdu)

        elif isinstance(lpdu, OriginalUnicastNPDU):
            ###TODO verify this is from a peer

            # build a vanilla PDU
            pdu = PDU(
                pdu.pduData,
                source=pdu.pduSource,
                destination=pdu.pduDestination,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPNAT._debug("    - upstream pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            if _debug:
                BIPNAT._debug("    - original broadcast dropped")

        else:
            BIPNAT._warning("invalid pdu type: %s", type(lpdu))

    def register_foreign_device(self, addr, ttl):
        """Add a foreign device to the FDT."""
        if _debug:
            BIPNAT._debug("register_foreign_device %r %r", addr, ttl)

        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = Address(addr)
        else:
            raise TypeError("addr must be a string or an Address")

        for fdte in self.bbmdFDT:
            if addr == fdte.fdAddress:
                break
        else:
            fdte = FDTEntry()
            fdte.fdAddress = addr
            self.bbmdFDT.append(fdte)

        fdte.fdTTL = ttl
        fdte.fdRemain = ttl + 5

        # return success
        return 0

    def delete_foreign_device_table_entry(self, addr):
        if _debug:
            BIPNAT._debug("delete_foreign_device_table_entry %r", addr)

        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = Address(addr)
        else:
            raise TypeError("addr must be a string or an Address")

        # find it and delete it
        stat = 0
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            if addr == self.bbmdFDT[i].fdAddress:
                del self.bbmdFDT[i]
                break
        else:
            stat = 99  ### entry not found

        # return status
        return stat

    def process_task(self):
        # look for foreign device registrations that have expired
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            fdte = self.bbmdFDT[i]
            fdte.fdRemain -= 1

            # delete it if it expired
            if fdte.fdRemain <= 0:
                if _debug:
                    BIPNAT._debug("foreign device expired: %r", fdte.fdAddress)
                del self.bbmdFDT[i]

    def add_peer(self, addr):
        if _debug:
            BIPNAT._debug("add_peer %r", addr)

        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = Address(addr)
        else:
            raise TypeError("addr must be a string or an Address")

        # if it's this BBMD, make it the first one
        if self.bbmdBDT and (addr == self.bbmdAddress):
            raise RuntimeError("add self to BDT as first address")

        # see if it's already there
        for bdte in self.bbmdBDT:
            if addr == bdte:
                break
        else:
            self.bbmdBDT.append(addr)

    def delete_peer(self, addr):
        if _debug:
            BIPNAT._debug("delete_peer %r", addr)

        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = Address(addr)
        else:
            raise TypeError("addr must be a string or an Address")

        # look for the peer address
        for i in range(len(self.bbmdBDT) - 1, -1, -1):
            if addr == self.bbmdBDT[i]:
                del self.bbmdBDT[i]
                break
        else:
            pass


#
#   BVLLServiceElement
#


@bacpypes_debugging
class BVLLServiceElement(ApplicationServiceElement):
    _debug: Callable[..., None]
    _warning: Callable[..., None]

    def __init__(self, *, aseID=None) -> None:
        if _debug:
            BVLLServiceElement._debug("__init__ aseID=%r", aseID)
        ApplicationServiceElement.__init__(self, aseID=aseID)

        self.read_bdt_future = None
        self.read_bdt_timeout_handle = None
        self.read_fdt_future = None
        self.read_fdt_timeout_handle = None
        self.write_bdt_future = None

    async def indication(self, lpdu: LPDU) -> None:
        if _debug:
            BVLLServiceElement._debug("indication %r", lpdu)

        # redirect
        fn = lpdu.__class__.__name__
        if hasattr(self, fn):
            await getattr(self, fn)(lpdu)
        else:
            BVLLServiceElement._warning("no handler for %s", fn)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BVLLServiceElement._debug("confirmation %r", lpdu)

        # redirect
        fn = lpdu.__class__.__name__
        if hasattr(self, fn):
            await getattr(self, fn)(lpdu)
        else:
            BVLLServiceElement._warning("no handler for %s", fn)

    async def Result(self, pdu: Result) -> None:
        if _debug:
            BVLLServiceElement._debug("Result %r", pdu)

        if self.read_bdt_future:
            if _debug:
                BVLLServiceElement._debug("  - read BDT Error")

            self.read_bdt_future.set_exception(pdu)
            self.read_bdt_future = None
            self.read_bdt_timeout_handle.cancel()
            self.read_bdt_timeout_handle = None

        elif self.read_fdt_future:
            if _debug:
                BVLLServiceElement._debug("  - read FDT Error")

            self.read_fdt_future.set_exception(pdu)
            self.read_fdt_future = None
            self.read_fdt_timeout_handle.cancel()
            self.read_fdt_timeout_handle = None

        elif self.write_bdt_future:
            if _debug:
                BVLLServiceElement._debug("  - write BDT Error")

            self.write_bdt_future.set_exception(pdu)
            self.write_bdt_future = None
            self.write_bdt_timeout_handle.cancel()
            self.write_bdt_timeout_handle = None

    def read_broadcast_distribution_table(
        self, address: IPv4Address, timeout: float = READ_BDT_TIMEOUT
    ) -> asyncio.Future:
        """
        Read the broadcast distribution table from a BBMD, returns a list of
        IPv4Address's (check the mask!) or None if there is no response.
        """
        if _debug:
            BVLLServiceElement._debug(
                "read_broadcast_distribution_table %r %r", address, timeout
            )

        # one at a time please
        if self.read_bdt_future:
            raise RuntimeError("request pending")

        self.read_bdt_future = asyncio.Future()
        if _debug:
            BVLLServiceElement._debug("    - read_bdt_future: %r", self.read_bdt_future)

        # get the loop to schedule a time to stop looking
        loop = asyncio.get_event_loop()
        if _debug:
            BVLLServiceElement._debug("    - loop time: %r", loop.time())

        # schedule a timeout
        self.read_bdt_timeout_handle = loop.call_later(timeout, self._read_bdt_timeout)
        if _debug:
            BVLLServiceElement._debug(
                "    - read_bdt_timeout_handle: %r", self.read_bdt_timeout_handle
            )

        asyncio.ensure_future(
            self.request(ReadBroadcastDistributionTable(destination=address))
        )

        return self.read_bdt_future

    def _read_bdt_timeout(self):
        if _debug:
            BVLLServiceElement._debug("_read_bdt_timeout")
        self.read_bdt_future.set_result(None)
        self.read_bdt_future = None

    async def ReadBroadcastDistributionTableAck(
        self, pdu: ReadBroadcastDistributionTableAck
    ) -> None:
        if _debug:
            BVLLServiceElement._debug("confirmation %r", pdu)

        # set the result and clear the timer
        self.read_bdt_future.set_result(pdu.bvlciBDT)
        self.read_bdt_future = None
        self.read_bdt_timeout_handle.cancel()
        self.read_bdt_timeout_handle = None

    def write_broadcast_distribution_table(
        self,
        address: IPv4Address,
        bdt: List[IPv4Address],
        timeout: float = WRITE_BDT_TIMEOUT,
    ) -> asyncio.Future:
        """
        Read the broadcast distribution table from a BBMD, returns a list of
        IPv4Address's (check the mask!) or None if there is no response.
        """
        if _debug:
            BVLLServiceElement._debug(
                "write_broadcast_distribution_table %r %r", address, timeout
            )

        # one at a time please
        if self.write_bdt_future:
            raise RuntimeError("request pending")

        self.write_bdt_future = asyncio.Future()
        if _debug:
            BVLLServiceElement._debug(
                "    - write_bdt_future: %r", self.write_bdt_future
            )

        # get the loop to schedule a time to stop looking
        loop = asyncio.get_event_loop()
        if _debug:
            BVLLServiceElement._debug("    - loop time: %r", loop.time())

        # schedule a timeout
        self.write_bdt_timeout_handle = loop.call_later(
            timeout, self._write_bdt_timeout
        )
        if _debug:
            BVLLServiceElement._debug(
                "    - write_bdt_timeout_handle: %r", self.write_bdt_timeout_handle
            )

        asyncio.ensure_future(
            self.request(WriteBroadcastDistributionTable(bdt, destination=address))
        )

        return self.write_bdt_future

    def _write_bdt_timeout(self):
        if _debug:
            BVLLServiceElement._debug("_write_bdt_timeout")
        self.write_bdt_future.set_result(None)
        self.write_bdt_future = None

    def read_foreign_device_table(
        self, address: IPv4Address, timeout: float = READ_FDT_TIMEOUT
    ) -> asyncio.Future:
        """
        Read the foreign device table from a BBMD, returns a list of FDTEntry's
        or None if there is no response.
        """
        if _debug:
            BVLLServiceElement._debug(
                "read_foreign_device_table %r %r", address, timeout
            )

        # one at a time please
        if self.read_fdt_future:
            raise RuntimeError("request pending")

        self.read_fdt_future = asyncio.Future()
        if _debug:
            BVLLServiceElement._debug("    - read_bdt_future: %r", self.read_bdt_future)

        # get the loop to schedule a time to stop looking
        loop = asyncio.get_event_loop()
        if _debug:
            BVLLServiceElement._debug("    - loop time: %r", loop.time())

        # schedule a timeout
        self.read_fdt_timeout_handle = loop.call_later(
            READ_BDT_TIMEOUT, self._read_fdt_timeout
        )
        if _debug:
            BVLLServiceElement._debug(
                "    - read_fdt_timeout_handle: %r", self.read_fdt_timeout_handle
            )

        asyncio.ensure_future(self.request(ReadForeignDeviceTable(destination=address)))

        return self.read_fdt_future

    def _read_fdt_timeout(self):
        if _debug:
            BVLLServiceElement._debug("_read_fdt_timeout")
        self.read_fdt_future.set_result(None)
        self.read_fdt_future = None

    async def ReadForeignDeviceTableAck(self, pdu: ReadForeignDeviceTableAck) -> None:
        if _debug:
            BVLLServiceElement._debug("confirmation %r", pdu)

        # set the result and clear the timer
        self.read_fdt_future.set_result(pdu.bvlciFDT)
        self.read_fdt_future = None
        self.read_fdt_timeout_handle.cancel()
        self.read_fdt_timeout_handle = None
