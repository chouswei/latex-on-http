//! ENDLEAF-R81-VECTOR: glyph quads and paths per page, as `extract_pages` gets them from
//! pdfminer.six (laparams off, paint order kept, top-left origin).

use crate::font::{load_font, Font};
use crate::pdf::{decode_stream, ContentParser, Dict, Doc, Obj, Res};
use std::collections::HashMap;
use std::rc::Rc;
use unicode_normalization::UnicodeNormalization;

pub type P = [f64; 2];
pub type M = [f64; 6];
const IDENT: M = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0];

#[derive(Clone, Debug)]
pub struct Glyph {
    pub text: String,
    pub size: f64,
    pub quad: [P; 4],
    pub u: P,
    pub v: P,
    pub origin: P,
    pub width: f64,
    pub z: usize,
    pub font: Rc<str>,
}

#[derive(Clone, Debug)]
pub struct Path {
    pub z: usize,
    pub bbox: [f64; 4],
    pub polylines: Vec<Vec<P>>,
    pub closed: bool,
    pub single: bool,
    pub stroke: bool,
    pub fill: bool,
    pub white: bool,
    pub image: bool,
}

pub struct RawPage {
    pub index: usize,
    pub width: f64,
    pub height: f64,
    pub glyphs: Vec<Glyph>,
    pub paths: Vec<Path>,
    pub offpage: usize,
}

pub fn mult(m1: &M, m0: &M) -> M {
    let [a1, b1, c1, d1, e1, f1] = *m1;
    let [a0, b0, c0, d0, e0, f0] = *m0;
    [
        a0 * a1 + c0 * b1,
        b0 * a1 + d0 * b1,
        a0 * c1 + c0 * d1,
        b0 * c1 + d0 * d1,
        a0 * e1 + c0 * f1 + e0,
        b0 * e1 + d0 * f1 + f0,
    ]
}

#[inline]
pub fn apply(m: &M, p: P) -> P {
    [m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]]
}

fn apply_rect(m: &M, r: [f64; 4]) -> [f64; 4] {
    let pts = [
        apply(m, [r[0], r[1]]),
        apply(m, [r[2], r[1]]),
        apply(m, [r[2], r[3]]),
        apply(m, [r[0], r[3]]),
    ];
    bound(&pts)
}

fn bound(pts: &[P]) -> [f64; 4] {
    let mut b = [f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY];
    for p in pts {
        b[0] = b[0].min(p[0]);
        b[1] = b[1].min(p[1]);
        b[2] = b[2].max(p[0]);
        b[3] = b[3].max(p[1]);
    }
    b
}

/// Python `str.isspace` per character.
pub fn py_isspace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

#[derive(Clone, Debug)]
enum Color {
    Gray(f64),
    Rgb([f64; 3]),
    Cmyk([f64; 4]),
    Other,
    PatternOn(Box<Color>),
}

fn is_white(c: &Color) -> bool {
    match c {
        Color::Gray(v) => *v >= 0.999,
        Color::Rgb(v) => v.iter().cloned().fold(f64::INFINITY, f64::min) >= 0.999,
        Color::Cmyk(v) => v.iter().cloned().fold(f64::NEG_INFINITY, f64::max) <= 0.001,
        Color::PatternOn(b) => matches!(**b, Color::Gray(v) if v >= 0.999),
        Color::Other => false,
    }
}

#[derive(Clone)]
struct ColorSpace {
    name: Rc<str>,
    n: usize,
}

fn predefined(name: &str) -> Option<ColorSpace> {
    let n = match name {
        "DeviceGray" | "CalGray" | "Separation" | "Indexed" | "Pattern" => 1,
        "DeviceRGB" | "CalRGB" | "Lab" => 3,
        "DeviceCMYK" => 4,
        _ => return None,
    };
    Some(ColorSpace { name: Rc::from(name), n })
}

#[derive(Clone)]
struct TextState {
    font: Option<Rc<Font>>,
    fontsize: f64,
    charspace: f64,
    wordspace: f64,
    scaling: f64,
    leading: f64,
    rise: f64,
    matrix: M,
    linematrix: P,
}

