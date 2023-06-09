"""
Simple example that has a device object and an additional custom object.
"""

import asyncio
import re
import json
from copy import copy

from typing import Callable, Optional

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.argparse import create_log_handler

from bacpypes3.comm import bind
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import (
    Destination,
    DeviceObjectPropertyReference,
    EngineeringUnits,
    EventParameter,
    EventParameterOutOfRange,
    EventState,
    EventType,
    FaultType,
    NotifyType,
    PropertyIdentifier,
    Recipient,
    Reliability,
    TimeStamp,
)
from bacpypes3.object import (
    AnalogValueObject as _AnalogValueObject,
    EventEnrollmentObject as _EventEnrollmentObject,
    NotificationClassObject,
    VendorInfo,
)

from bacpypes3.app import Application
from bacpypes3.local.object import Object as _Object
from bacpypes3.local.event import OutOfRangeEventAlgorithm
from bacpypes3.local.fault import OutOfRangeFaultAlgorithm

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app = None

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")


@bacpypes_debugging
class AnalogValueObject(_Object, _AnalogValueObject):
    """
    Vanilla Analog Value Object
    """

    pass


@bacpypes_debugging
class AnalogValueObjectIR(AnalogValueObject):
    """
    Analog Value Object with Intrinsic Reporting
    """

    _debug: Callable[..., None]
    _event_algorithm: OutOfRangeEventAlgorithm

    def __init__(self, **kwargs):
        if _debug:
            AnalogValueObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = OutOfRangeEventAlgorithm(None, self)


@bacpypes_debugging
class AnalogValueObjectFD(AnalogValueObject):
    """
    Analog Value Object with Fault Detection
    """

    _debug: Callable[..., None]
    _fault_algorithm: OutOfRangeFaultAlgorithm

    def __init__(self, **kwargs):
        if _debug:
            AnalogValueObjectFD._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic fault detection
        self._fault_algorithm = OutOfRangeFaultAlgorithm(None, self)


@bacpypes_debugging
class EventEnrollmentObject(_Object, _EventEnrollmentObject):
    """ """

    _debug: Callable[..., None]
    _event_algorithm: OutOfRangeEventAlgorithm
    _fault_algorithm: OutOfRangeFaultAlgorithm
    _monitored_object: _Object
    _notification_class_object: NotificationClassObject

    def __init__(self, **kwargs):
        if _debug:
            EventEnrollmentObject._debug("__init__ ...")
        super().__init__(**kwargs)

        # finish the initialization by following the object property reference
        asyncio.ensure_future(self.post_init())

    async def post_init(self):
        """
        This function is called after all of the objects are added to the
        application so that the objectPropertyReference property can
        find the correct object.
        """
        if _debug:
            EventEnrollmentObject._debug("post_init")

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
        if fault_type == FaultType.faultOutOfRange:
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
        if event_type == EventType.outOfRange:
            self._event_algorithm = OutOfRangeEventAlgorithm(
                self, self._monitored_object
            )
        else:
            raise NotImplementedError(f"event type not implemented: {event_type}")
        if _debug:
            EventEnrollmentObject._debug(
                "    - _event_algorithm: %r",
                self._event_algorithm,
            )

        # find the notification class
        for objid, obj in self._app.objectIdentifier.items():
            if isinstance(obj, NotificationClassObject):
                if obj.notificationClass == self.notificationClass:
                    self._notification_class_object = obj
                    break
        else:
            raise RuntimeError(
                f"notification class object {self.notificationClass} not found"
            )
        if _debug:
            EventEnrollmentObject._debug(
                "    - notification class object: %r",
                self._notification_class_object.objectIdentifier,
            )


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read(
        self,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
    ) -> None:
        """
        usage: read objid prop[indx]
        """
        if _debug:
            SampleCmd._debug("do_read %r %r", object_identifier, property_identifier)
        assert app

        # get the object
        obj = app.get_object_id(object_identifier)
        if not obj:
            raise RuntimeError("object not found")

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_name, property_array_index = property_index_match.groups()
        attribute_name = PropertyIdentifier(property_name).attr

        if property_array_index is None:
            await self.response(repr(getattr(obj, attribute_name)))
        else:
            print("not implemented")

    async def do_write(
        self,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value: str,
        priority: Optional[int] = None,
    ) -> None:
        """
        usage: write objid property[indx] value [ priority ]
        """
        if _debug:
            SampleCmd._debug(
                "do_write %r %r %r %r",
                object_identifier,
                attribute_name,
                value,
                priority,
            )
        global app

        # get the object
        obj = app.get_object_id(object_identifier)
        if not obj:
            raise RuntimeError("object not found")
        object_class = obj.__class__
        if _debug:
            SampleCmd._debug("    - object_class: %r", object_class)

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_name, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)
        prop = PropertyIdentifier(property_name)

        # now get the property type from the class
        property_type = object_class.get_property_type(prop)
        if _debug:
            SampleCmd._debug("    - property_type: %r", property_type)

        # translate the value
        value = property_type(value)
        if _debug:
            SampleCmd._debug("    - value: %r", value)

        if property_array_index is None:
            setattr(obj, prop.attr, value)
        else:
            print("not implemented")

    def do_lowLimitEnable(
        self,
        object_name: str,
        value: int,
    ) -> None:
        """
        usage: do_lowLimitEnable object_name (1 | 0)
        """
        if _debug:
            SampleCmd._debug(
                "lowLimitEnable %r %r",
                object_name,
                value,
            )

        obj = eval(object_name)
        limit_enable = copy(obj.limitEnable)
        limit_enable[LimitEnable.lowLimitEnable] = value
        obj.limitEnable = limit_enable

    def do_highLimitEnable(
        self,
        object_name: str,
        value: int,
    ) -> None:
        """
        usage: do_highLimitEnable object_name (1 | 0)
        """
        if _debug:
            SampleCmd._debug(
                "highLimitEnable %r %r",
                object_name,
                value,
            )

        obj = eval(object_name)
        limit_enable = copy(obj.limitEnable)
        limit_enable[LimitEnable.highLimitEnable] = value
        obj.limitEnable = limit_enable

    def do_debug(
        self,
        expr: str,
    ) -> None:
        value = eval(expr)  # , globals())
        print(value)
        if hasattr(value, "debug_contents"):
            value.debug_contents()


