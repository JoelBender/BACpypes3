"""
Simple example that has a device object, an Analog Value Object with no
intrinsic fault detection, an Event Enrollment Object to monitor for changes,
and a Notification Class Object to describe where to send notifications.
"""

import asyncio
import re

from typing import Callable, Optional

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.comm import bind
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import (
    Destination,
    DeviceObjectPropertyReference,
    EngineeringUnits,
    EventParameter,
    EventParameterOutOfRange,
    EventState,
    EventType,
    NotifyType,
    PropertyIdentifier,
    Recipient,
    Reliability,
    TimeStamp,
)
from bacpypes3.object import (
    NotificationClassObject,
)

from bacpypes3.app import Application
from bacpypes3.local.event import EventEnrollmentObject
from bacpypes3.local.analog import AnalogValueObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app = None

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")


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
                property_identifier,
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

    async def do_whois(
        self,
        address: Optional[Address] = None,
        low_limit: Optional[int] = None,
        high_limit: Optional[int] = None,
    ) -> None:
        """
        Send a Who-Is request and wait for the response(s).

        usage: whois [ address [ low_limit high_limit ] ]
        """
        if _debug:
            SampleCmd._debug("do_whois %r %r %r", address, low_limit, high_limit)

        i_ams = await app.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response("No response(s)")
        else:
            for i_am in i_ams:
                if _debug:
                    SampleCmd._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    def do_debug(
        self,
        expr: str,
    ) -> None:
        value = eval(expr)  # , globals())
        print(value)
        if hasattr(value, "debug_contents"):
            value.debug_contents()


async def main() -> None:
    global app, avo2, eeo2, nc1

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
            # reliabilityEvaluationInhibit=False,
            # faultType=
            # faultParameters=
        )
        if _debug:
            _log.debug("eeo2: %r", eeo2)

        app.add_object(eeo2)

        # notification class object
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
                    recipient=Recipient(device="device,990"),
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
