"""
Primitive Data Types
"""

from __future__ import annotations

import sys
import inspect
import struct
import datetime
import time
import re

from enum import IntEnum

from typing import (
    Any as _Any,
    Callable,
    cast,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List as _List,
    Optional,
    TextIO,
    Tuple,
    Type,
    Union,
)

from .debugging import ModuleLogger, bacpypes_debugging, btox
from .errors import DecodingError, InvalidTag, PropertyError
from .pdu import PDUData

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# enumeration names are analog-value rather that analogValue
_unupper_re = re.compile(r"([A-Z])([A-Z]+)([A-Z][a-z])")
_trailing_uppers_re = re.compile(r"([A-Z])([A-Z]+)$")
_wordsplit_re = re.compile(r"([a-z0-9])([A-Z]+)(?=.)")


def attr_to_asn1(k):
    """
    Translate enumeration names like 'analogValue' into 'analog-value'.
    """
    # translate DHCPSnork to DhcpSnork
    k = _unupper_re.sub(
        lambda m: m.groups()[0] + m.groups()[1].lower() + m.groups()[2], k
    )

    # translate subscribeCOV to subscribeCov
    k = _trailing_uppers_re.sub(lambda m: m.groups()[0] + m.groups()[1].lower(), k)

    # translate lowerCamel to lower-camel
    k = _wordsplit_re.sub(lambda m: m.groups()[0] + "-" + m.groups()[1].lower(), k)

    # more exceptions
    k = k.replace("-ipnat-", "-ip-nat-")
    k = k.replace("-ipudp-", "-ip-udp-")

    return k


class TagClass(IntEnum):
    application = 0
    context = 1
    opening = 2
    closing = 3


class TagNumber(IntEnum):
    null = 0
    boolean = 1
    unsigned = 2
    integer = 3
    real = 4
    double = 5
    octetString = 6
    characterString = 7
    bitString = 8
    enumerated = 9
    date = 10
    time = 11
    objectIdentifier = 12
    reserved13 = 13
    reserved14 = 14
    reserved15 = 15


class Tag:
    """
    Amazing documentation here.
    """

    tag_class: TagClass
    tag_number: Union[TagNumber, int]
    tag_lvt: int
    tag_data: bytes

    _app_tag_name = [
        "null",
        "boolean",
        "unsigned",
        "integer",
        "real",
        "double",
        "octetString",
        "characterString",
        "bitString",
        "enumerated",
        "date",
        "time",
        "objectIdentifier",
        "reserved13",
        "reserved14",
        "reserved15",
    ]
    _app_tag_class: _List[type]

    def __init__(self, *args: _Any) -> None:
        if args:
            if (len(args) == 1) and isinstance(args[0], PDUData):
                self.decode(args[0])
            elif len(args) >= 2:
                self.set(*args)
            else:
                raise ValueError("invalid Tag ctor arguments")

    def set(
        self,
        tclass: TagClass,
        tnum: Union[int, TagNumber],
        tlvt: int = 0,
        tdata: bytes = b"",
    ) -> None:
        """Set the attributes of the tag."""
        if isinstance(tdata, bytearray):
            tdata = bytes(tdata)
        elif not isinstance(tdata, bytes):
            raise TypeError("tag data must be bytes or bytearray")

        self.tag_class = tclass
        self.tag_number = tnum
        self.tag_lvt = tlvt
        self.tag_data = tdata

    def set_app_data(self, tnum: TagNumber, tdata: bytes) -> None:
        """Set the attributes of the tag as an application tag."""
        if isinstance(tdata, bytearray):
            tdata = bytes(tdata)
        elif not isinstance(tdata, bytes):
            raise TypeError("tag data must be bytes or bytearray")

        self.tag_class = TagClass.application
        self.tag_number = tnum
        self.tag_lvt = len(tdata)
        self.tag_data = tdata

    def encode(self) -> PDUData:
        """Encode a tag on the end of the PDU."""
        pdu_data = PDUData()

        # check for special encoding
        if self.tag_class == TagClass.context:
            data = 0x08
        elif self.tag_class == TagClass.opening:
            data = 0x0E
        elif self.tag_class == TagClass.closing:
            data = 0x0F
        else:
            data = 0x00

        # encode the tag number part
        if self.tag_number < 15:
            data += self.tag_number << 4
        else:
            data += 0xF0

        # encode the length/value/type part
        if self.tag_lvt < 5:
            data += self.tag_lvt
        else:
            data += 0x05

        # save this and the extended tag value
        pdu_data.put(data)
        if self.tag_number >= 15:
            pdu_data.put(self.tag_number)

        # really short lengths are already done
        if self.tag_lvt >= 5:
            if self.tag_lvt <= 253:
                pdu_data.put(self.tag_lvt)
            elif self.tag_lvt <= 65535:
                pdu_data.put(254)
                pdu_data.put_short(self.tag_lvt)
            else:
                pdu_data.put(255)
                pdu_data.put_long(self.tag_lvt)

        # now put the data
        pdu_data.put_data(self.tag_data)

        return pdu_data

    @classmethod
    def decode(cls, pdu_data: PDUData) -> Tag:
        """Decode a tag from the PDU."""
        try:
            tag = Tag()

            initial_octet = pdu_data.get()

            # extract the type
            tag.tag_class = TagClass((initial_octet >> 3) & 0x01)

            # extract the tag number
            tag.tag_number = initial_octet >> 4
            if tag.tag_number == 0x0F:
                tag.tag_number = pdu_data.get()

            # extract the length
            tag.tag_lvt = initial_octet & 0x07
            if tag.tag_lvt == 5:
                tag.tag_lvt = pdu_data.get()
                if tag.tag_lvt == 254:
                    tag.tag_lvt = pdu_data.get_short()
                elif tag.tag_lvt == 255:
                    tag.tag_lvt = pdu_data.get_long()
            elif tag.tag_lvt == 6:
                tag.tag_class = TagClass.opening
                tag.tag_lvt = 0
            elif tag.tag_lvt == 7:
                tag.tag_class = TagClass.closing
                tag.tag_lvt = 0

            # application tagged boolean has no more data
            if (tag.tag_class == TagClass.application) and (
                tag.tag_number == TagNumber.boolean
            ):
                # tag_lvt contains value
                tag.tag_data = b""
            else:
                # tag_lvt contains length
                tag.tag_data = pdu_data.get_data(tag.tag_lvt)
        except DecodingError:
            raise InvalidTag("invalid tag encoding")

        return tag

    def app_to_context(self, context: int) -> Tag:
        """Return a context tag from an application tag."""
        if self.tag_class != TagClass.application:
            raise ValueError("application tag required")

        # application tagged boolean now has data
        if self.tag_number == TagNumber.boolean:
            return ContextTag(context, bytearray([self.tag_lvt]))
        else:
            return ContextTag(context, self.tag_data)

    def context_to_app(self, tag_number: TagNumber) -> Tag:
        """Return an application tag from a context tag."""
        if self.tag_class != TagClass.context:
            raise ValueError("context tag required")

        # context booleans have value in data
        if tag_number == TagNumber.boolean:
            return Tag(
                TagClass.application,
                TagNumber.boolean,
                struct.unpack("B", self.tag_data)[0],
                b"",
            )
        else:
            return ApplicationTag(tag_number, self.tag_data)

    def app_to_object(self) -> Union[Atomic, None]:
        """Return the application object encoded by the tag."""
        if self.tag_class != TagClass.application:
            raise ValueError("application tag required")

        # get the class to build
        cls = cast(Type["Atomic"], self._app_tag_class[self.tag_number])
        if not cls:
            return None

        # tell the class to decode this tag and return an object
        return cast(Atomic, cls.decode(TagList([self])))

    def __repr__(self) -> str:
        sname = self.__module__ + "." + self.__class__.__name__
        try:
            if self.tag_class == TagClass.opening:
                desc = "(open(%d))" % (self.tag_number,)
            elif self.tag_class == TagClass.closing:
                desc = "(close(%d))" % (self.tag_number,)
            elif self.tag_class == TagClass.context:
                desc = "(context(%d))" % (self.tag_number,)
            elif self.tag_class == TagClass.application:
                desc = "(%s)" % (self._app_tag_name[self.tag_number],)
            else:
                raise ValueError("invalid tag class")
        except Exception:
            desc = "(?)"

        return "<" + sname + desc + " instance at 0x%08x" % (id(self),) + ">"

    def __eq__(self, tag: _Any) -> bool:
        """Tags are equal if all the attributes are equal."""
        assert isinstance(tag, Tag)

        return (
            (self.tag_class == tag.tag_class)
            and (self.tag_number == tag.tag_number)
            and (self.tag_lvt == tag.tag_lvt)
            and (self.tag_data == tag.tag_data)
        )

    def __ne__(self, arg: _Any) -> bool:
        """Inverse of __eq__."""
        return not self.__eq__(arg)

    def debug_contents(
        self,
        indent: int = 1,
        file: TextIO = sys.stderr,
        _ids: Optional[_List[_Any]] = None,
    ) -> None:
        # object reference first
        file.write("%s%r\n" % ("    " * indent, self))
        indent += 1

        # tag class
        msg = "%stag_class = %s " % ("    " * indent, self.tag_class)
        if self.tag_class == TagClass.application:
            msg += "application"
        elif self.tag_class == TagClass.context:
            msg += "context"
        elif self.tag_class == TagClass.opening:
            msg += "opening"
        elif self.tag_class == TagClass.closing:
            msg += "closing"
        else:
            msg += "?"
        file.write(msg + "\n")

        # tag number
        msg = "%stag_number = %d " % ("    " * indent, self.tag_number)
        if self.tag_class == TagClass.application:
            try:
                msg += self._app_tag_name[self.tag_number]
            except Exception:
                msg += "?"
        file.write(msg + "\n")

        # length, value, type
        file.write("%stag_lvt = %s\n" % ("    " * indent, self.tag_lvt))

        # data
        file.write("%stag_data = '%s'\n" % ("    " * indent, btox(self.tag_data, ".")))


