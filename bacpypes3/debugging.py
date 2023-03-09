"""
Debugging
"""

from __future__ import annotations

import sys
import re
import logging
import binascii
import inspect

from io import StringIO
from typing import (
    Any,
    Callable,
    cast,
    Dict,
    List,
    Optional,
    TextIO,
    Tuple,
    TypeVar,
    Union,
)

# create a root logger
root_logger = logging.getLogger("bacpypes3")

# types
FuncType = Callable[..., Any]
F = TypeVar("F", bound=FuncType)

# module loggers
module_loggers: Dict[logging.Logger, Dict[str, Any]] = {}


def btox(data: Union[bytes, bytearray], sep: str = "") -> str:
    """Return the hex encoding of a blob (byte string)."""
    # translate the blob into hex
    hex_str = str(binascii.hexlify(data), "ascii")

    # inject the separator if it was given
    if sep:
        hex_str = sep.join(hex_str[i : i + 2] for i in range(0, len(hex_str), 2))

    # return the result
    return hex_str


def xtob(data: str, sep: str = "") -> bytes:
    """Interpret the hex encoding of a blob (byte string)."""
    # remove the non-hex characters
    data = re.sub("[^0-9a-fA-F]", "", data)

    # interpret the hex
    return binascii.unhexlify(data)


def ModuleLogger(globs: Dict[str, Any]) -> logging.Logger:

    """
    Create a module level logger.

    To debug a module, create a _debug variable in the module, then use the
    ModuleLogger function to create a "module level" logger.  When a handler
    is added to this logger or a child of this logger, the _debug variable will
    be incremented.

    All of the calls within functions or class methods within the module should
    first check to see if _debug is set to prevent calls to formatter objects
    that aren't necessary.
    """

    global module_loggers

    # make sure that _debug is defined
    if "_debug" not in globs:
        raise RuntimeError("define _debug before creating a module logger")

    # logger name is the module name
    logger_name = globs["__name__"]

    # create a logger to be assigned to _log
    logger = logging.getLogger(logger_name)

    # put in a reference to the module globals
    module_loggers[logger] = globs

    # if this is a "root" logger add a default handler for warnings and up
    if "." not in logger_name:
        hdlr = logging.StreamHandler()
        hdlr.setLevel(logging.WARNING)
        hdlr.setFormatter(logging.Formatter(logging.BASIC_FORMAT, None))
        logger.addHandler(hdlr)

    return logger


# some debugging
_debug = 0
_log = ModuleLogger(globals())


