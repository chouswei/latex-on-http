"""Generate the gap fixtures of the R82 route checks and their expected JSON.

Usage:
  make_gap_fixtures.py REPO REF_PYTHON OUTDIR

  REPO        the worker checkout (it holds colophon/pdf_layout_check.py, the Python reference)
  REF_PYTHON  the interpreter with the pinned reference wheels (pdfminer.six, shapely, scipy)
  OUTDIR      tests/fixtures/gap (PDFs, sidecars, expected/*.json, manifest.json)

This script (not the tests) needs reportlab, for the CJK, TrueType and encrypted fixtures; run
it with an interpreter that has it. The Rust tests read only the committed output.

Each case is {name, node, pdf, template, blocks, texPages, marks, shellPages, compare}. The
expected file holds what the Python reference gives ({items, log, lines}); the exceptions are
the N4 cases, whose expected output is the Python result for the Flate twin of the same page
(pdfminer ignores /EarlyChange 0, so its own LZW answer is not the right one), and the
encrypted cases, whose expected output is the one skip note chosen in ENDLEAF-R82-DECODE.
`compare` says what the test compares: "items" (findings and log), "lines" (the --dump text
and boxes), or both.
"""
import json
import pathlib
import subprocess
import sys
import zlib

repo, ref_python, outdir = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
here = pathlib.Path(__file__).resolve().parent
(outdir / "expected").mkdir(parents=True, exist_ok=True)

BLOCK = (72.27, 72.27, 468.0 * 72.27 / 72, 648.0 * 72.27 / 72)
ESCAPE = "this line runs far past the right edge of the block"

CASES = []  # manifest rows


# --- PDF writers ----------------------------------------------------------------------------------
def pdf_bytes(pages, size=(612, 792), content_filter=None, encode=None):
    """A PDF with one content stream per page (font /F1 is Helvetica).

    ``encode(content_bytes) -> bytes`` writes the stream data and ``content_filter`` is the
    text that goes into its dictionary after /Length (for example "/Filter /LZWDecode").
    """
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    count = len(pages)
    kids = " ".join(f"{3 + 2 * n} 0 R" for n in range(count))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode()
    for n, content in enumerate(pages):
        page_id, stream_id = 3 + 2 * n, 4 + 2 * n
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {size[0]} {size[1]}] /Contents {stream_id} 0 R "
            f"/Resources << /Font << /F1 {3 + 2 * count} 0 R >> >> >>"
        ).encode()
        raw = content.encode("latin-1")
        body = encode(raw) if encode else raw
        extra = f" {content_filter}" if content_filter else ""
        objects[stream_id] = (
            f"<< /Length {len(body)}{extra} >>\nstream\n".encode() + body + b"\nendstream"
        )
    objects[3 + 2 * count] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    out = b"%PDF-1.4\n"
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def text(x, y, string, size=10):
    return f"BT /F1 {size} Tf {x} {y} Td ({string}) Tj ET\n"


def body(lines=20, start=700, left=72):
    return "".join(text(left, start - 14 * n, "an ordinary line of body text sits here") for n in range(lines))


# --- stream encoders (N4) -------------------------------------------------------------------------
def lzw_encode(data, early=1):
    """PDF LZW (MSB first, 9..12 bit codes). ``early`` is /EarlyChange."""
    table = {bytes([i]): i for i in range(256)}
    nxt = 258
    bits, nbits, out = 0, 0, bytearray()
    emitted = 0  # codes emitted since the clear code, the clear code excluded

    def put(code, width):
        nonlocal bits, nbits
        bits = (bits << width) | code
        nbits += width
        while nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
        bits &= (1 << nbits) - 1

    def width():
        # the reader's table has one entry fewer than ours after the first code
        size = 258 + max(0, emitted - 1) + early
        return 9 if size < 512 else 10 if size < 1024 else 11 if size < 2048 else 12

    put(256, 9)
    w = b""
    for byte in data:
        wc = w + bytes([byte])
        if wc in table:
            w = wc
            continue
        put(table[w], width())
        emitted += 1
        table[wc] = nxt
        nxt += 1
        assert nxt < 4094, "fixture too large for a single LZW table"
        w = bytes([byte])
    if w:
        put(table[w], width())
        emitted += 1
    put(257, width())
    if nbits:
        out.append((bits << (8 - nbits)) & 0xFF)
    return bytes(out)


