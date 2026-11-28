# Timing on the ARM build host (ENDLEAF-R81 Rust prototype, now endleaf-pdfcheck)

Host: ARM64 board (4x Cortex-A76 at 2.4 GHz, ondemand governor), 15 GiB RAM, NVMe,
Debian 13, glibc 2.41. The same board model as the worker; Python on it matches the worker
image's measured 0.92 s for `Dossier_Eleve.pdf`.

- Python: 3.11.18 in a venv with the hashed pins from `container/pdfcheck-requirements.txt`
  (shapely 2.2.0, pdfminer.six 20260107, scipy 1.17.1, numpy 2.4.6; cp311 aarch64 wheels),
  `colophon/pdf_layout_check.py` at master `0ab481a`.
- Rust: this crate, rustc 1.100.0 aarch64, release profile, dynamic glibc.
- Method (`scripts/bench_arm.py`, `scripts/pyone.py`): budgets lifted (1e9) so every page is
  timed. **Cold** = a fresh process per PDF, 3 runs, median; "check" is the in-process
  `check_pdf` time, "process" the whole process wall time (Python: interpreter + imports +
  preload + check). **Warm** = one process running the check 4 times on the same bytes; the
  first run is dropped and the median of the other 3 is shown. The page cache was warm in
  every run (no root to drop it). **Loaded** = the same with 3 busy-loop processes pinning
  the other 3 cores (load average reached 3.6). The idle run started at load 1.2, the tail of
  the release build that had just finished.
- "default budget" = a separate run at the shipped budgets (0.25 s/page, 2.0 s/doc).

## Idle (loadavg start 1.21 0.73 0.32, end 1.06 0.79 0.38, temp=62.6'C)

| PDF | pages | Py cold check s | Py cold process s | Py warm s | Py s/page (warm) | Rust cold check s | Rust cold process s | Rust warm s | Rust s/page (warm) | Rust max page s | speedup warm | default budget Py / Rust |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| examples/basic_curl_cli/sample.pdf | 1 | 0.105 | 0.754 | 0.103 | 0.1027 | 0.0046 | 0.0059 | 0.0030 | 0.00303 | 0.0043 | 34x | ok / ok |
| examples/bibtex/biblatex_sample.pdf | 1 | 0.095 | 0.733 | 0.091 | 0.0910 | 0.0050 | 0.0063 | 0.0034 | 0.00338 | 0.0046 | 27x | ok / ok |
| examples/bibtex/bibtex_sample.pdf | 1 | 0.116 | 0.770 | 0.115 | 0.1151 | 0.0054 | 0.0068 | 0.0039 | 0.00388 | 0.0052 | 30x | ok / ok |
| examples/bibtex/natlib_sample.pdf | 1 | 0.087 | 0.712 | 0.084 | 0.0840 | 0.0045 | 0.0059 | 0.0030 | 0.00298 | 0.0043 | 28x | ok / ok |
| examples/gitlab_ci/Dossier_Eleve.pdf | 4 | 0.898 | 2.060 | 0.904 | 0.2261 | 0.0248 | 0.0262 | 0.0230 | 0.00574 | 0.0083 | 39x | skip / ok |
| examples/httpie_multipart/sample.pdf | 1 | 0.105 | 0.747 | 0.101 | 0.1014 | 0.0045 | 0.0058 | 0.0030 | 0.00301 | 0.0042 | 34x | ok / ok |
| samples/eps-include/hbghlyj-sample.pdf | 1 | 0.010 | 0.558 | 0.009 | 0.0087 | 0.0018 | 0.0030 | 0.0003 | 0.00032 | 0.0017 | 27x | ok / ok |
| samples/invoices/mrzool-boilerplate/output-pandoc.pdf | 1 | 0.105 | 0.751 | 0.103 | 0.1030 | 0.0046 | 0.0059 | 0.0030 | 0.00301 | 0.0043 | 34x | ok / ok |
| samples/invoices/mrzool-boilerplate/output-xelatex.pdf | 1 | 0.103 | 0.747 | 0.100 | 0.0999 | 0.0045 | 0.0058 | 0.0029 | 0.00293 | 0.0042 | 34x | ok / ok |
| samples/quotes/mrzool-inspired/output-pandoc.pdf | 3 | 0.429 | 1.395 | 0.425 | 0.1416 | 0.0141 | 0.0155 | 0.0124 | 0.00414 | 0.0050 | 34x | ok / ok |
| samples/quotes/mrzool-inspired/output-xelatex.pdf | 3 | 0.432 | 1.409 | 0.433 | 0.1442 | 0.0142 | 0.0155 | 0.0125 | 0.00416 | 0.0052 | 35x | ok / ok |
| tests/samples/biblatex_biber/sample.pdf | 1 | 0.084 | 0.702 | 0.081 | 0.0805 | 0.0041 | 0.0054 | 0.0025 | 0.00255 | 0.0038 | 32x | ok / ok |
| tests/samples/hello_context/sample.pdf | 1 | 0.009 | 0.545 | 0.007 | 0.0070 | 0.0016 | 0.0028 | 0.0002 | 0.00016 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_japanese/sample.pdf | 1 | 0.049 | 0.612 | 0.028 | 0.0280 | 0.0046 | 0.0060 | 0.0010 | 0.00097 | 0.0043 | 29x | ok / ok |
| tests/samples/hello_world-concurrent/sample.pdf | 1 | 0.008 | 0.545 | 0.006 | 0.0061 | 0.0016 | 0.0029 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_world-lualatex/sample.pdf | 1 | 0.008 | 0.554 | 0.006 | 0.0062 | 0.0016 | 0.0029 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_world-multipart/sample.pdf | 1 | 0.008 | 0.543 | 0.006 | 0.0062 | 0.0016 | 0.0028 | 0.0001 | 0.00014 | 0.0015 | 45x | ok / ok |
| tests/samples/hello_world-pdflatex/sample.pdf | 1 | 0.011 | 0.553 | 0.009 | 0.0087 | 0.0018 | 0.0030 | 0.0003 | 0.00031 | 0.0017 | 28x | ok / ok |
| tests/samples/hello_world-xelatex/sample.pdf | 1 | 0.008 | 0.547 | 0.006 | 0.0061 | 0.0016 | 0.0028 | 0.0002 | 0.00017 | 0.0015 | 36x | ok / ok |
| tests/samples/hello_worldmultipart/sample.pdf | 1 | 0.008 | 0.543 | 0.006 | 0.0063 | 0.0016 | 0.0028 | 0.0001 | 0.00014 | 0.0014 | 45x | ok / ok |
| tests/samples/hello_worldquerystring/sample.pdf | 1 | 0.008 | 0.546 | 0.006 | 0.0062 | 0.0016 | 0.0028 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| **all 21** | 28 | 2.69 | 16.33 | 2.63 | 0.0939 | 0.110 | 0.137 | 0.075 | 0.00269 | | 35x | |

