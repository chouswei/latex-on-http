# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R64-ROWS. Overfull boxes in the caller's body, for every TeX template.

From the final-pass log the worker reads every ``Overfull \\hbox`` and
``Overfull \\vbox`` TeX reported and sends, in the layout map:

  overfullTotal  how many TeX reported in the body (plus those TeX gave no
                 line for, which cannot be ruled out), always, also past the cap
  overfull       rows, largest pt first, at most ``MAX_ROWS``:
                 {"line", "pt", "axis": "h"|"v", "page"?, "table"?}

``page`` is the number of the first shipout marker after the warning and is
omitted when none follows. ``table`` is present when the warning's line range
starts a tabular or longtable of the body, or lies inside one:
{"firstLine", "n", "share", "rules"}; ``share`` holds one entry per column,
its declared width over the sum of declared widths, or null for a column
without one. Only numbers and the axis letter leave the sandbox, never log or
document text.
"""

import re
from decimal import Decimal

# ENDLEAF-R64-ROWS maxRows and maxTableColumns, measured with the real encoder
# by tests/colophon/test_overfull_r64.py: 50 worst-case rows (5-digit lines,
# random pt, 3-digit pages, every row with a 20-column table field, random
# shares) encode to 5224 bytes, under half of the 12000-byte map cap (12
# columns: 3852 bytes).
# Without the column cap 60 columns gave about 11.8 kB and 100 about 18 kB, so
# a table wider than MAX_TABLE_COLUMNS is sent without its table field (no
# width Fix). If a map is still over the cap, the optional lists drop (R61)
# and overfullTotal stays: the gate prints "N lines, page unknown".
MAX_ROWS = 50
MAX_TABLE_COLUMNS = 20

_OVERFULL = re.compile(
    r"^Overfull \\([hv])box \(([0-9]+(?:\.[0-9]+)?)pt too (?:wide|high)\)"
    r"(?: in (?:paragraph|alignment) at lines ([0-9]+)--([0-9]+)| detected at line ([0-9]+))?",
    re.MULTILINE,
)
# A shipout writes "[<page>" to the log, followed by "]", a space, "{" or a newline.
# Page text TeX dumps after a box warning ("[]\OT1/cmr/m/n/10 see [7] ...") can
# hold the same shape, so every box dump is masked before shipouts are read: a
# dump runs from an Overfull/Underfull line to the next blank line.
_SHIPOUT = re.compile(r"\[([0-9]{1,5})(?=[\]\s{<])")
_BOX_DUMP = re.compile(r"^(?:Overfull|Underfull|Loose|Tight) \\[hv]box .*?(?:\n[ \t]*\n|\Z)", re.MULTILINE | re.DOTALL)
_ENV = re.compile(r"\\(begin|end)\{(tabular\*?|longtable)\}")
_PT_PER = {
    "pt": Decimal(1),
    "bp": Decimal("72.27") / Decimal(72),
    "in": Decimal("72.27"),
    "cm": Decimal("72.27") / Decimal("2.54"),
    "mm": Decimal("72.27") / Decimal("25.4"),
    "pc": Decimal(12),
    "dd": Decimal("1238") / Decimal("1157"),
    "cc": Decimal("14856") / Decimal("1157"),
    "sp": Decimal(1) / Decimal(65536),
}
_ABS = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(pt|bp|in|cm|mm|pc|dd|cc|sp)\s*$")
_REL = re.compile(r"^\s*([0-9]*\.?[0-9]*)\s*\\(linewidth|textwidth|columnwidth|hsize)\s*$")


def _mask_box_dumps(log):
    """The log with every box dump blanked out, same length so positions hold."""
    return _BOX_DUMP.sub(lambda match: " " * len(match.group(0)), log)


def _shipouts(log):
    masked = _mask_box_dumps(log)
    return [(match.start(), int(match.group(1))) for match in _SHIPOUT.finditer(masked)]


def _page_after(shipouts, position):
    for start, page in shipouts:
        if start > position:
            return page
    return None


def _group(spec, start):
    """The text of the {...} group at ``spec[start]`` and the index after it, or None."""
    if start >= len(spec) or spec[start] != "{":
        return None
    depth = 0
    for index in range(start, len(spec)):
        if spec[index] == "{":
            depth += 1
        elif spec[index] == "}":
            depth -= 1
            if depth == 0:
                return spec[start + 1 : index], index + 1
    return None


def parse_colspec(spec):
    """Columns as width strings (or None for l/c/r) and the vertical rule count; None when unparsed."""
    columns = []
    rules = 0
    index = 0
    while index < len(spec):
        char = spec[index]
        if char.isspace():
            index += 1
        elif char == "|":
            rules += 1
            index += 1
        elif char in "lcrX":
            columns.append(None)
            index += 1
        elif char in "pmb":
            group = _group(spec, index + 1)
            if group is None:
                return None
            columns.append(group[0])
            index = group[1]
        elif char in "@!><":
            group = _group(spec, index + 1)
            if group is None:
                return None
            index = group[1]
        elif char == "*":
            count = _group(spec, index + 1)
            if count is None or not count[0].strip().isdigit():
                return None
            inner = _group(spec, count[1])
            if inner is None:
                return None
            parsed = parse_colspec(inner[0])
            if parsed is None:
                return None
            times = int(count[0])
            columns.extend(parsed[0] * times)
            rules += parsed[1] * times
            index = inner[1]
        else:
            return None
    return (columns, rules) if columns else None


def column_shares(widths):
    """Each column's declared width over the sum, rounded to 4 places; None entries for columns without one."""
    values = []
    kind = None
    for width in widths:
        if width is None:
            values.append(None)
            continue
        match = _ABS.match(width)
        if match:
            this, value = "abs", Decimal(match.group(1)) * _PT_PER[match.group(2)]
        else:
            match = _REL.match(width)
            if not match:
                values.append(None)
                continue
            this, value = "rel", Decimal(match.group(1) or "1")
        if kind not in (None, this):
            return [None] * len(widths)
        kind = this
        values.append(value)
    known = [value for value in values if value is not None]
    total = sum(known, Decimal(0))
    if not known or total <= 0 or len(known) != len(values):
        return [None] * len(values)
    return [float((value / total).quantize(Decimal("0.0001"))) for value in values]


