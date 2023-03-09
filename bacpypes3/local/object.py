"""
Local Object
"""

import asyncio
import inspect

from collections import defaultdict
from copy import deepcopy
from functools import partial
from threading import Thread
from typing import Any as _Any, Callable, Dict, List

from ..debugging import bacpypes_debugging, ModuleLogger
from ..errors import PropertyError
from ..primitivedata import CharacterString, ObjectIdentifier
from ..basetypes import PropertyIdentifier
from ..constructeddata import ArrayOf

from ..object import Object as _Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class PropertyChangeThread(Thread):
    """
    An instance of this class is used when the setter and/or getter of
    a property is a coroutine function and must run in its own event
    loop.
    """

    def __init__(self, getattr_fn, setattr_fn, new_value) -> None:
        if _debug:
            PropertyChangeThread._debug(
                "__init__ %r %r %r", getattr_fn, setattr_fn, new_value
            )
        super().__init__()

        self.getattr_fn = getattr_fn
        self.setattr_fn = setattr_fn
        self.new_value = new_value

        # result is a (old_value, new_value) tuple if it changed
        self.result = None

        self.start()

    def run(self):
        loop = asyncio.new_event_loop()
        self.result = loop.run_until_complete(self._run())
        loop.close()

    async def _run(self):
        if _debug:
            PropertyChangeThread._debug("_run")

        # get the current value, wait for it if necessary
        current_value: _Any = self.getattr_fn()
        if _debug:
            PropertyChangeThread._debug("    - current_value: %r", current_value)
        if inspect.isawaitable(current_value):
            current_value = await current_value
            if _debug:
                PropertyChangeThread._debug(
                    "    - awaited current_value: %r", current_value
                )

        # usually these are primitive data elements
        current_value = deepcopy(current_value)
        if current_value == self.new_value:
            return

        set_result = self.setattr_fn(self.new_value)
        if _debug:
            PropertyChangeThread._debug("    - set_result: %r", set_result)
        if inspect.isawaitable(set_result):
            set_result = await set_result
            if _debug:
                PropertyChangeThread._debug("    - awaited set_result: %r", set_result)

        return (current_value, self.new_value)


