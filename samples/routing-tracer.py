"""
Routing Tracer

Trace the network layer messages routers use to find each other and report
the state of their networks:

* each Who-Is-Router-To-Network request is matched with the
  I-Am-Router-To-Network responses that follow it within the response
  timeout, then the request and the routers that responded are printed, or
  "no response" if none did, and CONFLICT if more than one router claims
  the same network;

* a routing table is learned from every I-Am-Router-To-Network, including
  the unsolicited ones routers send when they start, and a new network, or
  a second router for a known network (a CONFLICT), is printed as it is
  seen; Router-Busy-To-Network, Router-Available-To-Network and
  Reject-Message-To-Network messages are printed too, and the table is
  printed at the end (or Ctrl-C).

Decode capture files:

    python samples/routing-tracer.py capture.pcap [more.pcap ...]

or trace live from an interface, which needs permission to capture (see the
bacpypes3.analysis documentation), until Ctrl-C:

    sudo .venv/bin/python samples/routing-tracer.py -i eth0

The capture options are the same as `python -m bacpypes3.analysis`, plus
`--response-timeout` (seconds, default 10).

Addresses: the router is the link-level source of its message (as seen on
this network), the requester of a Who-Is-Router-To-Network is its
end-to-end source, which is different when the request was forwarded.

This is an example of using the (experimental) Tracer state machine in
bacpypes3.analysis.
"""

import sys
import warnings
from argparse import Namespace
from collections import Counter
from typing import Dict, List, Optional, Set

from bacpypes3.settings import settings
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.pdu import Address
from bacpypes3.npdu import (
    IAmRouterToNetwork,
    RejectMessageToNetwork,
    RouterAvailableToNetwork,
    RouterBusyToNetwork,
    WhoIsRouterToNetwork,
)

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

# Reject-Message-To-Network reasons (Clause 6.4.4)
reject_reasons = {
    0: "other error",
    1: "not directly connected to the network and no router to it found",
    2: "router busy",
    3: "unknown network layer message type",
    4: "message too long to be routed",
    5: "security error",
    6: "addressing error",
}


def output(*lines: str) -> None:
    """Print some lines and flush them so live output appears right away."""
    for line in lines:
        print(line)
    sys.stdout.flush()


def network_list(networks: List[int]) -> str:
    return ", ".join(str(network) for network in networks)


@bacpypes_debugging
class TraceWhoIsRouter(Tracer):
    """
    Trace the Who-Is-Router-To-Network requests and their responses.
    """

    timestamp: float
    expires: float
    requester: Optional[Address]
    heard_from: Optional[Address]
    network: Optional[int]
    responses: Dict[str, List[int]]

    def __init__(self) -> None:
        if _debug:
            TraceWhoIsRouter._debug("__init__")
        super().__init__()

        # no request yet
        self.requester = self.heard_from = None
        self.network = None
        self.responses = {}

    def start(self, frame: Frame) -> None:
        """
        Wait for a Who-Is-Router-To-Network request.
        """
        if isinstance(frame.npdu, WhoIsRouterToNetwork):
            if _debug:
                TraceWhoIsRouter._debug("%s: start %r", self, frame._number)
            self.timestamp = frame._timestamp
            self.expires = frame._timestamp + args.response_timeout
            self.requester = frame.npdu.pduSource
            self.heard_from = frame.npci.pduSource
            self.network = frame.npdu.wirtnNetwork
            self.next(self.wait_iam_router)

    def wait_iam_router(self, frame: Frame) -> None:
        """
        Collect the I-Am-Router-To-Network responses for the network, or all
        of them when the request was for any network.
        """
        if not isinstance(frame.npdu, IAmRouterToNetwork):
            return

        networks = list(frame.npdu.iartnNetworkList)
        if (self.network is not None) and (self.network not in networks):
            return
        if _debug:
            TraceWhoIsRouter._debug("%s: match %r", self, frame._number)

        # the same router can be heard more than once, for example a
        # broadcast that is also forwarded by a BBMD
        router = str(frame.npci.pduSource)
        if router not in self.responses:
            self.responses[router] = networks

    def tick(self, now: float) -> None:
        """
        The response timeout has passed.
        """
        if self.requester and (now > self.expires):
            self.stop()

    def stop(self) -> None:
        """
        Timeout or no more frames.
        """
        if _debug:
            TraceWhoIsRouter._debug("stop")

        # an idle tracer never saw a request
        if self.requester:
            network = "all" if self.network is None else self.network
            header = f"{strftimestamp(self.timestamp)} who-is-router {network} from {self.requester}"
            if str(self.requester) != str(self.heard_from):
                header += f" via {self.heard_from}"

            # look for networks claimed by more than one router
            claims: Dict[int, List[str]] = {}
            for router, networks in self.responses.items():
                for net in networks:
                    if (self.network is None) or (net == self.network):
                        claims.setdefault(net, []).append(router)
            conflicts = {
                net: routers for net, routers in claims.items() if len(routers) > 1
            }

            if not self.responses:
                output(f"{header}: no response")
            else:
                if conflicts:
                    summary = "CONFLICT " + "; ".join(
                        f"{len(routers)} routers claim {net}"
                        for net, routers in sorted(conflicts.items())
                    )
                else:
                    summary = f"{len(self.responses)} router(s)"
                output(
                    f"{header}: {summary}",
                    *(
                        f"    {router} -> {network_list(networks)}"
                        for router, networks in self.responses.items()
                    ),
                )

        super().stop()

    def __repr__(self):
        return f"<TraceWhoIsRouter({id(self)}) {self.network}>"


