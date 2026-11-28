//! PDF objects, a PostScript-style lexer that follows pdfminer.six's `psparser` rules,
//! the file-level parser (xref tables, xref streams, object streams, a fallback scan)
//! and stream filters.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::rc::Rc;

#[derive(Debug, Clone)]
pub struct Error(pub &'static str);

pub type Res<T> = Result<T, Error>;

#[derive(Clone, Debug)]
pub enum Obj {
    Null,
    Bool(bool),
    Int(i64),
    Real(f64),
    Str(Rc<Vec<u8>>),
    Name(Rc<str>),
    Array(Rc<Vec<Obj>>),
    Dict(Rc<Dict>),
    Stream(Rc<Stream>),
    Ref(u32),
    Keyword(Rc<str>),
}

#[derive(Debug, Default)]
pub struct Dict(pub Vec<(Rc<str>, Obj)>);

impl Dict {
    pub fn get(&self, key: &str) -> Option<&Obj> {
        self.0.iter().rev().find(|(k, _)| &**k == key).map(|(_, v)| v)
    }
    pub fn has(&self, key: &str) -> bool {
        self.get(key).is_some()
    }
}

#[derive(Debug)]
pub struct Stream {
    pub dict: Rc<Dict>,
    pub raw: Vec<u8>,
    pub objid: Option<u32>,
    decoded: RefCell<Option<Rc<Vec<u8>>>>,
}

impl Stream {
    pub fn new(dict: Rc<Dict>, raw: Vec<u8>, objid: Option<u32>) -> Stream {
        Stream {
            dict,
            raw,
            objid,
            decoded: RefCell::new(None),
        }
    }
}

impl Obj {
    pub fn num(&self) -> Option<f64> {
        match self {
            Obj::Int(i) => Some(*i as f64),
            Obj::Real(r) => Some(*r),
            Obj::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
            _ => None,
        }
    }
    pub fn int(&self) -> Option<i64> {
        match self {
            Obj::Int(i) => Some(*i),
            Obj::Bool(b) => Some(*b as i64),
            _ => None,
        }
    }
    pub fn name(&self) -> Option<&str> {
        match self {
            Obj::Name(n) => Some(n),
            _ => None,
        }
    }
    pub fn as_dict(&self) -> Option<&Rc<Dict>> {
        match self {
            Obj::Dict(d) => Some(d),
            Obj::Stream(s) => Some(&s.dict),
            _ => None,
        }
    }
    pub fn as_array(&self) -> Option<&Rc<Vec<Obj>>> {
        match self {
            Obj::Array(a) => Some(a),
            _ => None,
        }
    }
}

// ---- lexer ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub enum Tok {
    Int(i64),
    Real(f64),
    Bool(bool),
    Name(Rc<str>),
    Str(Vec<u8>),
    Kw(Rc<str>),
    ArrBegin,
    ArrEnd,
    DictBegin,
    DictEnd,
    ProcBegin,
    ProcEnd,
}

