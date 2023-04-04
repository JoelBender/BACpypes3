"""
Object
"""
# mypy: ignore-errors

from __future__ import annotations

import sys
import inspect
from functools import partial

from typing import (
    cast,
    Any as _Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Union,
)

from .debugging import ModuleLogger, bacpypes_debugging
from .primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Integer,
    ObjectIdentifier,
    ObjectType,
    OctetString,
    Real,
    Time,
    Unsigned,
    Unsigned16,
    Unsigned8,
)

from .constructeddata import (
    AnyAtomic,
    ArrayOf,
    ListOf,
    Sequence,
    SequenceMetaclass,
)
from .basetypes import (
    AccessCredentialDisable,
    AccessCredentialDisableReason,
    AccessEvent,
    AccessPassbackMode,
    AccessRule,
    AccessThreatLevel,
    AccessUserType,
    AccessZoneOccupancyState,
    AccumulatorRecord,
    Action,
    ActionList,
    AddressBinding,
    AssignedAccessRights,
    AssignedLandingCalls,
    AuditLevel,
    AuditLogRecord,
    AuditOperationFlags,
    AuthenticationFactor,
    AuthenticationFactorFormat,
    AuthenticationPolicy,
    AuthenticationStatus,
    AuthorizationException,
    AuthorizationMode,
    BackupState,
    BDTEntry,
    BinaryLightingPV,
    BinaryPV,
    CalendarEntry,
    ChannelValue,
    ClientCOV,
    COVMultipleSubscription,
    COVSubscription,
    CredentialAuthenticationFactor,
    DailySchedule,
    DateRange,
    DateTime,
    Destination,
    DeviceObjectPropertyReference,
    DeviceObjectReference,
    DeviceStatus,
    DoorAlarmState,
    DoorSecuredStatus,
    DoorStatus,
    DoorValue,
    EngineeringUnits,
    EscalatorFault,
    EscalatorMode,
    EscalatorOperationDirection,
    EventLogRecord,
    EventNotificationSubscription,
    EventParameter,
    EventState,
    EventTransitionBits,
    EventType,
    FaultParameter,
    FaultType,
    FDTEntry,
    FileAccessMethod,
    HostNPort,
    IPMode,
    IPv4OctetString,
    IPv6OctetString,
    LandingCallStatus,
    LandingDoorStatus,
    LifeSafetyMode,
    LifeSafetyOperation,
    LifeSafetyState,
    LiftCarCallList,
    LiftCarDirection,
    LiftCarDoorCommand,
    LiftCarDriveStatus,
    LiftCarMode,
    LiftFault,
    LiftGroupMode,
    LightingCommand,
    LightingInProgress,
    LightingTransition,
    LimitEnable,
    LockStatus,
    LoggingType,
    LogMultipleRecord,
    LogRecord,
    Maintenance,
    MACAddress,
    NameValue,
    NameValueCollection,
    NetworkNumberQuality,
    NetworkPortCommand,
    NetworkSecurityPolicy,
    NetworkType,
    NodeType,
    NotifyType,
    ObjectPropertyReference,
    ObjectSelector,
    ObjectTypesSupported,
    OptionalBinaryPV,
    OptionalCharacterString,
    OptionalPriorityFilter,
    OptionalReal,
    OptionalUnsigned,
    Polarity,
    PortPermission,
    Prescale,
    PriorityFilter,
    PriorityValue,
    ProcessIdSelection,
    ProgramError,
    ProgramRequest,
    ProgramState,
    PropertyAccessResult,
    PropertyIdentifier,
    ProtocolLevel,
    ReadAccessResult,
    ReadAccessSpecification,
    Recipient,
    Relationship,
    Reliability,
    RestartReason,
    RouterEntry,
    Scale,
    SecurityKeySet,
    SecurityLevel,
    Segmentation,
    ServicesSupported,
    SessionKey,
    SetpointReference,
    ShedLevel,
    ShedState,
    SilencedState,
    SpecialEvent,
    StageLimitValue,
    StatusFlags,
    TimerState,
    TimerStateChangeValue,
    TimerTransition,
    TimeStamp,
    ValueSource,
    VMACEntry,
    VTClass,
    VTSession,
    WriteStatus,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


#
#   VendorInfo
#


ASHRAE_vendor_info: VendorInfo
_vendor_info: Dict[int, VendorInfo] = {}


def get_vendor_info(vendor_identifier: int) -> VendorInfo:
    global _vendor_info, ASHRAE_vendor_info

    return _vendor_info.get(vendor_identifier, ASHRAE_vendor_info)


@bacpypes_debugging
class VendorInfo:
    _debug: Callable[..., None]

    vendor_identifier: int
    registered_object_classes: Dict[int, type] = {}

    object_type: type
    object_identifier: type
    property_identifier: type

    def __init__(
        self,
        vendor_identifier: int,
        object_type: Optional[type] = None,
        property_identifier: Optional[type] = None,
    ) -> None:
        if _debug:
            VendorInfo._debug("__init__ %r ...", vendor_identifier)
        global _vendor_info

        # put this in the global map
        if vendor_identifier in _vendor_info:
            raise RuntimeError(
                f"vendor identifier already registered: {vendor_identifier!r}"
            )

        assert vendor_identifier not in _vendor_info
        _vendor_info[vendor_identifier] = self

        self.vendor_identifier = vendor_identifier
        self.registered_object_classes = {}

        # reference the object type class
        if object_type:
            self.object_type = object_type

            # build an object identifier class with the specialized object type
            self.object_identifier = type(
                "ObjectIdentifier!",
                (ObjectIdentifier,),
                {
                    "_vendor_id": vendor_identifier,
                    "object_type_class": object_type,
                },
            )
        else:
            self.object_type = ObjectType
            self.object_identifier = ObjectIdentifier

        # there might be special property identifiers
        self.property_identifier = property_identifier or PropertyIdentifier

    def register_object_class(self, object_type: int, object_class: type) -> None:
        if _debug:
            VendorInfo._debug(
                "register_object_class(%d) %r %r",
                self.vendor_identifier,
                object_type,
                object_class,
            )
        if object_type in self.registered_object_classes:
            raise RuntimeError(
                f"object type {object_type!r}"
                f" for vendor identifier {self.vendor_identifier}"
                f" already registered: {self.registered_object_classes[object_type]}"
            )

        self.registered_object_classes[object_type] = object_class

    def get_object_class(self, object_type: int) -> Optional[type]:
        return self.registered_object_classes.get(
            object_type, None
        ) or ASHRAE_vendor_info.registered_object_classes.get(
            object_type, None
        )  # type: ignore[attr-defined]


# ASHRAE is Vendor ID 0
ASHRAE_vendor_info = VendorInfo(0)


@bacpypes_debugging
class ObjectMetaclass(SequenceMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __new__(
        cls: _Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, _Any],
    ) -> ObjectMetaclass:
        if _debug:
            ObjectMetaclass._debug(
                "ObjectMetaclass.__new__ %r %r %r %r",
                cls,
                clsname,
                superclasses,
                attributedict,
            )
        global _vendor_info

        # pretend this is any other sequence
        metaclass = cast(
            ObjectMetaclass,
            super(ObjectMetaclass, cls).__new__(
                cls, clsname, superclasses, attributedict
            ),
        )
        if _debug:
            ObjectMetaclass._debug("    - metaclass: %r", metaclass)
            ObjectMetaclass._debug("    - metaclass._elements: %r", metaclass._elements)  # type: ignore[attr-defined]

        # find the vendor identifier in the class definition
        _vendor_id = None
        if "_vendor_id" in attributedict:
            _vendor_id = attributedict["_vendor_id"]
            if _debug:
                ObjectMetaclass._debug(f"    - class vendor_id: {_vendor_id}")
        else:
            # check the module
            cls_module = inspect.getmodule(metaclass)
            assert cls_module
            if _debug:
                ObjectMetaclass._debug(
                    f"    - cls_module: {cls_module} {cls_module.__name__}"
                )

            _vendor_id = getattr(cls_module, "_vendor_id", None)
            if _vendor_id is not None:
                if _debug:
                    ObjectMetaclass._debug(
                        f"    - module {cls_module} vendor_id: {_vendor_id}"
                    )
            else:
                # check the parent module
                parent_module = sys.modules[
                    ".".join(cls_module.__name__.split(".")[:-1]) or "__main__"
                ]
                if _debug:
                    ObjectMetaclass._debug(f"    - parent_module: {parent_module}")
                _vendor_id = getattr(parent_module, "_vendor_id", None)
                if _vendor_id is not None:
                    if _debug:
                        ObjectMetaclass._debug(
                            f"    - parent module {parent_module} vendor_id: {_vendor_id}"
                        )
                else:
                    # check the superclasses that are in the same module
                    for supercls in superclasses:
                        supercls_module = inspect.getmodule(supercls)
                        if _debug:
                            ObjectMetaclass._debug(
                                f"    - supercls {supercls} module: {supercls_module}"
                            )
                        if supercls_module is not cls_module:
                            continue

                        _vendor_id = getattr(supercls, "_vendor_id", None)
                        if _vendor_id is not None:
                            if _debug:
                                ObjectMetaclass._debug(
                                    f"    - supercls {supercls} vendor_id: {_vendor_id}"
                                )
                            break

        # this could be the core Object class (defined below) which is not
        # associated with any vendor.  This module has _vendor_id set to zero
        # for the ASHRAE classes just before they are defined
        if _vendor_id is None:
            return metaclass

        # save a reference in the class
        metaclass._vendor_id = _vendor_id  # type: ignore[attr-defined]

        # find the vendor information for this vendor
        vendor_info = _vendor_info.get(_vendor_id, None)
        if not vendor_info:
            raise RuntimeError(
                f"no vendor information for vendor identifier: {_vendor_id}"
            )

        # if this class doesn't have a type it is a "generic" class that is
        # inherited by other classes for the vendor.  The LocalObject class
        # is an example.
        if not hasattr(metaclass, "objectType"):
            return metaclass

        # register this class
        vendor_info.register_object_class(metaclass.objectType, metaclass)

        # the object classes are in the vendor information, pass them along
        metaclass._object_identifier_class = vendor_info.object_identifier
        metaclass._property_identifier_class = vendor_info.property_identifier

        # find the elements that are not property identifiers
        bad_identifiers = set.difference(
            set(metaclass._elements),  # type: ignore[attr-defined]
            set(vendor_info.property_identifier._enum_map),  # type: ignore[attr-defined]
        )
        if bad_identifiers:
            raise AttributeError(
                "not a property identifier: " + ", ".join(bad_identifiers)
            )

        return metaclass


@bacpypes_debugging
class Object(Sequence, metaclass=ObjectMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    _vendor_id: int  # set by the metaclass
    _object_identifier_class = ObjectIdentifier
    _property_identifier_class = PropertyIdentifier

    _app: _Any  # used when added to an application
    _required = ("objectIdentifier", "objectName", "objectType", "propertyList")

    objectIdentifier: ObjectIdentifier
    objectName: CharacterString(_min_length=1)
    objectType: ObjectType
    description: CharacterString
    propertyList: ArrayOf(PropertyIdentifier)
    auditLevel: AuditLevel
    auditableOperations: AuditOperationFlags
    # auditPriorityFilter: OptionalPriorityFilter -- object specific
    tags: ArrayOf(NameValue)
    profileLocation: CharacterString
    profileName: CharacterString

    def __init__(
        self, init_dict: Optional[Dict[str, _Any]] = None, **kwargs: _Any
    ) -> None:
        if _debug:
            Object._debug("__init__ %r %r", init_dict, kwargs)

        # not added to an application
        self._app = None

        # check the initialization dictionary values
        if init_dict:
            for attr, value in init_dict.items():
                attr = self._property_identifier_class(attr).attr
                if attr not in self._elements:
                    raise AttributeError(f"not a property: {attr!r}")
                if attr in kwargs:
                    raise ValueError(f"initialization conflict: {attr!r}")
                kwargs[attr] = value

        # check the object identifier type
        if "objectIdentifier" in kwargs:
            object_identifier = kwargs["objectIdentifier"]
            if not isinstance(object_identifier, self._object_identifier_class):
                object_identifier = self._object_identifier_class.cast(
                    object_identifier
                )
            kwargs["objectIdentifier"] = object_identifier

        # initialize from prototypes not otherwise given as a kwarg
        if _debug:
            Object._debug("    - _inits: %r", self._inits)
        for attr, value in self._inits.items():
            if attr not in kwargs:
                kwargs[attr] = value

        super().__init__(**kwargs)

    @classmethod
    def get_property_type(cls, attr: Union[int, str, PropertyIdentifier]) -> _Any:
        """Given a property identifier, return its type, its associated class."""
        if _debug:
            Object._debug("get_property_type %r %r", cls, attr)

        # convert the string, which could be 'presentValue' or 'present-value'
        # to a property identifier so it can be normalized to the attribute
        # form in the next step
        if isinstance(attr, (int, str)):
            attr = cls._property_identifier_class(attr)

        # use the "attribute" form of the property identifier, e.g.,
        # 'presentValue', to look up the element
        return cls._elements.get(attr.attr, None)

    async def read_property(  # type: ignore[override]
        self,
        attr: Union[int, str],
        index: Optional[int] = None,
    ) -> _Any:
        if _debug:
            Object._debug("read_property %r %r", attr, index)

        if isinstance(attr, int):
            attr = self._property_identifier_class(attr).attr
        if attr not in self._elements:
            raise AttributeError(f"not a property: {attr!r}")

        element = self._elements[attr]

        class_attr = getattr(self.__class__, attr, None)
        if isinstance(class_attr, property):
            if _debug:
                Object._debug("    - reading from a property")
            getattr_fn = class_attr.fget
            if getattr_fn:
                getattr_fn = partial(getattr_fn, self)
        else:
            if _debug:
                Object._debug("    - not reading from a property")
            getattr_fn = partial(super().__getattribute__, attr)

        value = await element.read_property(
            getter=getattr_fn,
            index=index,
        )
        if _debug:
            Object._debug("    - value: %r", value)

        return value

    async def write_property(  # type: ignore[override]
        self,
        attr: Union[int, str],
        value: _Any,
        index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        if _debug:
            Object._debug("write_property %r %r %r %r", attr, value, index, priority)
        if isinstance(attr, int):
            attr = self._property_identifier_class(attr).attr
        if attr not in self._elements:
            raise AttributeError(f"not a property: {attr!r}")

        element = self._elements[attr]

        class_attr = getattr(self.__class__, attr, None)
        if isinstance(class_attr, property):
            if _debug:
                Object._debug("    - writing to a property")
            getattr_fn = class_attr.fget
            if getattr_fn:
                getattr_fn = partial(getattr_fn, self)
            setattr_fn = class_attr.fset
            if setattr_fn:
                setattr_fn = partial(setattr_fn, self)
        else:
            if _debug:
                Object._debug("    - not writing to a property")
            getattr_fn = partial(super().__getattribute__, attr)
            setattr_fn = partial(super().__setattr__, attr)

        value = await element.write_property(
            getter=getattr_fn,
            setter=setattr_fn,
            value=value,
            index=index,
            priority=priority,
        )


#
#   Objects
#

_vendor_id = 0


class AccessCredentialObject(Object):
    _required = (
        "globalIdentifier",
        "statusFlags",
        "reliability",
        "credentialStatus",
        "reasonForDisable",
        "authenticationFactors",
        "activationTime",
        "expirationTime",
        "credentialDisable",
        "assignedAccessRights",
    )
    objectType = ObjectType("accessCredential")
    globalIdentifier: Unsigned
    statusFlags: StatusFlags
    reliability: Reliability
    credentialStatus: BinaryPV
    reasonForDisable: ListOf(AccessCredentialDisableReason)
    authenticationFactors: ArrayOf(CredentialAuthenticationFactor)
    activationTime: DateTime
    expirationTime: DateTime
    credentialDisable: AccessCredentialDisable
    daysRemaining: Integer
    usesRemaining: Integer
    absenteeLimit: Unsigned
    belongsTo: DeviceObjectReference
    assignedAccessRights: ArrayOf(AssignedAccessRights)
    lastAccessPoint: DeviceObjectReference
    lastAccessEvent: AccessEvent
    lastUseTime: DateTime
    traceFlag: Boolean
    threatAuthority: AccessThreatLevel
    extendedTimeEnable: Boolean
    authorizationExemptions: ListOf(AuthorizationException)
    reliabilityEvaluationInhibit: Boolean


class AccessDoorObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "priorityArray",
        "relinquishDefault",
        "doorPulseTime",
        "doorExtendedPulseTime",
        "doorOpenTooLongTime",
        "currentCommandPriority",
    )
    objectType = ObjectType("accessDoor")
    presentValue: DoorValue
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: DoorValue
    doorStatus: DoorStatus
    lockStatus: LockStatus
    securedStatus: DoorSecuredStatus
    doorMembers: ArrayOf(DeviceObjectReference)
    doorPulseTime: Unsigned
    doorExtendedPulseTime: Unsigned
    doorUnlockDelayTime: Unsigned
    doorOpenTooLongTime: Unsigned
    doorAlarmState: DoorAlarmState
    maskedAlarmValues: ListOf(DoorAlarmState)
    maintenanceRequired: Maintenance
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ListOf(DoorAlarmState)
    faultValues: ListOf(DoorAlarmState)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class AccessPointObject(Object):
    _required = (
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "authenticationStatus",
        "activeAuthenticationPolicy",
        "numberOfAuthenticationPolicies",
        "accessEvent",
        "accessEventTag",
        "accessEventTime",
        "accessEventCredential",
        "accessDoors",
        "priorityForWriting",
    )
    objectType = ObjectType("accessPoint")
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    authenticationStatus: AuthenticationStatus
    activeAuthenticationPolicy: Unsigned
    numberOfAuthenticationPolicies: Unsigned
    authenticationPolicyList: ArrayOf(AuthenticationPolicy)
    authenticationPolicyNames: ArrayOf(CharacterString)
    authorizationMode: AuthorizationMode
    verificationTime: Unsigned
    lockout: Boolean
    lockoutRelinquishTime: Unsigned
    failedAttempts: Unsigned
    failedAttemptEvents: ListOf(AccessEvent)
    maxFailedAttempts: Unsigned
    failedAttemptsTime: Unsigned
    threatLevel: AccessThreatLevel
    occupancyUpperLimitEnforced: Boolean
    occupancyLowerLimitEnforced: Boolean
    occupancyCountAdjust: Boolean
    accompanimentTime: Unsigned
    accessEvent: AccessEvent
    accessEventTag: Unsigned
    accessEventTime: TimeStamp
    accessEventCredential: DeviceObjectReference
    accessEventAuthenticationFactor: AuthenticationFactor
    accessDoors: ArrayOf(DeviceObjectReference)
    priorityForWriting: Unsigned
    musterPoint: Boolean
    zoneTo: DeviceObjectReference
    zoneFrom: DeviceObjectReference
    notificationClass: Unsigned
    transactionNotificationClass: Unsigned
    accessAlarmEvents: ListOf(AccessEvent)
    accessTransactionEvents: ListOf(AccessEvent)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean


class AccessRightsObject(Object):
    _required = (
        "globalIdentifier",
        "statusFlags",
        "reliability",
        "enable",
        "negativeAccessRules",
        "positiveAccessRules",
    )
    objectType = ObjectType("accessRights")
    globalIdentifier: Unsigned
    statusFlags: StatusFlags
    reliability: Reliability
    enable: Boolean
    negativeAccessRules: ArrayOf(AccessRule)
    positiveAccessRules: ArrayOf(AccessRule)
    accompaniment: DeviceObjectReference
    reliabilityEvaluationInhibit: Boolean


class AccessUserObject(Object):
    _required = (
        "globalIdentifier",
        "statusFlags",
        "reliability",
        "userType",
        "credentials",
    )
    objectType = ObjectType("accessUser")
    globalIdentifier: Unsigned
    statusFlags: StatusFlags
    reliability: Reliability
    userType: AccessUserType
    userName: CharacterString
    userExternalIdentifier: CharacterString
    userInformationReference: CharacterString
    members: ListOf(DeviceObjectReference)
    memberOf: ListOf(DeviceObjectReference)
    credentials: ListOf(DeviceObjectReference)
    reliabilityEvaluationInhibit: Boolean


class AccessZoneObject(Object):
    _required = (
        "globalIdentifier",
        "occupancyState",
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "entryPoints",
        "exitPoints",
    )
    objectType = ObjectType("accessZone")
    globalIdentifier: Unsigned
    occupancyState: AccessZoneOccupancyState
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    occupancyCount: Unsigned
    occupancyCountEnable: Boolean
    adjustValue: Integer
    occupancyUpperLimit: Unsigned
    occupancyLowerLimit: Unsigned
    credentialsInZone: ListOf(DeviceObjectReference)
    lastCredentialAdded: DeviceObjectReference
    lastCredentialAddedTime: DateTime
    lastCredentialRemoved: DeviceObjectReference
    lastCredentialRemovedTime: DateTime
    passbackMode: AccessPassbackMode
    passbackTimeout: Unsigned
    entryPoints: ListOf(DeviceObjectReference)
    exitPoints: ListOf(DeviceObjectReference)
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ListOf(AccessZoneOccupancyState)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean


class AccumulatorObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "scale",
        "units",
        "maxPresValue",
    )
    objectType = ObjectType("accumulator")
    presentValue: Unsigned
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    scale: Scale
    units: EngineeringUnits
    prescale: Prescale
    maxPresValue: Unsigned
    valueChangeTime: DateTime
    valueBeforeChange: Unsigned
    valueSet: Unsigned
    loggingRecord: AccumulatorRecord
    loggingObject: ObjectIdentifier
    pulseRate: Unsigned
    highLimit: Unsigned
    lowLimit: Unsigned
    limitMonitoringInterval: Unsigned
    notificationClass: Unsigned
    timeDelay: Unsigned
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    faultHighLimit: Unsigned
    faultLowLimit: Unsigned


class AlertEnrollmentObject(Object):
    _required = (
        "presentValue",
        "eventState",
        "eventDetectionEnable",
        "notificationClass",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
    )
    objectType = ObjectType("alertEnrollment")
    presentValue: ObjectIdentifier
    eventState: EventState
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean


class AnalogInputObject(Object):
    _required = ("presentValue", "statusFlags", "eventState", "outOfService", "units")
    objectType = ObjectType("analogInput")
    presentValue: Real
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    updateInterval: Unsigned
    units: EngineeringUnits
    minPresValue: Real
    maxPresValue: Real
    resolution: Real
    covIncrement: Real
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Real
    lowLimit: Real
    deadband: Real
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalReal
    faultHighLimit: Real
    faultLowLimit: Real


class AnalogOutputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "units",
        "priorityArray",
        "relinquishDefault",
        "currentCommandPriority",
    )
    objectType = ObjectType("analogOutput")
    presentValue: Real
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    minPresValue: Real
    maxPresValue: Real
    resolution: Real
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Real
    covIncrement: Real
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Real
    lowLimit: Real
    deadband: Real
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalReal
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class AnalogValueObject(Object):
    _required = ("presentValue", "statusFlags", "eventState", "outOfService", "units")
    objectType = ObjectType("analogValue")
    presentValue: Real
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    minPresValue: Real
    maxPresValue: Real
    resolution: Real
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Real
    covIncrement: Real
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Real
    lowLimit: Real
    deadband: Real
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    faultHighLimit: Real
    faultLowLimit: Real
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class AuditLogObject(Object):
    _required = (
        "statusFlags" "eventState",
        "enable",
        "bufferSize",
        "logBuffer",
        "recordCount",
        "totalRecordCount",
    )
    objectType = ObjectType("auditLog")
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    enable: Boolean
    bufferSize: Unsigned
    logBuffer: ListOf(AuditLogRecord)
    recordCount: Unsigned
    totalRecordCount: Unsigned
    memberOf: DeviceObjectReference
    deleteOnForward: Boolean
    issueConfirmedNotifications: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class AuditReporterObject(Object):
    _required = (
        "statusFlags",
        "reliability",
        "eventState",
        "auditSourceReporter",
        "auditableOperations",
        "auditPriorityFilter",
        "issueConfirmedNotifications",
    )
    objectType = ObjectType("auditReporter")
    statusFlags: StatusFlags
    reliability: Reliability
    eventState: EventState
    auditLevel: AuditLevel
    auditSourceReporter: Boolean
    auditableOperations: AuditOperationFlags
    auditPriorityFilter: PriorityFilter
    issueConfirmedNotifications: Boolean
    monitoredObjects: ArrayOf(ObjectSelector)
    maximumSendDelay: Unsigned
    sendNow: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class AveragingObject(Object):
    _required = (
        "minimumValue",
        "averageValue",
        "maximumValue",
        "attemptedSamples",
        "validSamples",
        "objectPropertyReference",
        "windowInterval",
        "windowSamples",
    )
    objectType = ObjectType("averaging")
    minimumValue: Real
    minimumValueTimestamp: DateTime
    averageValue: Real
    varianceValue: Real
    maximumValue: Real
    maximumValueTimestamp: DateTime
    attemptedSamples: Unsigned
    validSamples: Unsigned
    objectPropertyReference: DeviceObjectPropertyReference
    windowInterval: Unsigned
    windowSamples: Unsigned


class BinaryInputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "polarity",
    )
    objectType = ObjectType("binaryInput")
    presentValue: BinaryPV
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    polarity: Polarity
    inactiveText: CharacterString
    activeText: CharacterString
    changeOfStateTime: DateTime
    changeOfStateCount: Unsigned
    timeOfStateCountReset: DateTime
    elapsedActiveTime: Unsigned
    timeOfActiveTimeReset: DateTime
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValue: BinaryPV
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalBinaryPV


class BinaryLightingOutputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "outOfService",
        "blinkWarnEnable",
        "egressTime",
        "egressActive",
        "priorityArray",
        "relinquishDefault",
        "lightingCommandDefaultPriority",
        "currentCommandPriority",
    )
    objectType = ObjectType("binaryLightingOutput")
    presentValue: BinaryLightingPV
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    blinkWarnEnable: Boolean
    egressTime: Unsigned
    egressActive: Boolean
    feedbackValue: BinaryLightingPV
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: BinaryLightingPV
    power: Real
    polarity: Polarity
    elapsedActiveTime: Unsigned
    timeOfActiveTimeReset: DateTime
    strikeCount: Unsigned
    timeOfStrikeCountReset: DateTime
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class BinaryOutputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "polarity",
        "priorityArray",
        "relinquishDefault",
        "currentCommandPriority",
    )
    objectType = ObjectType("binaryOutput")
    presentValue: BinaryPV
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    polarity: Polarity
    inactiveText: CharacterString
    activeText: CharacterString
    changeOfStateTime: DateTime
    changeOfStateCount: Unsigned
    timeOfStateCountReset: DateTime
    elapsedActiveTime: Unsigned
    timeOfActiveTimeReset: DateTime
    minimumOffTime: Unsigned
    minimumOnTime: Unsigned
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: BinaryPV
    timeDelay: Unsigned
    notificationClass: Unsigned
    feedbackValue: BinaryPV
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalBinaryPV
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class BinaryValueObject(Object):
    _required = ("presentValue", "statusFlags", "eventState", "outOfService")
    objectType = ObjectType("binaryValue")
    presentValue: BinaryPV
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    inactiveText: CharacterString
    activeText: CharacterString
    changeOfStateTime: DateTime
    changeOfStateCount: Unsigned
    timeOfStateCountReset: DateTime
    elapsedActiveTime: Unsigned
    timeOfActiveTimeReset: DateTime
    minimumOffTime: Unsigned
    minimumOnTime: Unsigned
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: BinaryPV
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValue: BinaryPV
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class BitStringValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("bitstringValue")
    presentValue: BitString
    bitText: ArrayOf(CharacterString)
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: BitString
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ArrayOf(BitString)
    bitMask: BitString
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class CalendarObject(Object):
    _required = ("presentValue", "dateList")
    objectType = ObjectType("calendar")
    presentValue: Boolean
    dateList: ListOf(CalendarEntry)


