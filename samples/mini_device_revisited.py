"""
Mini BACnet Device Example
==========================

This script initializes a minimal BACnet device with the following objects:

- 1 Read-Only Analog Value (AV)
- 1 Read-Only Binary Value (BV)
- 1 Commandable Analog Value (AV)
- 1 Commandable Binary Value (BV)

Each object updates at a 5-second interval, alternating values.

Usage:
------
Run the script with a specified device name, instance ID, and optional debug mode:

    python mini_device_revisited.py --name BensServerTest --instance 3456789 --debug

Arguments:
----------
- --name : The BACnet device name (e.g., "BensServerTest")
- --instance : The BACnet device instance ID (e.g., 3456789)
- --debug : Enables debug logging (built-in to BACpypes3)

"""

import asyncio
import sys
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

# Debugging (Follow BACpypes3 standard)
_debug = 0
_log = ModuleLogger(globals())

# Update interval
INTERVAL = 5.0


@bacpypes_debugging
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """Commandable Analog Value Object"""


@bacpypes_debugging
class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """Commandable Binary Value Object"""


@bacpypes_debugging
class SampleApplication:
    def __init__(self, args):
        """Initialize the BACnet application and objects."""

        if _debug:
            _log.debug("Initializing SampleApplication")

        # Initialize the BACnet Application
        self.app = Application.from_args(args)

        # Define BACnet objects
        self.read_only_av = AnalogValueObject(
            objectIdentifier=("analogValue", 1),
            objectName="read-only-av",
            presentValue=4.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
        )

        self.read_only_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="read-only-bv",
            presentValue="active",
            statusFlags=[0, 0, 0, 0],
        )

        self.commandable_av = CommandableAnalogValueObject(
            objectIdentifier=("analogValue", 2),
            objectName="commandable-av",
            presentValue=0.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            description="Commandable analog value object",
        )

        self.commandable_bv = CommandableBinaryValueObject(
            objectIdentifier=("binaryValue", 2),
            objectName="commandable-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Commandable binary value object",
        )

        # Add objects to BACnet app
        for obj in [self.read_only_av, self.read_only_bv, self.commandable_av, self.commandable_bv]:
            self.app.add_object(obj)

        _log.info("BACnet Objects initialized.")

        # Start periodic value updates
        asyncio.create_task(self.update_values())

    async def update_values(self):
        """Periodically updates AV/BV objects with alternating values."""
        test_values = [
            ("active", 1.0),
            ("inactive", 2.0),
            ("active", 3.0),
            ("inactive", 4.0),
        ]

        while True:
            await asyncio.sleep(INTERVAL)
            next_value = test_values.pop(0)
            test_values.append(next_value)  # Rotate values in sequence

            # Update read-only points
            self.read_only_av.presentValue = next_value[1]
            self.read_only_bv.presentValue = next_value[0]

            if _debug:
                _log.debug(f"Read-Only AV: {self.read_only_av.presentValue}")
                _log.debug(f"Read-Only BV: {self.read_only_bv.presentValue}")

                # Debugging for commandable objects (values don't change)
                _log.debug(f"Commandable AV: {self.commandable_av.presentValue}")
                _log.debug(f"Commandable BV: {self.commandable_bv.presentValue}")


async def main():
    """Parse arguments and initialize the BACnet application."""
    global _debug

    # SimpleArgumentParser already includes --debug
    parser = SimpleArgumentParser()
    args = parser.parse_args()

    # Enable debugging if the argument is passed
    if args.debug:
        _debug = 1
        _log.set_level("DEBUG")
        _log.debug("Debug mode enabled")

    if _debug:
        _log.debug(f"Parsed arguments: {args}")

    # Instantiate SampleApplication
    app = SampleApplication(args)

    await asyncio.Future()  # Keep running


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log.info("Keyboard interrupt received, shutting down.")
        sys.exit(0)