def body_tables(source):
    """Tables of the body: (firstLine, lastLine, n, share, rules), body lines 1-based."""
    lines = (source or "").split("\n")
    text = "\n".join(lines)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)

    def line_of(position):
        low, high = 0, len(offsets) - 1
        while low < high - 1:
            mid = (low + high) // 2
            if offsets[mid] <= position:
                low = mid
            else:
                high = mid
        return low + 1

    tables = []
    stack = []
    for match in _ENV.finditer(text):
        if match.group(1) == "begin":
            after = match.end()
            if match.group(2) == "tabular*":
                width = _group(text, after)
                after = width[1] if width else after
            while after < len(text) and text[after] == "[":
                close = text.find("]", after)
                after = close + 1 if close > 0 else after + 1
            spec = _group(text, after)
            stack.append((line_of(match.start()), spec[0] if spec else None))
        elif stack:
            first, spec = stack.pop()
            parsed = parse_colspec(spec) if spec is not None else None
            if parsed is None:
                continue
            widths, rules = parsed
            tables.append((first, line_of(match.start()), len(widths), column_shares(widths), rules))
    return tables


def _table_for(tables, first, last):
    best = None
    for table in tables:
        starts_here = first <= table[0] <= last
        inside = table[0] <= first and last <= table[1]
        if starts_here or inside:
            if best is None or table[0] >= best[0]:
                best = table
    return best


def overfull_rows(log, *, body_start, body_lines, source=None, max_rows=MAX_ROWS):
    """(rows, total) for the map; ([], 0) when TeX reported none in the body."""
    if not log or body_start is None or body_lines <= 0:
        return [], 0
    shipouts = _shipouts(log)
    tables = body_tables(source) if source else []
    rows = []
    total = 0
    for match in _OVERFULL.finditer(log):
        first = match.group(3) or match.group(5)
        last = match.group(4) or match.group(5)
        if first is None:
            # No line from TeX (a vbox while \output is active): counted, never listed.
            total += 1
            continue
        first, last = int(first), int(last)
        if not (body_start <= first < body_start + body_lines):
            continue
        total += 1
        line = first - body_start + 1
        # pt exactly as TeX printed it; the gate rounds in decimal (ENDLEAF-R64-REPORT).
        row = {"line": line, "pt": float(match.group(2)), "axis": match.group(1)}
        page = _page_after(shipouts, match.end())
        if page is not None:
            row["page"] = page
        table = _table_for(tables, line, last - body_start + 1)
        if table is not None and table[2] <= MAX_TABLE_COLUMNS:
            row["table"] = {"firstLine": table[0], "n": table[2], "share": table[3], "rules": table[4]}
        rows.append(row)
    rows.sort(key=lambda row: (-row["pt"], row.get("page", 10**6), row["line"]))
    return rows[:max_rows], total
