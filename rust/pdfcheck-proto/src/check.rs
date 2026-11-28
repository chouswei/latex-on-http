//! ENDLEAF-R81-GROUP / -REGION / -CHECKS / -BUDGET: grouping, the eight checks, dedupe and
//! the per-document run, ported from `colophon/pdf_layout_check.py`.

use crate::extract::{Extractor, Glyph, Path, RawPage, P};
use crate::geom::{self, components, Grid, KdTree};
use crate::pdf::Doc;
use regex::Regex;
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;
use std::time::Instant;

pub const PACKAGES: &str = "pdf";
pub const SKIP_CODE: &str = "pdf_check_skipped";
pub const MORE_CODE: &str = "pdf_more_findings";
pub const CODES: [&str; 8] = [
    "pdf_margin_escape",
    "pdf_caption_overlap",
    "pdf_label_on_stroke",
    "pdf_text_escapes_node",
    "pdf_text_overlap",
    "pdf_label_gutter",
    "pdf_stray_source",
    "pdf_empty_page",
];
const WORD_GAP_EM: f64 = 0.10;
const LINE_JOIN_EM: f64 = 1.5;
const LINE_NEIGHBOURS: usize = 24;
const WORD_NEIGHBOURS: usize = 12;
const OVERPRINT_EM: f64 = 0.2;
const WORD_OVERLAP_EM: f64 = 0.35;
const SAME_SIZE_PT: f64 = 0.1;
const GUARD_LOW_EM: f64 = 0.03;
const GUARD_HIGH_EM: f64 = 0.17;
const FIGURE_REGION_GAP_PT: f64 = 3.0 * 72.0 / 25.4;
const MARGIN_ESCAPE_MIN_PT: f64 = 1.0;
const OVERLAP_MIN_PT: f64 = 0.4;
const CORE_SHRINK_V_EM: f64 = 0.2;
const CORE_SHRINK_H_EM: f64 = 0.05;
const NODE_ESCAPE_MIN_PT: f64 = 0.5;
const NODE_INSIDE_MIN: f64 = 0.05;
const NODE_INSIDE_MAX: f64 = 0.95;
const NODE_MIN_WIDTH_EM: f64 = 2.0;
const SAME_BASELINE_PT: f64 = 0.1;
const LABEL_GUTTER_PT: f64 = 0.5 * 72.0 / 25.4;
const GUTTER_BASELINE_SHIFT_PT: f64 = 0.5;
const GUTTER_SIZE_SHIFT_PT: f64 = 0.1;
const NEAR_EMPTY_MAX_WORDS: usize = 5;
pub const PAGE_BUDGET_SEC: f64 = 0.250;
pub const DOCUMENT_BUDGET_SEC: f64 = 2.0;
pub const MAX_FINDINGS: usize = 10;
pub const TEX_PT_TO_BP: f64 = 72.0 / 72.27;
const MM_PER_PT: f64 = 25.4 / 72.0;
const COS_SAME_ANGLE: f64 = 0.995;
const EXTENSIBLE: &str = "-−‐‑‒–—―=⁼←→↔↑↓⇐⇒⇔⟵⟶⟷⟸⟹⟺↦⟼⟻⟽↼⇀↽⇁─━│┃⎯";

struct Res {
    caption: Regex,
    stray: Regex,
    folio: Regex,
    mono: Regex,
}

fn re() -> &'static Res {
    static R: OnceLock<Res> = OnceLock::new();
    R.get_or_init(|| Res {
        caption: Regex::new(r"^(Figure|Table|圖|表)\s*\d+[:：.]").expect("caption regex"),
        stray: Regex::new(r"([`‘]{3,}|~~~+)\s*\w*|\\(?:[A-Za-z]{2,}|[\[\]])(?:\{[^}]*\})?").expect("stray regex"),
        folio: Regex::new(r"^\d{1,4}\n?$").expect("folio regex"),
        mono: Regex::new(r"(?i)mono|courier|typewriter|cursor|consol|menlo").expect("mono regex"),
    })
}

#[inline]
fn dot(a: P, b: P) -> f64 {
    a[0] * b[0] + a[1] * b[1]
}

/// Python `round(x, 1)` (correctly rounded, ties to even on the exact binary value).
pub fn round1(x: f64) -> f64 {
    if !x.is_finite() {
        return x;
    }
    format!("{x:.1}").parse().unwrap_or(x)
}

#[derive(Clone, Debug)]
pub struct Hit {
    pub code: &'static str,
    pub page: usize,
    pub bx: [f64; 4],
    pub message: String,
    pub over_mm: Option<f64>,
    pub pitch: f64,
    pub count: usize,
    pub severity: f64,
}

impl Hit {
    fn new(code: &'static str, page: usize, bx: [f64; 4], message: String, pitch: f64) -> Hit {
        Hit {
            code,
            page,
            bx,
            message,
            over_mm: None,
            pitch,
            count: 1,
            severity: 0.0,
        }
    }
}

pub struct Word {
    pub text: String,
    pub members: Vec<usize>,
    pub u: P,
    pub v: P,
    pub size: f64,
    pub origin: P,
    pub extent: f64,
    pub center: P,
    pub bx: [f64; 4],
    pub core: [P; 4],
    pub z: usize,
    pub font: std::rc::Rc<str>,
    pub baseline: f64,
}

pub struct Line {
    pub text: String,
    pub words: Vec<usize>,
    pub bx: [f64; 4],
    pub size: f64,
    pub upright: bool,
    pub fonts: Vec<std::rc::Rc<str>>,
}

pub struct Page {
    pub number: usize,
    pub width: f64,
    pub height: f64,
    pub glyphs: Vec<Glyph>,
    pub paths: Vec<Path>,
    pub words: Vec<Word>,
    pub lines: Vec<Line>,
    pub body: Vec<usize>,
    pub cores: Vec<[P; 4]>,
    pub word_of: Vec<usize>,
    pub block: Option<[f64; 4]>,
    pub kind: String,
    pub run_of: Vec<usize>,
    pub runs: Vec<(String, usize)>,
}

pub struct Edges {
    pub i: Vec<usize>,
    pub cost: Vec<f64>,
    pub ahead: Vec<bool>,
}