class ChannelObject(Object):
    _required = (
        "presentValue",
        "lastPriority",
        "writeStatus",
        "statusFlags",
        "outOfService",
        "listOfObjectPropertyReferences",
        "channelNumber",
        "controlGroups",
    )
    objectType = ObjectType("channel")
    presentValue: ChannelValue
    lastPriority: Unsigned
    writeStatus: WriteStatus
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    listOfObjectPropertyReferences: ArrayOf(DeviceObjectPropertyReference)
    executionDelay: ArrayOf(Unsigned)
    allowGroupDelayInhibit: Boolean
    channelNumber: Unsigned
    controlGroups: ArrayOf(Unsigned)
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    eventState: EventState
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean
    valueSource: ValueSource
    auditPriorityFilter: OptionalPriorityFilter


class CharacterStringValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("characterstringValue")
    presentValue: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: CharacterString
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ArrayOf(OptionalCharacterString)
    faultValues: ArrayOf(OptionalCharacterString)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class CommandObject(Object):
    _required = ("presentValue", "inProcess", "allWritesSuccessful", "action")
    objectType = ObjectType("command")
    presentValue: Unsigned
    inProcess: Boolean
    allWritesSuccessful: Boolean
    action: ArrayOf(ActionList)
    actionText: ArrayOf(CharacterString)
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean
    valueSource: ValueSource


class CredentialDataInputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "reliability",
        "outOfService",
        "supportedFormats",
        "updateTime",
    )
    objectType = ObjectType("credentialDataInput")
    presentValue: AuthenticationFactor
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    supportedFormats: ArrayOf(AuthenticationFactorFormat)
    supportedFormatClasses: ArrayOf(Unsigned)
    updateTime: TimeStamp
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class DatePatternValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("datePatternValue")
    presentValue: Date
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Date
    reliabilityEvaluationInhibit: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class DateTimePatternValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("datetimePatternValue")
    presentValue: DateTime
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    isUTC: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: DateTime
    reliabilityEvaluationInhibit: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class DateTimeValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("datetimeValue")
    presentValue: DateTime
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: DateTime
    isUTC: Boolean
    reliabilityEvaluationInhibit: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class DateValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("dateValue")
    presentValue: Date
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Date
    reliabilityEvaluationInhibit: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class DeviceObject(Object):
    _required = (
        "systemStatus",
        "vendorName",
        "vendorIdentifier",
        "modelName",
        "firmwareRevision",
        "applicationSoftwareVersion",
        "protocolVersion",
        "protocolRevision",
        "protocolServicesSupported",
        "protocolObjectTypesSupported",
        "objectList",
        "maxApduLengthAccepted",
        "segmentationSupported",
        "apduTimeout",
        "numberOfApduRetries",
        "deviceAddressBinding",
        "databaseRevision",
    )
    # objectIdentifier: ObjectIdentifier
    # objectName: CharacterString(_min_length=1)
    objectType = ObjectType("device")
    systemStatus: DeviceStatus
    vendorName: CharacterString
    vendorIdentifier: Unsigned
    modelName: CharacterString
    firmwareRevision: CharacterString
    applicationSoftwareVersion: CharacterString
    location: CharacterString
    # description: CharacterString
    protocolVersion: Unsigned
    protocolRevision: Unsigned
    protocolServicesSupported: ServicesSupported
    protocolObjectTypesSupported: ObjectTypesSupported
    objectList: ArrayOf(ObjectIdentifier)
    structuredObjectList: ArrayOf(ObjectIdentifier)
    maxApduLengthAccepted: Unsigned
    segmentationSupported: Segmentation
    maxSegmentsAccepted: Unsigned
    vtClassesSupported: ListOf(VTClass)
    activeVtSessions: ListOf(VTSession)
    localTime: Time
    localDate: Date
    utcOffset: Integer
    daylightSavingsStatus: Boolean
    apduSegmentTimeout: Unsigned
    apduTimeout: Unsigned
    numberOfApduRetries: Unsigned
    listOfSessionKeys: ListOf(SessionKey)
    timeSynchronizationRecipients: ListOf(Recipient)
    maxMaster: Unsigned
    maxInfoFrames: Unsigned
    deviceAddressBinding: ListOf(AddressBinding)
    databaseRevision: Unsigned
    configurationFiles: ArrayOf(ObjectIdentifier)
    lastRestoreTime: TimeStamp
    backupFailureTimeout: Unsigned
    activeCovSubscriptions: ListOf(COVSubscription)
    lastRestartReason: RestartReason
    timeOfDeviceRestart: TimeStamp
    restartNotificationRecipients: ListOf(Recipient)
    utcTimeSynchronizationRecipients: ListOf(Recipient)
    timeSynchronizationInterval: Unsigned
    alignIntervals: Boolean
    intervalOffset: Unsigned
    backupPreparationTime: Unsigned
    restorePreparationTime: Unsigned
    restoreCompletionTime: Unsigned
    backupAndRestoreState: BackupState
    # propertyList: ArrayOf(PropertyIdentifier)
    serialNumber: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean
    activeCovMultipleSubscriptions: ListOf(COVMultipleSubscription)
    auditNotificationRecipient: Recipient
    auditLevel: AuditLevel
    auditableOperations: AuditOperationFlags
    deviceUUID: OctetString
    # tags: ArrayOf(NameValue)
    # profileLocation: CharacterString
    # deployedProfileLocation: CharacterString
    # profileName: CharacterString


