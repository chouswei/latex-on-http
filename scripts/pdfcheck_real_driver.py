"""In-image driver for scripts/pdfcheck_real_samples.py (runs inside the render image).

Reads one job payload (argv[1]), renders it with colophon.sandbox_render exactly as the
worker does, captures the final TeX log at the point where ``_pdf_layout_check`` is called,
builds the R82-IFACE sidecar with the image's own functions (same calls as
sandbox_render.py), runs the in-image Python check twice (budgets lifted, default budgets)
and prints ONE JSON object on stdout. The worker's own stdout (the PDF) is captured.
"""
import io
import json
import sys

from colophon import sandbox_render as sr


def _items(result):
    return {"items": result.items, "log": list(result.log_lines)}


def main():
    payload = open(sys.argv[1], "rb").read()
    captured = {}

    def capture(job, data, log, body_start, body_lines):
        from colophon.layout_map import page_blocks, page_marks
        from colophon.layout_warn import layout_warnings, shell_pages
        from colophon.overfull import overfull_rows
        from colophon.pdf_layout_check import check_pdf

        warnings = layout_warnings(log)
        rows, _ = overfull_rows(log, body_start=body_start, body_lines=body_lines)
        named = {row["page"] for row in rows if "page" in row}
        named |= {i["page"] for i in warnings if isinstance(i.get("page"), int)}
        blocks = page_blocks(log)
        marks = page_marks(log) if job.template_id == "fulldoc" else None
        shells = shell_pages(log)
        sidecar = {
            "templateId": job.template_id,
            "blocks": {str(p): list(v) for p, v in sorted(blocks.items())},
            "shellPages": {str(n): p for n, p in sorted(shells.items())},
            "texPages": sorted(named),
        }
        if marks is not None:
            sidecar["marks"] = marks
        kw = dict(
            template_id=job.template_id,
            blocks=blocks,
            marks=marks,
            shell_pages=shells,
            tex_pages=named,
        )
        captured["sidecar"] = sidecar
        captured["lifted"] = _items(check_pdf(data, page_budget=1e9, document_budget=1e9, **kw))
        captured["default"] = _items(check_pdf(data, **kw))
        captured["texLogLines"] = log.count("\n")
        captured["pageblockLines"] = log.replace("\n", "").count("ENDLEAF_PAGEBLOCK")

    sr._pdf_layout_check = capture
    real_stdout = sys.stdout
    sink = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    sys.stdout = sink
    try:
        code = sr.render_to_stdout(payload)
    finally:
        sys.stdout = real_stdout
    sink.flush()
    pdf = sink.buffer.getvalue()
    import base64

    pages = None
    try:
        from pdfminer.pdfpage import PDFPage

        pages = len(list(PDFPage.get_pages(io.BytesIO(pdf))))
    except Exception:
        pass
    out = {"exit": code, "pages": pages, "pdfBase64": base64.b64encode(pdf).decode("ascii")}
    out.update(captured)
    real_stdout.write(json.dumps(out))


main()
