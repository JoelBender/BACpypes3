import asyncio
import calendar
from time import mktime as _mktime

from typing import Any, Optional, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger
from ..primitivedata import Atomic, Null, Unsigned, Date, Time
from ..basetypes import CalendarEntry, WeekNDay, Reliability
from ..constructeddata import Array
from ..object import get_vendor_info, ScheduleObject as _ScheduleObject

from .object import Object as _Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   match_date
#


def match_date(date: Date, date_pattern: Date) -> bool:
    """
    Match a specific date, a four-tuple with no special values, with a date
    pattern, four-tuple possibly having special values.
    """
    # unpack the date and pattern
    year, month, day, day_of_week = date
    year_p, month_p, day_p, day_of_week_p = date_pattern

    # check the year
    if year_p == 255:
        # any year
        pass
    elif year != year_p:
        # specific year
        return False

    # check the month
    if month_p == 255:
        # any month
        pass
    elif month_p == 13:
        # odd months
        if (month % 2) == 0:
            return False
    elif month_p == 14:
        # even months
        if (month % 2) == 1:
            return False
    elif month != month_p:
        # specific month
        return False

    # check the day
    if day_p == 255:
        # any day
        pass
    elif day_p == 32:
        # last day of the month
        last_day = calendar.monthrange(year + 1900, month)[1]
        if day != last_day:
            return False
    elif day_p == 33:
        # odd days of the month
        if (day % 2) == 0:
            return False
    elif day_p == 34:
        # even days of the month
        if (day % 2) == 1:
            return False
    elif day != day_p:
        # specific day
        return False

    # check the day of week
    if day_of_week_p == 255:
        # any day of the week
        pass
    elif day_of_week != day_of_week_p:
        # specific day of the week
        return False

    # all tests pass
    return True


#
#   match_date_range
#


def match_date_range(date: Date, date_range: Date) -> bool:
    """
    Match a specific date, a four-tuple with no special values, with a DateRange
    object which as a start date and end date.
    """
    return (date[:3] >= date_range.startDate[:3]) and (
        date[:3] <= date_range.endDate[:3]
    )


#
#   match_weeknday
#


def match_weeknday(date: Date, weeknday: WeekNDay) -> bool:
    """
    Match a specific date, a four-tuple with no special values, with a
    BACnetWeekNDay, an octet string with three (unsigned) octets.
    """
    # unpack the date
    year, month, day, day_of_week = date
    last_day = calendar.monthrange(year + 1900, month)[1]

    # unpack the date pattern octet string
    month_p, week_of_month_p, day_of_week_p = weeknday

    # check the month
    if month_p == 255:
        # any month
        pass
    elif month_p == 13:
        # odd months
        if (month % 2) == 0:
            return False
    elif month_p == 14:
        # even months
        if (month % 2) == 1:
            return False
    elif month != month_p:
        # specific month
        return False

    # check the week of the month
    if week_of_month_p == 255:
        # any week
        pass
    elif week_of_month_p == 1:
        # days numbered 1-7
        if day > 7:
            return False
    elif week_of_month_p == 2:
        # days numbered 8-14
        if (day < 8) or (day > 14):
            return False
    elif week_of_month_p == 3:
        # days numbered 15-21
        if (day < 15) or (day > 21):
            return False
    elif week_of_month_p == 4:
        # days numbered 22-28
        if (day < 22) or (day > 28):
            return False
    elif week_of_month_p == 5:
        # days numbered 29-31
        if (day < 29) or (day > 31):
            return False
    elif week_of_month_p == 6:
        # last 7 days of this month
        if day < last_day - 6:
            return False
    elif week_of_month_p == 7:
        # any of the 7 days prior to the last 7 days of this month
        if (day < last_day - 13) or (day > last_day - 7):
            return False
    elif week_of_month_p == 8:
        # any of the 7 days prior to the last 14 days of this month
        if (day < last_day - 20) or (day > last_day - 14):
            return False
    elif week_of_month_p == 9:
        # any of the 7 days prior to the last 21 days of this month
        if (day < last_day - 27) or (day > last_day - 21):
            return False

    # check the day
    if day_of_week_p == 255:
        # any day
        pass
    elif day_of_week != day_of_week_p:
        # specific day
        return False

    # all tests pass
    return True


#
#   date_in_calendar_entry
#


@bacpypes_debugging
def date_in_calendar_entry(date: Date, calendar_entry: CalendarEntry) -> bool:
    if _debug:
        date_in_calendar_entry._debug(
            "date_in_calendar_entry %r %r", date, calendar_entry
        )

    match = False
    if calendar_entry.date:
        match = match_date(date, calendar_entry.date)
    elif calendar_entry.dateRange:
        match = match_date_range(date, calendar_entry.dateRange)
    elif calendar_entry.weekNDay:
        match = match_weeknday(date, calendar_entry.weekNDay)
    else:
        raise RuntimeError("")
    if _debug:
        date_in_calendar_entry._debug("    - match: %r", match)

    return match


