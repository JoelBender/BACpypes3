"""
Event
"""
from __future__ import annotations

import asyncio
from functools import partial

from typing import Callable, List, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger, DebugContents
from ..primitivedata import ObjectType
from ..basetypes import EventState, PropertyIdentifier, PropertyValue, Reliability
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
    object to a parameter of an event algorithm.  The property_change()
    function is called when the property changes value and that
    value is passed along as an attribute of the algorithm.
    """

    _debug: Callable[..., None]

    algorithm: EventAlgorithm
    parameter: str
    obj: Object
    prop: str
    indx: Optional[int]

    def __init__(
        self,
        algorithm: EventAlgorithm,
        parameter: str,
        obj: Object,
        prop: Union[int, str, PropertyIdentifier],
        indx: Optional[int] = None,
    ):
        if _debug:
            DetectionMonitor._debug("__init__ ... %r ...", parameter)

        # the property is the attribute name
        if isinstance(prop, int):
            prop = PropertyIdentifier(prop)
        if isinstance(prop, PropertyIdentifier):
            prop = prop.attr
        assert isinstance(prop, str)
        if _debug:
            DetectionMonitor._debug("    - prop: %r", prop)

        # keep track of the parameter values
        self.algorithm = algorithm
        self.parameter = parameter
        self.obj = obj
        self.prop = prop
        self.indx = indx

        # add the property value monitor function
        self.obj._property_monitors[self.prop].append(self.property_change)

    def property_change(self, old_value, new_value):
        if _debug:
            DetectionMonitor._debug(
                "property_change (%s) %r %r", self.parameter, old_value, new_value
            )

        # set the parameter value
        setattr(self.algorithm, self.parameter, new_value)

        # handy for debugging
        self.algorithm._what_changed[self.parameter] = (old_value, new_value)

        if not self.algorithm._execute_enabled:
            if _debug:
                DetectionMonitor._debug("    - execute disabled")
            return

        # if the algorithm is scheduled to run, don't bother checking for more
        if self.algorithm._execute_handle:
            if _debug:
                DetectionMonitor._debug("    - already scheduled")
            return

        # see if something changed
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
                    "    - scheduled: %r", self.algorithm._execute_handle
                )


#
#   EventAlgorithm
#


@bacpypes_debugging
class EventAlgorithm:
    _debug: Callable[..., None]

    _monitors: List[DetectionMonitor]
    _what_changed: Dict[str, Tuple[Any, Any]]

    _execute_enabled: bool
    _execute_handle: Optional[asyncio.Handle]
    _execute_fn: Callable[EventAlgorithm, None]

    monitored_object: Object
    monitoring_object: Optional[EventEnrollmentObject]

    pCurrentState: EventState
    pReliability: Reliability
    pEventDetectionEnable: Boolean
    pEventAlgorithmInhibit: Boolean

    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned
    pNotificationClass: Unsigned
    pEventEnable: EventTransitionBits
    pAckedTransitions: EventTransitionBits

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            EventAlgorithm._debug("__init__ %r %r", monitoring_object, monitored_object)

        # detection monitor objects
        self._monitors = []
        self._what_changed = {}

        # handle for being scheduled to run
        self._execute_enabled = True
        self._execute_handle = None
        self._execute_fn = self.execute

        # used for reading/writing the Event_State property
        self.monitored_object = monitored_object
        self.monitoring_object = monitoring_object

    def bind(self, **kwargs):
        if _debug:
            EventAlgorithm._debug("bind %r", kwargs)

        parm_names = []
        parm_tasks = []

        config_object = self.monitoring_object or self.monitored_object

        # if the monitored object has an event state
        if hasattr(self.monitored_object, "eventState"):
            if _debug:
                EventAlgorithm._debug("    - monitored_object has event-state")

            # track the value
            self.monitored_object._property_monitors["eventState"].append(
                self.event_state_changed
            )
        elif self.monitoring_object:
            # track the value
            self.monitoring_object._property_monitors["eventState"].append(
                self.event_state_changed
            )
        else:
            raise RuntimeError("somebody needs eventState")

        # current state is passed as one of the binding parameters

        # if the monitored object does not have reliability then there is
        # no fault detection
        if not hasattr(self.monitored_object, "reliability"):
            self.pReliability = None
        else:
            # make a detection monitor
            monitor = DetectionMonitor(
                self, "pReliability", self.monitored_object, "reliability"
            )
            if _debug:
                EventAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append("pReliability")
            parm_tasks.append(
                self.monitored_object.read_property(PropertyIdentifier.reliability)
            )

        # check for event detection enable, this is expected to be set as a
        # configuration value is not expected to change
        self.pEventDetectionEnable = getattr(
            config_object, "eventDetectionEnable", False
        )
        if not self.pEventDetectionEnable:
            if _debug:
                EventAlgorithm._debug("    - event detection not enabled")

            ### eventState should be set to normal
            ### event TimeStamp, eventMessageTexts, ackedTransitions set to
            ### initial conditions
            return

        # check for event algorithm inhibit
        self.pEventAlgorithmInhibit = getattr(
            config_object, "eventAlgorithmInhibit", None
        )

        # check for event algorithm inhibit reference
        eair: ObjectPropertyReference = getattr(
            config_object, "eventAlgorithmInhibitRef", None
        )
        if eair:
            if self.pEventAlgorithmInhibit is None:
                raise RuntimeError(
                    "eventAlgorithmInhibit required when eventAlgorithmInhibitRef provided"
                )

            # resolve the eair.objectIdentifier to point to an object
            eair_object: Optional[Object] = config_object._app.get_object_id(
                eair.objectIdentifier
            )

            # make a detection monitor
            monitor = DetectionMonitor(
                self,
                "pEventDetectionEnable",
                eair_object,
                eair.propertyIdentifier,
                eair.propertyArrayIndex,
            )
            if _debug:
                EventAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # add the property value monitor function
            eair_object._property_monitors[eair.propertyIdentifier].append(
                monitor.property_change
            )

            # make a task to read the value
            parm_names.append("pEventAlgorithmInhibit")
            parm_tasks.append(
                eair_object.read_property(
                    eair.propertyIdentifier, eair.propertyArrayIndex
                )
            )

        # loop through the rest of the parameter bindings
        for parameter, parameter_value in kwargs.items():
            if not isinstance(parameter_value, tuple):
                setattr(self, parameter, parameter_value)
                continue

            parameter_object, parameter_property = parameter_value

            # make a detection monitor
            monitor = DetectionMonitor(
                self, parameter, parameter_object, parameter_property
            )
            if _debug:
                EventAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append(parameter)
            parm_tasks.append(parameter_object.read_property(parameter_property))

        if parm_tasks:
            if _debug:
                EventAlgorithm._debug("    - parm_tasks: %r", parm_tasks)

            # gather all the parameter tasks and continue algorithm specific
            # initialization after they are all finished
            parm_await_task = asyncio.gather(*parm_tasks)
            parm_await_task.add_done_callback(partial(self._parameter_init, parm_names))

        else:
            # proceed with initialization
            self.init()

    def _parameter_init(self, parm_names, parm_await_task) -> None:
        """
        This callback function is associated with the asyncio.gather() task
        that reads all of the current property values collected together during
        the bind() call.
        """
        if _debug:
            EventAlgorithm._debug("_parameter_init: %r %r", parm_names, parm_await_task)

        parm_values = parm_await_task.result()
        if _debug:
            EventAlgorithm._debug("    - parm_values: %r", parm_values)

        for parm_name, parm_value in zip(parm_names, parm_values):
            setattr(self, parm_name, parm_value)

        # proceed with initialization
        self.init()

    def init(self):
        if _debug:
            EventAlgorithm._debug("init")

    def unbind(self):
        if _debug:
            EventAlgorithm._debug("unbind")

        # remove the property value monitor functions
        for monitor in self._monitors:
            if _debug:
                EventAlgorithm._debug("    - monitor: %r", monitor)
            monitor.obj._property_monitors[monitor.prop].remove(monitor.property_change)

        # abandon the array
        self._monitors = []

    def _execute(self):
        if _debug:
            EventAlgorithm._debug("_execute")

        # no longer scheduled
        self._execute_handle = None

        # event detection should be enabled
        assert self.pEventDetectionEnable

        # check if the algorithm is inhibited
        if self.pEventAlgorithmInhibit is None:
            if _debug:
                EventAlgorithm._debug("    - no eventAlgorithmInhibit")
        elif self.pEventAlgorithmInhibit:
            if _debug:
                EventAlgorithm._debug("    - inhibited")
            return

        # check reliability
        if self.pReliability is None:
            if _debug:
                EventAlgorithm._debug("    - no concept of reliability")
        elif self.pReliability != Reliability.noFaultDetected:
            if _debug:
                EventAlgorithm._debug("    - fault detected")
                EventAlgorithm._debug("    - pCurrentState: %r", self.pCurrentState)

            self.monitored_object.eventState = EventState.fault
            return

        # let the algorithm run
        self._execute_fn()

        # clear out what changed debugging
        self._what_changed = {}

    def execute(self):
        raise NotImplementedError("execute() not implemented")

    # -----

    def event_state_changed(self, old_value, new_value):
        if _debug:
            EventAlgorithm._debug("event_state_changed %r %r", old_value, new_value)

    def reliability_changed(self, old_value, new_value):
        """
        Trigger Event-State-Detection State Machine -- Clause 13.2.2
        """
        if _debug:
            EventAlgorithm._debug("reliability_changed %r %r", old_value, new_value)

    def cascade_reliability(self, old_value, new_value):
        """
        This function is called when the reliability has changed for the monitored
        object and the new value needs to be reflected in the monitoring object.
        """
        if _debug:
            EventAlgorithm._debug("cascade_reliability %r %r", old_value, new_value)

        asyncio.ensure_future(
            self.monitoring_object.write_property(
                PropertyIdentifier.eventState, new_value
            )
        )

    def event_algorithm_inhibit_changed(self, old_value, new_value):
        """
        Clause 13.2.2.1.5
        """
        if _debug:
            EventAlgorithm._debug(
                "event_algorithm_inhibit_changed %r %r", old_value, new_value
            )


#
#   ChangeOfBitstringEventAlgorithm
#


@bacpypes_debugging
class ChangeOfBitstringEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.1
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pAlarmValues: ListOf(BitString)
    pBitmask: BitString
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfBitstringEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=monitoring_object.eventParameters.changeOfBitstring.listOfBitstringValues,
                pBitmask=monitoring_object.eventParameters.changeOfBitstring.bitMask,
                pTimeDelay=monitoring_object.eventParameters.changeOfBitstring.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=(monitored_object, "alarmValues"),
                pBitmask=(monitored_object, "bitMask"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfBitstringEventAlgorithm._debug("execute")


#
#   ChangeOfStateEventAlgorithm
#


@bacpypes_debugging
class ChangeOfStateEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.2
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pAlarmValues: ListOf(BitString)
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfStateEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=monitoring_object.eventParameters.changeOfState.listOfValues,
                pTimeDelay=monitoring_object.eventParameters.changeOfState.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=(monitored_object, "alarmValue"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfStateEventAlgorithm._debug("execute")


#
#   ChangeOfValueEventAlgorithm
#


@bacpypes_debugging
class ChangeOfValueEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.2
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pIncrement: Real
    pBitmask: BitString
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfValueEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if not monitoring_object:
            raise RuntimeError("algorithmic reporting only")

        # algorithmic reporting
        self.bind(
            pCurrentState=(monitored_object, "eventState"),
            pMonitoredValue=(
                monitored_object,
                monitoring_object.objectPropertyReference.propertyIdentifier,
            ),
            pStatusFlags=(monitored_object, "statusFlags"),
            pIncrement=monitoring_object.eventParameters.changeOfValue.covCriteria.referencedPropertyIncrement,
            pBitmask=monitoring_object.eventParameters.changeOfValue.covCriteria.bitmask,
            pTimeDelay=monitoring_object.eventParameters.changeOfValue.timeDelay,
            pTimeDelayNormal=None,
        )

    def execute(self):
        if _debug:
            ChangeOfValueEventAlgorithm._debug("execute")


#
#   CommandFailureEventAlgorithm
#


@bacpypes_debugging
class CommandFailureEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.4
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pFeedbackValue: Any
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            CommandFailureEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            fpr: DeviceObjectPropertyReference = (
                monitoring_object.eventParameters.commandFailure.feedbackPropertyReference
            )

            # resolve the fpr.objectIdentifier to point to an object
            fpr_object: Optional[Object] = None

            # fpr.propertyIdentifier used below
            # fpr.propertyArrayIndex not supported, simple properties only
            # fpr.deviceIdentifier not supported, this device only

            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pFeedbackValue=(fpr_object, fpr.propertyIdentifier),
                pTimeDelay=monitoring_object.eventParameters.commandFailure.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pFeedbackValue=(monitored_object, "feedbackValue"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            CommandFailureEventAlgorithm._debug("execute")


#
#   FloatingLimitEventAlgorithm
#


@bacpypes_debugging
class FloatingLimitEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.5
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pSetpoint: Real
    pLowDiffLimit: Real
    pHighDiffLimit: Real
    pDeadband: Real
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            FloatingLimitEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            spr: DeviceObjectPropertyReference = (
                monitoring_object.eventParameters.floatingLimit.setpointReference
            )
            if spr.propertyArrayIndex is not None:
                raise NotImplementedError()
            if spr.deviceIdentifier is not None:
                raise NotImplementedError()

            # resolve the spr.objectIdentifier to point to an object
            spr_object: Optional[Object] = monitoring_object._app.get_object_id(
                spr.objectIdentifier
            )
            if not spr_object:
                raise RuntimeError("object not found")

            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pSetpoint=(spr_object, spr.propertyIdentifier),
                pLowDiffLimit=monitoring_object.eventParameters.floatingLimit.lowDiffLimit,
                pHighDiffLimit=monitoring_object.eventParameters.floatingLimit.highDiffLimit,
                pDeadband=monitoring_object.eventParameters.floatingLimit.deadband,
                pTimeDelay=monitoring_object.eventParameters.floatingLimit.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # check setpointReference, the presence of a reference indicates the
            # property of another object contains the setpoint value
            spr: DeviceObjectPropertyReference = monitored_object.setpointReference

            # resolve the spr.objectIdentifier to point to an object
            spr_object: Optional[Object] = None

            # spr.propertyIdentifier used below
            # spr.propertyArrayIndex not supported, simple properties only
            # spr.deviceIdentifier not supported, this device only

            if spr_object:
                setpoint = (spr_object, spr.propertyIdentifier)
            else:
                setpoint = (monitored_object, "setpoint")

            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pSetpoint=setpoint,
                pLowDiffLimit=(monitored_object, "lowDiffLimit"),
                pHighDiffLimit=(monitored_object, "errorLimit"),
                pDeadband=(monitored_object, "deadband"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            FloatingLimitEventAlgorithm._debug("execute")
            # use pHighDiffLimit for both high and low unless pLowDiffLimit has a value


#
#   OutOfRangeEventAlgorithm
#


@bacpypes_debugging
class OutOfRangeEventAlgorithm(EventAlgorithm, DebugContents):
    """
    Clause 13.3.6
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pCurrentState",
        "pMonitoredValue",
        "pStatusFlags",
        "pLowLimit",
        "pHighLimit",
        "pDeadband",
        "pLimitEnable",
        "pTimeDelay",
        "pTimeDelayNormal",
    )

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pLowLimit: Real
    pHighLimit: Real
    pDeadband: Real
    pLimitEnable: LimitEnable
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "__init__ %r %r", monitoring_object, monitored_object
            )
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=monitoring_object.eventParameters.outOfRange.lowLimit,
                pHighLimit=monitoring_object.eventParameters.outOfRange.highLimit,
                pDeadband=monitoring_object.eventParameters.outOfRange.deadband,
                pLimitEnable=None,
                pTimeDelay=monitoring_object.eventParameters.outOfRange.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=(monitored_object, "lowLimit"),
                pHighLimit=(monitored_object, "highLimit"),
                pDeadband=(monitored_object, "deadband"),
                pLimitEnable=(monitored_object, "limitEnable"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def init(self):
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "init(%s)", self.monitored_object.objectName
            )

    def execute(self):
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "execute(%s)", self.monitored_object.objectName
            )
            OutOfRangeEventAlgorithm._debug(
                "    - current state: %r", self.pCurrentState
            )
            OutOfRangeEventAlgorithm._debug(
                "    - what changed: %r", self._what_changed
            )