pub struct LinkIn<'a> {
    pub center: &'a [P],
    pub u: &'a [P],
    pub v: &'a [P],
    pub size: &'a [f64],
    pub extent: &'a [f64],
    pub origin: &'a [P],
}

/// `_link`: single-linkage components over kNN edges cut at the threshold.
pub fn link(
    x: &LinkIn,
    k: usize,
    gap_em: f64,
    tolerance_em: f64,
    min_cost: f64,
    size_tolerance: Option<f64>,
) -> (Vec<usize>, Option<Edges>) {
    let n = x.center.len();
    if n < 2 {
        return ((0..n).collect(), None);
    }
    let kk = (k + 1).min(n);
    let tree = KdTree::new(x.center);
    let mut near = Vec::with_capacity(kk);
    let mut keep = Vec::new();
    let mut edges = Edges {
        i: Vec::with_capacity(n * (kk - 1)),
        cost: Vec::with_capacity(n * (kk - 1)),
        ahead: Vec::with_capacity(n * (kk - 1)),
    };
    for i in 0..n {
        tree.knn(x.center[i], kk, &mut near);
        for &(_, j) in near.iter().skip(1) {
            let d = [x.center[j][0] - x.center[i][0], x.center[j][1] - x.center[i][1]];
            let smin = x.size[i].min(x.size[j]);
            let along = d[0] * x.u[i][0] + d[1] * x.u[i][1];
            let gap = along.abs() - (x.extent[i] + x.extent[j]) / 2.0;
            let cost = gap / smin;
            let same_angle = x.u[i][0] * x.u[j][0] + x.u[i][1] * x.u[j][1] > COS_SAME_ANGLE;
            let od = [x.origin[j][0] - x.origin[i][0], x.origin[j][1] - x.origin[i][1]];
            let baseline = (od[0] * x.v[i][0] + od[1] * x.v[i][1]).abs();
            let mut on_line = same_angle && baseline <= tolerance_em * smin;
            if let Some(t) = size_tolerance {
                on_line = on_line && (x.size[i] - x.size[j]).abs() <= t;
            }
            if on_line && cost <= gap_em && cost >= min_cost {
                keep.push((i, j));
            }
            edges.i.push(i);
            edges.cost.push(cost);
            edges.ahead.push(on_line && along > 0.0);
        }
    }
    let (_, labels) = components(n, keep.into_iter());
    (labels, Some(edges))
}

fn glyph_core(g: &Glyph) -> [P; 4] {
    let size = g.size;
    let sh = CORE_SHRINK_H_EM * size;
    let sv = CORE_SHRINK_V_EM * size;
    let (mut lo, mut hi) = (sh, g.width - sh);
    if hi <= lo {
        lo = g.width / 2.0;
        hi = lo;
    }
    let b = g.quad[0];
    let at = |a: f64, c: f64| [b[0] + g.u[0] * a + g.v[0] * c, b[1] + g.u[1] * a + g.v[1] * c];
    [at(lo, sv), at(hi, sv), at(hi, size - sv), at(lo, size - sv)]
}

fn by_label(labels: &[usize]) -> Vec<Vec<usize>> {
    let count = labels.iter().max().map(|m| m + 1).unwrap_or(0);
    let mut out = vec![Vec::new(); count];
    for (n, l) in labels.iter().enumerate() {
        out[*l].push(n);
    }
    out
}

fn fmax(it: impl Iterator<Item = f64>) -> f64 {
    it.fold(f64::NEG_INFINITY, f64::max)
}
fn fmin(it: impl Iterator<Item = f64>) -> f64 {
    it.fold(f64::INFINITY, f64::min)
}

