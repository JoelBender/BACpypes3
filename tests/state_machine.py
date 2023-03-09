#!/usr/bin/python

"""
Testing State Machine
---------------------
"""

import asyncio
import inspect
import traceback

from queue import Queue

from typing import Any, Callable, Optional, List, Set, Tuple

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.pdu import PDU
from bacpypes3.comm import Client, Server


# some debugging
_debug = 0
_log = ModuleLogger(globals())


class Transition:

    """
    Transition
    ~~~~~~~~~~

    Instances of this class are transitions betweeen states of a state
    machine.
    """

    def __init__(self, next_state) -> None:
        self.next_state = next_state


class SendTransition(Transition):
    def __init__(self, pdu, next_state) -> None:
        Transition.__init__(self, next_state)

        self.pdu = pdu


class ReceiveTransition(Transition):
    def __init__(self, criteria, next_state) -> None:
        Transition.__init__(self, next_state)

        self.criteria = criteria


class EventTransition(Transition):
    def __init__(self, event_id, next_state) -> None:
        Transition.__init__(self, next_state)

        self.event_id = event_id


class TimeoutTransition(Transition):
    def __init__(self, timeout, next_state) -> None:
        Transition.__init__(self, next_state)

        self.timeout = timeout


class CallTransition(Transition):
    def __init__(self, fnargs, next_state) -> None:
        Transition.__init__(self, next_state)

        # a tuple of (fn, *args, *kwargs)
        self.fnargs = fnargs


#
#   match_pdu
#


@bacpypes_debugging
def match_pdu(pdu, pdu_type=None, **pdu_attrs) -> bool:
    if _debug:
        match_pdu._debug("match_pdu %r %r %r", pdu, pdu_type, pdu_attrs)  # type: ignore[attr-defined]

    # check the type
    if pdu_type and not isinstance(pdu, pdu_type):
        if _debug:
            match_pdu._debug("    - failed match, wrong type")  # type: ignore[attr-defined]
        return False

    # check for matching attribute values
    for attr_name, attr_value in pdu_attrs.items():
        if not hasattr(pdu, attr_name):
            if _debug:
                match_pdu._debug("    - failed match, missing attr: %r", attr_name)  # type: ignore[attr-defined]
            return False
        if getattr(pdu, attr_name) != attr_value:
            if _debug:
                match_pdu._debug(  # type: ignore[attr-defined]
                    "    - failed match, attr value: %r, %r", attr_name, attr_value
                )
            return False
    if _debug:
        match_pdu._debug("    - successful match")  # type: ignore[attr-defined]

    return True


#
#   TimeoutTask
#


@bacpypes_debugging
class TimeoutTask:
    _debug: Callable[..., None]

    callback: Callable[..., None]
    args: Tuple[Any, ...]
    # loop: asyncio.events.AbstractEventLoop
    handle: Optional[asyncio.Handle]

    def __init__(self, callback: Callable[..., None], *args: Any) -> None:
        if _debug:
            TimeoutTask._debug("__init__ %r %r", callback, args)

        # save the function and args
        self.callback = callback
        self.args = args

        # self.loop = asyncio.get_event_loop()
        self.task = None
        self.handle = None

    def call_soon(self) -> None:
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.process_task())
        self.handle = asyncio.get_event_loop().call_soon(self.task)
        if _debug:
            TimeoutTask._debug("call_soon %r", self.handle)

    def call_later(self, delay: float) -> None:
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.process_task())
        self.handle = asyncio.get_event_loop().call_later(delay, self.task)
        if _debug:
            TimeoutTask._debug("call_later %r", self.handle)

    def call_at(self, when: float) -> None:
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.process_task())
        self.handle = asyncio.get_event_loop().call_at(when, self.task)
        if _debug:
            TimeoutTask._debug("call_at %r", self.handle)

    def cancel(self) -> None:
        if _debug:
            TimeoutTask._debug("cancel")
        assert self.handle

        self.handle.cancel()
        self.handle = None

    async def process_task(self) -> None:
        if _debug:
            TimeoutTask._debug("process_task %r %r", self.callback, self.args)
        response = self.callback(*self.args)
        if inspect.isawaitable(response):
            if _debug:
                TimeoutTask._debug("    - awaiting: %r", response)
            response = await response

    def __repr__(self) -> str:
        return "<%s of %r at %s>" % (
            self.__class__.__name__,
            self.callback,
            hex(id(self)),
        )


#
#   State
#