class ApplicationTag(Tag):
    """
    Amazing documentation here.
    """

    def __init__(self, *args: _Any) -> None:
        if len(args) == 1 and isinstance(args[0], PDUData):
            Tag.__init__(self, args[0])
            if self.tag_class != TagClass.application:
                raise InvalidTag("application tag not decoded")
        elif len(args) == 2:
            tnum, tdata = args
            Tag.__init__(self, TagClass.application, tnum, len(tdata), tdata)
        else:
            raise ValueError("ApplicationTag ctor requires a type and data or PDUData")


class ContextTag(Tag):
    """
    Amazing documentation here.
    """

    def __init__(self, context: int, data: Union[bytes, bytearray]) -> None:
        Tag.__init__(self, TagClass.context, context, len(data), data)


class OpeningTag(Tag):
    """
    Amazing documentation here.
    """

    def __init__(self, context: int) -> None:
        Tag.__init__(self, TagClass.opening, context)


class ClosingTag(Tag):
    """
    Amazing documentation here.
    """

    def __init__(self, context: int) -> None:
        Tag.__init__(self, TagClass.closing, context)


class TagList(Iterable):
    """
    Amazing documentation here.
    """

    tagList: _List[Tag]

    def __init__(self, arg: Union[_List[Tag], TagList, PDUData, None] = None) -> None:
        self.tagList = []

        if isinstance(arg, list):
            self.tagList = arg
        elif isinstance(arg, TagList):
            self.tagList = arg.tagList[:]
        elif isinstance(arg, PDUData):
            self.decode(arg)

    def append(self, tag: Tag) -> None:
        self.tagList.append(tag)

    def extend(self, taglist: Iterable[Tag]) -> None:
        self.tagList.extend(taglist)

    def __getitem__(self, item: int) -> Tag:
        return self.tagList[item]

    def __len__(self) -> int:
        return len(self.tagList)

    def __iter__(self) -> Iterator[Tag]:
        return iter(self.tagList)

    def __eq__(self, other: object) -> bool:
        """Tag lists are equal if all the tags are equal."""
        if not isinstance(other, TagList):
            return NotImplemented
        if len(self) != len(other):
            return False
        return all(x == y for x, y in zip(self.tagList, other.tagList))

    def __ne__(self, arg: _Any) -> bool:
        """Inverse of __eq__."""
        return not self.__eq__(arg)

    def peek(self) -> Union[Tag, None]:
        """Return the tag at the front of the list."""
        if self.tagList:
            return self.tagList[0]
        else:
            return None

    def push(self, tag: Tag) -> None:
        """Return a tag back to the front of the list."""
        self.tagList = [tag] + self.tagList

    def pop(self) -> Union[Tag, None]:
        """Remove the tag from the front of the list and return it."""
        if self.tagList:
            tag = self.tagList[0]
            del self.tagList[0]
            return tag
        else:
            return None

    def pop_context(self) -> TagList:
        """Return a list of one application or context encoded tag, or a list
        of tags with matching opening/closing pairs.
        """
        # peek at the first tag
        tag = self.peek()
        if not tag:
            return TagList([])

        # application or context encoded tag
        if (tag.tag_class == TagClass.application) or (
            tag.tag_class == TagClass.context
        ):
            self.pop()
            return TagList([tag])

        # don't step on someone elses closing tag
        if tag.tag_class == TagClass.closing:
            return TagList([])

        # forward pass
        i = 0
        lvl = 0
        while i < len(self.tagList):
            tag = self.tagList[i]
            if tag.tag_class == TagClass.opening:
                lvl += 1
            elif tag.tag_class == TagClass.closing:
                lvl -= 1
                if lvl == 0:
                    break
            i += 1

        # make sure we have a matched pair
        if lvl != 0:
            raise InvalidTag("mismatched open/close tags")

        # result is the list of tags
        tag_list = TagList(self.tagList[: i + 1])
        del self.tagList[: i + 1]

        return tag_list

    def encode(self) -> PDUData:
        """Encode the tag list."""
        pdu_data = PDUData()
        for tag in self.tagList:
            pdu_data.put_data(tag.encode().pduData)
        return pdu_data

    @classmethod
    def decode(cls, pdu_data: PDUData) -> TagList:
        """Decode a list of tags from PDU data."""
        assert isinstance(pdu_data, PDUData)

        tag_list = TagList()
        while pdu_data.pduData:
            tag_list.append(Tag.decode(pdu_data))

        return tag_list

    def debug_contents(
        self,
        indent: int = 1,
        file: TextIO = sys.stderr,
        _ids: Optional[_List[_Any]] = None,
    ) -> None:
        for i, tag in enumerate(self.tagList):
            file.write("%s[%d] %r'\n" % ("    " * indent, i, tag))


