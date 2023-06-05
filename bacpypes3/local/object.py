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
from typing import Any as _Any, Callable, Dict, List, Optional, Tuple, Union

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
class Algorithm:
    """
    This is an abstract superclass of FaultAlgorithm and EventAlgorithm.
    """

    _debug: Callable[..., None]

    _monitors: List[PropertyMonitor]
    _what_changed: Dict[str, Tuple[_Any, _Any]]

    _execute_enabled: bool
    _execute_handle: Optional[asyncio.Handle]
    _execute_fn: Callable[Algorithm, None]

    def __init__(self):
        if _debug:
            Algorithm._debug("__init__")

        # detection monitor objects
        self._monitors = []
        self._what_changed = {}

        # handle for being scheduled to run
        self._execute_enabled = True
        self._execute_handle = None
        self._execute_fn = self.execute

    def bind(self, **kwargs):
        if _debug:
            Algorithm._debug("bind %r", kwargs)

        parm_names = []
        parm_tasks = []

        # loop through the parameter bindings
        for parameter, parameter_value in kwargs.items():
            if not isinstance(parameter_value, tuple):
                setattr(self, parameter, parameter_value)
                continue

            parameter_object, parameter_property = parameter_value

            # make a detection monitor
            monitor = PropertyMonitor(
                self, parameter, parameter_object, parameter_property
            )
            if _debug:
                Algorithm._debug("    - monitor: %r", monitor)

            # keep track of all of these monitor objects for if/when we unbind
            self._monitors.append(monitor)

            # make a task to read the value
            parm_names.append(parameter)
            parm_tasks.append(parameter_object.read_property(parameter_property))

        if parm_tasks:
            if _debug:
                Algorithm._debug("    - parm_tasks: %r", parm_tasks)

            # gather all the parameter tasks and continue algorithm specific
            # initialization after they are all finished
            parm_await_task = asyncio.gather(*parm_tasks)
            parm_await_task.add_done_callback(partial(self._parameter_init, parm_names))

        else:
            # proceed with initialization
            self.init()

    def unbind(self):
        if _debug:
            Algorithm._debug("unbind")

        # remove the property value monitor functions
        for monitor in self._monitors:
            if _debug:
                Algorithm._debug("    - monitor: %r", monitor)
            monitor.obj._property_monitors[monitor.prop].remove(monitor.property_change)

        # abandon the array
        self._monitors = []

    def _parameter_init(self, parm_names, parm_await_task) -> None:
        """
        This callback function is associated with the asyncio.gather() task
        that reads all of the current property values collected together during
        the bind() call.
        """
        if _debug:
            Algorithm._debug("_parameter_init: %r %r", parm_names, parm_await_task)

        parm_values = parm_await_task.result()
        if _debug:
            Algorithm._debug("    - parm_values: %r", parm_values)

        for parm_name, parm_value in zip(parm_names, parm_values):
            setattr(self, parm_name, parm_value)

        # proceed with initialization
        self.init()

    def init(self):
        """
        This is called after the `bind()` call and after all of the parameter
        initialization tasks have completed.
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

    def execute(self):
        raise NotImplementedError("execute() not implemented")


@bacpypes_debugging
class PropertyMonitor:
    """
    An instance of this class is used to associate a property of an
    object to a parameter of an event algorithm.  The property_change()
    function is called when the property changes value and that
    value is passed along as an attribute of the algorithm.
    """

    _debug: Callable[..., None]

    algorithm: Algorithm
    parameter: str
    obj: Object
    prop: str
    indx: Optional[int]

    def __init__(
        self,
        algorithm: Algorithm,
        parameter: str,
        obj: Object,
        prop: Union[int, str, PropertyIdentifier],
        indx: Optional[int] = None,
    ):
        if _debug:
            PropertyMonitor._debug("__init__ ... %r ...", parameter)

        # the property is the attribute name
        if isinstance(prop, int):
            prop = PropertyIdentifier(prop)
        if isinstance(prop, PropertyIdentifier):
            prop = prop.attr
        assert isinstance(prop, str)
        if _debug:
            PropertyMonitor._debug("    - prop: %r", prop)

        # keep track of the parameter values
        self.algorithm = algorithm
        self.parameter = parameter
        self.obj = obj
        self.prop = prop
        self.indx = indx

        # add the property value monitor function
        self.obj._property_monitors[self.prop].append(self.property_change)

    def property_change(self, old_value, new_value):
        if _debug:
            PropertyMonitor._debug(
                "property_change (%s) %r %r", self.parameter, old_value, new_value
            )

        # set the parameter value
        setattr(self.algorithm, self.parameter, new_value)

        if not self.algorithm._execute_enabled:
            if _debug:
                PropertyMonitor._debug("    - execute disabled")
            return

        # if the algorithm is scheduled to run, don't bother checking for more
        if self.algorithm._execute_handle:
            if _debug:
                PropertyMonitor._debug("    - already scheduled")
            return

        # see if something changed
        change_found = old_value != new_value
        if _debug:
            PropertyMonitor._debug("    - change_found: %r", change_found)

        # handy for debugging
        if change_found:
            self.algorithm._what_changed[self.parameter] = (old_value, new_value)

        # schedule it
        if change_found and not self.algorithm._execute_handle:
            self.algorithm._execute_handle = asyncio.get_event_loop().call_soon(
                self.algorithm._execute
            )
            if _debug:
                PropertyMonitor._debug(
                    "    - scheduled: %r", self.algorithm._execute_handle
                )


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
