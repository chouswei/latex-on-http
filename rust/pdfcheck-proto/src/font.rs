//! Fonts the way pdfminer.six's `pdffont` reads them: widths, descent, decoding and text.

use crate::pdf::{decode_stream, ps_run, Dict, Doc, Obj};
use crate::tables;
use std::collections::HashMap;
use std::rc::Rc;
use std::sync::OnceLock;

pub fn glyph_lookup(name: &str) -> Option<&'static str> {
    tables::GLYPHLIST
        .binary_search_by(|(k, _)| (*k).cmp(name))
        .ok()
        .map(|i| tables::GLYPHLIST[i].1)
}

fn is_hex(s: &str) -> bool {
    // HEXADECIMAL.match: at least one hex digit at the start
    s.chars().next().is_some_and(|c| c.is_ascii_hexdigit())
}

fn valid_cp(v: u32) -> bool {
    !(55295 < v && v < 57344)
}

/// pdfminer `name2unicode`; `None` is its KeyError.
pub fn name2unicode(name: &str) -> Option<String> {
    let name = name.split('.').next().unwrap_or("");
    let parts: Vec<&str> = name.split('_').collect();
    if parts.len() > 1 {
        let mut out = String::new();
        for p in parts {
            out.push_str(&name2unicode(p)?);
        }
        return Some(out);
    }
    if let Some(u) = glyph_lookup(name) {
        return Some(u.to_string());
    }
    if name.starts_with("uni") {
        let rest = name.trim_matches(|c| c == 'u' || c == 'n' || c == 'i');
        if is_hex(rest) && rest.len() % 4 == 0 {
            let mut out = String::new();
            let b = rest.as_bytes();
            for i in (0..b.len()).step_by(4) {
                let v = u32::from_str_radix(std::str::from_utf8(&b[i..i + 4]).ok()?, 16).ok()?;
                if !valid_cp(v) {
                    return None;
                }
                out.push(char::from_u32(v)?);
            }
            return Some(out);
        }
        return None;
    }
    if name.starts_with('u') {
        let rest = name.trim_matches('u');
        if is_hex(rest) && (4..=6).contains(&rest.len()) {
            let v = u32::from_str_radix(rest, 16).ok()?;
            if !valid_cp(v) {
                return None;
            }
            return char::from_u32(v).map(|c| c.to_string());
        }
    }
    None
}

fn base_encoding(name: &str) -> HashMap<u32, String> {
    let t: &[(u8, &str)] = match name {
        "MacRomanEncoding" => tables::ENC_MAC,
        "WinAnsiEncoding" => tables::ENC_WIN,
        "PDFDocEncoding" => tables::ENC_PDFDOC,
        _ => tables::ENC_STD,
    };
    t.iter().map(|(c, s)| (*c as u32, s.to_string())).collect()
}

fn japan1() -> &'static HashMap<u32, String> {
    static MAP: OnceLock<HashMap<u32, String>> = OnceLock::new();
    MAP.get_or_init(|| {
        let blob: &[u8] = include_bytes!("japan1.bin");
        let mut m = HashMap::new();
        let mut i = 0;
        while i + 3 <= blob.len() {
            let cid = u16::from_le_bytes([blob[i], blob[i + 1]]) as u32;
            let n = blob[i + 2] as usize;
            let end = (i + 3 + n).min(blob.len());
            m.insert(cid, String::from_utf8_lossy(&blob[i + 3..end]).into_owned());
            i = end;
        }
        m
    })
}

#[derive(Debug)]
enum Decoder {
    OneByte,
    Identity2,
    Empty,
}

#[derive(Debug)]
enum UMap {
    None,
    File(HashMap<u32, String>),
    Identity,
    Japan1,
}

#[derive(Debug)]
pub struct Font {
    pub fontname: String,
    pub descent: f64,
    pub vscale: f64,
    pub hscale: f64,
    pub multibyte: bool,
    pub vertical: bool,
    decoder: Decoder,
    widths: HashMap<i64, Option<f64>>,
    str_widths: HashMap<String, f64>,
    default_width: f64,
    umap: UMap,
    cid2unicode: Option<HashMap<u32, String>>,
    disps: HashMap<u32, (Option<f64>, f64)>,
    default_disp: (Option<f64>, f64),
}