@bacpypes_debugging
class Object(_Object):
    """
    A local object has specialized property functions for changing the object
    name and identifier and has a dynamically generated propertyList property.
    """

    __objectName: CharacterString
    __objectIdentifier: ObjectIdentifier
    _property_monitors: Dict[str, List[Callable[..., None]]]

    def __init__(self, **kwargs) -> None:
        if _debug:
            Object._debug("__init__ %r", kwargs)

        self.__objectName = None
        self.__objectIdentifier = None
        self._property_monitors = defaultdict(list)

        super().__init__(**kwargs)

    def __setattr__(self, attr: str, value: _Any) -> None:
        """
        This function traps changes to properties that have at least
        one associated monitor function.
        """
        if attr.startswith("_") or (attr not in self._property_monitors):
            super().__setattr__(attr, value)
            return
        if _debug:
            Object._debug("__setattr__ %r %r", attr, value)

        element = self._elements[attr]
        if _debug:
            Object._debug("    - element: %r", element)

        if value.__class__ != element:
            if _debug:
                Object._debug(
                    f"    - {attr} casting call: %r != %r", value.__class__, element
                )
            value = element(element.cast(value))

        # this might not be an @property defined attribute
        try:
            attr_property = inspect.getattr_static(self, attr)
        except AttributeError:
            attr_property = None
        if _debug:
            Object._debug("    - attr_property: %r", attr_property)

        # if the getter and/or setter are coroutine functions then both
        # calls need to run in a separate thread with its own event
        # loop.
        if isinstance(attr_property, property) and (
            inspect.iscoroutinefunction(attr_property.fget)
            or inspect.iscoroutinefunction(attr_property.fset)
        ):

            thread = PropertyChangeThread(
                partial(attr_property.fget, self),
                partial(attr_property.fset, self),
                value,
            )
            thread.join()
            if not thread.result:
                return

            current_value, value = thread.result
        else:
            getattr_fn = partial(super().__getattribute__, attr)
            setattr_fn = partial(super().__setattr__, attr)

            # get the current value
            current_value: _Any = getattr_fn()
            if _debug:
                Object._debug("    - current_value: %r", current_value)

            # usually these are primitive data elements
            # current_value = deepcopy(current_value)
            if value == current_value:
                return

            element.set_attribute(
                getter=getattr_fn,
                setter=setattr_fn,
                value=value,
            )

        # tell the monitors
        for fn in self._property_monitors[attr]:
            fn(current_value, value)

    @property
    def objectName(self) -> CharacterString:
        """Return the private value of the object name."""
        if _debug:
            Object._debug("objectName(getter)")

        return self.__objectName

    @objectName.setter
    def objectName(self, value: CharacterString) -> None:
        """
        Change the object name, and if it is associated with an application,
        update the application reference to this object.
        """
        if _debug:
            Object._debug("objectName(setter) %r", value)
        if value is None:
            raise ValueError("objectName")

        # make sure it's the correct type
        object_name_class = self.__class__._elements["objectName"]
        if not isinstance(value, object_name_class):
            value = object_name_class.cast(value)

        # check if this is associated with an application
        if not self._app:
            self.__objectName = value
        else:
            # no change
            if value == self.__objectName:
                return
            if value in self._app.objectName:
                raise PropertyError("duplicate-name")

            # out with the old, in with the new
            if self.__objectName in self._app.objectName:
                del self._app.objectName[self.__objectName]
            self.__objectName = value
            self._app.objectName[value] = self

    @property
    def objectIdentifier(self) -> ObjectIdentifier:
        """
        Return the private value of the object identifier.
        """
        if _debug:
            Object._debug("objectIdentifier(getter)")

        return self.__objectIdentifier

    @objectIdentifier.setter
    def objectIdentifier(self, value: ObjectIdentifier) -> None:
        """
        Change the object identifier, and if it is associated with an
        application, update the application reference to this object.
        """
        if _debug:
            Object._debug("objectIdentifier(setter) %r", value)
        if value is None:
            raise ValueError("objectIdentifier")

        # make sure it's the correct type
        object_identifier_class = self.__class__._elements["objectIdentifier"]
        if not isinstance(value, object_identifier_class):
            value = object_identifier_class.cast(value)

        # check if this is associated with an application
        if not self._app:
            self.__objectIdentifier = value
        else:
            # no change
            if value == self.__objectIdentifier:
                return
            if value in self._app.objectIdentifier:
                raise PropertyError("duplicate-object-id")

            # no switching object types
            if value[0] != self.__objectIdentifier[0]:
                raise PropertyError("value-out-of-range")

            # out with the old, in with the new
            if self.__objectIdentifier in self._app.objectIdentifier:
                del self._app.objectIdentifier[self.__objectIdentifier]
            self.__objectIdentifier = value
            self._app.objectIdentifier[value] = self

    @property
    def propertyList(self) -> ArrayOf(PropertyIdentifier):  # type: ignore[valid-type, override]
        """Return an array of property identifiers."""
        if _debug:
            Object._debug("propertyList(getter)")

        property_list = []
        property_identifier_class = self._property_identifier_class
        for element_name in self._elements:
            value = inspect.getattr_static(self, element_name, None)
            if value is None:
                continue
            property_list.append(property_identifier_class(element_name))

        return ArrayOf(PropertyIdentifier)(property_list)

    @propertyList.setter
    def propertyList(self, value: _Any) -> None:
        """
        Change the property list, usually called with None in the case of
        an object being initialized, or in the case when the value is
        unmarshalled from a JSON blob or RDF graph, in both cases it
        can be ignored.
        """
        if _debug:
            Object._debug("propertyList(setter) %r", value)
