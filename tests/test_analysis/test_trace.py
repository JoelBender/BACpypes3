#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Tracing
---------------------

The trace() function gives tracers the time with tick() so they can time out
when a live capture is quiet, and stops the active tracers when the trace is
interrupted.
"""

import argparse
import time

import pytest

from bacpypes3 import analysis
from bacpypes3.analysis import (
    Frame,
    LINKTYPE_RAW,
    Tracer,
    TracerState,
    add_capture_arguments,
    capture_permission_help,
    capture_sources,
    trace,
)
from bacpypes3.apdu import WhoIsRequest

from .test_linktypes import RAW_ACK

# the Tracer API is experimental
pytestmark = pytest.mark.filterwarnings(
    "ignore::bacpypes3.analysis.ExperimentalWarning"
)


def frame(timestamp: float, who_is: bool = True) -> Frame:
    f = Frame()
    if who_is:
        f.apdu = WhoIsRequest()
    f._timestamp = timestamp
    return f


class WaitOneSecond(Tracer):
    """Start on a Who-Is, then stop one second later."""

    events: list = []

    def start(self, frame):
        if isinstance(frame.apdu, WhoIsRequest):
            self.expires = frame._timestamp + 1.0
            self.next(self.waiting)

    def waiting(self, frame):
        WaitOneSecond.events.append(("frame", frame._timestamp))

    def tick(self, now):
        if (self._state is TracerState.BUSY) and (now > self.expires):
            self.stop()

    def stop(self):
        if self._state is TracerState.BUSY:
            WaitOneSecond.events.append("stop")
        super().stop()


@pytest.fixture(autouse=True)
def clear_events():
    WaitOneSecond.events = []


def test_idle_tick_times_out():
    """An idle tick (None) times a tracer out without another frame."""

    def frames():
        yield frame(time.time() - 5.0)
        yield None
        WaitOneSecond.events.append("after idle tick")

    trace([frames()], [WaitOneSecond])
    assert WaitOneSecond.events == ["stop", "after idle tick"]


def test_tick_before_frame():
    """A tracer that times out at a frame is not given that frame."""
    frames = [frame(100.0), frame(100.5, who_is=False), frame(102.0, who_is=False)]
    trace([iter(frames)], [WaitOneSecond])
    assert WaitOneSecond.events == [("frame", 100.5), "stop"]


def test_interrupt_stops_active_tracers():
    def frames():
        yield frame(100.0)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        trace([frames()], [WaitOneSecond])
    assert WaitOneSecond.events == ["stop"]


def test_long_lived_idle_tracer():
    """A tracer that never leaves its starting state is the only instance."""

    class Counter(Tracer):
        instances = 0
        frames = 0
        stops = 0

        def __init__(self):
            super().__init__()
            Counter.instances += 1

        def start(self, frame):
            Counter.frames += 1

        def stop(self):
            Counter.stops += 1
            super().stop()

    trace([iter([frame(t) for t in range(5)] + [None])], [Counter])
    assert (Counter.instances, Counter.frames, Counter.stops) == (1, 5, 1)


#
#   decode_iface idle ticks
#


def fake_sniff(*args, **kwargs):
    yield len(RAW_ACK), 100.25, RAW_ACK
    yield 0, 0, b""
    yield len(RAW_ACK), 101.5, RAW_ACK


@pytest.fixture
def sniff(monkeypatch):
    pytest.importorskip("pylibpcap")
    monkeypatch.setattr(analysis.pylibpcap, "sniff", fake_sniff)


def test_decode_iface_idle_ticks(sniff):
    frames = list(analysis.decode_iface("eth0", linktype=LINKTYPE_RAW, idle_ticks=True))
    assert frames[1] is None
    assert [f._number for f in (frames[0], frames[2])] == [1, 2]
    assert [f._timestamp for f in (frames[0], frames[2])] == [100.25, 101.5]


def test_decode_iface_no_idle_ticks(sniff):
    frames = list(analysis.decode_iface("eth0", linktype=LINKTYPE_RAW))
    assert [f._number for f in frames] == [1, 2]


#
#   command line arguments
#


def parse(*argv):
    parser = argparse.ArgumentParser()
    add_capture_arguments(parser)
    return parser, parser.parse_args(list(argv))


@pytest.mark.parametrize(
    "argv, promiscuous",
    [((), True), (("-p",), False), (("--no-promiscuous",), False)],
)
def test_promiscuous(argv, promiscuous):
    _, args = parse("-i", "eth0", *argv)
    assert args.promiscuous is promiscuous


def test_old_promiscuous_spelling_rejected():
    with pytest.raises(SystemExit):
        parse("-i", "eth0", "--no-promiscous")


def test_capture_sources_needs_files_or_interface():
    parser, args = parse()
    with pytest.raises(SystemExit) as exc_info:
        capture_sources(parser, args)
    assert exc_info.value.code == 2


def test_capture_sources(tmp_path):
    parser, args = parse(
        str(tmp_path / "a.pcap"), str(tmp_path / "b.pcap"), "-i", "eth0"
    )
    assert len(capture_sources(parser, args)) == 3


def test_capture_permission_help():
    _, args = parse("-i", "eth3", "-f", "udp port 47809")
    text = capture_permission_help(PermissionError("eth3: denied"), args)
    assert text.startswith("error: eth3: denied\n")
    assert "dumpcap -i eth3 -f 'udp port 47809'" in text
    assert "setcap cap_net_raw" in text
