# Parity with the Python checker (ENDLEAF-R81)

Reference: `colophon/pdf_layout_check.py` at master `0ab481a` with the pinned wheels
(pdfminer.six 20260107, shapely 2.2.0, scipy 1.17.1, numpy 2.4.6), Python 3.11. Both
checkers ran with budgets lifted (`--page-budget 1e9 --doc-budget 1e9`). Reproduce with
`scripts/run_parity.sh`.

## 1. Findings on the 21 sample PDFs (`scripts/compare.py`)

An item matches when code, page and overMm are equal and each box edge is within 0.5 pt;
messages and worker log lines (`pdfcheck guard`, `offpage`, `noblock`) are compared exactly.
Required result holds: exactly one `pdf_margin_escape` on
`examples/gitlab_ci/Dossier_Eleve.pdf` page 4 with overMm 1.8 (box `[85.4, 62.1, 617.0, 74.1]`,
same message), and no findings on the other 20.

| pdf                                                    | py items | rust items | matched | result | messages | log |
|--------------------------------------------------------|----------|------------|---------|--------|----------|-----|
| examples/basic_curl_cli/sample.pdf                     | 0        | 0          | 0       | ok     | yes      | yes |
| examples/bibtex/biblatex_sample.pdf                    | 0        | 0          | 0       | ok     | yes      | yes |
| examples/bibtex/bibtex_sample.pdf                      | 0        | 0          | 0       | ok     | yes      | yes |
| examples/bibtex/natlib_sample.pdf                      | 0        | 0          | 0       | ok     | yes      | yes |
| examples/gitlab_ci/Dossier_Eleve.pdf                   | 1        | 1          | 1       | ok     | yes      | yes |
| examples/httpie_multipart/sample.pdf                   | 0        | 0          | 0       | ok     | yes      | yes |
| samples/eps-include/hbghlyj-sample.pdf                 | 0        | 0          | 0       | ok     | yes      | yes |
| samples/invoices/mrzool-boilerplate/output-pandoc.pdf  | 0        | 0          | 0       | ok     | yes      | yes |
| samples/invoices/mrzool-boilerplate/output-xelatex.pdf | 0        | 0          | 0       | ok     | yes      | yes |
| samples/quotes/mrzool-inspired/output-pandoc.pdf       | 0        | 0          | 0       | ok     | yes      | yes |
| samples/quotes/mrzool-inspired/output-xelatex.pdf      | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/biblatex_biber/sample.pdf                | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_context/sample.pdf                 | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_japanese/sample.pdf                | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_world-concurrent/sample.pdf        | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_world-lualatex/sample.pdf          | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_world-multipart/sample.pdf         | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_world-pdflatex/sample.pdf          | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_world-xelatex/sample.pdf           | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_worldmultipart/sample.pdf          | 0        | 0          | 0       | ok     | yes      | yes |
| tests/samples/hello_worldquerystring/sample.pdf        | 0        | 0          | 0       | ok     | yes      | yes |

21/21 PDFs agree

## 2. Internals: glyphs, words, lines (`scripts/py_dump.py` vs `--dump`)

Per page: glyph, word, line and path counts, and each line's text and box (a Python line
matches a Rust line with the same text and box edges within 0.5 pt, order-free).

| pdf | pages | pages with count diffs | py lines | py lines unmatched | rust lines unmatched |
|---|---|---|---|---|---|
| examples/basic_curl_cli/sample.pdf | 1 | 0 | 35 | 0 | 0 |
| examples/bibtex/biblatex_sample.pdf | 1 | 0 | 14 | 0 | 0 |
| examples/bibtex/bibtex_sample.pdf | 1 | 0 | 18 | 0 | 0 |
| examples/bibtex/natlib_sample.pdf | 1 | 0 | 15 | 0 | 0 |
| examples/gitlab_ci/Dossier_Eleve.pdf | 4 | 0 | 129 | 0 | 0 |
| examples/httpie_multipart/sample.pdf | 1 | 0 | 34 | 0 | 0 |
| samples/eps-include/hbghlyj-sample.pdf | 1 | 0 | 1 | 0 | 0 |
| samples/invoices/mrzool-boilerplate/output-pandoc.pdf | 1 | 0 | 36 | 0 | 0 |
| samples/invoices/mrzool-boilerplate/output-xelatex.pdf | 1 | 0 | 36 | 0 | 0 |
| samples/quotes/mrzool-inspired/output-pandoc.pdf | 3 | 0 | 101 | 0 | 0 |
| samples/quotes/mrzool-inspired/output-xelatex.pdf | 3 | 0 | 96 | 0 | 0 |
| tests/samples/biblatex_biber/sample.pdf | 1 | 0 | 14 | 0 | 0 |
| tests/samples/hello_context/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_japanese/sample.pdf | 1 | 0 | 9 | 0 | 0 |
| tests/samples/hello_world-concurrent/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_world-lualatex/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_world-multipart/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_world-pdflatex/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_world-xelatex/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_worldmultipart/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| tests/samples/hello_worldquerystring/sample.pdf | 1 | 0 | 2 | 0 | 0 |
| total | 28 | 0 | 554 | 0 | 0 |

