"""
Change Of Value
"""
from __future__ import annotations

import asyncio

from typing import Callable, List

from ..debugging import bacpypes_debugging, ModuleLogger
from ..primitivedata import ObjectType
from ..basetypes import PropertyValue
from ..constructeddata import Any
from ..apdu import (
    ConfirmedCOVNotificationRequest,
    UnconfirmedCOVNotificationRequest,
)
from ..object import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   DetectionMonitor
#


@bacpypes_debugging
class DetectionMonitor:
    """
    An instance of this class is used to associate a property of an
    object to a parameter of a COV algorithm.  The property_change()
    function is called when the property changes value and that
    value is passed along as an attribute of the algorithm.
    """

    _debug: Callable[..., None]

    def __init__(self, algorithm, parameter, obj, prop, filter=None):
        if _debug:
            DetectionMonitor._debug("__init__ ... %r ...", parameter)

        # keep track of the parameter values
        self.algorithm = algorithm
        self.parameter = parameter
        self.obj = obj
        self.prop = prop
        self.filter = None

    def property_change(self, old_value, new_value):
        if _debug:
            DetectionMonitor._debug("property_change %r %r", old_value, new_value)

        # set the parameter value
        setattr(self.algorithm, self.parameter, new_value)

        # if the algorithm is scheduled to run, don't bother checking for more
        if self.algorithm._execute_handle:
            if _debug:
                DetectionMonitor._debug("    - already scheduled")
            return

        # if there is a special filter, use it, otherwise use !=
        if self.filter:
            change_found = self.filter(old_value, new_value)
        else:
            change_found = old_value != new_value
        if _debug:
            DetectionMonitor._debug("    - change_found: %r", change_found)

        # schedule it
        if change_found and not self.algorithm._execute_handle:
            self.algorithm._execute_handle = asyncio.get_event_loop().call_soon(
                self.algorithm._execute
            )
            if _debug:
                DetectionMonitor._debug(
                    "    - deferred: %r", self.algorithm._execute_handle
                )


#
#   monitor_filter
#


def monitor_filter(parameter):
    def transfer_filter_decorator(fn):
        fn._monitor_filter = parameter
        return fn

    return transfer_filter_decorator


#
#   DetectionAlgorithm
#


@bacpypes_debugging
class DetectionAlgorithm:

    _debug: Callable[..., None]

    _monitors: List[DetectionMonitor]
    _execute_handle: asyncio.Handle

    def __init__(self):
        if _debug:
            DetectionAlgorithm._debug("__init__")

        # monitor objects
        self._monitors = []

        # handle for being scheduled to run
        self._execute_handle = None

    def bind(self, **kwargs):
        if _debug:
            DetectionAlgorithm._debug("bind %r", kwargs)

        # build a map of methods that are filters.  These have been decorated
        # with monitor_filter, but they are unbound methods (or simply
        # functions in Python3) at the time they are decorated but by looking
        # for them now they are bound to this instance.
        monitor_filters = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, "_monitor_filter"):
                monitor_filters[attr._monitor_filter] = attr
        if _debug:
            DetectionAlgorithm._debug("    - monitor_filters: %r", monitor_filters)

        for parameter, (obj, prop) in kwargs.items():
            if not hasattr(self, parameter):
                if _debug:
                    DetectionAlgorithm._debug(
                        "    - no matching parameter: %r", parameter
                    )

            # make a detection monitor
            monitor = DetectionMonitor(self, parameter, obj, prop)
            if _debug:
                DetectionAlgorithm._debug("    - monitor: %r", monitor)

            # check to see if there is a custom filter for it
            if parameter in monitor_filters:
                monitor.filter = monitor_filters[parameter]

            # keep track of all of these objects for if/when we unbind
            self._monitors.append(monitor)

            # add the property value monitor function
            obj._property_monitors[prop].append(monitor.property_change)

            # set the parameter value to the property value if it's not None
            property_value = getattr(obj, prop)
            if property_value is not None:
                if _debug:
                    DetectionAlgorithm._debug("    - %s: %r", parameter, property_value)
                setattr(self, parameter, property_value)

    def unbind(self):
        if _debug:
            DetectionAlgorithm._debug("unbind")

        # remove the property value monitor functions
        for monitor in self._monitors:
            if _debug:
                DetectionAlgorithm._debug("    - monitor: %r", monitor)
            monitor.obj._property_monitors[monitor.prop].remove(monitor.property_change)

        # abandon the array
        self._monitors = []

    def _execute(self):
        if _debug:
            DetectionAlgorithm._debug("_execute")

        # no longer scheduled
        self._execute_handle = None

        # provided by the derived class
        self.execute()

    def execute(self):
        raise NotImplementedError("execute not implemented")