async def main() -> None:
    global app, avo1, avo2, eeo1, avo3, eeo2, nc1

    try:
        app = None
        args = SimpleArgumentParser().parse_args()

        # make sure the vendor identifier is the custom one
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # make an object with intrinsic reporting
        avo1 = AnalogValueObjectIR(
            objectIdentifier="analog-value,1",
            objectName="avo1",
            description="test analog value",
            presentValue=50.0,
            eventState=EventState.normal,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            outOfService=False,
            units=EngineeringUnits.degreesFahrenheit,
            # OUT_OF_RANGE Event Algorithm
            # eventType=EventType.outOfRange,
            timeDelay=10,
            notificationClass=1,
            highLimit=100.0,
            lowLimit=0.0,
            deadband=5.0,
            limitEnable=[1, 1],  # lowLimitEnable, highLimitEnable
            eventEnable=[1, 1, 1],  # toOffNormal, toFault, toNormal
            ackedTransitions=[0, 0, 0],  # toOffNormal, toFault, toNormal
            notifyType=NotifyType.alarm,  # event, ackNotification
            eventTimeStamps=[
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
            ],
            eventMessageTexts=["", "", ""],
            # eventMessageTextsConfig=[
            #     "to off normal - {pCurrentState}",
            #     "to fault",
            #     "to normal",
            # ],
            eventDetectionEnable=True,
            # eventAlgorithmInhibitReference=ObjectPropertyReference
            eventAlgorithmInhibit=False,
            timeDelayNormal=2,
        )
        if _debug:
            _log.debug("avo1: %r", avo1)

        app.add_object(avo1)

        # make an analog value object with only the required parameters
        avo2 = AnalogValueObject(
            objectIdentifier="analog-value,2",
            objectName="avo2",
            description="test analog value",
            presentValue=50.0,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            eventState=EventState.normal,
            outOfService=False,
            units=EngineeringUnits.degreesFahrenheit,
        )
        if _debug:
            _log.debug("avo2: %r", avo2)

        app.add_object(avo2)

        # make an event enrollment object with only the required parameters
        eeo1 = EventEnrollmentObject(
            objectIdentifier="event-enrollment,1",
            objectName="eeo1",
            description="test event enrollment",
            eventType=EventType.outOfRange,
            notifyType=NotifyType.alarm,  # event, ackNotification
            eventParameters=EventParameter(
                outOfRange=EventParameterOutOfRange(
                    timeDelay=10,
                    lowLimit=0.0,
                    highLimit=100.0,
                    deadband=5.0,
                ),
            ),
            objectPropertyReference=DeviceObjectPropertyReference(
                objectIdentifier="analog-value,2",
                propertyIdentifier=PropertyIdentifier.presentValue,
            ),
            eventState=EventState.normal,
            eventEnable=[1, 1, 1],  # toOffNormal, toFault, toNormal
            ackedTransitions=[0, 0, 0],  # toOffNormal, toFault, toNormal
            notificationClass=1,
            eventTimeStamps=[
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
            ],
            # eventMessageTexts=["to off normal", "to fault", "to normal"],
            # eventMessageTextsConfig=[
            #     "to off normal config",
            #     "to fault config",
            #     "to normal config",
            # ],
            eventDetectionEnable=True,
            # eventAlgorithmInhibitReference=ObjectPropertyReference
            # eventAlgorithmInhibit=False,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            reliability=Reliability.noFaultDetected,
            # faultType=
            # faultParameters=
        )
        if _debug:
            _log.debug("eeo1: %r", eeo1)

        app.add_object(eeo1)

        # make an analog value object with fault detection
        avo3 = AnalogValueObjectFD(
            objectIdentifier="analog-value,3",
            objectName="avo3",
            description="test analog value",
            presentValue=50.0,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            eventState=EventState.normal,
            outOfService=False,
            units=EngineeringUnits.degreesFahrenheit,
            # reliability=Reliability.noFaultDetected,
            # reliabilityEvaluationInhibit=False,
            faultHighLimit=110.0,
            faultLowLimit=-10.0,
        )
        if _debug:
            _log.debug("avo3: %r", avo3)

        app.add_object(avo3)

        # make an event enrollment object with only the required parameters
        eeo2 = EventEnrollmentObject(
            objectIdentifier="event-enrollment,2",
            objectName="eeo2",
            description="test event enrollment",
            eventType=EventType.outOfRange,
            notifyType=NotifyType.alarm,  # event, ackNotification
            eventParameters=EventParameter(
                outOfRange=EventParameterOutOfRange(
                    timeDelay=10,
                    lowLimit=0.0,
                    highLimit=100.0,
                    deadband=5.0,
                ),
            ),
            objectPropertyReference=DeviceObjectPropertyReference(
                objectIdentifier="analog-value,3",
                propertyIdentifier=PropertyIdentifier.presentValue,
            ),
            eventState=EventState.normal,
            eventEnable=[1, 1, 1],  # toOffNormal, toFault, toNormal
            ackedTransitions=[0, 0, 0],  # toOffNormal, toFault, toNormal
            notificationClass=1,
            eventTimeStamps=[
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
            ],
            # eventMessageTexts=["to off normal", "to fault", "to normal"],
            # eventMessageTextsConfig=[
            #     "to off normal config",
            #     "to fault config",
            #     "to normal config",
            # ],
            eventDetectionEnable=True,
            # eventAlgorithmInhibitReference=ObjectPropertyReference
            # eventAlgorithmInhibit=False,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            reliability=Reliability.noFaultDetected,
            # faultType=
            # faultParameters=
        )
        if _debug:
            _log.debug("eeo2: %r", eeo2)

        app.add_object(eeo2)

        nc1 = NotificationClassObject(
            objectIdentifier="notification-class,1",
            objectName="nc1",
            description="test notification class",
            notificationClass=1,
            priority=[9, 9, 9],  # toOffNormal, toFault, toNormal priority
            ackRequired=[0, 0, 0],  # toOffNormal, toFault, toNormal
            recipientList=[
                Destination(
                    validDays=[1, 1, 1, 1, 1, 1, 1],
                    fromTime=(0, 0, 0, 0),
                    toTime=(23, 59, 59, 99),
                    recipient=Recipient(device="device,999"),
                    processIdentifier=0,
                    issueConfirmedNotifications=False,
                    transitions=[1, 1, 1],  # toOffNormal, toFault, toNormal
                )
            ],
        )
        if _debug:
            _log.debug("nc1: %r", nc1)

        app.add_object(nc1)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
