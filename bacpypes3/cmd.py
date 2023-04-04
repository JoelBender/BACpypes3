#!/usr/bin/python

"""
Support for line-oriented command interpreters
"""

import sys
import shlex
import inspect
import traceback
import logging
import typing
from typing import Awaitable, Callable, Dict, List, Tuple, Any, Optional, Union

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import create_log_handlers, remove_log_handler, logging_handlers
from bacpypes3.comm import Server
from bacpypes3.console import ConsolePDU

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class CmdProfile:
    """
    Instances of this class are wrappers around the do_command() methods
    of a Cmd instance.
    """

    _debug: Callable[..., None]

    def __init__(self, cmd_fn: Callable[..., None]) -> None:
        if _debug:
            CmdProfile._debug("__init__ %r", cmd_fn)

        self.cmd_fn = cmd_fn
        self.arg_spec = inspect.getfullargspec(cmd_fn)
        if _debug:
            CmdProfile._debug("    - arg_spec: %r", self.arg_spec)

    def convert_arg(self, arg: str, raw_arg: str, arg_type: Any) -> Any:
        if _debug:
            CmdProfile._debug("convert_arg %r %r %r", arg, raw_arg, arg_type)

        # if there is no type annotation, just give it the string
        if (not arg_type) or (arg_type is str):
            return raw_arg

        # try to convert the value
        if isinstance(arg_type, typing._GenericAlias):  # type: ignore[attr-defined]
            if arg_type.__origin__ is Union:
                for arg_subtype in arg_type.__args__:
                    if _debug:
                        CmdProfile._debug("    - arg_subtype: %r", arg_subtype)
                    if arg_subtype is None.__class__:
                        continue

                    try:
                        arg_value = arg_subtype(raw_arg)
                        return arg_value
                    except Exception as err:
                        if _debug:
                            CmdProfile._debug("    - exception: %r", err)
                        pass
                else:
                    arg_type_names = [
                        arg.__name__
                        for arg in arg_type.__args__
                        if arg is not None.__class__
                    ]
                    if len(arg_type_names) > 1:
                        raise RuntimeError(
                            f"parameter {arg}: one of {', '.join(arg_type_names)} expected"
                        )
                    else:
                        raise RuntimeError(
                            f"parameter {arg}: {arg_type_names[0]} expected"
                        )
            else:
                raise RuntimeError(
                    "annotation type not supported: {arg_type.__origin__}"
                )
        else:
            try:
                arg_value = arg_type(raw_arg)
                return arg_value
            except Exception as err:
                raise RuntimeError(
                    f"parameter {arg}: {err}: {arg_type.__name__} expected"
                )

    def __call__(self, args: List[str]) -> Tuple[Any, Any, Any]:
        if _debug:
            CmdProfile._debug("__call__ %r", args)

        arg: Optional[str]

        # split the args up into regular and keyword arg lists
        raw_args: List[str] = []
        raw_kwargs = {}
        parms = raw_args
        for arg in args:
            if arg.startswith("--"):
                parms = []
                raw_kwargs[arg[2:]] = parms
            else:
                parms.append(arg)
        if _debug:
            CmdProfile._debug("    - raw_args: %r", raw_args)
            CmdProfile._debug("    - raw_kwargs: %r", raw_kwargs)

        # calculate the number of required parameters
        arg_len = len(self.arg_spec.args) - 1
        if not self.arg_spec.defaults:
            req_len = arg_len
        else:
            req_len = arg_len - len(self.arg_spec.defaults)

        # make a list of the command parameters, parsed according to the type
        cmd_args = []
        for arg in self.arg_spec.args[1:]:
            arg_type = self.arg_spec.annotations.get(arg, None)
            if _debug:
                CmdProfile._debug("    - arg, arg_type: %r, %r", arg, arg_type)

            if not raw_args:
                if req_len > 0:
                    raise RuntimeError("missing required parameter: {}".format(arg))
                else:
                    break
            req_len -= 1
            raw_arg = raw_args.pop(0)

            # if there is no type annotation, just give it the string
            if (not arg_type) or (arg_type is str):
                cmd_args.append(raw_arg)
                continue

            # try to convert the value
            arg_value = self.convert_arg(arg, raw_arg, arg_type)
            if _debug:
                CmdProfile._debug("    - arg_value: %r", arg_value)
            cmd_args.append(arg_value)

        # see if there is a dumping ground for the rest of the values
        arg = self.arg_spec.varargs
        if arg and raw_args:
            arg_type = self.arg_spec.annotations.get(arg, None)
            if _debug:
                CmdProfile._debug("    - arg, arg_type: %r, %r", arg, arg_type)

            if (not arg_type) or (arg_type is str):
                cmd_args.extend(raw_args)
            else:
                # try to convert the values
                for raw_arg in raw_args:
                    # try to convert the value
                    arg_value = self.convert_arg(arg, raw_arg, arg_type)
                    if _debug:
                        CmdProfile._debug("    - arg_value: %r", arg_value)
                    cmd_args.append(arg_value)
        elif raw_args:
            raise RuntimeError("too many parameters")

        # make a dictionary of kwargs (options)
        cmd_kwargs: Dict[str, Any] = {}

        # check to see if the ones provided are all supposed to be there
        if not self.arg_spec.varkw:
            for arg in raw_kwargs:
                if arg not in self.arg_spec.kwonlyargs:
                    raise RuntimeError(f"unrecognized option: {arg}")

        # check the options to make sure the ones that require a value have
        # been given one, and parsed if a type has been provided
        for arg in self.arg_spec.kwonlyargs or []:
            arg_type = self.arg_spec.annotations.get(arg, None)
            if _debug:
                CmdProfile._debug("    - arg, arg_type: %r, %r", arg, arg_type)

            if (not self.arg_spec.kwonlydefaults) or (
                arg not in self.arg_spec.kwonlydefaults
            ):
                if arg not in raw_kwargs:
                    raise RuntimeError(f"option {arg}: value required")
            else:
                if arg not in raw_kwargs:
                    continue

            # string pieces after the option
            raw_args = raw_kwargs.pop(arg)
            if (not arg_type) or (arg_type is str):
                cmd_kwargs[arg] = raw_args
            elif not raw_args:
                if arg_type is bool:
                    cmd_kwargs[arg] = True
                else:
                    raise RuntimeError(f"option {arg}: switches must be boolean")
            elif isinstance(
                arg_type, typing._GenericAlias  # type: ignore[attr-defined]
            ) and (arg_type.__origin__ is list):
                # make a list of the converted the values
                arg_values = []
                arg_type = arg_type.__args__[0]
                if _debug:
                    CmdProfile._debug("    - list of kwargs arg_type: %r", arg_type)

                for raw_arg in raw_args:
                    # try to convert the value
                    arg_value = self.convert_arg(arg, raw_arg, arg_type)
                    if _debug:
                        CmdProfile._debug("    - arg_value: %r", arg_value)
                    arg_values.append(arg_value)
                cmd_kwargs[arg] = arg_values
            elif len(raw_args) != 1:
                raise RuntimeError(f"option {arg}: too many values")
            else:
                raw_arg = raw_args[0]
                if arg_type is bool:
                    if raw_arg.lower() in ("true", "set"):
                        cmd_kwargs[arg] = True
                    elif raw_arg.lower() in ("false", "reset"):
                        cmd_kwargs[arg] = False
                    else:
                        raise RuntimeError(
                            f"option {arg}: invalid keyword: {raw_arg}, true/false or set/reset expected"
                        )
                else:
                    # try to convert the value
                    arg_value = self.convert_arg(arg, raw_arg, arg_type)
                    if _debug:
                        CmdProfile._debug("    - arg_value: %r", arg_value)
                    cmd_kwargs[arg] = arg_value

        # see if there is a dumping ground for the rest of the options
        arg = self.arg_spec.varkw
        if arg and raw_kwargs:
            if _debug:
                CmdProfile._debug("    - kwargs dumping ground")

            arg_type = self.arg_spec.annotations.get(arg, None)
            if _debug:
                CmdProfile._debug("    - arg, arg_type: %r, %r", arg, arg_type)

            if (not arg_type) or (arg_type is str):
                cmd_kwargs.update(raw_kwargs)
            elif arg_type is bool:
                # provide a default or convert the keyword
                for arg, raw_args in raw_kwargs.items():
                    if len(raw_args) == 0:
                        cmd_kwargs[arg] = True
                    elif len(raw_args) != 1:
                        raise RuntimeError(f"option {arg}: too many values")
                    else:
                        raw_arg = raw_args[0]
                        if raw_arg.lower() in ("true", "set"):
                            cmd_kwargs[arg] = True
                        elif raw_arg.lower() in ("false", "reset"):
                            cmd_kwargs[arg] = False
                        else:
                            raise RuntimeError(
                                f"option {arg}: invalid keyword: {raw_arg}, true/false or set/reset expected"
                            )
            else:
                # try to convert the values
                for arg, raw_args in raw_kwargs.items():
                    if len(raw_args) == 1:
                        # try to convert the value
                        arg_value = self.convert_arg(arg, raw_args[0], arg_type)
                        if _debug:
                            CmdProfile._debug("    - arg_value: %r", arg_value)
                        cmd_kwargs[arg] = arg_value
                    else:
                        # make a list of the converted the values
                        arg_values = []
                        for raw_arg in raw_args:
                            # try to convert the value
                            arg_value = self.convert_arg(arg, raw_arg, arg_type)
                            if _debug:
                                CmdProfile._debug("    - arg_value: %r", arg_value)
                            arg_values.append(arg_value)
                        cmd_kwargs[arg] = arg_values

        elif raw_kwargs:
            raise RuntimeError(f"unknown options: {', '.join(raw_kwargs)}")

        return (self.cmd_fn, cmd_args, cmd_kwargs)


