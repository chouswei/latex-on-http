# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bind the worker only to one configured unicast address.

Unset, unspecified (0.0.0.0 and ::), loopback, link-local, multicast, and
LAN addresses are refused. The address itself comes from the environment
(COLOPHON_BIND_ADDRESS). Hostnames are refused.
"""

import ipaddress


_LAN_V4 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)
_ULA_V6 = ipaddress.ip_network("fc00::/7")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")


class BindError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _is_lan(ip):
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _LAN_V4)
    if isinstance(ip, ipaddress.IPv6Address):
        return ip in _LINK_LOCAL_V6 or ip in _ULA_V6
    return False


def validate_bind_address(address):
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
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or _is_lan(ip):
        raise BindError("lan")
    return str(ip)