#[derive(Clone)]
struct GState {
    ncolor: Color,
    ncs: ColorSpace,
    scs: ColorSpace,
}

#[derive(Clone)]
enum Seg {
    M(P),
    L(P),
    C(P, P, P),
    V(P, P),
    Y(P, P),
    H,
}

impl Seg {
    fn op(&self) -> u8 {
        match self {
            Seg::M(_) => b'm',
            Seg::L(_) => b'l',
            Seg::C(..) => b'c',
            Seg::V(..) => b'v',
            Seg::Y(..) => b'y',
            Seg::H => b'h',
        }
    }
    fn last(&self) -> Option<P> {
        match self {
            Seg::M(p) | Seg::L(p) => Some(*p),
            Seg::C(_, _, p) | Seg::V(_, p) | Seg::Y(_, p) => Some(*p),
            Seg::H => None,
        }
    }
    fn map(&self, m: &M) -> Seg {
        match self {
            Seg::M(p) => Seg::M(apply(m, *p)),
            Seg::L(p) => Seg::L(apply(m, *p)),
            Seg::C(a, b, c) => Seg::C(apply(m, *a), apply(m, *b), apply(m, *c)),
            Seg::V(a, b) => Seg::V(apply(m, *a), apply(m, *b)),
            Seg::Y(a, b) => Seg::Y(apply(m, *a), apply(m, *b)),
            Seg::H => Seg::H,
        }
    }
}

const BEZIER_CHORDS: usize = 8;

fn bez(cur: &mut Vec<P>, p0: P, p1: P, p2: P, p3: P) {
    for step in 1..=BEZIER_CHORDS {
        let t = step as f64 / BEZIER_CHORDS as f64;
        let s = 1.0 - t;
        cur.push([
            s.powi(3) * p0[0] + 3.0 * s * s * t * p1[0] + 3.0 * s * t * t * p2[0] + t.powi(3) * p3[0],
            s.powi(3) * p0[1] + 3.0 * s * s * t * p1[1] + 3.0 * s * t * t * p2[1] + t.powi(3) * p3[1],
        ]);
    }
}

/// `_flatten`: (polylines, closed, single), Beziers cut to 8 chords.
fn flatten(path: &[Seg], height: f64) -> (Vec<Vec<P>>, bool, bool) {
    let flip = |p: P| [p[0], height - p[1]];
    let mut lines: Vec<Vec<P>> = Vec::new();
    let mut flags: Vec<bool> = Vec::new();
    let mut cur: Vec<P> = Vec::new();
    let mut end = |cur: &mut Vec<P>, closed: bool, lines: &mut Vec<Vec<P>>| {
        if cur.len() >= 2 {
            lines.push(std::mem::take(cur));
            flags.push(closed);
        }
        cur.clear();
    };
    for seg in path {
        match seg {
            Seg::M(p) => {
                end(&mut cur, false, &mut lines);
                cur = vec![flip(*p)];
            }
            Seg::L(p) => cur.push(flip(*p)),
            Seg::C(a, b, c) => {
                if let Some(&p0) = cur.last() {
                    bez(&mut cur, p0, flip(*a), flip(*b), flip(*c));
                }
            }
            Seg::V(a, b) => {
                if let Some(&p0) = cur.last() {
                    bez(&mut cur, p0, p0, flip(*a), flip(*b));
                }
            }
            Seg::Y(a, b) => {
                if let Some(&p0) = cur.last() {
                    bez(&mut cur, p0, flip(*a), flip(*b), flip(*b));
                }
            }
            Seg::H => {
                if !cur.is_empty() {
                    let first = cur[0];
                    cur.push(first);
                    end(&mut cur, true, &mut lines);
                }
            }
        }
    }
    end(&mut cur, false, &mut lines);
    let closed = !flags.is_empty() && flags.iter().all(|f| *f);
    let single = lines.len() == 1;
    (lines, closed, single)
}

pub struct Extractor<'a, 'd> {
    doc: &'d Doc<'a>,
    fonts: HashMap<u32, Rc<Font>>,
    blank_font: Option<Rc<Font>>,
    // per page
    height: f64,
    width: f64,
    counter: usize,
    glyphs: Vec<Glyph>,
    paths: Vec<Path>,
    offpage: usize,
    cids: Vec<u32>,
}