impl Font {
    fn blank() -> Font {
        Font {
            fontname: "unknown".into(),
            descent: 0.0,
            vscale: 0.001,
            hscale: 0.001,
            multibyte: false,
            vertical: false,
            decoder: Decoder::OneByte,
            widths: HashMap::new(),
            str_widths: HashMap::new(),
            default_width: 0.0,
            umap: UMap::None,
            cid2unicode: None,
            disps: HashMap::new(),
            default_disp: (None, 0.0),
        }
    }

    pub fn get_descent(&self) -> f64 {
        self.descent * self.vscale
    }

    pub fn decode(&self, b: &[u8], out: &mut Vec<u32>) {
        out.clear();
        match self.decoder {
            Decoder::OneByte => out.extend(b.iter().map(|c| *c as u32)),
            Decoder::Identity2 => {
                out.extend(b.chunks_exact(2).map(|p| (p[0] as u32) << 8 | p[1] as u32))
            }
            Decoder::Empty => {}
        }
    }

    pub fn to_unichr(&self, cid: u32) -> Option<String> {
        match &self.umap {
            UMap::File(m) => {
                if let Some(s) = m.get(&cid) {
                    return Some(s.clone());
                }
            }
            UMap::Identity => {
                if self.cid2unicode.is_none() {
                    return char::from_u32(cid).map(|c| c.to_string());
                }
            }
            UMap::Japan1 => {
                if let Some(s) = japan1().get(&cid) {
                    return Some(s.clone());
                }
            }
            UMap::None => {}
        }
        self.cid2unicode.as_ref().and_then(|m| m.get(&cid).cloned())
    }

    pub fn char_width(&self, cid: u32) -> f64 {
        if let Some(Some(w)) = self.widths.get(&(cid as i64)) {
            return w * self.hscale;
        }
        if !self.str_widths.is_empty() {
            if let Some(s) = self.to_unichr(cid) {
                if let Some(w) = self.str_widths.get(&s) {
                    return w * self.hscale;
                }
            }
        }
        self.default_width * self.hscale
    }

    pub fn char_disp(&self, cid: u32) -> (Option<f64>, f64) {
        *self.disps.get(&cid).unwrap_or(&self.default_disp)
    }
}

