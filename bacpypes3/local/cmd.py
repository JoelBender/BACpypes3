from typing import (
    Any as _Any,
    Callable,
    Optional,
    Union,
)

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.errors import PropertyError
from bacpypes3.basetypes import PriorityArray as _PriorityArray, PriorityValue
from bacpypes3.local.object import Object as _Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class PriorityArray(_PriorityArray):
    """
    Capture changes to an item in a priority array and
    request the object owning the array to recalcuate the presentValue.
    """

    _debug: Callable[..., None]

    _obj: _Object

    def __init__(self, *args: _Any, **kwargs: _Any) -> None:
        if _debug:
            PriorityArray._debug("__init__ %r %r", args, kwargs)
        super().__init__(*args, **kwargs)

        self._obj = kwargs.pop("obj", None)

    def __setitem__(self, item: Union[int, slice], value: _Any) -> None:
        """
        Override the normal __setitem__() to follow up with recalculating
        the presentValue.
        """
        if _debug:
            PriorityArray._debug("__setitem__ %r %r", item, value)

        # pass along the item change to the list class
        super().__setitem__(item, value)

        # recompute the present value
        self._obj.recalculating()

    def __repr__(self):
        return f"<{self.__class__.__name__} _obj={self._obj}>"


@bacpypes_debugging
class Commandable:
    """
    This implements a commandable object where the presentValue
    is commandable and governed by the contents of the priorityArray
    and relinquishDefault proprties.
    """

    _debug: Callable[..., None]

    priorityArray: PriorityArray

    def __init__(self, **kwargs) -> None:
        if _debug:
            Commandable._debug("__init__ %r", kwargs)

        # postpone initialization so it can be converted
        priority_array = kwargs.pop("priorityArray", None)

        super().__init__(**kwargs)

        # default priority-array is all Null
        if priority_array is None:
            priority_array = [PriorityValue(null=()) for _ in range(16)]
        self.priorityArray = PriorityArray(priority_array, obj=self)

    def __setattr__(self, attr: str, value: _Any) -> None:
        """
        Changing the presentValue is actully writing to the priorityArray
        with a default of the lowest priority.  Writing the entire
        priorityArray is usually done during initialization with
        a keyword value or from unmarshalling from a JSON blob or
        RDF graph.
        """
        if attr not in ("presentValue", "priorityArray"):
            super().__setattr__(attr, value)
            return
        if _debug:
            Commandable._debug("__setattr__ %r %r", attr, type(value))

        if attr == "presentValue":
            value_type = self._elements["presentValue"]
            if not isinstance(value, value_type):
                if _debug:
                    Commandable._debug("    - casting to %r", value_type)
                value = value_type(value_type.cast(value))

            # default priority 16 (array index 15)
            self.priorityArray[15] = PriorityValue(value)

        elif attr == "priorityArray":
            if not isinstance(value, PriorityArray):
                raise TypeError("priorityArray")
            if value._obj is not self:
                if _debug:
                    Commandable._debug("    - setting obj ref")
                value._obj = self

            super().__setattr__(attr, value)

    async def write_property(  # type: ignore[override]
        self,
        attr: Union[int, str],
        value: _Any,
        index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        """
        Writing to the presentValue is redirected to writing to the
        priority array which is otherwise read-only.
        """
        if _debug:
            Commandable._debug(
                "write_property %r %r %r %r", attr, value, index, priority
            )
        if isinstance(attr, int):
            attr = self._property_identifier_class(attr).attr
        if attr not in self._elements:
            raise AttributeError(f"not a property: {attr!r}")

        if attr == "presentValue":
            if priority is None:
                priority = 16  # clause 19.2.1 paragraph 4

            await super().write_property(
                "priorityArray", PriorityValue(value), priority
            )

        elif attr == "priorityArray":
            raise PropertyError("writeAccessDenied")

        else:
            await super().write_property(attr, value, index, priority)

    def recalculating(self) -> None:
        """
        Look through the priority array to find the highest priority value
        where the PriorityValue doesn't have 'null' value.
        """
        if _debug:
            Commandable._debug("recalculating")

        value: _Any
        priority_array = self.priorityArray
        for i in range(0, 16):
            pv = priority_array[i]
            if pv.null is None:
                value = getattr(pv, pv._choice)
                break
        else:
            value = self.relinquishDefault
        if _debug:
            Commandable._debug("    - present value: %r", value)

        # update the presentValue
        super().__setattr__("presentValue", value)