#
#   COVDetection
#


@bacpypes_debugging
class COVDetection(DetectionAlgorithm):

    properties_tracked = ()
    properties_reported = ()
    monitored_property_reference = None

    def __init__(self, obj) -> None:
        if _debug:
            COVDetection._debug("__init__ %r", obj)
        DetectionAlgorithm.__init__(self)

        # keep track of the object
        self.obj = obj

        # build a list of parameters and matching object property references
        kwargs = {}
        for property_name in self.properties_tracked:
            setattr(self, property_name, None)
            kwargs[property_name] = (obj, property_name)

        # let the base class set up the bindings and initial values
        self.bind(**kwargs)

        # list of all active subscriptions
        self.cov_subscriptions = []

    def add_subscription(self, cov) -> None:
        if _debug:
            COVDetection._debug("add_subscription %r", cov)

        # add it to the subscription list for its object
        self.cov_subscriptions.append(cov)

    def cancel_subscription(self, cov) -> None:
        if _debug:
            COVDetection._debug("cancel_subscription %r", cov)

        # cancel the subscription timeout
        cov.cancel_subscription()

        # remove it from the subscription list for its object
        self.cov_subscriptions.remove(cov)

    def execute(self) -> None:
        """
        By default if one of the properties that are being tracked have changed
        then send out COV notifications to all of the active subscriptions.
        """
        if _debug:
            COVDetection._debug("execute")

        # something changed, send out the notifications
        self.send_cov_notifications()

    def send_cov_notifications(self, subscription=None) -> None:
        """
        Send out COV notifications to a specific subscription when it has
        newly joined, or all of the active subscriptions.
        """
        if _debug:
            COVDetection._debug("send_cov_notifications %r", subscription)

        # check for subscriptions
        if not len(self.cov_subscriptions):
            return

        # create a list of PropertyValue objects
        list_of_values = []
        for property_name in self.properties_reported:
            if _debug:
                COVDetection._debug("    - property_name: %r", property_name)

            property_value = getattr(self, property_name)
            if _debug:
                COVDetection._debug("    - property_value: %r", property_value)

            # bundle it into a sequence
            property_value = PropertyValue(
                propertyIdentifier=property_name,
                value=Any(property_value),
            )

            # add it to the list
            list_of_values.append(property_value)
        if _debug:
            COVDetection._debug("    - list_of_values: %r", list_of_values)

        # if the specific subscription was provided, that is the notification
        # list, otherwise send it to all of them
        if subscription is not None:
            notification_list = [subscription]
        else:
            notification_list = self.cov_subscriptions

        # get the current time from the running event loop
        current_time = asyncio.get_running_loop().time()
        if _debug:
            COVDetection._debug("    - current_time: %r", current_time)

        # loop through the subscriptions and send out notifications
        for cov in notification_list:
            if _debug:
                COVDetection._debug("    - cov: %s", repr(cov))

            # calculate time remaining
            if not cov.cancel_handle:
                time_remaining = 0
            else:
                time_remaining = int(cov.cancel_handle.when() - current_time)

                # make sure it is at least one second
                if not time_remaining:
                    time_remaining = 1

            # build a request with the correct type
            if cov.confirmed:
                request = ConfirmedCOVNotificationRequest()
            else:
                request = UnconfirmedCOVNotificationRequest()

            # find the device object
            device_object = None
            for obj in self.obj._app.objectIdentifier.values():
                if not isinstance(obj, DeviceObject):
                    continue
                if device_object is not None:
                    raise RuntimeError("duplicate device object")
                device_object = obj
            if device_object is None:
                raise RuntimeError("missing device object")

            # fill in the parameters
            request.pduDestination = cov.client_addr
            request.subscriberProcessIdentifier = cov.proc_id
            request.initiatingDeviceIdentifier = device_object.objectIdentifier
            request.monitoredObjectIdentifier = cov.obj_id
            request.timeRemaining = time_remaining
            request.listOfValues = list_of_values
            if _debug:
                COVDetection._debug("    - request: %s", repr(request))

            # let the application send it
            self.obj._app.cov_notification(cov, request)