def lzw_decode(data, early=1):
    """Reference decoder for the self-check of the encoder."""
    pos, out, table, prev = 0, bytearray(), None, None

    def read(width):
        nonlocal pos
        value = 0
        for _ in range(width):
            value = (value << 1) | ((data[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        return value

    width = 9
    while pos + width <= len(data) * 8:
        code = read(width)
        if code == 256:
            table, prev, width = [bytes([i]) for i in range(256)] + [b"", b""], None, 9
            continue
        if code == 257:
            break
        entry = table[code] if code < len(table) else prev + prev[:1]
        if prev is not None:
            table.append(prev + entry[:1])
        out += entry
        prev = entry
        size = len(table) + early
        width = 9 if size < 512 else 10 if size < 1024 else 11 if size < 2048 else 12
    return bytes(out)


def png_up(data, columns):
    """PNG 'Up' predictor rows (filter byte 2), the data padded with spaces to whole rows."""
    data = data + b" " * (-len(data) % columns)
    rows = [data[i : i + columns] for i in range(0, len(data), columns)]
    out, prev = bytearray(), bytes(columns)
    for row in rows:
        out.append(2)
        out += bytes((a - b) & 0xFF for a, b in zip(row, prev))
        prev = row
    return bytes(out)


def tiff_2(data, columns):
    data = data + b" " * (-len(data) % columns)
    out = bytearray()
    for i in range(0, len(data), columns):
        row = data[i : i + columns]
        out += bytes([row[0]]) + bytes((row[j] - row[j - 1]) & 0xFF for j in range(1, columns))
    return bytes(out)


def run_length(data):
    out, i = bytearray(), 0
    while i < len(data):
        run = 1
        while i + run < len(data) and data[i + run] == data[i] and run < 128:
            run += 1
        if run >= 2:
            out += bytes([257 - run, data[i]])
            i += run
            continue
        j = i
        while j < len(data) and j - i < 128 and (j + 1 >= len(data) or data[j] != data[j + 1]):
            j += 1
        j = max(j, i + 1)
        out += bytes([j - i - 1]) + data[i:j]
        i = j
    return bytes(out) + b"\x80"


# --- reference runs -------------------------------------------------------------------------------
def reference(name, pdf_path, spec):
    spec_path = outdir / "expected" / f"{name}.spec.json"
    spec_path.write_text(json.dumps(spec))
    got = subprocess.run(
        [ref_python, "-I", str(here / "gap_ref.py"), repo, str(pdf_path), str(spec_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    spec_path.unlink()
    return json.loads(got.stdout)


def add(name, node, pdf, template="fulldoc", blocks=None, tex_pages=(), marks=(), shell_pages=None,
        compare="items", twin=None, expected=None, sidecar=False, note=""):
    """Write the PDF and the expected JSON, and add the manifest row."""
    pdf_path = outdir / f"{name}.pdf"
    pdf_path.write_bytes(pdf)
    spec = {
        "template": template,
        "blocks": {str(k): list(v) for k, v in (blocks or {}).items()},
        "texPages": list(tex_pages),
        "marks": [list(m) for m in marks],
        "shellPages": {str(k): v for k, v in (shell_pages or {}).items()},
    }
    if expected is None:
        expected = reference(name, twin if twin is not None else pdf_path, spec)
    (outdir / "expected" / f"{name}.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n")
    CASES.append({"name": name, "node": node, "pdf": f"{name}.pdf", "compare": compare,
                  "sidecar": sidecar, "note": note, **spec})
    return pdf_path


B1 = {1: BLOCK}


# --- N2: sidecar, part ids, fence numbers, encrypted skip ------------------------------------------
def n2():
    two = text(400, 680, ESCAPE) + text(400, 600, ESCAPE)
    marks = [["p1", "s", 1, 750.0, "v"], ["p1", "e", 1, 640.0, "v"],
             ["p2", "s", 1, 640.0, "v"], ["p2", "e", 1, 500.0, "v"]]
    add("n2_sidecar_part", "N2", pdf_bytes([two]), "fulldoc", B1, marks=marks, sidecar=True,
        note="partId from the fulldoc marks, through --sidecar")
    shell = [text(400, 680, ESCAPE), body(5), text(400, 680, ESCAPE)]
    add("n2_sidecar_fence", "N2", pdf_bytes(shell), "document-shell", {1: BLOCK, 2: BLOCK, 3: BLOCK},
        shell_pages={1: 1, 2: 3}, sidecar=True, note="fenceNumber from shellPages")
    add("n2_sidecar_plain", "N2", pdf_bytes([body() + text(400, 40, "1"), text(72, 700, "short") + text(400, 680, ESCAPE)]),
        "fulldoc", {1: BLOCK, 2: BLOCK}, sidecar=True, note="plain sidecar run, stdout is exactly {items, log}")
    three = "".join(text(400, 700 - 12 * n, ESCAPE) for n in range(3))
    add("n2_sidecar_texpages", "N2", pdf_bytes([three]), "fulldoc", B1, tex_pages=(1,), sidecar=True,
        note="texPages from the sidecar silence a TeX-named page; the sidecar also carries an unknown key")
    from reportlab.lib.pdfencrypt import StandardEncryption
    from reportlab.pdfgen import canvas

    enc = outdir / "n2_encrypted.pdf"
    c = canvas.Canvas(str(enc), pagesize=(612, 792), pageCompression=0,
                      encrypt=StandardEncryption("", ownerPassword="owner", strength=40))
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "an encrypted page")
    c.drawString(400, 680, ESCAPE)
    c.save()
    note = {"code": "pdf_check_skipped", "packages": ["pdf"],
            "message": "pdf layout check stopped (encrypted) before pg1"}
    add("n2_encrypted_skip", "N2", enc.read_bytes(), "fulldoc", B1, sidecar=True,
        expected={"items": [note], "log": [], "lines": []},
        note="RC4 file: exactly one skip note, no decryption (accepted divergence from pdfminer)")


# --- N3: CJK ----------------------------------------------------------------------------------------
def cjk_pdf(path, face, encoding, strings, vertical=False, size=12):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import CIDFont, UnicodeCIDFont
    from reportlab.pdfgen import canvas

    font = CIDFont(face, encoding) if "-EUC-" in encoding or "RKSJ" in encoding or "B5" in encoding \
        or "UHC" in encoding else UnicodeCIDFont(face, isVertical=vertical)
    pdfmetrics.registerFont(font)
    if not isinstance(font, UnicodeCIDFont):  # byte CMaps take the bytes of the legacy encoding
        codec = "gbk" if "GBK" in encoding else "shift_jis"
        strings = [s.encode(codec).decode("latin-1") for s in strings]
    c = canvas.Canvas(str(path), pagesize=(612, 792), pageCompression=0)
    y = 700
    for s in strings:
        c.setFont(font.fontName, size)
        c.drawString(72, y, s)
        y -= 40
    # one line past the block edge so a finding rides on the text too
    c.setFont(font.fontName, size)
    c.drawString(380, 300, strings[0] * 3)
    c.showPage()
    c.save()
    return path.read_bytes()


def n3():
    cases = [
        ("n3_gb1_ucs2", "STSong-Light", "UniGB-UCS2-H", ["你好，世界", "排版检查 PDF 12"], False),
        ("n3_cns1_ucs2", "MSung-Light", "UniCNS-UCS2-H", ["你好，世界", "版面檢查 PDF 12"], False),
        ("n3_korea1_ucs2", "HYSMyeongJo-Medium", "UniKS-UCS2-H", ["안녕하세요 세계", "레이아웃 검사 12"], False),
        ("n3_japan1_ucs2", "HeiseiMin-W3", "UniJIS-UCS2-H", ["こんにちは世界", "レイアウト検査 12"], False),
        ("n3_japan1_vertical", "HeiseiMin-W3", "UniJIS-UCS2-V", ["縦書きの日本語"], True),
        ("n3_gb1_gbk_euc", "STSong-Light", "GBK-EUC-H", ["字节编码的中文", "第二行 12"], False),
        ("n3_japan1_rksj", "HeiseiMin-W3", "90ms-RKSJ-H", ["シフトJISの文字", "第二行 12"], False),
    ]
    for name, face, enc, strings, vertical in cases:
        path = outdir / f"{name}.pdf"
        data = cjk_pdf(path, face, enc, strings, vertical)
        add(name, "N3", data, "fulldoc", B1, compare="both", note=f"{face} {enc}, not embedded")

    # Identity-H TrueType (CIDFontType2, Adobe-Identity) without ToUnicode: Vera subset by
    # fontTools with the glyph ids kept, so the codes are glyph ids and only the font's own cmap
    # table tells the text.
    import io
    import os
    import reportlab
    from fontTools import subset
    from fontTools.ttLib import TTFont as FTFont

    ttf = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
    lines = [("Identity encoded TrueType text", 72, 700), ("second line 12 34", 72, 660),
             ("identity text past the right edge of the block", 380, 300)]
    chars = sorted({ch for t, _, _ in lines for ch in t})
    opts = subset.Options()
    opts.retain_gids = True
    opts.layout_features = []
    opts.name_IDs = []
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    font = FTFont(ttf)
    sub.populate(text="".join(chars))
    sub.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    data = buf.getvalue()
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()
    gid = {ch: order.index(cmap[ord(ch)]) for ch in chars}
    width = {ch: round(font["hmtx"][cmap[ord(ch)]][0] * 1000 / font["head"].unitsPerEm) for ch in chars}
    ws = " ".join(f"{gid[ch]} [{width[ch]}]" for ch in chars)
    content = ""
    for t, x, y in lines:
        hexs = "".join(f"{gid[ch]:04X}" for ch in t)
        content += f"BT /F2 12 Tf {x} {y} Td <{hexs}> Tj ET\n"
    comp = zlib.compress(data)
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F2 5 0 R >> >> >>",
        4: f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode("latin-1"),
        5: b"<< /Type /Font /Subtype /Type0 /BaseFont /VeraSub /Encoding /Identity-H /DescendantFonts [6 0 R] >>",
        6: (f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /VeraSub /CIDSystemInfo << /Registry (Adobe) "
            f"/Ordering (Identity) /Supplement 0 >> /FontDescriptor 7 0 R /DW 600 /W [{ws}] "
            f"/CIDToGIDMap /Identity >>").encode(),
        7: b"<< /Type /FontDescriptor /FontName /VeraSub /Flags 4 /FontBBox [-200 -250 1200 950] /ItalicAngle 0 "
           b"/Ascent 930 /Descent -236 /CapHeight 729 /StemV 80 /FontFile2 8 0 R >>",
        8: f"<< /Length {len(comp)} /Length1 {len(data)} /Filter /FlateDecode >>\nstream\n".encode() + comp + b"\nendstream",
    }
    out = b"%PDF-1.4\n"
    offs = {}
    for n in sorted(objs):
        offs[n] = len(out)
        out += f"{n} 0 obj\n".encode() + objs[n] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for n in sorted(objs):
        out += f"{offs[n]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    add("n3_truetype_identity", "N3", out, "fulldoc", B1, compare="both",
        note="Identity-H CIDFontType2 (embedded TrueType subset), no ToUnicode")


# --- N4: filters ------------------------------------------------------------------------------------
def n4():
    # long enough that the LZW table passes 511 entries, where /EarlyChange matters
    lines = []
    for n in range(26):
        lines.append(text(72, 730 - 14 * n, f"line {n} varies {n * 7919 % 1013} to keep the table growing {n}"))
    content = "".join(lines) + text(400, 300, ESCAPE)
    for entry in (1, 0):
        assert lzw_decode(lzw_encode(content.encode(), entry), entry) == content.encode()
    twin = pdf_bytes([content], encode=zlib.compress, content_filter="/Filter /FlateDecode")
    twin_path = add("n4_reg_flate_twin", "N4", twin, "fulldoc", B1, compare="both",
                    note="the Flate twin all the filter variants must equal (passes today: regression)")

    def variant(name, filt, encode, note):
        add(name, "N4", pdf_bytes([content], content_filter=filt, encode=encode), "fulldoc", B1,
            compare="both", twin=twin_path, note=note)

    variant("n4_lzw_early1", "/Filter /LZWDecode", lambda d: lzw_encode(d, 1), "LZW, EarlyChange 1 (the default)")
    variant("n4_lzw_early0", "/Filter /LZWDecode /DecodeParms << /EarlyChange 0 >>", lambda d: lzw_encode(d, 0),
            "LZW, EarlyChange 0")
    variant("n4_lzw_png", "/Filter /LZWDecode /DecodeParms << /Predictor 12 /Columns 16 >>",
            lambda d: lzw_encode(png_up(d, 16), 1), "LZW with the PNG Up predictor")
    variant("n4_lzw_tiff", "/Filter /LZWDecode /DecodeParms << /Predictor 2 /Columns 16 >>",
            lambda d: lzw_encode(tiff_2(d, 16), 1), "LZW with TIFF predictor 2")
    variant("n4_lzw_flate", "/Filter [/LZWDecode /FlateDecode]", lambda d: lzw_encode(zlib.compress(d), 1),
            "filter array LZW then Flate")
    variant("n4_runlength", "/Filter /RunLengthDecode", run_length, "RunLength")
    enc = (outdir / "n2_encrypted.pdf").read_bytes()
    note = {"code": "pdf_check_skipped", "packages": ["pdf"],
            "message": "pdf layout check stopped (encrypted) before pg1"}
    add("n4_encrypted", "N4", enc, "fulldoc", B1, expected={"items": [note], "log": [], "lines": []},
        note="RC4 copy: the skip note")


# --- N5: geometry -----------------------------------------------------------------------------------
def poly(points, op="S"):
    head = f"{points[0][0]} {points[0][1]} m " + " ".join(f"{x} {y} l" for x, y in points[1:])
    return f"0.5 w {head} h {op}\n"


def n5():
    # (a) text_escapes_node: node outlines that are not valid simple polygons
    nodes = {
        "bowtie": poly([(100, 600), (220, 640), (220, 600), (100, 640)]),
        "touch8": poly([(100, 600), (160, 640), (220, 600), (160, 640), (100, 640), (160, 600)][:5]),
        "pentagram": poly([(160, 650), (190, 580), (110, 625), (210, 625), (130, 580)]),
        "zero_area": poly([(100, 600), (160, 600), (220, 600), (160, 600)]),
        "collinear_diag": poly([(100, 600), (160, 620), (220, 640), (160, 620)]),
        "dup_vertices": poly([(100, 600), (100, 600), (220, 600), (220, 600), (220, 640), (100, 640), (100, 640)]),
        "spike": poly([(100, 600), (220, 600), (220, 640), (160, 640), (160, 700), (160, 640), (100, 640)]),
    }
    words = text(150, 612, "Escaping label wide") + text(105, 628, "in")
    for name, shape in nodes.items():
        add(f"n5_reg_node_{name}", "N5", pdf_bytes([shape + words]), "fulldoc", B1, note=f"node outline: {name}")
    # (b) label_on_stroke: where the representative point of the crossing lies against a white cover
    strokes = "0.5 w 60 604 m 300 604 l S\n"
    label = text(100, 600, "Pressure")
    for edge in (100.0, 105.0, 110.0, 118.5, 122.5, 127.0, 130.0, 135.0, 140.0, 150.0, 160.0):
        cover = f"1 g {edge} 595 60 16 re f 0 g\n"
        name = f"n5_reg_white_edge_{str(edge).replace('.', 'p')}"
        add(name, "N5", pdf_bytes([strokes + cover + label]), "fulldoc", B1, note=f"white cover starting at x={edge}")
    for edge in (100.0, 110.0, 120.0, 130.0, 140.0):
        cover = f"1 g {edge} 595 20 16 re f 0 g\n"
        add(f"n5_reg_white_narrow_{int(edge)}", "N5", pdf_bytes([strokes + cover + label]), "fulldoc", B1,
            note=f"narrow white cover at x={edge}")
    bow_white = "1 g 95 595 m 165 615 l 165 595 l 95 615 l h f 0 g\n"
    add("n5_reg_white_bowtie", "N5", pdf_bytes([strokes + bow_white + label]), "fulldoc", B1,
        note="invalid (bow-tie) white cover falls back to its bounding box")
    diag = "0.5 w 70 590 m 260 620 l S\n"
    add("n5_reg_stroke_diagonal", "N5", pdf_bytes([diag + label]), "fulldoc", B1, note="diagonal stroke through a word")
    multi = "0.5 w 60 604 m 300 604 l S 0.5 w 118 590 m 118 620 l S\n"
    add("n5_reg_stroke_cross", "N5", pdf_bytes([multi + label]), "fulldoc", B1, note="two strokes cross one word")
    zig = "0.5 w 60 596 m 110 606 l 150 598 l 200 606 l S\n"
    add("n5_reg_stroke_zigzag", "N5", pdf_bytes([zig + label]), "fulldoc", B1, note="polyline stroke, several pieces in the core")
    # (c) kNN: equidistant neighbours
    grid = "".join(text(72 + 24 * i, 700 - 24 * j, "o") for i in range(8) for j in range(8))
    add("n5_reg_knn_grid8", "N5", pdf_bytes([grid]), "fulldoc", B1, note="8x8 grid of single glyphs, every neighbour ring tied")
    tight = "".join(text(72 + 6.5 * i, 700 - 14 * j, "o") for i in range(30) for j in range(3))
    add("n5_reg_knn_rows", "N5", pdf_bytes([tight]), "fulldoc", B1, note="rows of evenly spaced glyphs, ties at k=12 and k=24")
    ring = "".join(text(300 + 40 * c_, 500 + 40 * s_, "x") for c_, s_ in
                   [(1, 0), (0, 1), (-1, 0), (0, -1), (0.7071067811865476, 0.7071067811865476),
                    (-0.7071067811865476, 0.7071067811865476), (-0.7071067811865476, -0.7071067811865476),
                    (0.7071067811865476, -0.7071067811865476)]) + text(300, 500, "x")
    add("n5_reg_knn_ring", "N5", pdf_bytes([ring]), "fulldoc", B1, note="a hub glyph with eight glyphs at one distance")
    dup = text(100, 600, "same") + text(100, 600, "same") + text(100, 600, "same") + text(130, 600, "word")
    add("n5_reg_knn_duplicates", "N5", pdf_bytes([dup]), "fulldoc", B1, note="exactly duplicated glyph centres")


    # Found by fuzzing (scripts exploring random outlines): the reference and the 019be7a7
    # binary disagree on these. Content streams are kept literally so the cases do not depend on
    # a random generator.
    gap = {
        "node_invalid_a": "0.5 w 109 609 m 206 625 l 135 613 l 101 598 l 191 648 l h S\nBT /F1 10 Tf 111 599 Td (in) Tj ET\n",
        "node_invalid_b": "0.5 w 172 607 m 209 619 l 184 646 l 195 597 l h S\nBT /F1 10 Tf 151 596 Td (Escaping label wide) Tj ET\n",
        "node_invalid_c": "0.5 w 104 634 m 201 608 l 176 645 l 198 659 l 214 639 l h S\nBT /F1 10 Tf 132 636 Td (Escaping label wide) Tj ET\n",
        "node_invalid_d": "0.5 w 191 601 m 169 649 l 210 625 l 180 600 l 127 631 l 133 602 l h S\nBT /F1 10 Tf 119 641 Td (Escaping label wide) Tj ET\n",
        "node_invalid_e": "0.5 w 110 640 m 200 650 l 120 630 l 220 610 l 110 640 l 130 630 l h S\nBT /F1 10 Tf 168 622 Td (Label) Tj ET\n",
        "node_invalid_f": "0.5 w 149 591 m 114 623 l 161 601 l 208 646 l 136 658 l 172 655 l h S\nBT /F1 10 Tf 129 599 Td (Label) Tj ET\n",
        "white_invalid_a": "0.5 w 60 602 m 160 602 l S\n1 g 105 620 m 145 595 l 120 590 l 120 590 l h f\n0 g\nBT /F1 10 Tf 100 600 Td (Ab) Tj ET\n",
        "white_invalid_b": "0.5 w 100 602 m 160 602 l S\n1 g 140 610 m 140 620 l 170 600 l 100 590 l 100 590 l h f\n0 g\nBT /F1 10 Tf 100 600 Td (Pressure) Tj ET\n",
        "white_invalid_c": "0.5 w 120 600 m 160 600 l S\n1 g 130 590 m 110 610 l 110 610 l 100 620 l 160 590 l h f\n0 g\nBT /F1 10 Tf 100 600 Td (Pressure) Tj ET\n",
    }
    for name, content in gap.items():
        add(f"n5_gap_{name}", "N5", pdf_bytes([content]), "fulldoc", B1,
            note="invalid outline: buffer(0) repair / is_valid fallback decides the finding")


n2()
n3()
n4()
n5()
(outdir / "manifest.json").write_text(json.dumps(CASES, indent=1) + "\n")
print(f"{len(CASES)} cases written to {outdir}")
