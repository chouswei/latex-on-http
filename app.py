# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Colophon worker entry.

The process binds only to COLOPHON_BIND_ADDRESS inside
COLOPHON_BIND_ALLOWED_CIDR. It refuses an unset address, an unset CIDR,
0.0.0.0, ::, loopback, link-local, multicast, RFC1918, and any address
with is_global true.
"""

from colophon.cli import main_worker

if __name__ == "__main__":
    raise SystemExit(main_worker())