class GenericCriteria(COVDetection):

    properties_tracked = (
        "presentValue",
        "statusFlags",
    )
    properties_reported = (
        "presentValue",
        "statusFlags",
    )
    monitored_property_reference = "presentValue"


@bacpypes_debugging
class COVIncrementCriteria(COVDetection):

    properties_tracked = (
        "presentValue",
        "statusFlags",
        "covIncrement",
    )
    properties_reported = (
        "presentValue",
        "statusFlags",
    )
    monitored_property_reference = "presentValue"

    def __init__(self, obj):
        if _debug:
            COVIncrementCriteria._debug("__init__ %r", obj)
        COVDetection.__init__(self, obj)

        # previously reported value
        self.previously_reported_value = None

    @monitor_filter("presentValue")
    def present_value_filter(self, old_value, new_value):
        if _debug:
            COVIncrementCriteria._debug(
                "present_value_filter %r %r", old_value, new_value
            )

        # first time around initialize to the old value
        if self.previously_reported_value is None:
            if _debug:
                COVIncrementCriteria._debug("    - first value: %r", old_value)
            self.previously_reported_value = old_value

        # see if it changed enough to trigger reporting
        value_changed = (
            new_value <= (self.previously_reported_value - self.obj.covIncrement)
        ) or (new_value >= (self.previously_reported_value + self.obj.covIncrement))
        if _debug:
            COVIncrementCriteria._debug(
                "    - value significantly changed: %r", value_changed
            )

        return value_changed

    def send_cov_notifications(self, subscription=None):
        if _debug:
            COVIncrementCriteria._debug("send_cov_notifications %r", subscription)

        # when sending out notifications, keep the current value
        self.previously_reported_value = self.presentValue

        # continue
        super().send_cov_notifications(subscription)


class AccessDoorCriteria(COVDetection):

    properties_tracked = (
        "presentValue",
        "statusFlags",
        "doorAlarmState",
    )
    properties_reported = (
        "presentValue",
        "statusFlags",
        "doorAlarmState",
    )


class AccessPointCriteria(COVDetection):

    properties_tracked = (
        "accessEventTime",
        "statusFlags",
    )
    properties_reported = (
        "accessEvent",
        "statusFlags",
        "accessEventTag",
        "accessEventTime",
        "accessEventCredential",
        "accessEventAuthenticationFactor",
    )
    monitored_property_reference = "accessEvent"


class CredentialDataInputCriteria(COVDetection):

    properties_tracked = ("updateTime", "statusFlags")
    properties_reported = (
        "presentValue",
        "statusFlags",
        "updateTime",
    )


class LoadControlCriteria(COVDetection):

    properties_tracked = (
        "presentValue",
        "statusFlags",
        "requestedShedLevel",
        "startTime",
        "shedDuration",
        "dutyWindow",
    )
    properties_reported = (
        "presentValue",
        "statusFlags",
        "requestedShedLevel",
        "startTime",
        "shedDuration",
        "dutyWindow",
    )


