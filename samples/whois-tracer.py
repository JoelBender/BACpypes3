""" """

from argparse import Namespace
from typing import List, Optional

from bacpypes3.settings import settings
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.pdu import Address
from bacpypes3.apdu import WhoIsRequest, IAmRequest

from bacpypes3.argparse import ArgumentParser
from bacpypes3.analysis import Frame, Tracer, trace, decode_file


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

    expires: float
    address: Optional[Address]
    low_limit: Optional[int]
    high_limit: Optional[int]
    i_ams: List[IAmRequest]

    def __init__(self) -> None:
        """ """
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
            self.expires = frame._timestamp + args.timeout
            self.address = frame.apdu.pduSource
            if _debug:
                TraceWhoIs._debug("    - address: %r", self.address)
            self.low_limit = frame.apdu.deviceInstanceRangeLowLimit
            self.high_limit = frame.apdu.deviceInstanceRangeHighLimit
            self.next(self.wait_iam)

    def stop(self) -> None:
        """
        Timeout or no more frames.
        """
        if _debug:
            TraceWhoIs._debug("stop")

        if self.address and (not self.i_ams):
            print(f"no match: {self.address}, {self.low_limit}..{self.high_limit}")

        super().stop()

    def wait_iam(self, frame: Frame) -> None:
        """
        Wait for a matching I-Am.
        """
        if _debug:
            TraceWhoIs._debug(
                "%s: wait_iam %r %r", self, frame._number, type(frame.apdu)
            )

        # check for timeout
        if frame._timestamp > self.expires:
            self.stop()
            return

        # match the I-Am
        if isinstance(frame.apdu, IAmRequest):
            if (self.low_limit is not None) and (self.high_limit is not None):
                if (frame.apdu.iAmDeviceIdentifier < self.low_limit) or (
                    frame.apdu.iAmDeviceIdentifier > self.high_limit
                ):
                    return
            if _debug:
                TraceWhoIs._debug("%s: match", self)
            self.i_ams.append(frame.apdu)

    def __repr__(self):
        return f"<TraceWhoIs({id(self)}) {self.low_limit}..{self.high_limit}>"


def main():
    global args
    parser = ArgumentParser()

    # pcap file decoding
    parser.add_argument(
        "filenames",
        nargs="+",
        help="the names of the pcaps file to decode",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="response timeout",
    )
    args = parser.parse_args()
    _log.debug("args: %r", args)
    _log.debug("settings: %r", settings)

    gen_fns = [decode_file(fname) for fname in args.filenames]
    tracer_classes = [TraceWhoIs]

    trace(gen_fns, tracer_classes)


if __name__ == "__main__":
    main()
