//! N5 route checks (red-first, ENDLEAF-R82). One test per fixture; see scripts/make_gap_fixtures.py.
//! `n5_gap_*` cases are where the reference and the 019be7a7 binary disagree (red); `n5_reg_*` agree
//! already and stay as regression checks.
mod common;

#[test]
fn n5_reg_node_bowtie() {
    common::assert_case("n5_reg_node_bowtie");
}

#[test]
fn n5_reg_node_touch8() {
    common::assert_case("n5_reg_node_touch8");
}

#[test]
fn n5_reg_node_pentagram() {
    common::assert_case("n5_reg_node_pentagram");
}

#[test]
fn n5_reg_node_zero_area() {
    common::assert_case("n5_reg_node_zero_area");
}

#[test]
fn n5_reg_node_collinear_diag() {
    common::assert_case("n5_reg_node_collinear_diag");
}

#[test]
fn n5_reg_node_dup_vertices() {
    common::assert_case("n5_reg_node_dup_vertices");
}

#[test]
fn n5_reg_node_spike() {
    common::assert_case("n5_reg_node_spike");
}

#[test]
fn n5_reg_white_edge_100p0() {
    common::assert_case("n5_reg_white_edge_100p0");
}

#[test]
fn n5_reg_white_edge_105p0() {
    common::assert_case("n5_reg_white_edge_105p0");
}

#[test]
fn n5_reg_white_edge_110p0() {
    common::assert_case("n5_reg_white_edge_110p0");
}

#[test]
fn n5_reg_white_edge_118p5() {
    common::assert_case("n5_reg_white_edge_118p5");
}

#[test]
fn n5_reg_white_edge_122p5() {
    common::assert_case("n5_reg_white_edge_122p5");
}

#[test]
fn n5_reg_white_edge_127p0() {
    common::assert_case("n5_reg_white_edge_127p0");
}

#[test]
fn n5_reg_white_edge_130p0() {
    common::assert_case("n5_reg_white_edge_130p0");
}

#[test]
fn n5_reg_white_edge_135p0() {
    common::assert_case("n5_reg_white_edge_135p0");
}

#[test]
fn n5_reg_white_edge_140p0() {
    common::assert_case("n5_reg_white_edge_140p0");
}

#[test]
fn n5_reg_white_edge_150p0() {
    common::assert_case("n5_reg_white_edge_150p0");
}

#[test]
fn n5_reg_white_edge_160p0() {
    common::assert_case("n5_reg_white_edge_160p0");
}

#[test]
fn n5_reg_white_narrow_100() {
    common::assert_case("n5_reg_white_narrow_100");
}

#[test]
fn n5_reg_white_narrow_110() {
    common::assert_case("n5_reg_white_narrow_110");
}

#[test]
fn n5_reg_white_narrow_120() {
    common::assert_case("n5_reg_white_narrow_120");
}

#[test]
fn n5_reg_white_narrow_130() {
    common::assert_case("n5_reg_white_narrow_130");
}

#[test]
fn n5_reg_white_narrow_140() {
    common::assert_case("n5_reg_white_narrow_140");
}

#[test]
fn n5_reg_white_bowtie() {
    common::assert_case("n5_reg_white_bowtie");
}

#[test]
fn n5_reg_stroke_diagonal() {
    common::assert_case("n5_reg_stroke_diagonal");
}

#[test]
fn n5_reg_stroke_cross() {
    common::assert_case("n5_reg_stroke_cross");
}

#[test]
fn n5_reg_stroke_zigzag() {
    common::assert_case("n5_reg_stroke_zigzag");
}

#[test]
fn n5_reg_knn_grid8() {
    common::assert_case("n5_reg_knn_grid8");
}

#[test]
fn n5_reg_knn_rows() {
    common::assert_case("n5_reg_knn_rows");
}

#[test]
fn n5_reg_knn_ring() {
    common::assert_case("n5_reg_knn_ring");
}

#[test]
fn n5_reg_knn_duplicates() {
    common::assert_case("n5_reg_knn_duplicates");
}

#[test]
fn n5_gap_node_invalid_a() {
    common::assert_case("n5_gap_node_invalid_a");
}

#[test]
fn n5_gap_node_invalid_b() {
    common::assert_case("n5_gap_node_invalid_b");
}

#[test]
fn n5_gap_node_invalid_c() {
    common::assert_case("n5_gap_node_invalid_c");
}

#[test]
fn n5_gap_node_invalid_d() {
    common::assert_case("n5_gap_node_invalid_d");
}

#[test]
fn n5_gap_node_invalid_e() {
    common::assert_case("n5_gap_node_invalid_e");
}

#[test]
fn n5_gap_node_invalid_f() {
    common::assert_case("n5_gap_node_invalid_f");
}

#[test]
fn n5_gap_white_invalid_a() {
    common::assert_case("n5_gap_white_invalid_a");
}

#[test]
fn n5_gap_white_invalid_b() {
    common::assert_case("n5_gap_white_invalid_b");
}

#[test]
fn n5_gap_white_invalid_c() {
    common::assert_case("n5_gap_white_invalid_c");
}