@bacpypes_debugging
class PulseConverterCriteria(COVIncrementCriteria):

    properties_tracked = (
        "presentValue",
        "statusFlags",
        "covPeriod",
    )
    properties_reported = (
        "presentValue",
        "statusFlags",
    )

    def __init__(self, obj):
        if _debug:
            PulseConverterCriteria._debug("__init__ %r", obj)
        COVIncrementCriteria.__init__(self, obj)

        # check for a period
        if self.covPeriod == 0:
            if _debug:
                PulseConverterCriteria._debug("    - no periodic notifications")
            self.cov_period_task = None
        else:
            if _debug:
                PulseConverterCriteria._debug("    - covPeriod: %r", self.covPeriod)
            # self.cov_period_task = RecurringFunctionTask(
            #     self.covPeriod * 1000, self.send_cov_notifications
            # )
            if _debug:
                PulseConverterCriteria._debug("    - cov period task created")

    def add_subscription(self, cov):
        if _debug:
            PulseConverterCriteria._debug("add_subscription %r", cov)

        # let the parent classes do their thing
        COVIncrementCriteria.add_subscription(self, cov)

        # if there is a COV period task, install it
        if self.cov_period_task:
            self.cov_period_task.install_task()
            if _debug:
                PulseConverterCriteria._debug("    - cov period task installed")

    def cancel_subscription(self, cov):
        if _debug:
            PulseConverterCriteria._debug("cancel_subscription %r", cov)

        # let the parent classes do their thing
        COVIncrementCriteria.cancel_subscription(self, cov)

        # if there are no more subscriptions, cancel the task
        if not len(self.cov_subscriptions):
            if self.cov_period_task and self.cov_period_task.isScheduled:
                self.cov_period_task.suspend_task()
                if _debug:
                    PulseConverterCriteria._debug("    - cov period task suspended")
                self.cov_period_task = None

    @monitor_filter("covPeriod")
    def cov_period_filter(self, old_value, new_value):
        if _debug:
            PulseConverterCriteria._debug(
                "cov_period_filter %r %r", old_value, new_value
            )

        # check for an old period
        if old_value != 0:
            if self.cov_period_task.isScheduled:
                self.cov_period_task.suspend_task()
                if _debug:
                    PulseConverterCriteria._debug("    - canceled old task")
            self.cov_period_task = None

        # check for a new period
        if new_value != 0:
            # self.cov_period_task = RecurringFunctionTask(
            #     new_value * 1000, self.send_cov_notifications
            # )
            self.cov_period_task.install_task()
            if _debug:
                PulseConverterCriteria._debug("    - new task created and installed")

        return False

    def send_cov_notifications(self, subscription=None):
        if _debug:
            PulseConverterCriteria._debug("send_cov_notifications %r", subscription)

        # pass along to the parent class as if something changed
        super().send_cov_notifications(subscription)


# mapping from object type to appropriate criteria class
criteria_type_map = {
    #   'accessDoor': GenericCriteria,  #TODO: needs AccessDoorCriteria
    "accessPoint": AccessPointCriteria,
    ObjectType.analogInput: COVIncrementCriteria,
    ObjectType.analogOutput: COVIncrementCriteria,
    ObjectType.analogValue: COVIncrementCriteria,
    "largeAnalogValue": COVIncrementCriteria,
    "integerValue": COVIncrementCriteria,
    "positiveIntegerValue": COVIncrementCriteria,
    "lightingOutput": COVIncrementCriteria,
    "binaryInput": GenericCriteria,
    "binaryOutput": GenericCriteria,
    "binaryValue": GenericCriteria,
    "lifeSafetyPoint": GenericCriteria,
    "lifeSafetyZone": GenericCriteria,
    "multiStateInput": GenericCriteria,
    "multiStateOutput": GenericCriteria,
    "multiStateValue": GenericCriteria,
    "octetString": GenericCriteria,
    "characterString": GenericCriteria,
    "timeValue": GenericCriteria,
    "dateTimeValue": GenericCriteria,
    "dateValue": GenericCriteria,
    "timePatternValue": GenericCriteria,
    "datePatternValue": GenericCriteria,
    "dateTimePatternValue": GenericCriteria,
    "credentialDataInput": CredentialDataInputCriteria,
    "loadControl": LoadControlCriteria,
    "loop": GenericCriteria,
    "pulseConverter": PulseConverterCriteria,
}
