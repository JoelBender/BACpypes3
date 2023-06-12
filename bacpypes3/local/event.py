"""
Event
"""
from __future__ import annotations

import asyncio
from typing import Callable, Dict, Optional, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger, DebugContents
from ..primitivedata import (
    Atomic,
    BitString,
    Boolean,
    CharacterString,
    Double,
    Integer,
    Real,
    Unsigned,
)
from ..basetypes import (
    BinaryPV,
    DateTime,
    DeviceObjectPropertyReference,
    EventState,
    EventTransitionBits,
    LimitEnable,
    NotificationParameters,
    NotificationParametersChangeOfReliabilityType,
    NotificationParametersChangeOfState,
    NotificationParametersOutOfRange,
    ObjectPropertyReference,
    OptionalCharacterString,
    PropertyIdentifier,
    PropertyStates,
    Reliability,
    SequenceOfEventParameterExtendedParameters,
    StatusFlags,
    TimerState,
    TimerTransition,
    TimeStamp,
)
from ..constructeddata import Any, ListOf
from ..object import (
    AccessDoorObject,
    AccessPointObject,
    AccessZoneObject,
    AccumulatorObject,
    AnalogInputObject,
    AnalogOutputObject,
    AnalogValueObject,
    BinaryInputObject,
    BinaryLightingOutputObject,
    BinaryOutputObject,
    BinaryValueObject,
    BitStringValueObject,
    ChannelObject,
    CharacterStringValueObject,
    CredentialDataInputObject,
    EscalatorObject,
    EventEnrollmentObject,
    GlobalGroupObject,
    IntegerValueObject,
    LargeAnalogValueObject,
    LifeSafetyPointObject,
    LifeSafetyZoneObject,
    LiftObject,
    LightingOutputObject,
    LoadControlObject,
    LoopObject,
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
    Object,
    PositiveIntegerValueObject,
    ProgramObject,
    PulseConverterObject,
    StagingObject,
    TimerObject,
)
from .object import Algorithm
from .fault import FaultAlgorithm

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   EventAlgorithm
#


