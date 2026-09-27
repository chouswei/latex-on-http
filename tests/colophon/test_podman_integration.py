# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration checks that need a working rootless Podman and the baked image.

Run with the marker selected and the default deselection cleared::

    uv run pytest -m podman -o addopts=

The image is not pulled. Set ENDLEAF_IMAGE to a locally built tag.
COLOPHON_IMAGE and COLOPHON_PODMAN are still read.
"""

import os
import shutil

import pytest

from colophon.settings import setting

pytestmark = pytest.mark.podman


@pytest.fixture
def podman_bin():
    binary_name, name = setting(os.environ, "PODMAN", default="podman")
    binary = shutil.which(binary_name)
    if binary is None:
        pytest.skip("podman is not installed")
    return binary, name


def test_podman_is_rootless_and_not_docker(podman_bin):
    import subprocess

    binary, name = podman_bin
    if os.path.basename(binary) == "docker":
        pytest.fail(f"{name} points at docker")
    info = subprocess.run(
        [binary, "info", "--format", "{{.Host.Security.Rootless}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if info.returncode != 0:
        pytest.skip(f"podman info failed: {info.stderr.strip()}")
    assert info.stdout.strip() == "true"


def test_image_runs_with_network_none(podman_bin):
    """Smoke-test the baked image when ENDLEAF_IMAGE is already present."""
    import json
    import subprocess

    image, _name = setting(os.environ, "IMAGE", default="")
    if not image:
        pytest.skip("ENDLEAF_IMAGE is unset; image was not built in this environment")
    binary, _podman_name = podman_bin
    exists = subprocess.run(
        [binary, "image", "exists", image],
        check=False,
    )
    if exists.returncode != 0:
        pytest.skip(f"image {image} is not present locally")
    from colophon.podman_args import build_podman_run_args

    args = build_podman_run_args(podman=binary, image=image, name="endleaf-job-itest")
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
    assert b"ENDLEAF_STATUS" in completed.stderr or completed.returncode == 0