@bacpypes_debugging
class State:

    """
    State
    ~~~~~

    Instances of this class, or a derived class, are the states of a state
    machine.
    """

    _debug: Callable[..., None]

    state_machine: "StateMachine"
    doc_string: str

    is_success_state: bool
    is_fail_state: bool

    send_transitions: List[Transition]
    receive_transitions: List[Transition]
    set_event_transitions: List[Transition]
    clear_event_transitions: List[Transition]
    wait_event_transitions: List[Transition]

    timeout_transition: Optional[TimeoutTransition]
    call_transition: Optional[CallTransition]

    def __init__(self, state_machine: "StateMachine", doc_string: str = "") -> None:
        """Create a new state, bound to a specific state machine.  This is
        typically called by the state machine.
        """
        if _debug:
            State._debug("__init__ %r doc_string=%r", state_machine, doc_string)

        self.state_machine = state_machine
        self.doc_string = doc_string
        self.is_success_state = False
        self.is_fail_state = False

        # empty lists of send and receive transitions
        self.send_transitions = []
        self.receive_transitions = []

        # empty lists of event transitions
        self.set_event_transitions = []
        self.clear_event_transitions = []
        self.wait_event_transitions = []

        # timeout transition
        self.timeout_transition = None

        # call transition
        self.call_transition = None

    def reset(self) -> None:
        """Override this method in a derived class if the state maintains
        counters or other information.  Called when the associated state
        machine is reset.
        """
        if _debug:
            State._debug("reset")

    def doc(self, doc_string: str) -> "State":
        """Change the documentation string (label) for the state.  The state
        is returned for method chaining.
        """
        if _debug:
            State._debug("doc %r", doc_string)

        # save the doc string
        self.doc_string = doc_string

        # chainable
        return self

    def success(self, doc_string: Optional[str] = None) -> "State":
        """Mark a state as a successful final state.  The state is returned
        for method chaining.

        :param doc_string: an optional label for the state
        """
        if _debug:
            State._debug("success %r", doc_string)

        # error checking
        if self.is_success_state:
            raise RuntimeError("already a success state")
        if self.is_fail_state:
            raise RuntimeError("already a fail state")

        # this is now a success state
        self.is_success_state = True

        # save the new doc string
        if doc_string is not None:
            self.doc_string = doc_string
        elif not self.doc_string:
            self.doc_string = "success"

        # chainable
        return self

    def fail(self, doc_string: Optional[str] = None) -> "State":
        """Mark a state as a failure final state.  The state is returned
        for method chaining.

        :param doc_string: an optional label for the state
        """
        if _debug:
            State._debug("fail %r", doc_string)

        # error checking
        if self.is_success_state:
            raise RuntimeError("already a success state")
        if self.is_fail_state:
            raise RuntimeError("already a fail state")

        # this is now a fail state
        self.is_fail_state = True

        # save the new doc string
        if doc_string is not None:
            self.doc_string = doc_string
        elif not self.doc_string:
            self.doc_string = "fail"

        # chainable
        return self

    def enter_state(self) -> None:
        """Called when the state machine is entering the state."""
        if _debug:
            State._debug("enter_state(%s)", self.doc_string)

        # if there is a timeout, schedule it
        if self.timeout_transition:
            if _debug:
                State._debug("    - waiting: %r", self.timeout_transition.timeout)

            # schedule the timeout
            self.state_machine.state_timeout_task.call_later(
                self.timeout_transition.timeout
            )
        else:
            if _debug:
                State._debug("    - no timeout")

    def exit_state(self) -> None:
        """Called when the state machine is exiting the state."""
        if _debug:
            State._debug("exit_state(%s)", self.doc_string)

        # if there was a timeout, suspend it
        if self.timeout_transition:
            if _debug:
                State._debug("    - canceling timeout")

            self.state_machine.state_timeout_task.cancel()

    def send(self, pdu, next_state=None) -> "State":
        """Create a SendTransition from this state to another, possibly new,
        state.  The next state is returned for method chaining.

        :param pdu: PDU to send
        :param next_state: state to transition to after sending
        """
        if _debug:
            State._debug("send(%s) %r next_state=%r", self.doc_string, pdu, next_state)

        # maybe build a new state
        if not next_state:
            next_state = self.state_machine.new_state()
            if _debug:
                State._debug("    - new next_state: %r", next_state)
        elif next_state not in self.state_machine.states:
            raise ValueError("off the rails")

        # add this to the list of transitions
        self.send_transitions.append(SendTransition(pdu, next_state))

        # return the next state
        return next_state

    def before_send(self, pdu) -> None:
        """Called before each PDU about to be sent."""
        self.state_machine.before_send(pdu)

    def after_send(self, pdu) -> None:
        """Called after each PDU sent."""
        self.state_machine.after_send(pdu)

    def receive(
        self, pdu_type, next_state: Optional["State"] = None, **pdu_attrs
    ) -> "State":
        """Create a ReceiveTransition from this state to another, possibly new,
        state.  The next state is returned for method chaining.

        :param criteria: PDU to match
        :param next_state: destination state after a successful match
        """
        if _debug:
            State._debug("receive(%s) %r %r", self.doc_string, pdu_type, pdu_attrs)

        # maybe build a new state
        if not next_state:
            next_state = self.state_machine.new_state()
            if _debug:
                State._debug("    - new next_state: %r", next_state)
        elif next_state not in self.state_machine.states:
            raise ValueError("off the rails")
        assert next_state

        # create a bundle of the match criteria
        criteria = (pdu_type, pdu_attrs)
        if _debug:
            State._debug("    - criteria: %r", criteria)

        # add this to the list of transitions
        self.receive_transitions.append(ReceiveTransition(criteria, next_state))

        # return the next state
        return next_state

    def before_receive(self, pdu) -> None:
        """Called with each PDU received before matching."""
        self.state_machine.before_receive(pdu)

    def after_receive(self, pdu) -> None:
        """Called with PDU received after match."""
        self.state_machine.after_receive(pdu)

    def ignore(self, pdu_type, **pdu_attrs) -> "State":
        """Create a ReceiveTransition from this state to itself, if match
        is successful the effect is to ignore the PDU.

        :param criteria: PDU to match
        """
        if _debug:
            State._debug("ignore(%s) %r %r", self.doc_string, pdu_type, pdu_attrs)

        # create a bundle of the match criteria
        criteria = (pdu_type, pdu_attrs)
        if _debug:
            State._debug("    - criteria: %r", criteria)

        # add this to the list of transitions
        self.receive_transitions.append(ReceiveTransition(criteria, self))

        # return this state, no new state is created
        return self

    def unexpected_receive(self, pdu):
        """Called with PDU that did not match."""
        if _debug:
            State._debug("unexpected_receive %r", pdu)

    def set_event(self, event_id) -> "State":
        """Create an EventTransition for this state that sets an event.  The
        current state is returned for method chaining.

        :param event_id: event identifier
        """
        if _debug:
            State._debug("set_event(%s) %r", self.doc_string, event_id)

        # add this to the list of transitions
        self.set_event_transitions.append(EventTransition(event_id, None))

        # return the next state
        return self

    def event_set(self, event_id) -> None:
        """Called with the event that was set."""
        pass

    def clear_event(self, event_id) -> "State":
        """Create an EventTransition for this state that clears an event.  The
        current state is returned for method chaining.

        :param event_id: event identifier
        """
        if _debug:
            State._debug("clear_event(%s) %r", self.doc_string, event_id)

        # add this to the list of transitions
        self.clear_event_transitions.append(EventTransition(event_id, None))

        # return the next state
        return self

    def wait_event(self, event_id, next_state: Optional["State"] = None) -> "State":
        """Create an EventTransition from this state to another, possibly new,
        state.  The next state is returned for method chaining.

        :param pdu: PDU to send
        :param next_state: state to transition to after sending
        """
        if _debug:
            State._debug(
                "wait_event(%s) %r next_state=%r", self.doc_string, event_id, next_state
            )

        # maybe build a new state
        if not next_state:
            next_state = self.state_machine.new_state()
            if _debug:
                State._debug("    - new next_state: %r", next_state)
        elif next_state not in self.state_machine.states:
            raise ValueError("off the rails")
        assert next_state

        # add this to the list of transitions
        self.wait_event_transitions.append(EventTransition(event_id, next_state))

        # return the next state
        return next_state

    def timeout(self, delay: float, next_state: Optional["State"] = None) -> "State":
        """Create a TimeoutTransition from this state to another, possibly new,
        state.  There can only be one timeout transition per state.  The next
        state is returned for method chaining.

        :param delay: the amount of time to wait for a matching PDU
        :param next_state: destination state after timeout
        """
        if _debug:
            State._debug(
                "timeout(%s) %r next_state=%r", self.doc_string, delay, next_state
            )

        # check to see if a timeout has already been specified
        if self.timeout_transition:
            raise RuntimeError("state already has a timeout")

        # maybe build a new state
        if not next_state:
            next_state = self.state_machine.new_state()
            if _debug:
                State._debug("    - new next_state: %r", next_state)
        elif next_state not in self.state_machine.states:
            raise ValueError("off the rails")
        assert next_state

        # set the transition
        self.timeout_transition = TimeoutTransition(delay, next_state)

        # return the next state
        return next_state

    def call(
        self,
        fn: Callable[..., None],
        *args: Any,
        next_state: Optional["State"] = None,
        **kwargs: Any
    ) -> "State":
        """Create a CallTransition from this state to another, possibly new,
        state.  The next state is returned for method chaining.

        :param criteria: PDU to match
        :param next_state: destination state after a successful match
        """
        if _debug:
            State._debug("call(%s) %r %r %r", self.doc_string, fn, args, kwargs)

        # only one call per state
        if self.call_transition:
            raise RuntimeError("only one 'call' per state")

        # maybe build a new state
        if not next_state:
            next_state = self.state_machine.new_state()
            if _debug:
                State._debug("    - new next_state: %r", next_state)
        elif next_state not in self.state_machine.states:
            raise ValueError("off the rails")
        assert next_state

        # create a bundle of the function and arguments
        fnargs = (fn, args, kwargs)
        if _debug:
            State._debug("    - fnargs: %r", fnargs)

        # add this to the list of transitions
        self.call_transition = CallTransition(fnargs, next_state)

        # return the next state
        return next_state

    def __repr__(self):
        return "<%s(%s) at %s>" % (
            self.__class__.__name__,
            self.doc_string,
            hex(id(self)),
        )


