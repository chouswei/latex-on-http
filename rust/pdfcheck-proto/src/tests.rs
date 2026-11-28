//! Unit tests for the ported pieces (geometry, grouping, text, budget note).

use crate::check::{link, otsu, round1, skip_message, start, Budget, LinkIn, Skip};
use crate::font::{name2unicode, utf16be};
use crate::geom::{self, components, KdTree};
use crate::pdf::{ContentParser, Lexer, Obj, Tok};
use unicode_normalization::UnicodeNormalization;

#[test]
fn components_are_labelled_by_smallest_member() {
    let (count, labels) = components(5, vec![(4, 3), (1, 0)].into_iter());
    assert_eq!(count, 3);
    assert_eq!(labels, vec![0, 0, 1, 2, 2]);
}

#[test]
fn link_joins_glyphs_on_one_baseline_and_splits_at_the_gap() {
    // five glyphs 10 pt wide, size 10: gaps 0, 0, 5 (0.5 em), 0
    let xs = [0.0, 10.0, 20.0, 35.0, 45.0];
    let center: Vec<[f64; 2]> = xs.iter().map(|x| [x + 5.0, 5.0]).collect();
    let origin: Vec<[f64; 2]> = xs.iter().map(|x| [*x, 8.0]).collect();
    let u = vec![[1.0, 0.0]; 5];
    let v = vec![[0.0, -1.0]; 5];
    let size = vec![10.0; 5];
    let extent = vec![10.0; 5];
    let x = LinkIn {
        center: &center,
        u: &u,
        v: &v,
        size: &size,
        extent: &extent,
        origin: &origin,
    };
    let (labels, edges) = link(&x, 12, 0.10, 0.1, -0.35, Some(0.1));
    assert_eq!(labels, vec![0, 0, 0, 1, 1]);
    assert!(edges.is_some());
    // a glyph off the baseline does not join
    let mut origin2 = origin.clone();
    origin2[1][1] = 12.0;
    let x2 = LinkIn { origin: &origin2, ..x };
    let (labels, _) = link(&x2, 12, 0.10, 0.1, -0.35, Some(0.1));
    assert_eq!(labels, vec![0, 1, 2, 3, 3]);
}

#[test]
fn kdtree_knn_matches_brute_force() {
    let pts: Vec<[f64; 2]> = (0..200).map(|i| [((i * 37) % 101) as f64, ((i * 53) % 97) as f64]).collect();
    let tree = KdTree::new(&pts);
    let mut out = Vec::new();
    for q in pts.iter().step_by(7) {
        tree.knn(*q, 9, &mut out);
        let mut brute: Vec<(f64, usize)> = pts
            .iter()
            .enumerate()
            .map(|(i, p)| ((p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2), i))
            .collect();
        brute.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
        assert_eq!(out, brute[..9].to_vec());
    }
}

#[test]
fn liang_barsky_clips_to_the_box() {
    let b = [0.0, 0.0, 10.0, 10.0];
    assert_eq!(geom::liang_barsky([-5.0, 5.0], [15.0, 5.0], b), Some((0.25, 0.75)));
    assert_eq!(geom::liang_barsky([-5.0, 20.0], [15.0, 20.0], b), None);
    // touching the edge counts (shapely intersects)
    assert_eq!(geom::liang_barsky([10.0, -5.0], [10.0, 15.0], b), Some((0.25, 0.75)));
    let quad = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]];
    let cb = geom::clip_segment_convex([-5.0, 5.0], [15.0, 5.0], &quad).unwrap();
    assert!((cb.0 - 0.25).abs() < 1e-12 && (cb.1 - 0.75).abs() < 1e-12);
}

#[test]
fn point_in_polygon_inside_boundary_outside() {
    let ring = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [2.0, 1.0], [0.0, 4.0], [0.0, 0.0]];
    assert_eq!(geom::point_in_polygon([1.0, 0.5], &ring), 1);
    assert_eq!(geom::point_in_polygon([2.0, 0.0], &ring), 0);
    assert_eq!(geom::point_in_polygon([2.0, 3.0], &ring), -1);
}

#[test]
fn convex_clip_area_and_difference_bounds() {
    let a = [[0.0, 0.0], [4.0, 0.0], [4.0, 2.0], [0.0, 2.0]];
    let b = [[3.0, -1.0], [6.0, -1.0], [6.0, 3.0], [3.0, 3.0]];
    let inter = geom::clip_convex(&b, &a);
    assert!((geom::area(&inter) - 2.0).abs() < 1e-12);
    let d = geom::difference_bounds(&a, &b).unwrap();
    assert_eq!(d, [0.0, 0.0, 3.0, 2.0]);
}

#[test]
fn nfkc_matches_python_unicodedata() {
    let s: String = "ﬁ½①Ａ".nfkc().collect();
    assert_eq!(s, "fi1⁄21A");
}

#[test]
fn glyph_names_and_utf16() {
    assert_eq!(name2unicode("fi").as_deref(), Some("ﬁ"));
    assert_eq!(name2unicode("uni0041").as_deref(), Some("A"));
    assert_eq!(name2unicode("u1F600").as_deref(), Some("😀"));
    assert_eq!(name2unicode("f_i.sc").as_deref(), Some("fi"));
    assert_eq!(name2unicode("nonsense-name"), None);
    assert_eq!(utf16be(&[0xd8, 0x3d, 0xde, 0x00]), "😀");
}

#[test]
fn lexer_follows_pdfminer_rules() {
    let mut lx = Lexer::new(b"-.5 5. 1.5e3 (a\\101\\q) <414> /A#42 T* - ");
    let mut toks = Vec::new();
    while let Some(t) = lx.next() {
        toks.push(format!("{t:?}"));
    }
    assert_eq!(
        toks,
        vec![
            "Real(-0.5)",
            "Real(5.0)",
            "Real(1.5)",
            "Kw(\"e3\")",
            "Str([97, 65])",
            "Str([65, 4])",
            "Name(\"AB\")",
            "Kw(\"T*\")",
        ]
    );
    let mut cp = ContentParser::new(b"[(a) 10 (b)] TJ");
    assert!(matches!(cp.next(), Some(Obj::Array(a)) if a.len() == 3));
    assert!(matches!(cp.next(), Some(Obj::Keyword(k)) if &*k == "TJ"));
    let _ = Tok::ArrBegin;
}

#[test]
fn otsu_splits_two_clusters() {
    let mut v = vec![0.05; 40];
    v.extend(vec![0.4; 40]);
    let t = otsu(&v, 50, 0.5).unwrap();
    assert!(t > 0.05 && t <= 0.4, "{t}");
}

#[test]
fn rounding_and_start_match_python() {
    assert_eq!(round1(0.25), 0.2);
    assert_eq!(round1(616.96), 617.0);
    assert_eq!(start("  a  b\tc ", 30), "a b c");
    assert_eq!(start("https://cstheory.stackexchange.com/q", 30), "https://cstheory.stackexchang…");
}

#[test]
fn budget_skip_message_matches_python() {
    assert_eq!(
        skip_message("time budget", 1),
        "pdf layout check stopped (time budget) after pg1; findings so far are kept"
    );
    assert_eq!(
        skip_message("error PDFSyntaxError", 0),
        "pdf layout check stopped (error PDFSyntaxError) before pg1"
    );
    let b = Budget::new(-1.0, 10.0);
    assert!(matches!(b.check(), Err(Skip::Budget)));
    let b = Budget::new(10.0, 10.0);
    assert!(b.check().is_ok());
}