@bacpypes_debugging
class Cmd(Server[ConsolePDU]):
    """
    Simple example server that echos the downstream strings as uppercase
    upstream strings.

    Method defined using the prefix `do_` will be executable from the command line.
    Docstring of those functions will be included in the help message if you call

        help command

    Calling help, will output all the available functions and print out the docstring
    of the class itself.

    """

    _debug: Callable[..., None]

    def __init__(self, sid: Optional[str] = None) -> None:
        if _debug:
            Cmd._debug("__init__ sid=%r", sid)

        self.cmd_profiles: Dict[str, CmdProfile] = {}

        # look for command that are methods called do_something
        for attr_name in dir(self):
            if not attr_name.startswith("do_"):
                continue

            cmd_fn = getattr(self, attr_name)
            if not inspect.ismethod(cmd_fn):
                continue
            cmd_name = attr_name[3:]
            self.cmd_profiles[cmd_name] = CmdProfile(cmd_fn)

        if _debug:
            Cmd._debug("    - cmd_profiles: %r", self.cmd_profiles)

    async def indication(self, pdu: ConsolePDU) -> None:
        if _debug:
            Cmd._debug("indication %r", pdu)
        if pdu is None:
            return

        # simple shell-like string split
        assert isinstance(pdu, str)
        split_result = shlex.split(pdu)
        if _debug:
            Cmd._debug("    - split_result: %r", split_result)
        if not split_result:
            return

        # first word is the command
        cmd = split_result.pop(0)
        cmd_profile = self.cmd_profiles.get(cmd, None)
        if not cmd_profile:
            await self.response("{}: command not found".format(cmd))
            return

        try:
            # build a function call from the command profile
            cmd_fn, cmd_args, cmd_kwargs = cmd_profile(split_result)
            response = cmd_fn(*cmd_args, **cmd_kwargs)
            if inspect.isawaitable(response):
                response = await response
        except Exception as err:
            if _debug:
                Cmd._debug("    - err: %r", err)
                Cmd._debug(
                    "    - stack: %r",
                    [
                        "%s:%s" % (filename.split("/")[-1], lineno)
                        for filename, lineno, _, _ in traceback.extract_stack()[-6:-1]
                    ],
                )
            await self.response(
                "{} error: {} | Error type : {}".format(cmd, err, type(err))
            )

    def do_help(self, cmd: str = "") -> None:
        """
        usage: help [ cmd ]
        """
        if _debug:
            Cmd._debug("do_help %r", cmd)

        if not cmd:
            class_doc = inspect.getdoc(self)
            if class_doc:
                print(class_doc + "\n")
            print("commands: " + ", ".join(self.cmd_profiles))
        elif cmd not in self.cmd_profiles:
            print(f"{cmd}: command not found")
        else:
            cmd_doc = inspect.getdoc(self.cmd_profiles[cmd].cmd_fn)
            if not cmd_doc:
                print(f"{cmd}: no help available")
            else:
                print(cmd_doc)

    def do_exit(self, status: int = 0) -> Awaitable[None]:
        """
        usage: exit [ status ]
        """
        if _debug:
            Cmd._debug("do_exit %r %r", status, self)

        return self.response(status)


@bacpypes_debugging
class CmdDebugging:
    _debug: Callable[..., None]

    """
    This is a Cmd mix-in class to add debugging commands.
    """

    def do_loggers(self) -> None:
        """
        usage: loggers
        """
        if _debug:
            CmdDebugging._debug("do_loggers")
        loggers = sorted(logging.Logger.manager.loggerDict.items())  # type: ignore[attr-defined]
        for logger_name, logger_ref in loggers:
            if logger_ref in logging_handlers:
                sys.stdout.write(f"* {logger_name}\n")
            else:
                sys.stdout.write(f"  {logger_name}\n")

    def do_bugin(self, *loggers: str, color: Optional[int] = None) -> None:
        """
        usage: bugin [LOGGER ...] [--color [int]]
        """
        if _debug:
            CmdDebugging._debug("do_bugin %r color=%r", loggers, color)
        create_log_handlers(loggers, color)

    def do_bugout(self, *loggers: str) -> None:
        """
        usage: bugout [LOGGER ...]
        """
        if _debug:
            CmdDebugging._debug("do_bugout %r", loggers)
        for logger in loggers:
            remove_log_handler(logger)