## 3. Synthetic cases from the tests (`scripts/synth_cases.py`)

The constructed PDFs of `tests/colophon/test_pdf_layout_check_r81.py` (its `pdf()`,
`text()`, `body()` helpers, base-14 Helvetica), with their template, blocks and TeX pages
in a sidecar JSON. "items agree" also compares box, overMm, message, regionCount and count.
The budget-overrun and late-clock tests use an injected clock in Python and cannot be
replayed against a real clock; `budget_two_pages` runs the same PDF with budgets lifted,
and the skip note text is covered by the unit test `budget_skip_message_matches_python`.

| case | template | python codes | rust codes | codes agree | items agree | log agrees |
|---|---|---|---|---|---|---|
| clean_page | fulldoc | - | - | yes | yes | yes |
| margin_escape | fulldoc | pdf_margin_escape | pdf_margin_escape | yes | yes | yes |
| margin_escape_noblock | fulldoc | - | - | yes | yes | yes |
| caption_overlap | fulldoc | pdf_caption_overlap | pdf_caption_overlap | yes | yes | yes |
| label_on_stroke | fulldoc | pdf_label_on_stroke | pdf_label_on_stroke | yes | yes | yes |
| label_on_stroke_white_cover | fulldoc | - | - | yes | yes | yes |
| text_escapes_node | fulldoc | pdf_label_on_stroke,pdf_text_escapes_node | pdf_label_on_stroke,pdf_text_escapes_node | yes | yes | yes |
| text_inside_node | fulldoc | - | - | yes | yes | yes |
| text_overlap | fulldoc | pdf_text_overlap | pdf_text_overlap | yes | yes | yes |
| text_overlap_extensible | fulldoc | - | - | yes | yes | yes |
| label_gutter_sysml | sysml | pdf_label_gutter | pdf_label_gutter | yes | yes | yes |
| label_gutter_plots | plots | - | - | yes | yes | yes |
| stray_source_shell | document-shell | pdf_stray_source,pdf_stray_source | pdf_stray_source,pdf_stray_source | yes | yes | yes |
| stray_source_plots | plots | - | - | yes | yes | yes |
| empty_page_inside | fulldoc | pdf_empty_page | pdf_empty_page | yes | yes | yes |
| empty_page_drawn | fulldoc | - | - | yes | yes | yes |
| empty_page_last_words | fulldoc | - | - | yes | yes | yes |
| empty_page_last_blank | fulldoc | pdf_empty_page | pdf_empty_page | yes | yes | yes |
| warning_item | fulldoc | pdf_margin_escape | pdf_margin_escape | yes | yes | yes |
| cap_at_ten | fulldoc | pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_more_findings | pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_margin_escape,pdf_more_findings | yes | yes | yes |
| dedupe_three | fulldoc | pdf_margin_escape | pdf_margin_escape | yes | yes | yes |
| dedupe_tex_pages | fulldoc | - | - | yes | yes | yes |
| offpage_dropped | fulldoc | - | - | yes | yes | yes |
| docstrum_guard | fulldoc | - | - | yes | yes | yes |
| budget_two_pages | fulldoc | pdf_margin_escape | pdf_margin_escape | yes | yes | yes |
| garbage | fulldoc | pdf_check_skipped | pdf_check_skipped | yes | yes | yes |

26/26 cases agree on codes

## Ported

