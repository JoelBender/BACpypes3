#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Date, Time and DateTime Patterns
-------------------------------------

DatePattern, TimePattern and BACnetDateTimePattern may have unspecified
octets (and special month and day values), Date, Time and BACnetDateTime are
the same types restricted to a specific or unspecified value (Clause 3,
Clause 21) and are implemented as subclasses of the patterns.  The
restriction is not enforced, is_valid checks it.  Values decoded without a
declared type are Date, Time and DateTime even when they have wildcards.
"""

import pytest

from bacpypes3.basetypes import (
    CalendarEntry,
    DateTime,
    DateTimePattern,
    NameValue,
    NameValueCollection,
    OptionalDatePattern,
    OptionalDateTimePattern,
    OptionalTimePattern,
    PriorityValue,
    TimerStateChangeValue,
)
from bacpypes3.constructeddata import AnyAtomic, ArrayOf
from bacpypes3.debugging import ModuleLogger, xtob
from bacpypes3.json.util import atomic_decode, atomic_encode
from bacpypes3.object import (
    DatePatternValueObject,
    DateTimePatternValueObject,
    DateValueObject,
    TimePatternValueObject,
)
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    CharacterString,
    Date,
    DatePattern,
    Null,
    Real,
    Tag,
    TagClass,
    TagList,
    TagNumber,
    Time,
    TimePattern,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# every December 25 and noon
XMAS = (255, 12, 25, 255)
NOON = (12, 0, 0, 0)


def encode(obj) -> bytes:
    """Encode an element into octets."""
    return obj.encode().encode().pduData


def decode(cls, data: bytes):
    """Decode octets into an element of the class, all octets consumed."""
    tag_list = TagList.decode(PDUData(data))
    obj = cls.decode(tag_list)
    assert len(tag_list) == 0
    return obj


def test_subclasses():
    assert issubclass(Date, DatePattern)
    assert issubclass(Time, TimePattern)
    assert issubclass(DateTime, DateTimePattern)

    # the derived classes for context tags keep the restricted type
    assert issubclass(Date(_context=1), Date)
    assert issubclass(DatePattern(_context=1), DatePattern)
    assert not issubclass(DatePattern(_context=1), Date)
    assert isinstance(DateTime(_context=2), DateTime)


@pytest.mark.parametrize(
    "value,valid",
    [
        ((124, 1, 2, 2), True),  # specific date
        ((255, 255, 255, 255), True),  # unspecified date
        ((124, 1, 2, 255), False),  # unspecified day of week
        ((255, 12, 25, 255), False),  # every December 25
        ((124, 13, 1, 255), False),  # odd months
        ((124, 1, 32, 255), False),  # last day of the month
    ],
)
def test_date_is_valid(value, valid):
    # patterns are accepted by both
    assert DatePattern(value) == value
    date = Date(value)
    assert type(date) is Date
    assert date.is_valid is valid
    assert date.is_unspecified is (value == (255, 255, 255, 255))


@pytest.mark.parametrize(
    "value,valid",
    [
        ((12, 34, 56, 78), True),
        ((255, 255, 255, 255), True),
        ((12, 255, 255, 255), False),
        ((12, 0, 0, 255), False),
    ],
)
def test_time_is_valid(value, valid):
    assert TimePattern(value) == value
    time = Time(value)
    assert type(time) is Time
    assert time.is_valid is valid
    assert time.is_unspecified is (value == (255, 255, 255, 255))


def test_cast_between():
    # a date is a date pattern, a pattern is copied into a date
    date = Date("2024-01-02")
    assert isinstance(date, DatePattern)
    assert type(DatePattern(date)) is DatePattern
    assert type(Date(DatePattern("2024-01-02"))) is Date
    assert type(Date.now()) is Date
    assert type(DatePattern.now()) is DatePattern
    assert type(Time(TimePattern("12:00"))) is Time


def test_application_tags():
    """Without a declared type the application tags decode as Date and Time."""
    tag = Tag(TagClass.application, TagNumber.date, 4, xtob("ff0c19ff"))
    obj = tag.app_to_object()
    assert type(obj) is Date
    assert obj == (255, 12, 25, 255)
    assert not obj.is_valid

    tag = Tag(TagClass.application, TagNumber.time, 4, xtob("0cffffff"))
    obj = tag.app_to_object()
    assert type(obj) is Time
    assert obj == (12, 255, 255, 255)
    assert not obj.is_valid

    # the application tag matches both the pattern and restricted elements
    assert type(decode(DatePattern, xtob("a4 ff0c19ff"))) is DatePattern
    assert type(decode(Date, xtob("a4 7c010202"))) is Date


def test_datetime_elements():
    assert DateTimePattern._elements["date"] is DatePattern
    assert DateTimePattern._elements["time"] is TimePattern
    assert DateTime._elements["date"] is Date
    assert DateTime._elements["time"] is Time
    assert DateTime(_context=2)._elements["date"] is Date
    assert DateTime._order == DateTimePattern._order

    obj = DateTime("2025-01-01 12:34:56")
    assert type(obj.date) is Date
    assert type(obj.time) is Time
    assert obj.is_valid

    obj = DateTimePattern(date=XMAS, time=NOON)
    assert type(obj.date) is DatePattern
    assert type(obj.time) is TimePattern
    assert obj.is_special
    assert not obj.is_unspecified

    # not enforced, but checked
    assert not DateTime(date=XMAS, time=NOON).is_valid
    assert DateTime(date=(255,) * 4, time=(255,) * 4).is_valid
    assert DateTime(date=(255,) * 4, time=(255,) * 4).is_unspecified

    # copies keep the type of the destination
    obj = DateTimePattern(DateTime("2025-01-01 12:34:56"))
    assert type(obj) is DateTimePattern
    assert type(obj.date) is DatePattern
    obj = DateTime(DateTimePattern("2025-01-01 12:34:56"))
    assert type(obj) is DateTime
    assert type(obj.date) is Date

    # the wire encoding is the same
    assert encode(DateTime("2025-01-01 12:34:56")) == encode(
        DateTimePattern("2025-01-01 12:34:56")
    )


def test_calendar_entry_date_pattern():
    """BACnetCalendarEntry date is a DatePattern."""
    obj = CalendarEntry(date=DatePattern(XMAS))
    assert encode(obj) == xtob("0c ff0c19ff")

    result = decode(CalendarEntry, encode(obj))
    assert isinstance(result.date, DatePattern)
    assert not isinstance(result.date, Date)
    assert result.date == (255, 12, 25, 255)


def test_timer_state_change_value_patterns():
    """The application tagged date and time choices are patterns."""
    obj = decode(TimerStateChangeValue, xtob("a4 ff0c19ff"))
    assert obj._choice == "date"
    assert type(obj.date) is DatePattern

    obj = decode(TimerStateChangeValue, xtob("b4 0cffffff"))
    assert obj._choice == "time"
    assert type(obj.time) is TimePattern

    obj = TimerStateChangeValue(datetime=DateTimePattern(date=XMAS, time=NOON))
    assert encode(obj) == xtob("2e a4ff0c19ff b40c000000 2f")
    result = decode(TimerStateChangeValue, encode(obj))
    assert isinstance(result.datetime, DateTimePattern)
    assert not isinstance(result.datetime, DateTime)
    assert result.datetime.date == (255, 12, 25, 255)


def test_optional_patterns():
    obj = OptionalDatePattern(datepattern=DatePattern((255, 255, 32, 255)))
    result = decode(OptionalDatePattern, encode(obj))
    assert type(result.datepattern) is DatePattern
    assert result.datepattern == (255, 255, 32, 255)

    obj = OptionalDateTimePattern(
        datetimepattern=DateTimePattern(date=(255,) * 4, time=NOON)
    )
    result = decode(OptionalDateTimePattern, encode(obj))
    assert result.datetimepattern.time == (12, 0, 0, 0)


def test_priority_value_patterns():
    """PriorityValue accepts patterns for the date and time choices."""
    assert PriorityValue(DatePattern(XMAS))._choice == "date"
    assert PriorityValue(TimePattern("12:*"))._choice == "time"
    assert PriorityValue(DateTimePattern(date=XMAS, time=NOON))._choice == "datetime"
    assert PriorityValue(Date("2025-12-25"))._choice == "date"
    assert PriorityValue(DateTime("2025-12-25 12:00"))._choice == "datetime"


def test_optional_pattern_values():
    """The Optional...Pattern choices accept values and PriorityValues."""
    assert OptionalDatePattern(Null(()))._choice == "null"
    for value in (DatePattern(XMAS), Date("2025-12-25")):
        obj = OptionalDatePattern(value)
        assert obj._choice == "datepattern"
        assert type(obj.datepattern) is DatePattern
        assert obj.datepattern == value

    obj = OptionalDatePattern(PriorityValue(date=Date("2025-12-25")))
    assert obj._choice == "datepattern"
    assert obj.datepattern == (125, 12, 25, 4)
    assert OptionalDatePattern(PriorityValue(null=()))._choice == "null"

    obj = OptionalTimePattern(Time("12:00"))
    assert obj._choice == "timepattern"
    assert type(obj.timepattern) is TimePattern

    obj = OptionalDateTimePattern(DateTime("2025-12-25 12:00"))
    assert obj._choice == "datetimepattern"
    assert isinstance(obj.datetimepattern, DateTimePattern)
    assert not isinstance(obj.datetimepattern, DateTime)
    obj = OptionalDateTimePattern(PriorityValue(datetime=DateTime("2025-12-25 12:00")))
    assert obj._choice == "datetimepattern"

    # the keyword form still works
    assert OptionalDatePattern(datepattern=XMAS).datepattern == XMAS

    with pytest.raises(TypeError):
        OptionalDatePattern(Time("12:00"))
    with pytest.raises(TypeError):
        OptionalDatePattern(PriorityValue(real=Real(1.0)))


def test_any_atomic_date():
    """Without a declared type an AnyAtomic date is a Date."""
    obj = AnyAtomic(DatePattern(XMAS))
    assert obj.get_value_type() is Date
    value = obj.get_value()
    assert type(value) is Date
    assert value == XMAS

    # a DateTime is not atomic
    with pytest.raises(TypeError):
        AnyAtomic(DateTime("2025-12-25 12:00"))


def test_name_value():
    """The value of a BACnetNameValue is a single primitive value."""
    obj = NameValue(name="xmas", value=DatePattern(XMAS))
    assert encode(obj) == xtob("0d 05 00786d6173 a4ff0c19ff")
    result = decode(NameValue, encode(obj))
    assert result.name == "xmas"
    assert result.value.get_value() == XMAS

    obj = NameValue(name="none")
    result = decode(NameValue, encode(obj))
    assert result.name == "none"
    assert result.value is None

    obj = NameValueCollection(
        members=[
            NameValue(name="a"),
            NameValue(name="b", value=CharacterString("c")),
            NameValue(name="d"),
        ]
    )
    result = decode(NameValueCollection, encode(obj))
    assert [member.name for member in result.members] == ["a", "b", "d"]
    assert result.members[0].value is None
    assert result.members[1].value.get_value() == "c"
    assert result.members[2].value is None


def test_pattern_value_objects():
    assert DatePatternValueObject._elements["presentValue"] is DatePattern
    assert TimePatternValueObject._elements["presentValue"] is TimePattern
    assert DateTimePatternValueObject._elements["presentValue"] is DateTimePattern
    assert DateValueObject._elements["presentValue"] is Date

    obj = DatePatternValueObject(presentValue=XMAS)
    assert type(obj.presentValue) is DatePattern
    assert obj.presentValue == (255, 12, 25, 255)

    # the priority arrays are the CSML BACnetOptional...Pattern
    for cls, subtype in (
        (DatePatternValueObject, OptionalDatePattern),
        (TimePatternValueObject, OptionalTimePattern),
        (DateTimePatternValueObject, OptionalDateTimePattern),
    ):
        assert cls._elements["priorityArray"]._subtype is subtype
        assert cls._elements["priorityArray"]._length == 16

    array_class = ArrayOf(OptionalDatePattern, _length=16)
    obj = array_class(
        [OptionalDatePattern(DatePattern(XMAS))]
        + [OptionalDatePattern(Null(())) for _ in range(15)]
    )
    result = decode(array_class, encode(obj))
    assert result[0].datepattern == XMAS
    assert result[1]._choice == "null"


def test_json_patterns():
    value = DatePattern((125, 12, 255, 255))
    assert atomic_encode(value) == "2025-12-* *"
    result = atomic_decode("2025-12-* *", DatePattern)
    assert type(result) is DatePattern
    assert result == value

    assert atomic_encode(TimePattern("12:*")) == "12:*:*.*"
    result = atomic_decode("12:*:*.*", TimePattern)
    assert type(result) is TimePattern
    assert result == (12, 255, 255, 255)
