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
- (prototype) `cargo test --release` 12 passed; `cargo clippy --release -- -D warnings` and
  `cargo fmt --check` clean.


## R82: worker-shaped run with the real samples (36 PDFs, 3 rounds)

Same 4-core ARM64 board type, rustc 1.100.0, `cargo build --release --locked` in 42 s,
binary 3,413,336 bytes (the CJK data adds about 0.6 MB), glibc 2.35 at most.
Rust = one `endleaf-pdfcheck` process per PDF (wall time including process start), default
budgets, real samples through `--sidecar`. Python = the reference oracle
`colophon/pdf_layout_check.py` with the hashed pins in a long-lived process with the
libraries preloaded (how the R81 worker ran it). **Loaded** = 4 checker workers in parallel
(each runs both checkers) plus 2 busy loops at nice 10 standing in for the TeX pass.
"Codes equal NO" rows are Python stopping at the default budget (`pdf_check_skipped`);
the binary never hit a budget, and with budgets lifted the findings are identical (parity
test). "Rust max page s" is the slowest page from `--timing`.

| mode | Rust proc s median / max | Rust slowest page s | Rust budget hits | Python check s median / max | Python budget hits |
|---|---|---|---|---|---|
| idle | 0.004 / 0.026 | 0.009 | 0 / 108 | 0.031 / 0.641 | 7 / 108 |
| loaded | 0.009 / 0.058 | 0.018 | 0 / 432 | 0.039 / 0.580 | 50 / 432 |

### idle (1 checker x 3 rounds; load ['0.76', '0.28', '0.10'] -> ['0.80', '0.31', '0.11']; wall 12.4 s)
| PDF | pages | Rust proc s (median/max) | Rust max page s | Python check s (median/max) | Python s/page | speed-up | budget hits rs/py | codes equal |
|---|---|---|---|---|---|---|---|---|
| basic_curl_cli | 1 | 0.006/0.006 | 0.004 | 0.105/0.105 | 0.105 | 17.6x | 0/0 | yes |
| bibtex | 1 | 0.006/0.006 | 0.005 | 0.093/0.093 | 0.093 | 14.6x | 0/0 | yes |
| bibtex | 1 | 0.007/0.007 | 0.005 | 0.117/0.118 | 0.117 | 17.1x | 0/0 | yes |
| bibtex | 1 | 0.006/0.006 | 0.004 | 0.085/0.087 | 0.085 | 14.3x | 0/0 | yes |
| gitlab_ci | 4 | 0.026/0.026 | 0.008 | 0.607/0.641 | 0.152 | 22.9x | 0/3 | NO |
| httpie_multipart | 1 | 0.006/0.006 | 0.004 | 0.103/0.104 | 0.103 | 17.7x | 0/0 | yes |
| eps-include | 1 | 0.003/0.003 | 0.002 | 0.009/0.010 | 0.009 | 3.0x | 0/0 | yes |
| mrzool-boilerplate | 1 | 0.006/0.006 | 0.004 | 0.103/0.104 | 0.103 | 17.6x | 0/0 | yes |
| mrzool-boilerplate | 1 | 0.006/0.006 | 0.004 | 0.103/0.139 | 0.103 | 17.6x | 0/0 | yes |
| mrzool-inspired | 3 | 0.016/0.016 | 0.005 | 0.436/0.439 | 0.145 | 28.1x | 0/0 | yes |
| mrzool-inspired | 3 | 0.016/0.016 | 0.005 | 0.434/0.479 | 0.145 | 27.8x | 0/0 | yes |
| biblatex_biber | 1 | 0.005/0.005 | 0.004 | 0.082/0.082 | 0.082 | 15.2x | 0/0 | yes |
| hello_context | 1 | 0.003/0.003 | 0.002 | 0.008/0.008 | 0.008 | 2.5x | 0/0 | yes |
| hello_japanese | 1 | 0.008/0.008 | 0.006 | 0.030/0.048 | 0.030 | 3.8x | 0/0 | yes |
| hello_world-concurrent | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.3x | 0/0 | yes |
| hello_world-lualatex | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.2x | 0/0 | yes |
| hello_world-multipart | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.3x | 0/0 | yes |
| hello_world-pdflatex | 1 | 0.003/0.003 | 0.002 | 0.009/0.009 | 0.009 | 2.9x | 0/0 | yes |
| hello_world-xelatex | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.2x | 0/0 | yes |
| hello_worldmultipart | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.4x | 0/0 | yes |
| hello_worldquerystring | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.2x | 0/0 | yes |
| circuits | 1 | 0.003/0.003 | 0.002 | 0.006/0.006 | 0.006 | 2.2x | 0/0 | yes |
| fulldoc-overhang | 4 | 0.013/0.013 | 0.009 | 0.319/0.322 | 0.080 | 24.1x | 0/3 | NO |
| fulldoc-two-parts | 2 | 0.012/0.012 | 0.007 | 0.341/0.344 | 0.171 | 27.6x | 0/1 | NO |
| pidcircuit | 1 | 0.003/0.003 | 0.002 | 0.007/0.007 | 0.007 | 2.3x | 0/0 | yes |
| plots | 1 | 0.004/0.004 | 0.002 | 0.033/0.033 | 0.033 | 9.0x | 0/0 | yes |
| shell-ja | 1 | 0.004/0.004 | 0.002 | 0.026/0.029 | 0.026 | 7.2x | 0/0 | yes |
| shell-ko | 1 | 0.004/0.004 | 0.002 | 0.027/0.027 | 0.027 | 7.5x | 0/0 | yes |
| shell-label-on-stroke | 1 | 0.003/0.004 | 0.002 | 0.023/0.023 | 0.023 | 6.7x | 0/0 | yes |
| shell-landscape | 1 | 0.003/0.004 | 0.002 | 0.021/0.021 | 0.021 | 6.1x | 0/0 | yes |
| shell-long-code-line | 1 | 0.004/0.004 | 0.003 | 0.046/0.047 | 0.046 | 10.7x | 0/0 | yes |
| shell-tikz-and-code | 1 | 0.004/0.004 | 0.002 | 0.031/0.031 | 0.031 | 8.1x | 0/0 | yes |
| shell-zh-cn | 1 | 0.004/0.004 | 0.002 | 0.025/0.025 | 0.025 | 6.7x | 0/0 | yes |
| shell-zh-tw | 1 | 0.004/0.004 | 0.002 | 0.025/0.025 | 0.025 | 7.0x | 0/0 | yes |
| stocklabel | 1 | 0.010/0.010 | 0.009 | 0.229/0.233 | 0.229 | 22.2x | 0/0 | yes |
| sysml-interconnection | 1 | 0.004/0.004 | 0.002 | 0.040/0.041 | 0.040 | 10.2x | 0/0 | yes |
| **all 36** | | 0.004/0.026 | 0.009 | 0.031/0.641 | | 16.3x (sum) | 0/7 | 33/36 |

