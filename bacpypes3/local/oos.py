from typing import Any as _Any, Callable, Optional, Union

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.errors import PropertyError
from bacpypes3.basetypes import PropertyIdentifier

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class OutOfService:
    """
    This mix-in class is used to make present-value readonly unless out-of-service
    is true.
    """

    _debug: Callable[..., None]

    async def write_property(  # type: ignore[override]
        self,
        attr: Union[int, str],
        value: _Any,
        index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        if _debug:
            OutOfService._debug(
                "write_property %r %r %r %r", attr, value, index, priority
            )
        if (attr == PropertyIdentifier.presentValue) and (not self.outOfService):
            raise PropertyError("writeAccessDenied")

        # pass along
        await super().write_property(attr, value, index, priority)
