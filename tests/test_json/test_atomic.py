"""Tests for JSON encoding and decoding of BACnet atomic values."""

from copy import deepcopy

import pytest

from bacpypes3.basetypes import BinaryPV, DateTime, LogRecord, LogRecordLogDatum
from bacpypes3.json.util import (
    atomic_decode,
    atomic_encode,
    json_to_sequence,
    sequence_to_json,
)
from bacpypes3.primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Enumerated,
    Integer,
    Null,
    ObjectIdentifier,
    OctetString,
    Real,
    Time,
    Unsigned,
)


class SampleBitString(BitString):
    first = 0
    second = 1


class QuickBrownFox(Enumerated):
    quick = 0
    brown = 1
    fox = 2


class EmptyEnumerated(Enumerated):
    pass


class SharedNameOne(Enumerated):
    shared = 4


class SharedNameTwo(Enumerated):
    shared = 5


@pytest.mark.parametrize(
    "value, expected_json",
    [
        (Null(()), []),
        (Boolean(False), False),
        (Boolean(True), True),
        (Unsigned(7), 7),
        (Unsigned(0xFFFFFFFF), 0xFFFFFFFF),
        (Integer(0), 0),
        (Integer(-7), -7),
        (Integer(9), 9),
        (Real(1.25), 1.25),
        (Double(-2.5), -2.5),
        (OctetString(b"\x00\xff"), "00ff"),
        (CharacterString("BACnet"), "BACnet"),
        (CharacterString("café"), "café"),
        (SampleBitString([0, 2]), ["first", 2]),
        (Enumerated(0), "0"),
        (Enumerated(1), "1"),
        (Enumerated(123), "123"),
        (QuickBrownFox("brown"), "brown"),
        (BinaryPV("inactive"), "inactive"),
        (BinaryPV("active"), "active"),
        (Enumerated(BinaryPV("inactive")), "inactive"),
        (Date("2026-09-25"), "2026-09-25"),
        (Date("1901-*-*"), "1901-*-* *"),
        (Time("16:58:24.39"), "16:58:24.39"),
        (Time("01:02:*"), "01:02:*.*"),
        (ObjectIdentifier("analog-input,1"), "analog-input,1"),
    ],
    ids=lambda value: type(value).__name__,
)
def test_atomic_json_roundtrip(value, expected_json):
    literal = atomic_encode(value)

    assert literal == expected_json

    decoded = atomic_decode(literal, type(value))

    assert decoded == value
    assert type(decoded) is type(value)


def test_generic_enumerated_reconstructs_unique_symbolic_value():
    record = {
        "timestamp": {
            "date": "2026-09-25",
            "time": "16:58:24.39",
        },
        "log-datum": {
            "enum-value": "inactive",
        },
        "status-flags": [],
    }

    decoded = json_to_sequence(deepcopy(record), LogRecord)

    assert isinstance(decoded.logDatum, LogRecordLogDatum)
    assert isinstance(decoded.logDatum.enumValue, Enumerated)
    assert decoded.logDatum.enumValue == BinaryPV.inactive


def test_empty_enumerated_subclass_does_not_use_generic_symbol_lookup():
    with pytest.raises(ValueError, match="inactive"):
        atomic_decode("inactive", EmptyEnumerated)


def test_log_record_json_roundtrip():
    original = LogRecord(
        timestamp=DateTime(
            date=Date("2026-09-25"),
            time=Time("16:58:24.39"),
        ),
        logDatum=LogRecordLogDatum(enumValue=BinaryPV("inactive")),
        statusFlags=[],
    )

    json_value = sequence_to_json(original)
    decoded = json_to_sequence(deepcopy(json_value), LogRecord)

    assert decoded == original
    assert sequence_to_json(decoded) == json_value


@pytest.mark.parametrize("value", ["active", "shared"])
def test_generic_enumerated_rejects_ambiguous_symbolic_value(value):
    with pytest.raises(ValueError, match="ambiguous"):
        atomic_decode(value, Enumerated)