struct Interp {
    resources: Option<Rc<Dict>>,
    fontmap: HashMap<String, Rc<Font>>,
    csmap: HashMap<String, ColorSpace>,
    ctm: M,
    ts: TextState,
    gs: GState,
    gstack: Vec<(M, TextState, GState)>,
    curpath: Vec<Seg>,
    args: Vec<Obj>,
    parents: Vec<u32>,
}

fn nums(args: &[Obj]) -> Option<Vec<f64>> {
    args.iter().map(|a| a.num()).collect()
}

impl<'a, 'd> Extractor<'a, 'd> {
    pub fn new(doc: &'d Doc<'a>) -> Self {
        Extractor {
            doc,
            fonts: HashMap::new(),
            blank_font: None,
            height: 0.0,
            width: 0.0,
            counter: 0,
            glyphs: Vec::new(),
            paths: Vec::new(),
            offpage: 0,
            cids: Vec::new(),
        }
    }

    pub fn page(&mut self, index: usize, attrs: &Dict) -> Res<RawPage> {
        let doc = self.doc;
        let mb: Vec<f64> = doc
            .rarray(attrs.get("MediaBox"))
            .and_then(|a| a.iter().map(|x| doc.resolve(x).num()).collect::<Option<Vec<f64>>>())
            .filter(|v| v.len() == 4)
            .unwrap_or_else(|| vec![0.0, 0.0, 612.0, 792.0]);
        let (x0, y0, x1, y1) = (mb[0], mb[1], mb[2], mb[3]);
        let rotate = ((doc.resolve(attrs.get("Rotate").unwrap_or(&Obj::Int(0))).int().unwrap_or(0) + 360) % 360 + 360) % 360;
        let ctm: M = match rotate {
            90 => [0.0, -1.0, 1.0, 0.0, -y0, x1],
            180 => [-1.0, 0.0, 0.0, -1.0, x1, y1],
            270 => [0.0, 1.0, -1.0, 0.0, y1, -x0],
            _ => [1.0, 0.0, 0.0, 1.0, -x0, -y0],
        };
        let r = apply_rect(&ctm, [x0, y0, x1, y1]);
        self.width = (r[0] - r[2]).abs();
        self.height = (r[1] - r[3]).abs();
        self.counter = 0;
        self.glyphs = Vec::new();
        self.paths = Vec::new();
        self.offpage = 0;
        let resources = doc.rdict(attrs.get("Resources"));
        let contents: Vec<Obj> = match attrs.get("Contents").map(|c| doc.resolve(c)) {
            Some(Obj::Array(a)) => a.to_vec(),
            Some(Obj::Null) | None => vec![],
            Some(_) => vec![attrs.get("Contents").cloned().unwrap_or(Obj::Null)],
        };
        self.render_contents(resources, &contents, ctm, &[]);
        Ok(RawPage {
            index,
            width: self.width,
            height: self.height,
            glyphs: std::mem::take(&mut self.glyphs),
            paths: std::mem::take(&mut self.paths),
            offpage: self.offpage,
        })
    }

    fn get_font(&mut self, objid: Option<u32>, spec: &Dict) -> Rc<Font> {
        if let Some(id) = objid {
            if let Some(f) = self.fonts.get(&id) {
                return f.clone();
            }
        }
        let f = Rc::new(load_font(self.doc, spec));
        if let Some(id) = objid {
            self.fonts.insert(id, f.clone());
        }
        f
    }

