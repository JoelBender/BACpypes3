#!/usr/bin/python

"""
argparse
"""

import os
import sys
import asyncio
import shlex
import json
import logging
import logging.handlers
import argparse

from configparser import ConfigParser as _ConfigParser
from typing import Any, Dict, Callable, Iterable, List, Optional, Sequence, Union, cast

from .settings import settings, Settings, os_settings, dict_settings
from .debugging import (
    bacpypes_debugging,
    ModuleLogger,
    module_loggers,
    LoggingFormatter,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# keep track of the logging handlers
logging_handlers: Dict[logging.Logger, List[logging.StreamHandler]] = {}


@bacpypes_debugging
def create_log_handler(
    logger: Union[str, logging.Logger] = "",
    handler: Optional[logging.StreamHandler] = None,
    level: int = logging.DEBUG,
    color: Optional[int] = None,
) -> None:
    """
    Add a stream handler with our custom formatter to a logger.
    """
    global logging_handlers
    _fn_debug = cast(Callable[..., None], create_log_handler._debug)  # type: ignore[attr-defined]
    if _debug:
        _fn_debug("create_log_handler %r ...", logger)

    logger_ref: logging.Logger

    if isinstance(logger, logging.Logger):
        logger_ref = logger

    elif isinstance(logger, str):
        # check for root
        if not logger:
            logger_ref = _log

        # check for a valid logger name
        elif logger not in logging.Logger.manager.loggerDict:  # type: ignore
            raise RuntimeError("not a valid logger name: %r" % (logger,))

        # get the logger
        logger_ref = logging.getLogger(logger)

    else:
        raise RuntimeError("not a valid logger reference: %r" % (logger,))
    if _debug:
        _fn_debug("    - logger_ref: %r", logger_ref)

    # if this is a module level logger, tell the module
    if logger_ref in module_loggers:
        if _debug:
            _fn_debug("    - in module loggers")
        module_loggers[logger_ref]["_debug"] += 1
    elif logger_ref.parent in module_loggers:
        if _debug:
            _fn_debug("    - parent in module loggers")
        module_loggers[logger_ref.parent]["_debug"] += 1  # type: ignore

    # make a handler if one wasn't provided
    if not handler:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        if _debug:
            _fn_debug("    - new handler: %r", handler)

    # use our formatter
    handler.setFormatter(LoggingFormatter(color))

    # add it to the logger
    logger_ref.addHandler(handler)
    if logger_ref not in logging_handlers:
        logging_handlers[logger_ref] = [handler]
    else:
        logging_handlers[logger_ref].append(handler)

    # make sure the logger has at least this level
    logger_ref.setLevel(level)


@bacpypes_debugging
def remove_log_handler(
    logger: Union[str, logging.Logger] = "",
    handler: Optional[logging.StreamHandler] = None,
) -> None:
    """
    Remove the stream handlers from a logger.
    """
    global logging_handlers
    _fn_debug = cast(Callable[..., None], create_log_handler._debug)  # type: ignore[attr-defined]
    if _debug:
        _fn_debug("remove_log_handlers %r ...", logger)

    logger_ref: logging.Logger

    if isinstance(logger, logging.Logger):
        logger_ref = logger

    elif isinstance(logger, str):
        # check for root
        if not logger:
            logger_ref = _log

        # check for a valid logger name
        elif logger not in logging.Logger.manager.loggerDict:  # type: ignore
            raise RuntimeError("not a valid logger name: %r" % (logger,))

        # get the logger
        logger_ref = logging.getLogger(logger)

    else:
        raise RuntimeError("not a valid logger reference: %r" % (logger,))
    if _debug:
        _fn_debug("    - logger_ref: %r", logger_ref)

    # see if there is a handler for this logger
    if (logger_ref not in logging_handlers) or (not logging_handlers[logger_ref]):
        raise RuntimeError(f"no logging handler(s): {logger}")

    # if this is a module level logger, tell the module
    if logger_ref in module_loggers:
        if _debug:
            _fn_debug("    - in module loggers")
        module_loggers[logger_ref]["_debug"] -= 1
    elif logger_ref.parent in module_loggers:
        if _debug:
            _fn_debug("    - parent in module loggers")
        module_loggers[logger_ref.parent]["_debug"] -= 1  # type: ignore

    # pick up the first handler if one wasn't provided
    if not handler:
        handler = logging_handlers[logger_ref][0]

    # remove it from the logger
    logger_ref.removeHandler(handler)
    logging_handlers[logger_ref].remove(handler)
    if not logging_handlers[logger_ref]:
        del logging_handlers[logger_ref]


@bacpypes_debugging
def create_log_handlers(
    loggers: Iterable[str], use_color: Union[bool, int, None] = None
) -> None:
    if _debug:
        create_log_handlers._debug(  # type: ignore[attr-defined]
            "create_log_handlers %r %r", loggers, use_color
        )

    # keep track of which files are going to be used
    file_handlers: Dict[str, logging.StreamHandler] = {}

    # loop through the bug list
    for i, logger_name in enumerate(loggers):
        # turn on asyncio debugging
        if logger_name == "asyncio":
            asyncio.get_event_loop().set_debug(True)

        color: Optional[int]
        if isinstance(use_color, bool):
            color = (i % 6) + 2 if use_color else None
        elif isinstance(use_color, int):
            color = use_color
        else:
            color = None

        debug_specs = logger_name.split(":")
        if (len(debug_specs) == 1) and (not settings.debug_file):
            create_log_handler(logger_name, color=color)
        else:
            # the debugger name is just the first component
            logger_name = debug_specs.pop(0)

            if debug_specs:
                file_name = debug_specs.pop(0)
            else:
                file_name = settings.debug_file

            # if the file is already being used, use the already created handler
            if file_name in file_handlers:
                handler = file_handlers[file_name]
            else:
                if debug_specs:
                    maxBytes = int(debug_specs.pop(0))
                else:
                    maxBytes = settings.max_bytes
                if debug_specs:
                    backupCount = int(debug_specs.pop(0))
                else:
                    backupCount = settings.backup_count

                # create a handler
                handler = logging.handlers.RotatingFileHandler(
                    file_name,
                    maxBytes=maxBytes,
                    backupCount=backupCount,
                )
                handler.setLevel(logging.DEBUG)

                # save it for more than one instance
                file_handlers[file_name] = handler

            # use this handler, no color
            create_log_handler(logger_name, handler=handler)


@bacpypes_debugging
class ArgumentParser(argparse.ArgumentParser):

    """
    ArgumentParser extends the one with the same name from the argparse module
    by adding the common command line arguments found in BACpypes applications.

        --loggers                       list the debugging logger names
        --debug [DEBUG [DEBUG ...]]     attach a handler to loggers
        --color                         debug in color
        --route-aware                   turn on route aware
    """

    _debug: Callable[..., None]

    def __init__(self, **kwargs: Any):
        """Follow normal initialization and add BACpypes arguments."""
        if _debug:
            ArgumentParser._debug("__init__")
        argparse.ArgumentParser.__init__(self, **kwargs)

        # load settings from the environment
        self.update_os_env()
        if _debug:
            ArgumentParser._debug("    - os environment")

        # add a way to get a list of the debugging hooks
        self.add_argument(
            "--loggers",
            help="list the debugging logger names",
            action="store_true",
        )

        # add a way to attach debuggers
        self.add_argument(
            "--debug",
            nargs="*",
            help="add a log handler to each debugging logger",
        )

        # add a way to turn on color debugging
        self.add_argument(
            "--color",
            help="turn on color debugging",
            action="store_true",
            default=None,
        )

        # add a way to turn on route aware
        self.add_argument(
            "--route-aware",
            help="turn on route aware",
            action="store_true",
            default=None,
        )

    def update_os_env(self) -> None:
        """Update the settings with values from the environment, if provided."""
        if _debug:
            ArgumentParser._debug("update_os_env")

        # use settings function
        os_settings()
        if _debug:
            ArgumentParser._debug("    - settings: %r", settings)

    # TODO: parse_args() is overloaded, namespace can be a keyword argument
    def parse_args(  # type: ignore[override]
        self,
        args: Optional[Sequence[str]] = None,
        namespace: Optional[argparse.Namespace] = None,
    ) -> argparse.Namespace:
        """Parse the arguments as usual, then add default processing."""
        if _debug:
            ArgumentParser._debug("parse_args")

        # check for environment args, used for testing
        if not args:
            os_args: str = os.getenv("BACPYPES_ARGS", "")
            if os_args:
                args = shlex.split(os_args)
        if _debug:
            ArgumentParser._debug("    - args: %r", args)

        # pass along to the parent class
        result_args = argparse.ArgumentParser.parse_args(self, args, namespace)

        # update settings
        self.expand_args(result_args)
        if _debug:
            ArgumentParser._debug("    - args expanded")

        # add debugging loggers
        self.interpret_debugging(result_args)
        if _debug:
            ArgumentParser._debug("    - interpreted debugging")

        # return what was parsed and expanded
        return result_args

    def expand_args(self, result_args: argparse.Namespace) -> None:
        """Expand the arguments and/or update the settings."""
        if _debug:
            ArgumentParser._debug("expand_args %r", result_args)

        # check for debug
        if result_args.debug is None:
            if _debug:
                ArgumentParser._debug("    - debug not specified")
        elif not result_args.debug:
            if _debug:
                ArgumentParser._debug("    - debug with no args")
            settings.debug.append("__main__")
        else:
            if _debug:
                ArgumentParser._debug("    - debug: %r", result_args.debug)
            settings.debug.extend(result_args.debug)

        # check for color
        if result_args.color is None:
            if _debug:
                ArgumentParser._debug("    - color not specified")
        else:
            if _debug:
                ArgumentParser._debug("    - color: %r", result_args.color)
            settings.color = result_args.color

        # check for route aware
        if result_args.route_aware is None:
            if _debug:
                ArgumentParser._debug("    - route_aware not specified")
        else:
            if _debug:
                ArgumentParser._debug("    - route_aware: %r", result_args.route_aware)
            settings.route_aware = result_args.route_aware

    def interpret_debugging(self, result_args: argparse.Namespace) -> None:
        """Take the result of parsing the args and interpret them."""
        if _debug:
            ArgumentParser._debug("interpret_debugging %r", result_args)
            ArgumentParser._debug("    - settings: %r", settings)

        # check to dump labels
        if result_args.loggers:
            loggers = sorted(logging.Logger.manager.loggerDict.keys())  # type: ignore[attr-defined]
            for loggerName in loggers:
                sys.stdout.write(loggerName + "\n")
            sys.exit(0)

        # pass off to the function that can also be called by Cmd
        create_log_handlers(settings.debug, settings.color)


@bacpypes_debugging
class SimpleArgumentParser(ArgumentParser):

    """
    SimpleArgumentParser extends the ArgumentParser with the arguments for
    building simple applications.
    """

    _debug: Callable[..., None]

    def __init__(self, **kwargs: Any):
        """Follow normal initialization and add BACpypes arguments."""
        if _debug:
            SimpleArgumentParser._debug("__init__")
        ArgumentParser.__init__(self, **kwargs)

        self.add_argument(
            "--name",
            type=str,
            help="device name",
            default=os.getenv("BACPYPES_DEVICE_NAME") or "Excelsior",
        )
        self.add_argument(
            "--instance",
            type=int,
            help="device object instance number, a.k.a., device identifier",
            default=int(os.getenv("BACPYPES_DEVICE_INSTANCE") or 999),
        )
        self.add_argument(
            "--network",
            type=int,
            help="local network number",
            default=int(os.getenv("BACPYPES_NETWORK") or 0),
        )
        self.add_argument(
            "--address",
            type=str,
            help="local network address",
            default=os.getenv("BACPYPES_DEVICE_ADDRESS"),
        )
        self.add_argument(
            "--vendoridentifier",
            type=int,
            help="vendor identifier",
            default=int(os.getenv("BACPYPES_VENDOR_IDENTIFIER") or 999),
        )
        self.add_argument(
            "--foreign",
            type=str,
            help="BBMD address to register as a foreign device",
            default=os.getenv("BACPYPES_FOREIGN_BBMD"),
        )
        self.add_argument(
            "--ttl",
            type=int,
            help="foreign device subscription time-to-live",
            default=os.getenv("BACPYPES_FOREIGN_TTL", 30),
        )
        self.add_argument(
            "--bbmd",
            nargs="*",
            help="BDT addresses as a BBMD",
            default=os.getenv("BACPYPES_BBMD_BDT"),
        )

    def expand_args(self, result_args: argparse.Namespace) -> None:
        """Expand the arguments and/or update the settings."""
        if _debug:
            SimpleArgumentParser._debug("expand_args %r", result_args)

        # do some error checking
        if (result_args.foreign is not None) and (result_args.bbmd is not None):
            raise RuntimeError("cannot be both a foreign device and a BBMD")

        # call the parent to continue expanding
        ArgumentParser.expand_args(self, result_args)


@bacpypes_debugging
class INIArgumentParser(ArgumentParser):

    """
    INIArgumentParser extends the ArgumentParser with the functionality to
    read in an INI configuration file.  The contents of the [BACpypes] section
    will be in the settings.ini attribute.

        --ini INI       provide a separate INI file
    """

    _debug: Callable[..., None]

    def __init__(self, **kwargs: Any):
        """Follow normal initialization and add BACpypes arguments."""
        if _debug:
            INIArgumentParser._debug("__init__")
        ArgumentParser.__init__(self, **kwargs)

        # add a way to read a configuration file
        self.add_argument(
            "--ini",
            help="device object configuration file",
            default=settings.ini,
        )

    def update_os_env(self) -> None:
        """Update the settings with values from the environment, if provided."""
        if _debug:
            INIArgumentParser._debug("update_os_env")

        # start with normal env vars
        ArgumentParser.update_os_env(self)

        # provide a default value for the INI file name
        settings["ini"] = os.getenv("BACPYPES_INI", "BACpypes.ini")

    def expand_args(self, result_args: argparse.Namespace) -> None:
        """Take the result of parsing the args and interpret them."""
        if _debug:
            INIArgumentParser._debug("expand_args %r", result_args)

        settings["ini"] = result_args.ini

        # read in the configuration file
        config = _ConfigParser()
        config.read(result_args.ini)
        if _debug:
            _log.debug("    - config: %r", config)

        # check for BACpypes section
        if not config.has_section("BACpypes"):
            raise RuntimeError("INI file with BACpypes section required")

        # convert the contents to an object
        ini_obj = dict(config.items("BACpypes"))
        dict_settings(**ini_obj)
        if _debug:
            _log.debug("    - ini_obj: %r", ini_obj)

        # continue with normal expansion
        ArgumentParser.expand_args(self, result_args)

        # stuff the ini contents into settings
        settings.config = ini_obj


@bacpypes_debugging
class JSONArgumentParser(ArgumentParser):

    """
    JSONArgumentParser extends the ArgumentParser with the functionality to
    read in a JSON configuration file.  The contents of the "BACpypes" element
    will be in the settings.json attribute.

        --json JSON    provide a separate JSON file
    """

    _debug: Callable[..., None]

    def __init__(self, **kwargs: Any):
        """Follow normal initialization and add BACpypes arguments."""
        if _debug:
            JSONArgumentParser._debug("__init__")
        ArgumentParser.__init__(self, **kwargs)

        # add a way to read a configuration file
        self.add_argument(
            "--json",
            help="configuration file",
            default=settings.json,
        )

    def update_os_env(self) -> None:
        """Update the settings with values from the environment, if provided."""
        if _debug:
            JSONArgumentParser._debug("update_os_env")

        # start with normal env vars
        ArgumentParser.update_os_env(self)

        # provide a default value for the JSON file name
        settings["json"] = os.getenv("BACPYPES_JSON", "BACpypes.json")

    def expand_args(self, result_args: argparse.Namespace) -> None:
        """Take the result of parsing the args and interpret them."""
        if _debug:
            JSONArgumentParser._debug("expand_args %r", result_args)

        # read in the settings file
        try:
            settings["json"] = result_args.json
            with open(result_args.json) as json_file:
                json_obj = json.load(json_file, object_hook=Settings)
                if _debug:
                    JSONArgumentParser._debug("    - json_obj: %r", json_obj)
        except FileNotFoundError:
            raise RuntimeError("settings file not found: %r\n" % (settings.json,))

        # look for settings
        if "BACpypes" in json_obj:
            dict_settings(**json_obj["BACpypes"])
            if _debug:
                JSONArgumentParser._debug("    - settings: %r", settings)

        # continue with normal expansion
        ArgumentParser.expand_args(self, result_args)

        # stuff the ini contents into settings
        settings.config = json_obj


@bacpypes_debugging
class YAMLArgumentParser(ArgumentParser):

    """
    YAMLArgumentParser extends the ArgumentParser with the functionality to
    read in a YAML configuration file.  The contents of the "BACpypes" element
    will be in the settings.yaml attribute.

        --yaml YAML    provide a separate YAML file
    """

    _debug: Callable[..., None]

    def __init__(self, **kwargs: Any):
        """Follow normal initialization and add BACpypes arguments."""
        if _debug:
            YAMLArgumentParser._debug("__init__")
        ArgumentParser.__init__(self, **kwargs)

        # add a way to read a configuration file
        self.add_argument(
            "--yaml",
            help="configuration file",
            default=settings.yaml,
        )

    def update_os_env(self) -> None:
        """Update the settings with values from the environment, if provided."""
        if _debug:
            YAMLArgumentParser._debug("update_os_env")

        # start with normal env vars
        ArgumentParser.update_os_env(self)

        # provide a default value for the YAML file name
        settings["yaml"] = os.getenv("BACPYPES_YAML", "BACpypes.yml")

    def expand_args(self, result_args: argparse.Namespace) -> None:
        """Take the result of parsing the args and interpret them."""
        if _debug:
            YAMLArgumentParser._debug("expand_args %r", result_args)

        # read in the settings file
        try:
            import yaml  # type: ignore[import]

            with open(result_args.yaml) as yaml_file:
                yaml_obj = yaml.safe_load(yaml_file)
                if _debug:
                    YAMLArgumentParser._debug("    - yaml_obj: %r", yaml_obj)
        except FileNotFoundError:
            raise RuntimeError("settings file not found: %r\n" % (settings.yaml,))

        # look for settings
        if "BACpypes" in yaml_obj:
            dict_settings(**yaml_obj["BACpypes"])
            if _debug:
                YAMLArgumentParser._debug("    - settings: %r", settings)

        # continue with normal expansion
        ArgumentParser.expand_args(self, result_args)

        # stuff the ini contents into settings
        settings.config = yaml_obj