@bacpypes_debugging
class RoutingTable(Tracer):
    """
    Learn the routing table from the network layer messages.  This tracer
    never leaves its starting state so there is only one of them, and it is
    given every frame.
    """

    routes: Dict[int, Dict[str, Address]]
    busy: Dict[int, Set[str]]
    rejects: Counter

    def __init__(self) -> None:
        if _debug:
            RoutingTable._debug("__init__")
        super().__init__()

        self.routes = {}
        self.busy = {}
        self.rejects = Counter()

    def router_networks(self, router: str) -> List[int]:
        """Return the networks a router has said it can reach."""
        return sorted(net for net, routers in self.routes.items() if router in routers)

    def start(self, frame: Frame) -> None:
        npdu = frame.npdu
        if npdu is None:
            return
        when = strftimestamp(frame._timestamp)

        # the router is the node on this network that sent the message
        router_address = frame.npci.pduSource
        router = str(router_address)

        if isinstance(npdu, IAmRouterToNetwork):
            for net in npdu.iartnNetworkList:
                routers = self.routes.setdefault(net, {})
                if router in routers:
                    continue
                routers[router] = router_address
                if len(routers) == 1:
                    output(f"{when} network {net} via {router}")
                else:
                    output(f"{when} CONFLICT network {net} via {', '.join(routers)}")

        elif isinstance(npdu, (RouterBusyToNetwork, RouterAvailableToNetwork)):
            busy = isinstance(npdu, RouterBusyToNetwork)
            networks = list(npdu.rbtnNetworkList if busy else npdu.ratnNetworkList)

            # an empty list is all of the networks the router serves
            what = network_list(networks) if networks else "all its networks"
            if not networks:
                networks = self.router_networks(router)

            for net in networks:
                if busy:
                    self.busy.setdefault(net, set()).add(router)
                else:
                    self.busy.get(net, set()).discard(router)
            state = "busy" if busy else "available"
            output(f"{when} router {router} {state} for {what}")

        elif isinstance(npdu, RejectMessageToNetwork):
            reason = npdu.rmtnRejectionReason
            reason_text = reject_reasons.get(reason, f"reason {reason}")
            self.rejects[npdu.rmtnDNET] += 1
            output(
                f"{when} reject network {npdu.rmtnDNET} from {router}"
                f" to {npdu.pduDestination}: {reason_text}"
            )

    def stop(self) -> None:
        """
        No more frames, print the table.
        """
        if _debug:
            RoutingTable._debug("stop")

        networks = sorted(set(self.routes) | set(self.rejects))
        if networks:
            lines = ["routing table:"]
            for net in networks:
                routers = list(self.routes.get(net, {}))
                line = f"    {net}: {', '.join(routers) if routers else '(no router)'}"
                if self.busy.get(net):
                    line += f" busy ({', '.join(sorted(self.busy[net]))})"
                if self.rejects[net]:
                    line += f" {self.rejects[net]} reject(s)"
                if len(routers) > 1:
                    line += " CONFLICT"
                lines.append(line)

            all_routers = {
                router for routers in self.routes.values() for router in routers
            }
            conflicts = sum(1 for routers in self.routes.values() if len(routers) > 1)
            lines.append(
                f"{len(self.routes)} network(s), {len(all_routers)} router(s),"
                f" {conflicts} conflict(s), {sum(self.rejects.values())} reject(s)"
            )
            output(*lines)

        super().stop()


def main():
    global args
    parser = ArgumentParser()

    # capture files and/or an interface, like python -m bacpypes3.analysis
    add_capture_arguments(parser)
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=10.0,
        help="how long to wait for I-Am-Router-To-Network responses in seconds"
        " (default: 10)",
    )
    args = parser.parse_args()
    _log.debug("args: %r", args)
    _log.debug("settings: %r", settings)

    # idle ticks let a live trace time out when the network is quiet
    gen_fns = capture_sources(parser, args, idle_ticks=True)

    try:
        trace(gen_fns, [TraceWhoIsRouter, RoutingTable])
    except KeyboardInterrupt:
        # the pending requests and the routing table have been reported
        pass
    except PermissionError as err:
        sys.stderr.write(capture_permission_help(err, args))
        sys.exit(1)


if __name__ == "__main__":
    main()
