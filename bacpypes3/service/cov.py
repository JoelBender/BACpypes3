"""
Change Of Value Services
"""
from __future__ import annotations

import asyncio
from functools import partial

from typing import (
    Any as _Any,
    Callable,
    Optional,
    Tuple,
)

from ..settings import settings
from ..debugging import bacpypes_debugging, DebugContents, ModuleLogger

from ..pdu import Address

from ..errors import (
    DecodingError,
    ExecutionError,
    ServicesError,
)
from ..primitivedata import Unsigned, ObjectIdentifier
from ..constructeddata import Array
from ..basetypes import PropertyIdentifier, PropertyValue
from ..apdu import (
    SimpleAckPDU,
    ErrorRejectAbortNack,
    SubscribeCOVRequest,
    ConfirmedCOVNotificationRequest,
    UnconfirmedCOVNotificationRequest,
)
from ..object import get_vendor_info

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class SubscriptionContextManager:
    _debug: Callable[..., None]

    app: "Application"  # noqa: F821
    address: Address
    monitored_object_identifier: ObjectIdentifier
    subscriber_process_identifier: int
    issue_confirmed_notifications: bool
    lifetime: int

    def __init__(
        self,
        app: "Application",  # noqa: F821
        address: Address,
        monitored_object_identifier: ObjectIdentifier,
        subscriber_process_identifier: int,
        issue_confirmed_notifications: bool,
        lifetime: int,
    ):
        if _debug:
            SubscriptionContextManager._debug("__init__ ...")

        # reference to the application for sending requests
        self.app = app

        # keep a copy of the request parameters
        self.address = address
        self.monitored_object_identifier = monitored_object_identifier
        self.subscriber_process_identifier = subscriber_process_identifier
        self.issue_confirmed_notifications = issue_confirmed_notifications
        self.lifetime = lifetime

        # queue of PropertyValue returned
        self.queue = asyncio.Queue()

        # timer handle to refresh the subscription
        self.refresh_subscription_handle = None

    async def __aenter__(self) -> SubscriptionContextManager:
        if _debug:
            SubscriptionContextManager._debug("__aenter__")

        # kick off the subscription
        await self.refresh_subscription()

        # save this in the app
        scm_key = (self.address, self.subscriber_process_identifier)
        if scm_key in self.app._cov_contexts:
            raise ValueError("existing context")
        self.app._cov_contexts[scm_key] = self

        return self

    async def __aexit__(self, *exc_details):
        """
        Exiting the context, cancel the subscription.
        """
        if _debug:
            SubscriptionContextManager._debug("__aexit__ %r", exc_details)

        # cancel the refresh
        if self.refresh_subscription_handle:
            if _debug:
                SubscriptionContextManager._debug("    - cancel refresh")
            self.refresh_subscription_handle.cancel()

        # delete the reference to this context
        del self.app._cov_contexts[(self.address, self.subscriber_process_identifier)]

        if exc_details != (None, None, None):
            if _debug:
                SubscriptionContextManager._debug("    - abandon context")
            return

        # create a request to cancel the subscription
        unsubscribe_cov_request = SubscribeCOVRequest(
            subscriberProcessIdentifier=self.subscriber_process_identifier,
            monitoredObjectIdentifier=self.monitored_object_identifier,
            destination=self.address,
        )

        # send the request, wait for the response
        response = await self.app.request(unsubscribe_cov_request)
        if _debug:
            SubscriptionContextManager._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                SubscriptionContextManager._debug(
                    "    - error/reject/abort: %r", response
                )

    async def refresh_subscription(self):
        """
        Send a subscription request.
        """
        if _debug:
            SubscriptionContextManager._debug("refresh_subscription")

        # create a request
        subscribe_cov_request = SubscribeCOVRequest(
            subscriberProcessIdentifier=self.subscriber_process_identifier,
            monitoredObjectIdentifier=self.monitored_object_identifier,
            issueConfirmedNotifications=self.issue_confirmed_notifications,
            lifetime=self.lifetime,
            destination=self.address,
        )
        if _debug:
            SubscriptionContextManager._debug(
                "    - subscribe_cov_request: %r", subscribe_cov_request
            )

        # send the request, wait for the response
        response = await self.app.request(subscribe_cov_request)
        if _debug:
            SubscriptionContextManager._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                SubscriptionContextManager._debug(
                    "    - error/reject/abort: %r", response
                )
            raise response

        # check for infinite lifetime
        if self.lifetime == 0:
            if _debug:
                SubscriptionContextManager._debug("    - infinite lifetime")
            return

        # get the loop to schedule a time to refresh
        loop = asyncio.get_event_loop()
        if _debug:
            SubscriptionContextManager._debug("    - loop time: %r", loop.time())

        # refresh time before it expires
        self.refresh_subscription_handle = loop.call_later(
            max(1.0, self.lifetime - 2.0), self.create_refresh_task
        )
        if _debug:
            SubscriptionContextManager._debug(
                "    - refresh_subscription_handle: %r",
                self.refresh_subscription_handle,
            )

        return

    def create_refresh_task(self):
        """
        Create a refresh task.  The `loop.call_later()` function does
        not take a coroutine so this function creates a task wrapping
        the `refresh_subscription()` coroutine.
        """
        if _debug:
            SubscriptionContextManager._debug("create_refresh_task")

        self.refresh_subscription_task = asyncio.create_task(
            self.refresh_subscription()
        )

    async def put(self, property_value: PropertyValue) -> None:
        """
        Add a property value to that has been received from a notification
        to the queue."""
        if _debug:
            SubscriptionContextManager._debug("put %r", property_value)

        await self.queue.put(property_value)

    async def get(self) -> PropertyValue:
        """
        Get the next property value from the queue or wait until one
        is available.  See `get_value()` for a specialized version.
        """
        if _debug:
            SubscriptionContextManager._debug("get")

        return await self.queue.get()

    async def get_value(self) -> Tuple[PropertyIdentifier, _Any]:
        """
        Get the next property value from the queue and interpret the
        propertyValue element to simplify the result.  Note that this
        will drop the property-index and priority elements after the
        interpretation.
        """
        if _debug:
            SubscriptionContextManager._debug("get_value")

        # get the next thing in the queue
        property_value_element = await self.get()

        # get information about the device from the application cache
        device_info = await self.app.device_info_cache.get_device_info(self.address)
        if _debug:
            SubscriptionContextManager._debug("    - device_info: %r", device_info)

        # using the device info, look up the vendor information
        if device_info:
            vendor_info = get_vendor_info(device_info.vendor_identifier)
        else:
            vendor_info = get_vendor_info(0)
        if _debug:
            SubscriptionContextManager._debug(
                "    - vendor_info (%d): %r", vendor_info.vendor_identifier, vendor_info
            )

        # using the vendor information, look up the class
        object_class = vendor_info.get_object_class(self.monitored_object_identifier[0])
        if not object_class:
            return (
                property_value_element.propertyIdentifier,
                DecodingError(
                    f"no object class: {self.monitored_object_identifier[0]}"
                ),
            )

        # now get the property type from the class
        property_type = object_class.get_property_type(
            property_value_element.propertyIdentifier
        )
        if _debug:
            SubscriptionContextManager._debug("    - property_type: %r", property_type)
        if not property_type:
            return (
                property_value_element.propertyIdentifier,
                DecodingError(
                    f"no property type: {property_value_element.propertyIdentifier}"
                ),
            )

        # filter the array index reference
        if issubclass(property_type, Array):
            if property_value_element.propertyArrayIndex is None:
                pass
            elif property_value_element.propertyArrayIndex == 0:
                property_type = Unsigned
            else:
                property_type = property_type._subtype
            if _debug:
                SubscriptionContextManager._debug(
                    "    - other property_type: %r", property_type
                )

        # cast it out of the Any
        property_value = property_value_element.value.cast_out(property_type)
        if _debug:
            SubscriptionContextManager._debug(
                "    - property_value: %r %r", property_value, property_type.__class__
            )

        return (property_value_element.propertyIdentifier, property_value)


