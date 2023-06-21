"""
Local Object
"""
from __future__ import annotations

import asyncio
import inspect

from collections import defaultdict
from copy import deepcopy
from functools import partial
from threading import Thread
from typing import cast, Any as _Any, Callable, Dict, List, Optional, Tuple, Union

from ..debugging import bacpypes_debugging, ModuleLogger
from ..errors import PropertyError
from ..primitivedata import CharacterString, ObjectIdentifier
from ..basetypes import EventState, PropertyIdentifier, Reliability, StatusFlags
from ..constructeddata import ArrayOf

from ..object import Object as _Object, NotificationClassObject


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# type for the execute() method of an algorithm
ExecuteMethod = Callable[["Algorithm"], _Any]

# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class PropertyGetterThread(Thread):
    """
    An instance of this class is used when the getter of a property is a
    coroutine function and must run in its own event loop.
    """

    def __init__(self, getattr_fn) -> None:
        if _debug:
            PropertyGetterThread._debug("__init__ %r", getattr_fn)
        super().__init__()

        self.getattr_fn = getattr_fn

        # result is a (old_value, new_value) tuple if it changed
        self.result = None

        self.start()

    def run(self):
        loop = asyncio.new_event_loop()
        self.result = loop.run_until_complete(self._run())
        loop.close()

    async def _run(self):
        if _debug:
            PropertyGetterThread._debug("_run")

        # get the current value, wait for it if necessary
        current_value: _Any = self.getattr_fn()
        if _debug:
            PropertyGetterThread._debug("    - current_value: %r", current_value)

        if inspect.iscoroutinefunction(current_value):
            current_value = await current_value
            if _debug:
                PropertySetterThread._debug(
                    "    - awaited coroutine current_value: %r", current_value
                )

        if inspect.isawaitable(current_value):
            current_value = await current_value
            if _debug:
                PropertyGetterThread._debug(
                    "    - awaited awaitable current_value: %r", current_value
                )

        return current_value