/// ToUnicode CMap (pdfminer `CMapParser` into a `FileUnicodeMap`).
fn parse_tounicode(data: &[u8]) -> HashMap<u32, String> {
    let mut m: HashMap<u32, String> = HashMap::new();
    let mut in_cmap = true;
    let add = |m: &mut HashMap<u32, String>, cid: u32, code: &Obj| {
        let s = match code {
            Obj::Name(n) => match name2unicode(n) {
                Some(s) => s,
                None => return,
            },
            Obj::Str(b) => utf16be(b),
            Obj::Int(i) => match char::from_u32(*i as u32) {
                Some(c) => c.to_string(),
                None => return,
            },
            _ => return,
        };
        if s == "\u{a0}" && m.get(&cid).map(|x| x.as_str()) == Some(" ") {
            return;
        }
        m.insert(cid, s);
    };
    ps_run(data, |k, cur| {
        match k {
            "begincmap" => {
                in_cmap = true;
                cur.clear();
                return;
            }
            "endcmap" => {
                in_cmap = false;
                return;
            }
            _ => {}
        }
        if !in_cmap {
            return;
        }
        match k {
            "def" => {
                let n = cur.len().saturating_sub(2);
                cur.truncate(n);
            }
            "usecmap" => {
                cur.pop();
            }
            "begincodespacerange"
            | "endcodespacerange"
            | "begincidrange"
            | "begincidchar"
            | "beginbfrange"
            | "beginbfchar"
            | "beginnotdefrange"
            | "endnotdefrange" => cur.clear(),
            "endcidrange" => {
                let objs = std::mem::take(cur);
                for c in objs.chunks_exact(3) {
                    if let (Obj::Str(s), Obj::Str(e), Obj::Int(cid)) = (&c[0], &c[1], &c[2]) {
                        if s.len() != e.len() {
                            continue;
                        }
                        let sp = &s[..s.len().saturating_sub(4)];
                        let ep = &e[..e.len().saturating_sub(4)];
                        if sp != ep {
                            continue;
                        }
                        let sv = &s[sp.len()..];
                        let start = nunpack(sv);
                        let end = nunpack(&e[ep.len()..]);
                        let vlen = sv.len();
                        for i in 0..(end.saturating_sub(start) + 1).min(65536) {
                            if end < start {
                                break;
                            }
                            let mut x = sp.to_vec();
                            let be = ((start + i) as u32).to_be_bytes();
                            x.extend_from_slice(&be[4 - vlen.min(4)..]);
                            add(&mut m, (*cid as u64 + i) as u32, &Obj::Str(Rc::new(x)));
                        }
                    }
                }
            }
            "endcidchar" => {
                let objs = std::mem::take(cur);
                for c in objs.chunks_exact(2) {
                    if let (Obj::Int(cid), code @ Obj::Str(_)) = (&c[0], &c[1]) {
                        add(&mut m, *cid as u32, code);
                    }
                }
            }
            "endbfrange" => {
                let objs = std::mem::take(cur);
                for c in objs.chunks_exact(3) {
                    let (Obj::Str(s), Obj::Str(e)) = (&c[0], &c[1]) else {
                        continue;
                    };
                    if s.len() != e.len() {
                        continue;
                    }
                    let start = nunpack(s);
                    let end = nunpack(e);
                    match &c[2] {
                        Obj::Array(a) => {
                            for (n, v) in a.iter().enumerate() {
                                let cid = start + n as u64;
                                if cid > end {
                                    break;
                                }
                                add(&mut m, cid as u32, v);
                            }
                        }
                        Obj::Str(code) => {
                            let var = &code[code.len().saturating_sub(4)..];
                            let base = nunpack(var);
                            let prefix = &code[..code.len() - var.len()];
                            let vlen = var.len();
                            if end >= start {
                                for i in 0..(end - start + 1).min(65536) {
                                    let mut x = prefix.to_vec();
                                    let be = ((base + i) as u32).to_be_bytes();
                                    x.extend_from_slice(&be[4 - vlen.min(4)..]);
                                    add(&mut m, (start + i) as u32, &Obj::Str(Rc::new(x)));
                                }
                            }
                        }
                        _ => {}
                    }
                }
            }
            "endbfchar" => {
                let objs = std::mem::take(cur);
                for c in objs.chunks_exact(2) {
                    if let (Obj::Str(cid), code @ Obj::Str(_)) = (&c[0], &c[1]) {
                        add(&mut m, nunpack(cid) as u32, code);
                    }
                }
            }
            _ => cur.push(Obj::Keyword(Rc::from(k))),
        }
    });
    m
}

fn nunpack(b: &[u8]) -> u64 {
    b.iter()
        .fold(0u64, |a, c| a.wrapping_mul(256).wrapping_add(*c as u64))
}

/// Python `bytes.decode("UTF-16BE", "ignore")`.
pub fn utf16be(b: &[u8]) -> String {
    let units: Vec<u16> = b
        .chunks_exact(2)
        .map(|p| (p[0] as u16) << 8 | p[1] as u16)
        .collect();
    char::decode_utf16(units).filter_map(|r| r.ok()).collect()
}

/// Built-in encoding of an embedded Type 1 program (`Type1FontHeaderParser`).
fn type1_encoding(data: &[u8]) -> HashMap<u32, String> {
    let mut m = HashMap::new();
    ps_run(data, |k, cur| {
        if k == "put" && cur.len() >= 2 {
            let v = cur.pop();
            let key = cur.pop();
            if let (Some(Obj::Int(key)), Some(Obj::Name(v))) = (key, v) {
                if let Some(u) = name2unicode(&v) {
                    m.insert(key as u32, u);
                }
            }
        } else if k == "put" {
            cur.clear();
        }
    });
    m
}