#[inline]
pub fn is_ws(c: u8) -> bool {
    matches!(c, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

#[inline]
fn ends_literal(c: u8) -> bool {
    is_ws(c) || matches!(c, b'#' | b'/' | b'%' | b'[' | b']' | b'(' | b')' | b'<' | b'>' | b'{' | b'}')
}

fn hexval(c: u8) -> Option<u8> {
    match c {
        b'0'..=b'9' => Some(c - b'0'),
        b'a'..=b'f' => Some(c - b'a' + 10),
        b'A'..=b'F' => Some(c - b'A' + 10),
        _ => None,
    }
}

fn kw(s: &[u8]) -> Tok {
    match s {
        b"[" => Tok::ArrBegin,
        b"]" => Tok::ArrEnd,
        b"{" => Tok::ProcBegin,
        b"}" => Tok::ProcEnd,
        _ => Tok::Kw(Rc::from(String::from_utf8_lossy(s).as_ref())),
    }
}

/// Tokens as pdfminer's `PSBaseParser` produces them (a missing trailing newline is
/// treated as one, as pdfminer does at EOF).
pub struct Lexer<'a> {
    pub s: &'a [u8],
    pub pos: usize,
}

impl<'a> Lexer<'a> {
    pub fn new(s: &'a [u8]) -> Lexer<'a> {
        Lexer { s, pos: 0 }
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.pos).copied()
    }

    /// Next token, `None` at EOF.
    pub fn next(&mut self) -> Option<Tok> {
        loop {
            while let Some(c) = self.peek() {
                if is_ws(c) {
                    self.pos += 1;
                } else {
                    break;
                }
            }
            let c = self.peek()?;
            self.pos += 1;
            match c {
                b'%' => {
                    while let Some(c) = self.peek() {
                        if c == b'\r' || c == b'\n' {
                            break;
                        }
                        self.pos += 1;
                    }
                }
                b'/' => return Some(self.literal()),
                b'-' | b'+' | b'0'..=b'9' => {
                    if let Some(t) = self.number(c) {
                        return Some(t);
                    }
                }
                b'.' => {
                    if let Some(t) = self.float(vec![b'.']) {
                        return Some(t);
                    }
                }
                b'(' => {
                    if let Some(t) = self.string() {
                        return Some(t);
                    }
                }
                b'<' => {
                    if self.peek() == Some(b'<') {
                        self.pos += 1;
                        return Some(Tok::DictBegin);
                    }
                    return Some(self.hexstring());
                }
                b'>' => {
                    if self.peek() == Some(b'>') {
                        self.pos += 1;
                        return Some(Tok::DictEnd);
                    }
                }
                0 => {}
                c if c.is_ascii_alphabetic() => {
                    let start = self.pos - 1;
                    while let Some(c) = self.peek() {
                        if ends_literal(c) {
                            break;
                        }
                        self.pos += 1;
                    }
                    let word = &self.s[start..self.pos];
                    return Some(match word {
                        b"true" => Tok::Bool(true),
                        b"false" => Tok::Bool(false),
                        _ => kw(word),
                    });
                }
                c => return Some(kw(&[c])),
            }
        }
    }

    fn literal(&mut self) -> Tok {
        let mut name = Vec::new();
        while let Some(c) = self.peek() {
            if c == b'#' {
                self.pos += 1;
                let mut hex = 0u8;
                let mut n = 0;
                while n < 2 {
                    match self.peek().and_then(hexval) {
                        Some(h) => {
                            hex = hex * 16 + h;
                            n += 1;
                            self.pos += 1;
                        }
                        None => break,
                    }
                }
                if n > 0 {
                    name.push(hex);
                }
                continue;
            }
            if ends_literal(c) {
                break;
            }
            name.push(c);
            self.pos += 1;
        }
        Tok::Name(Rc::from(String::from_utf8_lossy(&name).as_ref()))
    }

    fn number(&mut self, first: u8) -> Option<Tok> {
        let mut tok = vec![first];
        while let Some(c) = self.peek() {
            if c.is_ascii_digit() {
                tok.push(c);
                self.pos += 1;
            } else {
                break;
            }
        }
        if self.peek() == Some(b'.') {
            self.pos += 1;
            tok.push(b'.');
            return self.float(tok);
        }
        let s = std::str::from_utf8(&tok).ok()?;
        match s.parse::<i64>() {
            Ok(v) => Some(Tok::Int(v)),
            Err(_) => s.parse::<f64>().ok().filter(|_| s.len() > 1).map(Tok::Real),
        }
    }

    fn float(&mut self, mut tok: Vec<u8>) -> Option<Tok> {
        while let Some(c) = self.peek() {
            if c.is_ascii_digit() {
                tok.push(c);
                self.pos += 1;
            } else {
                break;
            }
        }
        let s = std::str::from_utf8(&tok).ok()?;
        // Python float() accepts "5." and ".5" but not "." / "-." / "+.".
        if !tok.iter().any(|c| c.is_ascii_digit()) {
            return None;
        }
        s.parse::<f64>().ok().map(Tok::Real)
    }

    fn string(&mut self) -> Option<Tok> {
        let mut out = Vec::new();
        let mut depth = 1;
        loop {
            let c = match self.peek() {
                Some(c) => c,
                None => return None,
            };
            self.pos += 1;
            match c {
                b'\\' => {
                    let mut oct = 0u32;
                    let mut n = 0;
                    while n < 3 {
                        match self.peek() {
                            Some(d @ b'0'..=b'7') => {
                                oct = oct * 8 + (d - b'0') as u32;
                                n += 1;
                                self.pos += 1;
                            }
                            _ => break,
                        }
                    }
                    if n > 0 {
                        out.push((oct & 0xff) as u8);
                        continue;
                    }
                    match self.peek() {
                        Some(e) => {
                            self.pos += 1;
                            match e {
                                b'b' => out.push(8),
                                b't' => out.push(9),
                                b'n' => out.push(10),
                                b'f' => out.push(12),
                                b'r' => out.push(13),
                                b'(' | b')' | b'\\' => out.push(e),
                                b'\r' if self.peek() == Some(b'\n') => self.pos += 1,
                                _ => {}
                            }
                        }
                        None => return None,
                    }
                }
                b'(' => {
                    depth += 1;
                    out.push(c);
                }
                b')' => {
                    depth -= 1;
                    if depth == 0 {
                        return Some(Tok::Str(out));
                    }
                    out.push(c);
                }
                _ => out.push(c),
            }
        }
    }

    fn hexstring(&mut self) -> Tok {
        let mut digits = Vec::new();
        while let Some(c) = self.peek() {
            if is_ws(c) {
                self.pos += 1;
            } else if let Some(h) = hexval(c) {
                digits.push(h);
                self.pos += 1;
            } else {
                break;
            }
        }
        let mut out = Vec::with_capacity(digits.len() / 2 + 1);
        for pair in digits.chunks(2) {
            if pair.len() == 2 {
                out.push(pair[0] * 16 + pair[1]);
            } else {
                out.push(pair[0]);
            }
        }
        Tok::Str(out)
    }
}

fn tok_obj(t: Tok) -> Obj {
    match t {
        Tok::Int(i) => Obj::Int(i),
        Tok::Real(r) => Obj::Real(r),
        Tok::Bool(b) => Obj::Bool(b),
        Tok::Name(n) => Obj::Name(n),
        Tok::Str(s) => Obj::Str(Rc::new(s)),
        Tok::Kw(k) => Obj::Keyword(k),
        _ => Obj::Null,
    }
}

pub fn dict_from(objs: Vec<Obj>) -> Dict {
    let mut out = Vec::with_capacity(objs.len() / 2);
    let mut it = objs.into_iter();
    while let (Some(k), Some(v)) = (it.next(), it.next()) {
        let key: Rc<str> = match k {
            Obj::Name(n) => n,
            Obj::Keyword(n) => n,
            _ => Rc::from(""),
        };
        out.push((key, v));
    }
    Dict(out)
}

#[derive(PartialEq, Clone, Copy)]
enum Ctx {
    Array,
    Dict,
    Proc,
    Inline,
}

/// pdfminer's `PDFContentParser`: emits top-level objects (keywords included) in order.
pub struct ContentParser<'a> {
    lex: Lexer<'a>,
    ctx: Vec<(Ctx, Vec<Obj>)>,
    cur: Vec<Obj>,
    out: std::collections::VecDeque<Obj>,
}

