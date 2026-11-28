//! N2 route checks (red-first, ENDLEAF-R82). One test per fixture; see scripts/make_gap_fixtures.py.
mod common;

#[test]
fn n2_sidecar_part() {
    common::assert_case("n2_sidecar_part");
}

#[test]
fn n2_sidecar_fence() {
    common::assert_case("n2_sidecar_fence");
}

#[test]
fn n2_sidecar_plain() {
    common::assert_case("n2_sidecar_plain");
}

#[test]
fn n2_sidecar_texpages() {
    common::assert_case("n2_sidecar_texpages");
}

#[test]
fn n2_encrypted_skip() {
    common::assert_case("n2_encrypted_skip");
}

#[test]
fn n2_version_exits_zero_and_names_the_crate() {
    let out = common::bin().arg("--version").output().expect("run");
    assert!(out.status.success(), "--version exit {:?}", out.status.code());
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(text.starts_with("endleaf-pdfcheck "), "version line: {text:?}");
    assert_eq!(text.trim_end().lines().count(), 1);
}

#[test]
fn n2_sidecar_flag_is_documented_in_usage() {
    let out = common::bin().arg("--help").output().expect("run");
    assert!(String::from_utf8_lossy(&out.stdout).contains("--sidecar"));
}