fn num_or(doc: &Doc, d: &Dict, k: &str, default: f64) -> f64 {
    doc.rnum(d.get(k)).unwrap_or(default)
}

fn simple_encoding(doc: &Doc, spec: &Dict, default: &str) -> HashMap<u32, String> {
    match spec.get("Encoding").map(|e| doc.resolve(e)) {
        Some(Obj::Dict(d)) => {
            let base = d
                .get("BaseEncoding")
                .and_then(|x| x.name())
                .unwrap_or(default)
                .to_string();
            let mut map = base_encoding(&base);
            if let Some(diff) = doc.rarray(d.get("Differences")) {
                let mut cid: i64 = 0;
                for x in diff.iter() {
                    match x {
                        Obj::Int(i) => cid = *i,
                        Obj::Name(n) => {
                            if let Some(u) = name2unicode(n) {
                                map.insert(cid as u32, u);
                            }
                            cid += 1;
                        }
                        _ => {}
                    }
                }
            }
            map
        }
        Some(Obj::Name(n)) => base_encoding(&n),
        _ => base_encoding(default),
    }
}

fn tounicode_stream(doc: &Doc, spec: &Dict) -> Option<HashMap<u32, String>> {
    match spec.get("ToUnicode").map(|o| doc.resolve(o)) {
        Some(Obj::Stream(s)) => Some(parse_tounicode(&decode_stream(&s))),
        _ => None,
    }
}

fn apply_descriptor(doc: &Doc, f: &mut Font, desc: &Dict, missing: bool) {
    let name = desc.get("FontName").map(|o| doc.resolve(o));
    f.fontname = match name {
        Some(Obj::Name(n)) => n.to_string(),
        Some(Obj::Str(s)) => format!("b'{}'", String::from_utf8_lossy(&s)),
        Some(Obj::Int(i)) => i.to_string(),
        _ => "unknown".into(),
    };
    f.descent = num_or(doc, desc, "Descent", 0.0);
    if missing {
        f.default_width = num_or(doc, desc, "MissingWidth", 0.0);
    }
    if f.descent > 0.0 {
        f.descent = -f.descent;
    }
}

pub fn load_font(doc: &Doc, spec: &Dict) -> Font {
    let subtype = spec
        .get("Subtype")
        .and_then(|x| x.name())
        .unwrap_or("Type1")
        .to_string();
    match subtype.as_str() {
        "Type0" => {
            let dfonts = doc.rarray(spec.get("DescendantFonts"));
            let sub = dfonts
                .as_ref()
                .and_then(|a| a.first())
                .and_then(|x| doc.rdict(Some(x)));
            match sub {
                Some(d) => {
                    let mut sub = Dict(d.0.clone());
                    for k in ["Encoding", "ToUnicode"] {
                        if let Some(v) = spec.get(k) {
                            sub.0.push((Rc::from(k), doc.resolve(v)));
                        }
                    }
                    let st = sub
                        .get("Subtype")
                        .and_then(|x| x.name())
                        .unwrap_or("Type1")
                        .to_string();
                    if st == "CIDFontType0" || st == "CIDFontType2" {
                        cid_font(doc, &sub)
                    } else {
                        type1_font(doc, &sub, &st)
                    }
                }
                None => Font::blank(),
            }
        }
        "CIDFontType0" | "CIDFontType2" => cid_font(doc, spec),
        "Type3" => type3_font(doc, spec),
        other => type1_font(doc, spec, other),
    }
}

fn widths_from_list(doc: &Doc, spec: &Dict) -> HashMap<i64, Option<f64>> {
    let first = doc
        .resolve(spec.get("FirstChar").unwrap_or(&Obj::Int(0)))
        .int()
        .unwrap_or(0);
    let mut w = HashMap::new();
    match doc.rarray(spec.get("Widths")) {
        Some(list) => {
            for (i, x) in list.iter().enumerate() {
                w.insert(i as i64 + first, doc.resolve(x).num());
            }
        }
        None => {
            for i in 0..256 {
                w.insert(i + first, Some(0.0));
            }
        }
    }
    w
}