impl<'a> ContentParser<'a> {
    pub fn new(s: &'a [u8]) -> ContentParser<'a> {
        ContentParser {
            lex: Lexer::new(s),
            ctx: Vec::new(),
            cur: Vec::new(),
            out: Default::default(),
        }
    }

    fn end(&mut self, kind: Ctx) -> Option<Vec<Obj>> {
        match self.ctx.last() {
            Some((k, _)) if *k == kind => {
                let (_, prev) = self.ctx.pop()?;
                Some(std::mem::replace(&mut self.cur, prev))
            }
            _ => None,
        }
    }

    fn inline_data(&mut self, eos: &[u8]) -> Vec<u8> {
        // get_inline_data(pos + len("ID "), target)
        let s = self.lex.s;
        let mut p = (self.lex.pos + 1).min(s.len());
        let start = p;
        let mut i = 0usize;
        while i <= eos.len() {
            if p >= s.len() {
                break;
            }
            let c = s[p];
            p += 1;
            if i == 0 {
                if c == eos[0] {
                    i = 1;
                }
                continue;
            }
            if (eos.len() <= i && is_ws_py(c)) || (i < eos.len() && c == eos[i]) {
                i += 1;
            } else {
                i = 0;
            }
        }
        self.lex.pos = p;
        let mut data = s[start..p].to_vec();
        let cut = data.len().saturating_sub(eos.len() + 1);
        data.truncate(cut);
        if data.ends_with(b"\r\n") {
            data.truncate(data.len() - 2);
        } else if data.ends_with(b"\r") || data.ends_with(b"\n") {
            data.truncate(data.len() - 1);
        }
        data
    }

    pub fn next(&mut self) -> Option<Obj> {
        loop {
            if let Some(o) = self.out.pop_front() {
                return Some(o);
            }
            let t = self.lex.next()?;
            match t {
                Tok::ArrBegin => self.start(Ctx::Array),
                Tok::DictBegin => self.start(Ctx::Dict),
                Tok::ProcBegin => self.start(Ctx::Proc),
                Tok::ArrEnd | Tok::ProcEnd => {
                    let k = if matches!(t, Tok::ArrEnd) { Ctx::Array } else { Ctx::Proc };
                    if let Some(objs) = self.end(k) {
                        self.cur.push(Obj::Array(Rc::new(objs)));
                    }
                }
                Tok::DictEnd => {
                    if let Some(objs) = self.end(Ctx::Dict) {
                        self.cur.push(Obj::Dict(Rc::new(dict_from(objs))));
                    }
                }
                Tok::Kw(ref k) if &**k == "BI" => self.start(Ctx::Inline),
                Tok::Kw(ref k) if &**k == "ID" => {
                    if let Some(objs) = self.end(Ctx::Inline) {
                        let d = dict_from(objs);
                        let mut eos: &[u8] = b"EI";
                        if let Some(f) = d.get("F") {
                            let first = match f {
                                Obj::Array(a) => a.first().and_then(|x| x.name()).map(|s| s.to_string()),
                                Obj::Name(n) => Some(n.to_string()),
                                _ => None,
                            };
                            if matches!(first.as_deref(), Some("ASCII85Decode") | Some("A85")) {
                                eos = b"~>";
                            }
                        }
                        let mut data = self.inline_data(eos);
                        if eos != b"EI" {
                            data.extend_from_slice(eos);
                        }
                        self.cur.push(Obj::Stream(Rc::new(Stream::new(Rc::new(d), data, None))));
                        if eos == b"EI" {
                            self.cur.push(Obj::Keyword(Rc::from("EI")));
                        }
                    }
                }
                other => self.cur.push(tok_obj(other)),
            }
            if self.ctx.is_empty() {
                self.out.extend(self.cur.drain(..));
            }
        }
    }

    fn start(&mut self, k: Ctx) {
        let prev = std::mem::take(&mut self.cur);
        self.ctx.push((k, prev));
    }
}

/// Python `bytes.isspace` for one byte.
fn is_ws_py(c: u8) -> bool {
    is_ws(c)
}

/// A generic PS stack machine with pdfminer's `PSStackParser` contexts; `flush` is a no-op,
/// so the whole input stays on one stack and `on_kw` decides what keywords do.
pub fn ps_run(data: &[u8], mut on_kw: impl FnMut(&str, &mut Vec<Obj>)) {
    let mut lex = Lexer::new(data);
    let mut ctx: Vec<(u8, Vec<Obj>)> = Vec::new();
    let mut cur: Vec<Obj> = Vec::new();
    while let Some(t) = lex.next() {
        match t {
            Tok::ArrBegin | Tok::DictBegin | Tok::ProcBegin => {
                let k = match t {
                    Tok::ArrBegin => b'a',
                    Tok::DictBegin => b'd',
                    _ => b'p',
                };
                ctx.push((k, std::mem::take(&mut cur)));
            }
            Tok::ArrEnd | Tok::ProcEnd | Tok::DictEnd => {
                let k = match t {
                    Tok::ArrEnd => b'a',
                    Tok::DictEnd => b'd',
                    _ => b'p',
                };
                if matches!(ctx.last(), Some((kk, _)) if *kk == k) {
                    if let Some((_, prev)) = ctx.pop() {
                        let objs = std::mem::replace(&mut cur, prev);
                        cur.push(if k == b'd' {
                            Obj::Dict(Rc::new(dict_from(objs)))
                        } else {
                            Obj::Array(Rc::new(objs))
                        });
                    }
                }
            }
            Tok::Kw(k) => on_kw(&k, &mut cur),
            other => cur.push(tok_obj(other)),
        }
    }
}

// ---- filters -------------------------------------------------------------------------

fn flate(data: &[u8]) -> Vec<u8> {
    match miniz_oxide::inflate::decompress_to_vec_zlib(data) {
        Ok(v) => v,
        Err(e) => {
            // pdfminer falls back to a byte-wise decompress that keeps what it got.
            let partial = e.output;
            if !partial.is_empty() {
                partial
            } else {
                miniz_oxide::inflate::decompress_to_vec(data.get(2..).unwrap_or(&[]))
                    .unwrap_or_default()
            }
        }
    }
}

fn ascii_hex(data: &[u8]) -> Vec<u8> {
    let mut digits = Vec::new();
    for &c in data {
        if c == b'>' {
            break;
        }
        if let Some(h) = hexval(c) {
            digits.push(h);
        }
    }
    if digits.len() % 2 == 1 {
        digits.push(0);
    }
    digits.chunks(2).map(|p| p[0] * 16 + p[1]).collect()
}

fn ascii85(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut n = 0u32;
    let mut b = 0u64;
    let body = data.strip_prefix(b"<~").unwrap_or(data);
    for &c in body {
        if c == b'~' {
            break;
        }
        if (b'!'..=b'u').contains(&c) {
            n += 1;
            b = b * 85 + (c - 33) as u64;
            if n == 5 {
                out.extend_from_slice(&(b as u32).to_be_bytes());
                n = 0;
                b = 0;
            }
        } else if c == b'z' && n == 0 {
            out.extend_from_slice(&[0, 0, 0, 0]);
        }
    }
    if n > 0 {
        for _ in n..5 {
            b = b * 85 + 84;
        }
        out.extend_from_slice(&(b as u32).to_be_bytes()[..(n - 1) as usize]);
    }
    out
}

fn png_predictor(data: &[u8], colors: usize, bpc: usize, columns: usize) -> Vec<u8> {
    let bpp = (colors * bpc).div_ceil(8).max(1);
    let row = (colors * bpc * columns).div_ceil(8);
    let mut out = Vec::with_capacity(data.len());
    let mut prev = vec![0u8; row];
    for chunk in data.chunks(row + 1) {
        if chunk.is_empty() {
            break;
        }
        let ft = chunk[0];
        let mut line = chunk[1..].to_vec();
        line.resize(row, 0);
        for i in 0..row {
            let a = if i >= bpp { line[i - bpp] } else { 0 };
            let b = prev[i];
            let c = if i >= bpp { prev[i - bpp] } else { 0 };
            let x = line[i];
            line[i] = match ft {
                1 => x.wrapping_add(a),
                2 => x.wrapping_add(b),
                3 => x.wrapping_add(((a as u16 + b as u16) / 2) as u8),
                4 => {
                    let p = a as i16 + b as i16 - c as i16;
                    let (pa, pb, pc) = ((p - a as i16).abs(), (p - b as i16).abs(), (p - c as i16).abs());
                    let pr = if pa <= pb && pa <= pc {
                        a
                    } else if pb <= pc {
                        b
                    } else {
                        c
                    };
                    x.wrapping_add(pr)
                }
                _ => x,
            };
        }
        out.extend_from_slice(&line);
        prev = line;
    }
    out
}

pub fn decode_stream(st: &Stream) -> Rc<Vec<u8>> {
    if let Some(d) = st.decoded.borrow().as_ref() {
        return d.clone();
    }
    let d = &st.dict;
    let filters: Vec<String> = match d.get("Filter").or_else(|| d.get("F")) {
        Some(Obj::Name(n)) => vec![n.to_string()],
        Some(Obj::Array(a)) => a.iter().filter_map(|x| x.name().map(|s| s.to_string())).collect(),
        _ => vec![],
    };
    let parms: Vec<Option<Rc<Dict>>> = match d.get("DecodeParms").or_else(|| d.get("DP")) {
        Some(Obj::Dict(p)) => vec![Some(p.clone())],
        Some(Obj::Array(a)) => a.iter().map(|x| x.as_dict().cloned()).collect(),
        _ => vec![],
    };
    let mut data = st.raw.clone();
    for (n, f) in filters.iter().enumerate() {
        data = match f.as_str() {
            "FlateDecode" | "Fl" => flate(&data),
            "ASCIIHexDecode" | "AHx" => ascii_hex(&data),
            "ASCII85Decode" | "A85" => ascii85(&data),
            _ => break, // DCT, JPX, JBIG2, CCITT, LZW, RunLength: kept raw (not needed for geometry)
        };
        if let Some(Some(p)) = parms.get(n).or_else(|| parms.first()) {
            let pred = p.get("Predictor").and_then(|x| x.int()).unwrap_or(1);
            if pred >= 10 {
                let colors = p.get("Colors").and_then(|x| x.int()).unwrap_or(1).max(1) as usize;
                let bpc = p.get("BitsPerComponent").and_then(|x| x.int()).unwrap_or(8).max(1) as usize;
                let cols = p.get("Columns").and_then(|x| x.int()).unwrap_or(1).max(1) as usize;
                data = png_predictor(&data, colors, bpc, cols);
            }
        }
    }
    let rc = Rc::new(data);
    *st.decoded.borrow_mut() = Some(rc.clone());
    rc
}

// ---- document ------------------------------------------------------------------------

#[derive(Clone, Copy, Debug)]
enum XRef {
    Offset(usize),
    InStream(u32, usize),
}

pub struct Doc<'a> {
    data: &'a [u8],
    xref: HashMap<u32, XRef>,
    pub trailer: Rc<Dict>,
    cache: RefCell<HashMap<u32, Obj>>,
    objstm: RefCell<HashMap<u32, Rc<Vec<Obj>>>>,
}

