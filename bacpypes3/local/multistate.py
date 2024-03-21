"""
Multistate Input, Output, and Value Object
"""

from __future__ import annotations

from typing import Callable

from ..debugging import ModuleLogger, bacpypes_debugging

# object module provides basic AnalogInputObject
from ..object import MultiStateInputObject as _MultiStateInputObject
from ..object import MultiStateOutputObject as _MultiStateOutputObject
from ..object import MultiStateValueObject as _MultiStateValueObject
from .cmd import Commandable
from .cov import COVIncrementCriteria
from .event import OutOfRangeEventAlgorithm
from .fault import OutOfRangeFaultAlgorithm

# local object provides dynamically generated propertyList property
from .object import Object as _Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class MultiStateInputObject(_Object, _MultiStateInputObject):
    """
    A local multistate input object.
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
    )


@bacpypes_debugging
class MultiStateOutputObject(Commandable, _Object, _MultiStateOutputObject):
    """
    A local multistate output object.
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
        "priorityArray",
        "relinquishDefault",
        "currentCommandPriority",
    )


@bacpypes_debugging
class MultiStateValueObject(_Object, _MultiStateValueObject):
    """
    Vanilla Multistate Value Object
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (
        "presentValue",
        "priorityArray",
        "statusFlags",
        "eventState",
        "outOfService",
        "numberOfStates",
    )