class ElevatorGroupObject(Object):
    _required = ("machineRoomID", "groupID", "groupMembers")
    objectType = ObjectType("elevatorGroup")
    machineRoomID: ObjectIdentifier
    groupID: Unsigned8
    groupMembers: ArrayOf(ObjectIdentifier)
    groupMode: LiftGroupMode
    landingCalls: ListOf(LandingCallStatus)
    landingCallControl: LandingCallStatus


class EscalatorObject(Object):
    _required = (
        "statusFlags",
        "elevatorGroup",
        "groupID",
        "installationID",
        "operationDirection",
        "outOfService",
        "passengerAlarm",
    )
    objectType = ObjectType("escalator")
    statusFlags: StatusFlags
    elevatorGroup: ObjectIdentifier
    groupID: Unsigned8
    installationID: Unsigned8
    powerMode: Boolean
    operationDirection: EscalatorOperationDirection
    escalatorMode: EscalatorMode
    energyMeter: Real
    energyMeterRef: DeviceObjectReference
    reliability: Reliability
    outOfService: Boolean
    faultSignals: ListOf(EscalatorFault)
    passengerAlarm: Boolean
    timeDelay: Unsigned
    timeDelayNormal: Unsigned
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    eventState: EventState
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventAlgorithmInhibit: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    reliabilityEvaluationInhibit: Boolean


class EventEnrollmentObject(Object):
    _required = (
        "eventType",
        "notifyType",
        "eventParameters",
        "objectPropertyReference",
        "eventState",
        "eventEnable",
        "ackedTransitions",
        "notificationClass",
        "eventTimeStamps",
        "eventDetectionEnable",
        "statusFlags",
        "reliability",
    )
    objectType = ObjectType("eventEnrollment")
    eventType: EventType
    notifyType: NotifyType
    eventParameters: EventParameter
    objectPropertyReference: DeviceObjectPropertyReference
    eventState: EventState
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notificationClass: Unsigned
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    statusFlags: StatusFlags
    reliability: Reliability
    faultType: FaultType
    faultParameters: FaultParameter
    reliabilityEvaluationInhibit: Boolean


class EventLogObject(Object):
    _required = (
        "statusFlags",
        "eventState",
        "enable",
        "stopWhenFull",
        "bufferSize",
        "logBuffer",
        "recordCount",
        "totalRecordCount",
    )
    objectType = ObjectType("eventLog")
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    enable: Boolean
    startTime: DateTime
    stopTime: DateTime
    stopWhenFull: Boolean
    bufferSize: Unsigned
    logBuffer: ListOf(EventLogRecord)
    recordCount: Unsigned
    totalRecordCount: Unsigned
    notificationThreshold: Unsigned
    recordsSinceNotification: Unsigned
    lastNotifyRecord: Unsigned
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean


class FileObject(Object):
    _required = (
        "fileType",
        "fileSize",
        "modificationDate",
        "archive",
        "readOnly",
        "fileAccessMethod",
    )
    objectType = ObjectType("file")
    fileType: CharacterString
    fileSize: Unsigned
    modificationDate: DateTime
    archive: Boolean
    readOnly: Boolean
    fileAccessMethod: FileAccessMethod
    recordCount: Unsigned


