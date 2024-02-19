"""
Simple example that has a device object and an additional Binary Value Object
with intrinsic event reporting and a Notifiaction Class Object to describe
where to send notifications.
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
    BinaryPV,
    Destination,
    EventState,
    NotifyType,
    PropertyIdentifier,
    Recipient,
    TimeStamp,
)
from bacpypes3.object import (
    NotificationClassObject,
)

from bacpypes3.app import Application
from bacpypes3.local.binary import BinaryInputObjectIR

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
            raise ValueError("property specification incorrect")
        property_name, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            raise NotImplementedError("property array index")
        attribute_name = PropertyIdentifier(property_name).attr

        await self.response(repr(getattr(obj, attribute_name)))

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
            raise ValueError("property specification incorrect")
        property_name, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            raise NotImplementedError("property array index")
        prop = PropertyIdentifier(property_name)

        # no priority :-(
        if priority:
            raise NotImplementedError("priority")

        # now get the property type from the class
        property_type = object_class.get_property_type(prop)
        if _debug:
            SampleCmd._debug("    - property_type: %r", property_type)

        # translate the value
        value = property_type(value)
        if _debug:
            SampleCmd._debug("    - value: %r", value)

        setattr(obj, prop.attr, value)

    async def do_enable(
        self,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """
        usage: enable objid
        """
        if _debug:
            SampleCmd._debug("do_enable %r", object_identifier)
        assert app

        # get the object
        obj = app.get_object_id(object_identifier)
        if not obj:
            raise RuntimeError("object not found")

        # enable event detection
        obj.eventAlgorithmInhibit = False

    async def do_disable(
        self,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """
        usage: disable objid
        """
        if _debug:
            SampleCmd._debug("do_disable %r", object_identifier)
        assert app

        # get the object
        obj = app.get_object_id(object_identifier)
        if not obj:
            raise RuntimeError("object not found")

        # disable event detection
        obj.eventAlgorithmInhibit = True

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
    global app, bio1, nc1

    try:
        app = None
        parser = SimpleArgumentParser()
        parser.add_argument(
            "recipient",
            help="notification recipient address",
        )
        parser.add_argument(
            "--confirmed",
            action="store_true",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # make an object with intrinsic reporting
        bio1 = BinaryInputObjectIR(
            objectIdentifier="binary-input,1",
            objectName="bio1",
            description="test binary value",
            presentValue=BinaryPV.inactive,
            eventState=EventState.normal,
            # statusFlags=[0, 0, 0, 0],  # inAlarm, fault, overridden, outOfService
            outOfService=False,
            # CHANGE_OF_STATE Event Algorithm
            timeDelay=1,
            notificationClass=1,
            alarmValue=BinaryPV.active,
            eventEnable=[1, 1, 1],  # toOffNormal, toFault, toNormal
            ackedTransitions=[0, 0, 0],  # toOffNormal, toFault, toNormal
            notifyType=NotifyType.alarm,  # event, ackNotification
            eventTimeStamps=[
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
                TimeStamp(time=(255, 255, 255, 255)),
            ],
            eventMessageTexts=["", "", ""],
            eventDetectionEnable=True,
            # eventMessageTextsConfig=[
            #     "to off normal - {pCurrentState}",
            #     "to fault",
            #     "to normal",
            # ],
            # eventAlgorithmInhibitReference=ObjectPropertyReference
            eventAlgorithmInhibit=False,
            timeDelayNormal=1,
        )
        if _debug:
            _log.debug("bio1: %r", bio1)

        app.add_object(bio1)

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
                    recipient=Recipient(address=args.recipient),
                    processIdentifier=0,
                    issueConfirmedNotifications=args.confirmed,
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
