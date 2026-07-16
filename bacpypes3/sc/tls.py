#!/usr/bin/python

"""
BACnet Secure Connect - Transport Layer Security

BACnet/SC only permits TLS-secured ("wss") WebSocket connections and requires
mutual TLS authentication using operational credentials (see Annex AB /
Clause YY.7.4).  This module builds the SSL contexts used by the hub connector
and, later, the hub function.

For initial bring-up the operational credentials are supplied as PEM file paths
(operational certificate, private key, and the accepted issuer/CA
certificates).  Modelling the credentials as BACnet File objects
(Operational_Certificate_File, Issuer_Certificate_Files,
Certificate_Signing_Request_File) is deferred.
"""

from __future__ import annotations

import ssl
from typing import Callable
from urllib.parse import urlparse

from ..debugging import ModuleLogger, bacpypes_debugging

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# the only permitted URI scheme for BACnet/SC connections
WSS_SCHEME = "wss"


@bacpypes_debugging
def require_wss(uri: str) -> None:
    """Raise a ValueError if the URI does not use the secure 'wss' scheme.

    BACnet/SC only permits TLS-secured WebSocket connections; a malformed URI
    or any scheme other than 'wss' is not supported (Clause YY.5.4, YY.7.2).
    """
    if _debug:
        require_wss._debug("require_wss %r", uri)

    scheme = urlparse(uri).scheme
    if scheme != WSS_SCHEME:
        raise ValueError(
            f"BACnet/SC requires the {WSS_SCHEME!r} scheme, got {scheme!r}: {uri!r}"
        )


@bacpypes_debugging
def harden_ssl_context(
    context: ssl.SSLContext, *, server_side: bool = False
) -> ssl.SSLContext:
    """Apply the BACnet/SC TLS policy to an SSL context (Clause YY.7.4).

    TLS 1.3 is required and mutual authentication is enforced.  Per the
    standard no hostname/subject checks are performed by default, only that the
    peer's operational certificate is valid and signed by a configured CA.
    """
    if _debug:
        harden_ssl_context._debug(
            "harden_ssl_context %r server_side=%r", context, server_side
        )

    # TLS 1.3 is required
    context.minimum_version = ssl.TLSVersion.TLSv1_3

    # mutual authentication, but no hostname/subject matching by default
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED

    # Clause YY.7.4 requires exactly four checks (well-formed, in validity
    # period, not revoked if known, signed by a configured CA) and states that
    # "no additional checks beyond the above shall be performed by default".
    # Newer OpenSSL/Python enable strict X.509 verification in the default
    # context (which, for example, rejects certificates lacking an Authority
    # Key Identifier); that harms interoperability, so it is disabled here.
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    return context


@bacpypes_debugging
def create_ssl_context(
    operational_certificate: str,
    private_key: str,
    issuer_certificates: str,
    *,
    server_side: bool = False,
) -> ssl.SSLContext:
    """Build an SSL context for a BACnet/SC connection from PEM files.

    :param operational_certificate: path to this node's operational certificate
    :param private_key: path to the matching private key
    :param issuer_certificates: path to the accepted issuer/CA certificate(s)
    :param server_side: build a context for accepting connections (hub side)
    """
    if _debug:
        create_ssl_context._debug(
            "create_ssl_context %r %r %r server_side=%r",
            operational_certificate,
            private_key,
            issuer_certificates,
            server_side,
        )

    purpose = ssl.Purpose.CLIENT_AUTH if server_side else ssl.Purpose.SERVER_AUTH
    context = ssl.create_default_context(purpose=purpose, cafile=issuer_certificates)

    harden_ssl_context(context, server_side=server_side)

    # this node's operational certificate and matching private key
    context.load_cert_chain(certfile=operational_certificate, keyfile=private_key)

    return context
