"""
Batch Read
"""

from __future__ import annotations

import asyncio

from dataclasses import dataclass
from functools import partial

from typing import Any, Callable, Dict, DefaultDict, List, Optional, Union

from ..debugging import bacpypes_debugging, ModuleLogger

from ..pdu import Address
from ..primitivedata import ObjectIdentifier
from ..basetypes import (
    ObjectType,
    PropertyIdentifier,
    PropertyReference,
    ServicesSupported,
)
from ..apdu import ErrorRejectAbortNack
from ..app import Application


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@dataclass(eq=True, order=True, frozen=True)
class DeviceAddressObjectPropertyReference:
    """
    Instances of this class are a request for the value of a property of an
    object associated with a "key".  When the results are read, the callback
    function is given the key and the value that was read.
    """

    key: Any
    deviceAddress: Address
    objectIdentifier: ObjectIdentifier
    propertyReference: PropertyReference

    def __init__(
        self,
        key: Any,
        device_address: Any,
        object_identifier: Any,
        property_reference: Any,
    ) -> None:
        object.__setattr__(
            self,
            "key",
            key,
        )
        object.__setattr__(
            self,
            "deviceAddress",
            device_address
            if isinstance(device_address, Address)
            else Address(device_address),
        )
        object.__setattr__(
            self,
            "objectIdentifier",
            object_identifier
            if isinstance(object_identifier, ObjectIdentifier)
            else ObjectIdentifier(object_identifier),
        )
        object.__setattr__(
            self,
            "propertyReference",
            property_reference
            if isinstance(property_reference, PropertyReference)
            else PropertyReference(property_reference),
        )

    def __repr__(self) -> str:
        s = (
            "<"
            f"DeviceAddressObjectPropertyReference {self.key}: "
            f"{self.deviceAddress}/{self.objectIdentifier}/{self.propertyReference}"
            ">"
        )
        return s


DeviceAddressObjectPropertyReferenceList = List[DeviceAddressObjectPropertyReference]

AddressGroupDefaultDict = DefaultDict[Address, DeviceAddressObjectPropertyReferenceList]


class AddressGroup(AddressGroupDefaultDict):
    """
    An address bucket is a mapping between an address and all of the references
    that are being requested.
    """

    def __init__(
        self,
        arg: Dict[Address, List[DeviceAddressObjectPropertyReference]] = {},
        **kwargs: Any,
    ) -> None:
        super().__init__(list, arg, **kwargs)


NetworkGroupDefaultDict = DefaultDict[Optional[int], AddressGroup]


class NetworkGroup(NetworkGroupDefaultDict):
    """
    A network bucket is a mapping between a BACnet network and an address
    bucket.
    """

    def __init__(
        self, arg: Dict[Optional[int], AddressGroup] = {}, **kwargs: Any
    ) -> None:
        super().__init__(AddressGroup, arg, **kwargs)


