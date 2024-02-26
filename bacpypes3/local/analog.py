"""
Analog Input, Output, and Value Object
"""

from __future__ import annotations

from typing import Callable

from ..debugging import bacpypes_debugging, ModuleLogger

# object module provides basic AnalogInputObject
from ..object import (
    AnalogInputObject as _AnalogInputObject,
    AnalogOutputObject as _AnalogOutputObject,
    AnalogValueObject as _AnalogValueObject,
)

# local object provides dynamically generated propertyList property
from .object import Object as _Object
from .cov import COVIncrementCriteria
from .cmd import Commandable
from .event import OutOfRangeEventAlgorithm
from .fault import OutOfRangeFaultAlgorithm

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class AnalogInputObject(_Object, _AnalogInputObject):
    """
    A local analog input object.
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (  # criteria Table 13-1
        "presentValue",
        "statusFlags",
        "covIncrement",
    )


@bacpypes_debugging
class AnalogInputObjectIR(AnalogInputObject):
    """
    A local analog input object with intrinsic event reporting.
    """

    _debug: Callable[..., None]
    _event_algorithm: OutOfRangeEventAlgorithm
    _required = (  # footnote 3
        "timeDelay",
        "notificationClass",
        "highLimit",
        "lowLimit",
        "deadband",
        "limitEnable",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
        "eventDetectionEnable",
    )
    _optional = (  # footnote 5
        "eventMessageTexts",
        "eventMessageTextsConfig",
        "eventAlgorithmInhibitReference",
        "timeDelayNormal",
    )

    def __init__(self, **kwargs):
        if _debug:
            AnalogInputObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = OutOfRangeEventAlgorithm(None, self)


@bacpypes_debugging
class AnalogInputObjectFD(AnalogInputObject):
    """
    A local analog input object with fault detection.
    """

    _debug: Callable[..., None]
    _fault_algorithm: OutOfRangeFaultAlgorithm
    _required = (
        "faultLowLimit",
        "faultHighLimit",
    )

    def __init__(self, **kwargs):
        if _debug:
            AnalogInputObjectFD._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic fault algorithm
        self._fault_algorithm = OutOfRangeFaultAlgorithm(None, self)


@bacpypes_debugging
class AnalogOutputObject(Commandable, _Object, _AnalogOutputObject):
    """
    A local analog output object.
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (  # criteria Table 13-1
        "presentValue",
        "statusFlags",
        "covIncrement",
    )


@bacpypes_debugging
class AnalogOutputObjectIR(AnalogOutputObject):
    """
    A local analog output object with intrinsic reporting.
    """

    _debug: Callable[..., None]
    _event_algorithm: OutOfRangeEventAlgorithm
    _required = (  # footnote 2
        "timeDelay",
        "notificationClass",
        "highLimit",
        "lowLimit",
        "deadband",
        "limitEnable",
        "eventEnable",
        "ackedTransitions",
        "notifyType",
        "eventTimeStamps",
        "eventDetectionEnable",
    )
    _optional = (  # footnote 4
        "eventMessageTexts",
        "eventMessageTextsConfig",
        "eventAlgorithmInhibitReference",
        "timeDelayNormal",
    )

    def __init__(self, **kwargs):
        if _debug:
            AnalogOutputObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = OutOfRangeEventAlgorithm(None, self)


@bacpypes_debugging
class AnalogValueObject(_Object, _AnalogValueObject):
    """
    Vanilla Analog Value Object
    """

    _debug: Callable[..., None]
    _cov_criteria = COVIncrementCriteria
    _required = (  # criteria Table 13-1
        "presentValue",
        "statusFlags",
        "covIncrement",
    )


@bacpypes_debugging
class AnalogValueObjectCmd(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """

    _required = ("priorityArray",)


@bacpypes_debugging
class AnalogValueObjectIR(AnalogValueObjectCmd):
    """
    Commandable Analog Value Object with Intrinsic Reporting
    """

    _debug: Callable[..., None]
    _event_algorithm: OutOfRangeEventAlgorithm
    _required = (  # footnote 3
        "timeDelay",
        "notificationClass",
        "highLimit",
        "lowLimit",
        "deadband",
        "limitEnable",
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
            AnalogValueObjectIR._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic event algorithm
        self._event_algorithm = OutOfRangeEventAlgorithm(None, self)


@bacpypes_debugging
class AnalogValueObjectFD(AnalogValueObject):
    """
    A local analog input object with fault detection.
    """

    _debug: Callable[..., None]
    _fault_algorithm: OutOfRangeFaultAlgorithm
    _required = (
        "faultLowLimit",
        "faultHighLimit",
    )

    def __init__(self, **kwargs):
        if _debug:
            AnalogValueObjectFD._debug("__init__ ...")
        super().__init__(**kwargs)

        # intrinsic fault algorithm
        self._fault_algorithm = OutOfRangeFaultAlgorithm(None, self)