@bacpypes_debugging
class PropertySetterThread(Thread):
    """
    An instance of this class is used when the setter and/or getter of
    a property is a coroutine function and must run in its own event
    loop.
    """

    def __init__(self, getattr_fn, setattr_fn, new_value) -> None:
        if _debug:
            PropertySetterThread._debug(
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
            PropertySetterThread._debug("_run")

        # get the current value, wait for it if necessary
        current_value: _Any = self.getattr_fn()
        if _debug:
            PropertySetterThread._debug("    - current_value: %r", current_value)

        if inspect.iscoroutinefunction(current_value):
            current_value = await current_value
            if _debug:
                PropertySetterThread._debug(
                    "    - awaited coroutine current_value: %r", current_value
                )
        if inspect.isawaitable(current_value):
            current_value = await current_value
            if _debug:
                PropertySetterThread._debug(
                    "    - awaited awaitable current_value: %r", current_value
                )

        # usually these are primitive data elements
        current_value = deepcopy(current_value)
        if current_value == self.new_value:
            return

        set_result = self.setattr_fn(self.new_value)
        if _debug:
            PropertySetterThread._debug("    - set_result: %r", set_result)

        if inspect.isawaitable(set_result):
            set_result = await set_result
            if _debug:
                PropertySetterThread._debug("    - awaited set_result: %r", set_result)

        return (current_value, self.new_value)


@bacpypes_debugging
class Algorithm:
    """
    This is an abstract superclass of FaultAlgorithm and EventAlgorithm.
    """

    _debug: Callable[..., None]

    _parameters: Dict[str, Parameter]
    _what_changed: Dict[str, Tuple[_Any, _Any]]

    _execute_enabled: bool
    _execute_handle: Optional[asyncio.Handle]
    _execute_fn: ExecuteMethod

    def __init__(self):
        if _debug:
            Algorithm._debug("__init__")

        # parameters
        self._parameters = {}
        self._what_changed = {}

        # handle for being scheduled to run
        self._execute_enabled = True
        self._execute_handle = None
        self._execute_fn = cast(ExecuteMethod, self.execute)

    def __getattr__(self, attr: str) -> _Any:
        """
        If attr is a parameter, redirect to the Parameter instance.
        """
        if attr.startswith("_") or (attr not in self._parameters):
            return object.__getattribute__(self, attr)
        if _debug:
            Algorithm._debug("__getattr__ %r", attr)

        return self._parameters[attr].getattr()

    def __setattr__(self, attr: str, value: _Any) -> None:
        """
        If attr is a parameter, redirect to the Parameter instance.
        """
        if attr.startswith("_") or (attr not in self._parameters):
            super().__setattr__(attr, value)
            return
        if _debug:
            Algorithm._debug("__setattr__ %r %r", attr, value)

        return self._parameters[attr].setattr(value)

    def bind(self, **kwargs):
        if _debug:
            Algorithm._debug("bind %r", kwargs)

        # loop through the parameter bindings
        for parameter_name, parameter_value in kwargs.items():
            # local value
            if not isinstance(parameter_value, tuple):
                setattr(self, parameter_name, parameter_value)
                continue

            # make a parameter reference, a.k.a. "smart" pointer
            parameter = Parameter(self, parameter_name, *parameter_value)
            if _debug:
                Algorithm._debug("    - parameter: %r", parameter)

            # keep track of all of these monitor objects for if/when we unbind
            self._parameters[parameter_name] = parameter

        # proceed with initialization
        self.init()

    def unbind(self):
        if _debug:
            Algorithm._debug("unbind")

        # remove the property value monitor functions
        for parameter in self._parameters.values():
            if _debug:
                Algorithm._debug("    - parameter: %r", parameter)
            if parameter.listen:
                parameter.obj._property_monitors[parameter.property_identifier].remove(
                    parameter.property_change
                )

        # abandon the mapping
        self._parameters = {}

    def init(self):
        """
        This is called after the `bind()` call.
        """
        if _debug:
            Algorithm._debug("init")

    def _execute(self):
        if _debug:
            Algorithm._debug("_execute")

        # no longer scheduled
        self._execute_handle = None

        # let the algorithm run
        self._execute_fn()

        # clear out what changed debugging
        self._what_changed = {}

    def execute(self) -> _Any:
        """
        Using the bound parameters, execute the algorithm.  This should be an
        @abstractmethod at some point.
        """
        raise NotImplementedError("execute() not implemented")


@bacpypes_debugging
class Parameter:
    """
    An instance of this class is used to associate a property of an
    object to a parameter of an event algorithm.  The property_change()
    function is called when the property changes value and that
    value is passed along as an attribute of the algorithm.
    """

    _debug: Callable[..., None]

    algorithm: Algorithm
    parameter_name: str
    obj: Object
    property_identifier: str
    listen: bool

    def __init__(
        self,
        algorithm: Algorithm,
        parameter_name: str,
        obj: Object,
        property_identifier: Union[int, str, PropertyIdentifier],
        listen: Optional[bool] = True,
    ):
        if _debug:
            Parameter._debug("__init__ ... %r ...", parameter_name)

        # the property_identifier is the attribute name
        if isinstance(property_identifier, int):
            property_identifier = PropertyIdentifier(property_identifier).attr
        if isinstance(property_identifier, PropertyIdentifier):
            property_identifier = property_identifier.attr
        if _debug:
            Parameter._debug("    - property_identifier: %r", property_identifier)

        # tiny bit of error checking
        if property_identifier not in obj._elements:
            raise ValueError(f"{property_identifier!r} is not a property of {obj}")

        # keep track of the parameter values
        self.algorithm = algorithm
        self.parameter_name = parameter_name
        self.obj = obj
        self.property_identifier = property_identifier
        self.listen = listen

        # add the property value monitor function
        if listen:
            self.obj._property_monitors[self.property_identifier].append(
                self.property_change
            )

    def getattr(self) -> _Any:
        """
        This function is called when the algoritm needs the value of the
        property from the object.
        """
        if _debug:
            Parameter._debug("getattr (%s)", self.parameter_name)

        return getattr(self.obj, self.property_identifier)

    def setattr(self, value: _Any) -> None:
        """
        This function is called when the algorithm updates the value of
        a property from the object.
        """
        if _debug:
            Parameter._debug("setattr (%s) %r", self.parameter_name, value)

        return setattr(self.obj, self.property_identifier, value)

    def property_change(self, old_value, new_value):
        if _debug:
            Parameter._debug(
                "property_change (%s) %r %r", self.parameter_name, old_value, new_value
            )

        if not self.algorithm._execute_enabled:
            if _debug:
                Parameter._debug("    - execute disabled")
            return

        # if the algorithm is scheduled to run, don't bother checking for more
        if self.algorithm._execute_handle:
            if _debug:
                Parameter._debug("    - already scheduled")
            return

        # see if something changed
        change_found = old_value != new_value
        if _debug:
            Parameter._debug("    - change_found: %r", change_found)

        # handy for debugging
        if change_found:
            self.algorithm._what_changed[self.parameter_name] = (old_value, new_value)

        # schedule it
        if change_found and not self.algorithm._execute_handle:
            self.algorithm._execute_handle = asyncio.get_event_loop().call_soon(
                self.algorithm._execute
            )
            if _debug:
                Parameter._debug("    - scheduled: %r", self.algorithm._execute_handle)


@bacpypes_debugging
class Object(_Object):
    """
    A local object has specialized property functions for changing the object
    name and identifier and has a dynamically generated propertyList property.
    """

    __objectName: CharacterString
    __objectIdentifier: ObjectIdentifier
    _property_monitors: Dict[str, List[Callable[..., None]]]
    _event_algorithm: Optional[Algorithm] = None
    _fault_algorithm: Optional[Algorithm] = None
    _notification_class_object: Optional[NotificationClassObject] = None

    def __init__(self, **kwargs) -> None:
        if _debug:
            Object._debug("__init__ %r", kwargs)

        self.__objectName = None
        self.__objectIdentifier = None
        self._property_monitors = defaultdict(list)

        super().__init__(**kwargs)

        # finish the initialization later
        asyncio.ensure_future(self._post_init())

    async def _post_init(self):
        """
        This function is called after all of the objects are added to the
        application so that references between objects can be made.
        """
        if _debug:
            Object._debug("_post_init")

        # link to the notification class object
        notification_class = self.notificationClass
        if notification_class is not None:
            for objid, obj in self._app.objectIdentifier.items():
                if isinstance(obj, NotificationClassObject):
                    if obj.notificationClass == notification_class:
                        self._notification_class_object = obj
                        break
            else:
                raise RuntimeError(
                    f"notification class object {self.notificationClass} not found"
                )
            if _debug:
                Object._debug(
                    "    - notification class object: %r",
                    self._notification_class_object.objectIdentifier,
                )

    def __getattribute__(self, attr: str) -> _Any:
        if attr.startswith("_") or (attr not in self._elements):
            return object.__getattribute__(self, attr)
        if _debug:
            Object._debug("__getattribute__ %r", attr)

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
        ):
            thread = PropertyGetterThread(
                partial(attr_property.fget, self),
            )
            if _debug:
                Object._debug("    - thread: %r", thread)

            thread.join()
            value = thread.result
        else:
            getattr_fn = partial(super().__getattribute__, attr)

            element = self._elements[attr]
            if _debug:
                Object._debug("    - element: %r", element)

            value = element.get_attribute(getter=getattr_fn)
        if _debug:
            Object._debug("    - value: %r", value)

        return value

    def __setattr__(self, attr: str, value: _Any) -> None:
        """
        This function traps changes to properties that have at least
        one associated monitor function.
        """
        if attr.startswith("_"):
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
            thread = PropertySetterThread(
                partial(attr_property.fget, self),
                partial(attr_property.fset, self),
                value,
            )
            thread.join()
            if not thread.result:
                if _debug:
                    Object._debug("    - no change")
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
                if _debug:
                    Object._debug("    - no change")
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

    @property
    def statusFlags(self) -> ArrayOf(PropertyIdentifier):  # type: ignore[valid-type, override]
        """Return the status flags."""
        if _debug:
            Object._debug("statusFlags(getter)")

        self_event_state = getattr(self, "eventState", None)
        self_reliability = getattr(self, "reliability", None)
        self_out_of_service = getattr(self, "outOfService", None)

        status_flags = StatusFlags(
            [
                int(
                    (self_event_state is not None)
                    and (self_event_state != EventState.normal)
                ),  # in alarm
                int(
                    (self_reliability is not None)
                    and (self_reliability != Reliability.noFaultDetected)
                ),  # fault
                0,  # overridden
                int(self_out_of_service == 1),  # out of service
            ]
        )
        if _debug:
            Object._debug("    - status_flags: %r", status_flags)

        return StatusFlags(status_flags)

    @statusFlags.setter
    def statusFlags(self, value: _Any) -> None:
        """
        Change the status flags, usually called with None in the case of
        an object being initialized, or in the case when the value is
        unmarshalled from a JSON blob or RDF graph, in both cases it
        can be ignored.
        """
        if _debug:
            Object._debug("statusFlags(setter) %r", value)