class GlobalGroupObject(Object):
    _required = (
        "groupMembers",
        "presentValue",
        "statusFlags",
        "eventState",
        "memberStatusFlags",
        "outOfService",
        "",
        "",
    )
    objectType = ObjectType("globalGroup")
    groupMembers: ArrayOf(DeviceObjectPropertyReference)
    groupMemberNames: ArrayOf(CharacterString)
    presentValue: ArrayOf(PropertyAccessResult)
    statusFlags: StatusFlags
    eventState: EventState
    memberStatusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    updateInterval: Unsigned
    requestedUpdateInterval: Unsigned
    covResubscriptionInterval: Unsigned
    clientCovIncrement: ClientCOV
    timeDelay: Unsigned
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    covuPeriod: Unsigned
    covuRecipients: ListOf(Recipient)
    reliabilityEvaluationInhibit: Boolean


class GroupObject(Object):
    _required = ("listOfGroupMembers", "presentValue")
    objectType = ObjectType("group")
    listOfGroupMembers: ListOf(ReadAccessSpecification)
    presentValue: ListOf(ReadAccessResult)


class IntegerValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("integerValue")
    presentValue: Integer
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Integer
    covIncrement: Unsigned
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Integer
    lowLimit: Integer
    deadband: Unsigned
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    minPresValue: Integer
    maxPresValue: Integer
    resolution: Integer
    faultHighLimit: Integer
    faultLowLimit: Integer
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class LargeAnalogValueObject(Object):
    _required = ("presentValue", "statusFlags", "units")
    objectType = ObjectType("largeAnalogValue")
    presentValue: Double
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Integer
    covIncrement: Unsigned
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Double
    lowLimit: Double
    deadband: Double
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    minPresValue: Double
    maxPresValue: Double
    resolution: Double
    faultHighLimit: Double
    faultLowLimit: Double
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class LifeSafetyPointObject(Object):
    _required = (
        "presentValue",
        "trackingValue",
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "mode",
        "acceptedModes",
        "silenced",
        "operationExpected",
    )
    objectType = ObjectType("lifeSafetyPoint")
    presentValue: LifeSafetyState
    trackingValue: LifeSafetyState
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    mode: LifeSafetyMode
    acceptedModes: ListOf(LifeSafetyMode)
    timeDelay: Unsigned
    notificationClass: Unsigned
    lifeSafetyAlarmValues: ListOf(LifeSafetyState)
    alarmValues: ListOf(LifeSafetyState)
    faultValues: ListOf(LifeSafetyState)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    silenced: SilencedState
    operationExpected: LifeSafetyOperation
    maintenanceRequired: Maintenance
    setting: Unsigned
    directReading: Real
    units: EngineeringUnits
    memberOf: ListOf(DeviceObjectReference)
    floorNumber: Unsigned8
    valueSource: ValueSource


class LifeSafetyZoneObject(Object):
    _required = (
        "presentValue",
        "trackingValue",
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "mode",
        "acceptedModes",
        "silenced",
        "operationExpected",
        "zomeMembers",
    )
    objectType = ObjectType("lifeSafetyZone")
    presentValue: LifeSafetyState
    trackingValue: LifeSafetyState
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    mode: LifeSafetyMode
    acceptedModes: ListOf(LifeSafetyMode)
    timeDelay: Unsigned
    notificationClass: Unsigned
    lifeSafetyAlarmValues: ListOf(LifeSafetyState)
    alarmValues: ListOf(LifeSafetyState)
    faultValues: ListOf(LifeSafetyState)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    silenced: SilencedState
    operationExpected: LifeSafetyOperation
    maintenanceRequired: Boolean
    zoneMembers: ListOf(DeviceObjectReference)
    memberOf: ListOf(DeviceObjectReference)
    floorNumber: Unsigned8
    valueSource: ValueSource


class LiftObject(Object):
    _required = (
        "statusFlags",
        "elevatorGroup",
        "groupID",
        "installationID",
        "carPosition",
        "carMovingDirection",
        "carDoorStatus",
        "passengerAlarm",
        "outOfService",
        "faultSignals",
    )
    objectType = ObjectType("lift")
    trackingValue: Real
    statusFlags: StatusFlags
    elevatorGroup: ObjectIdentifier
    groupID: Unsigned8
    installationID: Unsigned8
    floorText: ArrayOf(CharacterString)
    carDoorText: ArrayOf(CharacterString)
    assignedLandingCalls: ArrayOf(AssignedLandingCalls)
    makingCarCall: ArrayOf(Unsigned8)
    registeredCarCall: ArrayOf(LiftCarCallList)
    carPosition: Unsigned8
    carMovingDirection: LiftCarDirection
    carAssignedDirection: LiftCarDirection
    carDoorStatus: ArrayOf(DoorStatus)
    carDoorCommand: ArrayOf(LiftCarDoorCommand)
    carDoorZone: Boolean
    carMode: LiftCarMode
    carLoad: Real
    carLoadUnits: EngineeringUnits
    nextStoppingFloor: Unsigned
    passengerAlarm: Boolean
    timeDelay: Unsigned
    timeDelayNormal: Unsigned
    energyMeter: Real
    energyMeterRef: DeviceObjectReference
    reliability: Reliability
    outOfService: Boolean
    carDriveStatus: LiftCarDriveStatus
    faultSignals: ListOf(LiftFault)
    landingDoorStatus: ArrayOf(LandingDoorStatus)
    higherDeck: ObjectIdentifier
    lowerDeck: ObjectIdentifier
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    eventState: EventState
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean


class LightingOutputObject(Object):
    _required = (
        "presentValue",
        "trackingValue",
        "lightingCommand",
        "inProgress",
        "statusFlags",
        "outOfService",
        "blinkWarnEnable",
        "egressTime",
        "egressActive",
        "defaultFadeTime",
        "defaultRampRate",
        "defaultStepIncrement",
        "priorityArray",
        "relinquishDefault",
        "lightingCommandDefaultPriority",
        "currentCommandPriority",
    )
    objectType = ObjectType("lightingOutput")
    presentValue: Real
    trackingValue: Real
    lightingCommand: LightingCommand
    inProgress: LightingInProgress
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    blinkWarnEnable: Boolean
    egressTime: Unsigned
    egressActive: Boolean
    defaultFadeTime: Unsigned
    defaultRampRate: Real
    defaultStepIncrement: Real
    transition: LightingTransition
    feedbackValue: Real
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Real
    power: Real
    instantaneousPower: Real
    minActualValue: Real
    maxActualValue: Real
    lightingCommandDefaultPriority: Unsigned
    covIncrement: Real
    reliabilityEvaluationInhibit: Boolean
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class LoadControlObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "requestedShedLevel",
        "startTime",
        "shedDuration",
        "dutyWindow",
        "enable",
        "expectedShedLevel",
        "actualShedLevel",
        "shedLevels",
        "shedLevelDescriptions",
    )
    objectType = ObjectType("loadControl")
    presentValue: ShedState
    stateDescription: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    requestedShedLevel: ShedLevel
    startTime: DateTime
    shedDuration: Unsigned
    dutyWindow: Unsigned
    enable: Boolean
    fullDutyBaseline: Real
    expectedShedLevel: ShedLevel
    actualShedLevel: ShedLevel
    shedLevels: ArrayOf(Unsigned)
    shedLevelDescriptions: ArrayOf(CharacterString)
    notificationClass: Unsigned
    timeDelay: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    valueSource: ValueSource


class LoopObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "outputUnits",
        "manipulatedVariableReference",
        "controlledVariableReference",
        "controlledVariableValue",
        "controlledVariableUnits",
        "setpointReference",
        "setpoint",
        "action",
        "priorityForWriting",
    )
    objectType = ObjectType("loop")
    presentValue: Real
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    updateInterval: Unsigned
    outputUnits: EngineeringUnits
    manipulatedVariableReference: ObjectPropertyReference
    controlledVariableReference: ObjectPropertyReference
    controlledVariableValue: Real
    controlledVariableUnits: EngineeringUnits
    setpointReference: SetpointReference
    setpoint: Real
    action: Action
    proportionalConstant: Real
    proportionalConstantUnits: EngineeringUnits
    integralConstant: Real
    integralConstantUnits: EngineeringUnits
    derivativeConstant: Real
    derivativeConstantUnits: EngineeringUnits
    bias: Real
    maximumOutput: Real
    minimumOutput: Real
    priorityForWriting: Unsigned
    covIncrement: Real
    timeDelay: Unsigned
    notificationClass: Unsigned
    errorLimit: Real
    deadband: Real
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    lowDiffLimit: OptionalReal


class MultiStateInputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
    )
    objectType = ObjectType("multiStateInput")
    presentValue: Unsigned
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    numberOfStates: Unsigned
    stateText: ArrayOf(CharacterString)
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ListOf(Unsigned)
    faultValues: ListOf(Unsigned)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalUnsigned


class MultiStateOutputObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
        "priorityArray",
        "relinquishDefault",
        "currentCommandPriority",
    )
    objectType = ObjectType("multiStateOutput")
    presentValue: Unsigned
    deviceType: CharacterString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    numberOfStates: Unsigned
    stateText: ArrayOf(CharacterString)
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Unsigned
    timeDelay: Unsigned
    notificationClass: Unsigned
    feedbackValue: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    interfaceValue: OptionalUnsigned
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class MultiStateValueObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
    )
    objectType = ObjectType("multiStateValue")
    presentValue: Unsigned
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    numberOfStates: Unsigned
    stateText: ArrayOf(CharacterString)
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Unsigned
    timeDelay: Unsigned
    notificationClass: Unsigned
    alarmValues: ListOf(Unsigned)
    faultValues: ListOf(Unsigned)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class NetworkPortObject(Object):
    _required = (
        "statusFlags",
        "reliability",
        "outOfService",
        "networkType",
        "protocolLevel",
        "changesPending",
        "linkSpeed",
    )
    objectType = ObjectType("networkPort")
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    networkType: NetworkType
    protocolLevel: ProtocolLevel
    referencePort: Unsigned
    networkNumber: Unsigned16
    networkNumberQuality: NetworkNumberQuality
    changesPending: Boolean
    command: NetworkPortCommand
    macAddress: MACAddress
    apduLength: Unsigned
    linkSpeed: Real
    linkSpeeds: ArrayOf(Real)
    linkSpeedAutonegotiate: Boolean
    networkInterfaceName: CharacterString
    bacnetIPMode: IPMode
    ipAddress: IPv4OctetString
    bacnetIPUDPPort: Unsigned16
    ipSubnetMask: IPv4OctetString
    ipDefaultGateway: IPv4OctetString
    bacnetIPMulticastAddress: IPv4OctetString
    ipDNSServer: ArrayOf(IPv4OctetString)
    ipDHCPEnable: Boolean
    ipDHCPLeaseTime: Unsigned
    ipDHCPLeaseTimeRemaining: Unsigned
    ipDHCPServer: IPv4OctetString
    bacnetIPNATTraversal: Boolean
    bacnetIPGlobalAddress: HostNPort
    bbmdBroadcastDistributionTable: ListOf(BDTEntry)
    bbmdAcceptFDRegistrations: Boolean
    bbmdForeignDeviceTable: ListOf(FDTEntry)
    fdBBMDAddress: HostNPort
    fdSubscriptionLifetime: Unsigned16
    bacnetIPv6Mode: IPMode
    ipv6Address: IPv6OctetString
    ipv6PrefixLength: Unsigned8
    bacnetIPv6UDPPort: Unsigned16
    ipv6DefaultGateway: IPv6OctetString
    bacnetIPv6MulticastAddress: IPv6OctetString
    ipv6DNSServer: ArrayOf(IPv6OctetString)
    ipv6AutoAddressingEnabled: Boolean
    ipv6DHCPLeaseTime: Unsigned
    ipv6DHCPLeaseTimeRemaining: Unsigned
    ipv6DHCPServer: IPv6OctetString
    ipv6ZoneIndex: CharacterString
    maxMaster: Unsigned8
    maxInfoFrames: Unsigned8
    slaveProxyEnable: Boolean
    manualSlaveAddressBinding: ListOf(AddressBinding)
    autoSlaveDiscovery: Boolean
    slaveAddressBinding: ListOf(AddressBinding)
    virtualMACAddressTable: ListOf(VMACEntry)
    routingTable: ListOf(RouterEntry)
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventState: EventState
    reliabilityEvaluationInhibit: Boolean


class NetworkSecurityObject(Object):
    objectType = ObjectType("networkSecurity")
    baseDeviceSecurityPolicy: SecurityLevel
    networkAccessSecurityPolicies: ArrayOf(NetworkSecurityPolicy)
    securityTimeWindow: Unsigned
    packetReorderTime: Unsigned
    distributionKeyRevision: Unsigned
    keySets: ArrayOf(SecurityKeySet)
    lastKeyServer: AddressBinding
    securityPDUTimeout: Unsigned
    updateKeySetTimeout: Unsigned
    supportedSecurityAlgorithms: ListOf(Unsigned)
    doNotHide: Boolean


class NotificationClassObject(Object):
    _required = ("notificationClass", "priority", "ackRequired", "recipientList")
    objectType = ObjectType("notificationClass")
    notificationClass: Unsigned
    priority: ArrayOf(Unsigned)
    ackRequired: EventTransitionBits
    recipientList: ListOf(Destination)
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    eventDetectionEnable: Boolean
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class NotificationForwarderObject(Object):
    _required = (
        "statusFlags",
        "reliability",
        "outOfService",
        "recipientList",
        "subscribedRecipients",
        "processIdentifierFilter",
        "localForwardingOnly",
    )
    objectType = ObjectType("notificationForwarder")
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    recipientList: ListOf(Destination)
    subscribedRecipients: ListOf(EventNotificationSubscription)
    processIdentifierFilter: ProcessIdSelection
    portFilter: ArrayOf(PortPermission)
    localForwardingOnly: Boolean
    reliabilityEvaluationInhibit: Boolean


class OctetStringValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("octetstringValue")
    presentValue: OctetString
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: OctetString
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class PositiveIntegerValueObject(Object):
    _required = ("presentValue", "statusFlags", "units")
    objectType = ObjectType("positiveIntegerValue")
    presentValue: Unsigned
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Unsigned
    covIncrement: Unsigned
    timeDelay: Unsigned
    notificationClass: Unsigned
    highLimit: Unsigned
    lowLimit: Unsigned
    deadband: Unsigned
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean
    minPresValue: Unsigned
    maxPresValue: Unsigned
    resolution: Unsigned
    faultHighLimit: Unsigned
    faultLowLimit: Unsigned
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class ProgramObject(Object):
    _required = ("programState", "programChange", "statusFlags", "outOfService")
    objectType = ObjectType("program")
    programState: ProgramState
    programChange: ProgramRequest
    reasonForHalt: ProgramError
    descriptionOfHalt: CharacterString
    programLocation: CharacterString
    instanceOf: CharacterString
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class PulseConverterObject(Object):
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "units",
        "scaleFactor",
        "adjustValue",
        "count",
        "updateTime",
        "countChangeTime",
        "countBeforeChange",
    )
    objectType = ObjectType("pulseConverter")
    presentValue: Real
    inputReference: ObjectPropertyReference
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    scaleFactor: Real
    adjustValue: Real
    count: Unsigned
    updateTime: DateTime
    countChangeTime: DateTime
    countBeforeChange: Unsigned
    covIncrement: Real
    covPeriod: Unsigned
    notificationClass: Unsigned
    timeDelay: Unsigned
    highLimit: Real
    lowLimit: Real
    deadband: Real
    limitEnable: LimitEnable
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    timeDelayNormal: Unsigned
    reliabilityEvaluationInhibit: Boolean


class ScheduleObject(Object):
    _required = (
        "presentValue",
        "effectivePeriod",
        "scheduleDefault",
        "listOfObjectPropertyReferences",
        "priorityForWriting",
        "statusFlags",
        "reliability",
        "outOfService",
    )
    objectType = ObjectType("schedule")
    presentValue: AnyAtomic
    effectivePeriod: DateRange
    weeklySchedule: ArrayOf(DailySchedule, _length=7)
    exceptionSchedule: ArrayOf(SpecialEvent)
    scheduleDefault: AnyAtomic
    listOfObjectPropertyReferences: ListOf(DeviceObjectPropertyReference)
    priorityForWriting: Unsigned
    statusFlags: StatusFlags
    reliability: Reliability
    outOfService: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    eventState: EventState
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    reliabilityEvaluationInhibit: Boolean


class StagingObject(Object):
    _required = (
        "presentValue",
        "presentStage",
        "stages",
        "statusFlags",
        "eventState",
        "reliability",
        "outOfService",
        "units",
        "targetReferences",
        "priorityForWriting",
        "minPresValue",
        "maxPresValue",
    )
    objectType = ObjectType("staging")
    presentValue: Real
    presentStage: Unsigned
    stages: ArrayOf(StageLimitValue)
    stageNames: ArrayOf(CharacterString)
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    units: EngineeringUnits
    targetReferences: ArrayOf(DeviceObjectReference)
    priorityForWriting: Unsigned
    defaultPresentValue: Real
    minPresValue: Real
    maxPresValue: Real
    covIncrement: Real
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    reliabilityEvaluationInhibit: Boolean
    valueSource: ValueSource


class StructuredViewObject(Object):
    _required = ("nodeSubtype", "subordinateList")
    objectType = ObjectType("structuredView")
    nodeType: NodeType
    nodeSubtype: CharacterString
    subordinateList: ArrayOf(DeviceObjectReference)
    subordinateAnnotations: ArrayOf(CharacterString)
    subordinateTags: ArrayOf(NameValueCollection)
    subordinateNodeTypes: ArrayOf(NodeType)
    subordinateRelationships: ArrayOf(Relationship)
    defaultSubordinateRelationship: Relationship
    represents: DeviceObjectReference


class TimePatternValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("timePatternValue")
    presentValue: Time
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Time
    reliabilityEvaluationInhibit: Boolean
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class TimeValueObject(Object):
    _required = ("presentValue", "statusFlags")
    objectType = ObjectType("timeValue")
    presentValue: Time
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    priorityArray: ArrayOf(PriorityValue, _length=16)
    relinquishDefault: Time
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    currentCommandPriority: OptionalUnsigned
    valueSource: ValueSource
    valueSourceArray: ArrayOf(ValueSource, _length=16)
    lastCommandTime: TimeStamp
    commandTimeArray: ArrayOf(TimeStamp, _length=16)
    auditPriorityFilter: OptionalPriorityFilter


class TimerObject(Object):
    _required = ("presentValue", "statusFlags", "timerState", "timerRunning")
    objectType = ObjectType("timer")
    presentValue: Unsigned
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    outOfService: Boolean
    timerState: TimerState
    timerRunning: Boolean
    updateTime: DateTime
    lastStateChange: TimerTransition
    expirationTime: DateTime
    initialTimeout: Unsigned
    defaultTimeout: Unsigned
    minPresValue: Unsigned
    maxPresValue: Unsigned
    resolution: Unsigned
    stateChangeValues: ArrayOf(TimerStateChangeValue, _length=7)
    listOfObjectPropertyReferences: ListOf(DeviceObjectPropertyReference)
    priorityForWriting: Unsigned
    eventDetectionEnable: Boolean
    notificationClass: Unsigned
    timeDelay: Unsigned
    timeDelayNormal: Unsigned
    alarmValues: ListOf(TimerState)
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean


class TrendLogMultipleObject(Object):
    _required = (
        "statusFlags",
        "eventState",
        "enable",
        "logDeviceObjectProperty",
        "loggingType",
        "logInterval",
        "stopWhenFull",
        "bufferSize",
        "logBuffer",
        "recordCount",
        "totalRecordCount",
    )
    objectType = ObjectType("trendLogMultiple")
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    enable: Boolean
    startTime: DateTime
    stopTime: DateTime
    logDeviceObjectProperty: ArrayOf(DeviceObjectPropertyReference)
    loggingType: LoggingType
    logInterval: Unsigned
    alignIntervals: Boolean
    intervalOffset: Unsigned
    trigger: Boolean
    stopWhenFull: Boolean
    bufferSize: Unsigned
    logBuffer: ListOf(LogMultipleRecord)
    recordCount: Unsigned
    totalRecordCount: Unsigned
    notificationThreshold: Unsigned
    recordsSinceNotification: Unsigned
    lastNotifyRecord: Unsigned
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean


class TrendLogObject(Object):
    _required = (
        "enable",
        "stopWhenFull",
        "bufferSize",
        "logBuffer",
        "recordCount",
        "totalRecordCount",
        "loggingType",
        "statusFlags",
        "reliability",
    )
    objectType = ObjectType("trendLog")
    statusFlags: StatusFlags
    eventState: EventState
    reliability: Reliability
    enable: Boolean
    startTime: DateTime
    stopTime: DateTime
    logDeviceObjectProperty: DeviceObjectPropertyReference
    logInterval: Unsigned
    covResubscriptionInterval: Unsigned
    clientCovIncrement: ClientCOV
    stopWhenFull: Boolean
    bufferSize: Unsigned
    logBuffer: ListOf(LogRecord)
    recordCount: Unsigned
    totalRecordCount: Unsigned
    loggingType: LoggingType
    alignIntervals: Boolean
    intervalOffset: Unsigned
    trigger: Boolean
    notificationThreshold: Unsigned
    recordsSinceNotification: Unsigned
    lastNotifyRecord: Unsigned
    notificationClass: Unsigned
    eventEnable: EventTransitionBits
    ackedTransitions: EventTransitionBits
    notifyType: NotifyType
    eventTimeStamps: ArrayOf(TimeStamp, _length=3)
    eventMessageTexts: ArrayOf(CharacterString, _length=3)
    eventMessageTextsConfig: ArrayOf(CharacterString, _length=3)
    eventDetectionEnable: Boolean
    eventAlgorithmInhibitRef: ObjectPropertyReference
    eventAlgorithmInhibit: Boolean
    reliabilityEvaluationInhibit: Boolean