#
#   BufferReadyEventAlgorithm
#


@bacpypes_debugging
class BufferReadyEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.7
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pLogBuffer: DeviceObjectPropertyReference
    pThreshold: Unsigned
    pPreviousCount: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            BufferReadyEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pLogBuffer=monitored_object,
                pThreshold=monitoring_object.eventParameters.outOfRange.notificationThreshold,
                pPreviousCount=monitoring_object.eventParameters.outOfRange.previousNotificationCount,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "recordCount"),
                pLogBuffer=monitored_object,
                pThreshold=monitored_object.notificationThreshold,
                pPreviousCount=monitored_object.recordsSinceNotification,
            )

    def execute(self):
        if _debug:
            BufferReadyEventAlgorithm._debug("execute")


#
#   ChangeOfLifeSafetyEventAlgorithm -- 13.3.8
#

#
#   UnsignedRangeEventAlgorithm
#


@bacpypes_debugging
class UnsignedRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.9
    """

    pCurrentState: EventState
    pMonitoredValue: BitString
    pStatusFlags: StatusFlags
    pLowLimit: Unsigned
    pHighLimit: Unsigned
    pLimitEnable: LimitEnable
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            UnsignedRangeEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=monitoring_object.eventParameters.outOfRange.lowLimit,
                pHighLimit=monitoring_object.eventParameters.outOfRange.highLimit,
                pLimitEnable=None,
                pTimeDelay=monitoring_object.eventParameters.outOfRange.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=(monitored_object, "lowDiffLimit"),
                pHighLimit=(monitored_object, "errorLimit"),
                pLimitEnable=(monitored_object, "limitEnable"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            UnsignedRangeEventAlgorithm._debug("execute")
            # use pHighLimit for both high and low unless pLowLimit has a value


#
#   ExtendedEventAlgorithm
#


@bacpypes_debugging
class ExtendedEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.10
    """

    pCurrentState: EventState
    pVendorId: Unsigned
    pEventType: Unsigned
    pParameters: SequenceOfEventParameterExtendedParameters

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ExtendedEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if not monitoring_object:
            raise RuntimeError("algorithmic reporting only")

        # algorithmic reporting
        self.bind(
            pCurrentState=(monitored_object, "eventState"),
            pLowLimit=monitoring_object.eventParameters.extended.vendorID,
            pHighLimit=monitoring_object.eventParameters.extended.extendedEventType,
            pParameters=monitoring_object.eventParameters.extended.parameters,
        )

    def execute(self):
        if _debug:
            ExtendedEventAlgorithm._debug("execute")