@bacpypes_debugging
class AddressGroupWorker:
    """
    A worker is responsible for take the list of requests for a specific
    BACnet address and read them as a group (if Read Property Multiple is
    supported) or individually.
    """

    _debug: Callable[..., None]

    def __init__(
        self, address: Address, daopr_list: DeviceAddressObjectPropertyReferenceList
    ) -> None:
        """
        An AddressGroupWorker is associated with an AddressGroup to read
        the references.
        """
        if _debug:
            AddressGroupWorker._debug("__init__ %r ...", address)

        # save the address for debugging
        self.address = address

        # filter the list into just those for this BACnet address
        self.daopr_list = [
            daopr for daopr in daopr_list if daopr.deviceAddress == address
        ]

        # sort them by object identifier
        self.daopr_list.sort(key=lambda daopr: daopr.objectIdentifier)

    async def run(self, batch: BatchRead) -> None:
        if _debug:
            AddressGroupWorker._debug("run(%s)", self.address)

        # get the device information from the cache
        device_info = await batch.app.device_info_cache.get_device_info(self.address)
        if _debug:
            AddressGroupWorker._debug("    - device_info: %r", device_info)

        if not device_info:
            # send it a Who-Is and see if anything comes back
            i_ams = await batch.app.who_is(address=self.address)
            if _debug:
                AddressGroupWorker._debug("    - i_ams: %r", i_ams)
            if not i_ams:
                if batch.callback:
                    for daopr in self.daopr_list:
                        batch.callback(daopr.key, RuntimeError("no response"))
                return
            if len(i_ams) > 1:
                if _debug:
                    AddressGroupWorker._debug("    - yikes!")

            # stuff this in the cache
            device_info = await batch.app.device_info_cache.set_device_info(i_ams[0])

        # see if protocol-services-supported is cached
        if device_info.protocol_services_supported is None:
            try:
                pss = await batch.app.read_property(
                    self.address,
                    ObjectIdentifier((ObjectType.device, device_info.device_instance)),
                    "protocol-services-supported",
                )
                if _debug:
                    AddressGroupWorker._debug("    - pss: %r", pss)

                # ### needs to push updated device_info back into cache
                device_info.protocol_services_supported = pss
            except ErrorRejectAbortNack as err:
                if _debug:
                    AddressGroupWorker._debug("    - err: %r", err)
                device_info.protocol_services_supported = ServicesSupported([])

        if _debug:
            AddressGroupWorker._debug("    - device_info: %r", device_info)

        # try to use RPM if its available
        if device_info.protocol_services_supported["read-property-multiple"]:
            await self.read_property_multiple(batch)
        else:
            await self.read_property(batch)

    async def read_property(self, batch: BatchRead) -> None:
        if _debug:
            AddressGroupWorker._debug("read_property(%s)", self.address)

        # get the running loop to create tasks
        loop = asyncio.get_running_loop()

        for daopr in self.daopr_list:
            if batch._stop.is_set():
                if _debug:
                    AddressGroupWorker._debug("    - all stop")
                break

            # task to read the value
            read_task = loop.create_task(
                batch.app.read_property(  # type: ignore[union-attr]
                    daopr.deviceAddress,
                    daopr.objectIdentifier,
                    daopr.propertyReference.propertyIdentifier,
                    daopr.propertyReference.propertyArrayIndex,
                ),
                name=f"reading {daopr.key}",
            )
            read_task.add_done_callback(
                partial(batch._read_property_callback, daopr.key)
            )

            # task for the batch being stopped
            stop_wait = loop.create_task(batch._stop.wait(), name="stop wait")

            # wait for one of them to complete
            done, pending = await asyncio.wait(
                {read_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
            )

            # cancel the pending task(s)
            for task in pending:
                task.cancel()
            if _debug:
                AddressGroupWorker._debug("    - %r finished", daopr)
        if _debug:
            AddressGroupWorker._debug("    - finished(%s)", self.address)

    async def read_property_multiple(self, batch: BatchRead) -> None:
        if _debug:
            AddressGroupWorker._debug("read_property_multiple(%s)", self.address)

        # get the running loop to create tasks
        loop = asyncio.get_running_loop()

        ### calc based on device_info.max_apdu_length_accepted // 10
        chunk_size = 10

        i = 0
        while i < len(self.daopr_list):
            chunk = self.daopr_list[i:i+chunk_size]
            if _debug:
                AddressGroupWorker._debug("    - chunk: %r", chunk)
            i += chunk_size

            objid = None
            key_list = []
            parameter_list = []
            for daopr in chunk:
                if daopr.objectIdentifier != objid:
                    objid = daopr.objectIdentifier
                    property_reference_list = []
                    parameter_list.extend([objid, property_reference_list])

                key_list.append(daopr.key)
                property_reference_list.append(daopr.propertyReference)
            if _debug:
                AddressGroupWorker._debug("    - parameter_list: %r", parameter_list)

            # task to read the values
            read_task = loop.create_task(
                batch.app.read_property_multiple(  # type: ignore[union-attr]
                    self.address,
                    parameter_list,
                ),
                name=f"reading {key_list}",
            )
            read_task.add_done_callback(
                partial(batch._read_property_multiple_callback, key_list)
            )

            # task for the batch being stopped
            stop_wait = loop.create_task(batch._stop.wait(), name="stop wait")

            # wait for one of them to complete
            done, pending = await asyncio.wait(
                {read_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
            )

            # cancel the pending task(s)
            for task in pending:
                task.cancel()
            if _debug:
                AddressGroupWorker._debug("    - finished")
        if _debug:
            AddressGroupWorker._debug("    - finished(%s)", self.address)


@bacpypes_debugging
class NetworkGroupWorker:
    """
    A NetworkGroupWorker is responsible for running AddressGroupWorker
    instances sequentially for all of the addresses on its network.
    """

    _debug: Callable[..., None]

    def __init__(self, network: Union[int, None], address_group: AddressGroup) -> None:
        if _debug:
            NetworkGroupWorker._debug("__init__ ... %r ...", network)

        # save the network for debugging
        self.network = network

        # make a worker for each address
        self.address_worker_list = []
        for address, daopr_list in address_group.items():
            self.address_worker_list.append(AddressGroupWorker(address, daopr_list))

    async def run(self, batch: BatchRead) -> None:
        if _debug:
            NetworkGroupWorker._debug("run(%s)", self.network)

        # give each address on the network a turn in reading
        for address_worker in self.address_worker_list:
            if batch._stop.is_set():
                if _debug:
                    NetworkGroupWorker._debug("    - all stop")
                break

            await address_worker.run(batch)
        if _debug:
            NetworkGroupWorker._debug("    - finished(%s)", self.network)


CallbackFn = Callable[[Any, Any], None]


@bacpypes_debugging
class BatchRead:
    """
    Given a list of references to the properties of objects in some devices,
    read the values of the properties and pass the results to a callback
    function.
    """

    _debug: Callable[..., None]

    app: Optional[Application]
    fini: Optional[asyncio.Event]
    callback: Optional[CallbackFn]

    def __init__(self, daopr_list: DeviceAddressObjectPropertyReferenceList) -> None:
        if _debug:
            BatchRead._debug("__init__ ...")

        # filter the samples into buckets
        self.network_group = NetworkGroup()
        for daopr in daopr_list:
            if daopr.propertyReference.propertyIdentifier in (
                PropertyIdentifier.all,
                PropertyIdentifier.required,
                PropertyIdentifier.optional,
            ):
                raise ValueError(f"simple property references only, key={daopr.key}")
            self.network_group[daopr.deviceAddress.addrNet][daopr.deviceAddress].append(
                daopr
            )

        # no application or done event until we run
        self.app = None
        self.fini = None
        self.callback = None

    async def run(
        self, app: Application, callback: Optional[CallbackFn] = None
    ) -> None:
        """
        Read the contents of the buckets.
        """
        if _debug:
            BatchRead._debug("__init__ %r", app)

        # save a reference to the application and callback
        self.app = app
        self.callback = callback

        # set when process must stop, fini when it's done
        self._stop = asyncio.Event()
        self.fini = asyncio.Event()

        # create a set of network workers
        network_task_set = set()
        for network, address_group in self.network_group.items():
            network_worker = NetworkGroupWorker(network, address_group)
            network_worker_task = asyncio.create_task(
                network_worker.run(self), name=f"Network {network}"
            )
            if _debug:
                BatchRead._debug("    - network_worker_task: %r", network_worker_task)
            network_task_set.add(network_worker_task)

        # wait for them all to complete
        done, pending = await asyncio.wait(network_task_set)
        if _debug:
            BatchRead._debug("    - done: %r", done)
            BatchRead._debug("    - pending: %r", pending)

        # set the event we are done
        self.fini.set()

    def _read_property_callback(self, key: Any, task: Any) -> None:
        if _debug:
            BatchRead._debug("_read_property_callback %r %r", key, task)
        if not self.callback:
            return

        # if the task is canceled use None
        if task.cancelled():
            self.callback(key, None)
            return

        # get the exception or result from the task
        value = task.exception() or task.result()
        if _debug:
            BatchRead._debug("    - key, value: %r, %r", key, value)

        # pass the value back to the run() caller
        self.callback(key, value)

    def _read_property_multiple_callback(self, key_list: List[Any], task: Any) -> None:
        if _debug:
            BatchRead._debug("_read_property_multiple_callback %r %r", key_list, task)
        if not self.callback:
            return

        # if the task is canceled use None
        if task.cancelled():
            for key in key_list:
                self.callback(key, None)
            return

        exception = task.exception()
        if exception:
            if _debug:
                BatchRead._debug("    - exception: %r", exception)
            for key in key_list:
                self.callback(key, exception)
        else:
            result = task.result()
            if _debug:
                BatchRead._debug("    - result: %r", result)

            # dump out the results
            for key, (
                object_identifier,
                property_identifier,
                property_array_index,
                property_value,
            ) in zip(key_list, result):
                if _debug:
                    BatchRead._debug("    - key, value: %r, %r", key, property_value)
                self.callback(key, property_value)

    def stop(self):
        """
        Called when the batch reading process should cancel all of its
        incomplete tasks and skip reading any more, stopping as soon as
        possible.
        """
        self._stop.set()
