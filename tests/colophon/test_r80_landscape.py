"""ENDLEAF-R80: landscape fence margins and caption-aware height fit.

Unit cases (no TeX): c1 page.tex margin names, c2 fit.tex landscape derivation,
c3 the caption reserve in \\elfit@bounded, c4 the layout_too_tall warning.
TeX cases (a), (b) skip when xelatex or pdfinfo is missing. Caption position in
case (a) is checked from the PDF text position (pdftotext -bbox) when
pdftotext exists; otherwise the test emits a visible UNPROVEN warning (shown in
the pytest warnings summary) and records the property ``caption_position`` as
``UNPROVEN`` (junit xml / ``-rA`` shows it): a green run then does not read as
proof of the caption position.
"""
import warnings

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon import layout_warn
from colophon.templates import compose_with_body_line

_ROOT = Path(__file__).resolve().parents[2]
_SHARE = _ROOT / "colophon/share"
_OWNED = _SHARE / "templates/owned"
_TEX = _SHARE / "tex/latex/colophon-v1"
_PAGE = _TEX / "endleaf-page.tex"
_FIT = _TEX / "endleaf-fit.tex"
_VALUES = {"L": "20mm", "R": "20mm", "T": "20mm", "B": "22mm"}


def _code(path):
    return "\n".join(line.split("%", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())


def _braced(text, start):
    """Text from ``start`` to the end of the first balanced brace group after it."""
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError("unbalanced braces")


def _flat(text):
    text = re.sub(r"\\setlength\{(\\[A-Za-z@]+)\}\{([^{}]*)\}", r"\1=\2", text)
    return re.sub(r"\s+", " ", text)


def _cond(text, start):
    """(then, else) parts of the balanced conditional whose \\if token starts at ``start``."""
    depth = 0
    else_at = None
    first_end = None
    for m in re.finditer(r"\\(if[A-Za-z@]*|else|fi)(?![A-Za-z@])", text[start:]):
        tok, pos = m.group(1), start + m.start()
        if tok == "fi":
            depth -= 1
            if depth == 0:
                end = pos
                head = re.match(r"\\if[A-Za-z@]*", text[start:]).end() + start
                if else_at is None:
                    return text[head:end], ""
                return text[head:else_at], text[else_at + len(r"\else") : end]
        elif tok == "else":
            if depth == 1 and else_at is None:
                else_at = pos
        else:
            depth += 1
    raise AssertionError("unbalanced conditional")


_DEF = (
    r"\\(?:def|gdef|edef|xdef|newcommand\*?|renewcommand\*?|providecommand\*?|newdimen|newskip)"
    r"\s*\{?\\EndleafLand%s\b"
    r"|\\newlength\s*\{?\\EndleafLand%s\b"
)


# --- c1: endleaf-page.tex ----------------------------------------------------

@pytest.mark.parametrize("side", sorted(_VALUES))
def test_c1_page_defines_each_landscape_margin_once(side):
    code = _code(_PAGE)
    assert len(re.findall(_DEF % (side, side), code)) == 1, side
    value = _VALUES[side]
    assert re.search(rf"\\EndleafLand{side}\}}?\s*(?:=\s*|\{{){value}", code), (side, value)


# --- c2: endleaf-fit.tex landscape derivation --------------------------------

def _fit_landscape_parts():
    code = _code(_FIT)
    begin = _braced(code, code.index(r"\AtBeginDocument"))
    setland = _braced(code, code.index(r"\def\elfit@setlandscape"))
    return code, begin, setland


def test_c2_fit_landscape_uses_the_four_names():
    _, begin, setland = _fit_landscape_parts()
    for name in ("EndleafLandL", "EndleafLandR", "EndleafLandT", "EndleafLandB"):
        assert rf"\{name}" in begin, name
    for name in ("EndleafLandL", "EndleafLandT"):
        assert rf"\{name}" in setland, name


def test_c2_fit_has_one_ifdefined_fallback_with_equal_values():
    code = _code(_FIT)
    assert len(re.findall(r"\\ifdefined\s*\\EndleafLandL\b", code)) == 1
    start = re.search(r"\\ifdefined\s*\\EndleafLandL\b", code).start()
    then, other = _cond(code, start)
    block = then + " " + other
    for side, value in _VALUES.items():
        assert re.search(rf"\\EndleafLand{side}\}}?\s*(?:=\s*|\{{){value}", block), side


def test_c2_landscape_no_longer_derives_from_the_portrait_snapshot():
    _, begin, setland = _fit_landscape_parts()
    for macro in (r"\elfit@left", r"\elfit@right", r"\elfit@top", r"\elfit@bot"):
        assert not re.search(re.escape(macro) + r"(?![A-Za-z@])", begin), macro
    assert r"\elfit@portoddm" not in setland and r"\elfit@porttopm" not in setland
    assert r"\elfit@portevenm" not in setland


# --- c3: caption reserve in \elfit@bounded -----------------------------------

def _bounded():
    code = _code(_FIT)
    return _flat(_braced(code, code.index(r"\def\elfit@bounded")))


def test_c3_bounded_keeps_the_floor_and_names_the_reserve_parts():
    body = _bounded()
    assert r"\def\elfit@fencefloor{7}" in _flat(_code(_FIT))
    assert r"\elfit@minscale" in body and r"\elfit@fencefloor" in body
    for token in (r"\abovecaptionskip", r"\ElfitCaptionHeight", r"\elfit@capreserve", "ENDLEAF_SHELLTALL"):
        assert token in body, token
    assert r"3\baselineskip" in body.replace(" ", "") or r"\baselineskip" in body


def test_c3_reserve_applies_inside_a_wrapped_figure_or_table_float_only():
    body = _bounded()
    assert r"\abovecaptionskip" in body, "no caption reserve in \\elfit@bounded"
    at = body.index(r"\abovecaptionskip")
    starts = [m.start() for m in re.finditer(r"\\ifelfit@insidefloat(?![A-Za-z@])", body[:at])]
    assert starts, "the reserve must be chosen under \\ifelfit@insidefloat"
    # the governing block is the nearest one that still contains the reserve
    for start in reversed(starts):
        inside, outside = _cond(body, start)
        if r"\abovecaptionskip" in inside or r"\abovecaptionskip" in outside:
            break
    else:
        raise AssertionError("no \\ifelfit@insidefloat block contains \\abovecaptionskip")
    assert r"\abovecaptionskip" in inside and r"\elfit@capreserve" in inside
    assert r"\abovecaptionskip" not in outside
    assert re.search(r"\\elfit@capreserve\s*=\s*(?:0pt|\\z@)", outside), "outside a float the reserve is 0"


def _bound_register(body):
    """Register assigned \\elfit@landth under \\ifelfit@thisland and \\textheight in its else."""
    for m in re.finditer(r"\\ifelfit@thisland(?![A-Za-z@])", body):
        then, other = _cond(body, m.start())
        t = re.search(r"(\\[A-Za-z@]+)\s*=[^\\]*\\(?:dimexpr\s*)?\\?[^\\]*", then)
        o = re.search(r"(\\[A-Za-z@]+)\s*=", other)
        if t and o and t.group(1) == o.group(1) and r"\elfit@landth" in then and r"\textheight" in other:
            return t.group(1)
    return None


def test_c3_height_bound_is_landth_when_thisland_else_textheight():
    body = _bounded()
    assert _bound_register(body), "bound selection is not tied to \\ifelfit@thisland"
    # the height scale is computed against that bound, not the bare \textheight
    assert not re.search(r"\\Gscale@div\\elfit@h\{\\textheight\}", body.replace(" ", ""))


def test_c3_shelltall_avail_is_the_bound_itself():
    body = _bounded()
    bound = _bound_register(body)
    assert bound, "no bound register"
    assert "ENDLEAF_SHELLTALL" in body, "no SHELLTALL marker in \\elfit@bounded"
    at = body.index("ENDLEAF_SHELLTALL")
    depth, end = 0, len(body)
    for i in range(at, len(body)):  # end of the brace group that holds the marker
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            if depth == 0:
                end = i
                break
            depth -= 1
    group = body[at:end]
    thes = list(re.finditer(r"\\the(\\[A-Za-z@]+)", group))
    assert len(thes) >= 2, group
    assert thes[-1].group(1) == bound, group
    assert r"\elfit@capreserve" not in group[thes[-2].start() :], "avail must not subtract the reserve"


# --- c4: layout_warn ---------------------------------------------------------

_FIT_LINE = "ENDLEAF_SHELLFIT 1 250.0pt 300.0pt 10.0 1"
_PAGE_LINE = "ENDLEAF_SHELLPAGE 1 2 landscape"


def _tall(height, avail, extra=""):
    return "\n".join([_FIT_LINE, _PAGE_LINE, f"ENDLEAF_SHELLTALL 1 {height}pt {avail}pt", extra, ""])


def _too_tall(log):
    return [w for w in layout_warn.layout_warnings(log) if w.get("code") == "layout_too_tall"]


def test_c4_tall_fence_gives_one_layout_too_tall_item():
    items = _too_tall(_tall("512.3", "478.0"))
    assert len(items) == 1
    item = items[0]
    assert item["packages"] == ["diagram"]
    assert item["overMm"] == round((512.3 - 478.0) * layout_warn._PT_TO_MM, 1)
    assert item["page"] == 2 and item["landscape"] is True
    assert "pg2" in item["message"] and "mm" in item["message"]


def test_c4_margin_below_the_minimum_gives_no_item():
    assert len(_too_tall(_tall("512.3", "478.0"))) == 1
    assert not _too_tall(_tall("478.5", "478.0"))
    assert layout_warn.MIN_OVERHANG_PT > 0.5


def test_c4_duplicate_fence_number_gives_one_item():
    log = _tall("512.3", "478.0", "ENDLEAF_SHELLTALL 1 512.3pt 478.0pt")
    assert len(_too_tall(log)) == 1


def test_c4_survives_the_line_round_trip():
    items = _too_tall(_tall("512.3", "478.0"))
    assert items
    back = layout_warn.parse_layout(layout_warn.layout_line(items))
    assert [w["code"] for w in back] == ["layout_too_tall"]
    assert back[0]["overMm"] == items[0]["overMm"] and back[0]["packages"] == ["diagram"]


# --- TeX-level (skipped without xelatex) -------------------------------------

_tex = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdfinfo") is None, reason="xelatex/pdfinfo not installed"
)
_A4_L = "841.89 x 595.28"
_A4_P = "595.28 x 841.89"