/// Object parser over a byte slice (indirect references, `stream` bodies).
struct ObjParser<'a, 'd> {
    lex: Lexer<'a>,
    doc: Option<&'d Doc<'a>>,
}

impl<'a> ObjParser<'a, '_> {
    fn value(&mut self, depth: usize) -> Option<Obj> {
        if depth > 64 {
            return None;
        }
        let t = self.lex.next()?;
        Some(match t {
            Tok::Int(i) => {
                let save = self.lex.pos;
                if let Some(Tok::Int(_g)) = self.lex.next() {
                    if let Some(Tok::Kw(k)) = self.lex.next() {
                        if &*k == "R" && i >= 0 {
                            return Some(Obj::Ref(i as u32));
                        }
                    }
                }
                self.lex.pos = save;
                Obj::Int(i)
            }
            Tok::ArrBegin => {
                let mut v = Vec::new();
                loop {
                    let save = self.lex.pos;
                    match self.lex.next() {
                        Some(Tok::ArrEnd) | None => break,
                        _ => {
                            self.lex.pos = save;
                            match self.value(depth + 1) {
                                Some(o) => v.push(o),
                                None => break,
                            }
                        }
                    }
                }
                Obj::Array(Rc::new(v))
            }
            Tok::DictBegin => {
                let mut v = Vec::new();
                loop {
                    let save = self.lex.pos;
                    match self.lex.next() {
                        Some(Tok::DictEnd) | None => break,
                        _ => {
                            self.lex.pos = save;
                            match self.value(depth + 1) {
                                Some(o) => v.push(o),
                                None => break,
                            }
                        }
                    }
                }
                // pdfminer drops keys whose value is null
                let d = dict_from(v);
                Obj::Dict(Rc::new(Dict(
                    d.0.into_iter()
                        .filter(|(_, v)| !matches!(v, Obj::Keyword(k) if &**k == "null"))
                        .collect(),
                )))
            }
            Tok::Kw(k) if &*k == "null" => Obj::Null,
            other => tok_obj(other),
        })
    }

    /// After a dict, an optional `stream ... endstream`.
    fn maybe_stream(&mut self, obj: Obj, objid: Option<u32>) -> Obj {
        let d = match &obj {
            Obj::Dict(d) => d.clone(),
            _ => return obj,
        };
        let save = self.lex.pos;
        match self.lex.next() {
            Some(Tok::Kw(k)) if &*k == "stream" => {}
            _ => {
                self.lex.pos = save;
                return obj;
            }
        }
        let s = self.lex.s;
        let mut p = self.lex.pos;
        if s.get(p) == Some(&b'\r') {
            p += 1;
        }
        if s.get(p) == Some(&b'\n') {
            p += 1;
        }
        let mut len = d.get("Length").cloned();
        if let (Some(Obj::Ref(r)), Some(doc)) = (&len, self.doc) {
            len = doc.getobj(*r).ok();
        }
        let len = len.and_then(|x| x.int()).unwrap_or(-1);
        let mut end = None;
        if len >= 0 {
            let e = p.saturating_add(len as usize);
            if e <= s.len() {
                let tail = &s[e..(e + 20).min(s.len())];
                let t = tail.iter().position(|c| !is_ws(*c)).unwrap_or(tail.len());
                if tail[t..].starts_with(b"endstream") {
                    end = Some(e);
                }
            }
        }
        let end = match end {
            Some(e) => e,
            None => match find(&s[p..], b"endstream") {
                Some(i) => {
                    let mut e = p + i;
                    if e > p && s[e - 1] == b'\n' {
                        e -= 1;
                        if e > p && s[e - 1] == b'\r' {
                            e -= 1;
                        }
                    } else if e > p && s[e - 1] == b'\r' {
                        e -= 1;
                    }
                    e
                }
                None => s.len(),
            },
        };
        self.lex.pos = end;
        Obj::Stream(Rc::new(Stream::new(d, s[p..end].to_vec(), objid)))
    }
}

