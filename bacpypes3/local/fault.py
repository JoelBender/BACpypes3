"""
Fault
"""
from __future__ import annotations

import asyncio
from functools import partial

from typing import Callable, List, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger, DebugContents
from ..primitivedata import ObjectType
from ..basetypes import FaultParameterOutOfRangeValue, PropertyIdentifier, PropertyValue, Reliability
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

    algorithm: FaultAlgorithm
    parameter: str
    obj: Object
    prop: str
    indx: Optional[int]

    def __init__(
        self,
        algorithm: FaultAlgorithm,
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
#   FaultAlgorithm
#


@bacpypes_debugging
class FaultAlgorithm(DebugContents):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pCurrentReliability",
        "pReliabilityEvaluationInhibit",
    )

    _monitors: List[DetectionMonitor]
    _what_changed: Dict[str, Tuple[Any, Any]]

    _execute_enabled: bool
    _execute_handle: Optional[asyncio.Handle]
    _execute_fn: Callable[FaultAlgorithm, None]

    monitored_object: Object
    monitoring_object: Optional[EventEnrollmentObject]
    evaluated_reliability: Reliability

    pCurrentReliability: Reliability
    pReliabilityEvaluationInhibit: Boolean

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            FaultAlgorithm._debug("__init__ %r", monitored_object)

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

        # result of running the fault algorithm
        self.evaluated_reliability = Reliability.noFaultDetected

    def bind(self, **kwargs):
        if _debug:
            FaultAlgorithm._debug("bind %r", kwargs)

        parm_names = []
        parm_tasks = []

        # trigger on reliability -- optional for the monitored object,
        # required for the monitoring object
        if self.monitoring_object:
            monitor = DetectionMonitor(
                self, "pCurrentReliability", self.monitoring_object, "reliability"
            )
            if _debug:
                FaultAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append("pCurrentReliability")
            parm_tasks.append(
                self.monitoring_object.read_property(PropertyIdentifier.reliability)
            )
        else:
            monitor = DetectionMonitor(
                self, "pCurrentReliability", self.monitored_object, "reliability"
            )
            if _debug:
                FaultAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append("pCurrentReliability")
            parm_tasks.append(
                self.monitored_object.read_property(PropertyIdentifier.reliability)
            )

        # trigger on reliability-evaluation-inhibit
        monitor = DetectionMonitor(
            self,
            "pReliabilityEvaluationInhibit",
            self.monitored_object,
            "reliabilityEvaluationInhibit",
        )
        if _debug:
            FaultAlgorithm._debug("    - monitor: %r", monitor)

        # keep track of all of these monitor objects for if/when we unbind
        self._monitors.append(monitor)

        # make a task to read the value
        parm_names.append("pReliabilityEvaluationInhibit")
        parm_tasks.append(
            self.monitored_object.read_property(
                PropertyIdentifier.reliabilityEvaluationInhibit
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
                FaultAlgorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append(parameter)
            parm_tasks.append(parameter_object.read_property(parameter_property))

        if parm_tasks:
            if _debug:
                FaultAlgorithm._debug("    - parm_tasks: %r", parm_tasks)

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
            FaultAlgorithm._debug("_parameter_init: %r %r", parm_names, parm_await_task)

        parm_values = parm_await_task.result()
        if _debug:
            FaultAlgorithm._debug("    - parm_values: %r", parm_values)

        for parm_name, parm_value in zip(parm_names, parm_values):
            setattr(self, parm_name, parm_value)

        # proceed with initialization
        self.init()

    def init(self):
        if _debug:
            FaultAlgorithm._debug("init")

    def unbind(self):
        if _debug:
            FaultAlgorithm._debug("unbind")

        # remove the property value monitor functions
        for monitor in self._monitors:
            if _debug:
                FaultAlgorithm._debug("    - monitor: %r", monitor)
            monitor.obj._property_monitors[monitor.prop].remove(monitor.property_change)

        # abandon the array
        self._monitors = []

    def _execute(self):
        if _debug:
            FaultAlgorithm._debug("_execute")

        # no longer scheduled
        self._execute_handle = None

        # check if the algorithm is inhibited
        if self.pReliabilityEvaluationInhibit is None:
            if _debug:
                FaultAlgorithm._debug("    - no reliabilityEvaluationInhibit")
        elif self.pReliabilityEvaluationInhibit:
            if _debug:
                FaultAlgorithm._debug("    - inhibited")
            return

        self._execute_enabled = False

        # let the algorithm run
        self._execute_fn()

        self._execute_enabled = True

        # clear out what changed debugging
        self._what_changed = {}

    def execute(self):
        raise NotImplementedError("execute() not implemented")


#
#   NoneFaultAlgorithm
#


@bacpypes_debugging
class NoneFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.1

    This is a placeholder for the case where no fault algorithm is applied by
    the object.
    """

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            NoneFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        pCurrentReliability = Reliability.noFaultDetected
        pReliabilityEvaluationInhibit = False

    def execute(self):
        if _debug:
            NoneFaultAlgorithm._debug("execute")


#
#   CharacterStringFaultAlgorithm
#


@bacpypes_debugging
class CharacterStringFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.2
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pMonitoredValue",
        "pFaultValues",
    )

    pMonitoredValue: CharacterString
    pFaultValues: ListOf(
        OptionalCharacterString
    )  # maybe ArrayOf(OptionalCharacterString), or SequenceOf(CharacterString)

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            CharacterStringFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            self.bind(
                pCurrentReliability=(monitoring_object, "reliability"),
                pReliabilityEvaluationInhibit=(
                    monitoring_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMonitoredValue=(monitored_object, "presentValue"),
                pFaultValues=monitoring_object.faultParameters.faultCharacterString.listOfFaultValues,
            )
        else:
            self.bind(
                pCurrentReliability=(monitored_object, "reliability"),
                pReliabilityEvaluationInhibit=(
                    monitored_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMonitoredValue=(monitored_object, "presentValue"),
                pFaultValues=(monitored_object, "faultValues"),
            )

    def execute(self):
        if _debug:
            CharacterStringFaultAlgorithm._debug("execute")


#
#   ExtendedFaultAlgorithm
#


@bacpypes_debugging
class ExtendedFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.3
    """

    _debug_contents: Tuple[str, ...] = (
        "pVendorId",
        "pFaultType",
        "pParameters",
    )

    # pCurrentReliability: Reliability
    # pReliabilityEvaluationInhibit: Boolean
    pVendorId: Unsigned
    pFaultType: Unsigned
    pParameters: SequenceOfFaultParameterExtendedParameters

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            ExtendedFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        self.bind(
            pCurrentReliability=(monitoring_object, "reliability"),
            pReliabilityEvaluationInhibit=(
                monitoring_object,
                "reliabilityEvaluationInhibit",
            ),
            pVendorId=monitoring_object.faultParameters.extended.vendorID,
            pFaultType=monitoring_object.faultParameters.extended.extendedFaultType,
            pParameters=monitoring_object.faultParameters.extended.parameters,
        )

    def execute(self):
        if _debug:
            ExtendedFaultAlgorithm._debug("execute")


#
#   LifeSafetyFaultAlgorithm -- 13.4.4
#

#
#   StateFaultAlgorithm
#


@bacpypes_debugging
class StateFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.5
    """

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            StateFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)
        raise NotImplementedError()

    def execute(self):
        if _debug:
            StateFaultAlgorithm._debug("execute")


#
#   StatusFlagsFaultAlgorithm
#


@bacpypes_debugging
class StatusFlagsFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.6
    """

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            StatusFlagsFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)
        raise NotImplementedError()

    def execute(self):
        if _debug:
            ChangeOfValueFaultAlgorithm._debug("execute")


#
#   OutOfRangeFaultAlgorithm
#


@bacpypes_debugging
class OutOfRangeFaultAlgorithm(FaultAlgorithm, DebugContents):
    """
    Clause 13.4.7
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pMinimumNormalValue",
        "pMaximumNormalValue",
        "pMonitoredValue",
    )

    pMinimumNormalValue: Union[Real, Unsigned, Double, Integer]
    pMaximumNormalValue: Union[Real, Unsigned, Double, Integer]
    pMonitoredValue: Union[Real, Unsigned, Double, Integer]

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            OutOfRangeFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            self.bind(
                pCurrentReliability=(monitoring_object, "reliability"),
                pReliabilityEvaluationInhibit=(
                    monitoring_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMinimumNormalValue=monitoring_object.faultParameters.faultOutOfRange.minNormalValue,
                pMaximumNormalValue=monitoring_object.faultParameters.faultOutOfRange.maxNormalValue,
                pMonitoredValue=(monitored_object, "presentValue"),
            )
        else:
            self.bind(
                pCurrentReliability=(monitored_object, "reliability"),
                pReliabilityEvaluationInhibit=(
                    monitored_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMinimumNormalValue=(monitored_object, "faultLowLimit"),
                pMaximumNormalValue=(monitored_object, "faultHighLimit"),
                pMonitoredValue=(monitored_object, "presentValue"),
            )

    def init(self):
        if _debug:
            OutOfRangeFaultAlgorithm._debug(
                "init(%s)", self.monitored_object.objectName
            )

        # normalize the values
        if isinstance(self.pMinimumNormalValue, FaultParameterOutOfRangeValue):
            self.pMinimumNormalValue = getattr(
                self.pMinimumNormalValue, self.pMinimumNormalValue._choice
            )
        if isinstance(self.pMaximumNormalValue, FaultParameterOutOfRangeValue):
            self.pMaximumNormalValue = getattr(
                self.pMaximumNormalValue, self.pMaximumNormalValue._choice
            )

    def execute(self):
        if _debug:
            OutOfRangeFaultAlgorithm._debug(
                "execute(%s)", self.monitored_object.objectName
            )
            OutOfRangeFaultAlgorithm._debug(
                "    - what changed: %r", self._what_changed
            )

        if (self.pCurrentReliability == Reliability.noFaultDetected) and (
            self.pMonitoredValue < self.pMinimumNormalValue
        ):
            self.monitored_object.reliability = Reliability.underRange
        elif (self.pCurrentReliability == Reliability.noFaultDetected) and (
            self.pMonitoredValue > self.pMaximumNormalValue
        ):
            self.monitored_object.reliability = Reliability.overRange
        elif (self.pCurrentReliability == Reliability.underRange) and (
            self.pMonitoredValue > self.pMaximumNormalValue
        ):
            self.monitored_object.reliability = Reliability.overRange
        elif (self.pCurrentReliability == Reliability.overRange) and (
            self.pMonitoredValue < self.pMinimumNormalValue
        ):
            self.monitored_object.reliability = Reliability.underRange
        elif (
            (self.pCurrentReliability == Reliability.underRange)
            and (self.pMonitoredValue >= self.pMinimumNormalValue)
            and (self.pMonitoredValue <= self.pMaximumNormalValue)
        ):
            self.monitored_object.reliability = Reliability.noFaultDetected
        elif (
            (self.pCurrentReliability == Reliability.overRange)
            and (self.pMonitoredValue >= self.pMinimumNormalValue)
            and (self.pMonitoredValue <= self.pMaximumNormalValue)
        ):
            self.monitored_object.reliability = Reliability.noFaultDetected
        else:
            print("    - no transition")


#
#   FaultListedFaultAlgorithm
#


@bacpypes_debugging
class FaultListedFaultAlgorithm(FaultAlgorithm):
    """
    Clause 13.4.8
    """

    # pCurrentReliability: Reliability
    # pReliabilityEvaluationInhibit: Boolean

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            FaultListedFaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__(monitoring_object, monitored_object)

        if monitoring_object:
            self.bind(
                pCurrentReliability=(monitoring_object, "reliability"),
                pReliabilityEvaluationInhibit=(),
            )
        else:
            self.bind(
                pCurrentReliability=(monitored_object, "reliability"),
            )

    def execute(self):
        if _debug:
            FaultListedFaultAlgorithm._debug("execute")
