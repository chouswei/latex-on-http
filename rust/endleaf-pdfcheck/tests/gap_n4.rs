//! N4 route checks (red-first, ENDLEAF-R82). One test per fixture; see scripts/make_gap_fixtures.py.
mod common;

#[test]
fn n4_lzw_early1() {
    common::assert_case("n4_lzw_early1");
}

#[test]
fn n4_lzw_early0() {
    common::assert_case("n4_lzw_early0");
}

#[test]
fn n4_lzw_png() {
    common::assert_case("n4_lzw_png");
}

#[test]
fn n4_lzw_tiff() {
    common::assert_case("n4_lzw_tiff");
}

#[test]
fn n4_lzw_flate() {
    common::assert_case("n4_lzw_flate");
}

#[test]
fn n4_runlength() {
    common::assert_case("n4_runlength");
}

#[test]
fn n4_encrypted() {
    common::assert_case("n4_encrypted");
}

#[test]
fn n4_reg_flate_twin() {
    common::assert_case("n4_reg_flate_twin");
}