pub fn find(h: &[u8], n: &[u8]) -> Option<usize> {
    if n.is_empty() || h.len() < n.len() {
        return None;
    }
    h.windows(n.len()).position(|w| w == n)
}

fn rfind(h: &[u8], n: &[u8]) -> Option<usize> {
    if h.len() < n.len() {
        return None;
    }
    h.windows(n.len()).rposition(|w| w == n)
}

impl<'a> Doc<'a> {
    pub fn open(data: &'a [u8]) -> Res<Doc<'a>> {
        let mut doc = Doc {
            data,
            xref: HashMap::new(),
            trailer: Rc::new(Dict::default()),
            cache: RefCell::new(HashMap::new()),
            objstm: RefCell::new(HashMap::new()),
        };
        let ok = doc.load_xrefs().is_ok() && doc.trailer.has("Root");
        if !ok {
            doc.xref.clear();
            doc.cache.borrow_mut().clear();
            doc.fallback()?;
        }
        if doc.trailer.has("Encrypt") {
            return Err(Error("PDFEncryptionError"));
        }
        if !doc.trailer.has("Root") {
            return Err(Error("PDFSyntaxError"));
        }
        Ok(doc)
    }

    fn parser(&self, pos: usize) -> ObjParser<'a, '_> {
        let mut lex = Lexer::new(self.data);
        lex.pos = pos;
        ObjParser { lex, doc: Some(self) }
    }

    fn load_xrefs(&mut self) -> Res<()> {
        let tail_start = self.data.len().saturating_sub(4096);
        let i = rfind(&self.data[tail_start..], b"startxref").ok_or(Error("PDFNoValidXRef"))?;
        let mut lex = Lexer::new(self.data);
        lex.pos = tail_start + i + 9;
        let mut offset = match lex.next() {
            Some(Tok::Int(o)) if o >= 0 => o as usize,
            _ => return Err(Error("PDFNoValidXRef")),
        };
        let mut seen = HashSet::new();
        let mut first = true;
        let mut pending: Vec<usize> = Vec::new();
        loop {
            if !seen.insert(offset) || offset >= self.data.len() {
                break;
            }
            let trailer = self.read_xref_at(offset)?;
            if first {
                self.trailer = trailer.clone();
                first = false;
            } else if !self.trailer.has("Root") && trailer.has("Root") {
                self.trailer = trailer.clone();
            }
            if let Some(x) = trailer.get("XRefStm").and_then(|x| x.int()) {
                pending.push(x as usize);
            }
            for p in pending.drain(..) {
                if seen.insert(p) {
                    let _ = self.read_xref_at(p);
                }
            }
            match trailer.get("Prev").and_then(|x| x.int()) {
                Some(p) if p >= 0 => offset = p as usize,
                _ => break,
            }
        }
        Ok(())
    }

    fn read_xref_at(&mut self, offset: usize) -> Res<Rc<Dict>> {
        let mut lex = Lexer::new(self.data);
        lex.pos = offset;
        let save = lex.pos;
        match lex.next() {
            Some(Tok::Kw(k)) if &*k == "xref" => {
                loop {
                    let save = lex.pos;
                    let start = match lex.next() {
                        Some(Tok::Int(s)) => s,
                        Some(Tok::Kw(k)) if &*k == "trailer" => break,
                        _ => {
                            lex.pos = save;
                            break;
                        }
                    };
                    let count = match lex.next() {
                        Some(Tok::Int(c)) => c,
                        _ => return Err(Error("PDFNoValidXRef")),
                    };
                    for n in 0..count.max(0) {
                        let off = lex.next();
                        let _gen = lex.next();
                        let kind = lex.next();
                        let id = (start + n) as u32;
                        if let (Some(Tok::Int(o)), Some(Tok::Kw(k))) = (off, kind) {
                            if &*k == "n" {
                                self.xref.entry(id).or_insert(XRef::Offset(o.max(0) as usize));
                            }
                        } else {
                            return Err(Error("PDFNoValidXRef"));
                        }
                    }
                }
                let mut p = ObjParser { lex, doc: None };
                match p.value(0) {
                    Some(Obj::Dict(d)) => Ok(d),
                    _ => Err(Error("PDFNoValidXRef")),
                }
            }
            _ => {
                lex.pos = save;
                let (Some(Tok::Int(_)), Some(Tok::Int(_)), Some(Tok::Kw(k))) = (lex.next(), lex.next(), lex.next())
                else {
                    return Err(Error("PDFNoValidXRef"));
                };
                if &*k != "obj" {
                    return Err(Error("PDFNoValidXRef"));
                }
                let mut p = ObjParser { lex, doc: None };
                let v = p.value(0).ok_or(Error("PDFNoValidXRef"))?;
                let st = match p.maybe_stream(v, None) {
                    Obj::Stream(s) => s,
                    _ => return Err(Error("PDFNoValidXRef")),
                };
                let d = st.dict.clone();
                let w: Vec<usize> = d
                    .get("W")
                    .and_then(|x| x.as_array().cloned())
                    .map(|a| a.iter().map(|x| x.int().unwrap_or(0).max(0) as usize).collect())
                    .unwrap_or_default();
                if w.len() < 3 {
                    return Err(Error("PDFNoValidXRef"));
                }
                let size = d.get("Size").and_then(|x| x.int()).unwrap_or(0);
                let index: Vec<i64> = d
                    .get("Index")
                    .and_then(|x| x.as_array().cloned())
                    .map(|a| a.iter().map(|x| x.int().unwrap_or(0)).collect())
                    .unwrap_or_else(|| vec![0, size]);
                let data = decode_stream(&st);
                let rowlen: usize = w.iter().sum();
                let mut pos = 0;
                let field = |b: &[u8]| b.iter().fold(0u64, |a, c| a * 256 + *c as u64);
                for pair in index.chunks(2) {
                    if pair.len() < 2 {
                        break;
                    }
                    for n in 0..pair[1].max(0) {
                        if pos + rowlen > data.len() {
                            break;
                        }
                        let row = &data[pos..pos + rowlen];
                        pos += rowlen;
                        let t = if w[0] == 0 { 1 } else { field(&row[..w[0]]) };
                        let f1 = field(&row[w[0]..w[0] + w[1]]);
                        let f2 = field(&row[w[0] + w[1]..]);
                        let id = (pair[0] + n) as u32;
                        match t {
                            1 => {
                                self.xref.entry(id).or_insert(XRef::Offset(f1 as usize));
                            }
                            2 => {
                                self.xref.entry(id).or_insert(XRef::InStream(f1 as u32, f2 as usize));
                            }
                            _ => {}
                        }
                    }
                }
                Ok(d)
            }
        }
    }

    fn fallback(&mut self) -> Res<()> {
        let data = self.data;
        let mut trailer: Option<Rc<Dict>> = None;
        let mut start = 0;
        let mut stms = Vec::new();
        while start < data.len() {
            let end = data[start..]
                .iter()
                .position(|c| *c == b'\n' || *c == b'\r')
                .map(|e| start + e)
                .unwrap_or(data.len());
            let line = &data[start..end];
            if line.starts_with(b"trailer") {
                let mut p = self.parser(start + 7);
                if let Some(Obj::Dict(d)) = p.value(0) {
                    trailer = Some(d);
                }
            } else {
                let mut lex = Lexer::new(line);
                if let (Some(Tok::Int(id)), Some(Tok::Int(_)), Some(Tok::Kw(k))) = (lex.next(), lex.next(), lex.next())
                {
                    if line.first().is_some_and(|c| c.is_ascii_digit()) && (&*k == "obj" || k.starts_with("obj")) {
                        self.xref.insert(id as u32, XRef::Offset(start));
                        stms.push(id as u32);
                    }
                }
            }
            start = end + 1;
        }
        for id in stms {
            if let Ok(Obj::Stream(s)) = self.getobj(id) {
                let ty = s.dict.get("Type").and_then(|x| x.name()).unwrap_or("");
                if ty == "ObjStm" {
                    if let Ok(objs) = self.objstm_ids(id, &s) {
                        for (n, oid) in objs.into_iter().enumerate() {
                            self.xref.entry(oid).or_insert(XRef::InStream(id, n));
                        }
                    }
                } else if ty == "XRef" && trailer.is_none() {
                    trailer = Some(s.dict.clone());
                }
            }
        }
        self.cache.borrow_mut().clear();
        self.trailer = trailer.ok_or(Error("PDFSyntaxError"))?;
        Ok(())
    }

    fn objstm_ids(&self, _id: u32, s: &Stream) -> Res<Vec<u32>> {
        let n = s.dict.get("N").and_then(|x| x.int()).unwrap_or(0);
        let data = decode_stream(s);
        let mut lex = Lexer::new(&data);
        let mut out = Vec::new();
        for _ in 0..n {
            match (lex.next(), lex.next()) {
                (Some(Tok::Int(a)), Some(Tok::Int(_))) => out.push(a as u32),
                _ => break,
            }
        }
        Ok(out)
    }

    pub fn getobj(&self, id: u32) -> Res<Obj> {
        if let Some(o) = self.cache.borrow().get(&id) {
            return Ok(o.clone());
        }
        let entry = *self.xref.get(&id).ok_or(Error("PDFObjectNotFound"))?;
        let obj = match entry {
            XRef::Offset(off) => {
                let mut p = self.parser(off);
                let (Some(Tok::Int(_)), Some(Tok::Int(_)), Some(Tok::Kw(k))) = (p.lex.next(), p.lex.next(), p.lex.next())
                else {
                    return Err(Error("PDFSyntaxError"));
                };
                if !k.starts_with("obj") {
                    return Err(Error("PDFSyntaxError"));
                }
                let v = p.value(0).ok_or(Error("PDFSyntaxError"))?;
                p.maybe_stream(v, Some(id))
            }
            XRef::InStream(stm, idx) => {
                let objs = self.load_objstm(stm)?;
                objs.get(idx).cloned().ok_or(Error("PDFObjectNotFound"))?
            }
        };
        self.cache.borrow_mut().insert(id, obj.clone());
        Ok(obj)
    }

    fn load_objstm(&self, stm: u32) -> Res<Rc<Vec<Obj>>> {
        if let Some(v) = self.objstm.borrow().get(&stm) {
            return Ok(v.clone());
        }
        let s = match self.getobj(stm)? {
            Obj::Stream(s) => s,
            _ => return Err(Error("PDFSyntaxError")),
        };
        let n = s.dict.get("N").and_then(|x| x.int()).unwrap_or(0).max(0) as usize;
        let first = s.dict.get("First").and_then(|x| x.int()).unwrap_or(0).max(0) as usize;
        let data = decode_stream(&s);
        let mut lex = Lexer::new(&data);
        let mut offs = Vec::new();
        for _ in 0..n {
            match (lex.next(), lex.next()) {
                (Some(Tok::Int(_)), Some(Tok::Int(o))) => offs.push(o.max(0) as usize),
                _ => break,
            }
        }
        let mut objs = Vec::with_capacity(offs.len());
        for o in offs {
            let mut lex = Lexer::new(&data);
            lex.pos = (first + o).min(data.len());
            let mut p = ObjParser { lex, doc: None };
            objs.push(p.value(0).unwrap_or(Obj::Null));
        }
        let rc = Rc::new(objs);
        self.objstm.borrow_mut().insert(stm, rc.clone());
        Ok(rc)
    }

    /// pdfminer `resolve1`.
    pub fn resolve(&self, o: &Obj) -> Obj {
        let mut cur = o.clone();
        for _ in 0..32 {
            match cur {
                Obj::Ref(r) => cur = self.getobj(r).unwrap_or(Obj::Null),
                other => return other,
            }
        }
        Obj::Null
    }

    pub fn rdict(&self, o: Option<&Obj>) -> Option<Rc<Dict>> {
        o.map(|o| self.resolve(o)).and_then(|o| o.as_dict().cloned())
    }

    pub fn rarray(&self, o: Option<&Obj>) -> Option<Rc<Vec<Obj>>> {
        o.map(|o| self.resolve(o)).and_then(|o| o.as_array().cloned())
    }

    pub fn rnum(&self, o: Option<&Obj>) -> Option<f64> {
        o.map(|o| self.resolve(o)).and_then(|o| o.num())
    }

    /// The pages in pdfminer's `PDFPage.create_pages` order, with inherited attributes.
    pub fn pages(&self) -> Res<Vec<(u32, Dict)>> {
        let root = self.rdict(self.trailer.get("Root")).ok_or(Error("PDFSyntaxError"))?;
        let mut out = Vec::new();
        if let Some(pages) = root.get("Pages") {
            let mut visited = HashSet::new();
            self.dfs(pages, &root, &mut visited, &mut out, 0);
        }
        if out.is_empty() {
            let mut ids: Vec<u32> = self.xref.keys().copied().collect();
            ids.sort_unstable();
            for id in ids {
                if let Ok(Obj::Dict(d)) = self.getobj(id) {
                    if d.get("Type").and_then(|x| x.name()) == Some("Page") {
                        out.push((id, Dict(d.0.clone())));
                    }
                }
            }
        }
        Ok(out)
    }

    fn dfs(&self, obj: &Obj, parent: &Dict, visited: &mut HashSet<u32>, out: &mut Vec<(u32, Dict)>, depth: usize) {
        if depth > 64 {
            return;
        }
        let id = match obj {
            Obj::Ref(r) => *r,
            _ => u32::MAX - depth as u32,
        };
        if !visited.insert(id) {
            return;
        }
        let d = match self.resolve(obj).as_dict() {
            Some(d) => d.clone(),
            None => return,
        };
        let mut props = Dict(d.0.clone());
        for (k, v) in &parent.0 {
            if matches!(&**k, "Resources" | "MediaBox" | "CropBox" | "Rotate") && !props.has(k) {
                props.0.push((k.clone(), v.clone()));
            }
        }
        let ty = props.get("Type").or_else(|| props.get("type")).and_then(|x| x.name()).map(|s| s.to_string());
        match ty.as_deref() {
            Some("Pages") if props.has("Kids") => {
                if let Some(kids) = self.rarray(props.get("Kids")) {
                    for k in kids.iter() {
                        self.dfs(k, &props, visited, out, depth + 1);
                    }
                }
            }
            Some("Page") => out.push((id, props)),
            _ => {}
        }
    }
}