#
#   Subscription
#


@bacpypes_debugging
class Subscription(DebugContents):
    _debug_contents = (
        "obj_ref",
        "client_addr",
        "proc_id",
        "obj_id",
        "confirmed",
        "lifetime",
    )

    cancel_handle: Optional[asyncio.TimerHandle]

    def __init__(
        self, obj_ref, client_addr, proc_id, obj_id, confirmed, lifetime, cov_inc
    ):
        if _debug:
            Subscription._debug(
                "__init__ %r %r %r %r %r %r %r",
                obj_ref,
                client_addr,
                proc_id,
                obj_id,
                confirmed,
                lifetime,
                cov_inc,
            )
        # save the reference to the related object
        self.obj_ref = obj_ref

        # save the parameters
        self.client_addr = client_addr
        self.proc_id = proc_id
        self.obj_id = obj_id
        self.confirmed = confirmed
        self.lifetime = lifetime
        self.covIncrement = cov_inc

        # if lifetime is zero this is a permanent subscription
        if lifetime > 0:
            loop = asyncio.get_running_loop()
            self.cancel_handle = loop.call_later(
                lifetime, self.obj_ref._app.cancel_subscription, self
            )
        else:
            self.cancel_handle = None

    def cancel_subscription(self):
        if _debug:
            Subscription._debug("cancel_subscription")

        # if this is scheduled to call later, cancel it
        if self.cancel_handle:
            self.cancel_handle.cancel()
            self.cancel_handle = None

        # break the object reference
        self.obj_ref = None

    def renew_subscription(self, lifetime):
        if _debug:
            Subscription._debug("renew_subscription %r", lifetime)

        # if this is scheduled to call later, cancel it
        if self.cancel_handle:
            self.cancel_handle.cancel()
            self.cancel_handle = None

        # save the new lifetime
        self.lifetime = lifetime

        # reschedule a cancel if it's not infinite
        if lifetime > 0:
            loop = asyncio.get_running_loop()
            self.cancel_handle = loop.call_later(
                lifetime, self.obj_ref._app.cancel_subscription, self
            )


