# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF_* settings. COLOPHON_* is still read, with one deprecation line."""

import logging

logger = logging.getLogger(__name__)


def setting(env, suffix, default=None):
    """Return ``(value, name)`` for ``ENDLEAF_<suffix>``.

    A missing or blank new name falls back to ``COLOPHON_<suffix>``. Using
    the old name logs one warning. ``default`` is returned, under the new
    name, when both are missing or blank, and that path does not log.
    """
    new = f"ENDLEAF_{suffix}"
    old = f"COLOPHON_{suffix}"
    raw_new = env.get(new)
    if raw_new is not None and str(raw_new).strip() != "":
        return str(raw_new).strip(), new
    raw_old = env.get(old)
    if raw_old is not None and str(raw_old).strip() != "":
        logger.warning("deprecated environment variable %s; set %s", old, new)
        return str(raw_old).strip(), old
    return default, new