Python import + preload (outside the budget), median of 63 fresh processes: 0.398 s.
Findings diff (idle): 0 differences. Both: exactly one pdf_margin_escape on Dossier_Eleve.pdf p4, overMm 1.8, box [85.4, 62.1, 617.0, 74.1], identical message; 20 PDFs clean.

## Loaded (3 cores busy) (loadavg start 1.06 0.79 0.38, end 3.59 1.68 0.73, temp=70.3'C)

| PDF | pages | Py cold check s | Py cold process s | Py warm s | Py s/page (warm) | Rust cold check s | Rust cold process s | Rust warm s | Rust s/page (warm) | Rust max page s | speedup warm | default budget Py / Rust |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| examples/basic_curl_cli/sample.pdf | 1 | 0.105 | 0.835 | 0.103 | 0.1028 | 0.0045 | 0.0076 | 0.0030 | 0.00298 | 0.0042 | 35x | ok / ok |
| examples/bibtex/biblatex_sample.pdf | 1 | 0.095 | 0.816 | 0.090 | 0.0899 | 0.0050 | 0.0066 | 0.0034 | 0.00338 | 0.0046 | 27x | ok / ok |
| examples/bibtex/bibtex_sample.pdf | 1 | 0.118 | 0.864 | 0.114 | 0.1139 | 0.0055 | 0.0071 | 0.0039 | 0.00391 | 0.0052 | 29x | ok / ok |
| examples/bibtex/natlib_sample.pdf | 1 | 0.087 | 0.791 | 0.083 | 0.0828 | 0.0046 | 0.0062 | 0.0030 | 0.00298 | 0.0043 | 28x | ok / ok |
| examples/gitlab_ci/Dossier_Eleve.pdf | 4 | 0.903 | 2.148 | 0.902 | 0.2255 | 0.0248 | 0.0266 | 0.0230 | 0.00576 | 0.0083 | 39x | skip / ok |
| examples/httpie_multipart/sample.pdf | 1 | 0.105 | 0.840 | 0.103 | 0.1027 | 0.0045 | 0.0061 | 0.0030 | 0.00299 | 0.0042 | 34x | ok / ok |
| samples/eps-include/hbghlyj-sample.pdf | 1 | 0.010 | 0.641 | 0.009 | 0.0086 | 0.0017 | 0.0033 | 0.0003 | 0.00033 | 0.0016 | 26x | ok / ok |
| samples/invoices/mrzool-boilerplate/output-pandoc.pdf | 1 | 0.105 | 0.827 | 0.103 | 0.1027 | 0.0045 | 0.0062 | 0.0030 | 0.00300 | 0.0042 | 34x | ok / ok |
| samples/invoices/mrzool-boilerplate/output-xelatex.pdf | 1 | 0.101 | 0.826 | 0.100 | 0.0996 | 0.0044 | 0.0074 | 0.0029 | 0.00293 | 0.0042 | 34x | ok / ok |
| samples/quotes/mrzool-inspired/output-pandoc.pdf | 3 | 0.431 | 1.486 | 0.427 | 0.1423 | 0.0141 | 0.0181 | 0.0125 | 0.00416 | 0.0050 | 34x | ok / ok |
| samples/quotes/mrzool-inspired/output-xelatex.pdf | 3 | 0.431 | 1.479 | 0.429 | 0.1429 | 0.0142 | 0.0193 | 0.0125 | 0.00417 | 0.0051 | 34x | ok / ok |
| tests/samples/biblatex_biber/sample.pdf | 1 | 0.085 | 0.799 | 0.081 | 0.0807 | 0.0041 | 0.0057 | 0.0025 | 0.00254 | 0.0038 | 32x | ok / ok |
| tests/samples/hello_context/sample.pdf | 1 | 0.009 | 0.639 | 0.007 | 0.0071 | 0.0016 | 0.0032 | 0.0002 | 0.00016 | 0.0015 | 45x | ok / ok |
| tests/samples/hello_japanese/sample.pdf | 1 | 0.050 | 0.713 | 0.028 | 0.0276 | 0.0046 | 0.0063 | 0.0010 | 0.00098 | 0.0043 | 28x | ok / ok |
| tests/samples/hello_world-concurrent/sample.pdf | 1 | 0.008 | 0.639 | 0.006 | 0.0062 | 0.0016 | 0.0031 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_world-lualatex/sample.pdf | 1 | 0.008 | 0.642 | 0.006 | 0.0062 | 0.0016 | 0.0032 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_world-multipart/sample.pdf | 1 | 0.008 | 0.649 | 0.006 | 0.0062 | 0.0016 | 0.0031 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_world-pdflatex/sample.pdf | 1 | 0.011 | 0.633 | 0.009 | 0.0086 | 0.0018 | 0.0033 | 0.0003 | 0.00032 | 0.0016 | 27x | ok / ok |
| tests/samples/hello_world-xelatex/sample.pdf | 1 | 0.008 | 0.635 | 0.006 | 0.0061 | 0.0016 | 0.0032 | 0.0001 | 0.00015 | 0.0015 | 42x | ok / ok |
| tests/samples/hello_worldmultipart/sample.pdf | 1 | 0.008 | 0.630 | 0.006 | 0.0062 | 0.0016 | 0.0032 | 0.0001 | 0.00014 | 0.0015 | 44x | ok / ok |
| tests/samples/hello_worldquerystring/sample.pdf | 1 | 0.008 | 0.641 | 0.006 | 0.0061 | 0.0016 | 0.0032 | 0.0001 | 0.00014 | 0.0015 | 43x | ok / ok |
| **all 21** | 28 | 2.69 | 18.17 | 2.62 | 0.0936 | 0.109 | 0.152 | 0.075 | 0.00269 | | 35x | |

