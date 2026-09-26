# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bind the worker only on a Tailscale address.

The listener is the Pi's Tailscale address. Unset, unspecified (0.0.0.0
and ::), LAN (RFC1918, link-local, and non-Tailscale ULA), loopback, and
every other non-Tailscale address are refused. Tailscale's IPv4 range is
the CGNAT block 100.64.0.0/10, which is not an RFC1918 LAN.
"""

import ipaddress

from colophon.limits import TAILSCALE_IPV4_CIDR, TAILSCALE_IPV6_CIDR

_TAILSCALE_V4 = ipaddress.ip_network(TAILSCALE_IPV4_CIDR)
_TAILSCALE_V6 = ipaddress.ip_network(TAILSCALE_IPV6_CIDR)
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
    if ip in _TAILSCALE_V4 or ip in _TAILSCALE_V6:
        return str(ip)
    if isinstance(ip, ipaddress.IPv4Address) and any(ip in net for net in _LAN_V4):
        raise BindError("lan")
    if isinstance(ip, ipaddress.IPv6Address) and (
        ip in _LINK_LOCAL_V6 or ip in _ULA_V6
    ):
        raise BindError("lan")
    if ip.is_loopback or ip.is_link_local or ip.is_private:
        raise BindError("lan")
    raise BindError("not_tailscale")
