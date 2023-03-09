"""
BACnet IPv6 Virtual Link Layer Service
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging

from ..comm import Client, Server, ServiceAccessPoint, ApplicationServiceElement
from ..pdu import Address, LocalBroadcast, IPv6Address, VirtualAddress, PDU

from .bvll import (
    LPDU,
    FDTEntry,
    Result,
    OriginalUnicastNPDU,
    OriginalBroadcastNPDU,
    AddressResolution,
    ForwardedAddressResolution,
    AddressResolutionACK,
    VirtualAddressResolution,
    VirtualAddressResolutionACK,
    ForwardedNPDU,
    RegisterForeignDevice,
    DeleteForeignDeviceTableEntry,
    DistributeBroadcastToNetwork,
)

if TYPE_CHECKING:
    # class is declared as generic in stubs but not at runtime
    IPv6AddressFuture = asyncio.Future[IPv6Address]
    VirtualAddressFuture = asyncio.Future[VirtualAddress]
else:
    IPv6AddressFuture = asyncio.Future
    VirtualAddressFuture = asyncio.Future


# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   VirtualMACAddressTable
#


class VirtualMACAddressTable(DebugContents):
    """
    The Virtual MAC Address Table is used to provide source and destination
    information to the upper layers of the application because the 18-octet
    IPv6 addresses are too large for most BACnet applications that expect
    at most 6-octet Ethernet or IPv4 addresses.

    See Clause U.5.
    """

    _debug: Callable[..., None]
    _debug_contents = ("vmac_to_ipv6+", "ipv6_to_vmac+")

    vmac_to_ipv6: Dict[VirtualAddress, IPv6Address]
    ipv6_to_vmac: Dict[IPv6Address, VirtualAddress]

    def __init__(self):
        self.vmac_to_ipv6 = {}
        self.ipv6_to_vmac = {}

    def __getitem__(
        self, item: Union[VirtualAddress, IPv6Address]
    ) -> Union[VirtualAddress, IPv6Address, None]:
        if isinstance(item, VirtualAddress):
            return self.vmac_to_ipv6.get(item, None)
        elif isinstance(item, IPv6Address):
            return self.ipv6_to_vmac.get(item, None)
        else:
            raise TypeError(f"item: {item!r}")

    def __setitem__(
        self,
        item: Union[VirtualAddress, IPv6Address],
        addr: Union[VirtualAddress, IPv6Address],
    ) -> None:
        if isinstance(item, VirtualAddress):
            if item in self.vmac_to_ipv6:
                old_addr = self.vmac_to_ipv6[item]
                if addr == old_addr:
                    return
                if old_addr not in self.ipv6_to_vmac:
                    raise RuntimeError("inconsistent")
                del self.ipv6_to_vmac[old_addr]

            if addr in self.ipv6_to_vmac:
                old_item = self.ipv6_to_vmac[addr]
                if item == old_item:
                    return
                if old_item not in self.vmac_to_ipv6:
                    raise RuntimeError("inconsistent")
                del self.vmac_to_ipv6[old_item]

            self.vmac_to_ipv6[item] = addr
            self.ipv6_to_vmac[addr] = item

        elif isinstance(item, IPv6Address):
            if item in self.ipv6_to_vmac:
                old_addr = self.ipv6_to_vmac[item]
                if addr == old_addr:
                    return
                if old_addr not in self.vmac_to_ipv6:
                    raise RuntimeError("inconsistent")
                del self.vmac_to_ipv6[old_addr]

            if addr in self.vmac_to_ipv6:
                old_item = self.vmac_to_ipv6[addr]
                if item == old_item:
                    return
                if old_item not in self.ipv6_to_vmac:
                    raise RuntimeError("inconsistent")
                del self.ipv6_to_vmac[old_item]

            self.ipv6_to_vmac[item] = addr
            self.vmac_to_ipv6[addr] = item

        else:
            raise TypeError(f"item: {item!r}")


#
#   BVLLServiceAccessPoint
#


@bacpypes_debugging
class BVLLServiceAccessPoint(Client[LPDU], Server[PDU], ServiceAccessPoint):
    """
    BACnet IPv6 Service Access Point

    An instance of this is stacked on a BVLLCodec, as a server it presents
    PDUs.
    """

    _debug_contents = ("virtual_address", "vmac_addr_table")

    virtual_address: VirtualAddress  # see Clause H.7.2
    vmac_addr_table: VirtualMACAddressTable

    def __init__(
        self,
        *,
        virtual_address: VirtualAddress,
        sapID: Optional[str] = None,
        cid: Optional[str] = None,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            BVLLServiceAccessPoint._debug("__init__")
        Client.__init__(self, cid=cid)
        Server.__init__(self, sid=sid)
        ServiceAccessPoint.__init__(self, sapID=sapID)

        self.virtual_address = virtual_address
        self.vmac_addr_table = VirtualMACAddressTable()

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
class BIPNormal(BVLLServiceAccessPoint, DebugContents):

    _debug: Callable[..., None]
    _warning: Callable[..., None]

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPNormal._debug("indication %r", pdu)

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # destination address is a VirtualAddress
            destination_ipv6_address: IPv6Address = self.vmac_addr_table[
                pdu.pduDestination
            ]

            # if there is a service element, let it resolve it
            if not destination_ipv6_address:
                try:
                    destination_ipv6_address = await asyncio.wait_for(
                        self.serviceElement.resolve_virtual_address(pdu.pduDestination),
                        timeout=5,
                    )
                except asyncio.TimeoutError:
                    return
            if _debug:
                BIPNormal._debug(
                    "    - destination_ipv6_address: %r", destination_ipv6_address
                )

            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(
                self.virtual_address,
                pdu.pduDestination,
                pdu,
                destination=destination_ipv6_address,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            xpdu = OriginalBroadcastNPDU(
                self.virtual_address,
                pdu,
                destination=pdu.pduDestination,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        else:
            BIPNormal._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPNormal._debug("confirmation %r", lpdu)

        # some kind of response to a request
        if isinstance(lpdu, Result):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, OriginalUnicastNPDU):
            if lpdu.bvlciDestinationVirtualAddress != self.virtual_address:
                if _debug:
                    BIPNormal._debug("    - not for us")
                return

            # update the virtual address table
            self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

            # build a PDU
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=self.virtual_address,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            if lpdu.bvlciSourceVirtualAddress == self.virtual_address:
                if _debug:
                    BIPNormal._debug("    - from us")
                return

            # update the virtual address table
            self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

            # build a PDU with a local broadcast address
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, AddressResolution):
            if lpdu.bvlciSourceVirtualAddress == self.virtual_address:
                if _debug:
                    BIPNormal._debug("    - from us")
                return
            if lpdu.bvlciTargetVirtualAddress != self.virtual_address:
                if _debug:
                    BIPNormal._debug("    - not for us")
                return

            xpdu = AddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                destination=lpdu.pduSource,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ForwardedAddressResolution):
            if lpdu.bvlciTargetVirtualAddress != self.virtual_address:
                if _debug:
                    BIPNormal._debug("    - not for us")
                return

            xpdu = AddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciOriginalSourceVirtualAddress,
                destination=lpdu.bvlciOriginalSourceIPv6Address,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, AddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, VirtualAddressResolution):
            # send back an ACK
            xpdu = VirtualAddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                destination=lpdu.pduSource,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPNormal._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, VirtualAddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # update the virtual address table
            self.vmac_addr_table[
                lpdu.bvlciSourceVirtualAddress
            ] = lpdu.bvlciSourceIPv6Address

            # build a PDU with the source from the real source
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            # if route_aware:
            #     xpdu.pduSource.addrRoute = pdu.pduSource

            if _debug:
                BIPNormal._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x0090, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x00A0, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x00C0, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        else:
            BIPNormal._warning("invalid pdu type: %s", type(lpdu))


#
#   BIPForeign
#


@bacpypes_debugging
class BIPForeign(BVLLServiceAccessPoint, DebugContents):

    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = ("bbmdAddress", "bbmdTimeToLive", "bbmdRegistrationStatus")

    bbmdAddress: Optional[IPv6Address]
    bbmdTimeToLive: Optional[int]
    bbmdRegistrationStatus: int

    _registration_event: asyncio.Event
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

    async def sap_indication(self, lpdu: LPDU) -> None:
        if _debug:
            BIPForeign._debug("sap_indication %r", lpdu)

        # check for local stations
        if lpdu.pduDestination.addrType == Address.localStationAddr:
            # send it downstream
            await self.request(lpdu)

        # check for broadcasts, redirect them to the BBMD
        elif lpdu.pduDestination.addrType == Address.localBroadcastAddr:
            # check the BBMD registration status, we may not be registered
            if self.bbmdRegistrationStatus != 0:
                if _debug:
                    BIPForeign._debug("    - packet dropped, unregistered")
                return

            # redirect it to the BBMD
            lpdu.pduDestination = self.bbmdAddress

            # send it downstream
            await self.request(lpdu)

        else:
            BIPForeign._warning("invalid destination address: %r", lpdu.pduDestination)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPForeign._debug("indication %r", pdu)

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # destination address is a VirtualAddress
            destination_ipv6_address: IPv6Address = self.vmac_addr_table[
                pdu.pduDestination
            ]

            # if there is a service element, let it resolve it
            if not destination_ipv6_address:
                try:
                    destination_ipv6_address = await asyncio.wait_for(
                        self.serviceElement.resolve_virtual_address(pdu.pduDestination),
                        timeout=5,
                    )
                except asyncio.TimeoutError:
                    return
            if _debug:
                BIPNormal._debug(
                    "    - destination_ipv6_address: %r", destination_ipv6_address
                )

            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(
                self.virtual_address,
                pdu.pduDestination,
                pdu.pduData,
                destination=destination_ipv6_address,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

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
                    return  ###TODO raise TimeoutError?

            elif self.bbmdRegistrationStatus == 0:
                pass

            else:
                if _debug:
                    BIPForeign._debug(
                        "    - registration error: %r", self.bbmdRegistrationStatus
                    )
                return  ###TODO raise RuntimeError?

            # make a broadcast PDU
            xpdu = DistributeBroadcastToNetwork(
                self.virtual_address,
                pdu.pduData,
                destination=self.bbmdAddress,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        else:
            BIPForeign._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPForeign._debug("confirmation %r", lpdu)

        # some kind of response to a request
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
            self.bbmdRegistrationStatus = lpdu.bvlciResultCode

            # if successful, start tracking the registration
            if self.bbmdRegistrationStatus == 0:
                self._registration_event.set()
                self._start_tracking_registration()

        elif isinstance(lpdu, OriginalUnicastNPDU):
            if lpdu.bvlciDestinationVirtualAddress != self.virtual_address:
                if _debug:
                    BIPForeign._debug("    - not for us")
                return

            # update the virtual address table
            self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

            # build a PDU
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=self.virtual_address,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            if _debug:
                BIPForeign._debug("    - packet dropped")

        elif isinstance(lpdu, AddressResolution):
            if lpdu.bvlciTargetVirtualAddress != self.virtual_address:
                if _debug:
                    BIPForeign._debug("    - not for us")
                return

            xpdu = AddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                destination=lpdu.pduSource,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, ForwardedAddressResolution):
            if lpdu.bvlciTargetVirtualAddress != self.virtual_address:
                if _debug:
                    BIPForeign._debug("    - not for us")
                return

            xpdu = AddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciOriginalSourceVirtualAddress,
                destination=lpdu.bvlciOriginalSourceIPv6Address,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, AddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, VirtualAddressResolution):
            # send back an ACK
            xpdu = VirtualAddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                destination=lpdu.pduSource,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, VirtualAddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # update the virtual address table
            self.vmac_addr_table[
                lpdu.bvlciSourceVirtualAddress
            ] = lpdu.bvlciSourceIPv6Address

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

            # build a PDU with the source from the source virtual address
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=LocalBroadcast(),
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPForeign._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x0090, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x00A0, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # build a response
            xpdu = Result(
                self.virtual_address, result_code=0x00C0, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        else:
            BIPForeign._warning("invalid pdu type: %s", type(lpdu))

    def register(self, addr: IPv6Address, ttl: int) -> None:
        """Start the foreign device registration process with the given BBMD.

        Registration will be renewed periodically according to the ttl value
        until explicitly stopped by a call to `unregister`.
        """
        if _debug:
            BIPForeign._debug("register %r %r", addr, ttl)

        # a little error checking
        if not isinstance(addr, IPv6Address):
            raise TypeError("addr must be an IPv6Address")
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

        # stop tracking the registration, and there might not be one
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
        pdu = RegisterForeignDevice(
            self.virtual_address, self.bbmdTimeToLive, destination=self.bbmdAddress
        )
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
            min(5, self.bbmdTimeToLive), self._start_registration
        )
        if _debug:
            BIPForeign._debug(
                "    - re-registration timeout: %r", self._reregistration_timeout_handle
            )

    async def _stop_registration(self, bbmdAddress: IPv6Address) -> None:
        """Scheduled when the registration is being canceled."""
        if _debug:
            BIPForeign._debug("_stop_registration")

        pdu = RegisterForeignDevice(self.virtual_address, 0, destination=bbmdAddress)

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
            BIPForeign._debug("    _stop_tracking_registration")

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
    _debug_contents = ("bbmdAddress", "bbmdBDT+", "bbmdFDT++")

    bbmdAddress: IPv6Address
    bbmdBDT: List[IPv6Address]
    bbmdFDT: List[FDTEntry]

    _fdt_clock_handle: asyncio.TimerHandle

    def __init__(self, bbmd_address: IPv6Address, **kwargs):
        if _debug:
            BIPBBMD._debug("__init__ %r", bbmd_address)
        BVLLServiceAccessPoint.__init__(self, **kwargs)

        self.bbmdAddress = bbmd_address
        self.bbmdBDT = []
        self.bbmdFDT = []

        # schedule the clock to run
        self._fdt_clock_handle = asyncio.get_event_loop().call_soon(self.fdt_clock)

    async def sap_indication(self, lpdu: LPDU) -> None:
        if _debug:
            BIPBBMD._debug("sap_indication %r", lpdu)

        # check for local stations
        if lpdu.pduDestination.addrType == Address.localStationAddr:
            if _debug:
                BIPBBMD._debug("    - unicast")

            # send it downstream
            await self.request(lpdu)

        # check for broadcasts, redirect them to the BBMD
        elif lpdu.pduDestination.addrType == Address.localBroadcastAddr:
            # if route_aware and pdu.pduDestination.addrRoute:
            #     xpdu.pduDestination = pdu.pduDestination.addrRoute
            if _debug:
                BIPBBMD._debug("    - local broadcast")

            # send it downstream
            await self.request(lpdu)

            # skip other processing if the route was provided
            # if settings.route_aware and pdu.pduDestination.addrRoute:
            #     return
            if _debug:
                BIPBBMD._debug("    - forwarded lpdu: %r", lpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    lpdu.pduDestination = bdte
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
            BIPBBMD._warning("invalid destination address: %r", lpdu.pduDestination)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            BIPBBMD._debug("indication %r", pdu)

        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # destination address is a VirtualAddress
            destination_ipv6_address: IPv6Address = self.vmac_addr_table[
                pdu.pduDestination
            ]

            # if there is a service element, let it resolve it
            if not destination_ipv6_address:
                try:
                    destination_ipv6_address = await asyncio.wait_for(
                        self.serviceElement.resolve_virtual_address(pdu.pduDestination),
                        timeout=5,
                    )
                except asyncio.TimeoutError:
                    return
            if _debug:
                BIPBBMD._debug(
                    "    - destination_ipv6_address: %r", destination_ipv6_address
                )

            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(
                self.virtual_address,
                pdu.pduDestination,
                pdu.pduData,
                destination=destination_ipv6_address,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - original unicast xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            xpdu = OriginalBroadcastNPDU(
                self.virtual_address,
                pdu.pduData,
                destination=pdu.pduDestination,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - original broadcast xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

            # skip other processing if the route was provided
            # if settings.route_aware and pdu.pduDestination.addrRoute:
            #     return

            xpdu = ForwardedNPDU(
                self.virtual_address,
                self.bbmdAddress,
                pdu.pduData,
                user_data=pdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = bdte
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
            BIPBBMD._warning("invalid destination address: %r", pdu.pduDestination)

    async def confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            BIPBBMD._debug("confirmation %r", lpdu)

        # some kind of response to a request
        if isinstance(lpdu, Result):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, OriginalUnicastNPDU):
            if lpdu.bvlciDestinationVirtualAddress != self.virtual_address:
                if _debug:
                    BIPBBMD._debug("    - not for us")
                return

            # update the virtual address table
            self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

            # build a PDU
            pdu = PDU(
                lpdu.pduData,
                source=lpdu.bvlciSourceVirtualAddress,
                destination=self.virtual_address,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - pdu: %r", pdu)

            # send it upstream
            await self.response(pdu)

        elif isinstance(lpdu, OriginalBroadcastNPDU):
            if lpdu.bvlciSourceVirtualAddress == self.virtual_address:
                if _debug:
                    BIPBBMD._debug("    - from us")
                return

            # send it upstream if there is a network layer
            if self.serverPeer:
                # update the virtual address table
                self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.bvlciSourceVirtualAddress,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - pdu: %r", pdu)

                # send it upstream
                await self.response(pdu)

            # make a forwarded PDU
            xpdu = ForwardedNPDU(
                lpdu.bvlciSourceVirtualAddress,
                lpdu.pduSource,
                lpdu.pduData,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = bdte
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

        elif isinstance(lpdu, AddressResolution):
            if lpdu.bvlciTargetVirtualAddress == self.virtual_address:
                if _debug:
                    BIPBBMD._debug("    - looking for us")

                xpdu = AddressResolutionACK(
                    source_virtual_address=self.virtual_address,
                    destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                    destination=lpdu.pduSource,
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - xpdu: %r", xpdu)

                # send it downstream
                await self.request(xpdu)

            else:
                if _debug:
                    BIPBBMD._debug("    - looking for someone else")

                # make a forwarded address resolution
                xpdu = ForwardedAddressResolution(
                    lpdu.bvlciSourceVirtualAddress,
                    lpdu.bvlciTargetVirtualAddress,
                    lpdu.pduSource,
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - forwarded address resolution xpdu: %r", xpdu)

                # make a local broadcast
                xpdu.pduDestination = LocalBroadcast()
                if _debug:
                    BIPBBMD._debug(
                        "    - sending local broadcast: %r", xpdu.pduDestination
                    )
                await self.request(xpdu)

                # send it to the peers
                for bdte in self.bbmdBDT:
                    if bdte != self.bbmdAddress:
                        xpdu.pduDestination = bdte
                        if _debug:
                            BIPBBMD._debug(
                                "    - sending to peer: %r", xpdu.pduDestination
                            )
                        await self.request(xpdu)

                # send it to the registered foreign devices
                for fdte in self.bbmdFDT:
                    xpdu.pduDestination = fdte.fdAddress
                    if _debug:
                        BIPBBMD._debug(
                            "    - sending to foreign device: %r", xpdu.pduDestination
                        )
                    await self.request(xpdu)

        elif isinstance(lpdu, ForwardedAddressResolution):
            if lpdu.bvlciTargetVirtualAddress == self.virtual_address:
                if _debug:
                    BIPBBMD._debug("    - this is us")

                xpdu = AddressResolutionACK(
                    source_virtual_address=self.virtual_address,
                    destination_virtual_address=lpdu.bvlciOriginalSourceVirtualAddress,
                    destination=lpdu.bvlciOriginalSourceIPv6Address,
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - xpdu: %r", xpdu)

                # send it downstream
                await self.request(xpdu)

            else:
                # make sure it is from a peer
                for bdte in self.bbmdBDT:
                    if bdte == lpdu.pduSource:
                        break
                else:
                    if _debug:
                        BIPBBMD._debug("    - not from a peer")
                    return

                # make a local broadcast
                lpdu.pduDestination = LocalBroadcast()
                if _debug:
                    BIPBBMD._debug(
                        "    - sending local broadcast: %r", lpdu.pduDestination
                    )
                await self.request(xpdu)

                # send it to the registered foreign devices
                for fdte in self.bbmdFDT:
                    lpdu.pduDestination = fdte.fdAddress
                    if _debug:
                        BIPBBMD._debug(
                            "    - sending to foreign device: %r", lpdu.pduDestination
                        )
                    await self.request(lpdu)

        elif isinstance(lpdu, AddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, VirtualAddressResolution):
            # send back an ACK
            xpdu = VirtualAddressResolutionACK(
                source_virtual_address=self.virtual_address,
                destination_virtual_address=lpdu.bvlciSourceVirtualAddress,
                destination=lpdu.pduSource,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - xpdu: %r", xpdu)

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, VirtualAddressResolutionACK):
            # send this to the service access point
            await self.sap_response(lpdu)

        elif isinstance(lpdu, ForwardedNPDU):
            # make sure it is from a peer
            for bdte in self.bbmdBDT:
                if bdte == lpdu.pduSource:
                    break
            else:
                if _debug:
                    BIPBBMD._debug("    - not from a peer")
                return

            # send it upstream if there is a network layer
            if self.serverPeer:
                # update the virtual address table
                self.vmac_addr_table[
                    lpdu.bvlciSourceVirtualAddress
                ] = lpdu.bvlciSourceIPv6Address

                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.bvlciSourceVirtualAddress,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPNormal._debug("    - pdu: %r", pdu)

                # send it upstream
                await self.response(pdu)

            # make a forwarded PDU
            xpdu = ForwardedNPDU(
                lpdu.bvlciSourceVirtualAddress,
                lpdu.bvlciSourceIPv6Address,
                lpdu.pduData,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # broadcast it locally
            xpdu.pduDestination = LocalBroadcast()
            if _debug:
                BIPBBMD._debug("    - local broadcast")
            await self.request(xpdu)

            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if _debug:
                    BIPBBMD._debug(
                        "    - sending to foreign device: %r", xpdu.pduDestination
                    )
                await self.request(xpdu)

        elif isinstance(lpdu, RegisterForeignDevice):
            # process the request
            if lpdu.bvlciTimeToLive == 0:
                stat = self.delete_foreign_device_table_entry(lpdu.pduSource)
            else:
                stat = self.register_foreign_device(
                    lpdu.pduSource, lpdu.bvlciTimeToLive
                )

            # build a response
            xpdu = Result(
                self.virtual_address, result_code=stat, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DeleteForeignDeviceTableEntry):
            # process the request
            stat = self.delete_foreign_device_table_entry(lpdu.bvlciFDTEntry)

            # build a response
            xpdu = Result(
                self.virtual_address, result_code=stat, user_data=lpdu.pduUserData
            )
            xpdu.pduDestination = lpdu.pduSource

            # send it downstream
            await self.request(xpdu)

        elif isinstance(lpdu, DistributeBroadcastToNetwork):
            # send it to the other registered foreign devices
            for fdte in self.bbmdFDT:
                if fdte.fdAddress == lpdu.pduSource:
                    break
            else:
                if _debug:
                    BIPBBMD._debug("    - not from a registered foreign device")
                return

            # send it upstream if there is a network layer
            if self.serverPeer:
                # update the virtual address table
                self.vmac_addr_table[lpdu.bvlciSourceVirtualAddress] = lpdu.pduSource

                # build a PDU with a local broadcast address
                pdu = PDU(
                    lpdu.pduData,
                    source=lpdu.bvlciSourceVirtualAddress,
                    destination=LocalBroadcast(),
                    user_data=lpdu.pduUserData,
                )
                if _debug:
                    BIPBBMD._debug("    - pdu: %r", pdu)

                # send it upstream
                await self.response(pdu)

            # make a forwarded PDU
            xpdu = ForwardedNPDU(
                lpdu.bvlciSourceVirtualAddress,
                lpdu.pduSource,
                lpdu.pduData,
                user_data=lpdu.pduUserData,
            )
            if _debug:
                BIPBBMD._debug("    - forwarded xpdu: %r", xpdu)

            # broadcast it locally
            xpdu.pduDestination = LocalBroadcast()
            if _debug:
                BIPBBMD._debug("    - local broadcast")
            await self.request(xpdu)

            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = bdte
                    if _debug:
                        BIPBBMD._debug("    - sending to peer: %r", xpdu.pduDestination)
                    await self.request(xpdu)

            # send it to the other registered foreign devices
            for fdte in self.bbmdFDT:
                if fdte.fdAddress != lpdu.pduSource:
                    xpdu.pduDestination = fdte.fdAddress
                    if _debug:
                        BIPBBMD._debug(
                            "    - sending to foreign device: %r", xpdu.pduDestination
                        )
                    await self.request(xpdu)

        else:
            BIPBBMD._warning("invalid pdu type: %s", type(lpdu))

    def register_foreign_device(self, addr: IPv6Address, ttl: int) -> int:
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

    def delete_foreign_device_table_entry(self, addr: IPv6Address) -> int:
        if _debug:
            BIPBBMD._debug("delete_foreign_device_table_entry %r", addr)

        # find it and delete it
        stat = 0
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            if addr == self.bbmdFDT[i].fdAddress:
                del self.bbmdFDT[i]
                break
        else:
            stat = 0x0050  # entry not found

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

    def add_peer(self, addr: IPv6Address) -> None:
        if _debug:
            BIPBBMD._debug("add_peer %r", addr)

        # see if it's already there
        for bdte in self.bbmdBDT:
            if addr == bdte:
                break
        else:
            self.bbmdBDT.append(addr)

    def delete_peer(self, addr: IPv6Address) -> None:
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
#   BVLLServiceElement
#


@bacpypes_debugging
class BVLLServiceElement(ApplicationServiceElement):

    _debug: Callable[..., None]
    _warning: Callable[..., None]

    virtual_address_resolution: Dict[VirtualAddress, IPv6AddressFuture]

    def __init__(self, *, aseID=None) -> None:
        if _debug:
            BVLLServiceElement._debug("__init__ aseID=%r", aseID)
        ApplicationServiceElement.__init__(self, aseID=aseID)

        # empty dictionary of pending address resolution requests
        self.virtual_address_resolution = {}

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

    def resolve_virtual_address(self, address: VirtualAddress) -> IPv6AddressFuture:
        """
        This function returns a future which is awaitable and will be completed
        when the virtual address resolution response comes back.
        """
        if _debug:
            BVLLServiceElement._debug("resolve_virtual_address %r", address)

        if address in self.virtual_address_resolution:
            return self.virtual_address_resolution[address]

        # create a future
        future = IPv6AddressFuture()
        self.virtual_address_resolution[address] = future

        # add a callback in case the request is canceled (timeout)
        future.add_done_callback(partial(self._resolve_virtual_address_done, address))

        # create a request to resolve it and create a task to send it
        address_resolution = AddressResolution(
            source_virtual_address=self.elementService.virtual_address,
            target_virtual_address=address,
            destination=LocalBroadcast(),
        )
        asyncio.create_task(self.request(address_resolution))

        # return the future
        return future

    def _resolve_virtual_address_done(
        self, address: VirtualAddress, future: IPv6AddressFuture
    ) -> None:
        if _debug:
            BVLLServiceElement._debug(
                "_resolve_virtual_address_done %r %r", address, future
            )

        if address not in self.virtual_address_resolution:
            if _debug:
                BVLLServiceElement._debug("    - nothing pending")
            return
        if future.done():
            if _debug:
                BVLLServiceElement._debug("    - note: future is done")
        if future.cancelled():
            if _debug:
                BVLLServiceElement._debug("    - note: future has been cancelled")

        # remove it from the pending dictionary
        del self.virtual_address_resolution[address]

    async def AddressResolutionACK(self, lpdu: AddressResolutionACK) -> None:
        if _debug:
            BVLLServiceElement._debug("AddressResolutionACK %r", lpdu)

        address = lpdu.bvlciSourceVirtualAddress
        if address not in self.virtual_address_resolution:
            if _debug:
                BVLLServiceElement._debug("    - nothing pending")
            return

        # request is no longer pending, set the value
        future = self.virtual_address_resolution.pop(address)
        future.set_result(lpdu.pduSource)