@bacpypes_debugging
class EventAlgorithm(Algorithm, DebugContents):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pCurrentReliability",
        "pReliabilityEvaluationInhibit",
    )

    monitored_object: Object
    monitoring_object: Optional[EventEnrollmentObject]
    fault_algorithm: Optional[FaultAlgorithm]

    pCurrentState: EventState
    pEventDetectionEnable: Boolean
    pEventAlgorithmInhibit: Boolean

    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned
    pNotificationClass: Unsigned
    pEventEnable: EventTransitionBits
    pAckedTransitions: EventTransitionBits

    # if the transition is delayed then the handle is what was returned by
    # call_later() and the state is what it is scheduled to transition to
    _transition_state: Optional[EventState]
    _transition_timeout_handle: Optional[asyncio.Handle]

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            EventAlgorithm._debug("__init__ %r %r", monitoring_object, monitored_object)
        super().__init__()

        # used for reading/writing the Event_State property
        self.monitored_object = monitored_object
        self.monitoring_object = monitoring_object

        # if this is algorithmic reporting and it _also_ has fault detection
        # then the reliability-evaluation output will be from its reference
        if self.monitoring_object and self.monitoring_object._fault_algorithm:
            if self.monitored_object._fault_algorithm:
                raise RuntimeError("fault algorithm conflict")
            self.fault_algorithm = self.monitoring_object._fault_algorithm
        elif self.monitored_object._fault_algorithm:
            # if the monitored object has fault detection, use its output
            self.fault_algorithm = self.monitored_object._fault_algorithm
        else:
            # no fault detection
            self.fault_algorithm = None
        if _debug:
            EventAlgorithm._debug("    - fault_algorithm: %r", self.fault_algorithm)

        # no transition scheduled
        self._transition_state = None
        self._transition_timeout_handle = None

    def bind(self, **kwargs):
        if _debug:
            EventAlgorithm._debug("bind %r", kwargs)

        config_object = self.monitoring_object or self.monitored_object

        kwargs["pCurrentState"] = (config_object, "eventState")
        kwargs["pEventAlgorithmInhibit"] = (config_object, "eventAlgorithmInhibit")
        kwargs["pEventDetectionEnable"] = (config_object, "eventDetectionEnable")

        # continue with binding
        super().bind(**kwargs)

        # check for event algorithm inhibit reference
        eair: Optional[ObjectPropertyReference] = getattr(
            config_object, "eventAlgorithmInhibitRef", None
        )
        if eair:
            # follow the binding to make sure there's something there
            if self.pEventAlgorithmInhibit is None:
                raise RuntimeError(
                    "eventAlgorithmInhibit required when eventAlgorithmInhibitRef provided"
                )

            # resolve the eair.objectIdentifier to point to an object
            eair_object: Optional[Object] = config_object._app.get_object_id(
                eair.objectIdentifier
            )

            # cascade changes to the config object
            def cascade_algorithm_inhibit(old_value, new_value):
                if _debug:
                    EventAlgorithm._debug(
                        "cascade_algorithm_inhibit %r %r", old_value, new_value
                    )

                setattr(config_object, "eventAlgorithmInhibit", new_value)

            # add the property value monitor function
            eair_object._property_monitors[eair.propertyIdentifier].append(
                cascade_algorithm_inhibit
            )

    def _execute(self):
        if _debug:
            EventAlgorithm._debug("_execute")
            EventAlgorithm._debug("    - what changed: %r", self._what_changed)

        # no longer scheduled
        self._execute_handle = None

        # turn off property change notifications
        self._execute_enabled = False

        # snapshot of the current state which can be used in the execute()
        # method and event_notification_parameters
        self._current_state: EventState = self.pCurrentState

        if not self.pEventDetectionEnable:
            if _debug:
                EventAlgorithm._debug("    - event detection disabled")
            """
            If the Event_Detection_Enable property is FALSE, then this state
            machine is not evaluated. In this case, no transitions shall occur,
            Event_State shall be set to NORMAL, and Event_Time_Stamps,
            Event_Message_Texts and Acked_Transitions shall be set to their
            respective initial conditions.
            """
            if self._current_state != EventState.normal:
                if _debug:
                    EventAlgorithm._debug("    - quiet transition to normal")

                config_object = self.monitoring_object or self.monitored_object
                config_object.eventState = EventState.normal

        elif self.fault_algorithm:
            """
            Fault detection takes precedence over the detection of normal and
            offnormal states. As such, when Reliability has a value other than
            NO_FAULT_DETECTED, the event-state-detection process will determine
            the object's event state to be FAULT.
            """
            if (
                self.fault_algorithm.evaluated_reliability
                == Reliability.noFaultDetected
            ):
                if _debug:
                    EventAlgorithm._debug("    - no fault detected")

                if (
                    self.fault_algorithm.pCurrentReliability
                    == Reliability.noFaultDetected
                ):
                    if _debug:
                        EventAlgorithm._debug("    - no reliability change")
                else:
                    if _debug:
                        EventAlgorithm._debug("    - state change from fault to normal")

                    # if there is a monitoring object and its reliability is
                    # monitored-object-fault then it can change to
                    # no-fault-detected, otherwise it reflects the value of the
                    # event enrollment object, Clause 12.12.21
                    if self.fault_algorithm.monitoring_object and (
                        self.fault_algorithm.monitoring_object.reliability
                        == Reliability.monitoredObjectFault
                    ):
                        self.fault_algorithm.monitoring_object.reliability = (
                            Reliability.noFaultDetected
                        )

                    # reliability is an optional, still send notifications
                    if self.fault_algorithm.monitored_object.reliability is not None:
                        self.fault_algorithm.monitored_object.reliability = (
                            Reliability.noFaultDetected
                        )

                    # transition to normal
                    self.state_transition(EventState.normal)

            else:
                if _debug:
                    EventAlgorithm._debug("    - fault detected")

                if self._current_state != EventState.fault:
                    if _debug:
                        EventAlgorithm._debug(
                            "    - state change from normal/offnormal to fault"
                        )

                    # if there is a monitoring object and its reliability is
                    # no-fault-detected then it can change to
                    # monitored-object-fault, otherwise it reflects the value of the
                    # event enrollment object, Clause 12.12.21
                    if self.fault_algorithm.monitoring_object and (
                        self.fault_algorithm.monitoring_object.reliability
                        == Reliability.noFaultDetected
                    ):
                        self.fault_algorithm.monitoring_object.reliability = (
                            Reliability.monitoredObjectFault
                        )

                    # reliability is an optional, still send notifications
                    if self.fault_algorithm.monitored_object.reliability is not None:
                        self.fault_algorithm.monitored_object.reliability = (
                            self.fault_algorithm.evaluated_reliability
                        )

                    # transition to fault
                    self.state_transition(EventState.fault)
                    return

                if (
                    self.fault_algorithm.pCurrentReliability
                    == self.fault_algorithm.evaluated_reliability
                ):
                    if _debug:
                        EventAlgorithm._debug("    - no reliability change")
                else:
                    if _debug:
                        EventAlgorithm._debug("    - state change from fault to fault")

                    # the state hasn't changed so the event enrollment object
                    # reliability doesn't change, just the monitored object
                    self.fault_algorithm.monitored_object.reliability = (
                        self.fault_algorithm.evaluated_reliability
                    )

                    # still fault, but for a different reason
                    self.state_transition(EventState.fault)
                    return

        else:
            if _debug:
                EventAlgorithm._debug("    - no fault detection")

        if "pEventAlgorithmInhibit" in self._what_changed:
            old_value, new_value = self._what_changed["pEventAlgorithmInhibit"]
            if _debug:
                EventAlgorithm._debug(
                    "    - event algorithm inhibit: %r to %r", old_value, new_value
                )

            if new_value:
                """
                Upon Event_Algorithm_Inhibit changing to TRUE, the event shall
                transition to the NORMAL state if not already there. While
                Event_Algorithm_Inhibit remains TRUE, no transitions shall
                occur except those into and out of FAULT.
                """
                # check for possibly pending transition
                if self._transition_timeout_handle:
                    self._transition_timeout_handle.cancel()
                    self._transition_timeout_handle = None

                # transition to normal
                if self._current_state != EventState.normal:
                    self.state_transition(EventState.normal, True)

            else:
                """
                Upon Event_Algorithm_Inhibit changing to FALSE, any condition
                shall hold for its regular time delay after the change to FALSE
                before a transition is generated.
                """
                # let the event algorithm run to see if a transition from
                # something other than normal is still relevant
                self._execute_fn()

        elif self.pEventAlgorithmInhibit:
            if _debug:
                EventAlgorithm._debug("    - event algorithm inhibited")
        else:
            # let the event algorithm run
            self._execute_fn()

        # turn property change notifications back on
        self._execute_enabled = True

        # clear out what changed debugging, turn property monitors back on
        self._what_changed = {}

    def execute(self):
        """
        Using the bound parameters, determine if there should be a change in the
        event state.  This should be an @abstractmethod at some point.
        """
        raise NotImplementedError("execute() not implemented")

    # -----

    def state_transition_delayed(self) -> None:
        """
        This method is called when pTimeDelay and/or pTimeDelayNormal is
        provided and the transition delay has passed.
        """
        if _debug:
            EventAlgorithm._debug(
                "state_transition_delayed %r", EventState(self._transition_state)
            )

        new_state = self._transition_state
        self._transition_state = None
        self._transition_timeout_handle = None

        # transition now please
        self.state_transition(new_state, True)

    def state_transition(self, new_state: EventState, immediate: bool = False) -> None:
        if _debug:
            EventAlgorithm._debug(
                "state_transition %r %r", EventState(new_state), immediate
            )

        if immediate:
            # check for possibly pending transition
            if self._transition_timeout_handle:
                self._transition_state = None
                self._transition_timeout_handle.cancel()
                self._transition_timeout_handle = None
        else:
            if self._transition_timeout_handle:
                if new_state == self._transition_state:
                    if _debug:
                        EventAlgorithm._debug("    - transition already scheduled")
                    return
                else:
                    if _debug:
                        EventAlgorithm._debug("    - canceling old transition")
                    self._transition_state = None
                    self._transition_timeout_handle.cancel()
                    self._transition_timeout_handle = None

            # check for a time delay
            if new_state == EventState.normal:
                time_delay_normal = self.pTimeDelayNormal
                if time_delay_normal is not None:
                    time_delay = time_delay_normal
                else:
                    time_delay = self.pTimeDelay
            else:
                time_delay = self.pTimeDelay
            if _debug:
                EventAlgorithm._debug("    - time_delay: %r", time_delay)

            if time_delay:
                # schedule this to run later
                try:
                    self._transition_state = new_state
                    self._transition_timeout_handle = (
                        asyncio.get_running_loop().call_later(
                            time_delay,
                            self.state_transition_delayed,
                        )
                    )
                except RuntimeError:
                    self._transition_timeout_handle = None
                return

        # evaluate the current state group
        current_state_group: EventState
        if self._current_state == EventState.normal:
            current_state_group = EventState.normal
        elif self._current_state == EventState.fault:
            current_state_group = EventState.fault
        else:
            current_state_group = EventState.offnormal

        # evaluate the new state group
        new_state_group: EventState
        if new_state == EventState.normal:
            new_state_group = EventState.normal
        elif new_state == EventState.fault:
            new_state_group = EventState.fault
        else:
            new_state_group = EventState.offnormal

        # look up a transition function
        fn = EventAlgorithm.transition_functions.get(
            (current_state_group, new_state_group), None
        )
        if not fn:
            raise RuntimeError(
                f"no {EventState(current_state_group)} to {EventState(new_state_group)} transition function"
            )

        # pass along the transition
        fn(self, new_state)

    def transition_action(self, new_state: EventState) -> None:
        """
        Clause 13.2.2.1.4
        """
        if _debug:
            EventAlgorithm._debug("transition_action %r", EventState(new_state))

        # evaluate the new state group
        new_state_group: EventState
        if new_state == EventState.normal:
            new_state_group = EventState.normal
        elif new_state == EventState.fault:
            new_state_group = EventState.fault
        else:
            new_state_group = EventState.offnormal
        if _debug:
            EventAlgorithm._debug("    - new_state_group: %r", new_state_group)

        event_initiating_object = self.monitoring_object or self.monitored_object
        if _debug:
            EventAlgorithm._debug(
                "    - event_initiating_object: %r", event_initiating_object
            )

        # change the event state
        event_initiating_object.eventState = new_state

        # the event arrays are in a different order than event states
        new_state_index = {
            EventState.offnormal: 0,
            EventState.fault: 1,
            EventState.normal: 2,
        }[new_state_group]

        # store the timestamp
        current_time = TimeStamp.as_time()
        event_initiating_object.eventTimeStamps[new_state_index] = current_time

        # store text in eventMessageTexts if present
        if event_initiating_object.eventMessageTexts:
            if event_initiating_object.eventMessageTextsConfig:
                fstring = event_initiating_object.eventMessageTextsConfig[
                    new_state_index
                ]
                event_initiating_object.eventMessageTexts[
                    new_state_index
                ] = fstring.format(**self.__dict__)
            else:
                event_initiating_object.eventMessageTexts[
                    new_state_index
                ] = f"{event_initiating_object.eventState} at {current_time}"

        # Indicate the transition to the Alarm-Acknowledgment process (see
        # Clause 13.2.3) and the event-notification-distribution process (see
        # Clause 13.2.5).

    # -----

    def normal_to_normal(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value of NO_FAULT_DETECTED
        and the event algorithm indicates a transition to the Normal state
        and Event_Algorithm_Inhibit is FALSE, then perform the corresponding
        transition actions and re-enter the Normal state.
        """
        if _debug:
            EventAlgorithm._debug("normal_to_normal %r", EventState(new_state))

    def normal_to_offnormal(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value of NO_FAULT_DETECTED and
        the event algorithm indicates an offnormal event state and
        Event_Algorithm_Inhibit is FALSE, then perform the corresponding
        transition actions (see Clause 13.2.2.1.4) and enter the OffNormal
        state.
        """
        if _debug:
            EventAlgorithm._debug(
                "normal_to_offnormal %r",
                EventState(new_state),
            )

        # if there is no fault algorithm assume no fault detected
        no_fault_detected = (not self.fault_algorithm) or (
            self.fault_algorithm.evaluated_reliability == Reliability.noFaultDetected
        )
        if _debug:
            EventAlgorithm._debug("    - no_fault_detected: %r", no_fault_detected)

        if no_fault_detected and (not self.pEventAlgorithmInhibit):
            self.transition_action(new_state)

    def normal_to_fault(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value other than
        NO_FAULT_DETECTED, then perform the corresponding transition
        actions and enter the Fault state.
        """
        if _debug:
            EventAlgorithm._debug("normal_to_fault %r", EventState(new_state))

    def offnormal_to_normal(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value of NO_FAULT_DETECTED
        and the event algorithm indicates a normal event state, or if
        reliability-evaluation indicates a value of NO_FAULT_DETECTED and
        Event_Algorithm_Inhibit is TRUE, then perform the corresponding
        transition actions and enter the Normal state.
        """
        if _debug:
            EventAlgorithm._debug("offnormal_to_normal %r", EventState(new_state))

        # if there is no fault algorithm assume no fault detected
        no_fault_detected = (not self.fault_algorithm) or (
            self.fault_algorithm.evaluated_reliability == Reliability.noFaultDetected
        )
        if _debug:
            EventAlgorithm._debug("    - no_fault_detected: %r", no_fault_detected)

        if no_fault_detected or self.pEventAlgorithmInhibit:
            self.transition_action(new_state)

    def offnormal_to_offnormal(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value of NO_FAULT_DETECTED
        and the event algorithm indicates a transition to the OffNormal
        state and Event_Algorithm_Inhibit is FALSE, then perform the
        corresponding transition actions and re-enter the OffNormal state.
        """
        if _debug:
            EventAlgorithm._debug("offnormal_to_offnormal %r", EventState(new_state))

        # if there is no fault algorithm assume no fault detected
        no_fault_detected = (not self.fault_algorithm) or (
            self.fault_algorithm.evaluated_reliability == Reliability.noFaultDetected
        )
        if _debug:
            EventAlgorithm._debug("    - no_fault_detected: %r", no_fault_detected)

        if no_fault_detected and (not self.pEventAlgorithmInhibit):
            self.transition_action(new_state)

    def offnormal_to_fault(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value other than
        NO_FAULT_DETECTED, then perform the corresponding transition
        actions and enter the Fault state.
        """
        if _debug:
            EventAlgorithm._debug("offnormal_to_fault %r", EventState(new_state))

    def fault_to_normal(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a value of NO_FAULT_DETECTED,
        then perform the corresponding transition actions and enter the
        Normal state.
        """
        if _debug:
            EventAlgorithm._debug("fault_to_normal %r %r", EventState(new_state))

    def fault_to_fault(self, new_state: EventState) -> None:
        """
        If reliability-evaluation indicates a different Reliability value
        and the new Reliability value is not NO_FAULT_DETECTED or
        reliability-evaluation indicates a transition to the Fault state
        with the same Reliability value, then perform the corresponding
        transition actions and re-enter the Fault state.
        """
        if _debug:
            EventAlgorithm._debug("fault_to_fault %r", EventState(new_state))

    # -----

    def fault_notification_parameters(self) -> NotificationParameters:
        """
        Return the notification parameters for to/from fault states which are
        dependent on the monitored object type.
        """
        if _debug:
            EventAlgorithm._debug("fault_notification_parameters")

        monitored_object = self.fault_algorithm.monitored_object
        properties: Tuple[str, ...] = ()

        if isinstance(monitored_object, (AccessDoorObject,)):
            properties = ("doorAlarmState", "presentValue")
        elif isinstance(monitored_object, (AccessPointObject,)):
            properties = (
                "accessEvent",
                "accessEventTag",
                "accessEventTime",
                "accessEventCredential",
            )
        elif isinstance(monitored_object, (AccessZoneObject,)):
            properties = ("occupancyState",)
        elif isinstance(monitored_object, (AccumulatorObject,)):
            properties = ("pulseRate", "presentValue")
        elif isinstance(
            monitored_object,
            (
                AnalogInputObject,
                AnalogOutputObject,
                AnalogValueObject,
                BinaryInputObject,
                BinaryValueObject,
                BitStringValueObject,
                ChannelObject,
                CharacterStringValueObject,
                GlobalGroupObject,
                IntegerValueObject,
                LargeAnalogValueObject,
                LightingOutputObject,
                MultistateInputObject,
                MultistateValueObject,
                PositiveIntegerValueObject,
                PulseConverterObject,
            ),
        ):
            properties = ("presentValue",)
        elif isinstance(
            monitored_object,
            (BinaryOutputObject, BinaryLightingOutputObject, MultistateOutputObject),
        ):
            properties = ("presentValue", "feedbackValue")
        elif isinstance(monitored_object, (CredentialDataInputObject,)):
            properties = ("updateTime", "presentValue")
        elif isinstance(monitored_object, (EscalatorObject, LiftObject)):
            properties = ("faultSignals",)
        elif isinstance(monitored_object, (EventEnrollmentObject,)):
            properties = ("objectPropertyReference", "reliability", "statusFlags")
        elif isinstance(
            monitored_object, (LifeSafetyPointObject, LifeSafetyZoneObject)
        ):
            properties = ("presentValue", "mode", "operationExpected")
        elif isinstance(monitored_object, (LoadControlObject,)):
            properties = ("presentValue", "requestedShedLevel", "actualShedLevel")
        elif isinstance(monitored_object, (LoopObject,)):
            properties = ("presentValue", "controlledVariableValue", "setpoint")
        elif isinstance(monitored_object, (ProgramObject,)):
            properties = ("programState", "reasonForHalt", "descriptionOfHalt")
        elif isinstance(monitored_object, (StagingObject,)):
            properties = ("presentValue", "presentStage")
        elif isinstance(monitored_object, (TimerObject,)):
            properties = (
                "presentValue",
                "timerState",
                "updateTime",
                "lastStateChange",
                "initialTimeout",
                "expirationTime",
            )
        else:
            raise RuntimeError(f"unsupported object type: {type(monitored_object)}")

        property_values = []
        for attribute_name in properties:
            property_value = getattr(monitored_object, attribute_name)
            if property_value is None:
                continue

            property_values.append(
                PropertyValue(
                    propertyIdentifier=PropertyIdentifier(attribute_name),
                    value=property_value,
                )
            )

        notification_parameters = NotificationParameters(
            changeOfReliability=NotificationParametersChangeOfReliabilityType(
                reliability=self.fault_algorithm.evaluated_reliability,
                statusFlags=monitored_object.statusFlags,
                propertyValues=property_values,
            )
        )

        return notification_parameters

    def event_notification_parameters(self) -> NotificationParameters:
        """
        Return the notification parameters for to/from offnormal states which
        are dependent on the monitored object type.  This should be an
        @abstractmethod at some point.
        """
        if _debug:
            EventAlgorithm._debug("event_notification_parameters")

        raise NotImplementedError("")


EventAlgorithm.transition_functions: Dict[Tuple[int, int], Callable[..., None]] = {
    (EventState.normal, EventState.normal): EventAlgorithm.normal_to_normal,
    (EventState.normal, EventState.offnormal): EventAlgorithm.normal_to_offnormal,
    (EventState.normal, EventState.fault): EventAlgorithm.normal_to_fault,
    (EventState.offnormal, EventState.normal): EventAlgorithm.offnormal_to_normal,
    (EventState.offnormal, EventState.offnormal): EventAlgorithm.offnormal_to_offnormal,
    (EventState.offnormal, EventState.fault): EventAlgorithm.offnormal_to_fault,
    (EventState.fault, EventState.normal): EventAlgorithm.fault_to_normal,
    (EventState.fault, EventState.fault): EventAlgorithm.fault_to_fault,
}

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
    pMonitoredValue: Atomic
    pStatusFlags: StatusFlags
    pAlarmValues: ListOf(Atomic)
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

            # translate the list of values
            list_of_values = []
            for (
                property_state
            ) in monitoring_object.eventParameters.changeOfState.listOfValues:
                property_value = property_state.getattr(property_state._choice)
                list_of_values.append(property_value)
            if _debug:
                ChangeOfStateEventAlgorithm._debug(
                    "    - list_of_values: %r", list_of_values
                )

            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(
                    monitored_object,
                    monitoring_object.objectPropertyReference.propertyIdentifier,
                ),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=list_of_values,
                pTimeDelay=monitoring_object.eventParameters.changeOfState.timeDelay,
                pTimeDelayNormal=None,
            )
        else:
            # intrinsic reporting
            if isinstance(monitored_object, (BinaryInputObject, BinaryValueObject)):
                list_of_values = ListOf(BinaryPV)(
                    [
                        monitored_object.alarmValue,
                    ]
                )
            else:
                list_of_values = monitored_object.alarmValues

            self.bind(
                pCurrentState=(monitored_object, "eventState"),
                pMonitoredValue=(monitored_object, "presentValue"),
                pStatusFlags=(monitored_object, "statusFlags"),
                pAlarmValues=list_of_values,
                pTimeDelay=(monitored_object, "timeDelay"),
                pTimeDelayNormal=(monitored_object, "timeDelayNormal"),
            )

    def execute(self):
        if _debug:
            ChangeOfStateEventAlgorithm._debug("execute")
            ChangeOfStateEventAlgorithm._debug(
                "    - current state: %r", self._current_state
            )

        # assume pTimeDelay and pTimeDelayNormal are both zero for now

        # extract some parameter values
        monitored_value: Atomic = self.pMonitoredValue

        # set a new value
        new_state: Optional[EventState] = None

        """
        (a) If pCurrentState is NORMAL, and pMonitoredValue is equal to any of
        the values contained in pAlarmValues for pTimeDelay, then indicate a
        transition to the OFFNORMAL event state.
        """
        if (self._current_state == EventState.normal) and (
            monitored_value in self.pAlarmValues
        ):
            if _debug:
                ChangeOfStateEventAlgorithm._debug("    - (a)")
            new_state = EventState.offnormal

        """
        (b) If pCurrentState is OFFNORMAL, and pMonitoredValue is not equal to
        any of the values contained in pAlarmValues for pTimeDelayNormal, then
        indicate a transition to the NORMAL event state.
        """
        if (self._current_state == EventState.offnormal) and (
            monitored_value not in self.pAlarmValues
        ):
            if _debug:
                ChangeOfStateEventAlgorithm._debug("    - (b)")
            new_state = EventState.normal

        """
        (c) Optional: If pCurrentState is OFFNORMAL, and pMonitoredValue is
        equal to one of the values contained in pAlarmValues that is different
        from the value that caused the last transition to OFFNORMAL, and remains
        equal to that value for pTimeDelay, then indicate a transition to the
        OFFNORMAL event state.
        """
        # not implemented

        if new_state is not None:
            self.state_transition(new_state)

    def event_notification_parameters(self) -> NotificationParameters:
        if _debug:
            ChangeOfStateEventAlgorithm._debug("event_notification_parameters")

        choice_types = set()
        for choice_type, choice_class in PropertyStates._elements.items():
            parent_class = choice_class.__mro__[1]
            if isinstance(monitored_value, parent_class):
                choice_types.add(choice_type)
        if len(choice_types) != 1:
            raise RuntimeError(f"choice not found: {choice_types}")

        property_states = PropertyStates(**{choice_types.pop(): monitored_value})
        if _debug:
            ChangeOfStateEventAlgorithm._debug(
                "    - property_states: %r", property_states
            )

        notification_parameters = NotificationParameters(
            changeOfState=NotificationParametersChangeOfState(
                newState=property_states,
                statusFlags=self.pStatusFlags,
            ),
        )

        return notification_parameters


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
                "    - current state: %r", self._current_state
            )
            OutOfRangeEventAlgorithm._debug(
                "    - what changed: %r", self._what_changed
            )

        # assume pTimeDelay and pTimeDelayNormal are both zero for now

        limit_enable = self.pLimitEnable or LimitEnable([1, 1])
        if _debug:
            OutOfRangeEventAlgorithm._debug("    - limit_enable: %r", limit_enable)

        status_flags = self.pStatusFlags or StatusFlags([0, 0, 0, 0])
        if _debug:
            OutOfRangeEventAlgorithm._debug("    - status_flags: %r", status_flags)

        monitored_value: Atomic = self.pMonitoredValue
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - monitored_value: %r", monitored_value
            )

        """
        (a) If pCurrentState is NORMAL, and the HighLimitEnable flag of
        pLimitEnable is TRUE, and pMonitoredValue is greater than pHighLimit
        for pTimeDelay, then indicate a transition to the HIGH_LIMIT event
        state.
        """
        if (
            (self._current_state == EventState.normal)
            and limit_enable[LimitEnable.highLimitEnable]
            and (monitored_value > self.pHighLimit)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (a)")
            self.state_transition(EventState.highLimit)
            return

        """
        (b) If pCurrentState is NORMAL, and the LowLimitEnable flag of
        pLimitEnable is TRUE, and pMonitoredValue is less than pLowLimit for
        pTimeDelay, then indicate a transition to the LOW_LIMIT event state.
        """
        if (
            (self._current_state == EventState.normal)
            and limit_enable[LimitEnable.lowLimitEnable]
            and (monitored_value < self.pLowLimit)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (b)")
            self.state_transition(EventState.lowLimit)
            return

        """
        (c) If pCurrentState is HIGH_LIMIT, and the HighLimitEnable flag of
        pLimitEnable is FALSE, then indicate a transition to the NORMAL event
        state.
        """
        if (self._current_state == EventState.highLimit) and (
            not limit_enable[LimitEnable.highLimitEnable]
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (c)")
            self.state_transition(EventState.normal)
            return

        """
        (d) Optional: If pCurrentState is HIGH_LIMIT, and the LowLimitEnable
        flag of pLimitEnable is TRUE, and pMonitoredValue is less than
        pLowLimit for pTimeDelay, then indicate a transition to the LOW_LIMIT
        event state.
        """
        if (
            (self._current_state == EventState.highLimit)
            and limit_enable[LimitEnable.lowLimitEnable]
            and (monitored_value < self.pLowLimit)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (d)")
            self.state_transition(EventState.lowLimit)
            return

        """
        (e) If pCurrentState is HIGH_LIMIT, and pMonitoredValue is less than
        (pHighLimit – pDeadband) for pTimeDelayNormal, then indicate a
        transition to the NORMAL event state.
        """
        if (self._current_state == EventState.highLimit) and (
            monitored_value < (self.pHighLimit - self.pDeadband)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (e)")
            self.state_transition(EventState.normal)
            return

        """
        (f) If pCurrentState is LOW_LIMIT, and the LowLimitEnable flag of
        pLimitEnable is FALSE, then indicate a transition to the NORMAL event
        state.
        """
        if (self._current_state == EventState.lowLimit) and (
            not limit_enable[LimitEnable.lowLimitEnable]
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (f)")
            self.state_transition(EventState.normal)
            return

        """
        (g) Optional: If pCurrentState is LOW_LIMIT, and the HighLimitEnable
        flag of pLimitEnable is TRUE, and pMonitoredValue is greater than
        pHighLimit for pTimeDelay, then indicate a transition to the HIGH_LIMIT
        event state.
        """
        if (
            (self._current_state == EventState.lowLimit)
            and limit_enable[LimitEnable.highLimitEnable]
            and (monitored_value > self.pHighLimit)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (g)")
            self.state_transition(EventState.highLimit)
            return

        """
        (h) If pCurrentState is LOW_LIMIT, and pMonitoredValue is greater than
        (pLowLimit + pDeadband) for pTimeDelayNormal, then indicate a
        transition to the NORMAL event state.
        """
        if (self._current_state == EventState.lowLimit) and (
            monitored_value > (self.pLowLimit + self.pDeadband)
        ):
            if _debug:
                OutOfRangeEventAlgorithm._debug("    - (h)")
            self.state_transition(EventState.normal)
            return

        if _debug:
            OutOfRangeEventAlgorithm._debug("    - (x)")

    def event_notification_parameters(self) -> NotificationParameters:
        if _debug:
            OutOfRangeEventAlgorithm._debug("event_notification_parameters")

        new_state: EventState = self.pCurrentState
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - new_state: %r", EventState(new_state)
            )
        new_status_flags: EventState = self.pStatusFlags
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - new_status_flags: %r", EventState(new_status_flags)
            )

        if (self._current_state == EventState.normal) and (
            new_state == EventState.highLimit
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pHighLimit,
                ),
            )

        if (self._current_state == EventState.normal) and (
            new_state == EventState.lowLimit
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pLowLimit,
                ),
            )

        if (self._current_state == EventState.highLimit) and (
            new_state == EventState.normal
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pHighLimit,
                ),
            )

        if (self._current_state == EventState.highLimit) and (
            new_state == EventState.lowLimit
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pLowLimit,
                ),
            )

        if (self._current_state == EventState.highLimit) and (
            new_state == EventState.normal
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pHighLimit,
                ),
            )

        if (self._current_state == EventState.lowLimit) and (
            new_state == EventState.normal
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pLowLimit,
                ),
            )

        if (self._current_state == EventState.lowLimit) and (
            new_state == EventState.highLimit
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pHighLimit,
                ),
            )

        if (self._current_state == EventState.lowLimit) and (
            new_state == EventState.normal
        ):
            notification_parameters = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pLowLimit,
                ),
            )

        return notification_parameters


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

    Used when only fault detection is in use by an object.  The Event
    Enrollment object evaluates reliability only and does not apply an event
    algorithm.
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