@bacpypes_debugging
class StateMachine:

    """
    StateMachine
    ~~~~~~~~~~~~

    A state machine consisting of states.  Every state machine has a start
    state where the state machine begins when it is started.  It also has
    an *unexpected receive* fail state where the state machine goes if
    there is an unexpected (unmatched) PDU received.
    """

    _debug: Callable[..., None]

    name: str

    states: List[State]
    start_state: State
    unexpected_receive_state: State
    timeout_state: Optional[State]
    timeout_task: Optional[TimeoutTask]

    state_transitioning: int
    transition_queue: Queue
    transaction_log: List[Tuple[str, PDU]]

    running: bool
    is_success_state: Optional[bool]
    is_fail_state: Optional[bool]
    machine_group: Optional["StateMachineGroup"]

    state_subclass: Callable[..., State]

    def __init__(
        self,
        timeout: Optional[float] = None,
        start_state: Optional[State] = None,
        unexpected_receive_state: Optional[State] = None,
        machine_group: Optional["StateMachineGroup"] = None,
        state_subclass: Callable[..., State] = State,
        name: str = "",
    ) -> None:
        if _debug:
            StateMachine._debug("__init__(%s)", name)

        # save the name for debugging
        self.name = name

        # no states to starting out, not running
        self.states = []
        self.running = False

        # flags for remembering success or fail
        self.is_success_state = None
        self.is_fail_state = None

        # might be part of a group
        self.machine_group = machine_group

        # reset to initial condition
        self.reset()

        # save the state subclass for new states
        self.state_subclass = state_subclass  # type: ignore[assignment]
        if _debug:
            StateMachine._debug("    - state_subclass: %r", self.state_subclass)

        # create the start state
        if start_state:
            if start_state.state_machine:
                raise RuntimeError("start state already bound to a machine")
            self.states.append(start_state)
            start_state.state_machine = self
        else:
            start_state = self.new_state("start")
        self.start_state = start_state
        if _debug:
            StateMachine._debug("    - start_state: %r", self.start_state)

        # create the unexpected receive state
        if unexpected_receive_state:
            if unexpected_receive_state.state_machine:
                raise RuntimeError(
                    "unexpected receive state already bound to a machine"
                )
            self.states.append(unexpected_receive_state)
            unexpected_receive_state.state_machine = self
        else:
            unexpected_receive_state = self.new_state("unexpected receive").fail()
        self.unexpected_receive_state = unexpected_receive_state
        if _debug:
            StateMachine._debug(
                "    - unexpected_receive_state: %r", self.unexpected_receive_state
            )

        # received messages get queued during state transitions
        self.state_transitioning = 0
        self.transition_queue = Queue()

        # create a state timeout task, to be installed as necessary
        self.state_timeout_task = TimeoutTask(self.state_timeout)

        # create a state machine timeout task
        self.timeout = timeout
        if timeout:
            self.timeout_state = self.new_state("state machine timeout").fail()
            self.timeout_task = TimeoutTask(self.state_machine_timeout)
        else:
            self.timeout_state = None
            self.timeout_task = None

    def new_state(
        self, doc: str = "", state_subclass: Optional[Callable[..., State]] = None
    ) -> State:
        if _debug:
            StateMachine._debug("new_state(%s) %r %r", self.name, doc, state_subclass)

        # make the state object from the class that was provided or default
        state = (state_subclass or self.state_subclass)(self, doc)
        if _debug:
            StateMachine._debug("    - state: %r", state)

        # save a reference to make sure we don't go off the rails
        self.states.append(state)

        # return the new state
        return state

    def reset(self) -> None:
        if _debug:
            StateMachine._debug("reset(%s)", self.name)

        # make sure we're not running
        if self.running:
            raise RuntimeError("state machine running")

        # flags for remembering success or fail
        self.is_success_state = None
        self.is_fail_state = None

        # no current state, empty transaction log
        self.current_state = None
        self.transaction_log = []

        # we are not starting up
        self._startup_flag = False

        # give all the states a chance to reset
        for state in self.states:
            state.reset()

    async def run(self) -> None:
        if _debug:
            StateMachine._debug("run(%s)", self.name)

        if self.running:
            raise RuntimeError("state machine running")
        if self.current_state:
            raise RuntimeError("not running but has a current state")

        # if there is a timeout task, schedule the fail
        if self.timeout_task:
            if _debug:
                StateMachine._debug("    - schedule runtime limit")
            assert self.timeout
            self.timeout_task.call_later(self.timeout)

        # we are starting up
        self._startup_flag = True

        # go to the start state
        await self.goto_state(self.start_state)

        # startup complete
        self._startup_flag = False

        # if it is part of a group, let the group know
        if self.machine_group:
            self.machine_group.started(self)

            # if it stopped already, let the group know
            if not self.running:
                self.machine_group.stopped(self)

    def halt(self) -> None:
        """Called when the state machine should no longer be running."""
        if _debug:
            StateMachine._debug("halt(%s)", self.name)

        # make sure we're running
        if not self.running:
            raise RuntimeError("state machine not running")

        # cancel the timeout task
        if self.timeout_task:
            if _debug:
                StateMachine._debug("    - cancel runtime limit")
            self.timeout_task.cancel()

        # no longer running
        self.running = False

    def success(self) -> None:
        """Called when the state machine has successfully completed."""
        if _debug:
            StateMachine._debug("success(%s)", self.name)

        # flags for remembering success or fail
        self.is_success_state = True

    def fail(self) -> None:
        """Called when the state machine has failed."""
        if _debug:
            StateMachine._debug("fail(%s)", self.name)

        # flags for remembering success or fail
        self.is_fail_state = True

    async def goto_state(self, state) -> None:
        if _debug:
            StateMachine._debug("goto_state(%s) %r", self.name, state)

        # where do you think you're going?
        if state not in self.states:
            raise RuntimeError("off the rails")

        # transitioning
        self.state_transitioning += 1

        # exit the old state
        if self.current_state:
            self.current_state.exit_state()
        elif state is self.start_state:
            # starting up
            self.running = True
        else:
            raise RuntimeError("start at the start state")

        # here we are
        current_state = self.current_state = state

        # let the state do something
        current_state.enter_state()
        if _debug:
            StateMachine._debug("    - state entered")

        # events are managed by a state machine group
        if self.machine_group:
            # setting events, wait for each one to complete state transition
            for transition in current_state.set_event_transitions:
                if _debug:
                    StateMachine._debug("    - setting event: %r", transition.event_id)
                await self.machine_group.set_event(transition.event_id)

            # clearing events
            for transition in current_state.clear_event_transitions:
                if _debug:
                    StateMachine._debug("    - clearing event: %r", transition.event_id)
                self.machine_group.clear_event(transition.event_id)

        # check for success state
        if current_state.is_success_state:
            if _debug:
                StateMachine._debug("    - success state")
            self.state_transitioning -= 1

            self.halt()
            self.success()

            # if it is part of a group, let the group know
            if self.machine_group and not self._startup_flag:
                self.machine_group.stopped(self)

            return

        # check for fail state
        if current_state.is_fail_state:
            if _debug:
                StateMachine._debug("    - fail state")
            self.state_transitioning -= 1

            self.halt()
            self.fail()

            # if it is part of a group, let the group know
            if self.machine_group and not self._startup_flag:
                self.machine_group.stopped(self)

            return

        # assume we can stay
        next_state = None

        # events are managed by a state machine group
        if self.machine_group:
            # check to see if there are events that are already set
            for transition in current_state.wait_event_transitions:
                if _debug:
                    StateMachine._debug("    - waiting event: %r", transition.event_id)

                # check for a transition
                if transition.event_id in self.machine_group.events:
                    next_state = transition.next_state
                    if _debug:
                        StateMachine._debug("    - next_state: %r", next_state)

                    if next_state is not current_state:
                        break
            else:
                if _debug:
                    StateMachine._debug("    - no events already set")
        else:
            if _debug:
                StateMachine._debug("    - not part of a group")

        # call things that need to be called
        if current_state.call_transition:
            if _debug:
                StateMachine._debug("    - calling: %r", current_state.call_transition)

            # pull apart the pieces and call it
            fn, args, kwargs = current_state.call_transition.fnargs
            try:
                fn(*args, **kwargs)
                if _debug:
                    StateMachine._debug("    - called, no exception")

                # check for a transition
                next_state = current_state.call_transition.next_state
                if _debug:
                    StateMachine._debug("    - next_state: %r", next_state)

            except AssertionError as err:
                if _debug:
                    StateMachine._debug("    - called, exception: %r", err)
                self.state_transitioning -= 1

                self.halt()
                self.fail()

                # if it is part of a group, let the group know
                if self.machine_group and not self._startup_flag:
                    self.machine_group.stopped(self)

                return
        else:
            if _debug:
                StateMachine._debug("    - no calls")

        # send everything that needs to be sent
        if not next_state:
            for transition in current_state.send_transitions:
                if _debug:
                    StateMachine._debug("    - sending: %r", transition)

                current_state.before_send(transition.pdu)
                await self.send(transition.pdu)
                current_state.after_send(transition.pdu)

                # check for a transition
                next_state = transition.next_state
                if _debug:
                    StateMachine._debug("    - next_state: %r", next_state)

                if next_state is not current_state:
                    break

        if not next_state:
            if _debug:
                StateMachine._debug("    - nowhere to go")

        elif next_state is self.current_state:
            if _debug:
                StateMachine._debug("    - going nowhere")

        else:
            if _debug:
                StateMachine._debug("    - going")

            await self.goto_state(next_state)

        # no longer transitioning
        self.state_transitioning -= 1

        # could be recursive call
        if not self.state_transitioning:
            while self.running and not self.transition_queue.empty():
                pdu = self.transition_queue.get()
                if _debug:
                    StateMachine._debug("    - transition_queue pdu: %r", pdu)

                # try again
                await self.receive(pdu)

    def before_send(self, pdu) -> None:
        """Called before each PDU about to be sent."""

        # add a reference to the pdu in the transaction log
        self.transaction_log.append(
            ("<<<", pdu),
        )

    async def send(self, pdu) -> None:
        if _debug:
            StateMachine._debug("send(%s) %r", self.name, pdu)

        raise NotImplementedError("send not implemented")

    def after_send(self, pdu) -> None:
        """Called after each PDU sent."""
        pass

    def before_receive(self, pdu) -> None:
        """Called with each PDU received before matching."""

        # add a reference to the pdu in the transaction log
        self.transaction_log.append(
            (">>>", pdu),
        )

    async def receive(self, pdu) -> None:
        if _debug:
            StateMachine._debug("receive(%s) %r", self.name, pdu)

        # check to see if haven't started yet or we are transitioning
        if (not self.current_state) or self.state_transitioning:
            if _debug:
                StateMachine._debug("    - queue for later")

            self.transition_queue.put(pdu)
            if _debug:
                StateMachine._debug(
                    "    - stack: %r",
                    [
                        "%s:%s" % (filename.split("/")[-1], lineno)
                        for filename, lineno, _, _ in traceback.extract_stack()[-6:-1]
                    ],
                )
            return

        # if this is not running it already completed
        if not self.running:
            if _debug:
                StateMachine._debug("    - already completed")
            return

        # reference the current state
        current_state = self.current_state
        if _debug:
            StateMachine._debug("    - current_state: %r", current_state)

        # let the state know this was received
        current_state.before_receive(pdu)

        match_found = False

        # look for a matching receive transition
        for transition in current_state.receive_transitions:
            if self.match_pdu(pdu, transition.criteria):
                if _debug:
                    StateMachine._debug("    - match found")
                match_found = True

                # let the state know this was matched
                current_state.after_receive(pdu)

                # check for a transition
                next_state = transition.next_state
                if _debug:
                    StateMachine._debug("    - next_state: %r", next_state)

                # a match was found, but by transitioning back to the
                # current state, the pdu will not be "unexpectedly received"
                # and there could be a subsequent match
                if next_state is not current_state:
                    break
        else:
            if _debug:
                StateMachine._debug("    - no matches")

        if not match_found:
            if _debug:
                StateMachine._debug("    - unexpected")

            # let the state know
            current_state.unexpected_receive(pdu)

            # now the state machine gets a crack at it
            await self.unexpected_receive(pdu)

        elif next_state is not current_state:
            if _debug:
                StateMachine._debug("    - going")

            await self.goto_state(next_state)

    def after_receive(self, pdu) -> None:
        """Called with PDU received after match."""
        pass

    async def unexpected_receive(self, pdu) -> None:
        """Called with PDU that did not match."""
        if _debug:
            StateMachine._debug("unexpected_receive(%s) %r", self.name, pdu)
            StateMachine._debug("    - current_state: %r", self.current_state)

        # go to the unexpected receive state (failing)
        await self.goto_state(self.unexpected_receive_state)

    async def event_set(self, event_id) -> None:
        """Called by the state machine group when an event is set, the state
        machine checks to see if it's waiting for the event and makes the
        state transition if there is a match."""
        if _debug:
            StateMachine._debug("event_set(%s) %r", self.name, event_id)

        if not self.running:
            if _debug:
                StateMachine._debug("    - not running")
            return

        # check to see if we are transitioning
        if self.state_transitioning:
            if _debug:
                StateMachine._debug("    - transitioning")
            return
        if not self.current_state:
            raise RuntimeError("no current state")
        current_state = self.current_state

        match_found = False

        # look for a matching event transition
        for transition in current_state.wait_event_transitions:
            if transition.event_id == event_id:
                if _debug:
                    StateMachine._debug("    - match found")
                match_found = True

                # let the state know this event was set
                current_state.event_set(event_id)

                # check for a transition
                next_state = transition.next_state
                if _debug:
                    StateMachine._debug("    - next_state: %r", next_state)

                if next_state is not current_state:
                    break
        else:
            if _debug:
                StateMachine._debug("    - going nowhere")

        if match_found and next_state is not current_state:
            if _debug:
                StateMachine._debug("    - going")

            await self.goto_state(next_state)

    async def state_timeout(self) -> None:
        if _debug:
            StateMachine._debug("state_timeout(%s)", self.name)

        if not self.running:
            raise RuntimeError("state machine not running")

        assert self.current_state
        if not self.current_state.timeout_transition:
            raise RuntimeError("state timeout, but no timeout transition")

        # go to the state specified
        await self.goto_state(self.current_state.timeout_transition.next_state)

    async def state_machine_timeout(self) -> None:
        if _debug:
            StateMachine._debug("state_machine_timeout(%s)", self.name)

        if not self.running:
            raise RuntimeError("state machine not running")

        # go to the state specified
        await self.goto_state(self.timeout_state)

    def match_pdu(self, pdu, criteria) -> bool:
        if _debug:
            StateMachine._debug("match_pdu(%s) %r %r", self.name, pdu, criteria)

        # separate the pdu_type and attributes to match
        pdu_type, pdu_attrs = criteria

        # pass along to the global function
        return match_pdu(pdu, pdu_type, **pdu_attrs)

    def __repr__(self) -> str:
        if not self.current_state:
            state_text = "not started"
        elif self.is_success_state:
            state_text = "success"
        elif self.is_fail_state:
            state_text = "fail"
        elif not self.running:
            state_text = "idle"
        else:
            state_text = "in"

        if self.current_state:
            state_text += " " + repr(self.current_state)

        return "<%s(%s) %s at %s>" % (
            self.__class__.__name__,
            self.name,
            state_text,
            hex(id(self)),
        )