Python import + preload (outside the budget), median of 63 fresh processes: 0.487 s.
Findings diff (loaded): 0 differences. Both: exactly one pdf_margin_escape on Dossier_Eleve.pdf p4, overMm 1.8, box [85.4, 62.1, 617.0, 74.1], identical message; 20 PDFs clean.

## All 4 cores busy (4 busy loops), Dossier_Eleve.pdf only

- Python: check 1.02 / 1.08 / 1.13 / 1.13 s (4 runs), import+preload 0.61 s; at the default
  budgets it still stops with `pdf_check_skipped`.
- Rust: 0.045 s first run, then 0.023 s; slowest page 16 ms. At the default budgets it
  finishes and reports the p4 `pdf_margin_escape` (1.8 mm).

## Build

- Clean release build (crates already fetched): 39.0 s and 39.0 s (two runs); touching
  `src/main.rs` and rebuilding: 26.5 s (fat LTO relinks the whole crate).
- Binary: 2,757,552 bytes (2.6 MiB) stripped, aarch64 PIE; needs glibc 2.35 at most
  (`objdump -T`), so it also loads on Debian 12 (glibc 2.36). Links only libc, libm, libgcc_s.
- `cargo test --release` 12 passed; `cargo clippy --release -- -D warnings` and
  `cargo fmt --check` clean.