@bacpypes_debugging
class ElementMetaclass(type):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _type_signatures: Dict[FrozenSet[Tuple[str, _Any]], type] = {}
    _signature_parameters = (
        "_context",
        "_optional",
        "_low_limit",
        "_high_limit",
        "_length",
        "_encoding",
        "_max_length",
        "_min_length",
        # "_prototype",  # reserved for fixed length arrays
    )

    def __new__(
        cls: _Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, _Any],
    ) -> ElementMetaclass:
        if _debug:
            ElementMetaclass._debug(
                "ElementMetaclass.__new__ %r %r %r %r",
                cls,
                clsname,
                superclasses,
                attributedict,
            )

        return cast(
            ElementMetaclass, type.__new__(cls, clsname, superclasses, attributedict)
        )

    def __call__(cls, *args: _Any, **kwargs: _Any) -> Union[ElementMetaclass, Element]:
        if _debug:
            ElementMetaclass._debug(
                "ElementMetaclass.__call__ %r %r %r", cls, args, kwargs
            )
        assert issubclass(cls, Element)

        if kwargs:
            for k in kwargs:
                if k not in ElementMetaclass._signature_parameters:
                    raise TypeError(f"unexpected keyword argument: {k}")

            sig = frozenset({"cls": cls, **kwargs}.items())
            if _debug:
                ElementMetaclass._debug("    - sig: %r", sig)

            if sig in ElementMetaclass._type_signatures:
                new_type = ElementMetaclass._type_signatures[sig]
            else:
                # new_type = type(cls.__name__ + "!", cls.__mro__, kwargs)
                new_type = type(cls.__name__, cls.__mro__, kwargs)

                # save the signature
                cast(Element, new_type)._signature = sig

                # save the signature parameters in the class
                for k, v in kwargs.items():
                    setattr(new_type, k, v)

                ElementMetaclass._type_signatures[sig] = new_type
            if _debug:
                ElementMetaclass._debug("    - new_type: %r", new_type)
        else:
            if _debug:
                ElementMetaclass._debug("    - vanilla")
            new_type = cls

        if args:
            if not isinstance(args[0], new_type):
                if _debug:
                    ElementMetaclass._debug("    - casting call: %r", new_type)
                args = (new_type.cast(args[0]),)  # type: ignore[attr-defined]
                if _debug:
                    ElementMetaclass._debug("    - args: %r", args)
            return cast(Element, type.__call__(new_type, *args))
        else:
            return cast(Element, new_type)


@bacpypes_debugging
class ElementInterface:
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _signature: FrozenSet[Tuple[str, _Any]] = frozenset()
    _optional: Optional[bool] = None
    _context: Optional[int] = None

    @classmethod
    def get_attribute(cls, getter: Callable[[], _Any]) -> _Any:
        if _debug:
            ElementInterface._debug("ElementInterface.get_attribute %r %r", cls, getter)
        return getter()

    @classmethod
    def set_attribute(
        cls, getter: Callable[[], _Any], setter: Callable[[_Any], None], value: _Any
    ) -> None:
        if _debug:
            ElementInterface._debug(
                "ElementInterface.set_attribute %r %r %r %r", cls, getter, setter, value
            )

        if cls._optional and value is None:
            # None is accepted for optional elements
            pass
        elif type(value) is not cls:
            # make sure the object type is preserved
            value = cls.cast(value)

        # pass along the value change
        setter(value)

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        raise NotImplementedError(f"cast() not implemented: {cls}")

    @classmethod
    async def read_property(
        cls, getter: Optional[Callable[[], _Any]], index: Optional[int] = None
    ) -> _Any:
        if _debug:
            ElementInterface._debug(
                "ElementInterface.read_property %r %r %r", cls, getter, index
            )
        if index is not None:
            raise PropertyError("propertyIsNotAnArray")
        if not getter:
            raise PropertyError("readAccessDenied")

        # get the value, wait for it if necessary
        value = getter()
        if _debug:
            ElementInterface._debug("    - value:", value)
        if inspect.isawaitable(value):
            if _debug:
                ElementInterface._debug("    - awaitable")
            value = await value

        return value

    @classmethod
    async def write_property(
        cls,
        getter: Callable[[], _Any],
        setter: Optional[Callable[[_Any], _Any]],
        value: _Any,
        index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        if _debug:
            ElementInterface._debug(
                "ElementInterface.write_property %r %r %r %r %r %r",
                cls,
                getter,
                setter,
                value,
                index,
                priority,
            )
        if index is not None:
            raise PropertyError("propertyIsNotAnArray")
        if not setter:
            raise PropertyError("writeAccessDenied")
        if priority is not None:
            if _debug:
                ElementInterface._debug("    - priority is ignored")

        # set the value, wait for it if necessary
        fn_result = setter(value)
        if _debug:
            ElementInterface._debug("    - fn_result: %r", fn_result)
        if inspect.isawaitable(fn_result):
            if _debug:
                ElementInterface._debug("    - awaitable")
            await fn_result

    def encode(self) -> TagList:
        """Encode the element as a tag list."""
        if _debug:
            ElementInterface._debug("encode")
        raise NotImplementedError

    @classmethod
    def decode(cls, tag_list: TagList) -> ElementInterface:
        """Decode an element from a tag list."""
        if _debug:
            ElementInterface._debug("decode %r %r", cls, tag_list)
        raise NotImplementedError


class Element(ElementInterface, metaclass=ElementMetaclass):
    pass


@bacpypes_debugging
class Atomic(Element):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _value: _Any = None

    def __init__(
        self,
        *args: _Any,
        _optional: Optional[bool] = None,
        _context: Optional[int] = None,
        **kwargs: _Any,
    ) -> None:
        if _debug:
            Atomic._debug("Atomic.__init__ %r %r", args, kwargs)

        # handy reference
        self._value = args[0] if args else None


@bacpypes_debugging
class Null(Atomic, tuple):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if isinstance(arg, (tuple, list)):
            if len(arg) != 0:
                raise ValueError()
        elif isinstance(arg, str):
            if arg.lower() != "null":
                raise ValueError()
        else:
            raise TypeError()

        return ()

    def encode(self) -> TagList:
        """Encode a null element as a tag list."""
        if _debug:
            ElementInterface._debug("Null.encode")

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.null, b"")
        else:
            tag = ContextTag(self._context, b"")
        if _debug:
            ElementInterface._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Null:
        """Decode an element from a tag list."""
        if _debug:
            ElementInterface._debug("Null.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("empty tag list")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"null context tag {cls._context} expected")
            if tag.tag_number != TagNumber.null:
                raise InvalidTag("null application tag required")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("null application tag required")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) != 0:
            raise InvalidTag("invalid tag length")

        # return an instance of this thing
        return cls(())


