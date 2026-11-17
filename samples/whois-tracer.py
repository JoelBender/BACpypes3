"""
Who-Is Tracer

Match each Who-Is request with the I-Am responses that follow it within the
response timeout, then print the request and the devices that responded, or
"no match" if none did.  Decode capture files:

    python samples/whois-tracer.py capture.pcap [more.pcap ...]

or trace live from an interface, which needs permission to capture (see the
bacpypes3.analysis documentation), until Ctrl-C:

    sudo .venv/bin/python samples/whois-tracer.py -i eth0

The capture options are the same as `python -m bacpypes3.analysis`, plus
`--response-timeout` (seconds, default 10).  Live results are printed when
the response timeout of each request has passed.

This is an example of using the (experimental) Tracer state machine in
bacpypes3.analysis.
"""

import sys
import warnings
from argparse import Namespace
from typing import List, Optional

from bacpypes3.settings import settings
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.pdu import Address
from bacpypes3.apdu import WhoIsRequest, IAmRequest

from bacpypes3.argparse import ArgumentParser
from bacpypes3.analysis import (
    ExperimentalWarning,
    Frame,
    Tracer,
    add_capture_arguments,
    capture_permission_help,
    capture_sources,
    strftimestamp,
    trace,
)

# this sample knows the Tracer API is experimental
warnings.simplefilter("ignore", ExperimentalWarning)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
args: Namespace


@bacpypes_debugging
class TraceWhoIs(Tracer):
    """
    Trace the Who-Is requests and their responses.
    """

    timestamp: float
    expires: float
    address: Optional[Address]
    low_limit: Optional[int]
    high_limit: Optional[int]
    i_ams: List[IAmRequest]

    def __init__(self) -> None:
        if _debug:
            TraceWhoIs._debug("__init__")
        super().__init__()

        # no source or limits yet
        self.address = None
        self.low_limit = self.high_limit = None
        self.i_ams = []

    def start(self, frame: Frame) -> None:
        """
        Wait for a Who-Is request.
        """
        if _debug:
            TraceWhoIs._debug("%s: start %r %r", self, frame._number, type(frame.apdu))

        if isinstance(frame.apdu, WhoIsRequest):
            self.timestamp = frame._timestamp
            self.expires = frame._timestamp + args.response_timeout
            self.address = frame.apdu.pduSource
            if _debug:
                TraceWhoIs._debug("    - address: %r", self.address)
            self.low_limit = frame.apdu.deviceInstanceRangeLowLimit
            self.high_limit = frame.apdu.deviceInstanceRangeHighLimit
            self.next(self.wait_iam)

    def tick(self, now: float) -> None:
        """
        The response timeout has passed.
        """
        if self.address and (now > self.expires):
            self.stop()

    def stop(self) -> None:
        """
        Timeout or no more frames.
        """
        if _debug:
            TraceWhoIs._debug("stop")

        # an idle tracer never saw a Who-Is
        if self.address:
            if self.low_limit is None:
                limits = "all"
            else:
                limits = f"{self.low_limit}..{self.high_limit}"
            header = f"{strftimestamp(self.timestamp)} {self.address} {limits}"

            if not self.i_ams:
                print(f"{header}: no match", flush=True)
            else:
                print(f"{header}: {len(self.i_ams)} response(s)")
                for i_am in self.i_ams:
                    print(f"    {i_am.iAmDeviceIdentifier} from {i_am.pduSource}")
                sys.stdout.flush()

        super().stop()

    def wait_iam(self, frame: Frame) -> None:
        """
        Wait for a matching I-Am.
        """
        if _debug:
            TraceWhoIs._debug(
                "%s: wait_iam %r %r", self, frame._number, type(frame.apdu)
            )

        # match the I-Am, the limits are device instance numbers
        if isinstance(frame.apdu, IAmRequest):
            if (self.low_limit is not None) and (self.high_limit is not None):
                device_instance = frame.apdu.iAmDeviceIdentifier[1]
                if not (self.low_limit <= device_instance <= self.high_limit):
                    return
            if _debug:
                TraceWhoIs._debug("%s: match", self)
            self.i_ams.append(frame.apdu)

    def __repr__(self):
        return f"<TraceWhoIs({id(self)}) {self.low_limit}..{self.high_limit}>"


def main():
    global args
    parser = ArgumentParser()

    # capture files and/or an interface, like python -m bacpypes3.analysis
    add_capture_arguments(parser)
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=10.0,
        help="how long to wait for I-Am responses in seconds (default: 10)",
    )
    args = parser.parse_args()
    _log.debug("args: %r", args)
    _log.debug("settings: %r", settings)

    # idle ticks let a live trace time out when the network is quiet
    gen_fns = capture_sources(parser, args, idle_ticks=True)

    try:
        trace(gen_fns, [TraceWhoIs])
    except KeyboardInterrupt:
        # the pending requests have been reported
        pass
    except PermissionError as err:
        sys.stderr.write(capture_permission_help(err, args))
        sys.exit(1)


if __name__ == "__main__":
    main()