fn group_words(glyphs: &[Glyph], cores: &[[P; 4]], labels: &[usize]) -> Vec<Word> {
    let mut words = Vec::new();
    for mut idx in by_label(labels) {
        if idx.is_empty() {
            continue;
        }
        let first = &glyphs[idx[0]];
        let (u, v) = (first.u, first.v);
        idx.sort_by(|a, b| dot(glyphs[*a].origin, u).total_cmp(&dot(glyphs[*b].origin, u)));
        let quads: Vec<P> = idx.iter().flat_map(|n| glyphs[*n].quad).collect();
        let pts: Vec<f64> = quads.iter().map(|p| dot(*p, u)).collect();
        let extent = fmax(pts.iter().copied()) - fmin(pts.iter().copied());
        let corner: Vec<P> = idx.iter().flat_map(|n| cores[*n]).collect();
        let cu: Vec<f64> = corner.iter().map(|p| dot(*p, u)).collect();
        let cv: Vec<f64> = corner.iter().map(|p| dot(*p, v)).collect();
        let (umin, umax) = (fmin(cu.iter().copied()), fmax(cu.iter().copied()));
        let (vmin, vmax) = (fmin(cv.iter().copied()), fmax(cv.iter().copied()));
        let at = |a: f64, b: f64| [u[0] * a + v[0] * b, u[1] * a + v[1] * b];
        let core = [at(umin, vmin), at(umax, vmin), at(umax, vmax), at(umin, vmax)];
        let bx = [
            fmin(quads.iter().map(|p| p[0])),
            fmin(quads.iter().map(|p| p[1])),
            fmax(quads.iter().map(|p| p[0])),
            fmax(quads.iter().map(|p| p[1])),
        ];
        let mut sizes: Vec<f64> = idx.iter().map(|n| glyphs[*n].size).collect();
        sizes.sort_by(|a, b| a.total_cmp(b));
        let m0 = &glyphs[idx[0]];
        words.push(Word {
            text: idx.iter().map(|n| glyphs[*n].text.as_str()).collect(),
            u,
            v,
            size: sizes[sizes.len() / 2],
            origin: m0.origin,
            extent,
            center: [(bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0],
            bx,
            core,
            z: idx.iter().map(|n| glyphs[*n].z).min().unwrap_or(0),
            font: m0.font.clone(),
            baseline: dot(m0.origin, v),
            members: idx,
        });
    }
    words
}

fn group_lines(words: &[Word]) -> Vec<Line> {
    if words.is_empty() {
        return vec![];
    }
    let center: Vec<P> = words.iter().map(|w| w.center).collect();
    let u: Vec<P> = words.iter().map(|w| w.u).collect();
    let v: Vec<P> = words.iter().map(|w| w.v).collect();
    let size: Vec<f64> = words.iter().map(|w| w.size).collect();
    let extent: Vec<f64> = words.iter().map(|w| w.extent).collect();
    let origin: Vec<P> = words.iter().map(|w| w.origin).collect();
    let x = LinkIn {
        center: &center,
        u: &u,
        v: &v,
        size: &size,
        extent: &extent,
        origin: &origin,
    };
    let (labels, _) = link(&x, LINE_NEIGHBOURS, LINE_JOIN_EM, 0.5, -1e9, None);
    let mut lines = Vec::new();
    for mut members in by_label(&labels) {
        if members.is_empty() {
            continue;
        }
        let u0 = words[members[0]].u;
        members.sort_by(|a, b| dot(words[*a].origin, u0).total_cmp(&dot(words[*b].origin, u0)));
        let bx = [
            fmin(members.iter().map(|w| words[*w].bx[0])),
            fmin(members.iter().map(|w| words[*w].bx[1])),
            fmax(members.iter().map(|w| words[*w].bx[2])),
            fmax(members.iter().map(|w| words[*w].bx[3])),
        ];
        let mut sizes: Vec<f64> = members.iter().map(|w| words[*w].size).collect();
        sizes.sort_by(|a, b| a.total_cmp(b));
        let mut fonts: Vec<std::rc::Rc<str>> = Vec::new();
        for w in &members {
            if !fonts.contains(&words[*w].font) {
                fonts.push(words[*w].font.clone());
            }
        }
        lines.push(Line {
            text: members.iter().map(|w| words[*w].text.as_str()).collect::<Vec<_>>().join(" "),
            bx,
            size: sizes[sizes.len() / 2],
            upright: u0[0].abs() > COS_SAME_ANGLE && u0[1].abs() < 0.1,
            fonts,
            words: members,
        });
    }
    lines
}

/// numpy.histogram(np.clip(values, 0, high), bins, range=(0, high)) then Otsu.
pub fn otsu(values: &[f64], bins: usize, high: f64) -> Option<f64> {
    let edges: Vec<f64> = (0..=bins)
        .map(|k| if k == bins { high } else { k as f64 * (high / bins as f64) })
        .collect();
    let mut hist = vec![0i64; bins];
    for &x in values {
        let x = x.clamp(0.0, high);
        let mut i = ((x - 0.0) / high * bins as f64) as usize;
        if i == bins {
            i -= 1;
        }
        if x < edges[i] {
            i = i.saturating_sub(1);
        }
        if x >= edges[i + 1] && i != bins - 1 {
            i += 1;
        }
        hist[i] += 1;
    }
    let total: i64 = hist.iter().sum();
    if total == 0 {
        return None;
    }
    let centers: Vec<f64> = (0..bins).map(|k| (edges[k] + edges[k + 1]) / 2.0).collect();
    let (mut best, mut threshold) = (-1.0f64, None);
    for cut in 1..bins {
        let w0: i64 = hist[..cut].iter().sum();
        let w1: i64 = hist[cut..].iter().sum();
        if w0 == 0 || w1 == 0 {
            continue;
        }
        let p0: Vec<f64> = (0..cut).map(|k| hist[k] as f64 * centers[k]).collect();
        let p1: Vec<f64> = (cut..bins).map(|k| hist[k] as f64 * centers[k]).collect();
        let m0 = geom::np_sum(&p0) / w0 as f64;
        let m1 = geom::np_sum(&p1) / w1 as f64;
        let between = (w0 * w1) as f64 * (m0 - m1).powi(2);
        if between > best {
            best = between;
            threshold = Some(edges[cut]);
        }
    }
    threshold
}

fn guard(edges: &Option<Edges>, page: usize, log: &mut Vec<String>) {
    let Some(e) = edges else { return };
    let ok: Vec<usize> = (0..e.i.len())
        .filter(|&n| e.ahead[n] && e.cost[n] > -0.5 && e.cost[n] < 1.0)
        .collect();
    if ok.len() < 30 {
        return;
    }
    let size = e.i.iter().max().map(|m| m + 1).unwrap_or(0);
    let mut nearest = vec![f64::INFINITY; size];
    for &n in &ok {
        let i = e.i[n];
        if e.cost[n] < nearest[i] || nearest[i].is_nan() {
            nearest[i] = nearest[i].min(e.cost[n]);
        }
    }
    let vals: Vec<f64> = nearest.into_iter().filter(|x| x.is_finite()).collect();
    if let Some(t) = otsu(&vals, 50, 0.5) {
        if !(GUARD_LOW_EM..=GUARD_HIGH_EM).contains(&t) {
            log.push(format!("pdfcheck guard page={page} otsuEm={t:.3} usedEm={WORD_GAP_EM}"));
        }
    }
}

fn figure_regions(paths: &[Path], reference_width: f64) -> Vec<[f64; 4]> {
    let kept: Vec<&Path> = paths.iter().filter(|p| (p.bbox[2] - p.bbox[0]) < 0.98 * reference_width).collect();
    if kept.is_empty() {
        return vec![];
    }
    let half = FIGURE_REGION_GAP_PT / 2.0;
    let boxes: Vec<[f64; 4]> = kept
        .iter()
        .map(|p| [p.bbox[0] - half, p.bbox[1] - half, p.bbox[2] + half, p.bbox[3] + half])
        .collect();
    let mut grid = Grid::new(boxes.clone(), 20.0);
    let mut pairs = Vec::new();
    let mut out = Vec::new();
    for (a, b) in boxes.iter().enumerate() {
        grid.query(b, &mut out);
        pairs.extend(out.iter().map(|&c| (a, c)));
    }
    let (count, labels) = components(kept.len(), pairs.into_iter());
    let mut regions = vec![[f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY]; count];
    for (n, p) in kept.iter().enumerate() {
        let r = &mut regions[labels[n]];
        r[0] = r[0].min(p.bbox[0]);
        r[1] = r[1].min(p.bbox[1]);
        r[2] = r[2].max(p.bbox[2]);
        r[3] = r[3].max(p.bbox[3]);
    }
    regions
}

/// Python `_start`.
pub fn start(text: &str, limit: usize) -> String {
    let t = text.split(crate::extract::py_isspace).filter(|s| !s.is_empty()).collect::<Vec<_>>().join(" ");
    if t.chars().count() <= limit {
        t
    } else {
        let mut s: String = t.chars().take(limit - 1).collect();
        s.push('…');
        s
    }
}

fn union(boxes: &[[f64; 4]]) -> [f64; 4] {
    [
        fmin(boxes.iter().map(|b| b[0])),
        fmin(boxes.iter().map(|b| b[1])),
        fmax(boxes.iter().map(|b| b[2])),
        fmax(boxes.iter().map(|b| b[3])),
    ]
}

fn check_margin_escape(page: &Page) -> Vec<Hit> {
    let mut hits = Vec::new();
    for &l in &page.body {
        let line = &page.lines[l];
        if !line.upright {
            continue;
        }
        let (x0, x1) = (line.bx[0], line.bx[2]);
        let mut excess = (-x0).max(x1 - page.width);
        if let Some(b) = page.block {
            let (left, width) = (b[0], b[2]);
            excess = excess.max(left - x0).max(x1 - (left + width));
        }
        if excess > MARGIN_ESCAPE_MIN_PT {
            let mm = excess * MM_PER_PT;
            let mut h = Hit::new(
                "pdf_margin_escape",
                page.number,
                line.bx,
                format!(
                    "pg{}: text runs {mm:.1} mm past the text block: '{}'",
                    page.number,
                    start(&line.text, 30)
                ),
                line.size * 1.2,
            );
            h.over_mm = Some(round1(mm));
            h.severity = excess;
            hits.push(h);
        }
    }
    hits
}

/// Stroked polylines with their path index (`_lines_as_shapes`).
fn stroke_lines(paths: &[Path]) -> Vec<(usize, &Vec<P>)> {
    let mut out = Vec::new();
    for (n, p) in paths.iter().enumerate() {
        if !p.stroke {
            continue;
        }
        for poly in &p.polylines {
            if poly.len() >= 2 {
                out.push((n, poly));
            }
        }
    }
    out
}

fn is_degenerate(core: &[P; 4]) -> bool {
    geom::area(core) == 0.0
}

/// Pieces of `line ∩ core` (core convex), each a (start, end) pair in line order.
fn line_core_pieces(line: &[P], core: &[P; 4]) -> Vec<(P, P)> {
    let mut out = Vec::new();
    if is_degenerate(core) {
        let (a, b) = (core[0], core[3]);
        for s in line.windows(2) {
            if let Some(x) = geom::seg_point(s[0], s[1], a, b) {
                out.push((x, x));
            }
        }
        return out;
    }
    let cb = geom::bounds(core);
    for s in line.windows(2) {
        let sb = geom::bounds(s);
        if sb[0] > cb[2] || sb[2] < cb[0] || sb[1] > cb[3] || sb[3] < cb[1] {
            continue;
        }
        let axis_aligned = core[0][1] == core[1][1] && core[1][0] == core[2][0] && core[2][1] == core[3][1];
        let clip = if axis_aligned {
            geom::liang_barsky(s[0], s[1], cb)
        } else {
            geom::clip_segment_convex(s[0], s[1], core)
        };
        if let Some((t0, t1)) = clip {
            let at = |t: f64| [s[0][0] + (s[1][0] - s[0][0]) * t, s[0][1] + (s[1][1] - s[0][1]) * t];
            let p = if t0 == 0.0 { s[0] } else { at(t0) };
            let q = if t1 == 1.0 { s[1] } else { at(t1) };
            out.push((p, q));
        }
    }
    out
}

/// GEOS InteriorPointLine (or the point) of the merged pieces.
fn representative_point(pieces: &[(P, P)]) -> Option<P> {
    let lines: Vec<(P, P)> = pieces.iter().filter(|(a, b)| a != b).cloned().collect();
    if lines.is_empty() {
        return pieces.first().map(|p| p.0);
    }
    let mut merged: Vec<Vec<P>> = Vec::new();
    for (a, b) in lines {
        match merged.last_mut() {
            Some(l) if l.last() == Some(&a) => l.push(b),
            _ => merged.push(vec![a, b]),
        }
    }
    let (mut sx, mut sy, mut total) = (0.0, 0.0, 0.0);
    for l in &merged {
        for s in l.windows(2) {
            let len = (s[1][0] - s[0][0]).hypot(s[1][1] - s[0][1]);
            sx += len * (s[0][0] + s[1][0]) / 2.0;
            sy += len * (s[0][1] + s[1][1]) / 2.0;
            total += len;
        }
    }
    let c = [sx / total, sy / total];
    let dist = |p: P| (p[0] - c[0]).hypot(p[1] - c[1]);
    let mut best: Option<(f64, P)> = None;
    for l in &merged {
        for p in &l[1..l.len() - 1] {
            let d = dist(*p);
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, *p));
            }
        }
    }
    if best.is_none() {
        for l in &merged {
            for p in [l[0], l[l.len() - 1]] {
                let d = dist(p);
                if best.is_none_or(|(bd, _)| d < bd) {
                    best = Some((d, p));
                }
            }
        }
    }
    best.map(|b| b.1)
}

