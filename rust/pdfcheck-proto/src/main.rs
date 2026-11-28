//! `endleaf-pdfcheck`: Rust port of the ENDLEAF-R81 PDF layout checker.
//!
//! Worker mode (ENDLEAF-R82-IFACE): `endleaf-pdfcheck --sidecar <sidecar.json> <file.pdf>`
//! prints exactly one `{"items": [...], "log": [...]}` object and exits 0, also when there
//! are findings or skip notes; exit 2 is a usage error. The R81 flags stay for parity runs.

mod check;
mod extract;
mod font;
mod geom;
mod pdf;
mod tables;
#[cfg(test)]
mod tests;

use check::{check_pdf, round1, Mark, Options, Page};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::time::Instant;

const USAGE: &str = "usage: endleaf-pdfcheck --sidecar FILE.json PDF
       endleaf-pdfcheck [--page-budget SEC] [--doc-budget SEC] [--template ID] \
[--blocks FILE.json] [--tex-pages N,N] [--repeat N] [--timing] [--dump] PDF...
       endleaf-pdfcheck --version";

fn parse_blocks_value(v: &Value, src: &str) -> Result<HashMap<usize, [f64; 4]>, String> {
    let mut out = HashMap::new();
    if let Value::Object(m) = v {
        for (k, b) in m {
            let page: usize = k.parse().map_err(|_| format!("{src}: bad page {k}"))?;
            let a: Vec<f64> = b
                .as_array()
                .map(|a| a.iter().filter_map(|x| x.as_f64()).collect())
                .unwrap_or_default();
            if a.len() != 4 {
                return Err(format!("{src}: page {k} needs 4 numbers"));
            }
            out.insert(page, [a[0], a[1], a[2], a[3]]);
        }
    }
    Ok(out)
}

fn read_json(path: &str) -> Result<Value, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    serde_json::from_str(&text).map_err(|e| format!("{path}: {e}"))
}

fn parse_blocks(path: &str) -> Result<HashMap<usize, [f64; 4]>, String> {
    parse_blocks_value(&read_json(path)?, path)
}

/// Fill `opt` from an R82-IFACE sidecar object: templateId, blocks, marks, shellPages,
/// texPages. Missing or null fields are empty; unknown keys are ignored.
fn apply_sidecar(v: &Value, opt: &mut Options) -> Result<(), String> {
    let obj = v.as_object().ok_or("sidecar: not a JSON object")?;
    let field = |k: &str| obj.get(k).filter(|x| !x.is_null());
    if let Some(t) = field("templateId") {
        opt.template = t.as_str().ok_or("sidecar: templateId is not a string")?.into();
    }
    if let Some(b) = field("blocks") {
        if !b.is_object() {
            return Err("sidecar: blocks is not an object".into());
        }
        opt.blocks = parse_blocks_value(b, "sidecar blocks")?;
    }
    if let Some(rows) = field("marks") {
        let rows = rows.as_array().ok_or("sidecar: marks is not an array")?;
        opt.marks = rows
            .iter()
            .map(|r| {
                let r = r.as_array().filter(|r| r.len() >= 4);
                let bad = || "sidecar: a marks row is not [id, tag, page, yFromBottomPt, ...]";
                let r = r.ok_or_else(bad)?;
                Ok(Mark {
                    id: r[0].as_str().ok_or_else(bad)?.into(),
                    tag: r[1].as_str().ok_or_else(bad)?.into(),
                    page: r[2].as_f64().ok_or_else(bad)?,
                    y: r[3].as_f64().ok_or_else(bad)?,
                })
            })
            .collect::<Result<_, &str>>()?;
    }
    if let Some(s) = field("shellPages") {
        let s = s.as_object().ok_or("sidecar: shellPages is not an object")?;
        opt.shell_pages = s
            .iter()
            .map(|(k, p)| {
                let n: u64 = k.parse().map_err(|_| format!("sidecar: bad fence number {k}"))?;
                let p = p.as_u64().ok_or(format!("sidecar: shellPages {k} is not a page"))?;
                Ok((n, p as usize))
            })
            .collect::<Result<_, String>>()?;
    }
    if let Some(t) = field("texPages") {
        let t = t.as_array().ok_or("sidecar: texPages is not an array")?;
        opt.tex_pages = t
            .iter()
            .map(|p| p.as_u64().map(|p| p as usize).ok_or("sidecar: bad texPages entry"))
            .collect::<Result<_, _>>()?;
    }
    Ok(())
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
    let (mut sidecar, mut r81_flags) = (None::<String>, false);
    let mut files = Vec::new();
    let fail = |m: String| -> ! {
        eprintln!("{m}\n{USAGE}");
        std::process::exit(2)
    };
    while let Some(a) = args.next() {
        let mut val = |name: &str| {
            args.next()
                .unwrap_or_else(|| fail(format!("{name} needs a value")))
        };
        match a.as_str() {
            "--page-budget" => {
                opt.page_budget = val(&a)
                    .parse()
                    .unwrap_or_else(|_| fail("bad --page-budget".into()))
            }
            "--doc-budget" => {
                opt.doc_budget = val(&a)
                    .parse()
                    .unwrap_or_else(|_| fail("bad --doc-budget".into()))
            }
            "--sidecar" => sidecar = Some(val(&a)),
            "--template" => {
                r81_flags = true;
                opt.template = val(&a)
            }
            "--blocks" => {
                r81_flags = true;
                opt.blocks = parse_blocks(&val(&a)).unwrap_or_else(|e| fail(e))
            }
            "--tex-pages" => {
                r81_flags = true;
                opt.tex_pages = val(&a)
                    .split(',')
                    .filter(|s| !s.is_empty())
                    .map(|s| {
                        s.trim()
                            .parse()
                            .unwrap_or_else(|_| fail("bad --tex-pages".into()))
                    })
                    .collect::<HashSet<usize>>()
            }
            "--repeat" => {
                repeat = val(&a)
                    .parse()
                    .unwrap_or_else(|_| fail("bad --repeat".into()))
            }
            "--timing" => timing = true,
            "--dump" => dump = true,
            "-V" | "--version" => {
                println!("endleaf-pdfcheck {}", env!("CARGO_PKG_VERSION"));
                return;
            }
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
    if let Some(path) = &sidecar {
        if r81_flags || dump || repeat != 1 {
            fail("--sidecar takes no --template, --blocks, --tex-pages, --dump or --repeat".into());
        }
        if files.len() != 1 {
            fail("--sidecar takes exactly one PDF".into());
        }
        read_json(path)
            .and_then(|v| apply_sidecar(&v, &mut opt))
            .unwrap_or_else(|e| fail(e));
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
        if sidecar.is_some() {
            // Worker mode: exactly {items, log}; timing fields only on request.
            row.insert("items".into(), Value::Array(r.items));
            row.insert("log".into(), json!(r.log));
            if timing {
                row.insert("sec".into(), runs[0].into());
                row.insert("page_sec".into(), json!(r.page_sec));
            }
            let _ = writeln!(out, "{}", Value::Object(row));
            continue;
        }
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
            let warm = if runs.len() > 1 {
                &runs[1..]
            } else {
                &runs[..]
            };
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