_PROBE = (
    r"\typeout{R80TB \the\textwidth\space\the\textheight\space\the\paperwidth\space\the\paperheight"
    r"\space\the\EndleafPageL\space\the\EndleafPageR\space\the\EndleafPageT\space\the\EndleafPageB}"
)


def _compile(tmp_path, name, body, orientation=None):
    tex, _ = compose_with_body_line("document-shell", "InstruMeasure", body, root=_OWNED, orientation=orientation)
    tex = tex.replace(r"\end{document}", _PROBE + r"\end{document}")
    d = tmp_path / name
    d.mkdir()
    (d / "job.tex").write_text(tex, encoding="utf-8")
    env = dict(os.environ, TEXINPUTS=f".:{_SHARE / 'tex'}//:")
    subprocess.run(["xelatex", "-interaction=nonstopmode", "job.tex"], cwd=d, env=env, capture_output=True, timeout=240)
    log = (d / "job.log").read_text(encoding="utf-8", errors="replace")
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "99", str(d / "job.pdf")], capture_output=True, text=True).stdout
    pages = [l.split(":", 1)[1].split("pts")[0].strip() for l in info.splitlines() if re.match(r"Page\s+\d+ size", l)]
    return d, pages, log


@_tex
def test_a_landscape_fence_with_caption_fits_one_page_at_scale_one(tmp_path, record_property):
    """Checks: one page, SHELLFIT scale 1, no SHELLTALL, no layout_too_tall.

    Caption position: a PDF text-position check runs only when pdftotext exists;
    otherwise the test warns "UNPROVEN" and records property caption_position
    = UNPROVEN (log markers cannot show it); it does not pass silently.
    """
    body = (
        "```tikz\n\\draw (0,0) rectangle (20cm,11.5cm);\n```\n\n"
        "Figure: Two line caption that is long enough to wrap onto a second line of the caption "
        "on this landscape page, with a few more words to be sure.\n"
    )
    d, pages, log = _compile(tmp_path, "land", body, orientation="landscape")
    assert pages == [_A4_L]
    fit = re.findall(r"ENDLEAF_SHELLFIT \d+ \S+ \S+ \S+ (\S+)", log)
    assert fit and all(float(s) == 1.0 for s in fit)
    assert "ENDLEAF_SHELLTALL" not in log
    assert "layout_too_tall" not in str(layout_warn.layout_warnings(log))
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-bbox", str(d / "job.pdf"), "-"], capture_output=True, text=True).stdout
        ys = [float(y) for y, w in re.findall(r'yMax="([0-9.]+)">([^<]*)<', out) if w in ("Two", "caption", "wrap", "sure.")]
        # text block bottom = paper height - 22 mm; the footskip sits below it
        assert ys and max(ys) <= 595.28 - 22 * 72.27 / 25.4 * 72 / 72.27 + 1
        record_property("caption_position", "proven")
    else:
        record_property("caption_position", "UNPROVEN")
        warnings.warn("UNPROVEN: pdftotext missing, landscape caption position not checked", stacklevel=1)


@_tex
def test_b_portrait_fence_is_unchanged(tmp_path):
    body = "```tikz\n\\draw (0,0) rectangle (12cm,6cm);\n```\n"
    _, pages, log = _compile(tmp_path, "port", body)
    assert pages == [_A4_P]
    assert "ENDLEAF_SHELLTALL" not in log
    fit = re.findall(r"ENDLEAF_SHELLFIT \d+ \S+ \S+ \S+ (\S+)", log)
    assert all(float(s) == 1.0 for s in fit)
    probe = re.findall(r"R80TB (\S+)pt (\S+)pt (\S+)pt (\S+)pt (\S+)pt (\S+)pt (\S+)pt (\S+)pt", log)
    assert probe, "text-block probe line missing from the log"
    tw, th, pw, ph, l, r, t, b = (float(x) for x in probe[-1])
    # portrait baseline: the text block is the paper minus the class-derived page margins
    assert abs(tw - (pw - l - r)) < 0.5 and abs(th - (ph - t - b)) < 0.5, probe[-1]
    assert abs(pw - 595.28 * 72.27 / 72) < 1 and abs(ph - 841.89 * 72.27 / 72) < 1
    assert tw < pw and th < ph and tw > 0.5 * pw and th > 0.5 * ph
