# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP worker. Binds only to the configured address."""

import hmac
import logging
import threading

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from colophon.enums import JobRejected, parse_job
from colophon.legacy import parse_legacy_build
from colophon.limits import HOST_LOAD_REPORT_INTERVAL_SEC, INPUT_CAP_BYTES
from colophon.revision import version_payload
from colophon.runner import Outcome, enforce_output_cap, kill_container

logger = logging.getLogger(__name__)

_STATUS = {
    "rejectBusy": 429,
    "rejectLoadShed": 429,
    "rejectKillSwitch": 403,
    "rejectInvalidInput": 400,
    "rejectSpawnFail": 500,
    "rejectRenderError": 422,
    "failTimeout": 408,
    "failCapHit": 413,
}


def _token_ok(header, token):
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    presented = header[len("Bearer ") :]
    if presented == "" or any(ch.isspace() for ch in presented):
        return False
    return hmac.compare_digest(presented, token)


def _error(kind, *, retry_after=None, extra=None):
    body = {"error": kind}
    if extra:
        body.update(extra)
    response = jsonify(body)
    response.status_code = _STATUS[kind]
    response.headers["Cache-Control"] = "no-store"
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response


def _switch_block(switch):
    state = switch.read()
    if not state.blocks_jobs:
        return None
    return _error(
        "rejectKillSwitch",
        extra={"readable": state.readable, "engaged": True},
    )


def create_app(config, switch, monitor, supervisor):
    app = Flask("colophon")
    app.config["MAX_CONTENT_LENGTH"] = INPUT_CAP_BYTES
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def authorized():
        return _token_ok(request.headers.get("Authorization", ""), config.worker_token)

    def before_job(parse):
        if not authorized():
            return None, _error_status_401()
        blocked = _switch_block(switch)
        if blocked is not None:
            return None, blocked
        if supervisor.busy():
            return None, _error("rejectBusy", retry_after=config.retry_after_sec)
        payload = request.get_json(force=False, silent=True)
        try:
            job = parse(payload)
        except JobRejected as exc:
            return None, _error("rejectInvalidInput", extra={"field": exc.reason})
        decision = monitor.decision()
        if decision is not None:
            report = monitor.report(busy=False)
            return None, _error(
                "rejectLoadShed",
                retry_after=config.retry_after_sec,
                extra={"reason": decision, "load": report},
            )
        blocked = _switch_block(switch)
        if blocked is not None:
            return None, blocked
        return job, None

    def finish(job):
        outcome = supervisor.submit(job)
        if not isinstance(outcome, Outcome):
            return _error("rejectSpawnFail")
        if outcome.kind == "rejectBusy":
            return _error("rejectBusy", retry_after=config.retry_after_sec)
        if outcome.kind != "ok":
            return _error(outcome.kind)
        try:
            enforce_output_cap(outcome.body)
        except ValueError:
            return _error("failCapHit")
        if not outcome.body:
            return _error("rejectRenderError")
        response = app.response_class(outcome.body, mimetype=outcome.content_type)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Colophon-Result"] = "ok"
        return response

    @app.get("/version")
    def version():
        if not authorized():
            return _error_status_401()
        response = jsonify(version_payload())
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def root():
        if not authorized():
            return _error_status_401()
        return jsonify(
            service="colophon-render-worker",
            sandbox="rootless-podman",
        )

    @app.get("/v1/host-load")
    def host_load():
        if not authorized():
            return _error_status_401()
        report = monitor.report(busy=supervisor.busy())
        status = 200 if report["readable"] else 503
        response = jsonify(report)
        response.status_code = status
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/jobs")
    def jobs():
        job, error = before_job(parse_job)
        if error is not None:
            return error
        return finish(job)

    @app.post("/builds/sync")
    def builds_sync():
        job, error = before_job(parse_legacy_build)
        if error is not None:
            return error
        return finish(job)

    @app.post("/v1/jobs/abort")
    def abort():
        if not authorized():
            return _error_status_401()
        result = supervisor.request_abort(
            lambda name: kill_container(config.podman, name)
        )
        if result == "idle":
            response = jsonify({"aborted": False, "error": "idle"})
            response.status_code = 404
        elif result == "kill_failed":
            return _error("rejectSpawnFail")
        else:
            response = jsonify({"aborted": True})
            response.status_code = 200
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/switch")
    def switch_route():
        if not authorized():
            return _error_status_401()
        payload = request.get_json(force=False, silent=True)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("engaged"), bool
        ):
            return _error("rejectInvalidInput", extra={"field": "engaged"})
        try:
            switch.write(payload["engaged"])
        except OSError:
            return _error(
                "rejectKillSwitch",
                extra={"readable": False, "engaged": True},
            )
        state = switch.read()
        if state.blocks_jobs and not payload["engaged"]:
            return _error(
                "rejectKillSwitch",
                extra={"readable": state.readable, "engaged": True},
            )
        response = jsonify({"readable": state.readable, "engaged": state.engaged})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def too_large(_exc):
        if not authorized():
            return _error_status_401()
        return _error("rejectInvalidInput", extra={"field": "input"})

    @app.errorhandler(Exception)
    def fail_closed(exc):
        if isinstance(exc, HTTPException):
            return exc
        logger.warning("fail closed: %s", exc.__class__.__name__)
        return _error("rejectSpawnFail")

    return app


def _error_status_401():
    response = jsonify({"error": "unauthorized"})
    response.status_code = 401
    response.headers["Cache-Control"] = "no-store"
    return response


def serve(config, switch, monitor, supervisor):
    """Listen on the configured address. One process, several threads.

    Threads let AbortJob and HostLoadReport run while the single job holds
    the concurrency lock. A second process would not share that lock.
    """
    monitor.sample()
    stop = threading.Event()

    def loop():
        while not stop.wait(HOST_LOAD_REPORT_INTERVAL_SEC):
            monitor.sample()

    thread = threading.Thread(target=loop, name="colophon-load", daemon=True)
    thread.start()
    app = create_app(config, switch, monitor, supervisor)
    try:
        app.run(
            host=config.bind_address,
            port=config.port,
            threaded=True,
            use_reloader=False,
        )
    finally:
        stop.set()
