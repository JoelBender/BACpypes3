"""
Binary Input, Output, and Value Object
"""

from __future__ import annotations

from typing import Callable

from ..debugging import bacpypes_debugging, ModuleLogger

# object module provides basic objects
from ..object import (
    BinaryInputObject as _BinaryInputObject,
    BinaryOutputObject as _BinaryOutputObject,
    BinaryValueObject as _BinaryValueObject,
)

# local object provides dynamically generated propertyList property
from .object import Object as _Object
from .cov import GenericCriteria
from .cmd import Commandable
from .event import ChangeOfStateEventAlgorithm, CommandFailureEventAlgorithm

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class BinaryInputObject(_Object, _BinaryInputObject):
    """
    A local binary input object.
    """

    _debug: Callable[..., None]
    _cov_criteria = GenericCriteria
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "polarity",
    )


@bacpypes_debugging
class BinaryInputObjectIR(BinaryInputObject):
    """
    A local binary input object with intrinsic reporting.
    """

    _debug: Callable[..., None]
    _event_algorithm: ChangeOfStateEventAlgorithm

    _required = (  # footnote 5
        "timeDelay",
        "notificationClass",
        "alarmValue",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
        "eventDetectionEnable",
    )
    _optional = (  # footnote 7
        "eventMessageTexts",
        "eventMessageTextsConfig",
        "eventAlgorithmInhibitReference",
        "timeDelayNormal",
    )

    def __init__(self, **kwargs):
        if _debug:
            BinaryInputObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = ChangeOfStateEventAlgorithm(None, self)


@bacpypes_debugging
class BinaryOutputObject(Commandable, _Object, _BinaryOutputObject):
    """
    A local binary output object.
    """

    _debug: Callable[..., None]
    _cov_criteria = GenericCriteria
    _required = (
        "presentValue",
        "statusFlags",
        "eventState",
        "outOfService",
        "polarity",
        "priorityArray",
        "relinquishDefault",
        "currentCommandPriority",
    )


@bacpypes_debugging
class BinaryOutputObjectIR(BinaryOutputObject):
    """
    A local binary output object with intrinsic reporting.
    """

    _debug: Callable[..., None]
    _event_algorithm: CommandFailureEventAlgorithm

    _required = (  # footnote 4
        "timeDelay",
        "notificationClass",
        "feedbackValue",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
        "eventDetectionEnable",
    )
    _optional = (  # footnote 6
        "eventMessageTexts",
        "eventMessageTextsConfig",
        "eventAlgorithmInhibitReference",
        "timeDelayNormal",
    )

    def __init__(self, **kwargs):
        if _debug:
            BinaryOutputObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = CommandFailureEventAlgorithm(None, self)


@bacpypes_debugging
class BinaryValueObject(_Object, _BinaryValueObject):
    """
    Vanilla Binary Value Object
    """

    _debug: Callable[..., None]
    _cov_criteria = GenericCriteria
    _required = (
        "presentValue",
        "priorityArray",
        "statusFlags",
        "eventState",
        "outOfService",
    )


@bacpypes_debugging
class BinaryValueObjectCmd(Commandable, _BinaryValueObject):
    """
    Commandable Binary Value Object
    """

    _required = ("priorityArray",)


@bacpypes_debugging
class BinaryValueObjectIR(BinaryValueObjectCmd):
    """
    Commandable Binary Value Object with Intrinsic Reporting
    """

    _debug: Callable[..., None]
    _event_algorithm: ChangeOfStateEventAlgorithm
    _required = (  # footnote 6
        "timeDelay",
        "notificationClass",
        "feedbackValue",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
        "eventDetectionEnable",
    )
    _optional = (  # footnote 8
        "eventMessageTexts",
        "eventMessageTextsConfig",
        "eventAlgorithmInhibitReference",
        "timeDelayNormal",
    )

    def __init__(self, **kwargs):
        if _debug:
            BinaryValueObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = ChangeOfStateEventAlgorithm(None, self)