    fn render_contents(&mut self, resources: Option<Rc<Dict>>, streams: &[Obj], ctm: M, parents: &[u32]) {
        let doc = self.doc;
        let mut it = Interp {
            resources: resources.clone(),
            fontmap: HashMap::new(),
            csmap: HashMap::new(),
            ctm,
            ts: TextState {
                font: None,
                fontsize: 0.0,
                charspace: 0.0,
                wordspace: 0.0,
                scaling: 100.0,
                leading: 0.0,
                rise: 0.0,
                matrix: IDENT,
                linematrix: [0.0, 0.0],
            },
            gs: GState {
                ncolor: Color::Gray(0.0),
                ncs: predefined("DeviceGray").unwrap_or(ColorSpace { name: Rc::from("DeviceGray"), n: 1 }),
                scs: predefined("DeviceGray").unwrap_or(ColorSpace { name: Rc::from("DeviceGray"), n: 1 }),
            },
            gstack: Vec::new(),
            curpath: Vec::new(),
            args: Vec::new(),
            parents: parents.to_vec(),
        };
        for n in ["DeviceGray", "CalGray", "Separation", "Indexed", "Pattern", "DeviceRGB", "CalRGB", "Lab", "DeviceCMYK"] {
            if let Some(cs) = predefined(n) {
                it.csmap.insert(n.to_string(), cs);
            }
        }
        if let Some(res) = &resources {
            if let Some(fd) = doc.rdict(res.get("Font")) {
                for (k, v) in &fd.0 {
                    let objid = if let Obj::Ref(r) = v { Some(*r) } else { None };
                    let spec = doc.rdict(Some(v)).unwrap_or_default();
                    let f = self.get_font(objid, &spec);
                    it.fontmap.insert(k.to_string(), f);
                }
            }
            if let Some(cd) = doc.rdict(res.get("ColorSpace")) {
                for (k, v) in &cd.0 {
                    let spec = doc.resolve(v);
                    let cs = match &spec {
                        Obj::Array(a) => {
                            let name = a.first().and_then(|x| x.name()).unwrap_or("").to_string();
                            if name == "ICCBased" && a.len() >= 2 {
                                let n = doc.resolve(&a[1]).as_dict().and_then(|d| doc.rnum(d.get("N")));
                                n.map(|n| ColorSpace { name: Rc::from("ICCBased"), n: n as usize })
                            } else if name == "DeviceN" && a.len() >= 2 {
                                doc.rarray(Some(&a[1])).map(|l| ColorSpace { name: Rc::from("DeviceN"), n: l.len() })
                            } else {
                                predefined(&name)
                            }
                        }
                        Obj::Name(n) => predefined(n),
                        _ => None,
                    };
                    if let Some(cs) = cs {
                        it.csmap.insert(k.to_string(), cs);
                    }
                }
            }
        }
        let mut data: Vec<u8> = Vec::new();
        let mut ids = Vec::new();
        for s in streams {
            let objid = if let Obj::Ref(r) = s { Some(*r) } else { None };
            if let Obj::Stream(st) = doc.resolve(s) {
                let id = st.objid.or(objid);
                let Some(id) = id else { continue };
                if parents.contains(&id) {
                    continue;
                }
                ids.push(id);
                data.extend_from_slice(&decode_stream(&st));
            }
        }
        it.parents.extend(ids);
        let mut parser = ContentParser::new(&data);
        while let Some(obj) = parser.next() {
            match obj {
                Obj::Keyword(k) => self.op(&mut it, &k),
                other => it.args.push(other),
            }
        }
    }

    fn pop(it: &mut Interp, n: usize) -> Option<Vec<Obj>> {
        if n == 0 {
            return Some(vec![]);
        }
        let k = it.args.len().saturating_sub(n);
        let v: Vec<Obj> = it.args.drain(k..).collect();
        if v.len() == n {
            Some(v)
        } else {
            None
        }
    }

