#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Services Supported
-----------------------

Application.get_services_supported() sets the Protocol_Services_Supported
bits for the services the application has helper methods for.  Confirmed and
unconfirmed service choices share numbers (I-Am and AcknowledgeAlarm are
both 0), so each kind has to be translated by its own enumeration.
"""

import pytest

from bacpypes3.apdu import (
    ConfirmedServiceChoice,
    UnconfirmedServiceChoice,
    confirmed_request_types,
    unconfirmed_request_types,
)
from bacpypes3.app import Application
from bacpypes3.basetypes import ServicesSupported
from bacpypes3.debugging import ModuleLogger

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# services removed from the standard, they no longer have a bit
REMOVED = {"authenticate", "readPropertyConditional", "requestKey"}


def bits_set(services_supported):
    return {
        name
        for name, bit in services_supported._bitstring_names.items()
        if services_supported[bit]
    }


def test_default_application():
    app = Application()
    expected = set()
    for service_types, service_choice_class in (
        (confirmed_request_types, ConfirmedServiceChoice),
        (unconfirmed_request_types, UnconfirmedServiceChoice),
    ):
        for service_choice, service_request_class in service_types.items():
            if hasattr(app, "do_" + service_request_class.__name__):
                expected.add(service_choice_class(service_choice).asn1)

    bits = bits_set(app.get_services_supported())
    assert bits == expected

    # unconfirmed services set their own bits
    assert {"i-am", "who-is", "who-has", "i-have"} <= bits

    # and not the confirmed services with the same numbers
    assert not ({"acknowledge-alarm", "atomic-write-file", "add-list-element"} & bits)


@pytest.mark.parametrize(
    "service_types, service_choice_class",
    [
        (confirmed_request_types, ConfirmedServiceChoice),
        (unconfirmed_request_types, UnconfirmedServiceChoice),
    ],
)
def test_every_service_has_a_bit(service_types, service_choice_class):
    """The service choice attribute names match the bit names."""
    for service_choice in service_types:
        attr = service_choice_class(service_choice).attr
        if attr in REMOVED:
            assert not hasattr(ServicesSupported, attr)
        else:
            assert hasattr(ServicesSupported, attr), attr


def test_removed_service_helper():
    """A helper for a removed service does not have a bit to set."""

    class OldApplication(Application):
        async def do_AuthenticateRequest(self, apdu):
            pass

    bits = bits_set(OldApplication().get_services_supported())
    assert "authenticate" not in bits
    assert "who-is" in bits
