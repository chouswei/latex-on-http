# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process entry points for the worker and the preflight command."""

import logging
import sys

from colophon.config import ConfigError, load_config
from colophon.killswitch import KillSwitch
from colophon.load import LoadMonitor
from colophon.preflight import main as preflight_main
from colophon.runner import Supervisor, make_podman_runner
from colophon.worker import serve


def main_worker():
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s %(name)s] %(message)s"
    )
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"colophon: refusing to start: {exc}", file=sys.stderr)
        return 2
    switch = KillSwitch(config.kill_switch_file)
    monitor = LoadMonitor()
    supervisor = Supervisor(
        make_podman_runner(config, switch),
        retry_after_sec=config.retry_after_sec,
    )
    serve(config, switch, monitor, supervisor)
    return 0


def main_preflight():
    return preflight_main()


if __name__ == "__main__":
    raise SystemExit(main_worker())
