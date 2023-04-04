"""
Application Module
"""

from __future__ import annotations

import asyncio
import argparse
import dataclasses

from functools import partial

from typing import (
    TYPE_CHECKING,
    cast,
    Any as _Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Set,
)

from .debugging import bacpypes_debugging, DebugContents, ModuleLogger

from .comm import ApplicationServiceElement, bind
from .pdu import Address

from .apdu import (
    APDU,
    UnconfirmedRequestPDU,
    ConfirmedRequestPDU,
    SimpleAckPDU,
    ComplexAckPDU,
    ErrorPDU,
    RejectPDU,
    AbortPDU,
    Error,
)

from .errors import ExecutionError, UnrecognizedService, AbortException, RejectException

# for computing protocol services supported
from .apdu import (
    confirmed_request_types,
    unconfirmed_request_types,
    IAmRequest,
)
from .primitivedata import ObjectType, ObjectIdentifier
from .basetypes import (
    Segmentation,
    ServicesSupported,
    ProtocolLevel,
    NetworkType,
    IPMode,
    HostNPort,
    BDTEntry,
)
from .object import Object, DeviceObject, get_vendor_info

from .appservice import ApplicationServiceAccessPoint
from .netservice import (
    NetworkServiceAccessPoint,
    NetworkServiceElement,
    RouterInfoCache,
)

# basic services
from .service.device import WhoIsIAmServices, WhoHasIHaveServices
from .service.object import (
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
)
from .service.cov import ChangeOfValueServices

from .local.networkport import NetworkPortObject
from .ipv4.link import (
    NormalLinkLayer as NormalLinkLayer_ipv4,
    ForeignLinkLayer as ForeignLinkLayer_ipv4,
    BBMDLinkLayer as BBMDLinkLayer_ipv4,
)

from .local.schedule import ScheduleObject

# for serialized parameter initialization
from .json import json_to_sequence

if TYPE_CHECKING:
    # class is declared as generic in stubs but not at runtime
    APDUFuture = asyncio.Future[Optional[APDU]]
else:
    APDUFuture = asyncio.Future

# some debugging
_debug = 0
_log = ModuleLogger(globals())


#
#   DeviceInfo
#


@bacpypes_debugging
@dataclasses.dataclass
class DeviceInfo(DebugContents):
    _debug_contents = (
        "device_instance",
        "device_address",
        "max_apdu_length_accepted",
        "segmentation_supported",
        "vendor_identifier",
        "max_npdu_length",
        "max_segments_accepted",
    )

    device_instance: int
    device_address: Address
    max_apdu_length_accepted: int = 1024
    segmentation_supported: Segmentation = Segmentation.noSegmentation
    vendor_identifier: Optional[int] = None
    max_segments_accepted: Optional[int] = None
    max_npdu_length: Optional[int] = None  # See Clause 19.4


#
#   DeviceInfoCache
#


