#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Sequence Optional Elements
-------------------------------

An optional Choice or SequenceOf element that is absent is skipped when
decoding, including when it is context tagged and other elements follow it.
"""

import pytest

from bacpypes3.apdu import DirectoryQueryACK
from bacpypes3.basetypes import AuditNotification, Recipient, TimeStamp
from bacpypes3.constructeddata import Choice, Sequence, SequenceOf
from bacpypes3.debugging import ModuleLogger
from bacpypes3.primitivedata import (
    Boolean,
    CharacterString,
    ObjectIdentifier,
    Real,
    TagList,
    Unsigned,
)

from ..test_pdu.test_apdu_services import round_trip as apdu_round_trip

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def round_trip(obj):
    tag_list = TagList(list(obj.encode()))
    result = obj.__class__.decode(tag_list)
    assert len(tag_list) == 0
    return result


def test_absent_tagged_choice_followed_by_elements():
    """AuditNotification starts with two optional context tagged choices."""
    notification = AuditNotification(
        sourceDevice=Recipient(device=("device", 1)),
        operation="write",
        targetDevice=Recipient(device=("device", 2)),
    )
    result = round_trip(notification)
    assert result.sourceTimestamp is None
    assert result.targetTimestamp is None
    assert result.targetDevice.device == ObjectIdentifier(("device", 2))

    notification.targetTimestamp = TimeStamp(sequenceNumber=5)
    result = round_trip(notification)
    assert result.sourceTimestamp is None
    assert result.targetTimestamp.sequenceNumber == 5


def test_absent_tagged_sequence_of_followed_by_elements():
    ack = DirectoryQueryACK(directoryRevision=3, deviceInstances=[1], moreCursor=9)
    _, result = apdu_round_trip(ack, invoke_id=1)
    assert result.deviceDetails is None
    assert result.moreCursor == 9


class UntaggedChoice(Choice):
    real = Real()
    string = CharacterString()


class Optionals(Sequence):
    _order = ("first", "choice", "values", "last")
    first = Unsigned(_context=0)
    choice = UntaggedChoice(_optional=True)
    values = SequenceOf(Unsigned, _context=1, _optional=True)
    last = Boolean(_context=2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"choice": UntaggedChoice(real=1.0)},
        {"values": [1, 2]},
        {"choice": UntaggedChoice(string="x"), "values": []},
    ],
)
def test_optional_elements(kwargs):
    result = round_trip(Optionals(first=1, last=True, **kwargs))
    assert result.first == 1
    assert result.last is True or result.last == 1
    assert (result.choice is None) is ("choice" not in kwargs)
    assert (result.values is None) is ("values" not in kwargs)


class Required(Sequence):
    _order = ("choice", "last")
    choice = UntaggedChoice(_context=0)
    last = Boolean(_context=1)


def test_absent_required_tagged_choice():
    with pytest.raises(AttributeError):
        Required.decode(TagList(list(Boolean(True, _context=1).encode())))
