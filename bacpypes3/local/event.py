"""
Event
"""
from __future__ import annotations

import asyncio
from typing import Any as _Any, Callable, Dict, Optional, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger, DebugContents
from ..pdu import (
    Address,
    LocalBroadcast,
    LocalStation,
    RemoteBroadcast,
    RemoteStation,
)
from ..primitivedata import (
    Atomic,
    BitString,
    Boolean,
    CharacterString,
    Double,
    Integer,
    Real,
    Unsigned,
    Date,
    Time,
)
from ..basetypes import (
    BinaryPV,
    DateTime,
    DeviceObjectPropertyReference,
    EventState,
    EventTransitionBits,
    EventType,
    FaultType,
    LimitEnable,
    NotificationParameters,
    NotificationParametersChangeOfReliabilityType,
    NotificationParametersChangeOfState,
    NotificationParametersOutOfRange,
    ObjectPropertyReference,
    OptionalCharacterString,
    PropertyIdentifier,
    PropertyStates,
    PropertyValue,
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
    EventEnrollmentObject as _EventEnrollmentObject,
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
    PositiveIntegerValueObject,
    ProgramObject,
    PulseConverterObject,
    StagingObject,
    TimerObject,
)
from ..apdu import (
    APDU,
    ConfirmedEventNotificationRequest,
    UnconfirmedEventNotificationRequest,
)
from .object import (
    Algorithm,
    Object,
)
from .fault import FaultAlgorithm, OutOfRangeFaultAlgorithm

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

    event_type: EventType = None

    monitored_object: Object
    monitoring_object: Optional[EventEnrollmentObject]
    fault_algorithm: Optional[FaultAlgorithm]

    pCurrentState: EventState
    pCurrentReliability: Reliability
    pEventDetectionEnable: Boolean
    pEventAlgorithmInhibit: Boolean

    pTimeDelay: Unsigned
    pTimeDelayNormal: Unsigned
    pNotificationClass: Unsigned
    pEventEnable: EventTransitionBits
    pAckedTransitions: EventTransitionBits

    _current_state: Optional[EventState]

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
        kwargs["pCurrentReliability"] = (config_object, "reliability")
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
            if not eair_object:
                raise RuntimeError(
                    f"eventAlgorithmInhibitRef object not found: {eair.objectIdentifier}"
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

        # snapshot of the current state
        self._current_state: EventState = self.pCurrentState
        if _debug:
            EventAlgorithm._debug("    - _current_state: %r", self._current_state)

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

            self._what_changed = {}
            return

        evaluated_reliability: Optional[Reliability] = None
        current_reliability: Optional[Reliability] = self.pCurrentReliability
        if _debug:
            EventAlgorithm._debug(
                "    - current_reliability: %r",
                current_reliability,
            )
        if current_reliability is None:
            # this can only be the case when there is no monitoring object
            # (intrinsic event reporting) and the monitored object has
            # no reliability property
            if _debug:
                EventAlgorithm._debug("    - event state detection only")

            if self.fault_algorithm:
                # the evaluated reliability will be None if there is no change
                evaluated_reliability = self.fault_algorithm.evaluated_reliability
            else:
                evaluated_reliability = None

        if "pCurrentReliability" in self._what_changed:
            # this change occurs when (a) the monitored object reliability has
            # changed due to intrinsic fault detection, or (b) when the
            # monitored object is out-of-service and the reliability is
            # changed, (c) when the monitoring event enrollment object has had
            # its innate reliability changed.
            old_value, new_value = self._what_changed.pop("pCurrentReliability")
            if _debug:
                EventAlgorithm._debug(
                    "    - reliability changed: %r to %r", old_value, new_value
                )
            evaluated_reliability = current_reliability

        if _debug:
            EventAlgorithm._debug(
                "    - evaluated_reliability: %r",
                evaluated_reliability,
            )

        if evaluated_reliability is not None:
            """
            Fault detection takes precedence over the detection of normal and
            offnormal states. As such, when Reliability has a value other than
            NO_FAULT_DETECTED, the event-state-detection process will determine
            the object's event state to be FAULT.
            """
            if evaluated_reliability == Reliability.noFaultDetected:
                if _debug:
                    EventAlgorithm._debug("    - no fault detected")

                if self._current_state == EventState.normal:
                    if _debug:
                        EventAlgorithm._debug("    - already normal")
                else:
                    if _debug:
                        EventAlgorithm._debug("    - state change from fault to normal")

                    # transition to normal
                    self.state_transition(EventState.normal)
                    return

            else:
                if _debug:
                    EventAlgorithm._debug("    - fault detected")

                if self._current_state != EventState.fault:
                    if _debug:
                        EventAlgorithm._debug(
                            "    - state change from normal/offnormal to fault"
                        )

                    # transition to fault
                    self.state_transition(EventState.fault)

                elif self.fault_algorithm.pCurrentReliability == evaluated_reliability:
                    if _debug:
                        EventAlgorithm._debug("    - no reliability change")
                else:
                    if _debug:
                        EventAlgorithm._debug(
                            "    - state change from one fault to another"
                        )

                    # still fault, but for a different reason
                    self.state_transition(EventState.fault)
                return

        else:
            if _debug:
                EventAlgorithm._debug("    - no reliability change")

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

    def state_transition_cancel(self) -> None:
        """
        This method is called to cancel a transition that has been scheduled.
        """
        if _debug:
            EventAlgorithm._debug("state_transition_cancel")

        self._transition_state = None
        self._transition_timeout_handle.cancel()
        self._transition_timeout_handle = None

    def state_transition(
        self, new_state: Optional[EventState], immediate: bool = False
    ) -> None:
        """
        Request a transition to a new state, or new_state is None then the
        current state is acceptable.
        """
        if _debug:
            EventAlgorithm._debug(
                "state_transition %r immediate=%r",
                EventState(new_state) if new_state is not None else None,
                immediate,
            )
            EventAlgorithm._debug(
                "    - current state: %r", EventState(self._current_state)
            )
            EventAlgorithm._debug(
                "    - transition state: %r",
                EventState(self._transition_state)
                if self._transition_timeout_handle
                else None,
            )

        if new_state is not None:
            # a new state is being requested
            if self._transition_timeout_handle:
                if new_state == self._transition_state:
                    if _debug:
                        EventAlgorithm._debug("    - transition already scheduled")
                    return

                if new_state == self._current_state:
                    if _debug:
                        EventAlgorithm._debug("    - canceling old transition (1)")
                    self.state_transition_cancel()
                    return

        else:
            # no new state is being requested, current state is fine
            if self._transition_timeout_handle and (
                self._current_state != self._transition_state
            ):
                if _debug:
                    EventAlgorithm._debug(
                        "    - current state no longer needs to be transition state (2)"
                    )
                self.state_transition_cancel()
                return

        # check for possibly pending transition
        if immediate:
            if self._transition_timeout_handle:
                if _debug:
                    EventAlgorithm._debug("    - canceling old transition (3)")
                self.state_transition_cancel()
        else:
            if self._transition_timeout_handle:
                if new_state == self._transition_state:
                    if _debug:
                        EventAlgorithm._debug("    - transition already scheduled")
                    return

                if _debug:
                    EventAlgorithm._debug("    - canceling old transition (4)")
                self.state_transition_cancel()

                if new_state == self._current_state:
                    if _debug:
                        EventAlgorithm._debug("    - transition noop")
                    return

            if new_state is None:
                if _debug:
                    EventAlgorithm._debug("    - no transition")
                return

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
                if _debug:
                    EventAlgorithm._debug("    - schedule to run %ds later", time_delay)

                # schedule this to run later
                self._transition_state = new_state
                self._transition_timeout_handle = asyncio.get_running_loop().call_later(
                    time_delay,
                    self.state_transition_delayed,
                )
                return

        event_initiating_object = self.monitoring_object or self.monitored_object
        if _debug:
            EventAlgorithm._debug(
                "    - event_initiating_object: %r", event_initiating_object
            )

        # save the current state for building notifications
        old_state: EventState = self._current_state

        # evaluate the current state group
        old_state_group: EventState
        if old_state == EventState.normal:
            old_state_group = EventState.normal
        elif old_state == EventState.fault:
            old_state_group = EventState.fault
        else:
            old_state_group = EventState.offnormal

        # evaluate the new state group
        new_state_group: EventState
        if new_state == EventState.normal:
            new_state_group = EventState.normal
        elif new_state == EventState.fault:
            new_state_group = EventState.fault
        else:
            new_state_group = EventState.offnormal

        # turn off property change notifications
        self._execute_enabled = False

        # make the transition
        self.pCurrentState = new_state
        # self._current_state = new_state

        # turn property change notifications back on
        self._execute_enabled = True

        # the event arrays are in a different order than event states
        new_state_index = {
            EventState.offnormal: 0,
            EventState.fault: 1,
            EventState.normal: 2,
        }[new_state_group]

        # store the timestamp
        time_stamp = TimeStamp.as_time()
        event_initiating_object.eventTimeStamps[new_state_index] = time_stamp

        # store text in eventMessageTexts if present
        message_text: Optional[str]
        if event_initiating_object.eventMessageTexts:
            if event_initiating_object.eventMessageTextsConfig:
                fstring = event_initiating_object.eventMessageTextsConfig[
                    new_state_index
                ]
                message_text = fstring.format(**self.__dict__)
            else:
                message_text = f"{event_initiating_object.eventState} at {time_stamp}"
            event_initiating_object.eventMessageTexts[new_state_index] = message_text
        else:
            message_text = None

        # build up event notification request parameters
        notification_parameters: Dict[str, _Any] = {
            # processIdentifier in recipient list element
            "initiatingDeviceIdentifier": event_initiating_object._app.device_object.objectIdentifier,
            "eventObjectIdentifier": event_initiating_object.objectIdentifier,
            "timeStamp": time_stamp,
            "notificationClass": event_initiating_object.notificationClass,
            "priority": event_initiating_object._notification_class_object.priority[
                new_state_group
            ],
            "messageText": message_text,
            "notifyType": event_initiating_object.notifyType,
            "ackRequired": event_initiating_object._notification_class_object.ackRequired[
                new_state_group
            ],
            "fromState": old_state,
            "toState": new_state,
        }

        if (old_state_group == EventState.fault) or (
            new_state_group == EventState.fault
        ):
            # Notify Type will be ALARM or EVENT and not ACK_NOTIFICATION, so this
            # is always CHANGE_OF_RELIABILITY, Clause 13.9.1.1.7
            notification_parameters["eventType"] = EventType.changeOfReliability
            notification_parameters[
                "eventValues"
            ] = self.fault_notification_parameters()
        else:
            notification_parameters["eventType"] = self.event_type
            notification_parameters[
                "eventValues"
            ] = self.event_notification_parameters()

        # pass these parameters to send out confirmed or unconfirmed event
        # notification requests
        asyncio.ensure_future(self.send_notifications(notification_parameters))

        # if this is a fault-to-normal transition, schedule another evaluation
        # to see if normal is still appropriate or it needs to go to off-normal
        if (old_state_group == EventState.fault) and (
            new_state_group == EventState.normal
        ):
            asyncio.get_event_loop().call_soon(self._execute)

    # -----

    async def send_notifications(
        self, notification_parameters: Dict[str, _Any]
    ) -> None:
        if _debug:
            EventAlgorithm._debug("send_notifications %r", notification_parameters)

        event_initiating_object = self.monitoring_object or self.monitored_object
        notification_class_object = event_initiating_object._notification_class_object
        if _debug:
            EventAlgorithm._debug(
                "    - event_initiating_object: %r", event_initiating_object
            )
            EventAlgorithm._debug(
                "    - notification_class_object: %r", notification_class_object
            )

        # my goodness, look at the time
        current_date = Date.now()
        current_time = Time.now()
        if _debug:
            EventAlgorithm._debug(
                "    - current_date, current_time: %r, %r", current_date, current_time
            )

        # build up a set of request calls
        recipient_futures = set()

        for destination in notification_class_object.recipientList:
            if _debug:
                EventAlgorithm._debug("    - destination: %r", destination)
            if not destination.validDays[3]:
                if _debug:
                    EventAlgorithm._debug("    - not today")
                continue
            if (current_time < destination.fromTime) or (
                current_time > destination.toTime
            ):
                if _debug:
                    EventAlgorithm._debug("    - not now")
                continue

            # evaluate the new state index
            new_state = notification_parameters["toState"]
            if new_state == EventState.normal:
                new_state_index = 2
            elif new_state == EventState.fault:
                new_state_index = 1
            else:
                new_state_index = 0
            if not destination.transitions[new_state_index]:
                if _debug:
                    EventAlgorithm._debug("    - not these transitions")
                continue

            # get the recipient
            recipient = destination.recipient
            if _debug:
                EventAlgorithm._debug("    - recipient: %r", recipient)

            # get its address
            pdu_destination: Address
            if recipient.device:
                device_info = await event_initiating_object._app.device_info_cache.get_device_info(
                    recipient.device[1]
                )
                if not device_info:
                    if _debug:
                        EventAlgorithm._debug("    - no device info")
                    continue
                pdu_destination = device_info.address
            elif recipient.address:
                network_number = recipient.address.networkNumber
                mac_address = recipient.address.macAddress

                if network_number == 0:
                    if not mac_address:
                        pdu_destination = LocalBroadcast()
                    else:
                        pdu_destination = LocalStation(mac_address)
                else:
                    if not mac_address:
                        pdu_destination = RemoteBroadcast(network_number)
                    else:
                        pdu_destination = RemoteStation(network_number, mac_address)
            else:
                raise RuntimeError("invalid recipient")
            if _debug:
                EventAlgorithm._debug("    - pdu_destination: %r", pdu_destination)

            # make an APDU
            notification_request: APDU
            if destination.issueConfirmedNotifications:
                notification_request = ConfirmedEventNotificationRequest(
                    **notification_parameters
                )
            else:
                notification_request = UnconfirmedEventNotificationRequest(
                    **notification_parameters
                )

            # set the destination and process identifier
            notification_request.pduDestination = pdu_destination
            notification_request.processIdentifier = destination.processIdentifier

            # pass along to the application
            recipient_futures.add(
                event_initiating_object._app.request(notification_request)
            )

        # might not be any notifications to send out
        if not recipient_futures:
            if _debug:
                EventAlgorithm._debug("    - no requests to send")
            return

        # wait for them all to complete
        done, pending = await asyncio.wait(recipient_futures)
        if _debug:
            EventAlgorithm._debug("    - done: %r", done)
            EventAlgorithm._debug("    - pending: %r", pending)

        # look for exceptions, which _should_ be mapped back to resolving
        # problems with the recipient
        for request_future in done:
            try:
                request_exception = request_future.exception()
                if not request_exception:
                    continue
                if _debug:
                    EventAlgorithm._debug(
                        "    - request exception: %r", request_exception
                    )
            except asyncio.CancelledError:
                if _debug:
                    EventAlgorithm._debug("    - cancelled error: %r")

    # -----

    def fault_notification_parameters(self) -> NotificationParameters:
        """
        Return a dictionary of the parameters to the confirmed and unconfirmed
        event notification services.  The eventValues (of type NotificationParameters)
        for to/from fault states are dependent on the monitored object type.
        """
        if _debug:
            EventAlgorithm._debug("fault_notification_parameters")
            EventAlgorithm._debug(
                "    - _current_state: %r", EventState(self._current_state)
            )

        monitored_object = self.monitored_object
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
                MultiStateInputObject,
                MultiStateValueObject,
                PositiveIntegerValueObject,
                PulseConverterObject,
            ),
        ):
            properties = ("presentValue",)
        elif isinstance(
            monitored_object,
            (BinaryOutputObject, BinaryLightingOutputObject, MultiStateOutputObject),
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

        return NotificationParameters(
            changeOfReliability=NotificationParametersChangeOfReliabilityType(
                reliability=self.pCurrentReliability,
                statusFlags=monitored_object.statusFlags,
                propertyValues=property_values,
            ),
        )

    # -----

    def event_notification_parameters(self) -> NotificationParameters:
        """
        Return the notification parameters for to/from offnormal states which
        are dependent on the event detection algorithm.  This should be an
        @abstractmethod at some point.
        """
        if _debug:
            EventAlgorithm._debug("event_notification_parameters")
            EventAlgorithm._debug(
                "    - _current_state: %r", EventState(self._current_state)
            )

        raise NotImplementedError("")


#
#   ChangeOfBitstringEventAlgorithm
#


@bacpypes_debugging
class ChangeOfBitstringEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.1
    """

    event_type = EventType.changeOfBitstring

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
        raise NotImplementedError("CHANGE_OF_BITSTRING not implemented")


#
#   ChangeOfStateEventAlgorithm
#


@bacpypes_debugging
class ChangeOfStateEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.2
    """

    event_type = EventType.changeOfState

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
                property_value = getattr(property_state, property_state._choice)
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
            self.state_transition(EventState.offnormal)
            return

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
            self.state_transition(EventState.normal)
            return

        """
        (c) Optional: If pCurrentState is OFFNORMAL, and pMonitoredValue is
        equal to one of the values contained in pAlarmValues that is different
        from the value that caused the last transition to OFFNORMAL, and remains
        equal to that value for pTimeDelay, then indicate a transition to the
        OFFNORMAL event state.
        """
        # not implemented

        if _debug:
            ChangeOfStateEventAlgorithm._debug("    - (x)")
        self.state_transition(None)

    def event_notification_parameters(self) -> NotificationParameters:
        """
        Return the notification parameters for to/from offnormal states.
        """
        if _debug:
            ChangeOfStateEventAlgorithm._debug("event_notification_parameters")
            ChangeOfStateEventAlgorithm._debug(
                "    - _current_state: %r", EventState(self._current_state)
            )

        # extract some parameter values
        monitored_value: Atomic = self.pMonitoredValue

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

        return NotificationParameters(
            changeOfState=NotificationParametersChangeOfState(
                newState=property_states,
                statusFlags=self.pStatusFlags,
            ),
        )


#
#   ChangeOfValueEventAlgorithm
#


@bacpypes_debugging
class ChangeOfValueEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.2
    """

    event_type = EventType.changeOfValue

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
        raise NotImplementedError("CHANGE_OF_VALUE not implemented")


#
#   CommandFailureEventAlgorithm
#


@bacpypes_debugging
class CommandFailureEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.4
    """

    event_type = EventType.commandFailure

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
        raise NotImplementedError("COMMAND_FAILURE not implemented")


#
#   FloatingLimitEventAlgorithm
#


@bacpypes_debugging
class FloatingLimitEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.5
    """

    event_type = EventType.floatingLimit

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
            if spr:
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
        raise NotImplementedError("FLOATING_LIMIT not implemented")


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

    event_type = EventType.outOfRange

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
        self.state_transition(None)

    def event_notification_parameters(self) -> NotificationParameters:
        """
        Return the notification parameters for to/from offnormal states.
        """
        if _debug:
            OutOfRangeEventAlgorithm._debug("event_notification_parameters")
            OutOfRangeEventAlgorithm._debug(
                "    - _current_state: %r", EventState(self._current_state)
            )

        new_state: EventState = self.pCurrentState
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - new_state: %r", EventState(new_state)
            )
        new_status_flags: StatusFlags = self.pStatusFlags
        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - new_status_flags: %r",
                new_status_flags,
            )

        # nothing yet
        event_values: Optional[NotificationParameters] = None

        if (self._current_state == EventState.normal) and (
            new_state == EventState.highLimit
        ):
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
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
            event_values = NotificationParameters(
                outOfRange=NotificationParametersOutOfRange(
                    exceedingValue=self.pMonitoredValue,
                    statusFlags=new_status_flags,
                    deadband=self.pDeadband,
                    exceededLimit=self.pLowLimit,
                ),
            )

        if _debug:
            OutOfRangeEventAlgorithm._debug(
                "    - event_values: %r",
                event_values,
            )
        assert event_values

        return event_values


#
#   BufferReadyEventAlgorithm
#


@bacpypes_debugging
class BufferReadyEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.7
    """

    event_type = EventType.bufferReady

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
        raise NotImplementedError("BUFFER_READY not implemented")


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

    event_type = EventType.unsignedRange

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
        raise NotImplementedError("UNSIGNED_RANGE not implemented")


#
#   ExtendedEventAlgorithm
#


@bacpypes_debugging
class ExtendedEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.10
    """

    event_type = EventType.extended

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
        raise NotImplementedError("EXTENDED not implemented")


#
#   ChangeOfStatusFlags
#


@bacpypes_debugging
class ChangeOfStatusFlags(EventAlgorithm):
    """
    Clause 13.3.11
    """

    event_type = EventType.changeOfStatusFlags

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
        raise NotImplementedError("CHANGE_OF_STATUS_FLAGS not implemented")


#
#   AccessEventEventAlgorithm
#


@bacpypes_debugging
class AccessEventEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.12
    """

    event_type = EventType.accessEvent

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            AccessEventEventAlgorithm._debug("__init__ %r", monitored_object)
        raise NotImplementedError("ACCESS_EVENT")


#
#   DoubleOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class DoubleOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.13
    """

    event_type = EventType.doubleOutOfRange

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
        raise NotImplementedError("DOUBLE_OUT_OF_RANGE not implemented")


#
#   SignedOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class SignedOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.13
    """

    event_type = EventType.signedOutOfRange

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
        raise NotImplementedError("SIGNED_OUT_OF_RANGE not implemented")


#
#   UnsignedOutOfRangeEventAlgorithm
#


@bacpypes_debugging
class UnsignedOutOfRangeEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.15
    """

    event_type = EventType.unsignedOutOfRange

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
        raise NotImplementedError("UNSIGNED_OUT_OF_RANGE not implemented")


#
#   ChangeOfCharacterStringEventAlgorithm
#


@bacpypes_debugging
class ChangeOfCharacterStringEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.16
    """

    event_type = EventType.changeOfCharacterstring

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
        raise NotImplementedError("CHANGE_OF_CHARACTERSTRING not implemented")


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

    event_type = EventType.none

    def __init__(
        self,
        monitoring_object: Optional[EventEnrollmentObject],
        monitored_object: Object,
    ):
        if _debug:
            NoneEventEventAlgorithm._debug(
                "__init__ %r %r", monitoring_object, monitored_object
            )
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

    event_type = EventType.changeOfDiscreteValue

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
        raise NotImplementedError("CHANGE_OF_DISCRETE_VALUE not implemented")


#
#   ChangeOfTimerEventAlgorithm
#


@bacpypes_debugging
class ChangeOfTimerEventAlgorithm(EventAlgorithm):
    """
    Clause 13.3.19
    """

    event_type = EventType.changeOfTimer

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
            ChangeOfTimerEventAlgorithm._debug("__init__ %r", monitored_object)
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
            ChangeOfTimerEventAlgorithm._debug("execute")
        raise NotImplementedError("CHANGE_OF_TIMER not implemented")


#
#   EventEnrollmentObject
#


@bacpypes_debugging
class EventEnrollmentObject(Object, _EventEnrollmentObject):
    """ """

    _debug: Callable[..., None]
    _event_algorithm: EventAlgorithm
    _fault_algorithm: FaultAlgorithm
    _monitored_object: Object

    __reliability: Reliability = Reliability("no-fault-detected")

    def __init__(self, **kwargs):
        if _debug:
            EventEnrollmentObject._debug("__init__ ...")
        super().__init__(**kwargs)

    async def _post_init(self):
        """
        This function is called after all of the objects are added to the
        application so that the objectPropertyReference property can
        find the correct object and the algorithms can be set.
        """
        if _debug:
            EventEnrollmentObject._debug("_post_init")

        # checks for notification class reference
        await super()._post_init()

        # look up the object being monitored
        dopr: DeviceObjectPropertyReference = self.objectPropertyReference
        if dopr.propertyArrayIndex is not None:
            raise NotImplementedError()
        if dopr.deviceIdentifier is not None:
            raise NotImplementedError()

        self._monitored_object: Object = self._app.get_object_id(dopr.objectIdentifier)
        if not self._monitored_object:
            raise RuntimeError("object not found")

        # the type of fault algorithm is based on the faultType property
        fault_type: FaultType = self.faultType
        if (fault_type is None) or (fault_type == FaultType.none):
            self._fault_algorithm = None
        elif fault_type == FaultType.faultOutOfRange:
            self._fault_algorithm = OutOfRangeFaultAlgorithm(
                self, self._monitored_object
            )
        else:
            self._fault_algorithm = None
        if _debug:
            EventEnrollmentObject._debug(
                "    - _fault_algorithm: %r",
                self._fault_algorithm,
            )

        # the type of event algorithm is based on the eventType property
        event_type: EventType = self.eventType
        if event_type is None:
            self._event_algorithm = None
        elif event_type == EventType.outOfRange:
            self._event_algorithm = OutOfRangeEventAlgorithm(
                self, self._monitored_object
            )
        elif event_type == EventType.changeOfState:
            self._event_algorithm = ChangeOfStateEventAlgorithm(
                self, self._monitored_object
            )
        else:
            raise NotImplementedError(f"event type not implemented: {event_type}")
        if _debug:
            EventEnrollmentObject._debug(
                "    - _event_algorithm: %r",
                self._event_algorithm,
            )

    @property
    def reliability(self) -> Reliability:
        """Return the reliability of the object, Clause 12.12.21."""
        if _debug:
            Object._debug("reliability(getter)")

        evaluated_reliability = self.__reliability
        if self.__reliability == Reliability.noFaultDetected:
            if self._monitored_object.reliability != Reliability.noFaultDetected:
                evaluated_reliability = Reliability("monitored-object-fault")
            elif self._fault_algorithm:
                evaluated_reliability = self._fault_algorithm.evaluated_reliability

        return evaluated_reliability

    @reliability.setter
    def reliability(self, value: Reliability) -> None:
        """
        Change the reliability of this object.
        """
        if _debug:
            Object._debug("reliability(setter) %r", value)
        if value is None:
            raise ValueError("reliability")

        # make sure it's the correct type
        if not isinstance(value, Reliability):
            value = Reliability.cast(value)

        self.__reliability = value