@bacpypes_debugging
class DeviceInfoCache(DebugContents):
    _debug_contents = ("address_cache++", "instance_cache++")
    _debug: Callable[..., None]

    address_cache: Dict[Address, DeviceInfo]
    instance_cache: Dict[int, DeviceInfo]

    def __init__(self, device_info_class=DeviceInfo):
        if _debug:
            DeviceInfoCache._debug("__init__")

        # a little error checking
        if not issubclass(device_info_class, DeviceInfo):
            raise ValueError("not a DeviceInfo subclass: %r" % (device_info_class,))

        # empty caches
        self.address_cache = {}
        self.instance_cache = {}

        # class for new records
        self.device_info_class = device_info_class

    async def get_device_info(self, addr: Address) -> Optional[DeviceInfo]:
        if _debug:
            DeviceInfoCache._debug("get_device_info %r", addr)

        # get the info if it's there
        device_info = self.address_cache.get(addr, None)
        if _debug:
            DeviceInfoCache._debug("    - device_info: %r", device_info)

        return device_info

    async def set_device_info(self, apdu: IAmRequest):
        """
        Create/update a device information record based on the contents of an
        IAmRequest and put it in the cache.
        """
        if _debug:
            DeviceInfoCache._debug("set_device_info %r", apdu)

        # make sure the apdu is an I-Am
        if not isinstance(apdu, IAmRequest):
            raise ValueError("not an IAmRequest: %r" % (apdu,))

        # get the primary keys
        device_address = apdu.pduSource
        device_instance = apdu.iAmDeviceIdentifier[1]

        # check for existing references
        info1 = self.address_cache.get(device_address, None)
        info2 = self.instance_cache.get(device_instance, None)

        device_info = None
        if info1 and info2 and (info1 is info2):
            device_info = info1
            if _debug:
                DeviceInfoCache._debug("    - update: %r", device_info)

        elif info1 or info2:
            log_message = f"I-Am from {device_address}, device {device_instance}:"
            if info1:
                log_message += f" was device {info1.device_instance}"
                del self.instance_cache[info1.device_instance]
            if info2:
                log_message += f" was address {info2.device_address}"
                del self.address_cache[info2.device_address]
            DeviceInfoCache._info(log_message)

        if not device_info:
            # create an entry
            device_info = self.device_info_class(device_instance, device_address)
            device_info.deviceIdentifier = device_instance
            device_info.address = device_address

            # put it in the cache, replacing possible existing instance(s)
            self.address_cache[device_address] = device_info
            self.instance_cache[device_instance] = device_info

        # update record contents
        device_info.max_apdu_length_accepted = apdu.maxAPDULengthAccepted
        device_info.segmentation_supported = apdu.segmentationSupported
        device_info.vendor_identifier = apdu.vendorID

    def update_device_info(self, device_info: DeviceInfo):
        """
        Update a device information record based on what was changed
        from the APCI information from the segmentation state
        machine.
        """
        if _debug:
            DeviceInfoCache._debug("update_device_info %r", device_info)

        # get the primary keys
        device_address = device_info.address
        device_instance = device_info.deviceIdentifier

        # check for existing references
        info1 = self.address_cache.get(device_address, None)
        info2 = self.instance_cache.get(device_instance, None)

        # if any of these references are different the cache has been
        # updated while a segmentation state machine was running, just
        # log it
        if (device_info is not info1) or (device_info is not info2):
            DeviceInfoCache._info(f"Cache update for device {device_instance}")

    def acquire(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        will be using the device information.
        """
        if _debug:
            DeviceInfoCache._debug("acquire %r", device_info)

        # reference bump
        device_info._ref_count += 1

    def release(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        has finished with the device information.
        """
        if _debug:
            DeviceInfoCache._debug("release %r", device_info)

        # this information record might be used by more than one SSM
        if device_info._ref_count == 0:
            raise RuntimeError("reference count")

        # decrement the reference count
        device_info._ref_count -= 1


#
#   Application
#


@bacpypes_debugging
class Application(
    ApplicationServiceElement,
    WhoIsIAmServices,
    WhoHasIHaveServices,
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
    ChangeOfValueServices,
):
    _debug: Callable[..., None]
    _exception: Callable[..., None]
    _startup_disabled = False

    asap: ApplicationServiceAccessPoint
    nsap: NetworkServiceAccessPoint
    nse: NetworkServiceElement

    device_object: Optional[DeviceObject] = None
    device_info_cache: DeviceInfoCache

    objectName: Dict[str, _Any]
    objectIdentifier: Dict[ObjectIdentifier, _Any]
    link_layers: Dict[ObjectIdentifier, _Any]

    next_invoke_id: int
    _requests: Dict[Address, List[Tuple[APDU, APDUFuture]]]

    def __init__(
        self, *args, device_info_cache: Optional[DeviceInfoCache] = None, **kwargs
    ):
        if _debug:
            Application._debug(
                "__init__ device_info_cache=%r %r",
                device_info_cache,
                kwargs,
            )

        # local objects by ID and name
        self.objectName = {}
        self.objectIdentifier = {}

        # references to link layer objects
        self.link_layers = {}

        # use the provided cache or make a default one
        self.device_info_cache = device_info_cache or DeviceInfoCache()

        self.next_invoke_id = 0
        self._requests = {}

        # other services
        ChangeOfValueServices.__init__(self)

    @classmethod
    def from_object_list(
        cls,
        objects: List[Object],
        device_info_cache: Optional[DeviceInfoCache] = None,
        router_info_cache: Optional[RouterInfoCache] = None,
        aseID=None,
    ) -> Application:
        """
        Create an instance of an Application given a list of objects.
        """
        if _debug:
            Application._debug(
                "from_object_list %s device_info_cache=%r aseID=%r",
                repr(objects),
                device_info_cache,
                aseID,
            )

        # find the device object
        device_object = None
        for obj in objects:
            if not isinstance(obj, DeviceObject):
                continue
            if device_object is not None:
                raise RuntimeError("duplicate device object")
            device_object = obj
        if device_object is None:
            raise RuntimeError("missing device object")

        # create a base instance
        app = cls(device_info_cache=device_info_cache, aseID=aseID)

        # a application service access point will be needed
        app.asap = ApplicationServiceAccessPoint(device_object, app.device_info_cache)

        # a network service access point will be needed
        app.nsap = NetworkServiceAccessPoint(router_info_cache=router_info_cache)

        # give the NSAP a generic network layer service element
        app.nse = NetworkServiceElement()
        bind(app.nse, app.nsap)

        # bind the top layers
        bind(app, app.asap, app.nsap)

        # add the objects
        for obj in objects:
            app.add_object(obj)

        # return the built application
        return app

    @classmethod
    def from_json(
        cls,
        objects: List[Dict[str, _Any]],
        device_info_cache: Optional[DeviceInfoCache] = None,
        router_info_cache: Optional[RouterInfoCache] = None,
        aseID=None,
    ) -> Application:
        """
        Create an instance of an Application after converting the objects
        from JSON objects to BACpypes objects.
        """
        if _debug:
            Application._debug(
                "from_json %s device_info_cache=%r aseID=%r",
                repr(objects),
                device_info_cache,
                aseID,
            )

        # first pass, look for the device object and the vendor identifier
        # to get the context to instantiate objects, continue scanning the
        # list to make sure there isn't more than one device object
        vendor_identifier = None
        for obj in objects:
            object_identifier = obj.get("object-identifier", None)
            if not object_identifier:
                raise RuntimeError("missing object identifier")
            if _debug:
                Application._debug("    - object_identifier: %r", object_identifier)

            object_type = obj.get("object-type", None)
            implicit_type = object_identifier.split(",")[0]
            if not object_type:
                object_type = implicit_type
            elif object_type != implicit_type:
                raise RuntimeError("mismatched object type")
            if _debug:
                Application._debug("    - object_type: %r", object_type)

            if object_type != "device":
                continue
            if vendor_identifier is not None:
                raise RuntimeError("multiple device objects")

            vendor_identifier = obj.get("vendor-identifier", None)
            if vendor_identifier is None:
                raise RuntimeError("missing vendor identifier")

        # should be found at this point
        if vendor_identifier is None:
            raise RuntimeError("missing vendor identifier")
        if _debug:
            Application._debug("    - vendor_identifier: %r", vendor_identifier)
        vendor_info = get_vendor_info(vendor_identifier)
        if _debug:
            Application._debug("    - vendor_info: %r", vendor_info)

        # convert the object as JSON to objects
        object_list: List[Object] = []
        for obj in objects:
            object_identifier = obj.get("object-identifier", None)
            if not object_identifier:
                raise RuntimeError("missing object identifier")

            object_type = obj.get("object-type", None)
            implicit_type = object_identifier.split(",")[0]
            if not object_type:
                object_type = implicit_type
            elif object_type != implicit_type:
                raise RuntimeError("mismatched object type")

            # using vendor info get the appropriate class for this type
            object_class = vendor_info.get_object_class(ObjectType(object_type))
            if _debug:
                Application._debug("    - object_class: %r", object_class)
            if not object_class:
                raise RuntimeError("unsupported object type: " + object_type)

            new_object = cast(Object, json_to_sequence(obj, object_class))
            if _debug:
                Application._debug("    - new_object: %r", new_object)

            object_list.append(new_object)

        # continue the build process
        return cls.from_object_list(
            object_list,
            device_info_cache=device_info_cache,
            router_info_cache=router_info_cache,
            aseID=aseID,
        )

    @classmethod
    def from_args(
        cls,
        args: argparse.Namespace,
        device_info_cache: Optional[DeviceInfoCache] = None,
        router_info_cache: Optional[RouterInfoCache] = None,
        aseID=None,
    ) -> Application:
        if _debug:
            Application._debug(
                "from_args %r %r device_info_cache=%r aseID=%r",
                cls,
                args,
                device_info_cache,
                aseID,
            )

        # get the vendor info for the provided identifier
        vendor_info = get_vendor_info(args.vendoridentifier)
        if not vendor_info:
            raise RuntimeError(f"missing vendor info: {args.vendoridentifier}")

        # get the device object class and make an instance
        device_object_class = vendor_info.get_object_class(ObjectType.device)
        if not device_object_class:
            raise RuntimeError(
                f"vendor indentifier {args.vendoridentifier} missing device object class"
            )
        if _debug:
            Application._debug("    - device_object_class: %r", device_object_class)
        device_object = device_object_class(
            objectIdentifier=("device", int(args.instance)), objectName=args.name
        )
        if _debug:
            Application._debug("    - device_object: %r", device_object)

        # get the network port object class and make an instance
        network_port_object_class = vendor_info.get_object_class(ObjectType.networkPort)
        if not network_port_object_class:
            raise RuntimeError(
                f"vendor indentifier {args.vendoridentifier} missing network port object class"
            )
        if _debug:
            Application._debug(
                "    - network_port_object_class: %r", network_port_object_class
            )

        # default address is 'host' or 'host:0' for a foreign device
        address = args.address
        if not address:
            address = "host:0" if args.foreign else "host"

        # make a network port object
        network_port_object = network_port_object_class(
            address,
            objectIdentifier=("network-port", 1),
            objectName="NetworkPort-1",
            networkNumber=args.network,
            networkNumberQuality="configured" if args.network else "unknown",
        )
        if _debug:
            Application._debug("    - network_port_object: %r", network_port_object)

        # maybe this is a foreign device
        if args.foreign is not None:
            network_port_object.bacnetIPMode = IPMode.foreign
            network_port_object.fdBBMDAddress = HostNPort(args.foreign)
            network_port_object.fdSubscriptionLifetime = args.ttl

        # maybe this is a BBMD
        if args.bbmd is not None:
            network_port_object.bacnetIPMode = IPMode.bbmd
            network_port_object.bbmdAcceptFDRegistrations = True  # Boolean
            network_port_object.bbmdForeignDeviceTable = []  # ListOf(FDTEntry)

            # populate the BDT
            bdt = []
            for addr in args.bbmd:
                bdt_entry = BDTEntry(addr)
                if _debug:
                    Application._debug("    - bdt_entry: %r", bdt_entry)
                bdt.append(bdt_entry)
            network_port_object.bbmdBroadcastDistributionTable = bdt

        # continue the build process
        return cls.from_object_list(
            [device_object, network_port_object],
            device_info_cache=device_info_cache,
            router_info_cache=router_info_cache,
            aseID=aseID,
        )

    # -----

    def add_object(self, obj):
        """Add an object to the application."""
        if _debug:
            Application._debug("add_object %r", obj)

        # extract the object name and identifier
        object_name = obj.objectName
        if not object_name:
            raise RuntimeError("object name required")
        object_identifier = obj.objectIdentifier
        if not object_identifier:
            raise RuntimeError("object identifier required")

        # make sure it hasn't already been defined
        if object_name in self.objectName:
            raise RuntimeError("already an object with name %r" % (object_name,))
        if object_identifier in self.objectIdentifier:
            raise RuntimeError(
                "already an object with identifier %r" % (object_identifier,)
            )

        # now put it in local dictionaries
        self.objectName[object_name] = obj
        self.objectIdentifier[object_identifier] = obj

        # let the object know which application it belongs to
        obj._app = self

        # if this is the device object, save a reference to it
        if isinstance(obj, DeviceObject):
            if self.device_object:
                raise RuntimeError("existing device object %r", (self.device_object,))
            self.device_object = obj

        if isinstance(obj, NetworkPortObject):
            if obj.protocolLevel != ProtocolLevel.bacnetApplication:
                pass
            elif obj.networkType == NetworkType.ipv4:
                link_address = obj.address
                if _debug:
                    Application._debug("     - link_address: %r", link_address)

                if obj.bacnetIPMode == IPMode.normal:
                    link_layer = NormalLinkLayer_ipv4(link_address)
                    if _debug:
                        Application._debug("     - link_layer: %r", link_layer)

                elif obj.bacnetIPMode == IPMode.foreign:
                    link_layer = ForeignLinkLayer_ipv4(link_address)
                    if _debug:
                        Application._debug("     - link_layer: %r", link_layer)

                    # start the registration process
                    link_layer.register(
                        obj.fdBBMDAddress.address, obj.fdSubscriptionLifetime
                    )

                elif obj.bacnetIPMode == IPMode.bbmd:
                    link_layer = BBMDLinkLayer_ipv4(link_address)
                    if _debug:
                        Application._debug("     - link_layer: %r", link_layer)

                    for bdt_entry in obj.bbmdBroadcastDistributionTable:
                        if _debug:
                            Application._debug("     - bdt_entry: %r", bdt_entry)

                        link_layer.add_peer(bdt_entry.address)

                else:
                    raise NotImplementedError(f"{obj.bacnetIPMode}")

                # capture the bound address before sending stuff
                # link_layer.server._transport_tasks.append(
                #     asyncio.create_task(self.capture_bound_address(obj, link_layer))
                # )

                # save a reference from the object to the link layer, maybe
                # this will be deleted (in which case it will be closed)
                self.link_layers[obj.objectIdentifier] = link_layer

                # let the NSAP know about this link layer
                if obj.networkNumber == 0:
                    self.nsap.bind(link_layer, address=link_address)
                else:
                    self.nsap.bind(
                        link_layer, net=obj.networkNumber, address=link_address
                    )

            elif obj.networkType == NetworkType.ipv6:
                raise NotImplementedError("IPv6")

            else:
                raise NotImplementedError(f"{obj.networkType}")

        # if this is a schedule object interpret it which will also schedule it
        # to be interpreted again at the next transition
        if isinstance(obj, ScheduleObject):
            obj.interpret_schedule()

    # async def capture_bound_address(self, network_port_object, link_layer):
    #     if _debug:
    #         Application._debug("capture_bound_address %r %r", network_port_object, link_layer)
    #
    #     print(f"\n>>> {link_layer.server = } {dir(link_layer.server)}\n")

    def delete_object(self, obj):
        """Add an object to the local collection."""
        if _debug:
            Application._debug("delete_object %r", obj)

        # if this is the device object clear out the reference
        if obj is self.device_object:
            raise RuntimeError("do not delete the device object")

        # extract the object name and identifier
        object_name = obj.objectName
        object_identifier = obj.objectIdentifier

        # delete it from the application
        del self.objectName[object_name]
        del self.objectIdentifier[object_identifier]

        # let the object knows it's no longer associated with an application
        obj._app = None

        if isinstance(obj, NetworkPortObject):
            link_layer = self.link_layers.get(obj.objectIdentifier, None)
            if _debug:
                Application._debug("     - link_layer: %r", link_layer)
            if link_layer:
                link_layer.close()
                del self.link_layers.get[obj.objectIdentifier]

    def get_object_id(self, objid):
        """Return a local object or None."""
        return self.objectIdentifier.get(objid, None)

    def get_object_name(self, objname):
        """Return a local object or None."""
        return self.objectName.get(objname, None)

    def iter_objects(self):
        """Iterate over the objects."""
        return iter(self.objectIdentifier.values())

    # -----

    def get_services_supported(self):
        """Return a ServicesSupported bit string based in introspection, look
        for helper methods that match confirmed and unconfirmed services."""
        if _debug:
            Application._debug("get_services_supported")

        services_supported = ServicesSupported([])

        # look through the confirmed services
        for service_choice, service_request_class in confirmed_request_types.items():
            service_helper = "do_" + service_request_class.__name__
            if hasattr(self, service_helper):
                services_supported[service_choice] = 1

        # look through the unconfirmed services
        for service_choice, service_request_class in unconfirmed_request_types.items():
            service_helper = "do_" + service_request_class.__name__
            if hasattr(self, service_helper):
                services_supported[service_choice] = 1

        # return the bit list
        return services_supported

    # -----

    def close(self):
        """
        Close the applications link layer objects.
        """
        if _debug:
            Application._debug("close")

        for link_layer in self.link_layers.values():
            if _debug:
                Application._debug("    - link_layer: %r", link_layer)
            link_layer.close()

    # -----

    def request(self, apdu: APDU) -> APDUFuture:  # type: ignore[override]
        """
        This function is called by a subclass of Application when it has a
        confirmed or unconfirmed request to send.  It returns a future that
        will have the acknowledgement/error/reject/abort set as the result.

        If the APDU does not have an invoke ID set it will be assigned one, and
        it will be reassigned to a new one if there is already an outstanding
        request with the same one.

        There is no throttling of the number of outstanding requests.
        """
        if _debug:
            Application._debug("request %r", apdu)

        # create a future
        future = APDUFuture()
        if isinstance(apdu, UnconfirmedRequestPDU):
            future.set_result(None)

        elif isinstance(apdu, ConfirmedRequestPDU):
            pdu_destination = apdu.pduDestination
            assert pdu_destination

            # make sure the invoke ID is set
            if apdu.apduInvokeID is None:
                apdu.apduInvokeID = self.next_invoke_id
                self.next_invoke_id = (self.next_invoke_id + 1) % 256

            # check to see if there are any requests for this destination
            if pdu_destination in self._requests:
                # make sure the invoke ID isn't already being used
                used_invoke_ids: Set[int] = set(
                    pdu.apduInvokeID for pdu, fut in self._requests[pdu_destination]
                )
                while apdu.apduInvokeID in used_invoke_ids:
                    apdu.apduInvokeID = self.next_invoke_id
                    self.next_invoke_id = (self.next_invoke_id + 1) % 256

                self._requests[pdu_destination].append((apdu, future))
            else:
                self._requests[pdu_destination] = [(apdu, future)]
            if _debug:
                Application._debug("    - _requests: %r", self._requests)

            # add a callback in case the request is canceled (timeout)
            future.add_done_callback(partial(self._request_done, apdu))
        else:
            raise TypeError("APDU expected")

        # create a task to send it
        asyncio.create_task(ApplicationServiceElement.request(self, apdu))

        return future

    def _request_done(self, apdu, future) -> None:
        """
        This function is called when the future that was created for sending
        a confirmed service request is completed or canceled.
        """
        if _debug:
            Application._debug("_request_done %r %r", apdu, future)

        # the apdu is a reference to the original request
        pdu_destination = apdu.pduDestination

        # check to see if there are any requests for this destination
        if pdu_destination not in self._requests:
            if _debug:
                Application._debug("    - not in _requests")
            return

        # find the apdu in the list
        requests = self._requests[pdu_destination]
        for indx, (pdu, fut) in enumerate(requests):
            if apdu is pdu:
                del requests[indx]
                break
        else:
            if _debug:
                Application._debug("    - not in _requests for source")
            return

        # see if the list is empty
        if not requests:
            del self._requests[pdu_destination]
        if _debug:
            Application._debug("    - removed from _requests")

    async def indication(self, apdu) -> None:  # type: ignore[override]
        """
        This function is called when the application service element has
        an incoming request that should be processed by the application.
        """
        if _debug:
            Application._debug("indication %r", apdu)

        # get a helper function
        helperName = "do_" + apdu.__class__.__name__
        helperFn = getattr(self, helperName, None)
        if _debug:
            Application._debug("    - helperFn: %r", helperFn)

        error_pdu: Optional[APDU] = None
        try:
            if not helperFn:
                if isinstance(apdu, ConfirmedRequestPDU):
                    raise UnrecognizedService("no function %s" % (helperName,))
                return

            # pass the apdu on to the helper function
            await helperFn(apdu)
        except RejectException as err:
            if _debug:
                Application._debug("    - reject exception: %r", err)
            error_pdu = RejectPDU(reason=err.rejectReason, context=apdu)

        except AbortException as err:
            if _debug:
                Application._debug("    - abort exception: %r", err)
            error_pdu = AbortPDU(reason=err.abortReason, context=apdu)

        except ExecutionError as err:
            if _debug:
                Application._debug("    - execution error: %r", err)
            error_pdu = Error(
                service_choice=apdu.apduService,
                errorClass=err.errorClass,
                errorCode=err.errorCode,
                context=apdu,
            )

        except Exception as err:
            Application._exception("exception: %r", err)
            error_pdu = Error(
                service_choice=apdu.apduService,
                errorClass="device",
                errorCode="operationalProblem",
                context=apdu,
            )

        if error_pdu and isinstance(apdu, ConfirmedRequestPDU):
            if _debug:
                Application._debug("    - error_pdu: %r", error_pdu)
            await self.response(error_pdu)

    async def response(self, apdu: APDU) -> None:  # type: ignore[override]
        """This function is called by the application when it has a response to
        an incoming confirmed service."""
        if _debug:
            Application._debug("response %r", apdu)

        # double check the input is the right kind of APDU
        if not isinstance(
            apdu,
            (
                SimpleAckPDU,
                ComplexAckPDU,
                ErrorPDU,
                RejectPDU,
                AbortPDU,
            ),
        ):
            raise TypeError("apdu")

        # this is an ack, error, reject or abort
        await ApplicationServiceElement.response(self, apdu)

    async def confirmation(self, apdu: APDU) -> None:  # type: ignore[override]
        """This function is called when application is receiving the response
        from sending a confirmed service request."""
        if _debug:
            Application._debug("confirmation %r", apdu)
        assert apdu.pduSource

        # check to see if there are any requests for this address
        pdu_source = apdu.pduSource
        if pdu_source not in self._requests:
            if _debug:
                Application._debug("   - no requests")
            return

        # look for a matching invoke ID
        requests = self._requests[pdu_source]
        for indx, (request, future) in enumerate(requests):
            if request.apduInvokeID == apdu.apduInvokeID:
                break
        else:
            if _debug:
                Application._debug("   - no match")
            return
        if _debug:
            Application._debug("   - match: %s %s", str(request), str(future))

        if isinstance(apdu, (SimpleAckPDU, ComplexAckPDU)):
            # set the future value
            future.set_result(apdu)
        elif isinstance(apdu, (ErrorPDU, RejectPDU, AbortPDU)):
            # set the future exception
            future.set_exception(apdu)
        else:
            raise TypeError("apdu")
