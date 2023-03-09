#!/usr/bin/python

"""
Console
"""

import sys
import signal
import asyncio
import os
import threading
import ctypes

from typing import TYPE_CHECKING, Callable, Optional, Union

from .debugging import bacpypes_debugging, ModuleLogger
from .comm import Client

# readline is used for history files
try:
    import readline
except ImportError:
    readline = None  # type: ignore

# some debugging
_debug = 0
_log = ModuleLogger(globals())


ConsolePDU = Union[int, str, None]
if TYPE_CHECKING:
    ConsoleQueue = asyncio.Queue[ConsolePDU]
else:
    ConsoleQueue = asyncio.Queue


@bacpypes_debugging
class Console(Client[ConsolePDU]):

    """
    A Console object sits at the top of a stack reading input from the
    interactive console (a.k.a. terminal), pipe input, or file input, and sends
    each string down the stack.  Strings coming up the stack are written to
    stdout.

    The 'fini' event is set when there is no more input, a.k.a. EOF.
    """

    _debug: Callable[..., None]

    fini: asyncio.Event
    exit_status: int

    def __init__(
        self,
        prompt: Optional[str] = "> ",
        history_file: Optional[str] = sys.argv[0] + ".history",
        cid: Optional[str] = None,
    ) -> None:
        if _debug:
            Console._debug("__init__ %r %r %r", prompt, history_file, cid)
        Client.__init__(self, cid=cid)

        # if this not interactive, disable the prompt
        self.interactive = sys.__stdin__.isatty()
        if not self.interactive:
            prompt = ""

        loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()

        self.loop = loop
        self.prompt = prompt
        self.history_file = history_file
        self.exit_status = 0

        # end-of-file event
        self.fini = asyncio.Event()
        self.console_task = asyncio.ensure_future(self.console_supervisor())

        # add a Ctrl-C signal handler, or something that keeps the loop awake
        # for Windows because it doesn't have signals
        try:
            loop.add_signal_handler(signal.SIGINT, self.console_task.cancel)
        except NotImplementedError:

            def _wakeup() -> None:
                loop.call_later(0.1, _wakeup)

            loop.call_later(0.1, _wakeup)

        # blocking input() runs in a separate thread
        self.console_thread: Optional[threading.Thread] = None

    def preloop(self) -> None:
        """Initialization before prompting user for commands."""
        try:
            if readline and self.history_file:
                readline.read_history_file(self.history_file)
        except Exception as err:
            if not isinstance(err, IOError):
                sys.stdout.write("history error: %s\n" % err)

    def postloop(self) -> None:
        """Take care of any unfinished business."""
        try:
            if readline and self.history_file:
                readline.write_history_file(self.history_file)
        except Exception as err:
            if not isinstance(err, IOError):
                sys.stderr.write("history error: %s\n" % err)

    def kill(self) -> None:
        """
        Send a SystemExit exception to the console input thread.
        """
        if self.console_thread and self.console_thread.is_alive():
            console_thread_ident = ctypes.c_long(self.console_thread.ident)  # type: ignore
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                console_thread_ident, ctypes.py_object(SystemExit)
            )
            if res == 0:
                raise ValueError("invalid thread id")
            elif res != 1:
                # "if it returns a number greater than one, you're in trouble,
                # and you should call it again with exc=NULL to revert the effect"
                ctypes.pythonapi.PyThreadState_SetAsyncExc(console_thread_ident, None)
                raise SystemError("PyThreadState_SetAsyncExc failed")

            # reset the terminal
            os.system("stty sane") if "nt" not in os.name else ...

    def console_input(self, fini: asyncio.Event, prompt: str) -> None:
        """
        This method uses the input() blocking function to read a line of text
        from stdin and supports readline for interactive sessions.  It runs in
        its own thread to keep the main event loop alive.
        """
        try:
            while True:
                line = input(prompt)
                if line is None:
                    break

                # get a future that will run in the main thread
                future = asyncio.run_coroutine_threadsafe(self.request(line), self.loop)

                # wait for it to complete
                future.result()

        except EOFError:
            if _debug:
                Console._debug("console_input exception: EOFError")
        except SystemExit:
            if _debug:
                Console._debug("console_input exception: SystemExit")

        # tell the console loop this is finished
        self.loop.call_soon_threadsafe(fini.set)

    async def console_supervisor(self) -> None:
        """
        This supervisory function calls preloop to load up the history, starts
        the console thread and wait for it to complete, sends an EOF message
        down the stack, saves the history, and sets the fini event flag.
        """
        # create an event for console being finished
        console_fini = asyncio.Event()

        # call the blocking function in another thread
        self.console_thread = threading.Thread(
            target=self.console_input, args=(console_fini, self.prompt)
        )

        # running as a daemon so it doesn't block the main thread on exit
        self.console_thread.daemon = True

        # load up the history
        self.preloop()

        # start the thread
        self.console_thread.start()

        try:
            # wait for the thread to finish
            await console_fini.wait()
        except asyncio.CancelledError:
            if _debug:
                Console._debug("console_task canceled")
        except Exception as err:
            if _debug:
                Console._debug("console_loop exception: {!r}".format(err))

        # if the console thread is running, send it a SystemExit exception
        if self.console_thread.is_alive():
            self.kill()

        # send a None down the stack as an EOF message
        await self.request(None)

        # save the history
        self.postloop()

        # we're all done
        self.fini.set()

    async def confirmation(self, pdu: ConsolePDU) -> None:
        """
        Upstream messages are strings to send to stdout, or integer status
        codes to shutdown the console down.  It is the responsibility of the
        main() function to call sys.exit() with the exit status code when it is
        appropriate.
        """
        if _debug:
            Console._debug("confirmation {!r}".format(pdu))

        # check for a status code
        if isinstance(pdu, int):
            self.exit_status = pdu
            self.kill()
            return

        # print the string
        print(pdu)