### loaded (4 checkers x 3 rounds; load ['0.90', '0.34', '0.12'] -> ['2.03', '0.61', '0.22']; wall 14.1 s)
| PDF | pages | Rust proc s (median/max) | Rust max page s | Python check s (median/max) | Python s/page | speed-up | budget hits rs/py | codes equal |
|---|---|---|---|---|---|---|---|---|
| basic_curl_cli | 1 | 0.009/0.022 | 0.009 | 0.123/0.162 | 0.123 | 13.3x | 0/0 | yes |
| bibtex | 1 | 0.013/0.022 | 0.009 | 0.110/0.172 | 0.110 | 8.7x | 0/0 | yes |
| bibtex | 1 | 0.011/0.018 | 0.010 | 0.140/0.199 | 0.140 | 12.6x | 0/0 | yes |
| bibtex | 1 | 0.011/0.018 | 0.009 | 0.102/0.161 | 0.102 | 9.4x | 0/0 | yes |
| gitlab_ci | 4 | 0.034/0.058 | 0.017 | 0.291/0.396 | 0.073 | 8.6x | 0/12 | NO |
| httpie_multipart | 1 | 0.012/0.018 | 0.009 | 0.124/0.172 | 0.124 | 10.5x | 0/0 | yes |
| eps-include | 1 | 0.007/0.011 | 0.002 | 0.010/0.014 | 0.010 | 1.4x | 0/0 | yes |
| mrzool-boilerplate | 1 | 0.010/0.019 | 0.012 | 0.129/0.213 | 0.129 | 12.6x | 0/0 | yes |
| mrzool-boilerplate | 1 | 0.012/0.017 | 0.009 | 0.123/0.179 | 0.123 | 9.9x | 0/0 | yes |
| mrzool-inspired | 3 | 0.022/0.036 | 0.013 | 0.504/0.580 | 0.168 | 23.1x | 0/1 | NO |
| mrzool-inspired | 3 | 0.020/0.034 | 0.011 | 0.500/0.529 | 0.167 | 24.9x | 0/3 | NO |
| biblatex_biber | 1 | 0.010/0.018 | 0.012 | 0.104/0.190 | 0.104 | 10.0x | 0/0 | yes |
| hello_context | 1 | 0.007/0.011 | 0.002 | 0.008/0.013 | 0.008 | 1.2x | 0/0 | yes |
| hello_japanese | 1 | 0.013/0.021 | 0.015 | 0.038/0.057 | 0.038 | 3.0x | 0/0 | yes |
| hello_world-concurrent | 1 | 0.007/0.012 | 0.002 | 0.007/0.011 | 0.007 | 1.1x | 0/0 | yes |
| hello_world-lualatex | 1 | 0.006/0.011 | 0.002 | 0.007/0.014 | 0.007 | 1.2x | 0/0 | yes |
| hello_world-multipart | 1 | 0.006/0.012 | 0.002 | 0.007/0.015 | 0.007 | 1.3x | 0/0 | yes |
| hello_world-pdflatex | 1 | 0.006/0.019 | 0.003 | 0.010/0.018 | 0.010 | 1.6x | 0/0 | yes |
| hello_world-xelatex | 1 | 0.008/0.011 | 0.008 | 0.007/0.015 | 0.007 | 0.9x | 0/0 | yes |
| hello_worldmultipart | 1 | 0.006/0.011 | 0.008 | 0.008/0.012 | 0.008 | 1.2x | 0/0 | yes |
| hello_worldquerystring | 1 | 0.006/0.011 | 0.002 | 0.007/0.014 | 0.007 | 1.1x | 0/0 | yes |
| circuits | 1 | 0.007/0.010 | 0.002 | 0.007/0.014 | 0.007 | 1.0x | 0/0 | yes |
| fulldoc-overhang | 4 | 0.016/0.032 | 0.018 | 0.368/0.420 | 0.092 | 23.4x | 0/12 | NO |
| fulldoc-two-parts | 2 | 0.018/0.029 | 0.016 | 0.269/0.394 | 0.135 | 15.2x | 0/12 | NO |
| pidcircuit | 1 | 0.006/0.011 | 0.002 | 0.007/0.015 | 0.007 | 1.2x | 0/0 | yes |
| plots | 1 | 0.006/0.016 | 0.007 | 0.039/0.049 | 0.039 | 6.6x | 0/0 | yes |
| shell-ja | 1 | 0.009/0.016 | 0.003 | 0.033/0.056 | 0.033 | 3.6x | 0/0 | yes |
| shell-ko | 1 | 0.008/0.011 | 0.003 | 0.035/0.057 | 0.035 | 4.6x | 0/0 | yes |
| shell-label-on-stroke | 1 | 0.007/0.011 | 0.002 | 0.029/0.051 | 0.029 | 3.9x | 0/0 | yes |
| shell-landscape | 1 | 0.006/0.010 | 0.002 | 0.027/0.106 | 0.027 | 4.3x | 0/0 | yes |
| shell-long-code-line | 1 | 0.007/0.013 | 0.007 | 0.053/0.097 | 0.053 | 7.1x | 0/0 | yes |
| shell-tikz-and-code | 1 | 0.007/0.011 | 0.006 | 0.033/0.065 | 0.033 | 5.0x | 0/0 | yes |
| shell-zh-cn | 1 | 0.007/0.013 | 0.002 | 0.028/0.050 | 0.028 | 3.8x | 0/0 | yes |
| shell-zh-tw | 1 | 0.006/0.012 | 0.002 | 0.029/0.033 | 0.029 | 4.9x | 0/0 | yes |
| stocklabel | 1 | 0.020/0.026 | 0.018 | 0.270/0.301 | 0.270 | 13.7x | 0/10 | NO |
| sysml-interconnection | 1 | 0.006/0.017 | 0.007 | 0.047/0.077 | 0.047 | 7.3x | 0/0 | yes |
| **all 36** | | 0.009/0.058 | 0.018 | 0.039/0.580 | | 9.3x (sum) | 0/50 | 30/36 |
- R82 head: `cargo fmt --check` clean and `cargo clippy --release --locked` 0 warnings on rustc 1.100.0.
