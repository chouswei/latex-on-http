//! Black-box helpers for the gap route checks: run the built binary on a committed fixture and
//! compare with the committed expected JSON (made by `scripts/make_gap_fixtures.py` from the
//! Python reference). No Python, venv or PDF writer is needed at test time.
#![allow(dead_code)]

use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

pub fn gap_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/gap")
}

pub fn manifest_row(name: &str) -> Value {
    let text = std::fs::read_to_string(gap_dir().join("manifest.json")).expect("manifest.json");
    let rows: Vec<Value> = serde_json::from_str(&text).expect("manifest json");
    rows.into_iter()
        .find(|r| r["name"] == name)
        .unwrap_or_else(|| panic!("no manifest row {name}"))
}

fn expected(name: &str) -> Value {
    let text = std::fs::read_to_string(gap_dir().join("expected").join(format!("{name}.json")))
        .expect("expected json");
    serde_json::from_str(&text).expect("expected json parses")
}

fn scratch(name: &str, suffix: &str) -> PathBuf {
    std::env::temp_dir().join(format!("gap-{}-{}-{suffix}", std::process::id(), name))
}

pub fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_endleaf-pdfcheck"))
}

fn blocks_json(row: &Value) -> Value {
    row["blocks"].clone()
}

/// Run the binary the way the row says: `--sidecar` for sidecar rows, the R81 flags otherwise.
fn run_row(row: &Value, dump: bool) -> Output {
    let name = row["name"].as_str().unwrap();
    let pdf = gap_dir().join(row["pdf"].as_str().unwrap());
    let mut cmd = bin();
    let mut files = Vec::new();
    if row["sidecar"] == true && !dump {
        let mut side = json!({
            "templateId": row["template"],
            "blocks": blocks_json(row),
            "shellPages": row["shellPages"],
            "texPages": row["texPages"],
            "future": {"unknown": "keys are ignored"},
        });
        if row["template"] == "fulldoc" {
            side["marks"] = row["marks"].clone();
        }
        let path = scratch(name, "sidecar.json");
        std::fs::write(&path, side.to_string()).unwrap();
        cmd.arg("--sidecar").arg(&path);
        files.push(path);
    } else {
        cmd.args(["--page-budget", "1e9", "--doc-budget", "1e9"]);
        cmd.args(["--template", row["template"].as_str().unwrap()]);
        if row["blocks"].as_object().is_some_and(|m| !m.is_empty()) {
            let path = scratch(name, "blocks.json");
            std::fs::write(&path, blocks_json(row).to_string()).unwrap();
            cmd.arg("--blocks").arg(&path);
            files.push(path);
        }
        let tex: Vec<String> = row["texPages"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.to_string())
            .collect();
        if !tex.is_empty() {
            cmd.args(["--tex-pages", &tex.join(",")]);
        }
        if dump {
            cmd.arg("--dump");
        }
    }
    cmd.arg(&pdf);
    let out = cmd.output().expect("run endleaf-pdfcheck");
    for f in files {
        let _ = std::fs::remove_file(f);
    }
    out
}

fn close(a: &Value, b: &Value) -> bool {
    match (a.as_f64(), b.as_f64()) {
        (Some(x), Some(y)) => (x - y).abs() < 1e-9,
        _ => a == b,
    }
}

/// Item equality as the parity tables use it: every key equal, box edges within 0.5 pt.
fn item_diff(want: &Value, got: &Value) -> Option<String> {
    let (w, g) = (want.as_object().unwrap(), got.as_object().unwrap());
    let keys: std::collections::BTreeSet<_> = w.keys().chain(g.keys()).collect();
    for k in keys {
        if k == "box" {
            let (a, b) = (w.get("box"), g.get("box"));
            let ok = match (a.and_then(|v| v.as_array()), b.and_then(|v| v.as_array())) {
                (Some(a), Some(b)) => {
                    a.len() == b.len()
                        && a.iter()
                            .zip(b)
                            .all(|(x, y)| (x.as_f64().unwrap() - y.as_f64().unwrap()).abs() <= 0.5)
                }
                (None, None) => true,
                _ => false,
            };
            if !ok {
                return Some(format!("box: want {a:?}, got {b:?}"));
            }
        } else if !w.get(k).zip(g.get(k)).is_some_and(|(x, y)| close(x, y)) {
            return Some(format!("{k}: want {:?}, got {:?}", w.get(k), g.get(k)));
        }
    }
    None
}