#
#   Change Of Value
#


@bacpypes_debugging
class ChangeOfValueServices:
    def __init__(self):
        if _debug:
            ChangeOfValueServices._debug("__init__")

        self._cov_next_id = 1
        self._cov_contexts = {}
        self._cov_detections = {}

    # -----

    def change_of_value(
        self,
        address: Address,
        monitored_object_identifier: ObjectIdentifier,
        subscriber_process_identifier: Optional[int] = None,
        issue_confirmed_notifications: Optional[bool] = True,
        lifetime: Optional[int] = None,
    ) -> SubscriptionContextManager:
        """
        Create and return an async subscription context manager.
        """
        if _debug:
            ChangeOfValueServices._debug(
                "change_of_value %r %r %r %r %r",
                address,
                monitored_object_identifier,
                subscriber_process_identifier,
                issue_confirmed_notifications,
                lifetime,
            )

        if subscriber_process_identifier is None:
            while True:
                subscriber_process_identifier = self._cov_next_id
                self._cov_next_id = (self._cov_next_id + 1) % (1 << 22)
                if (address, subscriber_process_identifier) not in self._cov_contexts:
                    break
            if _debug:
                ChangeOfValueServices._debug(
                    "    - subscriber_process_identifier: %r",
                    subscriber_process_identifier,
                )

        if lifetime is None:
            lifetime = settings.cov_lifetime
            if _debug:
                ChangeOfValueServices._debug("    - lifetime: %r", lifetime)

        scm = SubscriptionContextManager(
            self,
            address,
            monitored_object_identifier,
            subscriber_process_identifier,
            issue_confirmed_notifications,
            lifetime,
        )
        if _debug:
            ChangeOfValueServices._debug("    - scm: %r", scm)

        return scm

    async def do_ConfirmedCOVNotificationRequest(
        self, apdu: ConfirmedCOVNotificationRequest
    ) -> None:
        if _debug:
            ChangeOfValueServices._debug("do_ConfirmedCOVNotificationRequest %r", apdu)

        address = apdu.pduSource
        subscriber_process_identifier = apdu.subscriberProcessIdentifier

        # find the context
        scm = self._cov_contexts.get((address, subscriber_process_identifier), None)
        if (not scm) or (
            apdu.monitoredObjectIdentifier != scm.monitored_object_identifier
        ):
            if _debug:
                ChangeOfValueServices._debug("    - scm not found")
            raise ServicesError(errorCode="unknownSubscription")

        # queue the property values
        for property_value in apdu.listOfValues:
            await scm.put(property_value)

        # success
        resp = SimpleAckPDU(context=apdu)
        if _debug:
            ChangeOfValueServices._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)

    async def do_UnconfirmedCOVNotificationRequest(
        self, apdu: UnconfirmedCOVNotificationRequest
    ) -> None:
        if _debug:
            ChangeOfValueServices._debug(
                "do_UnconfirmedCOVNotificationRequest %r", apdu
            )

        address = apdu.pduSource
        subscriber_process_identifier = apdu.subscriberProcessIdentifier

        # find the context
        scm = self._cov_contexts.get((address, subscriber_process_identifier), None)
        if (not scm) or (
            apdu.monitoredObjectIdentifier != scm.monitored_object_identifier
        ):
            if _debug:
                ChangeOfValueServices._debug("    - scm not found")
            return

        # queue the property values
        for property_value in apdu.listOfValues:
            await scm.put(property_value)

    # -----

    def add_subscription(self, cov):
        if _debug:
            ChangeOfValueServices._debug("add_subscription %r", cov)

        # let the detection algorithm know this is a new or additional subscription
        self._cov_detections[cov.obj_ref.objectIdentifier].add_subscription(cov)

    def cancel_subscription(self, cov):
        if _debug:
            ChangeOfValueServices._debug("cancel_subscription %r", cov)

        # stash the object identifier
        object_identifier = cov.obj_ref.objectIdentifier

        # get the detection algorithm object
        cov_detection = self._cov_detections[object_identifier]

        # let the detection algorithm know this subscription is going away
        cov_detection.cancel_subscription(cov)

        # if the detection algorithm doesn't have any subscriptions, remove it
        if not len(cov_detection.cov_subscriptions):
            if _debug:
                ChangeOfValueServices._debug("    - no more subscriptions")

            # unbind all the hooks into the object
            cov_detection.unbind()

            # delete it from the object map
            del self._cov_detections[object_identifier]

    # -----

    def cov_notification(self, cov, apdu):
        """
        Schedule a task to send out a notification related to a COV subscription.
        """
        if _debug:
            ChangeOfValueServices._debug("cov_notification %r %r", cov, apdu)

        # if this is a confirmed service, this function call will return an
        # APDUFuture and the callback will get the error/reject/abort that
        # comes back, otherwise this is None.
        confirmed_service = self.request(apdu)
        if confirmed_service:
            confirmed_service.add_done_callback(partial(self.cov_confirmation, cov))

    def cov_confirmation(self, cov, future) -> None:
        """
        Callback function for sending out notifications.
        """
        if _debug:
            ChangeOfValueServices._debug("cov_confirmation %r %r", cov, future)

        apdu = future.result()
        if _debug:
            ChangeOfValueServices._debug("    - apdu: %r", apdu)
        if not apdu:
            ChangeOfValueServices._debug("    - simple ack")
            return

    # -----

    async def do_SubscribeCOVRequest(self, apdu):
        if _debug:
            ChangeOfValueServices._debug("do_SubscribeCOVRequest %r", apdu)

        # extract the pieces
        client_addr = apdu.pduSource
        proc_id = apdu.subscriberProcessIdentifier
        obj_id = apdu.monitoredObjectIdentifier
        confirmed = apdu.issueConfirmedNotifications
        lifetime = apdu.lifetime

        # request is to cancel the subscription
        cancel_subscription = (confirmed is None) and (lifetime is None)

        # find the object
        obj = self.get_object_id(obj_id)
        if _debug:
            ChangeOfValueServices._debug("    - object: %r", obj)
        if not obj:
            raise ExecutionError(errorClass="object", errorCode="unknownObject")

        # look for an algorithm already associated with this object
        cov_detection = self._cov_detections.get(obj_id, None)

        # if there isn't one, make one and associate it with the object
        if not cov_detection:
            # look for an associated class and if it's not there it's not supported
            criteria_class = getattr(obj, "_cov_criteria", None)
            if _debug:
                ChangeOfValueServices._debug("    - criteria_class: %r", criteria_class)

            if not criteria_class:
                raise ExecutionError(
                    errorClass="services", errorCode="covSubscriptionFailed"
                )

            # make one of these and bind it to the object
            cov_detection = criteria_class(obj)

            # keep track of it for other subscriptions
            self._cov_detections[obj_id] = cov_detection
        if _debug:
            ChangeOfValueServices._debug("    - cov_detection: %r", cov_detection)

        # can a match be found?
        for cov in cov_detection.cov_subscriptions:
            all_equal = (
                (cov.client_addr == client_addr)
                and (cov.proc_id == proc_id)
                and (cov.obj_id == obj_id)
            )
            if _debug:
                ChangeOfValueServices._debug(
                    "    - cov, all_equal: %r %r", cov, all_equal
                )

            if all_equal:
                break
        else:
            cov = None
        if _debug:
            ChangeOfValueServices._debug("    - cov: %r", cov)

        # if a match was found, update the subscription
        if cov:
            if cancel_subscription:
                if _debug:
                    ChangeOfValueServices._debug("    - cancel the subscription")
                self.cancel_subscription(cov)
            else:
                if _debug:
                    ChangeOfValueServices._debug("    - renew the subscription")
                cov.renew_subscription(lifetime)
        else:
            if cancel_subscription:
                if _debug:
                    ChangeOfValueServices._debug(
                        "    - cancel a subscription that doesn't exist"
                    )
            else:
                if _debug:
                    ChangeOfValueServices._debug("    - create a subscription")

                # make a subscription
                cov = Subscription(
                    obj, client_addr, proc_id, obj_id, confirmed, lifetime, None
                )
                if _debug:
                    ChangeOfValueServices._debug("    - cov: %r", cov)

                # add it to our subscriptions lists
                self.add_subscription(cov)

        # success
        response = SimpleAckPDU(context=apdu)

        # return the result
        await self.response(response)

        # if the subscription is not being canceled, it is new or renewed,
        # so send it a notification when you get a chance.
        if not cancel_subscription:
            if _debug:
                ChangeOfValueServices._debug("    - send a notification")
            loop = asyncio.get_running_loop()
            loop.call_soon(cov_detection.send_cov_notifications, cov)
