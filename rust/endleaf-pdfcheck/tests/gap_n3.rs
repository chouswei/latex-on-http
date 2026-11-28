//! N3 route checks (red-first, ENDLEAF-R82). One test per fixture; see scripts/make_gap_fixtures.py.
mod common;

#[test]
fn n3_gb1_ucs2() {
    common::assert_case("n3_gb1_ucs2");
}

#[test]
fn n3_cns1_ucs2() {
    common::assert_case("n3_cns1_ucs2");
}

#[test]
fn n3_korea1_ucs2() {
    common::assert_case("n3_korea1_ucs2");
}

#[test]
fn n3_japan1_ucs2() {
    common::assert_case("n3_japan1_ucs2");
}

#[test]
fn n3_japan1_vertical() {
    common::assert_case("n3_japan1_vertical");
}

#[test]
fn n3_gb1_gbk_euc() {
    common::assert_case("n3_gb1_gbk_euc");
}

#[test]
fn n3_japan1_rksj() {
    common::assert_case("n3_japan1_rksj");
}

#[test]
fn n3_truetype_identity() {
    common::assert_case("n3_truetype_identity");
}