#
#   ChangeOfStatusFlags
#


@bacpypes_debugging
class ChangeOfStatusFlags(EventAlgorithm):
    """
    Clause 13.3.11
    """

    pCurrentState: EventState
    pMonitoredValue: StatusFlags
    pSelectedFlags: StatusFlags
    pPresentValue: Any
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfStatusFlags._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,  # memberStatusFlags -- 12.50.10
                ),
                pSelectedFlags=monitoring_object.eventParameters.changeOfStatusflags.selectedFlags,
                pPresentValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.presentValue,
                ),
                pTimeDelay=monitoring_object.eventParameters.changeOfStatusflags.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    PropertyIdentifier.memberStatusFlags,
                ),
                pSelectedFlags=StatusFlags([1, 1, 0, 0]),  # inAlarm, fault
                pPresentValue=(monitored_object, "presentValue"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfStatusFlags._debug("execute")


#
#   AccessEventEventAlgorithm
#


@bacpypes_debugging
class AccessEventEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.12
    """

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            AccessEventEventAlgorithm._debug("__init__ %r", monitored_object)
        raise NotImplementedError("AccessEventEventAlgorithm")


#
#   DoubleOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class DoubleOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.13
    """

    pCurrentState: EventState
    pMonitoredValue: Double
    pStatusFlags: StatusFlags
    pLowLimit: Double
    pHighLimit: Double
    pDeadband: Double
    pLimitEnable: LimitEnable
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            DoubleOutOfRangeEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=monitoring_object.eventParameters.doubleOutOfRange.lowLimit,
                pHighLimit=monitoring_object.eventParameters.doubleOutOfRange.highLimit,
                pDeadband=monitoring_object.eventParameters.doubleOutOfRange.deadband,
                pLimitEnable=None,
                pTimeDelay=monitoring_object.eventParameters.doubleOutOfRange.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=(monitored_object, "lowDiffLimit"),
                pHighLimit=(monitored_object, "errorLimit"),
                pDeadband=(monitored_object, "deadband"),
                pLimitEnable=(monitored_object, "limitEnable"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            DoubleOutOfRangeEventAlgorithm._debug("execute")
            # use pHighLimit for both high and low unless pLowLimit has a value


#
#   SignedOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class SignedOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.13
    """

    pCurrentState: EventState
    pMonitoredValue: Integer
    pStatusFlags: StatusFlags
    pLowLimit: Integer
    pHighLimit: Integer
    pDeadband: Unsigned
    pLimitEnable: LimitEnable
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            SignedOutOfRangeEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=monitoring_object.eventParameters.signedOutOfRange.lowLimit,
                pHighLimit=monitoring_object.eventParameters.signedOutOfRange.highLimit,
                pDeadband=monitoring_object.eventParameters.signedOutOfRange.deadband,
                pLimitEnable=None,
                pTimeDelay=monitoring_object.eventParameters.signedOutOfRange.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=(monitored_object, "lowDiffLimit"),
                pHighLimit=(monitored_object, "errorLimit"),
                pDeadband=(monitored_object, "deadband"),
                pLimitEnable=(monitored_object, "limitEnable"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            SignedOutOfRangeEventAlgorithm._debug("execute")
            # use pHighLimit for both high and low unless pLowLimit has a value


#
#   UnsignedOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class UnsignedOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.15
    """

    pCurrentState: EventState
    pMonitoredValue: Unsigned
    pStatusFlags: StatusFlags
    pLowLimit: Unsigned
    pHighLimit: Unsigned
    pDeadband: Unsigned
    pLimitEnable: LimitEnable
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            UnsignedOutOfRangeEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=monitoring_object.eventParameters.unsignedOutOfRange.lowLimit,
                pHighLimit=monitoring_object.eventParameters.unsignedOutOfRange.highLimit,
                pDeadband=monitoring_object.eventParameters.unsignedOutOfRange.deadband,
                pLimitEnable=None,
                pTimeDelay=monitoring_object.eventParameters.unsignedOutOfRange.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pLowLimit=(monitored_object, "lowDiffLimit"),
                pHighLimit=(monitored_object, "errorLimit"),
                pDeadband=(monitored_object, "deadband"),
                pLimitEnable=(monitored_object, "limitEnable"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            UnsignedOutOfRangeEventAlgorithm._debug("execute")
            # use pHighLimit for both high and low unless pLowLimit has a value


#
#   ChangeOfCharacterStringEventAlgorithm
#


@bacpypes_debugging
class ChangeOfCharacterStringEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.16
    """

    pCurrentState: EventState
    pMonitoredValue: CharacterString
    pStatusFlags: StatusFlags
    pAlarmValues: ListOf(
        OptionalCharacterString
    )  # maybe ArrayOf(OptionalCharacterString), or SequenceOf(CharacterString)
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfCharacterStringEventAlgorithm._debug(
                "__init__ %r", monitored_object
            )
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=monitoring_object.eventParameters.changeOfCharacterstring.listOfAlarmValues,
                pTimeDelay=monitoring_object.eventParameters.changeOfCharacterstring.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=(monitored_object, "alarmValues"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfCharacterStringEventAlgorithm._debug("execute")


#
#   NoneEventEventAlgorithm
#


@bacpypes_debugging
class NoneEventEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.17

    Used when only fault detection is in use by an object.
    """

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            NoneEventEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

    def execute(self):
        if _debug:
            NoneEventEventAlgorithm._debug("execute")


#
#   ChangeOfDiscreteValueEventAlgorithm
#


@bacpypes_debugging
class ChangeOfDiscreteValueEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.18
    """

    pCurrentState: EventState
    pMonitoredValue: CharacterString
    pStatusFlags: StatusFlags
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfDiscreteValueEventAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pTimeDelay=monitoring_object.eventParameters.changeOfCharacterstring.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfDiscreteValueEventAlgorithm._debug("execute")


#
#   ChangeOfTimerEventAlgorithm
#


@bacpypes_debugging
class ChangeOfTimerEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.19
    """

    pCurrentState: EventState
    pMonitoredValue: TimerState
    pStatusFlags: StatusFlags
    pUpdateTime: DateTime
    pLastStateChange: TimerTransition
    pInitialTimeout: Unsigned
    pExpirationTime: DateTime
    pAlarmValues: ListOf(TimerState)
    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ChangeOfDiscreteValueEventAlgorithm._debug("__init__ %r", monitored_object)
        raise NotImplementedError("special assistance needed")

        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            # what to do with monitoring_object.eventParameters.changeOfTimer.updateTimeReference

            # algorithmic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                # pUpdateTime: DateTime
                # pLastStateChange: TimerTransition
                # pInitialTimeout: Unsigned
                # pExpirationTime: DateTime
                pAlarmValues=monitoring_object.eventParameters.changeOfTimer.alarmValues,
                pTimeDelay=monitoring_object.eventParameters.changeOfTimer.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pUpdateTime=(monitored_object, "updateTime"),
                pLastStateChange=(monitored_object, "lastStateChange"),
                pInitialTimeout=(monitored_object, "initialTimeout"),
                pExpirationTime=(monitored_object, "expirationTime"),
                pAlarmValues=(monitored_object, "alarmValues"),
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfDiscreteValueEventAlgorithm._debug("execute")
