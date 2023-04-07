"""
Constructed Data
"""
# mypy: ignore-errors

from __future__ import annotations

import sys
import inspect

# import traceback
import copy
from functools import partial

from typing import (
    get_type_hints,
    Any as _Any,
    List as _List,
    Callable,
    TextIO,
    Tuple,
    Dict,
    Set,
    FrozenSet,
    Optional,
    Union,
    cast,
)


from .debugging import ModuleLogger, DebugContents, bacpypes_debugging
from .errors import InvalidTag, EncodingError, PropertyError
from .primitivedata import (
    Tag,
    TagClass,
    TagList,
    TagNumber,
    Atomic,
    ClosingTag,
    Element,
    ElementInterface,
    ElementMetaclass,
    OpeningTag,
    Null,
    Unsigned,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# type signatures for keeping track of what constructed types have already
# been created and for error checking (no list of arrays, for example)
_sequence_type_signatures: Dict[FrozenSet[Tuple[str, _Any]], type] = {}
_sequence_of_classes: Set[type] = set()

_array_type_signatures: Dict[FrozenSet[Tuple[str, _Any]], type] = {}
_array_of_classes: Set[type] = set()

_list_type_signatures: Dict[FrozenSet[Tuple[str, _Any]], type] = {}
_list_of_classes: Set[type] = set()


@bacpypes_debugging
class SequenceMetaclass(ElementMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _type_signatures: Dict[FrozenSet[Tuple[str, _Any]], type] = {}
    _structures: Set[type] = set()

    def __new__(
        cls: _Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, _Any],
    ) -> "SequenceMetaclass":
        if _debug:
            SequenceMetaclass._debug(
                "__new__ %r %r %r %r",
                cls,
                clsname,
                superclasses,
                attributedict,
            )

        # create the class
        metaclass = cast(
            SequenceMetaclass,
            super(SequenceMetaclass, cls).__new__(
                cls, clsname, superclasses, attributedict
            ),
        )
        if _debug:
            SequenceMetaclass._debug("    - metaclass: %r", metaclass)

        # start with an empty property function map and order
        _elements: Dict[str, type] = {}
        _inits: Dict[str, _Any] = {}
        _order: _List[str] = []
        _debug_contents: _List[str] = []

        # include the property function maps we've already built
        for supercls in reversed(superclasses):
            if hasattr(supercls, "_elements"):
                if _debug:
                    SequenceMetaclass._debug("    - supercls._elements: %r", supercls._elements)  # type: ignore[attr-defined]
                _elements.update(supercls._elements)  # type: ignore[attr-defined]
            if hasattr(supercls, "_inits"):
                if _debug:
                    SequenceMetaclass._debug("    - supercls._inits: %r", supercls._inits)  # type: ignore[attr-defined]
                _inits.update(supercls._inits)  # type: ignore[attr-defined]
            if hasattr(supercls, "_order"):
                if _debug:
                    SequenceMetaclass._debug("    - supercls._order: %r", supercls._order)  # type: ignore[attr-defined]
                for element in supercls._order:  # type: ignore[attr-defined]
                    if element not in _order:
                        _order.append(element)

        # add the ordered elements to the end
        if "_order" in attributedict:
            for element in attributedict["_order"]:
                if element not in _order:
                    _order.append(element)
        if _debug:
            SequenceMetaclass._debug("    - _order: %r", _order)

        # pick up the components defined by annotations
        for attr, attr_type in get_type_hints(metaclass).items():
            if attr.startswith("_"):
                continue
            if _debug:
                SequenceMetaclass._debug(f"    - attr, attr_type: {attr}, {attr_type}")
            if inspect.isclass(attr_type) and issubclass(attr_type, ElementInterface):
                _elements[attr] = attr_type
                _debug_contents.append(attr)
        if _debug:
            SequenceMetaclass._debug("    - _elements: %r", _elements)

        # look for initializers
        for attr, value in attributedict.items():
            if attr.startswith("_"):
                continue
            if attr in _elements:
                if isinstance(value, property):
                    if _debug:
                        SequenceMetaclass._debug(f"    - {attr} = value is a property")
                    continue

                attr_class = _elements[attr]
                if _debug:
                    SequenceMetaclass._debug(
                        f"    - attr = value: {attr}, {value} {attr_class}"
                    )

                if not isinstance(value, attr_class):
                    value = attr_class(value)
                    if _debug:
                        SequenceMetaclass._debug(f"        - cast value: {value}")

                _inits[attr] = value
            elif inspect.isclass(value) and issubclass(value, ElementInterface):
                if _debug:
                    SequenceMetaclass._debug(f"    - attr = class: {attr} = {value}")
                _elements[attr] = value
                _debug_contents.append(attr)
            elif isinstance(value, ElementInterface):
                if _debug:
                    SequenceMetaclass._debug(f"    - attr = value: {attr} = {value}")
                _elements[attr] = value.__class__
                _debug_contents.append(attr)
        if _debug:
            SequenceMetaclass._debug("    - _inits: %r", _inits)
            SequenceMetaclass._debug("    - _elements: %r", _elements)

        # if this is ordered, all of the elements must be in the list
        if _order:
            # find the elements that are not in _order
            bad_elements = set.difference(
                set(_elements),
                set(_order),
            )
            if bad_elements:
                raise AttributeError("element not ordered: " + ", ".join(bad_elements))

            # find the elements in _order that are not elements
            bad_elements = set.difference(
                set(_order),
                set(_elements),
            )
            if bad_elements:
                raise AttributeError(
                    "not an ordered element: " + ", ".join(bad_elements)
                )

        # add these special attributes to the class
        setattr(metaclass, "_elements", _elements)
        setattr(metaclass, "_inits", _inits)
        setattr(metaclass, "_order", _order)
        setattr(metaclass, "_debug_contents", tuple(_debug_contents))

        # save this class as a known structure
        SequenceMetaclass._structures.add(metaclass)

        return metaclass

    def __call__(cls, *args: _Any, **kwargs: _Any) -> Sequence:
        if _debug:
            SequenceMetaclass._debug("__call__(%s) %r %r", cls.__name__, args, kwargs)
        assert issubclass(cls, Sequence)

        # pull out the signature parameters
        signature_args = {}
        for kw in ElementMetaclass._signature_parameters:
            if kw in kwargs:
                signature_args[kw] = kwargs.pop(kw)

        if signature_args:
            sig = frozenset({"cls": cls, **signature_args}.items())
            if sig in SequenceMetaclass._type_signatures:
                new_type = SequenceMetaclass._type_signatures[sig]
            else:
                # new_type = type(cls.__name__ + "!", cls.__mro__, signature_args)
                new_type = type(cls.__name__, cls.__mro__, signature_args)

                # save the signature
                cast(Sequence, new_type)._signature = sig

                SequenceMetaclass._type_signatures[sig] = new_type
            if _debug:
                SequenceMetaclass._debug("    - new_type: %r", new_type)
        else:
            if _debug:
                SequenceMetaclass._debug("    - vanilla")
            new_type = cls

        # return an instance
        return cast(Sequence, type.__call__(new_type, *args, **kwargs))


@bacpypes_debugging
class Sequence(Element, DebugContents, metaclass=SequenceMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...]
    _elements: Dict[str, _Any]
    _inits: Dict[str, _Any]
    _order: Tuple[str, ...]

    def __init__(
        self, arg: Union["Sequence", Dict[str, _Any], None] = None, **kwargs: _Any
    ) -> None:
        if _debug:
            Sequence._debug(
                "(%s.%s).__init__ %r %r",
                self.__class__.__module__,
                self.__class__.__name__,
                arg,
                kwargs,
            )

        value: _Any
        elements = set(self._elements.keys())
        if _debug:
            Sequence._debug("    - elements: %r", elements)

        # merge the arg as a template, values overridden with the kwargs
        if isinstance(arg, dict):
            kwargs = {**arg, **kwargs}

        # find the kwargs that are not elements
        wrong_kwargs = set(kwargs).difference(elements)
        if wrong_kwargs:
            raise AttributeError(
                "not a sequence element: {}".format(", ".join(wrong_kwargs))
            )

        # build a map of initialization values
        init_map = {}
        for attr in elements:
            if attr in kwargs:
                init_map[attr] = kwargs[attr]
            elif isinstance(arg, Sequence) and hasattr(arg, attr):
                init_map[attr] = getattr(arg, attr)
            elif isinstance(arg, dict) and attr in arg:
                init_map[attr] = arg[attr]
            elif attr in self.__class__._inits:
                init_map[attr] = self.__class__._inits[attr]
        if _debug:
            Sequence._debug("    - init_map: %r", init_map)

        # make sure they are all the correct type
        for attr, value in init_map.items():
            if value is None:
                continue

            # remove it from the set that will be set to None below
            elements.remove(attr)

            element = self._elements[attr]
            if value.__class__ != element:
                if _debug:
                    Sequence._debug(
                        f"    - {attr} casting call: %r, element: %r", value, element
                    )
                value = element(element.cast(value))

            super().__setattr__(attr, value)

        # clear out the rest of the elements
        for attr in elements:
            try:
                # guard agaist elements defined as a property
                if isinstance(inspect.getattr_static(self, attr), property):
                    if _debug:
                        Sequence._debug(f"    - {attr} is a property")
                    continue
            except AttributeError:
                pass

            super().__setattr__(attr, None)
            if _debug:
                Sequence._debug(f"    - {attr} set to None")

    def __getattr__(self, attr: str) -> _Any:
        if attr.startswith("_") or (attr not in self._elements):
            return object.__getattribute__(self, attr)
        if _debug:
            Sequence._debug("__getattr__ %r", attr)

        element = self._elements[attr]
        getattr_fn = partial(super().__getattribute__, attr)

        value = element.get_attribute(getter=getattr_fn)

        return value

    def __setattr__(self, attr: str, value: _Any) -> None:
        if (attr not in self._elements) or (value is None):
            super().__setattr__(attr, value)
            return
        if _debug:
            Sequence._debug("__setattr__ %r %r", attr, value)

        element = self._elements[attr]

        if value.__class__ != element:
            if _debug:
                Sequence._debug(
                    f"    - {attr} casting call: %r != %r", value.__class__, element
                )
            value = element(element.cast(value))

        getattr_fn = partial(super().__getattribute__, attr)
        setattr_fn = partial(super().__setattr__, attr)

        element.set_attribute(
            getter=getattr_fn,
            setter=setattr_fn,
            value=value,
        )

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return a sequence object with values copied from arg."""
        if _debug:
            Sequence._debug("(%r).cast %r", cls.__name__, arg)
        assert issubclass(cls, Sequence)

        # start with an empty sequence with the correct signature
        sequence = cls()
        value: _Any

        # fill it in with attribute values from a dict
        if isinstance(arg, dict):
            for attr, value in arg.items():
                if value is None:
                    continue
                if _debug:
                    Sequence._debug("    - attr %r: %r", attr, value)

                setattr(sequence, attr, value)

        # fill it in with attribute values from a similar sequence
        elif isinstance(arg, Sequence):
            for attr in cls._elements:
                if hasattr(arg, attr):
                    value = getattr(arg, attr)
                    if value is None:
                        continue
                    if _debug:
                        Sequence._debug("    - attr %r: %r", attr, value)

                    setattr(sequence, attr, value)

        return sequence

    def encode(self) -> TagList:
        """Encode a sequence as a tag list."""
        if _debug:
            Sequence._debug("(%s).encode", self.__class__.__name__)
        if not self._order:
            raise RuntimeError("sequences must be ordered")

        tag_list = TagList()

        # maybe context tagged
        if self._context is not None:
            tag_list.append(OpeningTag(self._context))

        for attr in self._order:
            element = self._elements[attr]

            # ask the element to get the value
            getattr_fn = partial(super().__getattribute__, attr)
            value = element.get_attribute(getter=getattr_fn)
            if _debug:
                Sequence._debug(f"    - {attr}, {element}: {value}")

            # check for optional elements
            if value is None:
                if not element._optional:
                    raise AttributeError(
                        f"{attr} is a required element of {self.__class__.__name__}"
                    )
                continue

            # append the encoded element
            tag_list.extend(value.encode())

        # maybe context tagged
        if self._context is not None:
            tag_list.append(ClosingTag(self._context))

        return tag_list

    @classmethod
    def decode(cls, tag_list: TagList, class_: Optional[type] = None) -> Sequence:
        """Decode a sequence from a tag list."""
        if _debug:
            Sequence._debug("(%s).decode %r %r", cls.__name__, tag_list, class_)
            for i, tag in enumerate(tag_list):
                Sequence._debug("    [%d] %r", i, tag)

        # override the cls parameter when necessary
        if class_:
            cls = class_
        if not cls._order:
            raise RuntimeError("sequences must be ordered")

        # look ahead for elements
        tag: Optional[Tag] = tag_list.peek()
        if _debug:
            Sequence._debug("    - first tag: %r", tag)

        # if this is context encoded, check and consume the opening tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.opening):
                raise InvalidTag(f"opening tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()
            tag = tag_list.peek()
            if _debug:
                Sequence._debug("    - next tag: %r", tag)

        # result is an instance of a subclass of Sequence
        result = cls()

        # look for the elements in order
        for attr in cls._order:
            element = cls._elements[attr]
            if _debug:
                Sequence._debug(
                    "    - attr, element, tag: %r, %r, %r", attr, element, tag
                )

            value: _Any = None

            # no tag or closing tag is the end of the encoded elements in
            # this sequence so all of the rest of the elements must be optional
            if (not tag) or (tag.tag_class == TagClass.closing):
                if not element._optional:
                    raise AttributeError(
                        f"{attr} is a required element of {cls.__name__}"
                    )
                else:
                    continue

            # check for a choice of somethings
            if issubclass(element, Choice):
                value = element.decode(tag_list)
                tag = tag_list.peek()
                if _debug:
                    Sequence._debug("    - next tag: %r", tag)

            # check for a sequence of something else
            elif issubclass(element, ExtendedList):
                value = element.decode(tag_list)
                tag = tag_list.peek()
                if _debug:
                    Sequence._debug("    - next tag: %r", tag)

            # check for a specific context
            elif tag.tag_class == TagClass.context or tag.tag_class == TagClass.opening:
                if tag.tag_number == element._context:
                    value = element.decode(tag_list)
                    tag = tag_list.peek()
                    if _debug:
                        Sequence._debug("    - next tag: %r", tag)
                elif not element._optional:
                    raise AttributeError(
                        f"{attr} is a context tagged {element._context} required element of {cls.__name__}"
                    )
                else:
                    continue

            # application encoded atomic value
            elif issubclass(element, Atomic):
                if issubclass(element, Tag._app_tag_class[tag.tag_number]):
                    value = element.decode(tag_list)
                    tag = tag_list.peek()
                    if _debug:
                        Sequence._debug("    - next tag: %r", tag)
                elif not element._optional:
                    raise AttributeError(
                        f"{attr} is an application tagged required element of {cls.__name__}"
                    )
                else:
                    continue
            else:
                try:
                    if _debug:
                        Sequence._debug("    - generic decode: %r", element)
                    value = element.decode(tag_list)
                    tag = tag_list.peek()
                    if _debug:
                        Sequence._debug("    - next tag: %r", tag)
                except InvalidTag:
                    if not element._optional:
                        raise AttributeError(
                            f"{attr} is a required element of {cls.__name__}"
                        )
                    continue

            if _debug:
                Sequence._debug(f"    - {attr}, {element} := {value}")

            # ask the element to set the value
            getattr_fn = partial(result.__getattribute__, attr)
            setattr_fn = partial(result.__setattr__, attr)
            element.set_attribute(
                getter=getattr_fn,
                setter=setattr_fn,
                value=value,
            )

        # if this is context encoded, check and consume the closing tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.closing):
                raise InvalidTag(f"closing tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()

        # return the sequence
        return result

    def __eq__(self, other: _Any) -> bool:
        """Compare two sequences for equality."""
        if _debug:
            Sequence._debug("Sequence.__eq__ %r", other)

        if isinstance(other, self.__class__):
            pass
        elif isinstance(self, other.__class__):
            pass
        else:
            if _debug:
                Sequence._debug("    - not instances of the same class")
            return False

        # check the elements
        for attr in self._elements:
            if _debug:
                Sequence._debug("    - attr: %r", attr)

            self_value = self.__getattribute__(attr)
            other_value = other.__getattribute__(attr)
            if self_value != other_value:
                if _debug:
                    Sequence._debug("    - %r != %r", self_value, other_value)
                return False

        return True

    def __ne__(self, other: _Any) -> bool:
        return not self.__eq__(other)


@bacpypes_debugging
class Choice(Sequence):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _choice: Optional[str] = None

    def __init__(
        self, arg: Union["Choice", Dict[str, _Any], None] = None, **kwargs: _Any
    ) -> None:
        if _debug:
            Choice._debug("(%s).__init__ %r %r", self.__class__.__name__, arg, kwargs)

        # assume no choice
        choice = None

        # pick the choice from arg
        if isinstance(arg, dict):
            kw_list = list(arg)
            if len(kw_list) > 1:
                raise RuntimeError("initialize one choice: " + ", ".join(kw_list))
            choice = kw_list[0]
        elif isinstance(arg, Choice):
            choice = arg._choice
        elif arg is not None:
            raise TypeError("dict or Choice expected")

        # pick the choice from the kwargs
        if kwargs:
            kw_list = list(kwargs)
            if len(kw_list) > 1:
                raise RuntimeError("initialize one choice: " + ", ".join(kw_list))
            choice = kw_list[0]

        # make sure it's one of ours
        if choice and choice not in self._elements:
            raise AttributeError(f"choice is not an element: {choice}")

        # proceed with initialization
        super().__init__(arg, **kwargs)

        # set the current choice
        super().__setattr__("_choice", choice)

    def __setattr__(self, attr: str, value: _Any) -> None:
        if _debug:
            Choice._debug(
                "(%s).__setattr__ %r %r", self.__class__.__name__, attr, value
            )
        if attr not in self._elements:
            super().__setattr__(attr, value)
            return

        if self._choice:
            if attr == self._choice:
                if value is None:
                    if _debug:
                        Choice._debug("    - eliminate choice")
                    super().__setattr__(attr, value)
                    self._choice = None
                    return
            else:
                if _debug:
                    Choice._debug("    - reset current choice")
                super().__setattr__(self._choice, None)
                self._choice = None
        elif value is None:
            if _debug:
                Choice._debug("    - useless")
            return

        element = self._elements[attr]

        # make sure the value is the correct type
        if value.__class__ != element:
            if _debug:
                Sequence._debug(f"    - {attr} casting call: %r", value)
            value = element(element.cast(value))

        getattr_fn = partial(super().__getattribute__, attr)
        setattr_fn = partial(super().__setattr__, attr)

        element.set_attribute(
            getter=getattr_fn,
            setter=setattr_fn,
            value=value,
        )

        # new choice
        self._choice = attr

    def encode(self) -> TagList:
        """Encode a choice as a tag list."""
        if _debug:
            Choice._debug("(%s).encode", self.__class__.__name__)

        tag_list = TagList()

        if not self._choice:
            raise AttributeError("no choice")

        # maybe context tagged
        if self._context is not None:
            tag_list.append(OpeningTag(self._context))

        attr = self._choice
        element = self._elements[attr]

        # ask the element to get the value
        getattr_fn = partial(super().__getattribute__, attr)
        value = element.get_attribute(getter=getattr_fn)
        if _debug:
            Choice._debug(f"    - {attr}, {element}: {value}")

        # append the encoded element
        tag_list.extend(value.encode())

        # maybe context tagged
        if self._context is not None:
            tag_list.append(ClosingTag(self._context))

        return tag_list

    @classmethod
    def decode(cls, tag_list: TagList) -> Choice:
        """Decode a choice from a tag list."""
        if _debug:
            Choice._debug("(%s).decode %r", cls.__name__, tag_list)

        # look ahead for elements
        tag: Optional[Tag] = tag_list.peek()
        if _debug:
            Choice._debug("    - first tag: %r", tag)

        # if this is context encoded, check and consume the opening tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.opening):
                raise InvalidTag(f"opening tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()
            tag = tag_list.peek()
            if _debug:
                Choice._debug("    - next tag: %r", tag)

        # result is an instance of a Choice
        result = cls()

        # look for a matching element
        for attr, element in cls._elements.items():
            if _debug:
                Choice._debug("    - attr, element: %r, %r", attr, element)

            value: _Any = None

            # no tag or closing tag is the end of the encoded elements in
            # this sequence so there is no match
            if (not tag) or (tag.tag_class == TagClass.closing):
                raise AttributeError(f"{cls.__name__} choice not found")

            # check for a specific context
            if tag.tag_class == TagClass.context or tag.tag_class == TagClass.opening:
                if tag.tag_number == element._context:
                    value = element.decode(tag_list)
                    tag = tag_list.peek()
                    if _debug:
                        Choice._debug("    - next tag: %r", tag)
                else:
                    continue

            # application encoded atomic value
            elif issubclass(element, Atomic):
                if issubclass(element, Tag._app_tag_class[tag.tag_number]):
                    value = element.decode(tag_list)
                    tag = tag_list.peek()
                    if _debug:
                        Choice._debug("    - next tag: %r", tag)
                else:
                    continue
            else:
                try:
                    # make a copy of the tag list
                    tag_list_copy = TagList(tag_list)

                    # decode that which can be decoded
                    value = element.decode(tag_list_copy)

                    # delete from this list the tags that were consumed
                    del tag_list.tagList[
                        : len(tag_list.tagList) - len(tag_list_copy.tagList)
                    ]
                except (AttributeError, InvalidTag):
                    continue

            if _debug:
                Choice._debug(f"    - {attr}, {element}: {value}")

            # ask the element to set the value
            getattr_fn = partial(result.__getattribute__, attr)
            setattr_fn = partial(result.__setattr__, attr)
            element.set_attribute(
                getter=getattr_fn,
                setter=setattr_fn,
                value=value,
            )

            # found the choice, stop looking
            break
        else:
            raise AttributeError("choice not found")

        # if this is context encoded, check and consume the closing tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.closing):
                raise InvalidTag(f"closing tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()

        # return the sequence
        return result


@bacpypes_debugging
class ExtendedListMetaclass(type):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __call__(cls, *args: _Any, **kwargs: _Any) -> _Any:
        if _debug:
            ExtendedListMetaclass._debug("__call__ %r %r %r", cls, args, kwargs)
        assert issubclass(cls, ExtendedList)

        # for filename, lineno, fn, _ in traceback.extract_stack()[:-1]:
        #     ExtendedListMetaclass._debug(
        #         "    %-20s  %s:%s", fn, filename.split("/")[-1], lineno
        #     )

        # normally no subtyping weirdness
        new_type = cast(ExtendedList, cls)

        # if there are kwargs the signature is changing
        if 0:  #### kwargs:
            # pull out the signature parameters
            signature_args = {}
            for kw in ElementMetaclass._signature_parameters:
                if kw in kwargs:
                    signature_args[kw] = kwargs.pop(kw)
                else:
                    kw_value = getattr(cls, kw, None)
                    if kw_value is not None:
                        signature_args[kw] = kw_value
            if kwargs:
                if _debug:
                    ExtendedListMetaclass._debug(
                        "    - non-signature kwargs: %r", kwargs
                    )

            signature = frozenset({"cls": new_type._subtype, **signature_args}.items())
            if _debug:
                ExtendedListMetaclass._debug("    - signature: %r", signature)

            new_type = cast(
                ExtendedList,
                type(cls.__name__, cls.__mro__, signature_args),
            )
            if _debug:
                ExtendedListMetaclass._debug("    - new_type: %r", new_type)
                ExtendedListMetaclass._debug("    - __mro__: %r", new_type.__mro__)

            # save the signature
            new_type._signature = signature

        # make sure the initial values are the correct type
        if args:
            ding = False
            new_list = []
            for i, item in enumerate(args[0]):
                # make sure the item is the correct type
                if item.__class__ != cls._subtype:  # type: ignore[attr-defined]
                    if _debug:
                        ExtendedListMetaclass._debug(
                            f"    - [{i}] casting call: {item!r}"
                        )

                    item = cls._subtype(cls._subtype.cast(item))  # type: ignore[attr-defined]
                    ding = True
                new_list.append(item)
            if ding:
                args = (new_list,)

        # create a new instance of the extended list
        new_obj = type.__call__(cast(type, new_type), *args, **kwargs)
        if _debug:
            ExtendedListMetaclass._debug("    - new_obj: %r, %r", new_obj, args)

        # hideousness with lists
        list.__init__(new_obj, *args)

        return new_obj


@bacpypes_debugging
class ExtendedList(list, ElementInterface, metaclass=ExtendedListMetaclass):  # type: ignore[type-arg]
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _subtype: type

    def __init__(self, *args: _Any, **kwargs: _Any) -> None:
        if _debug:
            ExtendedList._debug(
                "(%s).__init__ %r %r", self.__class__.__name__, args, kwargs
            )

    def append(self, item: _Any) -> None:
        if _debug:
            ExtendedList._debug("(%r).append %r", item)
        cls = self._subtype

        if issubclass(cls, Atomic) and (not isinstance(item, cls)):
            if _debug:
                ExtendedList._debug(f"    - casting call: {item!r}")
            item = cls(cls.cast(item))
        elif not isinstance(item, cls):
            raise TypeError(f"{cls} expected")

        super().append(item)

    def __getitem__(self, item: Union[int, slice]) -> _Any:
        if _debug:
            ExtendedList._debug("(%s).__getitem__ %r", self.__class__.__name__, item)

        rslt = super().__getitem__(item)
        if isinstance(item, slice):
            if _debug:
                ExtendedList._debug(f"    - rebuild: {rslt!r}")
            for i, v in enumerate(rslt):
                if _debug:
                    ExtendedList._debug(f"        [{i}]: {v} {type(v)}")
            rslt = self.__class__(rslt)
        if _debug:
            ExtendedList._debug("    - rslt: %r", rslt)

        return rslt

    def __setitem__(self, item: Union[int, slice], value: _Any) -> None:
        if _debug:
            ExtendedList._debug("(%s).__setitem__ %r %r", self.__class__, item, value)
        cls = self._subtype

        if isinstance(item, slice):
            if issubclass(cls, Atomic):
                ding = False
                new_list = []
                for i, list_item in enumerate(value):
                    if list_item.__class__ != cls:
                        if _debug:
                            ExtendedList._debug(
                                f"    - [{i}] casting call: {list_item!r}"
                            )
                        list_item = cls(cls.cast(list_item))
                        ding = True
                    new_list.append(list_item)
                if ding:
                    value = new_list
            else:
                for i, list_item in enumerate(value):
                    if not isinstance(list_item, cls):
                        raise TypeError(f"item {i}: {cls} expected")
        elif issubclass(cls, Atomic) and (not isinstance(value, cls)):
            if _debug:
                ExtendedList._debug(f"    - casting call: {value!r}")
            value = cls(cls.cast(value))
        elif not isinstance(value, cls):
            raise TypeError(f"{cls} expected")

        return super().__setitem__(item, value)

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return a sequence object with values copied from arg."""
        if _debug:
            ExtendedList._debug("(%s).cast %r", cls.__name__, arg)
        assert issubclass(cls, ExtendedList)

        new_list = []
        for i, item in enumerate(arg):
            # make sure the item is the correct type
            if item.__class__ != cls._subtype:
                if _debug:
                    ExtendedListMetaclass._debug(f"    - [{i}] casting call: {item!r}")
                item = cls._subtype(cls._subtype.cast(item))  # type: ignore[attr-defined]
            new_list.append(item)
        if _debug:
            ExtendedList._debug("    - new_list: %r", new_list)

        return new_list

    def encode(self) -> TagList:
        """Encode an extended list as a tag list."""
        if _debug:
            ExtendedList._debug("(%s).encode", self.__class__.__name__)

        tag_list = TagList()

        # maybe context tagged
        if self._context is not None:
            tag_list.append(OpeningTag(self._context))

        # loop through the items
        for item in self:
            # append the encoded element
            tag_list.extend(item.encode())

        # maybe context tagged
        if self._context is not None:
            tag_list.append(ClosingTag(self._context))

        return tag_list

    @classmethod
    def decode(cls, tag_list: TagList) -> ExtendedList:
        """Decode a choice from a tag list."""
        if _debug:
            ExtendedList._debug("(%s).decode %r", cls.__name__, tag_list)

        # look ahead for elements
        tag: Optional[Tag] = tag_list.peek()
        if _debug:
            ExtendedList._debug("    - first tag: %r", tag)

        # if this is context encoded, check and consume the opening tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.opening):
                raise InvalidTag(f"opening tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()
            tag = tag_list.peek()
            if _debug:
                ExtendedList._debug("    - next tag: %r", tag)

        # result is an instance of an extended list
        list_elements = []

        # look for a matching element
        while tag:
            value: _Any = None

            # a closing tag is the end of the encoded elements in
            # this extended list
            if tag.tag_class == TagClass.closing:
                break

            try:
                # make a copy of the tag list
                tag_list_copy = TagList(tag_list)

                # decode that which can be decoded
                value = cls._subtype.decode(tag_list_copy)  # type: ignore[attr-defined]

                # delete from this list the tags that were consumed
                del tag_list.tagList[
                    : len(tag_list.tagList) - len(tag_list_copy.tagList)
                ]
            except (AttributeError, InvalidTag):
                break

            # append the value, peek at the next tag
            list_elements.append(value)
            tag = tag_list.peek()

        # if this is context encoded, check and consume the closing tag
        if cls._context is not None:
            if (not tag) or (tag.tag_class != TagClass.closing):
                raise InvalidTag(f"closing tag {cls._context} expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()

        # return the extended list, initialized with the list elements
        return cls(list_elements)


def SequenceOf(cls: type, **kwargs: _Any) -> type:
    """
    Amazing documentation here.
    """

    global _sequence_of_classes, _array_of_classes

    # called with a class, not an instance (prototype)
    if not inspect.isclass(cls):
        raise TypeError(f"class expected, got instance: {cls}")

    # no SequenceOf(SequenceOf(...)) allowed
    if cls in _sequence_of_classes:
        raise TypeError("nested sequences disallowed")
    # no SequenceOf(ArrayOf(...)) allowed
    if cls in _array_of_classes:
        raise TypeError("sequences of arrays disallowed")

    # pull out the signature parameters
    signature_args = {}
    for kw in ElementMetaclass._signature_parameters:
        if kw in kwargs:
            signature_args[kw] = kwargs.pop(kw)

    # check for unknown kwargs
    if kwargs:
        raise TypeError(
            "SequenceOf() got an unexpected keyword argument: "
            + ", ".join(repr(k) for k in kwargs)
        )

    # build a signature, maybe this is a repeat
    signature = frozenset({"cls": cls, **signature_args}.items())
    if signature in _sequence_type_signatures:
        return _sequence_type_signatures[signature]

    # build the class
    new_class = type(
        "SequenceOf" + cls.__name__,
        (ExtendedList,),
        {"_signature": signature, "_subtype": cls, **signature_args},
    )

    # cache this type
    _sequence_type_signatures[signature] = new_class
    _sequence_of_classes.add(new_class)

    # return this new type
    return new_class


@bacpypes_debugging
class List(ExtendedList):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __init__(self, *args: _Any, **kwargs: _Any) -> None:
        if _debug:
            List._debug("__init__ %r %r", args, kwargs)
        super().__init__(*args, **kwargs)


def ListOf(cls: type, **kwargs: _Any) -> type:
    """
    Function to return a class that can encode and decode a list of
    some other type.
    """
    global _sequence_of_classes, _array_of_classes

    # called with a class, not an instance (prototype)
    if not inspect.isclass(cls):
        raise TypeError(f"class expected, got instance: {cls}")

    # no ListOf(SequenceOf(...)) allowed
    if cls in _sequence_of_classes:
        raise TypeError("nested sequences disallowed")
    # no ListOf(ListOf(...)) allowed
    if cls in _list_of_classes:
        raise TypeError("sequences of arrays disallowed")
    # no ListOf(ArrayOf(...)) allowed
    if cls in _array_of_classes:
        raise TypeError("sequences of arrays disallowed")

    # pull out the signature parameters
    signature_args = {}
    for kw in ElementMetaclass._signature_parameters:
        if kw in kwargs:
            signature_args[kw] = kwargs.pop(kw)

    # check for unknown kwargs
    if kwargs:
        raise TypeError(
            "ListOf() got an unexpected keyword argument: "
            + ", ".join(repr(k) for k in kwargs)
        )

    # build a signature, maybe this is a repeat
    signature = frozenset({"cls": cls, **signature_args}.items())
    if signature in _list_type_signatures:
        return _list_type_signatures[signature]

    # build the class
    new_class = type(
        "ListOf" + cls.__name__,
        (
            List,
            ExtendedList,
        ),
        {"_signature": signature, "_subtype": cls, **signature_args},
    )

    # cache this type
    _list_type_signatures[signature] = new_class
    _list_of_classes.add(new_class)

    # return this new type
    return new_class


@bacpypes_debugging
class ArrayMetaclass(ExtendedListMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __call__(cls, *args: _Any, **kwargs: _Any) -> _Any:
        if _debug:
            ArrayMetaclass._debug("__call__ %r %r %r", cls, args, kwargs)
        assert issubclass(cls, Array)

        # normally no subtyping weirdness
        new_type = cast(Array, cls)

        # pull out the signature parameters
        signature_args = {}
        for kw in ElementMetaclass._signature_parameters:
            if kw in kwargs:
                signature_args[kw] = kwargs.pop(kw)

        # check if the signature is changing
        if signature_args:
            signature = frozenset({"cls": new_type._subtype, **signature_args}.items())
            if _debug:
                ArrayMetaclass._debug("    - signature: %r", signature)

            new_type = cast(
                Array,
                # type(cls.__name__ + "!", cls.__mro__, signature_args)
                type(cls.__name__, cls.__mro__, signature_args),
            )
            if _debug:
                ArrayMetaclass._debug("    - new_type: %r", new_type)

            # save the signature
            new_type._signature = signature

        if _debug:
            ArrayMetaclass._debug("    - _init: %r", new_type._init)
            ArrayMetaclass._debug("    - _length: %r", new_type._length)

        # make sure the initial values are the correct type
        if args:
            if (new_type._length is not None) and (len(args[0]) != new_type._length):
                raise ValueError("invalid list length")

            if issubclass(new_type._subtype, Atomic):
                ding = False
                new_list = []
                for i, item in enumerate(args[0]):
                    if not isinstance(item, new_type._subtype):
                        if _debug:
                            ArrayMetaclass._debug(f"    - [{i}] casting call: {item!r}")
                        item = new_type._subtype(new_type._subtype.cast(item))
                        ding = True
                    new_list.append(item)
                if ding:
                    args = (new_list,)
            else:
                for i, item in enumerate(args[0]):
                    if not isinstance(item, new_type._subtype):
                        raise TypeError(f"item {i}: {new_type._subtype} expected")
        elif new_type._length is not None:
            if new_type._init is None:
                new_list = list(new_type._subtype() for i in range(new_type._length))
            else:
                new_list = list(
                    copy.deepcopy(new_type._init) for i in range(new_type._length)
                )
            args = (new_list,)

        # continue
        return super().__call__(*args, **kwargs)


@bacpypes_debugging
class Array(ExtendedList, metaclass=ArrayMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _init: Optional[_Any] = None
    _length: Optional[int] = None

    def __init__(self, *args: _Any, **kwargs: _Any) -> None:
        if _debug:
            Array._debug("__init__ %r %r", args, kwargs)
        super().__init__(*args, **kwargs)

    def append(self, item: _Any) -> None:
        if _debug:
            Array._debug("append %r", item)
        if self._length is not None:
            raise RuntimeError("fixed length array")

        cls = self._subtype

        if issubclass(cls, Atomic) and (not isinstance(item, cls)):
            if _debug:
                Array._debug(f"    - casting call: {item!r}")
            item = cls(cls.cast(item))
        elif not isinstance(item, cls):
            raise TypeError(f"{cls} expected")

        super().append(item)

    def __getitem__(self, item: Union[int, slice]) -> _Any:
        if _debug:
            Array._debug("__getitem__ %r", item)

        rslt = super().__getitem__(item)
        if isinstance(item, slice):
            rslt = self.__class__(rslt)

        return rslt

    def __setitem__(self, item: Union[int, slice], value: _Any) -> None:
        if _debug:
            Array._debug("__setitem__ %r %r", item, value)
        cls = self._subtype

        if isinstance(item, slice):
            if issubclass(cls, Atomic):
                ding = False
                new_list = []
                for i, list_item in enumerate(value):
                    if not isinstance(list_item, cls):
                        list_item = cls(cls.cast(list_item))
                        ding = True
                    new_list.append(list_item)
                if ding:
                    value = new_list
            else:
                for i, list_item in enumerate(value):
                    if not isinstance(list_item, cls):
                        raise TypeError(f"item {i}: {cls} expected")
        elif issubclass(cls, Atomic) and (not isinstance(value, cls)):
            if _debug:
                Array._debug(f"    - casting call: {value!r}")
            value = cls(cls.cast(value))
        elif not isinstance(value, cls):
            raise TypeError(f"{cls} expected")

        # pass along as usual
        super().__setitem__(item, value)

        # make sure the fixed length hasn't been violated
        if (self._length is not None) and (len(self) != self._length):
            raise ValueError("invalid list length")

    def __delitem__(self, item: _Any) -> None:
        if _debug:
            Array._debug("__delitem__ %r", item)
        if self._length is not None:
            raise RuntimeError("fixed length array")

        return super().__delitem__(item)

    @classmethod
    async def read_property(
        cls, getter: Callable[[], _Any], index: Optional[int] = None
    ) -> _Any:
        if _debug:
            Array._debug("read_property %r %r %r", cls, getter, index)
        if not getter:
            raise PropertyError("readAccessDenied")

        # get the value, wait for it if necessary
        value: _Any = getter()
        if _debug:
            Array._debug("    - value: %r", value)
        if inspect.isawaitable(value):
            if _debug:
                Array._debug("    - awaitable")
            value = await value

        # check the index
        if index is not None:
            if (index < 0) or (index > len(value)):
                raise PropertyError("invalidArrayIndex")
            if index == 0:
                value = Unsigned(len(value))
            else:
                value = value[index - 1]

        return value

    @classmethod
    async def write_property(
        cls,
        getter: Callable[[], _Any],
        setter: Callable[[_Any], _Any],
        value: _Any,
        index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        if _debug:
            Array._debug(
                "write_property %r %r %r %r %r %r",
                cls,
                getter,
                setter,
                value,
                index,
                priority,
            )
        if priority is not None:
            raise RuntimeError("property has no priority")
        if not setter:
            raise PropertyError("writeAccessDenied")

        # check the index
        if index is not None:
            if not getter:
                raise RuntimeError("array updated denied")

            # get the current value, wait for it if necessary
            current_value: _Any = getter()
            if _debug:
                Array._debug("    - current_value: %r", current_value)
            if inspect.isawaitable(current_value):
                if _debug:
                    Array._debug("    - awaitable")
                current_value = await current_value

            # check for resize
            if index == 0:
                if cls._length is not None:
                    raise PropertyError("writeAccessDenied")
                if value == cls._length:
                    if _debug:
                        Array._debug("    - no change")
                    pass
                elif value < len(current_value):
                    if _debug:
                        Array._debug("    - trim")
                    del current_value[value:]
                else:
                    if _debug:
                        Array._debug("    - extend, prototype: %r", cls._prototype)
                    if cls._prototype is None:
                        raise PropertyError("writeAccessDenied")
                    for _ in range(value - len(current_value)):
                        current_value.append(copy.deepcopy(cls._prototype))
            else:
                if (index < 0) or (index > len(current_value)):
                    raise PropertyError("invalidArrayIndex")
                current_value[index - 1] = value

            # the value to be written is current value
            value = current_value
        if _debug:
            Array._debug("    - new value: %r", value)

        # set the value, wait for it if necessary
        fn_result = setter(value)
        if _debug:
            Array._debug("    - fn_result: %r", fn_result)
        if inspect.isawaitable(fn_result):
            if _debug:
                Array._debug("    - awaitable")
            await fn_result


@bacpypes_debugging
def ArrayOf(cls: type, **kwargs: _Any) -> type:
    """
    Amazing documentation here.
    """
    if _debug:
        ArrayOf._debug("ArrayOf %r %r", cls, kwargs)

    global _sequence_of_classes, _array_of_classes

    # called with a class or an instance prototype
    kw_args = {}
    if not inspect.isclass(cls):
        kw_args["_init"] = cls
        cls = cls.__class__

    # no ArrayOf(ArrayOf(...)) allowed
    if cls in _array_of_classes:
        raise TypeError("arrays of arrays disallowed")

    # pull out the signature parameters
    signature_args = {}
    for kw in ElementMetaclass._signature_parameters:
        if kw in kwargs:
            signature_args[kw] = kwargs.pop(kw)
    if _debug:
        ArrayOf._debug("    - signature_args: %r", signature_args)

    # prototype is not hashable, pull it if it's there and it will get put
    # back in the attribute dictionary when the class is built
    prototype = kwargs.pop("_prototype", None)

    # check for unknown kwargs
    if kwargs:
        raise TypeError(
            "ArrayOf() got an unexpected keyword argument: "
            + ", ".join(repr(k) for k in kwargs)
        )

    # build a signature, maybe this is a repeat
    signature = frozenset({"cls": cls, **signature_args}.items())
    if signature in _array_type_signatures:
        if _debug:
            ArrayOf._debug("    - cache hit")
        return _array_type_signatures[signature]

    # build the class
    new_class = type(
        "ArrayOf" + cls.__name__,
        (
            Array,
            ExtendedList,
        ),
        {
            "_signature": signature,
            "_subtype": cls,
            "_prototype": prototype,
            **signature_args,
        },
    )
    if _debug:
        ArrayOf._debug("    - new_class: %r", new_class)

    # cache this type
    _array_type_signatures[signature] = new_class
    _array_of_classes.add(new_class)

    # return this new type
    return new_class


@bacpypes_debugging
class Any(Element):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    tagList: Optional[TagList]

    def __init__(
        self,
        arg: Optional[TagList] = None,
        _optional: Optional[bool] = None,
        _context: Optional[int] = None,
    ) -> None:
        if _debug:
            Any._debug("__init__ %r", arg)
        if arg is None:
            self.tagList = None
        elif isinstance(arg, TagList):
            self.tagList = arg
        elif isinstance(arg, Any):
            self.tagList = arg.tagList
        else:
            raise TypeError()

        super().__init__()

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return a valid value for the class."""
        if _debug:
            Any._debug("cast %r", arg)
        # accept None as no content
        if arg is None:
            return None

        # tag list is fine the way it is
        if isinstance(arg, TagList):
            return arg

        # start with a fresh tag list
        tag_list = TagList()

        # maybe context tagged
        if cls._context is not None:
            tag_list.append(OpeningTag(cls._context))

        # append the encoded element
        tag_list.extend(arg.encode())

        # maybe context tagged
        if cls._context is not None:
            tag_list.append(ClosingTag(cls._context))

        # tag list is in the element
        return tag_list

    def encode(self) -> TagList:
        """Encode an any element as a tag list."""
        if _debug:
            Any._debug("encode")

        if self.tagList is None:
            raise EncodingError("Any has no content")

        # contents are already encoded
        return self.tagList

    @classmethod
    def decode(cls, tag_list: TagList) -> "_Any":
        """Decode an element from a tag list."""
        if _debug:
            Any._debug("decode %r", tag_list)

        # look ahead for application tagged value
        tag: Optional[Tag] = tag_list.peek()
        if _debug:
            Any._debug("    - first tag: %r", tag)
        if not tag:
            raise InvalidTag("empty tag list")
        if tag.tag_class == TagClass.application:
            if cls._context is not None:
                raise InvalidTag(f"context tag {cls._context} expected")
            return cls([tag_list.pop()])

        if tag.tag_class == TagClass.context:
            if cls._context is None:
                raise InvalidTag("application tag expected")
            if tag.tag_number != cls._context:
                raise InvalidTag("mismatched context")
            return cls([tag_list.pop()])

        # don't step on someone elses closing tag
        if tag.tag_class == TagClass.closing:
            raise InvalidTag("tag expected")

        # this is an opening tag, cls must have a matching context
        if cls._context is None:
            raise InvalidTag("opening tag {tag.tag_number} but no context")
        if tag.tag_number != cls._context:
            raise InvalidTag("mismatched context")

        # look for the matching closing tag
        i = 1
        lvl = 0
        while i < len(tag_list.tagList):
            tag = tag_list.tagList[i]
            if tag.tag_class == TagClass.opening:
                lvl += 1
            elif tag.tag_class == TagClass.closing:
                if lvl == 0:
                    if tag.tag_number != cls._context:
                        raise InvalidTag("mismatched context")
                    break
                lvl -= 1
            i += 1

        # make sure we have a matched pair
        if lvl != 0:
            raise InvalidTag("mismatched open/close tags")

        # result is the list of tags
        value = TagList(tag_list.tagList[: i + 1])
        del tag_list.tagList[: i + 1]

        return cls(value)

    def cast_in(self, element: Element) -> None:
        """..."""
        if _debug:
            Any._debug("cast_in %r", element)

        # start with a fresh tag list
        tag_list = TagList()

        # maybe context tagged
        if self._context is not None:
            tag_list.append(OpeningTag(self._context))

        # append the encoded element
        tag_list.extend(element.encode())

        # maybe context tagged
        if self._context is not None:
            tag_list.append(ClosingTag(self._context))

        # save the result
        self.tagList = tag_list

    def cast_out(self, cls: type, null: bool = False) -> _Any:
        """
        Given the tag list, decode the contents as an object of type `cls`.
        Null is acceptable when decoding the property value of a Write Property
        Request and the priority has been provided.
        """
        if _debug:
            Any._debug("cast_out %r null=%r", cls.__name__, null)

        # make a copy of the tag list so this is non-destructive
        tag_list = TagList(self.tagList[:])

        # look ahead for elements
        tag: Optional[Tag] = tag_list.peek()
        if _debug:
            Any._debug("    - first tag: %r", tag)

        # if this is context encoded, check and consume the opening tag
        if self._context is not None:
            if (not tag) or (tag.tag_class != TagClass.opening):
                raise InvalidTag(f"opening tag {self._context} expected")
            if tag.tag_number != self._context:
                raise InvalidTag("mismatched context")
            tag_list.pop()
            tag = tag_list.peek()
            if _debug:
                Any._debug("    - next tag: %r", tag)

        # maybe null is acceptable otherwise the class provides the decoder
        if (
            null
            and (tag.tag_class == TagClass.application)
            and (tag.tag_number == TagNumber.null)
        ):
            if _debug:
                Any._debug("    - got a null")
            result = Null.decode(tag_list)
        else:
            if _debug:
                Any._debug("    - no null")
            result = cls.decode(tag_list)

        # look ahead for the closing tag
        if self._context is not None:
            tag = tag_list.peek()
            if (not tag) or (tag.tag_class != TagClass.closing):
                raise InvalidTag(f"closing tag {self._context} expected")
            if tag.tag_class != TagClass.closing:
                raise InvalidTag(f"closing tag {self._context} expected")
            if tag.tag_number != self._context:
                raise InvalidTag("mismatched context")

        # return the sequence
        return result

    def get_value_type(self) -> type:
        """Return the datatype encoded in the Any iff possible."""
        raise TypeError("unable to determine encoded type")

    def __eq__(self, other: _Any) -> bool:
        """Compare two Any for equality."""
        if _debug:
            Any._debug("__eq__ %r", other)

        if isinstance(other, self.__class__):
            pass
        elif isinstance(self, other.__class__):
            pass
        else:
            if _debug:
                Any._debug(
                    f"    - not instances of the same class: {self.__class__} {other.__class__}"
                )
            return False

        # check the tag lists
        return self.tagList == other.tagList

    def __ne__(self, other: _Any) -> bool:
        return not self.__eq__(other)

    def debug_contents(
        self,
        indent: int = 1,
        file: TextIO = sys.stderr,
        _ids: Optional[_List[_Any]] = None,
    ) -> None:
        if self.tagList is None:
            file.write("%stagList = None")
        else:
            file.write("%stagList = [\n" % ("    " * indent,))
            indent += 1
            elem: Tag
            for i, elem in enumerate(self.tagList):
                file.write("%s[%d] %r\n" % ("    " * indent, i, elem))
            indent -= 1
            file.write("%s    ]\n" % ("    " * indent,))


class SequenceOfAny(SequenceOf(Any)):
    pass


@bacpypes_debugging
class AnyAtomic(Any):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    tagList: Optional[TagList]

    def __init__(
        self,
        arg: Optional[TagList] = None,
        _optional: Optional[bool] = None,
        _context: Optional[int] = None,
    ) -> None:
        if _debug:
            AnyAtomic._debug("__init__ %r", arg)

        if isinstance(arg, TagList):
            super().__init__(arg)
        elif isinstance(arg, Atomic):
            super().__init__()
            super().cast_in(arg)
        else:
            raise TypeError("atomic element expected")

    @classmethod
    def cast(cls: type, arg: _Any) -> _Any:
        """Return a valid value for the class."""
        if _debug:
            AnyAtomic._debug("cast %r %r", cls, arg)

        # tag list is fine the way it is
        if isinstance(arg, TagList):
            return arg

        # make sure it is atomic
        if not isinstance(arg, Atomic):
            raise TypeError("atomic element expected")

        # let the argument encode itself
        tag_list = arg.encode()

        return tag_list

    def encode(self) -> TagList:
        """Encode an any element as a tag list."""
        if _debug:
            AnyAtomic._debug("encode")

        if self.tagList is None:
            raise EncodingError("AnyAtomic has no content")

        # contents are already encoded
        return self.tagList

    @classmethod
    def decode(cls, tag_list: TagList) -> _Any:
        """Decode an element from a tag list."""
        if _debug:
            AnyAtomic._debug("decode %r", tag_list)

        # there should only be one thing here
        tag: Optional[Tag] = tag_list.pop()
        if not tag:
            raise InvalidTag("empty tag list")
        if tag.tag_class != TagClass.application:
            raise InvalidTag("application tag expected")
        if _debug:
            AnyAtomic._debug("    - tag: %r", tag)

        # this is the tag we are looking for
        return cls(TagList([tag]))

    def cast_in(self, element: Element) -> None:
        """..."""
        if _debug:
            AnyAtomic._debug("cast_in %r %r", element.__class__.__name__, element)
        if not isinstance(element, Atomic):
            raise TypeError("atomic element expected")

        # carry on
        super().cast_in(element)

    def cast_out(self, cls: type) -> _Any:
        """..."""
        if _debug:
            AnyAtomic._debug("cast_out %r", cls.__name__)
        if not issubclass(cls, Atomic):
            raise TypeError("atomic class expected")

        # carry on
        return super().cast_out(cls)

    def get_value(self) -> _Any:
        """Return the value encoded in the type."""
        return super().cast_out(self.get_value_type())

    def get_value_type(self) -> type:
        """Return the datatype encoded in the Any iff possible."""
        if (len(self.tagList) == 1) and (
            self.tagList[0].tag_class == TagClass.application
        ):
            return Tag._app_tag_class[self.tagList[0].tag_number]

        raise TypeError("unable to determine encoded type")