fn check_caption_overlap(page: &Page) -> Vec<Hit> {
    let r = re();
    let captions: Vec<&Line> = page.body.iter().map(|l| &page.lines[*l]).filter(|l| r.caption.is_match(&l.text)).collect();
    if captions.is_empty() || page.paths.is_empty() {
        return vec![];
    }
    let shapes = stroke_lines(&page.paths);
    let mut hits = Vec::new();
    for cap in captions {
        let [cx0, cy0, cx1, cy1] = cap.bx;
        let cores: Vec<&[P; 4]> = cap
            .words
            .iter()
            .flat_map(|w| page.words[*w].members.iter().map(|n| &page.cores[*n]))
            .collect();
        for (n, path) in page.paths.iter().enumerate() {
            let [x0, y0, x1, y1] = path.bbox;
            if x1.min(cx1) - x0.max(cx0) <= OVERLAP_MIN_PT || y1.min(cy1) - y0.max(cy0) <= OVERLAP_MIN_PT {
                continue;
            }
            if x0 >= cx0 - OVERLAP_MIN_PT && x1 <= cx1 + OVERLAP_MIN_PT && y0 >= cy0 - OVERLAP_MIN_PT && y1 <= cy1 + OVERLAP_MIN_PT {
                continue;
            }
            let mut crosses = false;
            if !shapes.is_empty() && !path.image {
                'outer: for (owner, line) in &shapes {
                    if *owner != n {
                        continue;
                    }
                    for c in &cores {
                        if !line_core_pieces(line, c).is_empty() {
                            crosses = true;
                            break 'outer;
                        }
                    }
                }
            }
            if path.fill || crosses {
                hits.push(Hit::new(
                    "pdf_caption_overlap",
                    page.number,
                    cap.bx,
                    format!("pg{}: a drawing overlaps the caption '{}'", page.number, start(&cap.text, 30)),
                    cap.size * 1.2,
                ));
                break;
            }
        }
    }
    hits
}