@bacpypes_debugging
class StateMachineGroup:

    """
    StateMachineGroup
    ~~~~~~~~~~~~~~~~~

    A state machine group is a collection of state machines that are all
    started and stopped together.  There are methods available to derived
    classes that are called when all of the machines in the group have
    completed, either all successfully or at least one has failed.

    .. note:: When creating a group of state machines, add the ones that
        are expecting to receive one or more PDU's first before the ones
        that send PDU's.  They will be started first, and be ready for the
        PDU that might be sent.
    """

    _debug: Callable[..., None]

    state_machines: List[StateMachine]
    _startup_flag: bool
    is_running: bool
    is_success_state: Optional[bool]
    is_fail_state: Optional[bool]

    events: Set[str]

    def __init__(self) -> None:
        """Create a state machine group."""
        if _debug:
            StateMachineGroup._debug("__init__")

        # empty list of machines
        self.state_machines = []

        # flag for starting up
        self._startup_flag = False

        # flag for at least one machine running
        self.is_running = False

        # flags for remembering success or fail
        self.is_success_state = None
        self.is_fail_state = None

        # set of events that are set
        self.events = set()

    def append(self, state_machine) -> None:
        """Add a state machine to the end of the list of state machines."""
        if _debug:
            StateMachineGroup._debug("append %r", state_machine)

        # check the state machine
        if not isinstance(state_machine, StateMachine):
            raise TypeError("not a state machine")
        if state_machine.machine_group:
            raise RuntimeError("state machine already a part of a group")

        # tell the state machine it is a member of this group
        state_machine.machine_group = self

        # add it to the list
        self.state_machines.append(state_machine)

    def remove(self, state_machine) -> None:
        """Remove a state machine from the list of state machines."""
        if _debug:
            StateMachineGroup._debug("remove %r", state_machine)

        # check the state machine
        if not isinstance(state_machine, StateMachine):
            raise TypeError("not a state machine")
        if state_machine.machine_group is not self:
            raise RuntimeError("state machine not a member of this group")

        # tell the state machine it is no longer a member of this group
        state_machine.machine_group = None

        # pass along to the list
        self.state_machines.remove(state_machine)

    def reset(self) -> None:
        """Resets all the machines in the group."""
        if _debug:
            StateMachineGroup._debug("reset")

        # pass along to each machine
        for state_machine in self.state_machines:
            if _debug:
                StateMachineGroup._debug("    - resetting: %r", state_machine)
            state_machine.reset()

        # flags for remembering success or fail
        self.is_success_state = False
        self.is_fail_state = False

        # events that are set
        self.events = set()

    async def set_event(self, event_id) -> None:
        """Save an event as 'set' and pass it to the state machines to see
        if they are in a state that is waiting for the event."""
        if _debug:
            StateMachineGroup._debug("set_event %r", event_id)

        self.events.add(event_id)
        if _debug:
            StateMachineGroup._debug("    - event set")

        # pass along to each machine
        for state_machine in self.state_machines:
            if _debug:
                StateMachineGroup._debug("    - state_machine: %r", state_machine)
            await state_machine.event_set(event_id)

    def clear_event(self, event_id) -> None:
        """Remove an event from the set of elements that are 'set'."""
        if _debug:
            StateMachineGroup._debug("clear_event %r", event_id)

        if event_id in self.events:
            self.events.remove(event_id)
            if _debug:
                StateMachineGroup._debug("    - event cleared")
        else:
            if _debug:
                StateMachineGroup._debug("    - noop")

    async def run(self) -> None:
        """Runs all the machines in the group."""
        if _debug:
            StateMachineGroup._debug("run")

        # turn on the startup flag
        self._startup_flag = True
        self.is_running = True

        # pass along to each machine
        for state_machine in self.state_machines:
            if _debug:
                StateMachineGroup._debug("    - starting: %r", state_machine)
            await state_machine.run()

        # turn off the startup flag
        self._startup_flag = False
        if _debug:
            StateMachineGroup._debug("    - all started")

        # check for success/fail, all of the machines may already be done
        all_success, some_failed = self.check_for_success()
        if all_success:
            self.success()
        elif some_failed:
            self.fail()
        else:
            if _debug:
                StateMachineGroup._debug("    - some still running")

    def started(self, state_machine) -> None:
        """Called by a state machine in the group when it has completed its
        transition into its starting state."""
        if _debug:
            StateMachineGroup._debug("started %r", state_machine)

    def stopped(self, state_machine) -> None:
        """Called by a state machine after it has halted and its success()
        or fail() method has been called."""
        if _debug:
            StateMachineGroup._debug("stopped %r", state_machine)

        # if we are starting up try again later
        if self._startup_flag:
            if _debug:
                StateMachineGroup._debug("    - still starting up")
            return

        all_success, some_failed = self.check_for_success()
        if all_success:
            self.success()
        elif some_failed:
            self.fail()
        else:
            if _debug:
                StateMachineGroup._debug("    - some still running")

    def check_for_success(self) -> Tuple[Optional[bool], Optional[bool]]:
        """Called after all of the machines have started, and each time a
        machine has stopped, to see if the entire group should be considered
        a success or fail."""
        if _debug:
            StateMachineGroup._debug("check_for_success")

        # accumulators
        all_success: Optional[bool] = True
        some_failed: Optional[bool] = False

        # check each machine
        for state_machine in self.state_machines:
            if state_machine.running:
                if _debug:
                    StateMachineGroup._debug("    - running: %r", state_machine)
                all_success = some_failed = None
                break

            # if there is no current state it hasn't started
            if not state_machine.current_state:
                if _debug:
                    StateMachineGroup._debug("    - not started: %r", state_machine)
                all_success = some_failed = None
                continue

            all_success = all_success and state_machine.current_state.is_success_state
            some_failed = some_failed or state_machine.current_state.is_fail_state

        if _debug:
            StateMachineGroup._debug("    - all_success: %r", all_success)
            StateMachineGroup._debug("    - some_failed: %r", some_failed)

        # return the results of the check
        return (all_success, some_failed)

    def halt(self) -> None:
        """Halts all of the running machines in the group."""
        if _debug:
            StateMachineGroup._debug("halt")

        # pass along to each machine
        for state_machine in self.state_machines:
            if state_machine.running:
                state_machine.halt()

    def success(self) -> None:
        """Called when all of the machines in the group have halted and they
        are all in a 'success' final state."""
        if _debug:
            StateMachineGroup._debug("success")

        self.is_running = False
        self.is_success_state = True

    def fail(self) -> None:
        """Called when all of the machines in the group have halted and at
        at least one of them is in a 'fail' final state."""
        if _debug:
            StateMachineGroup._debug("fail")
            for state_machine in self.state_machines:
                StateMachineGroup._debug("    - machine: %r", state_machine)
                for direction, pdu in state_machine.transaction_log:
                    StateMachineGroup._debug("        %s %s", direction, str(pdu))

        self.is_running = False
        self.is_fail_state = True