Everything the checker uses: extraction (text matrix x CTM, font size, Tc/Tw/Tz/Ts, TJ
kerning, simple-font `/Widths`+`/FirstChar`+`MissingWidth`, CID `/W` + `/DW`, base-14 AFM
widths by character, Type 3 `/FontMatrix` scales and `FontBBox` descent, descriptor
descent forced negative, ToUnicode bfchar/bfrange/cidrange, standard/WinAnsi/MacRoman/
PDFDoc encodings with Differences and glyph-name fallbacks (`uniXXXX`, `uXXXX`, ligature
`_` names), the built-in encoding of an embedded Type 1 program, Adobe-Japan1 for CID fonts
without ToUnicode, `(cid:N)` for undefined codes, NFKC and Python `isspace` blank test);
paths split at each `m` the way pdfminer does, `re` as `mlllh`, Beziers (`c`/`v`/`y`) cut to
8 chords, stroke/fill flags, non-stroking colour and the white test (gray, RGB, CMYK,
uncolored patterns), images (XObject and inline `BI/ID/EI`) as filled boxes, Form XObject
recursion with pdfminer's fresh state per form and its loop guard, page rotation and
MediaBox offset, off-page glyph drop and count, z (paint order) counted like pdfminer's
layout items; `_link` (kNN, cost along the baseline over the smaller size, single-linkage
components), words, lines, Docstrum guard with numpy's histogram binning and pairwise
sums, glyph runs, the folio rule, figure regions, all eight checks, `dedupe`, `item_for`
rounding, `MAX_FINDINGS` and `pdf_more_findings`, budgets and `pdf_check_skipped`.

## Not ported / known deviations

- Placement fields: `partId` (layout marks) and `fenceNumber` (shell pages) have no CLI
  input yet; items never carry them. `--tex-pages` (OD-PDF-4) is supported.
- `_count_blocks` is not ported: the Python module defines it but never calls it.
- Predefined CJK CMaps other than `Identity-H/V` and `OneByteIdentityH/V` (for example
  `UniJIS-UCS2-H`) decode to nothing, so such text is dropped (pdfminer would load them).
- CID fonts without ToUnicode: only Adobe-Japan1 is mapped; GB1, CNS1, Korea1 and the
  TrueType `cmap` fallback for Adobe-Identity fonts give `(cid:N)` text (geometry is the
  same; only text-based rules such as captions, folios and stray source could differ).
- Filters (ENDLEAF-R82-DECODE): Flate, LZW, RunLength, ASCIIHex and ASCII85, in filter
  arrays, with the PNG (>= 10) and TIFF 2 predictors from DecodeParms. LZW follows pdfminer's
  decoder (257 skipped, an unknown code ends the stream) and honours `/EarlyChange 0`, which
  pdfminer ignores; the gap fixtures expect the correct (Flate twin) output there. TIFF 2
  with other than 8 bits per component, and truncated RunLength runs, keep what they have
  where pdfminer raises. DCT, JPX, JBIG2 and CCITT stay encoded (images are boxes only).
  Encrypted PDFs stop with `error PDFEncryptionError` (no decryption; the CLI maps that to
  the encrypted skip note).
- Geometry stands in for GEOS: invalid node outlines are used as drawn instead of
  `buffer(0)`; `is_valid` is a simple ring test; the point used for the white-cover test
  of `pdf_label_on_stroke` follows GEOS InteriorPointLine on merged pieces, but may differ
  in the last bits; boundary-only contacts may differ in exactly degenerate cases.
- kNN ties: cKDTree's order among equidistant neighbours is not specified; Rust breaks
  ties by index. Only the k-th neighbour boundary and exact duplicate centres can differ.
- Exception names in `pdf_check_skipped` notes follow pdfminer's for the common cases
  (`PDFSyntaxError`); other Python exceptions (assertions on bad octal escapes, odd
  dictionary tokens) are tolerated in Rust instead of stopping the check.
- Vertical writing (`Identity-V`) advances along y as pdfminer does, but the glyph quad is
  the same horizontal formula as the Python `add_glyph`; not exercised by the corpus.
- `cargo fmt --check` and `cargo clippy --release -- -D warnings` are clean on Rust 1.100
  (aarch64); the first commit was built on 1.85 without them.