#
#   datetime_to_time
#


def datetime_to_time(date: Date, time: Time) -> float:
    """
    Take the date and time 4-tuples and return the time in seconds since
    the epoch as a floating point number.
    """
    if (255 in date) or (255 in time):
        raise RuntimeError("specific date and time required")

    time_tuple = (
        date[0] + 1900,
        date[1],
        date[2],
        time[0],
        time[1],
        time[2],
        0,
        0,
        -1,
    )
    return _mktime(time_tuple)


#
#   ScheduleObject
#


@bacpypes_debugging
class ScheduleObject(_Object, _ScheduleObject):

    _interpret_schedule_handle: Optional[asyncio.Handle]

    def __init__(self, **kwargs):
        if _debug:
            ScheduleObject._debug("__init__ %r", kwargs)

        # make sure present value was provided
        if "presentValue" not in kwargs:
            raise RuntimeError("presentValue required")
        if not isinstance(kwargs["presentValue"], Atomic):
            raise TypeError("presentValue must be an Atomic value")

        # continue initialization
        super().__init__(**kwargs)

        # add some monitors to check the reliability if these properties change
        for prop in ("weeklySchedule", "exceptionSchedule", "scheduleDefault"):
            self._property_monitors[prop].append(self.check_reliability)

        self._property_monitors["presentValue"].append(self.present_value_changed)
        self._property_monitors["weeklySchedule"].append(self.schedule_changed)
        self._property_monitors["exceptionSchedule"].append(self.schedule_changed)

        # check it now
        ###TODO self.check_reliability()
        self.reliability = Reliability.noFaultDetected

        # schedule an interpretation
        try:
            self._interpret_schedule_handle = asyncio.get_running_loop().call_soon(
                self.interpret_schedule
            )
        except RuntimeError:
            self._interpret_schedule_handle = None

    def check_reliability(self, old_value=None, new_value=None):
        """
        This function is called when the object is created and after
        one of its configuration properties has changed.  The new and old value
        parameters are ignored, this is called after the property has been
        changed and this is only concerned with the current value.
        """
        if _debug:
            ScheduleObject._debug("check_reliability %r %r", old_value, new_value)

        try:
            schedule_default = self.scheduleDefault
            if schedule_default is None:
                raise ValueError("schedule-default required")

            schedule_datatype = schedule_default.get_value_type()
            if _debug:
                ScheduleObject._debug("    - schedule_datatype: %r", schedule_datatype)

            if (self.weeklySchedule is None) and (self.exceptionSchedule is None):
                raise ValueError("schedule required")

            # check the weekly schedule values
            if self.weeklySchedule:
                for daily_schedule in self.weeklySchedule:
                    for time_value in daily_schedule.daySchedule:
                        if _debug:
                            ScheduleObject._debug(
                                "    - daily time_value: %r", time_value
                            )
                        time_value_value = time_value.value.get_value()
                        if not isinstance(time_value_value, (Null, schedule_datatype)):
                            if _debug:
                                ScheduleObject._debug(
                                    "    - wrong type: expected %r, got %r",
                                    schedule_datatype,
                                    time_value_value,
                                )
                            raise TypeError("wrong type")
                        elif 255 in time_value.time:
                            if _debug:
                                ScheduleObject._debug("    - wildcard in time")
                            raise ValueError("must be a specific time")

            # check the exception schedule values
            if self.exceptionSchedule:
                for special_event in self.exceptionSchedule:
                    for time_value in special_event.listOfTimeValues:
                        if _debug:
                            ScheduleObject._debug(
                                "    - special event time_value: %r", time_value
                            )
                        time_value_value = time_value.value.get_value()
                        if not isinstance(time_value_value, (Null, schedule_datatype)):
                            if _debug:
                                ScheduleObject._debug(
                                    "    - wrong type: expected %r, got %r",
                                    schedule_datatype,
                                    time_value_value,
                                )
                            raise TypeError("wrong type")

            # check list of object property references
            obj_prop_refs = self.listOfObjectPropertyReferences
            if obj_prop_refs:
                if not self._app:
                    raise RuntimeError("not associated with an app")

                vendor_identifier = self._app.device_object.vendorIdentifier
                if vendor_identifier is None:
                    raise RuntimeError("missing vendor identifier")
                vendor_info = get_vendor_info(vendor_identifier)
                if vendor_info is None:
                    raise RuntimeError("missing vendor information")
                if _debug:
                    ScheduleObject._debug("    - vendor_info: %r", vendor_info)

                for obj_prop_ref in obj_prop_refs:
                    if obj_prop_ref.deviceIdentifier:
                        # see Clause 12.24.10
                        raise RuntimeError(
                            "restricted to referencing objects within the device"
                        )

                    # get the datatype of the property to be written
                    obj_type = obj_prop_ref.objectIdentifier[0]

                    # using the vendor information, look up the class
                    object_class = vendor_info.get_object_class(obj_type)
                    if not object_class:
                        raise RuntimeError("missing object class")

                    # now get the property type from the class
                    property_type = object_class.get_property_type(
                        obj_prop_ref.propertyIdentifier
                    )
                    if not property_type:
                        raise RuntimeError("missing property type")
                    if _debug:
                        ScheduleObject._debug("    - property_type: %r", property_type)

                    if issubclass(property_type, Array) and (
                        obj_prop_ref.propertyArrayIndex is not None
                    ):
                        if obj_prop_ref.propertyArrayIndex == 0:
                            property_type = Unsigned
                        else:
                            property_type = property_type._subtype
                            if _debug:
                                ScheduleObject._debug(
                                    "    - other property_type: %r", property_type
                                )

                    if property_type is not schedule_datatype:
                        if _debug:
                            ScheduleObject._debug(
                                "    - wrong type: expected %r, got %r",
                                property_type,
                                schedule_datatype,
                            )
                        raise TypeError("wrong type")

            # all good
            self.reliability = Reliability.noFaultDetected
            if _debug:
                ScheduleObject._debug("    - no fault detected")

        except Exception as err:
            if _debug:
                ScheduleObject._debug("    - exception: %r", err)
            self.reliability = Reliability.configurationError

    def present_value_changed(self, old_value, new_value):
        """
        This function is called when the presentValue of the local schedule
        object has changed, both internally by this interpreter, or externally
        by some client using WriteProperty.
        """
        if _debug:
            ScheduleObject._debug("present_value_changed %s %s", old_value, new_value)

        # if this hasn't been added to an application, there's nothing to do
        if not self._app:
            if _debug:
                ScheduleObject._debug("    - no application")
            return

        # process the list of [device] object property [array index] references
        obj_prop_refs = self.listOfObjectPropertyReferences
        if not obj_prop_refs:
            if _debug:
                ScheduleObject._debug("    - no writes defined")
            return

        # primitive values just set the value part
        atomic_value = new_value.get_value()
        if _debug:
            ScheduleObject._debug("    - atomic_value: %r", atomic_value)

        # loop through the writes
        for obj_prop_ref in obj_prop_refs:
            if obj_prop_ref.deviceIdentifier:
                if _debug:
                    ScheduleObject._debug("    - no externals")
                continue

            # get the object from the application
            obj = self._app.get_object_id(obj_prop_ref.objectIdentifier)
            if not obj:
                if _debug:
                    ScheduleObject._debug("    - no object")
                continue

            # try to change the value
            try:
                obj.write_property(
                    obj_prop_ref.propertyIdentifier,
                    atomic_value,
                    arrayIndex=obj_prop_ref.propertyArrayIndex,
                    priority=self.priorityForWriting,
                )
                if _debug:
                    ScheduleObject._debug("    - success")
            except Exception as err:
                if _debug:
                    ScheduleObject._debug("    - error: %r", err)

    def schedule_changed(self, old_value, new_value):
        """
        This function is called when the weeklySchedule or the exceptionSchedule
        property of the local schedule object has changed, both internally by
        this interpreter, or externally by some client using WriteProperty.
        """
        if _debug:
            ScheduleObject._debug(
                "schedule_changed(%s) %s %s",
                self.objectName,
                old_value,
                new_value,
            )

        # if this hasn't been added to an application, there's nothing to do
        if not self._app:
            if _debug:
                ScheduleObject._debug("    - no application")
            return

        # real work done by interpret_schedule
        self.interpret_schedule()

    def interpret_schedule(self):
        if _debug:
            ScheduleObject._debug("interpret_schedule(%s)", self.objectName)

        # check for a valid configuration
        if self.reliability != Reliability.noFaultDetected:
            if _debug:
                ScheduleObject._debug("    - fault: %r", self.reliability)
            return

        # get the date and time from the device object in case it provides
        # some custom functionality
        if self._app and self._app.device_object:
            current_date = self._app.device_object.localDate
            if _debug:
                ScheduleObject._debug("    - current_date: %r", current_date)

            current_time = self._app.device_object.localTime
            if _debug:
                ScheduleObject._debug("    - current_time: %r", current_time)
        else:
            # get the current date and time
            current_date = Date.now()
            if _debug:
                ScheduleObject._debug("    - current_date: %r", current_date)

            current_time = Time.now()
            if _debug:
                ScheduleObject._debug("    - current_time: %r", current_time)

        # evaluate the time
        current_value, next_transition = self.eval(current_date, current_time)
        if _debug:
            ScheduleObject._debug(
                "    - current_value, next_transition: %r, %r",
                current_value,
                next_transition,
            )

        # set the present value
        self.presentValue = current_value

        # compute the time of the next transition
        transition_time = datetime_to_time(current_date, next_transition)

        # schedule this to run
        try:
            self._interpret_schedule_handle = asyncio.get_running_loop().call_at(
                transition_time, self.interpret_schedule
            )
        except RuntimeError:
            self._interpret_schedule_handle = None

    def eval(self, edate: Date, etime: Time) -> Optional[Tuple[Any, Any]]:
        """
        Evaluate the schedule according to the provided date and time and
        return the appropriate present value with the time of the next
        transition, or None if not in the effective
        period.
        """
        if _debug:
            ScheduleObject._debug("eval %r %r", edate, etime)

        # verify the date falls in the effective period
        if not match_date_range(edate, self.effectivePeriod):
            return None

        # the event priority is a list of values that are in effect for
        # exception schedules with the special event priority, see 135.1-2013
        # clause 7.3.2.23.10.3.8, Revision 4 Event Priority Test
        event_priority = [None] * 16

        next_day = (24, 0, 0, 0)
        next_transition_time = [None] * 16

        # check the exception schedule values
        if self.exceptionSchedule:
            for special_event in self.exceptionSchedule:
                if _debug:
                    ScheduleObject._debug("    - special_event: %r", special_event)

                # check the special event period
                special_event_period = special_event.period
                if special_event_period is None:
                    raise RuntimeError("special event period required")

                match = False
                calendar_entry = special_event_period.calendarEntry
                if calendar_entry:
                    if _debug:
                        ScheduleObject._debug(
                            "    - calendar_entry: %r", calendar_entry
                        )
                    match = date_in_calendar_entry(edate, calendar_entry)
                else:
                    # get the calendar object from the application
                    calendar_object = self._app.get_object_id(
                        special_event_period.calendarReference
                    )
                    if not calendar_object:
                        raise RuntimeError("invalid calendar object reference")
                    if _debug:
                        ScheduleObject._debug(
                            "    - calendar_object: %r", calendar_object
                        )

                    for calendar_entry in calendar_object.dateList:
                        if _debug:
                            ScheduleObject._debug(
                                "    - calendar_entry: %r", calendar_entry
                            )
                        match = date_in_calendar_entry(edate, calendar_entry)
                        if match:
                            break

                # didn't match the period, try the next special event
                if not match:
                    if _debug:
                        ScheduleObject._debug("    - no matching calendar entry")
                    continue

                # event priority array index
                priority = special_event.eventPriority - 1
                if _debug:
                    ScheduleObject._debug("    - priority: %r", priority)

                # look for all of the possible times
                for time_value in special_event.listOfTimeValues:
                    tval = time_value.time
                    if tval <= etime:
                        if isinstance(time_value.value, Null):
                            if _debug:
                                ScheduleObject._debug(
                                    "    - relinquish exception @ %r", tval
                                )
                            event_priority[priority] = None
                            next_transition_time[priority] = None
                        else:
                            if _debug:
                                ScheduleObject._debug(
                                    "    - consider exception @ %r", tval
                                )
                            event_priority[priority] = time_value.value
                            next_transition_time[priority] = next_day
                    else:
                        next_transition_time[priority] = tval
                        break

        # assume the next transition will be at the start of the next day
        earliest_transition = next_day

        # check if any of the special events came up with something
        for priority_value, next_transition in zip(
            event_priority, next_transition_time
        ):
            if next_transition is not None:
                earliest_transition = min(earliest_transition, next_transition)
            if priority_value is not None:
                if _debug:
                    ScheduleObject._debug("    - priority_value: %r", priority_value)
                return priority_value, earliest_transition

        # start out with the default
        daily_value = self.scheduleDefault

        # check the daily schedule
        if self.weeklySchedule:
            # the day-of-week is 1=Monday, ... and arrays are zero-based
            daily_schedule = self.weeklySchedule[edate[3] - 1]
            if _debug:
                ScheduleObject._debug("    - daily_schedule: %r", daily_schedule)

            # look for all of the possible times
            for time_value in daily_schedule.daySchedule:
                if _debug:
                    ScheduleObject._debug("    - time_value: %r", time_value)

                tval = time_value.time
                if tval <= etime:
                    if isinstance(time_value.value, Null):
                        if _debug:
                            ScheduleObject._debug("    - back to normal @ %r", tval)
                        daily_value = self.scheduleDefault
                    else:
                        if _debug:
                            ScheduleObject._debug("    - new value @ %r", tval)
                        daily_value = time_value.value
                else:
                    earliest_transition = min(earliest_transition, tval)
                    break

        # return what was matched, if anything
        return daily_value, earliest_transition