@bacpypes_debugging
class Boolean(Atomic, int):
    """
    Note that this is a subclass of the int built-in type, bool cannot be.
    """

    _debug: Callable[..., None]

    def __init__(
        self,
        *args: bool,
        _optional: Optional[bool] = None,
        _context: Optional[int] = None,
    ) -> None:
        if _debug:
            Boolean._debug("Boolean.__init__ %r", args)

        if args:
            if isinstance(args[0], bool):
                pass
            elif isinstance(args[0], int):
                if args[0] not in (0, 1):
                    raise ValueError()
            else:
                raise TypeError()

        super().__init__(*args)

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Boolean._debug("Boolean.cast %r", arg)

        if isinstance(arg, bool):
            pass
        elif isinstance(arg, int):
            arg = bool(arg)
        elif isinstance(arg, str):
            arg = arg.lower()
            if arg in ("1", "set", "true"):
                arg = True
            elif arg in ("0", "reset", "false"):
                arg = False
            else:
                raise ValueError()
        else:
            raise TypeError()

        return arg

    def encode(self) -> TagList:
        """Encode a null element as a tag list."""
        if _debug:
            Boolean._debug("Boolean.encode")

        tag: Tag
        if self._context is None:
            tag = Tag(TagClass.application, TagNumber.boolean, int(self), b"")
        else:
            tag = ContextTag(self._context, bytes([int(self)]))
        if _debug:
            Boolean._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Boolean:
        """Decode an element from a tag list."""
        if _debug:
            Boolean._debug("Boolean.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("empty tag list")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"boolean context tag {cls._context} expected")
            if tag.tag_number != TagNumber.boolean:
                raise InvalidTag("boolean application tag expected")
            value = bool(tag.tag_lvt)
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("boolean application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            if len(tag.tag_data) != 1:
                raise InvalidTag("invalid tag length")
            value = bool(tag.tag_data[0])
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if _debug:
            Boolean._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


@bacpypes_debugging
class Unsigned(Atomic, int):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _base: Optional[int] = 0
    _low_limit: Optional[int] = None
    _high_limit: Optional[int] = None

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Unsigned._debug("Unsigned.cast %r", arg)

        if isinstance(arg, str):
            arg = int(arg, base=cls._base or 0)  # type: ignore[attr-defined]
        elif isinstance(arg, bool) or (not isinstance(arg, int)):
            raise TypeError()

        if arg < 0:
            raise ValueError("unsigned")

        low_limit = getattr(cls, "_low_limit", None)
        if (low_limit is not None) and (arg < low_limit):
            raise ValueError("low limit")

        high_limit = getattr(cls, "_high_limit", None)
        if (high_limit is not None) and (arg > high_limit):
            raise ValueError("high limit")

        return arg

    def encode(self) -> TagList:
        """Encode an unsigned element as a tag list."""
        if _debug:
            Unsigned._debug("Unsigned.encode")

        # rip apart the number
        data = bytearray(struct.pack(">L", self))
        if _debug:
            Unsigned._debug("    - data: %r", data)

        # reduce the value to the smallest number of octets
        while (len(data) > 1) and (data[0] == 0):
            del data[0]

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.unsigned, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Unsigned._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Unsigned:
        """Decode an unsigned element from a tag list."""
        if _debug:
            Unsigned._debug("Unsigned.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("unsigned application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"unsigned context tag {cls._context} expected")
            if tag.tag_number != TagNumber.unsigned:
                raise InvalidTag("unsigned application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("unsigned application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 1:
            raise InvalidTag("invalid tag length")

        # get the data
        value = 0
        for c in tag.tag_data:
            value = (value << 8) + c
        if _debug:
            Unsigned._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


class Unsigned8(Unsigned):
    """
    Amazing documentation here.
    """

    _high_limit = 255


class Unsigned16(Unsigned):
    """
    Amazing documentation here.
    """

    _high_limit = 65535


@bacpypes_debugging
class Integer(Atomic, int):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _base: Optional[int] = 0
    _low_limit: Optional[int] = None
    _high_limit: Optional[int] = None

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Integer._debug("Integer.cast %r", arg)

        if isinstance(arg, str):
            arg = int(arg, base=cls._base or 0)  # type: ignore[attr-defined]
        elif isinstance(arg, bool) or (not isinstance(arg, int)):
            raise TypeError()

        low_limit = getattr(cls, "_low_limit", None)
        if (low_limit is not None) and (arg < low_limit):
            raise ValueError("low limit")

        high_limit = getattr(cls, "_high_limit", None)
        if (high_limit is not None) and (arg > high_limit):
            raise ValueError("high limit")

        return arg

    def encode(self) -> TagList:
        """Encode an integer as a tag list."""
        if _debug:
            Integer._debug("Integer.encode")

        # rip apart the number
        data = bytearray(struct.pack(">I", self & 0xFFFFFFFF))

        # reduce the value to the smallest number of bytes, be
        # careful about sign extension
        if self < 0:
            while len(data) > 1:
                if data[0] != 255:
                    break
                if data[1] < 128:
                    break
                del data[0]
        else:
            while len(data) > 1:
                if data[0] != 0:
                    break
                if data[1] >= 128:
                    break
                del data[0]

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.integer, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Integer._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Integer:
        """Decode an integer from a tag list."""
        if _debug:
            Integer._debug("Integer.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if _debug:
            Integer._debug("    - tag: %r %r", tag, tag.tag_data if tag else None)

        if not tag:
            raise InvalidTag("integer application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"integer context tag {cls._context} expected")
            if tag.tag_number != TagNumber.integer:
                raise InvalidTag("integer application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("integer application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 1:
            raise InvalidTag("invalid tag length")

        # get the data
        value = tag.tag_data[0]
        if (value & 0x80) != 0:
            value = (-1 << 8) | value
        for c in tag.tag_data[1:]:
            value = (value << 8) | c
        if _debug:
            Unsigned._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


@bacpypes_debugging
class Real(Atomic, float):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _low_limit: Optional[float] = None
    _high_limit: Optional[float] = None

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Real._debug("Real.cast %r", arg)

        if isinstance(arg, str):
            arg = float(arg)
        elif isinstance(arg, int):
            arg = float(arg)
        elif not isinstance(arg, float):
            raise TypeError()

        low_limit = getattr(cls, "_low_limit", None)
        if (low_limit is not None) and (arg < low_limit):
            raise ValueError("low limit exceeded")

        high_limit = getattr(cls, "_high_limit", None)
        if (high_limit is not None) and (arg > high_limit):
            raise ValueError("high limit exceeded")

        return arg

    def encode(self) -> TagList:
        """Encode a real as a tag list."""
        if _debug:
            Real._debug("Real.encode")

        data = struct.pack(">f", self)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.real, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Real._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Real:
        """Decode a real from a tag list."""
        if _debug:
            Real._debug("Real.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("real application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"real context tag {cls._context} expected")
            if tag.tag_number != TagNumber.real:
                raise InvalidTag("real application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("real application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 4:
            raise InvalidTag("invalid tag length")

        # get the data
        value = struct.unpack(">f", tag.tag_data)[0]
        if _debug:
            Real._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


class Double(Real):
    """
    Amazing documentation here.
    """

    def encode(self) -> TagList:
        """Encode a double as a tag list."""
        if _debug:
            Double._debug("Double.encode")

        data = struct.pack(">d", self)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.double, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Double._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Double:
        """Decode a double from a tag list."""
        if _debug:
            Double._debug("Double.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("double application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"double context tag {cls._context} expected")
            if tag.tag_number != TagNumber.double:
                raise InvalidTag("double application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("double application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 8:
            raise InvalidTag("invalid tag length")

        # get the data
        value = struct.unpack(">d", tag.tag_data)[0]
        if _debug:
            Double._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


@bacpypes_debugging
class OctetString(Atomic, bytes):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _min_length: Optional[int]
    _max_length: Optional[int]

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            OctetString._debug("OctetString.cast %r", arg)
        if not isinstance(arg, (bytes, bytearray)):
            raise TypeError("bytes or bytearray expected")

        min_length = getattr(cls, "_min_length", None)
        if (min_length is not None) and (len(arg) < min_length):
            raise ValueError(f"minimum length: {min_length}")

        max_length = getattr(cls, "_max_length", None)
        if (max_length is not None) and (len(arg) > max_length):
            raise ValueError(f"maximum length: {max_length}")

        return arg

    def encode(self) -> TagList:
        """Encode an octet string as a tag list."""
        if _debug:
            OctetString._debug("OctetString.encode")

        # strip off any class identity and just get the data
        data = bytes(self)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.octetString, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            OctetString._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> OctetString:  # type: ignore[override]
        """
        Decode an octet string from a tag.  Note that this overrides the
        bytes.decode() function, which can be called by bytes.decode(obj,...).
        """
        if _debug:
            OctetString._debug("OctetString.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("octet string application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"octet string context tag {cls._context} expected")
            if tag.tag_number != TagNumber.octetString:
                raise InvalidTag("octet string application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("octet string application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")

        # return an instance of this thing
        return cls(tag.tag_data)


@bacpypes_debugging
class CharacterString(Atomic, str):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _encoding: int = 0
    _min_length: Optional[int]
    _max_length: Optional[int]

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            CharacterString._debug("CharacterString.cast %r", arg)
        if not isinstance(arg, str):
            raise TypeError("string expected")

        min_length = getattr(cls, "_min_length", None)
        if (min_length is not None) and (len(arg) < min_length):
            raise ValueError(f"minimum length: {min_length}")

        max_length = getattr(cls, "_max_length", None)
        if (max_length is not None) and (len(arg) > max_length):
            raise ValueError(f"maximum length: {max_length}")

        return arg

    def encode(self) -> TagList:  # type: ignore[override]
        """
        Encode the character string as a tag.  Note that this overrides the
        str.encode() function, which can be called by str.encode(obj,...).
        """
        if _debug:
            CharacterString._debug("CharacterString.encode")

        # start with the encoding
        data = bytes([self._encoding])

        # encode the value
        if self._encoding == 0:
            data += str.encode(self, "utf-8", "strict")
        elif self._encoding == 3:
            data += str.encode(self, "utf_32be")
        elif self._encoding == 4:
            data += str.encode(self, "utf_16be")
        elif self._encoding == 5:
            data += str.encode(self, "latin_1")
        else:
            raise ValueError(f"unknown encoding: {self._encoding}")

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.characterString, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            CharacterString._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> CharacterString:
        """Decode a character string from a tag."""
        if _debug:
            CharacterString._debug("CharacterString.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("character string application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(
                    f"character string context tag {cls._context} expected"
                )
            if tag.tag_number != TagNumber.characterString:
                raise InvalidTag("character string application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("character string application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 1:
            raise InvalidTag("invalid tag length")

        # extract the encoding
        encoding = tag.tag_data[0]
        data = bytes(tag.tag_data[1:])

        if encoding not in (0, 3, 4, 5):
            if _debug:
                CharacterString._debug("    - unknowing encoding: %r", encoding)
            encoding = 0

        # decode the data
        if encoding == 0:
            try:
                value = bytes.decode(data, "utf-8", "strict")
            except UnicodeDecodeError:
                # Wrong encoding... trying with latin-1 as
                # we probably face a Windows software encoding issue
                try:
                    value = bytes.decode(data, "latin-1")
                except UnicodeDecodeError:
                    raise
        elif encoding == 3:
            value = bytes.decode(data, "utf_32be")
        elif encoding == 4:
            value = bytes.decode(data, "utf_16be")
        elif encoding == 5:
            value = bytes.decode(data, "latin_1")
        if _debug:
            CharacterString._debug("    - value: %r", value)

        # most of the time the encoding matches
        if encoding == cls._encoding:
            return cls(value)

        # build a new class, preserving this cls attributes
        kwargs: Dict[str, _Any] = {"_encoding": encoding}
        optional = getattr(cls, "_optional", None)
        if optional is not None:
            kwargs["_optional"] = optional
        context = getattr(cls, "_context", None)
        if context is not None:
            kwargs["_context"] = context
        min_length = getattr(cls, "_min_length", None)
        if min_length is not None:
            kwargs["_min_length"] = min_length
        min_length = getattr(cls, "_min_length", None)
        if min_length is not None:
            kwargs["_min_length"] = min_length
        if _debug:
            CharacterString._debug("    - new class: %r", kwargs)

        # return an instance of this thing
        return cls(value, **kwargs)


@bacpypes_debugging
class BitStringMetaclass(ElementMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __new__(
        cls: _Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, _Any],
    ) -> BitStringMetaclass:
        if _debug:
            BitStringMetaclass._debug(
                "BitStringMetaclass.__new__ %r %r %r %r",
                cls,
                clsname,
                superclasses,
                attributedict,
            )

        # start with an empty enumeration map
        _bitstring_names: Dict[str, int] = {}
        _bitstring_length: int = 0

        # include the maps we've already built
        for supercls in reversed(superclasses):
            if hasattr(supercls, "_bitstring_names"):
                _bitstring_names.update(supercls._bitstring_names)  # type: ignore[attr-defined]
            if hasattr(supercls, "_bitstring_length"):
                _bitstring_length = max(_bitstring_length, supercls._bitstring_length)  # type: ignore[attr-defined]

        # look for integer properties
        for attr, value in attributedict.items():
            if (not attr.startswith("_")) and isinstance(value, int):
                split_attr = attr_to_asn1(attr)
                # _bitstring_names[attr] = value
                _bitstring_names[split_attr] = value

        # compute the length
        if _bitstring_names:
            min_length = max(_bitstring_names.values()) + 1
            _bitstring_length = max(_bitstring_length, min_length)

        # add special attributes to the class
        attributedict["_bitstring_names"] = _bitstring_names
        attributedict["_bitstring_length"] = _bitstring_length
        if _debug:
            BitStringMetaclass._debug("    - _bitstring_names: %r", _bitstring_names)
            BitStringMetaclass._debug("    - _bitstring_length: %r", _bitstring_length)

        new_class = cast(
            BitStringMetaclass,
            super().__new__(cls, clsname, superclasses, attributedict),
        )
        if _debug:
            BitStringMetaclass._debug("    - new_class: %r", new_class)

        return new_class

    def __call__(cls, *args: _Any, **kwargs: _Any) -> BitString:
        if _debug:
            BitStringMetaclass._debug(
                "BitStringMetaclass.__call__(%s) %r %r", cls.__name__, args, kwargs
            )
        assert issubclass(cls, BitString)

        if args:
            args = (cls.cast(args[0]),)  # type: ignore[attr-defined]

        # continue with the ElementMetaclass
        new_obj = cast(BitString, super().__call__(*args, **kwargs))
        if _debug:
            BitStringMetaclass._debug("    - new_obj: %r", new_obj)

        # if this is a class, just return it
        if inspect.isclass(new_obj):
            if _debug:
                BitStringMetaclass._debug("    - it's a class")
            return cast(BitString, new_obj)

        # hideousness with lists
        list.__init__(new_obj, *args)

        return new_obj


@bacpypes_debugging
class BitString(Atomic, list, metaclass=BitStringMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _bitstring_names: Dict[str, int] = {}
    _bitstring_length: int

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        if _debug:
            BitString._debug("BitString.cast %r", arg)
        assert issubclass(cls, BitString)

        # translate string or lists of strings and ints
        if isinstance(arg, list):
            arg_list = arg
        elif isinstance(arg, str):
            if not arg:
                arg_list = []
            else:
                arg_list = arg.split(";")
        else:
            raise TypeError()
        if _debug:
            BitString._debug("    - arg_list: %r", arg_list)

        # look for just 0's and 1's or include bit numbers and named bits
        only_bits = all((bit == 0) or (bit == 1) for bit in arg_list)
        if not only_bits:
            bits = []
            for bit_name in arg_list:
                if bit_name in cls._bitstring_names:
                    bit_value = cls._bitstring_names[bit_name]
                elif isinstance(bit_name, int):
                    bit_value = bit_name
                else:
                    bit_value = int(bit_name, base=0)
                bits.append(bit_value)

            bit_list = [0] * (max(bits) + 1)
            for bit_value in bits:
                bit_list[bit_value] = 1

            arg_list = bit_list

        # extend it to make sure it includes the named bits
        bitstring_length = getattr(cls, "_bitstring_length", 0)
        if len(arg_list) < bitstring_length:
            arg_list.extend([0] * (bitstring_length - len(arg_list)))

        return arg_list

    def __getitem__(self, item: Union[int, str]) -> int:  # type: ignore[override]
        if _debug:
            BitString._debug("BitString.__getitem__ %r", item)

        if isinstance(item, int):
            pass
        elif isinstance(item, str):
            item = self._bitstring_names[item]

        return cast(int, super().__getitem__(item))

    def __setitem__(self, item: Union[int, str], value: int) -> None:  # type: ignore[override]
        if _debug:
            BitString._debug("BitString.__setitem__ %r %r", item, value)

        if isinstance(item, int):
            pass
        elif isinstance(item, str):
            item = self._bitstring_names[item]

        super().__setitem__(item, value)

    def __str__(self) -> str:
        bit_names = {v: k for k, v in self._bitstring_names.items()}

        bits_set = []
        for bit_number, bit in enumerate(self):
            if bit:
                bits_set.append(bit_names.get(bit_number, str(bit_number)))

        return ";".join(bits_set)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {str(self)}>"

    def encode(self) -> TagList:
        """Encode an octet string as a tag list."""
        if _debug:
            BitString._debug("BitString.encode")

        # compute the unused bits to fill out the string
        _, used = divmod(len(self), 8)
        unused = used and (8 - used) or 0

        # start with the number of unused bits
        data = bytearray([unused])

        # build and append each packed octet
        bits = self + [0] * unused
        for i in range(0, len(bits), 8):
            x = 0
            for j in range(0, 8):
                x |= bits[i + j] << (7 - j)
            data.append(x)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.bitString, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            BitString._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> BitString:
        """
        Decode a bit string from a tag.  Note that this overrides the
        bytes.decode() function, which can be called by bytes.decode(obj,...).
        """
        if _debug:
            BitString._debug("BitString.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("bit string application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"bit string context tag {cls._context} expected")
            if tag.tag_number != TagNumber.bitString:
                raise InvalidTag("bit string application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("bit string application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")

        tag_data = bytearray(tag.tag_data)

        # extract the number of unused bits
        unused = tag_data[0]

        # extract the data
        data = []
        for x in tag_data[1:]:
            for i in range(8):
                if (x & (1 << (7 - i))) != 0:
                    data.append(1)
                else:
                    data.append(0)

        # trim off the unused bits
        if unused:
            value = data[:-unused]
        else:
            value = data

        # return an instance of this thing
        return cls(value)


@bacpypes_debugging
class EnumeratedMetaclass(ElementMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __new__(
        cls: _Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, _Any],
    ) -> EnumeratedMetaclass:
        if _debug:
            EnumeratedMetaclass._debug(
                "EnumeratedMetaclass.__new__ %r %r %r %r",
                cls,
                clsname,
                superclasses,
                attributedict,
            )

        # start with an empty enumeration map
        _enum_map: Dict[str, int] = {}
        _attr_map: Dict[int, str] = {}
        _asn1_map: Dict[int, str] = {}

        # include the maps we've already built
        for supercls in reversed(superclasses):
            if hasattr(supercls, "_enum_map"):
                _enum_map.update(supercls._enum_map)  # type: ignore[attr-defined]
            if hasattr(supercls, "_attr_map"):
                _attr_map.update(supercls._attr_map)  # type: ignore[attr-defined]
            if hasattr(supercls, "_asn1_map"):
                _asn1_map.update(supercls._asn1_map)  # type: ignore[attr-defined]

        # look for integer properties
        for attr, value in attributedict.items():
            if (not attr.startswith("_")) and isinstance(value, int):
                split_attr = attr_to_asn1(attr)
                _enum_map[split_attr] = value
                _enum_map[attr] = value
                _attr_map[value] = attr
                _asn1_map[value] = split_attr

        # add this special attribute to the class
        attributedict["_enum_map"] = _enum_map
        attributedict["_attr_map"] = _attr_map
        attributedict["_asn1_map"] = _asn1_map
        if _debug:
            EnumeratedMetaclass._debug("    - _enum_map: %r", _enum_map)

        # build the class
        new_class = cast(
            EnumeratedMetaclass,
            super().__new__(cls, clsname, superclasses, attributedict),
        )

        return new_class

    def __call__(cls, *args: _Any, **kwargs: _Any) -> Enumerated:
        if _debug:
            EnumeratedMetaclass._debug(
                "EnumeratedMetaclass.__call__ %r %r", args, kwargs
            )
        assert issubclass(cls, Enumerated)

        # look up the string or interpret it as an int
        if args and isinstance(args[0], str):
            if args[0] in cls._enum_map:  # type: ignore[attr-defined]
                args = (cls._enum_map[args[0]],)  # type: ignore[attr-defined]
            else:
                try:
                    args = (int(args[0], base=0),)
                except ValueError:
                    raise ValueError(args[0])
        if _debug:
            EnumeratedMetaclass._debug("    - args: %r", args)

        # continue with the ElementMetaclass
        return cast(Enumerated, super().__call__(*args, **kwargs))


@bacpypes_debugging
class Enumerated(Atomic, int, metaclass=EnumeratedMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _enum_map: Dict[str, int] = {}
    _attr_map: Dict[int, str]
    _asn1_map: Dict[int, str]
    _low_limit: int = 0
    _high_limit: Optional[int] = None

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Enumerated._debug("Enumerated.cast %r", arg)
        assert issubclass(cls, Enumerated)

        if isinstance(arg, str):
            if arg in cls._enum_map:
                arg = cls._enum_map[arg]
            else:
                try:
                    arg = int(arg, base=0)
                except ValueError:
                    raise ValueError(arg)
        elif isinstance(arg, int):
            pass
        else:
            raise TypeError()
        if _debug:
            Enumerated._debug("    - arg: %r", arg)

        low_limit = getattr(cls, "_low_limit", None)
        if (low_limit is not None) and (arg < low_limit):
            raise ValueError("low limit exceeded")

        high_limit = getattr(cls, "_high_limit", None)
        if (high_limit is not None) and (arg > high_limit):
            raise ValueError("high limit exceeded")

        return arg

    @property
    def attr(self) -> str:
        return self._attr_map.get(self, str(self._value))

    @property
    def asn1(self) -> str:
        return self._asn1_map.get(self, str(self._value))

    def __str__(self) -> str:
        return self.asn1

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.asn1}>"

    def encode(self) -> TagList:
        """Encode an enumerated element as a tag list."""
        if _debug:
            Enumerated._debug("Enumerated.encode")

        # pack the number
        data = bytearray(struct.pack(">L", self))
        if _debug:
            Enumerated._debug("    - data: %r", data)

        # reduce the value to the smallest number of octets
        while (len(data) > 1) and (data[0] == 0):
            del data[0]

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.enumerated, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Enumerated._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Enumerated:
        """Decode an enumerated element from a tag list."""
        if _debug:
            Enumerated._debug("Enumerated.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("enumerated application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"enumerated context tag {cls._context} expected")
            if tag.tag_number != TagNumber.enumerated:
                raise InvalidTag("enumerated application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("enumerated application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) < 1:
            raise InvalidTag("invalid tag length")

        # get the data
        value = 0
        for c in tag.tag_data:
            value = (value << 8) + c
        if _debug:
            Enumerated._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


#
#   Date
#

_mm = r"(?P<month>0?[1-9]|1[0-4]|odd|even|255|[*])"
_dd = r"(?P<day>[0-3]?\d|last|odd|even|255|[*])"
_yy = r"(?P<year>\d{2}|255|[*])"
_yyyy = r"(?P<year>\d{4}|255|[*])"
_dow = r"(?P<dow>[1-7]|mon|tue|wed|thu|fri|sat|sun|255|[*])"

_special_mon = {"*": 255, "odd": 13, "even": 14, None: 255}
_special_mon_inv = {255: "*", 13: "odd", 14: "even"}

_special_day = {"*": 255, "last": 32, "odd": 33, "even": 34, None: 255}
_special_day_inv = {255: "*", 32: "last", 33: "odd", 34: "even"}

_special_dow = {
    "*": 255,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
    "sun": 7,
}
_special_dow_inv = {
    255: "*",
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun",
}


def _merge(*args):
    """Create a composite pattern and compile it."""
    return re.compile(r"^" + r"[/-]".join(args) + r"(?:\s+" + _dow + ")?$")


# make a list of compiled patterns
_date_patterns = [
    _merge(_yyyy, _mm, _dd),
    _merge(_mm, _dd, _yyyy),
    _merge(_dd, _mm, _yyyy),
    _merge(_yy, _mm, _dd),
    _merge(_mm, _dd, _yy),
    _merge(_dd, _mm, _yy),
]


@bacpypes_debugging
class Date(Atomic, tuple):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Date._debug("Date.cast %r", arg)

        if isinstance(arg, tuple):
            if len(arg) != 4:
                raise ValueError("4-tuple expected")

            # allow a full year
            year = arg[0]
            if year > 1900:
                arg = (year - 1900,) + arg[1:]

        elif isinstance(arg, datetime.date):
            arg = (arg.year - 1900, arg.month, arg.day, arg.weekday() + 1)

        elif isinstance(arg, str):
            # lower case everything
            arg = arg.lower()

            # make a list of the contents from matching patterns
            matches = []
            for p in _date_patterns:
                m = p.match(arg)
                if m:
                    matches.append(m.groupdict())

            # try to find a good one
            match = None
            if not matches:
                raise ValueError("unmatched")

            # if there is only one, success
            if len(matches) == 1:
                match = matches[0]
            else:
                # check to see if they really are the same
                for a, b in zip(matches[:-1], matches[1:]):
                    if a != b:
                        raise ValueError("ambiguous")
                        break
                else:
                    match = matches[0]

            # extract the year and normalize
            year = match["year"]
            if (year == "*") or (not year):
                year = 255
            else:
                year = int(year)
                if year == 255:
                    pass
                elif year < 35:
                    year += 2000
                elif year < 100:
                    year += 1900
                elif year < 1900:
                    raise ValueError("invalid year")

            # extract the month and normalize
            month = match["month"]
            if month in _special_mon:
                month = _special_mon[month]
            else:
                month = int(month)
                if month == 255:
                    pass
                elif (month == 0) or (month > 14):
                    raise ValueError("invalid month")

            # extract the day and normalize
            day = match["day"]
            if day in _special_day:
                day = _special_day[day]
            else:
                day = int(day)
                if day == 255:
                    pass
                elif (day == 0) or (day > 34):
                    raise ValueError("invalid day")

            # extract the day-of-week and normalize
            day_of_week = match["dow"]
            if day_of_week in _special_dow:
                day_of_week = _special_dow[day_of_week]
            elif not day_of_week:
                pass
            else:
                day_of_week = int(day_of_week)
                if day_of_week == 255:
                    pass
                elif day_of_week > 7:
                    raise ValueError("invalid day of week")

            # year becomes the correct octet
            if year != 255:
                year -= 1900

            # assume the worst
            day_of_week = 255

            # check for special values
            if year == 255:
                pass
            elif month in _special_mon_inv:
                pass
            elif day in _special_day_inv:
                pass
            else:
                try:
                    today = time.mktime((year + 1900, month, day, 0, 0, 0, 0, 0, -1))
                    day_of_week = time.gmtime(today)[6] + 1
                except OverflowError:
                    pass

            # save the value
            arg = (year, month, day, day_of_week)

        else:
            raise TypeError()

        return arg

    @classmethod
    def now(cls: type, when: Optional[float] = None) -> Date:
        """Set the current value to the correct tuple based on the seconds
        since the epoch.
        """
        if when is None:
            when = time.time()
        tup = time.localtime(when)

        # convert to the correct tuple values
        value = (tup[0] - 1900, tup[1], tup[2], tup[6] + 1)

        # return an instance
        return cast(Date, cls(value))

    @property
    def is_special(self) -> bool:
        """Date has wildcard values."""
        # rip it apart
        year, month, day, day_of_week = self

        return (
            (year == 255)
            or (month in _special_mon_inv)
            or (day in _special_day_inv)
            or (day_of_week == 255)
        )

    def __str__(self) -> str:
        """String representation of the date."""
        # rip it apart
        year, month, day, day_of_week = self

        if year == 255:
            year = "*"
        else:
            year = str(year + 1900)

        month = _special_mon_inv.get(month, str(month))
        day = _special_day_inv.get(day, str(day))
        day_of_week = _special_dow_inv.get(day_of_week, str(day_of_week))

        return "%s-%s-%s %s" % (
            year,
            month,
            day,
            day_of_week,
        )

    def encode(self) -> TagList:
        """Encode an enumerated element as a tag list."""
        if _debug:
            Date._debug("Date.encode")

        # pack the value
        data = bytearray(self)
        if _debug:
            Date._debug("    - data: %r", data)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.date, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Date._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Date:
        """Decode an enumerated element from a tag list."""
        if _debug:
            Date._debug("Date.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("date application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"date context tag {cls._context} expected")
            if tag.tag_number != TagNumber.date:
                raise InvalidTag("date application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("date application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) != 4:
            raise InvalidTag("invalid tag length")

        # get the data
        value = tuple(tag.tag_data)
        if _debug:
            Date._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


#
#   Time
#

_time_regex = re.compile(
    "^([*]|[0-9]+)[:]([*]|[0-9]+)(?:[:]([*]|[0-9]+)(?:[.]([*]|[0-9]+))?)?$"
)


@bacpypes_debugging
class Time(Atomic, tuple):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            Time._debug("Time.cast %r")

        if isinstance(arg, tuple):
            if len(arg) != 4:
                raise ValueError("4-tuple expected")
        elif isinstance(arg, datetime.time):
            arg = (arg.hour, arg.minute, arg.second, int(arg.microsecond / 10000.0))
        elif isinstance(arg, str):
            tup_match = _time_regex.match(arg)
            if not tup_match:
                raise ValueError("invalid time pattern")

            tup_list = []
            tup_items = list(tup_match.groups())
            for s in tup_items:
                if s == "*":
                    tup_list.append(255)
                elif s is None:
                    if "*" in tup_items:
                        tup_list.append(255)
                    else:
                        tup_list.append(0)
                else:
                    tup_list.append(int(s))

            # fix the hundredths if necessary
            if (tup_list[3] > 0) and (tup_list[3] < 10):
                tup_list[3] = tup_list[3] * 10

            arg = tuple(tup_list)

        else:
            raise TypeError()

        return arg

    @classmethod
    def now(cls: type, when: Optional[float] = None) -> Time:
        """
        Set the current value to the correct tuple based on the seconds
        since the epoch.
        """
        if when is None:
            when = time.time()
        tup = time.localtime(when)

        # convert to the correct tuple values
        value = (tup[3], tup[4], tup[5], int((when - int(when)) * 100))

        # return an instance
        return cast(Time, cls(value))

    @property
    def is_special(self) -> bool:
        """Date has wildcard values."""
        # rip it apart
        hour, minute, second, hundredth = self

        return (hour == 255) or (minute == 255) or (second == 255) or (hundredth == 255)

    def __str__(self) -> str:
        # rip it apart
        hour, minute, second, hundredth = self

        rslt = ""
        if hour == 255:
            rslt += "*:"
        else:
            rslt += "%02d:" % (hour,)
        if minute == 255:
            rslt += "*:"
        else:
            rslt += "%02d:" % (minute,)
        if second == 255:
            rslt += "*."
        else:
            rslt += "%02d." % (second,)
        if hundredth == 255:
            rslt += "*"
        else:
            rslt += "%02d" % (hundredth,)

        return rslt

    def encode(self) -> TagList:
        """Encode an enumerated element as a tag list."""
        if _debug:
            Time._debug("Time.encode")

        # pack the value
        data = bytearray(self)
        if _debug:
            Date._debug("    - data: %r", data)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.time, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            Date._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> Time:
        """Decode an enumerated element from a tag list."""
        if _debug:
            Time._debug("Time.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("time application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"enumerated context tag {cls._context} expected")
            if tag.tag_number != TagNumber.time:
                raise InvalidTag("time application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("time application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) != 4:
            raise InvalidTag("invalid tag length")

        # get the data
        value = tuple(tag.tag_data)
        if _debug:
            Time._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


class ObjectType(Enumerated):
    _vendor_range = (128, 1023)
    _high_limit: int = 1023
    accessCredential = 32
    accessDoor = 30
    accessPoint = 33
    accessRights = 34
    accessUser = 35
    accessZone = 36
    accumulator = 23
    alertEnrollment = 52
    analogInput = 0
    analogOutput = 1
    analogValue = 2
    auditLog = 61
    auditReporter = 62
    averaging = 18
    binaryInput = 3
    binaryLightingOutput = 55
    binaryOutput = 4
    binaryValue = 5
    bitstringValue = 39
    calendar = 6
    channel = 53
    characterstringValue = 40
    command = 7
    credentialDataInput = 37
    datePatternValue = 41
    dateValue = 42
    datetimePatternValue = 43
    datetimeValue = 44
    device = 8
    elevatorGroup = 57
    escalator = 58
    eventEnrollment = 9
    eventLog = 25
    file = 10
    globalGroup = 26
    group = 11
    integerValue = 45
    largeAnalogValue = 46
    lifeSafetyPoint = 21
    lifeSafetyZone = 22
    lift = 59
    lightingOutput = 54
    loadControl = 28
    loop = 12
    multiStateInput = 13
    multiStateOutput = 14
    multiStateValue = 19
    networkSecurity = 38
    networkPort = 56
    notificationClass = 15
    notificationForwarder = 51
    octetstringValue = 47
    positiveIntegerValue = 48
    program = 16
    pulseConverter = 24
    schedule = 17
    staging = 60
    structuredView = 29
    timePatternValue = 49
    timeValue = 50
    timer = 31
    trendLog = 20
    trendLogMultiple = 27


@bacpypes_debugging
class ObjectIdentifier(Atomic, tuple):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    object_type_class: type = ObjectType

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return True if arg is valid value for the class."""
        if _debug:
            ObjectIdentifier._debug("ObjectIdentifier.cast %r", arg)

        object_type_class = getattr(cls, "object_type_class")

        if isinstance(arg, tuple):
            if len(arg) != 2:
                raise ValueError("2-tuple expected")
            obj_type, obj_instance = arg

            if not isinstance(obj_type, object_type_class):
                obj_type = object_type_class(obj_type)

            if isinstance(obj_instance, str):
                obj_instance = int(obj_instance, base=0)
            elif isinstance(obj_instance, bool) or (not isinstance(obj_instance, int)):
                raise TypeError("invalid instance type")

            if (obj_instance < 0) or (obj_instance > 4194303):
                raise ValueError("instance out of range")

            arg = (obj_type, obj_instance)

        elif isinstance(arg, int):
            if arg < 0:
                raise ValueError("unsigned integer expected")

            obj_type, obj_instance = (arg >> 22), (arg & 0x3FFFFF)
            obj_type = object_type_class(obj_type)

            arg = (obj_type, obj_instance)

        elif isinstance(arg, str):
            if "," in arg:
                arg = arg.split(",")
            elif ":" in arg:
                arg = arg.split(":")
            if len(arg) != 2:
                raise ValueError("'type,instance' or 'type:instance' expected")
            obj_type, obj_instance = arg

            obj_type = object_type_class(obj_type)
            obj_instance = int(obj_instance, base=0)
            if (obj_instance < 0) or (obj_instance > 4194303):
                raise ValueError("instance out of range")

            arg = (obj_type, obj_instance)

        else:
            raise TypeError()

        return arg

    def __int__(self) -> int:
        """Return the object identifier as a integer."""
        return cast(int, (self[0] << 22) + self[1])

    def __str__(self) -> str:
        """Return a string of the form 'type,instance'."""
        try:
            obj_type, obj_instance = self
            return str(obj_type) + "," + str(obj_instance)
        except ValueError:
            return "(uninitialized)"

    def encode(self) -> TagList:
        """Encode an enumerated element as a tag list."""
        if _debug:
            ObjectIdentifier._debug("ObjectIdentifier.encode")

        # pack the value
        data = struct.pack(">L", int(self))
        if _debug:
            Unsigned._debug("    - data: %r", data)

        tag: Tag
        if self._context is None:
            tag = ApplicationTag(TagNumber.objectIdentifier, data)
        else:
            tag = ContextTag(self._context, data)
        if _debug:
            ObjectIdentifier._debug(f"    - tag: {tag}")

        return TagList([tag])

    @classmethod
    def decode(cls, tag_list: TagList) -> ObjectIdentifier:
        """Decode an enumerated element from a tag list."""
        if _debug:
            ObjectIdentifier._debug("ObjectIdentifier.decode %r", tag_list)

        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("object identifier application tag expected")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(
                    f"object identifier context tag {cls._context} expected"
                )
            if tag.tag_number != TagNumber.objectIdentifier:
                raise InvalidTag("object identifier application tag expected")
        elif tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("object identifier application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
        else:
            raise InvalidTag("unexpected opening/closing tag")
        if len(tag.tag_data) != 4:
            raise InvalidTag("invalid tag length")

        # get the data
        value = struct.unpack(">L", tag.tag_data)[0]
        if _debug:
            Time._debug("    - value: %r", value)

        # return an instance of this thing
        return cls(value)


Tag._app_tag_class = [
    Null,
    Boolean,
    Unsigned,
    Integer,
    Real,
    Double,
    OctetString,
    CharacterString,
    BitString,
    Enumerated,
    Date,
    Time,
    ObjectIdentifier,
    None,  # type: ignore[list-item]
    None,  # type: ignore[list-item]
    None,  # type: ignore[list-item]
]
