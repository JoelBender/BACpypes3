#!/usr/bin/env python3
"""
Mini BACnet Device Example
========================================

This script initializes a minimal BACnet server device using BACpypes3.
It is ideal for rapid prototyping and testing with BACnet client tools
or supervisory platforms. You can easily add or remove objects to fit
your use case.

Included Objects:
-----------------
- 1 Read-Only Analog Value (AV)
- 1 Read-Only Binary Value (BV)
- 1 Commandable Analog Value (AV)
- 1 Commandable Binary Value (BV)

Commandable Points:
-------------------
Commandable AV and BV points support writes via the BACnet priority array.
They emulate real-world control points, such as thermostat setpoints,
damper commands, etc.

Usage:
------
Run the script with the device name, instance ID, and optional debug flag:

    python mini_device_no_schedule.py --name BensServerTest --instance 3456 --debug

Arguments:
----------
- --name       : The BACnet device name (e.g., "BensServerTest")
- --instance   : The BACnet device instance ID (e.g., 3456789)
- --address    : Optional — override the automatically detected IP address and port.
                 Requires ifaddr package for auto-detection.
                 See: https://bacpypes3.readthedocs.io/en/latest/gettingstarted/addresses.html#bacpypes3-addresses
- --debug      : Enables verbose debug logging (built-in to BACpypes3)
"""

import asyncio
import sys

from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

# Debug logging setup
_debug = 0
_log = ModuleLogger(globals())

# Interval for updating values
INTERVAL = 5.0


@bacpypes_debugging
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """Commandable Analog Value Object"""


@bacpypes_debugging
class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """Commandable Binary Value Object"""


@bacpypes_debugging
class SampleApplication:
    """
    Simple BACnet application exposing four points:

    - analogValue,1: read-only, simulated ramp
    - binaryValue,1: read-only, simulated on/off
    - analogValue,2: commandable (priority array)
    - binaryValue,2: commandable (priority array)
    """

    def __init__(self, args):
        if _debug:
            _log.debug("Initializing SampleApplication (no schedule)")

        # Build application (DeviceObject is created from args)
        self.app = Application.from_args(args)

        # --- Read-only points ---
        self.read_only_av = AnalogValueObject(
            objectIdentifier=("analogValue", 1),
            objectName="read-only-av",
            presentValue=4.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Simulated Read-Only Analog Value",
        )

        self.read_only_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="read-only-bv",
            presentValue="active",
            statusFlags=[0, 0, 0, 0],
            description="Simulated Read-Only Binary Value",
        )

        # --- Commandable points ---
        self.commandable_av = CommandableAnalogValueObject(
            objectIdentifier=("analogValue", 2),
            objectName="commandable-av",
            presentValue=0.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Commandable Analog Value (Simulated)",
        )

        self.commandable_bv = CommandableBinaryValueObject(
            objectIdentifier=("binaryValue", 2),
            objectName="commandable-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Commandable Binary Value (Simulated)",
        )

        # Register all objects with the application
        for obj in [
            self.read_only_av,
            self.read_only_bv,
            self.commandable_av,
            self.commandable_bv,
        ]:
            self.app.add_object(obj)

        _log.info("BACnet Objects initialized (no schedule).")

        # Start a simple simulation task
        asyncio.create_task(self.update_values())

    async def update_values(self) -> None:
        """
        Periodically update the read-only AV/BV to simulate activity.
        Commandable points are left alone so client writes are not overridden.
        """
        test_values = [
            ("active", 1.0),
            ("inactive", 2.0),
            ("active", 3.0),
            ("inactive", 4.0),
        ]

        while True:
            await asyncio.sleep(INTERVAL)
            next_value = test_values.pop(0)
            test_values.append(next_value)

            self.read_only_av.presentValue = next_value[1]
            self.read_only_bv.presentValue = next_value[0]

            if _debug:
                _log.debug(f"Read-Only AV: {self.read_only_av.presentValue}")
                _log.debug(f"Read-Only BV: {self.read_only_bv.presentValue}")
                _log.debug(f"Commandable AV: {self.commandable_av.presentValue}")
                _log.debug(f"Commandable BV: {self.commandable_bv.presentValue}")


async def main() -> None:
    global _debug

    parser = SimpleArgumentParser()
    args = parser.parse_args()

    if args.debug:
        _debug = 1
        _log.set_level("DEBUG")
        _log.debug("Debug mode enabled")

    if _debug:
        _log.debug(f"Parsed arguments: {args}")

    app = SampleApplication(args)

    # Keep running forever
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log.info("Keyboard interrupt received, shutting down.")
        sys.exit(0)
