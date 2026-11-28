//! `endleaf-pdfcheck`: prototype Rust port of the ENDLEAF-R81 PDF layout checker.

mod check;
mod extract;
mod font;
mod geom;
mod pdf;
mod tables;
#[cfg(test)]
mod tests;

use check::{check_pdf, round1, Options, Page};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::time::Instant;

const USAGE: &str = "usage: endleaf-pdfcheck [--page-budget SEC] [--doc-budget SEC] [--template ID] \
[--blocks FILE.json] [--tex-pages N,N] [--repeat N] [--timing] [--dump] PDF...";

fn parse_blocks(path: &str) -> Result<HashMap<usize, [f64; 4]>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    let v: Value = serde_json::from_str(&text).map_err(|e| format!("{path}: {e}"))?;
    let mut out = HashMap::new();
    if let Value::Object(m) = v {
        for (k, b) in m {
            let page: usize = k.parse().map_err(|_| format!("{path}: bad page {k}"))?;
            let a: Vec<f64> = b
                .as_array()
                .map(|a| a.iter().filter_map(|x| x.as_f64()).collect())
                .unwrap_or_default();
            if a.len() != 4 {
                return Err(format!("{path}: page {k} needs 4 numbers"));
            }
            out.insert(page, [a[0], a[1], a[2], a[3]]);
        }
    }
    Ok(out)
}

fn dump_page(file: &str, page: &Page) -> Value {
    let lines: Vec<Value> = page
        .lines
        .iter()
        .map(|l| json!([l.text, l.bx.iter().map(|x| round1(*x)).collect::<Vec<_>>()]))
        .collect();
    json!({"file": file, "page": page.number, "glyphs": page.glyphs.len(), "words": page.words.len(),
           "lines": page.lines.len(), "paths": page.paths.len(), "line_items": lines})
}

fn main() {
    let mut args = std::env::args().skip(1);
    let mut opt = Options {
        page_budget: check::PAGE_BUDGET_SEC,
        doc_budget: check::DOCUMENT_BUDGET_SEC,
        ..Default::default()
    };
    let (mut repeat, mut timing, mut dump) = (1usize, false, false);
    let mut files = Vec::new();
    let fail = |m: String| -> ! {
        eprintln!("{m}\n{USAGE}");
        std::process::exit(2)
    };
    while let Some(a) = args.next() {
        let mut val = |name: &str| args.next().unwrap_or_else(|| fail(format!("{name} needs a value")));
        match a.as_str() {
            "--page-budget" => opt.page_budget = val(&a).parse().unwrap_or_else(|_| fail("bad --page-budget".into())),
            "--doc-budget" => opt.doc_budget = val(&a).parse().unwrap_or_else(|_| fail("bad --doc-budget".into())),
            "--template" => opt.template = val(&a),
            "--blocks" => opt.blocks = parse_blocks(&val(&a)).unwrap_or_else(|e| fail(e)),
            "--tex-pages" => {
                opt.tex_pages = val(&a)
                    .split(',')
                    .filter(|s| !s.is_empty())
                    .map(|s| s.trim().parse().unwrap_or_else(|_| fail("bad --tex-pages".into())))
                    .collect::<HashSet<usize>>()
            }
            "--repeat" => repeat = val(&a).parse().unwrap_or_else(|_| fail("bad --repeat".into())),
            "--timing" => timing = true,
            "--dump" => dump = true,
            "-h" | "--help" => {
                println!("{USAGE}");
                return;
            }
            _ if a.starts_with("--") => fail(format!("unknown option {a}")),
            _ => files.push(a),
        }
    }
    if files.is_empty() {
        fail("no PDF given".into());
    }
    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    for file in &files {
        let data = match std::fs::read(file) {
            Ok(d) => d,
            Err(e) => {
                eprintln!("{file}: {e}");
                std::process::exit(1);
            }
        };
        if dump {
            let mut rows = Vec::new();
            let mut hook = |p: &Page| rows.push(dump_page(file, p));
            check_pdf(&data, &opt, Some(&mut hook));
            for r in rows {
                let _ = writeln!(out, "{r}");
            }
            continue;
        }
        let mut runs = Vec::new();
        let mut first = None;
        for _ in 0..repeat.max(1) {
            let t0 = Instant::now();
            let r = check_pdf(&data, &opt, None);
            runs.push(t0.elapsed().as_secs_f64());
            if first.is_none() {
                first = Some(r);
            }
        }
        let Some(r) = first else { continue };
        let mut row = serde_json::Map::new();
        row.insert("file".into(), file.as_str().into());
        row.insert("pages".into(), r.pages.into());
        row.insert("sec".into(), runs[0].into());
        row.insert("page_sec".into(), json!(r.page_sec));
        row.insert("items".into(), Value::Array(r.items));
        row.insert("log".into(), json!(r.log));
        if repeat > 1 {
            row.insert("runs_sec".into(), json!(runs));
        }
        let _ = writeln!(out, "{}", Value::Object(row));
        if timing {
            let warm = if runs.len() > 1 { &runs[1..] } else { &runs[..] };
            let mut sorted = warm.to_vec();
            sorted.sort_by(|a, b| a.total_cmp(b));
            let med = sorted[sorted.len() / 2];
            let max_page = r.page_sec.iter().cloned().fold(0.0, f64::max);
            eprintln!(
                "timing {file}: pages={} first={:.4}s median={:.4}s per_page={:.4}s max_page={:.4}s runs={}",
                r.pages,
                runs[0],
                med,
                med / r.pages.max(1) as f64,
                max_page,
                runs.len()
            );
        }
    }
}
