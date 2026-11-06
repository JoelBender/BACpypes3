#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Capture Permission
--------------------------------

Opening an interface without the privileges to capture is reported as a
PermissionError, other libpcap errors are passed through unchanged.
"""

import pytest

from bacpypes3 import analysis

pytest.importorskip("pylibpcap")


def fake_sniff(message):
    def sniff(*args, **kwargs):
        raise analysis.LibpcapError(message)

    return sniff


@pytest.mark.parametrize(
    "message",
    [
        "Attempt to create packet socket failed - CAP_NET_RAW may be required",
        "socket: Operation not permitted",
        "You don't have permission to capture on that device",
        "(cannot open BPF device) /dev/bpf0: Permission denied",
    ],
)
def test_permission_error(monkeypatch, message):
    monkeypatch.setattr(analysis.pylibpcap, "sniff", fake_sniff(message))
    with pytest.raises(PermissionError) as exc_info:
        next(analysis.decode_iface("eth0", linktype=analysis.LINKTYPE_ETHERNET))
    assert str(exc_info.value).startswith(f"eth0: {message}")
    assert isinstance(exc_info.value.__cause__, analysis.LibpcapError)


def test_other_error_passes_through(monkeypatch):
    message = "eth9: No such device exists"
    monkeypatch.setattr(analysis.pylibpcap, "sniff", fake_sniff(message))
    with pytest.raises(analysis.LibpcapError) as exc_info:
        next(analysis.decode_iface("eth9", linktype=analysis.LINKTYPE_ETHERNET))
    assert str(exc_info.value) == message