fn check_label_on_stroke(page: &Page) -> Vec<Hit> {
    if page.words.is_empty() || page.paths.is_empty() {
        return vec![];
    }
    let shapes = stroke_lines(&page.paths);
    if shapes.is_empty() {
        return vec![];
    }
    let mut whites: Vec<(usize, Vec<P>)> = Vec::new();
    for path in &page.paths {
        if path.white && !path.image {
            let ring = &path.polylines[0];
            let b = path.bbox;
            let bx = vec![[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
            let poly = if ring.len() >= 3 { ring.clone() } else { bx.clone() };
            whites.push((path.z, if geom::ring_valid(&poly) { poly } else { bx }));
        }
    }
    let mut grid = Grid::new(page.cores.iter().map(|c| geom::bounds(c)).collect(), 20.0);
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    let mut hits = Vec::new();
    let mut cand = Vec::new();
    for (owner, line) in &shapes {
        grid.query(&geom::bounds(line), &mut cand);
        let path = &page.paths[*owner];
        for &c in &cand {
            let wi = page.word_of[c];
            let key = (wi, *owner);
            if seen.contains(&key) {
                continue;
            }
            let pieces = line_core_pieces(line, &page.cores[c]);
            let Some(point) = representative_point(&pieces) else { continue };
            let gz = page.glyphs[c].z;
            let covered = whites
                .iter()
                .any(|(z, poly)| path.z < *z && *z < gz && geom::point_in_polygon(point, poly) == 1);
            if covered {
                continue;
            }
            seen.insert(key);
            let w = &page.words[wi];
            hits.push(Hit::new(
                "pdf_label_on_stroke",
                page.number,
                w.bx,
                format!("pg{}: label '{}' sits on a stroked line", page.number, start(&w.text, 30)),
                w.size * 1.2,
            ));
        }
    }
    hits
}

fn check_text_escapes_node(page: &Page) -> Vec<Hit> {
    let mut nodes: Vec<(&Vec<P>, f64)> = Vec::new();
    for path in &page.paths {
        if path.image || !(path.stroke && path.closed && path.single) || path.polylines[0].len() < 4 {
            continue;
        }
        let ring = &path.polylines[0];
        if !geom::ring_valid(ring) && geom::area(ring) == 0.0 {
            continue; // buffer(0) of a zero-area ring is empty
        }
        nodes.push((ring, path.bbox[2] - path.bbox[0]));
    }
    if nodes.is_empty() || page.words.is_empty() {
        return vec![];
    }
    let mut hits = Vec::new();
    let mut grid = Grid::new(nodes.iter().map(|(r, _)| geom::bounds(r)).collect(), 50.0);
    let mut cand = Vec::new();
    for w in &page.words {
        grid.query(&geom::bounds(&w.core), &mut cand);
        for &n in &cand {
            let (node, width) = nodes[n];
            if width <= NODE_MIN_WIDTH_EM * w.size {
                continue;
            }
            if !geom::polygons_intersect(&w.core, node) {
                continue;
            }
            let area = geom::area(&w.core);
            if area <= 0.0 {
                continue;
            }
            let fraction = geom::area(&geom::clip_convex(node, &w.core)) / area;
            if !(NODE_INSIDE_MIN < fraction && fraction < NODE_INSIDE_MAX) {
                continue;
            }
            if let Some(b) = geom::difference_bounds(&w.core, node) {
                if (b[2] - b[0]).max(b[3] - b[1]) <= NODE_ESCAPE_MIN_PT {
                    continue;
                }
            }
            hits.push(Hit::new(
                "pdf_text_escapes_node",
                page.number,
                w.bx,
                format!("pg{}: label '{}' runs out of its node", page.number, start(&w.text, 30)),
                w.size * 1.2,
            ));
            break;
        }
    }
    hits
}

fn tex_logo(page: &Page, wa: usize, wb: usize, ta: &str, tb: &str) -> bool {
    let logo = |t: &str| matches!(t, "L" | "A" | "T" | "E" | "X");
    if !logo(ta) || !logo(tb) {
        return false;
    }
    for line in &page.lines {
        if line.words.contains(&wa) && line.words.contains(&wb) {
            let flat = line.text.to_uppercase().replace(' ', "");
            return flat.contains("TEX") || flat.contains("TAEX");
        }
    }
    false
}

fn check_text_overlap(page: &Page) -> Vec<Hit> {
    if page.glyphs.len() < 2 {
        return vec![];
    }
    let mut grid = Grid::new(page.cores.iter().map(|c| geom::bounds(c)).collect(), 20.0);
    let mut found: Vec<((usize, usize), [f64; 4])> = Vec::new();
    let mut index: HashMap<(usize, usize), usize> = HashMap::new();
    let mut cand = Vec::new();
    for a in 0..page.glyphs.len() {
        grid.query(&geom::bounds(&page.cores[a]), &mut cand);
        for &b in &cand {
            if a >= b {
                continue;
            }
            let (ga, gb) = (&page.glyphs[a], &page.glyphs[b]);
            let inter = geom::clip_convex(&page.cores[a], &page.cores[b]);
            if inter.is_empty() {
                continue;
            }
            let ib = geom::bounds(&inter);
            if ib[2] - ib[0] <= OVERLAP_MIN_PT || ib[3] - ib[1] <= OVERLAP_MIN_PT {
                continue;
            }
            let same_baseline = (dot(ga.origin, ga.v) - dot(gb.origin, ga.v)).abs() <= SAME_BASELINE_PT;
            let ext = |t: &str| {
                let mut c = t.chars();
                matches!((c.next(), c.next()), (Some(ch), None) if EXTENSIBLE.contains(ch))
            };
            if same_baseline && ext(&ga.text) && ext(&gb.text) {
                continue;
            }
            let (wa, wb) = (page.word_of[a], page.word_of[b]);
            if wa == wb {
                let along: Vec<f64> = inter.iter().map(|p| p[0] * ga.u[0] + p[1] * ga.u[1]).collect();
                if fmax(along.iter().copied()) - fmin(along.iter().copied()) <= OVERPRINT_EM * ga.size.min(gb.size) {
                    continue;
                }
            } else if tex_logo(page, wa, wb, &ga.text, &gb.text) {
                continue;
            }
            let (ra, rb) = (page.run_of[a], page.run_of[b]);
            let key = if page.runs[rb].1 < page.runs[ra].1 { (rb, ra) } else { (ra, rb) };
            match index.get(&key) {
                Some(&k) => found[k].1 = union(&[found[k].1, ib]),
                None => {
                    index.insert(key, found.len());
                    found.push((key, ib));
                }
            }
        }
    }
    let mut hits = Vec::new();
    for ((first, second), bx) in found {
        let size = fmax(
            page.run_of
                .iter()
                .enumerate()
                .filter(|(_, r)| **r == first || **r == second)
                .map(|(n, _)| page.glyphs[n].size),
        );
        hits.push(Hit::new(
            "pdf_text_overlap",
            page.number,
            bx,
            format!(
                "pg{}: '{}' overlaps '{}'",
                page.number,
                start(&page.runs[first].0, 24),
                start(&page.runs[second].0, 24)
            ),
            size * 1.2,
        ));
    }
    hits
}

fn check_label_gutter(page: &Page, regions: &[[f64; 4]]) -> Vec<Hit> {
    if page.kind != "sysml" {
        return vec![];
    }
    let words: Vec<&Word> = page
        .words
        .iter()
        .filter(|w| {
            let [cx, cy] = w.center;
            regions.iter().any(|r| r[0] <= cx && cx <= r[2] && r[1] <= cy && cy <= r[3])
        })
        .filter(|w| w.u[0].abs() > COS_SAME_ANGLE)
        .collect();
    let mut hits = Vec::new();
    for a in 0..words.len() {
        for b in (a + 1)..words.len() {
            let (wa, wb) = (words[a], words[b]);
            let overlap_v = wa.bx[3].min(wb.bx[3]) - wa.bx[1].max(wb.bx[1]);
            if overlap_v < 0.5 * (wa.bx[3] - wa.bx[1]).min(wb.bx[3] - wb.bx[1]) {
                continue;
            }
            let different = (wa.baseline - wb.baseline).abs() > GUTTER_BASELINE_SHIFT_PT
                || (wa.size - wb.size).abs() > GUTTER_SIZE_SHIFT_PT;
            if !different {
                continue;
            }
            let gap = wa.bx[0].max(wb.bx[0]) - wa.bx[2].min(wb.bx[2]);
            if gap >= LABEL_GUTTER_PT {
                continue;
            }
            let (first, second) = if wb.z < wa.z { (wb, wa) } else { (wa, wb) };
            let mm = gap.max(0.0) * MM_PER_PT;
            let mut h = Hit::new(
                "pdf_label_gutter",
                page.number,
                union(&[wa.bx, wb.bx]),
                format!(
                    "pg{}: labels '{}' and '{}' are {mm:.1} mm apart",
                    page.number,
                    start(&first.text, 24),
                    start(&second.text, 24)
                ),
                wa.size.max(wb.size) * 1.2,
            );
            h.over_mm = Some(round1(mm));
            hits.push(h);
        }
    }
    hits
}

fn check_stray_source(page: &Page) -> Vec<Hit> {
    if page.kind != "document-shell" && page.kind != "fulldoc" {
        return vec![];
    }
    let r = re();
    let mut hits = Vec::new();
    for &l in &page.body {
        let line = &page.lines[l];
        if line.fonts.iter().any(|f| r.mono.is_match(f)) {
            continue;
        }
        if let Some(m) = r.stray.find(&line.text) {
            hits.push(Hit::new(
                "pdf_stray_source",
                page.number,
                line.bx,
                format!("pg{}: raw source printed as text: '{}'", page.number, start(m.as_str(), 30)),
                line.size * 1.2,
            ));
        }
    }
    hits
}

fn check_empty_page(page: &Page, last: bool) -> Vec<Hit> {
    let words: usize = page.body.iter().map(|l| page.lines[*l].words.len()).sum();
    let limit = if last { 0 } else { NEAR_EMPTY_MAX_WORDS };
    if words <= limit && page.paths.is_empty() {
        return vec![Hit::new(
            "pdf_empty_page",
            page.number,
            [0.0, 0.0, page.width, page.height],
            format!("pg{}: page has {words} words and no drawing", page.number),
            page.height,
        )];
    }
    vec![]
}

pub fn dedupe(hits: Vec<Hit>, tex_pages: &HashSet<usize>) -> Vec<Hit> {
    let mut keys: Vec<(&'static str, usize)> = Vec::new();
    let mut groups: HashMap<(&'static str, usize), Vec<Hit>> = HashMap::new();
    for h in hits {
        if h.code == "pdf_margin_escape" && tex_pages.contains(&h.page) {
            continue;
        }
        let k = (h.code, h.page);
        if !groups.contains_key(&k) {
            keys.push(k);
        }
        groups.entry(k).or_default().push(h);
    }
    let mut merged = Vec::new();
    for k in keys {
        let group = groups.remove(&k).unwrap_or_default();
        let n = group.len();
        let mut parent: Vec<usize> = (0..n).collect();
        fn find(p: &mut [usize], mut x: usize) -> usize {
            while p[x] != x {
                p[x] = p[p[x]];
                x = p[x];
            }
            x
        }
        for a in 0..n {
            for b in (a + 1)..n {
                let gap = (group[a].pitch + group[b].pitch) / 2.0;
                let (ba, bb) = (group[a].bx, group[b].bx);
                if ba[2].min(bb[2]) - ba[0].max(bb[0]) >= -gap && ba[3].min(bb[3]) - ba[1].max(bb[1]) >= -gap {
                    let ra = find(&mut parent, a);
                    let rb = find(&mut parent, b);
                    parent[ra] = rb;
                }
            }
        }
        let mut order: Vec<usize> = Vec::new();
        let mut clusters: HashMap<usize, Vec<usize>> = HashMap::new();
        for i in 0..n {
            let r = find(&mut parent, i);
            if !clusters.contains_key(&r) {
                order.push(r);
            }
            clusters.entry(r).or_default().push(i);
        }
        for r in order {
            let members = &clusters[&r];
            let mut best = members[0];
            for &m in &members[1..] {
                let (a, b) = (&group[m], &group[best]);
                let ka = (a.severity, -a.bx[1], -a.bx[0]);
                let kb = (b.severity, -b.bx[1], -b.bx[0]);
                if ka.partial_cmp(&kb) == Some(std::cmp::Ordering::Greater) {
                    best = m;
                }
            }
            let b = &group[best];
            let boxes: Vec<[f64; 4]> = members.iter().map(|m| group[*m].bx).collect();
            merged.push(Hit {
                code: b.code,
                page: b.page,
                bx: union(&boxes),
                message: b.message.clone(),
                over_mm: b.over_mm,
                pitch: b.pitch,
                count: members.iter().map(|m| group[*m].count).sum(),
                severity: b.severity,
            });
        }
    }
    let order = |c: &str| CODES.iter().position(|x| *x == c).unwrap_or(99);
    merged.sort_by(|a, b| {
        (a.page, round1(a.bx[1]), order(a.code), a.bx[0])
            .partial_cmp(&(b.page, round1(b.bx[1]), order(b.code), b.bx[0]))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    merged
}

fn glyph_runs(glyphs: &[Glyph]) -> (Vec<usize>, Vec<(String, usize)>) {
    let mut run_of = vec![0; glyphs.len()];
    let mut runs: Vec<Vec<usize>> = Vec::new();
    let mut order: Vec<usize> = (0..glyphs.len()).collect();
    order.sort_by_key(|n| glyphs[*n].z);
    let mut prev: Option<usize> = None;
    for n in order {
        let g = &glyphs[n];
        let same = prev.is_some_and(|p| {
            let q = &glyphs[p];
            let d = [g.origin[0] - q.origin[0], g.origin[1] - q.origin[1]];
            g.z == q.z + 1
                && (g.size - q.size).abs() <= SAME_SIZE_PT
                && dot(d, g.v).abs() <= SAME_BASELINE_PT
                && -0.01 <= dot(d, g.u)
                && dot(d, g.u) <= q.width + 0.5 * g.size
        });
        if !same {
            runs.push(Vec::new());
        }
        if let Some(r) = runs.last_mut() {
            r.push(n);
        }
        run_of[n] = runs.len() - 1;
        prev = Some(n);
    }
    let runs = runs
        .into_iter()
        .map(|r| (r.iter().map(|n| glyphs[*n].text.as_str()).collect::<String>(), glyphs[r[0]].z))
        .collect();
    (run_of, runs)
}

pub fn build_page(raw: RawPage, block: Option<[f64; 4]>, kind: &str, log: &mut Vec<String>) -> Page {
    let RawPage {
        index,
        width,
        height,
        glyphs,
        paths,
        offpage,
    } = raw;
    let cores: Vec<[P; 4]> = glyphs.iter().map(glyph_core).collect();
    let (mut words, mut lines, mut edges) = (Vec::new(), Vec::new(), None);
    if !glyphs.is_empty() {
        let center: Vec<P> = glyphs
            .iter()
            .map(|g| {
                let q = g.quad;
                [
                    (((q[0][0] + q[1][0]) + q[2][0]) + q[3][0]) / 4.0,
                    (((q[0][1] + q[1][1]) + q[2][1]) + q[3][1]) / 4.0,
                ]
            })
            .collect();
        let u: Vec<P> = glyphs.iter().map(|g| g.u).collect();
        let v: Vec<P> = glyphs.iter().map(|g| g.v).collect();
        let size: Vec<f64> = glyphs.iter().map(|g| g.size).collect();
        let width_: Vec<f64> = glyphs.iter().map(|g| g.width).collect();
        let origin: Vec<P> = glyphs.iter().map(|g| g.origin).collect();
        let x = LinkIn {
            center: &center,
            u: &u,
            v: &v,
            size: &size,
            extent: &width_,
            origin: &origin,
        };
        let (labels, e) = link(&x, WORD_NEIGHBOURS, WORD_GAP_EM, 0.1, -WORD_OVERLAP_EM, Some(SAME_SIZE_PT));
        edges = e;
        words = group_words(&glyphs, &cores, &labels);
        lines = group_lines(&words);
    }
    guard(&edges, index, log);
    if offpage > 0 {
        log.push(format!("pdfcheck offpage page={index} glyphs={offpage}"));
    }
    let floor = match block {
        Some(b) => b[1] + b[3],
        None => 0.88 * height,
    };
    let folio = &re().folio;
    let body: Vec<usize> = (0..lines.len())
        .filter(|&l| !(folio.is_match(&lines[l].text) && lines[l].bx[1] >= floor - 1.0))
        .collect();
    let mut word_of = vec![0; glyphs.len()];
    for (n, w) in words.iter().enumerate() {
        for &m in &w.members {
            word_of[m] = n;
        }
    }
    let (run_of, runs) = glyph_runs(&glyphs);
    Page {
        number: index,
        width,
        height,
        glyphs,
        paths,
        words,
        lines,
        body,
        cores,
        word_of,
        block,
        kind: kind.to_string(),
        run_of,
        runs,
    }
}

// ---- the run --------------------------------------------------------------------------

pub struct Budget {
    pub page_sec: f64,
    pub document_sec: f64,
    start: Instant,
    page_start: Instant,
}

#[derive(Debug)]
pub enum Skip {
    Budget,
    Error(&'static str),
}

impl Budget {
    pub fn new(page_sec: f64, document_sec: f64) -> Budget {
        let now = Instant::now();
        Budget {
            page_sec,
            document_sec,
            start: now,
            page_start: now,
        }
    }
    pub fn begin_page(&mut self) {
        self.page_start = Instant::now();
    }
    pub fn check(&self) -> Result<(), Skip> {
        let now = Instant::now();
        if (now - self.page_start).as_secs_f64() > self.page_sec || (now - self.start).as_secs_f64() > self.document_sec {
            return Err(Skip::Budget);
        }
        Ok(())
    }
}

pub fn skip_message(skipped: &str, last: usize) -> String {
    if last > 0 {
        format!("pdf layout check stopped ({skipped}) after pg{last}; findings so far are kept")
    } else {
        format!("pdf layout check stopped ({skipped}) before pg1")
    }
}

#[derive(Default)]
pub struct Options {
    pub template: String,
    pub blocks: HashMap<usize, [f64; 4]>,
    pub tex_pages: HashSet<usize>,
    pub page_budget: f64,
    pub doc_budget: f64,
}

pub struct Outcome {
    pub pages: usize,
    pub items: Vec<serde_json::Value>,
    pub log: Vec<String>,
    pub page_sec: Vec<f64>,
}

fn run_page(page: &Page, last: bool, budget: &Budget) -> Result<Vec<Hit>, (Vec<Hit>, Skip)> {
    let mut hits = Vec::new();
    if let Err(e) = budget.check() {
        return Err((hits, e));
    }
    let regions = figure_regions(&page.paths, page.block.map(|b| b[2]).unwrap_or(0.75 * page.width));
    if let Err(e) = budget.check() {
        return Err((hits, e));
    }
    for n in 0..8 {
        hits.extend(match n {
            0 => check_margin_escape(page),
            1 => check_caption_overlap(page),
            2 => check_label_on_stroke(page),
            3 => check_text_escapes_node(page),
            4 => check_text_overlap(page),
            5 => check_label_gutter(page, &regions),
            6 => check_stray_source(page),
            _ => check_empty_page(page, last),
        });
        if let Err(e) = budget.check() {
            return Err((hits, e));
        }
    }
    Ok(hits)
}

fn item(hit: &Hit) -> serde_json::Value {
    let mut m = serde_json::Map::new();
    m.insert("code".into(), hit.code.into());
    m.insert("packages".into(), serde_json::json!([PACKAGES]));
    m.insert("message".into(), hit.message.clone().into());
    m.insert("page".into(), hit.page.into());
    m.insert("box".into(), serde_json::json!(hit.bx.iter().map(|x| round1(*x)).collect::<Vec<_>>()));
    m.insert("regionCount".into(), hit.count.into());
    if let Some(o) = hit.over_mm {
        m.insert("overMm".into(), o.into());
    }
    serde_json::Value::Object(m)
}

/// Per-page hook for the `--dump` mode.
pub type PageHook<'h> = &'h mut dyn FnMut(&Page);

pub fn check_pdf(data: &[u8], opt: &Options, mut hook: Option<PageHook>) -> Outcome {
    let mut budget = Budget::new(opt.page_budget, opt.doc_budget);
    let mut log = Vec::new();
    let mut hits = Vec::new();
    let mut page_sec = Vec::new();
    let mut skipped: Option<String> = None;
    let (mut last, mut no_block, mut total) = (0usize, 0usize, 0usize);
    let result = (|| -> Result<(), Skip> {
        let doc = Doc::open(data).map_err(|e| Skip::Error(e.0))?;
        let pages = doc.pages().map_err(|e| Skip::Error(e.0))?;
        total = pages.len();
        let mut ex = Extractor::new(&doc);
        for (n, (_, attrs)) in pages.iter().enumerate() {
            let index = n + 1;
            budget.begin_page();
            let t0 = Instant::now();
            let raw = ex.page(index, attrs).map_err(|e| Skip::Error(e.0))?;
            budget.check()?;
            let block = opt.blocks.get(&index).map(|b| b.map(|x| x * TEX_PT_TO_BP));
            if block.is_none() {
                no_block += 1;
            }
            let page = build_page(raw, block, &opt.template, &mut log);
            if let Some(h) = hook.as_mut() {
                h(&page);
            }
            let r = run_page(&page, index == total, &budget);
            page_sec.push(t0.elapsed().as_secs_f64());
            match r {
                Ok(h) => hits.extend(h),
                Err((h, e)) => {
                    hits.extend(h);
                    return Err(e);
                }
            }
            last = index;
        }
        Ok(())
    })();
    match result {
        Ok(()) => {}
        Err(Skip::Budget) => skipped = Some("time budget".into()),
        Err(Skip::Error(name)) => skipped = Some(format!("error {name}")),
    }
    if no_block > 0 {
        log.push(format!("pdfcheck noblock pages={no_block}"));
    }
    let merged = dedupe(hits, &opt.tex_pages);
    let mut items: Vec<serde_json::Value> = merged.iter().take(MAX_FINDINGS).map(item).collect();
    if merged.len() > MAX_FINDINGS {
        let more = merged.len() - MAX_FINDINGS;
        items.push(serde_json::json!({
            "code": MORE_CODE, "packages": [PACKAGES],
            "message": format!("{more} more PDF layout findings not listed"), "count": more}));
    }
    if let Some(s) = skipped {
        let mut note = serde_json::Map::new();
        note.insert("code".into(), SKIP_CODE.into());
        note.insert("packages".into(), serde_json::json!([PACKAGES]));
        note.insert("message".into(), skip_message(&s, last).into());
        if last > 0 {
            note.insert("page".into(), last.into());
        }
        items.push(serde_json::Value::Object(note));
    }
    Outcome {
        pages: total,
        items,
        log,
        page_sec,
    }
}