@bacpypes_debugging
class ClientStateMachine(Client, StateMachine):

    """
    ClientStateMachine
    ~~~~~~~~~~~~~~~~~~

    An instance of this class sits at the top of a stack.  PDU's that the
    state machine sends are sent down the stack and PDU's coming up the
    stack are fed as received PDU's.
    """

    _debug: Callable[..., None]

    def __init__(self, name="") -> None:
        if _debug:
            ClientStateMachine._debug("__init__")

        Client.__init__(self)
        StateMachine.__init__(self, name=name)

    async def send(self, pdu) -> None:
        if _debug:
            ClientStateMachine._debug("send(%s) %r", self.name, pdu)
        await self.request(pdu)

    async def confirmation(self, pdu) -> None:
        if _debug:
            ClientStateMachine._debug("confirmation(%s) %r", self.name, pdu)
        await self.receive(pdu)


@bacpypes_debugging
class ServerStateMachine(Server, StateMachine):

    """
    ServerStateMachine
    ~~~~~~~~~~~~~~~~~~

    An instance of this class sits at the bottom of a stack.  PDU's that the
    state machine sends are sent up the stack and PDU's coming down the
    stack are fed as received PDU's.
    """

    _debug: Callable[..., None]

    def __init__(self, name="") -> None:
        if _debug:
            ServerStateMachine._debug("__init__")

        Server.__init__(self)
        StateMachine.__init__(self, name=name)

    async def send(self, pdu) -> None:
        if _debug:
            ServerStateMachine._debug("send %r", pdu)
        await self.response(pdu)

    async def indication(self, pdu) -> None:
        if _debug:
            ServerStateMachine._debug("indication %r", pdu)
        await self.receive(pdu)


#
#   TrafficLog
#


class TrafficLog:
    traffic: List[Tuple[Any, ...]]

    def __init__(self) -> None:
        """Initialize with no traffic."""
        self.traffic = []

    def __call__(self, *args: Any) -> None:
        """Capture the current time and the arguments."""
        self.traffic.append((asyncio.get_event_loop().time(),) + args)

    def dump(self, handler_fn: Callable[..., None]) -> None:
        """Dump the traffic, pass the correct handler like SomeClass._debug"""
        for args in self.traffic:
            arg_format = "   %6.3f:"
            for arg in args[1:]:
                if hasattr(arg, "debug_contents"):
                    arg_format += " %r"
                else:
                    arg_format += " %s"
            handler_fn(arg_format, *args)