    fn op(&mut self, it: &mut Interp, k: &str) {
        let nargs = match k {
            "q" | "Q" | "h" | "S" | "s" | "f" | "F" | "f*" | "B" | "B*" | "b" | "b*" | "n" | "W" | "W*" | "BT"
            | "ET" | "BX" | "EX" | "EMC" | "T*" | "BI" | "ID" | "SCN" | "scn" | "SC" | "sc" => 0,
            "w" | "J" | "j" | "M" | "ri" | "i" | "gs" | "CS" | "cs" | "G" | "g" | "sh" | "MP" | "BMC" | "Tc"
            | "Tw" | "Tz" | "TL" | "Tr" | "Ts" | "TJ" | "Tj" | "'" | "EI" | "Do" => 1,
            "d" | "m" | "l" | "DP" | "BDC" | "Tf" | "Td" | "TD" => 2,
            "RG" | "rg" | "\"" => 3,
            "v" | "y" | "re" | "K" | "k" => 4,
            "cm" | "c" | "Tm" => 6,
            _ => return,
        };
        let Some(a) = Self::pop(it, nargs) else { return };
        let f = |i: usize| a.get(i).and_then(|x| x.num());
        match k {
            "q" => it.gstack.push((it.ctm, it.ts.clone(), it.gs.clone())),
            "Q" => {
                if let Some((c, t, g)) = it.gstack.pop() {
                    it.ctm = c;
                    it.ts = t;
                    it.gs = g;
                }
            }
            "cm" => {
                if let Some(v) = nums(&a) {
                    it.ctm = mult(&[v[0], v[1], v[2], v[3], v[4], v[5]], &it.ctm);
                }
            }
            "m" | "l" => {
                if let (Some(x), Some(y)) = (f(0), f(1)) {
                    it.curpath.push(if k == "m" { Seg::M([x, y]) } else { Seg::L([x, y]) });
                }
            }
            "c" => {
                if let Some(v) = nums(&a) {
                    it.curpath.push(Seg::C([v[0], v[1]], [v[2], v[3]], [v[4], v[5]]));
                }
            }
            "v" | "y" => {
                if let Some(v) = nums(&a) {
                    it.curpath.push(if k == "v" {
                        Seg::V([v[0], v[1]], [v[2], v[3]])
                    } else {
                        Seg::Y([v[0], v[1]], [v[2], v[3]])
                    });
                }
            }
            "h" => it.curpath.push(Seg::H),
            "re" => {
                if let Some(v) = nums(&a) {
                    let (x, y, w, h) = (v[0], v[1], v[2], v[3]);
                    it.curpath.push(Seg::M([x, y]));
                    it.curpath.push(Seg::L([x + w, y]));
                    it.curpath.push(Seg::L([x + w, y + h]));
                    it.curpath.push(Seg::L([x, y + h]));
                    it.curpath.push(Seg::H);
                }
            }
            "S" => self.paint(it, true, false),
            "s" => {
                it.curpath.push(Seg::H);
                self.paint(it, true, false)
            }
            "f" | "f*" => self.paint(it, false, true),
            "B" | "B*" => self.paint(it, true, true),
            "b" | "b*" => {
                it.curpath.push(Seg::H);
                self.paint(it, true, true)
            }
            "n" => it.curpath.clear(),
            "CS" | "cs" => {
                if let Some(cs) = a[0].name().and_then(|n| it.csmap.get(n)).cloned() {
                    if k == "CS" {
                        it.gs.scs = cs;
                    } else {
                        it.gs.ncs = cs;
                    }
                }
            }
            "G" => {
                if f(0).is_some() {
                    if let Some(cs) = it.csmap.get("DeviceGray").cloned() {
                        it.gs.scs = cs;
                    }
                }
            }
            "RG" => {
                if nums(&a).is_some() {
                    if let Some(cs) = it.csmap.get("DeviceRGB").cloned() {
                        it.gs.scs = cs;
                    }
                }
            }
            "K" => {
                if nums(&a).is_some() {
                    if let Some(cs) = it.csmap.get("DeviceCMYK").cloned() {
                        it.gs.scs = cs;
                    }
                }
            }
            "g" => {
                if let Some(v) = f(0) {
                    it.gs.ncolor = Color::Gray(v);
                    if let Some(cs) = it.csmap.get("DeviceGray").cloned() {
                        it.gs.ncs = cs;
                    }
                }
            }
            "rg" => {
                if let Some(v) = nums(&a) {
                    it.gs.ncolor = Color::Rgb([v[0], v[1], v[2]]);
                    if let Some(cs) = it.csmap.get("DeviceRGB").cloned() {
                        it.gs.ncs = cs;
                    }
                }
            }
            "k" => {
                if let Some(v) = nums(&a) {
                    it.gs.ncolor = Color::Cmyk([v[0], v[1], v[2], v[3]]);
                    if let Some(cs) = it.csmap.get("DeviceCMYK").cloned() {
                        it.gs.ncs = cs;
                    }
                }
            }
            "SCN" | "SC" => {
                let n = it.gs.scs.n;
                let _ = Self::pop(it, n);
            }
            "scn" | "sc" => {
                let n = it.gs.ncs.n;
                if let Some(comp) = Self::pop(it, n) {
                    let parse = |c: &[Obj]| -> Option<Color> {
                        let v = nums(c)?;
                        match v.len() {
                            1 => Some(Color::Gray(v[0])),
                            3 => Some(Color::Rgb([v[0], v[1], v[2]])),
                            4 => Some(Color::Cmyk([v[0], v[1], v[2], v[3]])),
                            _ => None,
                        }
                    };
                    if &*it.gs.ncs.name != "Pattern" {
                        if let Some(c) = parse(&comp) {
                            it.gs.ncolor = c;
                        }
                    } else if let Some(Obj::Name(_)) = comp.last() {
                        if comp.len() == 1 {
                            it.gs.ncolor = Color::Other;
                        } else if let Some(c) = parse(&comp[..comp.len() - 1]) {
                            it.gs.ncolor = Color::PatternOn(Box::new(c));
                        }
                    }
                }
            }
            "BT" => {
                it.ts.matrix = IDENT;
                it.ts.linematrix = [0.0, 0.0];
            }
            "Tc" => {
                if let Some(v) = f(0) {
                    it.ts.charspace = v;
                }
            }
            "Tw" => {
                if let Some(v) = f(0) {
                    it.ts.wordspace = v;
                }
            }
            "Tz" => {
                if let Some(v) = f(0) {
                    it.ts.scaling = v;
                }
            }
            "TL" => {
                if let Some(v) = f(0) {
                    it.ts.leading = -v;
                }
            }
            "Ts" => {
                if let Some(v) = f(0) {
                    it.ts.rise = v;
                }
            }
            "Tf" => {
                let font = a[0].name().and_then(|n| it.fontmap.get(n)).cloned();
                it.ts.font = Some(match font {
                    Some(f) => f,
                    None => self.blank_font.get_or_insert_with(|| Rc::new(load_font(self.doc, &Dict::default()))).clone(),
                });
                if let Some(v) = f(1) {
                    it.ts.fontsize = v;
                }
            }
            "Td" | "TD" => {
                if let (Some(tx), Some(ty)) = (f(0), f(1)) {
                    let [a_, b, c, d, e, ff] = it.ts.matrix;
                    it.ts.matrix = [a_, b, c, d, tx * a_ + ty * c + e, tx * b + ty * d + ff];
                }
                if k == "TD" {
                    if let Some(ty) = f(1) {
                        it.ts.leading = ty;
                    }
                }
                it.ts.linematrix = [0.0, 0.0];
            }
            "Tm" => {
                if let Some(v) = nums(&a) {
                    it.ts.matrix = [v[0], v[1], v[2], v[3], v[4], v[5]];
                    it.ts.linematrix = [0.0, 0.0];
                }
            }
            "T*" => self.tstar(it),
            "TJ" => {
                let seq = match &a[0] {
                    Obj::Array(x) => x.to_vec(),
                    _ => vec![],
                };
                self.render_string(it, &seq);
            }
            "Tj" => self.render_string(it, &a[..1]),
            "'" => {
                self.tstar(it);
                self.render_string(it, &a[..1]);
            }
            "\"" => {
                if let Some(v) = f(0) {
                    it.ts.wordspace = v;
                }
                if let Some(v) = f(1) {
                    it.ts.charspace = v;
                }
                self.render_string(it, &a[2..3]);
            }
            "EI" => {
                if let Obj::Stream(s) = &a[0] {
                    if s.dict.has("W") && s.dict.has("H") {
                        self.image(it);
                    }
                }
            }
            "Do" => self.do_xobject(it, &a[0]),
            _ => {}
        }
    }

