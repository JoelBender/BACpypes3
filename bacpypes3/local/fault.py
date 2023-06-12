"""
Fault
"""
from __future__ import annotations

import asyncio
from functools import partial

from typing import Callable, List, Optional, Tuple, Union

from ..debugging import bacpypes_debugging, ModuleLogger, DebugContents
from ..primitivedata import (
    Boolean,
    CharacterString,
    Double,
    Integer,
    Real,
    Unsigned,
)
from ..constructeddata import ListOf
from ..basetypes import (
    FaultParameterOutOfRangeValue,
    OptionalCharacterString,
    PropertyIdentifier,
    Reliability,
    SequenceOfFaultParameterExtendedParameters,
)
from ..object import Object, EventEnrollmentObject
from .object import Algorithm

# some debugging
_debug = 0
_log = ModuleLogger(globals())


#
#   FaultAlgorithm
#


@bacpypes_debugging
class FaultAlgorithm(Algorithm, DebugContents):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pCurrentReliability",
        "pReliabilityEvaluationInhibit",
    )

    monitored_object: Object
    monitoring_object: Optional[EventEnrollmentObject]
    evaluated_reliability: Optional[Reliability]  # None indicates no transition

    pCurrentReliability: Reliability
    pReliabilityEvaluationInhibit: Boolean

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            FaultAlgorithm._debug("__init__ %r", monitored_object)
        super().__init__()

        self.monitoring_object = monitoring_object
        self.monitored_object = monitored_object

        # reliability-evaluation process in indicates a reliability transition
        # which may be the same value as the current reliability, None indicates
        # no transition
        self.evaluated_reliability = None

    def bind(self, **kwargs):
        if _debug:
            FaultAlgorithm._debug("bind %r", kwargs)

        parm_names = []
        parm_tasks = []

        config_object = self.monitoring_object or self.monitored_object

        kwargs["pCurrentReliability"] = (config_object, "reliability")
        kwargs["pReliabilityEvaluationInhibit"] = (
            config_object,
            "reliabilityEvaluationInhibit",
        )

        # continue with binding
        super().bind(**kwargs)

    def init(self):
        """
        This is called after the `bind()` call and after all of the parameter
        initialization tasks have completed.
        """
        if _debug:
            FaultAlgorithm._debug("init")

        # if pCurrentReliability is None it implies that the monitored object
        # has an intrinsic fault algorithm but does not have a reliability
        # property (huh?).  If that's true then the result will be used
        # for event state detection only.
        if self.pCurrentReliability is None:
            self.pCurrentReliability = Reliability.noFaultDetected

    def _execute(self):
        if _debug:
            FaultAlgorithm._debug("_execute")

        # no longer scheduled
        self._execute_handle = None

        # check if the algorithm is inhibited
        if self.pReliabilityEvaluationInhibit is None:
            if _debug:
                FaultAlgorithm._debug("    - no reliability-evaluation-inhibit")
        elif self.pReliabilityEvaluationInhibit:
            if _debug:
                FaultAlgorithm._debug("    - inhibited")
            self.evaluated_reliability = None
            return

        # turn off property change notifications
        self._execute_enabled = False

        # let the algorithm run
        self.evaluated_reliability = self._execute_fn()
        if _debug:
            if self.evaluated_reliability is None:
                FaultAlgorithm._debug(
                    "    - evaluated_reliability: None (no-transition)"
                )
            else:
                FaultAlgorithm._debug(
                    "    - evaluated_reliability: %r",
                    Reliability(self.evaluated_reliability),
                )

        # turn property change notifications back on
        self._execute_enabled = True

        # clear out what changed debugging
        self._what_changed = {}

    def execute(self) -> Optional[Reliability]:
        """
        Using the bound parameters, determine if there should be a change in the
        reliability by providing a value to evaluated_reliability, for no
        transition leave it None.  This should be an @abstractmethod at some
        point.
        """
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

        self.pCurrentReliability = None
        self.pReliabilityEvaluationInhibit = None

    def execute(self) -> Optional[Reliability]:
        if _debug:
            NoneFaultAlgorithm._debug("execute")

        # no reliability transition
        return None


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

    def execute(self) -> Optional[Reliability]:
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

    def execute(self) -> Optional[Reliability]:
        if _debug:
            ExtendedFaultAlgorithm._debug("execute")

        return Reliability.noFaultDetected


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

    def execute(self) -> Optional[Reliability]:
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

    def execute(self) -> Optional[Reliability]:
        if _debug:
            StatusFlagsFaultAlgorithm._debug("execute")


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
        super().init()

        # normalize the values
        if isinstance(self.pMinimumNormalValue, FaultParameterOutOfRangeValue):
            self.pMinimumNormalValue = getattr(
                self.pMinimumNormalValue, self.pMinimumNormalValue._choice
            )
        if isinstance(self.pMaximumNormalValue, FaultParameterOutOfRangeValue):
            self.pMaximumNormalValue = getattr(
                self.pMaximumNormalValue, self.pMaximumNormalValue._choice
            )

        if _debug:
            OutOfRangeFaultAlgorithm._debug(
                "    - min..max: %r..%r",
                self.pMinimumNormalValue,
                self.pMaximumNormalValue,
            )

    def execute(self) -> Optional[Reliability]:
        if _debug:
            OutOfRangeFaultAlgorithm._debug(
                "execute(%s)", self.monitored_object.objectName
            )
            OutOfRangeFaultAlgorithm._debug(
                "    - what changed: %r", self._what_changed
            )
            OutOfRangeFaultAlgorithm._debug(
                "    - pCurrentReliability: %r", Reliability(self.pCurrentReliability)
            )

        if (self.pCurrentReliability == Reliability.noFaultDetected) and (
            self.pMonitoredValue < self.pMinimumNormalValue
        ):
            return Reliability.underRange
        elif (self.pCurrentReliability == Reliability.noFaultDetected) and (
            self.pMonitoredValue > self.pMaximumNormalValue
        ):
            return Reliability.overRange
        elif (self.pCurrentReliability == Reliability.underRange) and (
            self.pMonitoredValue > self.pMaximumNormalValue
        ):
            return Reliability.overRange
        elif (self.pCurrentReliability == Reliability.overRange) and (
            self.pMonitoredValue < self.pMinimumNormalValue
        ):
            return Reliability.underRange
        elif (
            (self.pCurrentReliability == Reliability.underRange)
            and (self.pMonitoredValue >= self.pMinimumNormalValue)
            and (self.pMonitoredValue <= self.pMaximumNormalValue)
        ):
            return Reliability.noFaultDetected
        elif (
            (self.pCurrentReliability == Reliability.overRange)
            and (self.pMonitoredValue >= self.pMinimumNormalValue)
            and (self.pMonitoredValue <= self.pMaximumNormalValue)
        ):
            return Reliability.noFaultDetected


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
    pMonitoredList: List

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
                pReliabilityEvaluationInhibit=(
                    monitoring_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMonitoredList=monitoring_object.faultParameters.faultListed.faultListReference,
            )
        else:
            self.bind(
                pCurrentReliability=(monitored_object, "reliability"),
                pReliabilityEvaluationInhibit=(
                    monitored_object,
                    "reliabilityEvaluationInhibit",
                ),
                pMonitoredList=(monitored_object, "faultSignals"),
            )

    def execute(self) -> Optional[Reliability]:
        if _debug:
            FaultListedFaultAlgorithm._debug("execute")
