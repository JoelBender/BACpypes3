"""
Test Event State Transitions
----------------------------

The Notification Class Priority and Ack_Required arrays and the
Acked_Transitions bits are in TO_OFFNORMAL, TO_FAULT, TO_NORMAL order.  A
transition picks its entries by that index (not by the EventState value),
stores a time stamp, and clears the Acked_Transitions bit when an
acknowledgment is required (Clause 13.2.3, see PR #149).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from bacpypes3.app import Application
from bacpypes3.basetypes import EventState, TimeStamp
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.analog import AnalogInputObjectIR
from bacpypes3.local.device import DeviceObject
from bacpypes3.object import NotificationClassObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())


async def settle(n: int = 5) -> None:
    """Let the scheduled tasks and callbacks run."""
    for _ in range(n):
        await asyncio.sleep(0)


async def test_transition_index():
    app = Application()
    app.add_object(
        DeviceObject(
            objectIdentifier=("device", 1),
            objectName="dev",
            vendorIdentifier=999,
        )
    )
    app.add_object(
        NotificationClassObject(
            objectIdentifier=("notification-class", 1),
            objectName="nc",
            notificationClass=1,
            # to-offnormal, to-fault, to-normal
            priority=[10, 20, 30],
            ackRequired=[1, 0, 1],
            recipientList=[],
        )
    )
    ai = AnalogInputObjectIR(
        objectIdentifier=("analog-input", 1),
        objectName="ai",
        presentValue=50.0,
        statusFlags=[0, 0, 0, 0],
        eventState=EventState.normal,
        outOfService=False,
        units="degreesFahrenheit",
        timeDelay=0,
        notificationClass=1,
        highLimit=100.0,
        lowLimit=0.0,
        deadband=1.0,
        limitEnable=[1, 1],
        eventEnable=[1, 1, 1],
        ackedTransitions=[1, 1, 1],
        notifyType="alarm",
        eventTimeStamps=[TimeStamp.as_time()] * 3,
        eventDetectionEnable=True,
    )
    app.add_object(ai)
    await settle()

    # capture the notification parameters
    notifications: List[Dict[str, Any]] = []

    async def send_notifications(notification_parameters: Dict[str, Any]) -> None:
        notifications.append(notification_parameters)

    ai._event_algorithm.send_notifications = send_notifications  # type: ignore[method-assign]

    # to-offnormal, index 0
    ai.presentValue = 150.0
    await settle()

    assert ai.eventState == EventState.highLimit
    assert len(notifications) == 1
    assert notifications[0]["priority"] == 10
    assert notifications[0]["ackRequired"]
    assert list(ai.ackedTransitions) == [0, 1, 1]
    assert ai.eventTimeStamps[0].dateTime is not None

    # back to normal, index 2
    ai.presentValue = 50.0
    await settle()

    assert ai.eventState == EventState.normal
    assert len(notifications) == 2
    assert notifications[1]["priority"] == 30
    assert notifications[1]["ackRequired"]
    assert list(ai.ackedTransitions) == [0, 1, 0]
    assert ai.eventTimeStamps[2].dateTime is not None

    app.close()