    fn tstar(&mut self, it: &mut Interp) {
        let [a, b, c, d, e, f] = it.ts.matrix;
        let l = it.ts.leading;
        it.ts.matrix = [a, b, c, d, l * c + e, l * d + f];
        it.ts.linematrix = [0.0, 0.0];
    }

    fn image(&mut self, it: &Interp) {
        self.counter += 1; // the LTFigure
        let b = apply_rect(&it.ctm, [0.0, 0.0, 1.0, 1.0]);
        self.counter += 1;
        let h = self.height;
        self.paths.push(Path {
            z: self.counter,
            bbox: [b[0], h - b[3], b[2], h - b[1]],
            polylines: vec![],
            closed: false,
            single: false,
            stroke: false,
            fill: true,
            white: false,
            image: true,
        });
    }

    fn do_xobject(&mut self, it: &mut Interp, name: &Obj) {
        let doc = self.doc;
        let Some(name) = name.name() else { return };
        let Some(res) = it.resources.clone() else { return };
        let Some(xd) = doc.rdict(res.get("XObject")) else { return };
        let Some(xref) = xd.get(name).cloned() else { return };
        let Obj::Stream(st) = doc.resolve(&xref) else { return };
        let sub = st.dict.get("Subtype").and_then(|x| x.name()).unwrap_or("");
        if sub == "Form" && st.dict.has("BBox") {
            let m: M = doc
                .rarray(st.dict.get("Matrix"))
                .and_then(|a| a.iter().map(|x| doc.resolve(x).num()).collect::<Option<Vec<f64>>>())
                .filter(|v| v.len() == 6)
                .map(|v| [v[0], v[1], v[2], v[3], v[4], v[5]])
                .unwrap_or(IDENT);
            let xres = match st.dict.get("Resources") {
                Some(r) => doc.rdict(Some(r)),
                None => it.resources.clone(),
            };
            self.counter += 1; // the LTFigure
            let ctm = mult(&m, &it.ctm);
            let parents = it.parents.clone();
            let streams = [xref];
            self.render_contents(xres, &streams, ctm, &parents);
        } else if sub == "Image" && st.dict.has("Width") && st.dict.has("Height") {
            self.image(it);
        }
    }

