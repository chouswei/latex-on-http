# pdfcheck-real: real worker output for the Rust PDF layout checker (ENDLEAF-R82 probe)

- image: localhost/endleaf-render:libs, id b9b6488c9166, ENDLEAF_GIT_COMMIT b848df94d33d2a28e8f55acb9c2ff5496d3c97ec
- generated: 2026-11-28 by scripts/pdfcheck_real_samples.py
- python-lifted.json: colophon.pdf_layout_check.check_pdf in the image with budgets lifted;
  python-default.json: default budgets (0.25 s per page, 2.0 s per document). Both are `{items, log}`.
- sidecar.json: R82-IFACE shape, built in the image with page_blocks, page_marks (fulldoc only),
  shell_pages and texPages = overfull-row pages | layout-warning pages.

| sample | kind | pages | findings lifted | findings default | pdf bytes | skips |
|---|---|---|---|---|---|---|
| sysml-interconnection | sysml | 1 | 0 | 0 | 12528 | - |
| shell-label-on-stroke | document-shell | 1 | 1 | 1 | 9581 | - |
| shell-tikz-and-code | document-shell | 1 | 0 | 0 | 15515 | - |
| shell-long-code-line | document-shell | 1 | 2 | 2 | 10028 | - |
| fulldoc-two-parts | fulldoc | 2 | 0 | 0 | 11291 | - |
| fulldoc-overhang | fulldoc | 4 | 1 | 1 | 15768 | - |
| stocklabel | stocklabel | 1 | 0 | 0 | 20538 | - |
| circuits | circuits | 1 | 0 | 0 | 2309 | - |
| plots | plots | 1 | 0 | 0 | 11655 | - |
| pidcircuit | pidcircuit | 1 | 0 | 0 | 2294 | - |
| shell-zh-tw | document-shell | 1 | 0 | 0 | 21448 | - |
| shell-zh-cn | document-shell | 1 | 0 | 0 | 19815 | - |
| shell-ko | document-shell | 1 | 0 | 0 | 16728 | - |
| shell-ja | document-shell | 1 | 0 | 0 | 21199 | - |
| shell-landscape | document-shell | 1 | 0 | 0 | 9558 | - |
- skips: none of the 15 samples hit pdf_check_skipped under either budget; shell-landscape and sysml-interconnection are landscape pages (blocks width > height).
