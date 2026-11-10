#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC TLS helpers
--------------------------
"""

import ssl
import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.sc.tls import require_wss, harden_ssl_context, create_ssl_context

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestRequireWSS(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_wss_ok(self):
        # does not raise
        require_wss("wss://hub.example.org:47808/")
        require_wss("wss://10.0.0.1/path")

    def test_non_wss_rejected(self):
        for uri in ["ws://hub.example.org/", "https://hub/", "http://hub/", "hub"]:
            with self.assertRaises(ValueError):
                require_wss(uri)


@bacpypes_debugging
class TestSSLPolicy(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_harden_client(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        harden_ssl_context(context)
        assert context.minimum_version == ssl.TLSVersion.TLSv1_3
        assert context.check_hostname is False
        assert context.verify_mode == ssl.CERT_REQUIRED

    def test_harden_server(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        harden_ssl_context(context, server_side=True)
        assert context.minimum_version == ssl.TLSVersion.TLSv1_3
        assert context.check_hostname is False
        assert context.verify_mode == ssl.CERT_REQUIRED

    def test_strict_verification_disabled(self):
        # Clause YY.7.4 forbids extra checks; strict X.509 verification (which
        # rejects certificates missing an Authority Key Identifier) must be off
        if not hasattr(ssl, "VERIFY_X509_STRICT"):
            self.skipTest("VERIFY_X509_STRICT not available")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        harden_ssl_context(context)
        assert not (context.verify_flags & ssl.VERIFY_X509_STRICT)

    def test_missing_ca_file_raises(self):
        # a non-existent issuer certificate file must fail
        with self.assertRaises(Exception):
            create_ssl_context(
                "nonexistent-cert.pem",
                "nonexistent-key.pem",
                "nonexistent-ca.pem",
            )


if __name__ == "__main__":
    unittest.main()