    fn render_string(&mut self, it: &mut Interp, seq: &[Obj]) {
        let Some(font) = it.ts.font.clone() else { return };
        let matrix = mult(&it.ts.matrix, &it.ctm);
        let fontsize = it.ts.fontsize;
        let scaling = it.ts.scaling * 0.01;
        let charspace = it.ts.charspace * scaling;
        let mut wordspace = it.ts.wordspace * scaling;
        let rise = it.ts.rise;
        if font.multibyte {
            wordspace = 0.0;
        }
        let dxscale = 0.001 * fontsize * scaling;
        let [mut x, mut y] = it.ts.linematrix;
        let vertical = font.vertical;
        let mut need = false;
        let mut cids = std::mem::take(&mut self.cids);
        for obj in seq {
            match obj {
                Obj::Int(_) | Obj::Real(_) | Obj::Bool(_) => {
                    let v = obj.num().unwrap_or(0.0);
                    if vertical {
                        y -= v * dxscale;
                    } else {
                        x -= v * dxscale;
                    }
                    need = true;
                }
                Obj::Str(b) => {
                    font.decode(b, &mut cids);
                    for &cid in &cids {
                        if need {
                            if vertical {
                                y += charspace;
                            } else {
                                x += charspace;
                            }
                        }
                        let m = [matrix[0], matrix[1], matrix[2], matrix[3], x * matrix[0] + y * matrix[2] + matrix[4], x * matrix[1] + y * matrix[3] + matrix[5]];
                        let adv = self.render_char(&m, &font, fontsize, scaling, rise, cid);
                        if vertical {
                            y += adv;
                        } else {
                            x += adv;
                        }
                        if cid == 32 && wordspace != 0.0 {
                            if vertical {
                                y += wordspace;
                            } else {
                                x += wordspace;
                            }
                        }
                        need = true;
                    }
                }
                _ => {}
            }
        }
        self.cids = cids;
        it.ts.linematrix = [x, y];
    }