fn items_equal(want: &Value, got: &Value) -> Result<(), String> {
    let (w, g) = (
        want.as_array().unwrap(),
        got.as_array().ok_or("items is not an array")?,
    );
    if w.len() != g.len() {
        let codes = |v: &[Value]| -> Vec<String> {
            v.iter()
                .map(|i| format!("{}:{}", i["code"], i["message"]))
                .collect()
        };
        return Err(format!(
            "{} items wanted {:?}, got {} {:?}",
            w.len(),
            codes(w),
            g.len(),
            codes(g)
        ));
    }
    for (n, (a, b)) in w.iter().zip(g).enumerate() {
        if let Some(d) = item_diff(a, b) {
            return Err(format!("item {n} ({}): {d}", a["code"]));
        }
    }
    Ok(())
}

fn first_json(out: &Output) -> Result<Value, String> {
    if !out.status.success() {
        return Err(format!(
            "exit {:?}; stderr: {}",
            out.status.code(),
            String::from_utf8_lossy(&out.stderr)
                .lines()
                .next()
                .unwrap_or("")
        ));
    }
    let text = String::from_utf8_lossy(&out.stdout);
    serde_json::from_str(text.trim()).map_err(|e| format!("stdout is not one JSON object: {e}"))
}

fn lines_equal(want: &Value, rows: &str) -> Result<(), String> {
    let mut left: Vec<(i64, String, Vec<f64>)> = Vec::new();
    for row in rows.lines().filter(|l| !l.trim().is_empty()) {
        let v: Value = serde_json::from_str(row).map_err(|e| e.to_string())?;
        for li in v["line_items"].as_array().unwrap() {
            let b = li[1]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_f64().unwrap())
                .collect();
            left.push((
                v["page"].as_i64().unwrap(),
                li[0].as_str().unwrap().to_string(),
                b,
            ));
        }
    }
    let mut missing = Vec::new();
    for l in want.as_array().unwrap() {
        let (page, text) = (l[0].as_i64().unwrap(), l[1].as_str().unwrap());
        let b: Vec<f64> = l[2]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_f64().unwrap())
            .collect();
        let hit = left.iter().position(|(p, t, rb)| {
            *p == page && t == text && rb.iter().zip(&b).all(|(x, y)| (x - y).abs() <= 0.5)
        });
        match hit {
            Some(i) => {
                left.remove(i);
            }
            None => missing.push(format!("pg{page} {text:?}")),
        }
    }
    if missing.is_empty() && left.is_empty() {
        return Ok(());
    }
    let extra: Vec<String> = left
        .iter()
        .map(|(p, t, _)| format!("pg{p} {t:?}"))
        .collect();
    Err(format!(
        "lines missing from the binary {missing:?}; extra {extra:?}"
    ))
}

/// Run one manifest row and compare with its expected JSON; Err carries the reason.
pub fn check(name: &str) -> Result<(), String> {
    let row = manifest_row(name);
    let want = expected(name);
    let compare = row["compare"].as_str().unwrap();
    if compare == "items" || compare == "both" {
        let out = run_row(&row, false);
        let got = first_json(&out)?;
        if row["sidecar"] == true {
            let keys: Vec<&String> = got.as_object().ok_or("not an object")?.keys().collect();
            if keys != ["items", "log"] {
                return Err(format!(
                    "sidecar run must print exactly {{items, log}}, got keys {keys:?}"
                ));
            }
        }
        items_equal(&want["items"], &got["items"])?;
        let encrypted = name.ends_with("encrypted") || name.ends_with("encrypted_skip");
        if !encrypted && want["log"] != got["log"] {
            return Err(format!("log: want {}, got {}", want["log"], got["log"]));
        }
    }
    if compare == "lines" || compare == "both" {
        let out = run_row(&row, true);
        if !out.status.success() {
            return Err(format!("--dump exit {:?}", out.status.code()));
        }
        lines_equal(&want["lines"], &String::from_utf8_lossy(&out.stdout))?;
    }
    Ok(())
}

pub fn assert_case(name: &str) {
    if let Err(e) = check(name) {
        panic!("{name}: {e}");
    }
}
