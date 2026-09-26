# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration checks that need a working rootless Podman and the baked image.

Run with the marker selected and the default deselection cleared::

    uv run pytest -m podman -o addopts=

The image is not pulled. Set COLOPHON_IMAGE to a locally built tag.
"""

import os
import shutil

import pytest

pytestmark = pytest.mark.podman


@pytest.fixture
def podman_bin():
    binary = shutil.which(os.environ.get("COLOPHON_PODMAN", "podman"))
    if binary is None:
        pytest.skip("podman is not installed")
    return binary


def test_podman_is_rootless_and_not_docker(podman_bin):
    import subprocess

    if os.path.basename(podman_bin) == "docker":
        pytest.fail("COLOPHON_PODMAN points at docker")
    info = subprocess.run(
        [podman_bin, "info", "--format", "{{.Host.Security.Rootless}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if info.returncode != 0:
        pytest.skip(f"podman info failed: {info.stderr.strip()}")
    assert info.stdout.strip() == "true"


def test_image_runs_with_network_none(podman_bin):
    """Smoke-test the baked image when COLOPHON_IMAGE is already present."""
    import json
    import subprocess

    image = os.environ.get("COLOPHON_IMAGE", "")
    if not image:
        pytest.skip("COLOPHON_IMAGE is unset; image was not built in this environment")
    exists = subprocess.run(
        [podman_bin, "image", "exists", image],
        check=False,
    )
    if exists.returncode != 0:
        pytest.skip(f"image {image} is not present locally")
    from colophon.podman_args import build_podman_run_args

    args = build_podman_run_args(
        podman=podman_bin, image=image, name="colophon-job-itest"
    )
    payload = json.dumps(
        {
            "body": "Hello",
            "templateId": "document-shell",
            "outputFormat": "html",
            "lane": "Weft",
        }
    ).encode("utf-8")
    completed = subprocess.run(
        args,
        input=payload,
        capture_output=True,
        check=False,
        timeout=70,
    )
    assert b"COLOPHON_STATUS" in completed.stderr or completed.returncode == 0