    fn render_char(&mut self, m: &M, font: &Font, fontsize: f64, scaling: f64, rise: f64, cid: u32) -> f64 {
        self.counter += 1;
        let z = self.counter;
        let width = font.char_width(cid);
        let adv = width * fontsize * scaling;
        if font.vertical {
            let _ = font.char_disp(cid);
        }
        let raw = match font.to_unichr(cid) {
            Some(s) => s,
            None => format!("(cid:{cid})"),
        };
        let text: String = raw.nfkc().collect();
        if !text.chars().any(|c| !py_isspace(c)) {
            return adv;
        }
        if fontsize == 0.0 {
            return adv;
        }
        let desc = font.get_descent() * fontsize + rise;
        let h = self.height;
        let point = |px: f64, py: f64| {
            let q = apply(m, [px, py]);
            [q[0], h - q[1]]
        };
        let p00 = point(0.0, desc);
        let p10 = point(adv, desc);
        let p11 = point(adv, desc + fontsize);
        let p01 = point(0.0, desc + fontsize);
        let b0 = point(0.0, rise);
        let b1 = point(adv, rise);
        let span = (b1[0] - b0[0]).hypot(b1[1] - b0[1]);
        let size = (p01[0] - p00[0]).hypot(p01[1] - p00[1]);
        if size <= 0.0 || span <= 0.0 || span.is_nan() || size.is_nan() {
            return adv;
        }
        let quad = [p00, p10, p11, p01];
        let xs = quad.iter().map(|p| p[0]);
        let ys = quad.iter().map(|p| p[1]);
        let (xmax, xmin) = (xs.clone().fold(f64::NEG_INFINITY, f64::max), xs.fold(f64::INFINITY, f64::min));
        let (ymax, ymin) = (ys.clone().fold(f64::NEG_INFINITY, f64::max), ys.fold(f64::INFINITY, f64::min));
        if xmax < 0.0 || xmin > self.width || ymax < 0.0 || ymin > self.height {
            self.offpage += 1;
            return adv;
        }
        let u = [(b1[0] - b0[0]) / span, (b1[1] - b0[1]) / span];
        let v = [(p01[0] - p00[0]) / size, (p01[1] - p00[1]) / size];
        self.glyphs.push(Glyph {
            text,
            size,
            quad,
            u,
            v,
            origin: b0,
            width: span,
            z,
            font: Rc::from(font.fontname.as_str()),
        });
        adv
    }

    fn paint(&mut self, it: &mut Interp, stroke: bool, fill: bool) {
        let path = std::mem::take(&mut it.curpath);
        self.paint_path(it, stroke, fill, &path);
    }

    fn paint_path(&mut self, it: &Interp, stroke: bool, fill: bool, path: &[Seg]) {
        if path.first().map(|s| s.op()) != Some(b'm') {
            return;
        }
        let ms = path.iter().filter(|s| s.op() == b'm').count();
        if ms > 1 {
            // re.finditer(r"m[^m]+", shape)
            let mut i = 0;
            while i < path.len() {
                if path[i].op() == b'm' {
                    let mut j = i + 1;
                    while j < path.len() && path[j].op() != b'm' {
                        j += 1;
                    }
                    if j > i + 1 {
                        self.paint_path(it, stroke, fill, &path[i..j]);
                    }
                    i = j;
                } else {
                    i += 1;
                }
            }
            return;
        }
        let first = path[0].last().unwrap_or([0.0, 0.0]);
        let pts: Vec<P> = path.iter().map(|s| apply(&it.ctm, s.last().unwrap_or(first))).collect();
        let transformed: Vec<Seg> = path.iter().map(|s| s.map(&it.ctm)).collect();
        self.counter += 1;
        let (lines, closed, single) = flatten(&transformed, self.height);
        if lines.is_empty() {
            return;
        }
        let b = bound(&pts);
        let h = self.height;
        self.paths.push(Path {
            z: self.counter,
            bbox: [b[0], h - b[3], b[2], h - b[1]],
            polylines: lines,
            closed,
            single,
            stroke,
            fill,
            white: fill && is_white(&it.gs.ncolor),
            image: false,
        });
    }
}