fn type1_font(doc: &Doc, spec: &Dict, subtype: &str) -> Font {
    let mut f = Font::blank();
    let basefont = spec
        .get("BaseFont")
        .and_then(|x| x.name())
        .unwrap_or("unknown")
        .to_string();
    let base14 = tables::BASE14.iter().find(|b| b.0 == basefont);
    let mut descriptor: Option<Rc<Dict>> = None;
    match base14 {
        Some((_, fontname, descent, _asc, widths)) => {
            f.fontname = fontname.to_string();
            f.descent = if *descent > 0.0 { -descent } else { *descent };
            f.str_widths = widths.iter().map(|(k, v)| (k.to_string(), *v)).collect();
        }
        None => {
            let d = doc.rdict(spec.get("FontDescriptor")).unwrap_or_default();
            apply_descriptor(doc, &mut f, &d, true);
            f.widths = widths_from_list(doc, spec);
            descriptor = Some(d);
        }
    }
    let default = if subtype == "TrueType" {
        "WinAnsiEncoding"
    } else {
        "StandardEncoding"
    };
    f.cid2unicode = Some(simple_encoding(doc, spec, default));
    if let Some(m) = tounicode_stream(doc, spec) {
        f.umap = UMap::File(m);
    }
    if !spec.has("Encoding") {
        if let Some(d) = descriptor {
            if let Some(Obj::Stream(ff)) = d.get("FontFile").map(|o| doc.resolve(o)) {
                let len1 = doc.rnum(ff.dict.get("Length1")).unwrap_or(0.0).max(0.0) as usize;
                let data = decode_stream(&ff);
                f.cid2unicode = Some(type1_encoding(&data[..len1.min(data.len())]));
            }
        }
    }
    f
}

fn type3_font(doc: &Doc, spec: &Dict) -> Font {
    let mut f = Font::blank();
    f.widths = widths_from_list(doc, spec);
    let desc = doc.rdict(spec.get("FontDescriptor"));
    if let Some(d) = &desc {
        apply_descriptor(doc, &mut f, d, true);
    }
    f.cid2unicode = Some(simple_encoding(doc, spec, "StandardEncoding"));
    if let Some(m) = tounicode_stream(doc, spec) {
        f.umap = UMap::File(m);
    }
    let bbox_src = match &desc {
        Some(d) => d.get("FontBBox").cloned(),
        None => spec.get("FontBBox").cloned(),
    };
    let bbox: Vec<f64> = doc
        .rarray(bbox_src.as_ref())
        .map(|a| a.iter().filter_map(|x| doc.resolve(x).num()).collect())
        .unwrap_or_default();
    f.descent = if bbox.len() == 4 { bbox[1] } else { 0.0 };
    let m: Vec<f64> = doc
        .rarray(spec.get("FontMatrix"))
        .map(|a| a.iter().filter_map(|x| doc.resolve(x).num()).collect())
        .unwrap_or_default();
    if m.len() >= 4 {
        f.hscale = m[0] + m[2];
        f.vscale = m[1] + m[3];
    }
    f
}

fn cid_widths(doc: &Doc, seq: &[Obj]) -> HashMap<i64, Option<f64>> {
    let mut w = HashMap::new();
    let mut r: Vec<Obj> = Vec::new();
    for v in seq {
        let v = doc.resolve(v);
        match &v {
            Obj::Array(list) => {
                if let Some(c1) = r.last().and_then(|x| x.num()) {
                    for (i, x) in list.iter().enumerate() {
                        w.insert(c1 as i64 + i as i64, x.num());
                    }
                }
                r.clear();
            }
            Obj::Int(_) | Obj::Real(_) => {
                r.push(v.clone());
                if r.len() == 3 {
                    if let (Obj::Int(a), Obj::Int(b)) = (&r[0], &r[1]) {
                        for i in *a..=(*b).min(*a + 1_000_000) {
                            w.insert(i, r[2].num());
                        }
                    }
                    r.clear();
                }
            }
            _ => {}
        }
    }
    w
}