class DebugContents:
    """
    A mix-in class that adds a function for debugging the contents of an
    instance.  It assumes that the class has a _debug_contents tuple of
    property names.
    """

    _debug_contents: Tuple[str, ...]

    def debug_contents(
        self,
        indent: int = 1,
        file: TextIO = sys.stderr,
        _ids: Optional[List[Any]] = None,
    ) -> None:
        """Debug the contents of an object."""
        if _debug:
            _log.debug("debug_contents indent=%r file=%r _ids=%r", indent, file, _ids)

        klasses = list(self.__class__.__mro__)
        klasses.reverse()
        if _debug:
            _log.debug("    - klasses: %r", klasses)

        # loop through the classes and look for _debug_contents
        attrs: List[str] = []
        cids: List[int] = []
        ownFn: List[type] = []
        klass: type

        for klass in klasses:
            if klass is DebugContents:
                continue

            if not issubclass(klass, DebugContents) and hasattr(
                klass, "debug_contents"
            ):
                for i, seenAlready in enumerate(ownFn):
                    if issubclass(klass, seenAlready):
                        del ownFn[i]
                        break
                ownFn.append(klass)
                continue

            # look for a tuple of attribute names
            debugContents: Optional[Tuple[str, ...]] = getattr(
                klass, "_debug_contents", None
            )
            if not debugContents:
                continue
            if not isinstance(debugContents, tuple):
                raise RuntimeError(
                    "%s._debug_contents must be a tuple" % (klass.__name__,)
                )

            # already seen it?
            if id(debugContents) in cids:
                continue
            cids.append(id(debugContents))

            for attr in debugContents:
                if attr not in attrs:
                    attrs.append(attr)

        # a bit of debugging
        if _debug:
            _log.debug("    - attrs: %r", attrs)
            _log.debug("    - ownFn: %r", ownFn)

        # make/extend the list of objects already seen
        if _ids is None:
            _ids = []

        # loop through the attributes
        for attr in attrs:
            # assume you're going deep, but not into lists and dicts
            goDeep = True
            goListDict = False
            goHexed = False

            # attribute list might want to go deep
            if attr.endswith("-"):
                goDeep = False
                attr = attr[:-1]
            elif attr.endswith("*"):
                goHexed = True
                attr = attr[:-1]
            elif attr.endswith("+"):
                goDeep = False
                goListDict = True
                attr = attr[:-1]
                if attr.endswith("+"):
                    goDeep = True
                    attr = attr[:-1]

            # get the value without triggering functions
            value = inspect.getattr_static(self, attr, None)

            # skip None
            if value is None:
                continue

            # standard output
            if goListDict and isinstance(value, list) and value:
                file.write("%s%s = [\n" % ("    " * indent, attr))
                indent += 1
                for i, elem in enumerate(value):
                    file.write("%s[%d] %r\n" % ("    " * indent, i, elem))
                    if goDeep and hasattr(elem, "debug_contents"):
                        if id(elem) not in _ids:
                            _ids.append(id(elem))
                            elem.debug_contents(indent + 1, file, _ids)
                indent -= 1
                file.write("%s    ]\n" % ("    " * indent,))
            elif goListDict and isinstance(value, dict) and value:
                file.write("%s%s = {\n" % ("    " * indent, attr))
                indent += 1
                for key, elem in value.items():
                    file.write("%s%r : %r\n" % ("    " * indent, key, elem))
                    if goDeep and hasattr(elem, "debug_contents"):
                        if id(elem) not in _ids:
                            _ids.append(id(elem))
                            elem.debug_contents(indent + 1, file, _ids)
                indent -= 1
                file.write("%s    }\n" % ("    " * indent,))
            elif goHexed and isinstance(value, (bytes, bytearray)):
                if len(value) > 20:
                    hexed = btox(value[:20], ".") + "..."
                else:
                    hexed = btox(value, ".")
                file.write("%s%s = x'%s'\n" % ("    " * indent, attr, hexed))
            elif goHexed and isinstance(value, int):
                file.write("%s%s = 0x%X\n" % ("    " * indent, attr, value))
            else:
                file.write("%s%s = %r\n" % ("    " * indent, attr, value))

                # go nested if it is debugable
                if goDeep and hasattr(value, "debug_contents"):
                    if id(value) not in _ids:
                        _ids.append(id(value))
                        value.debug_contents(indent + 1, file, _ids)

        # go through the functions
        ownFn.reverse()
        for klass in ownFn:
            klass.debug_contents(self, indent, file, _ids)  # type: ignore[attr-defined]


class LoggingFormatter(logging.Formatter):

    """
    A logging Formatter subclass that provides a specialized format routine
    and optionally wraps the output in escape codes for color.  This is used
    for console debugging when the --color option is provided.
    """

    color: Optional[int]

    def __init__(self, color: Optional[int] = None) -> None:
        logging.Formatter.__init__(self, logging.BASIC_FORMAT, None)

        # check the color
        if color is not None:
            if color not in range(8):
                raise ValueError("colors are 0 (black) through 7 (white)")

        # save the color
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        """
        This function extends the default format function by adding descriptions
        of the the contents of all of the arguments that are instances of
        DebugContents.
        """
        try:
            # use the basic formatting
            msg: str = logging.Formatter.format(self, record) + "\n"

            # look for detailed arguments
            if record.args:
                for arg in record.args:
                    if isinstance(arg, DebugContents):
                        if msg:
                            sio = StringIO()
                            sio.write(msg)
                            msg = ""
                        sio.write("    %r\n" % (arg,))
                        arg.debug_contents(indent=2, file=sio)

            # get the message from the StringIO buffer
            if not msg:
                msg = sio.getvalue()

            # trim off the last '\n'
            msg = msg[:-1]
        except Exception as err:
            record_attrs = [
                attr + ": " + str(getattr(record, attr, "N/A"))
                for attr in (
                    "name",
                    "level",
                    "pathname",
                    "lineno",
                    "msg",
                    "args",
                    "exc_info",
                    "func",
                )
            ]
            record_attrs[:0] = ["LoggingFormatter exception: " + str(err)]
            msg = "\n    ".join(record_attrs)

        if self.color is not None:
            msg = "\x1b[%dm" % (30 + self.color,) + msg + "\x1b[0m"

        return msg


def bacpypes_debugging(obj: F) -> F:
    """Decorator function that attaches a debugging logger to a class or function."""
    # create a logger for this object
    logger = logging.getLogger(obj.__module__ + "." + obj.__name__)

    # cast away attribute checking
    debugged_object = cast(Any, obj)

    # make it available to instances
    debugged_object._logger = logger
    debugged_object._debug = logger.debug
    debugged_object._info = logger.info
    debugged_object._warning = logger.warning
    debugged_object._error = logger.error
    debugged_object._exception = logger.exception
    debugged_object._critical = logger.critical

    return obj
