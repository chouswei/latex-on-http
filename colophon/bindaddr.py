# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bind the worker only inside an allowed overlay CIDR.

ENDLEAF_BIND_ADDRESS must be inside ENDLEAF_BIND_ALLOWED_CIDR.
``load_config`` still accepts the COLOPHON_* names and logs a deprecation
line. An unset CIDR is refused. Addresses with ``ipaddress`` ``is_global``
true are refused,
as are unspecified, loopback, link-local, multicast, and RFC1918 LAN
addresses, even when the CIDR would include them. A unique-local address
is allowed only when it falls inside the configured CIDR. Common overlay
examples are 100.64.0.0/10 and fd7a:115c:a1e0::/48. Hostnames are refused.
"""

import ipaddress

_RFC1918 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


class BindError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _is_rfc1918(ip):
    if not isinstance(ip, ipaddress.IPv4Address):
        return False
    return any(ip in net for net in _RFC1918)


def _parse_cidr(allowed_cidr):
    if allowed_cidr is None or str(allowed_cidr).strip() == "":
        raise BindError("cidr_unset")
    text = str(allowed_cidr).strip()
    try:
        return ipaddress.ip_network(text, strict=True)
    except ValueError as exc:
        raise BindError("cidr_invalid") from exc


def _in_network(ip, network):
    try:
        return ip in network
    except TypeError:
        return False


def validate_bind_address(address, allowed_cidr):
    """Return the normalised address, or raise ``BindError``."""
    if address is None or str(address).strip() == "":
        raise BindError("unset")
    text = str(address).strip()
    if "%" in text:
        raise BindError("invalid")
    try:
        ip = ipaddress.ip_address(text)
    except ValueError as exc:
        raise BindError("invalid") from exc
    if ip.is_unspecified:
        raise BindError("unspecified")
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or _is_rfc1918(ip):
        raise BindError("lan")
    if ip.is_global:
        raise BindError("global")
    network = _parse_cidr(allowed_cidr)
    if not _in_network(ip, network):
        raise BindError("cidr")
    return str(ip)