fn cid_font(doc: &Doc, spec: &Dict) -> Font {
    let mut f = Font::blank();
    f.multibyte = true;
    let info = doc.rdict(spec.get("CIDSystemInfo")).unwrap_or_default();
    let field = |k: &str| match info.get(k).map(|o| doc.resolve(o)) {
        Some(Obj::Str(s)) => s.iter().map(|c| *c as char).collect::<String>(),
        _ => "unknown".into(),
    };
    let ordering = field("Ordering");
    let cidcoding = format!("{}-{}", field("Registry").trim(), ordering.trim());
    let cmap_name = match spec.get("Encoding") {
        Some(Obj::Name(n)) => n.to_string(),
        Some(o) => match doc
            .resolve(o)
            .as_dict()
            .and_then(|d| d.get("CMapName").cloned())
        {
            Some(Obj::Name(n)) => n.to_string(),
            _ => "unknown".into(),
        },
        None => "unknown".into(),
    };
    let cmap_name = match cmap_name.as_str() {
        "DLIdent-H" => "Identity-H".to_string(),
        "DLIdent-V" => "Identity-V".to_string(),
        _ => cmap_name,
    };
    let (decoder, vertical) = match cmap_name.as_str() {
        "Identity-H" => (Decoder::Identity2, false),
        "Identity-V" => (Decoder::Identity2, true),
        "OneByteIdentityH" => (Decoder::OneByte, false),
        "OneByteIdentityV" => (Decoder::OneByte, true),
        _ => (Decoder::Empty, false), // predefined CMaps other than Identity are not ported
    };
    f.decoder = decoder;
    f.vertical = vertical;
    let desc = doc.rdict(spec.get("FontDescriptor")).unwrap_or_default();
    match spec.get("ToUnicode") {
        Some(Obj::Stream(s)) => f.umap = UMap::File(parse_tounicode(&decode_stream(s))),
        Some(Obj::Name(n)) => {
            let enc = spec.get("Encoding").and_then(|x| x.name()).unwrap_or("");
            if ordering.contains("Identity") || n.contains("Identity") || enc.contains("Identity") {
                f.umap = UMap::Identity;
            }
        }
        Some(_) => {}
        None => {
            if cidcoding == "Adobe-Japan1" && !vertical {
                f.umap = UMap::Japan1;
            }
            // Adobe-Identity TrueType cmap tables and the GB1/CNS1/Korea1 maps are not ported.
        }
    }
    if vertical {
        let w2 = doc
            .rarray(spec.get("W2"))
            .map(|a| a.to_vec())
            .unwrap_or_default();
        let mut r: Vec<f64> = Vec::new();
        for v in &w2 {
            match v {
                Obj::Array(list) => {
                    if let Some(c1) = r.last() {
                        let c1 = *c1 as i64;
                        for (i, t) in list.chunks_exact(3).enumerate() {
                            let cid = c1 + i as i64;
                            f.widths.insert(cid, t[0].num());
                            f.disps
                                .insert(cid as u32, (t[1].num(), t[2].num().unwrap_or(0.0)));
                        }
                    }
                    r.clear();
                }
                o => {
                    if let Some(x) = o.num() {
                        r.push(x);
                        if r.len() == 5 {
                            for c in (r[0] as i64)..=(r[1] as i64) {
                                f.widths.insert(c, Some(r[2]));
                                f.disps.insert(c as u32, (Some(r[3]), r[4]));
                            }
                            r.clear();
                        }
                    }
                }
            }
        }
        let dw2: Vec<f64> = doc
            .rarray(spec.get("DW2"))
            .map(|a| a.iter().filter_map(|x| x.num()).collect())
            .unwrap_or_else(|| vec![880.0, -1000.0]);
        f.default_disp = (None, *dw2.first().unwrap_or(&880.0));
        apply_descriptor(doc, &mut f, &desc, false);
        f.default_width = *dw2.get(1).unwrap_or(&-1000.0);
    } else {
        let w = doc
            .rarray(spec.get("W"))
            .map(|a| a.to_vec())
            .unwrap_or_default();
        f.widths = cid_widths(doc, &w);
        apply_descriptor(doc, &mut f, &desc, false);
        f.default_width = doc.rnum(spec.get("DW")).unwrap_or(1000.0);
    }
    f
}
