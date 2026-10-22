# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test-only lane names.

Tests use neutral placeholder lanes as sample data. ``PROD_LANES`` is read
from colophon.enums when this module is first imported, before any test
patches it, so tests that need the real list (template folders on disk,
the enforcement test) never spell a lane name out.
"""

import colophon.enums as _enums

PROD_LANES = tuple(_enums.LANES)
LANE_A = "lane-a"
LANE_B = "lane-b"
PLACEHOLDER_LANES = (LANE_A, LANE_B)
# Placeholders render with an existing lane's template folder.
TEMPLATE_LANE = {LANE_A: PROD_LANES[0], LANE_B: PROD_LANES[1]}
