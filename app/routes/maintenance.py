import logging
from functools import wraps

import click
import requests
from flask import Blueprint, current_app, jsonify, request
from qstash import Receiver

from app.errors import ApiError
from app.services.background import cleanup_expired_records, dispatch_pending, enabled, process_job
from app.services.device_health import mark_stale_doors_offline
from app.validation import require_json, string_field

maintenance_bp = Blueprint("maintenance", __name__)
logger = logging.getLogger(__name__)


def qstash_required(handler):
    @wraps(handler)
    def protected(*args, **kwargs):
        current_key = current_app.config.get("QSTASH_CURRENT_SIGNING_KEY")
        next_key = current_app.config.get("QSTASH_NEXT_SIGNING_KEY")
        if not current_key or not next_key:
            raise ApiError("Background jobs are not configured.", 503, "jobs_unavailable")
        try:
            Receiver(current_signing_key=current_key, next_signing_key=next_key).verify(
                signature=request.headers.get("Upstash-Signature", ""),
                body=request.get_data(as_text=True),
                url=f"{current_app.config['PUBLIC_APP_URL']}{request.path}",
            )
        except Exception as error:
            raise ApiError("Job authentication failed.", 401, "job_unauthorized") from error
        return handler(*args, **kwargs)
    return protected


@maintenance_bp.post("/jobs")
@qstash_required
def run_background_job():
    data = require_json(request)
    job_id = string_field(data, "job_id", max_length=32)
    try:
        result = process_job(job_id)
    except Exception:
        logger.exception("Background job failed job_id=%s", job_id)
        raise ApiError("Job will be retried.", 503, "job_retry")
    return jsonify({"status": result})


@maintenance_bp.post("/maintenance")
@qstash_required
def run_maintenance():
    offline_doors = mark_stale_doors_offline()
    published = dispatch_pending()
    return jsonify({"status": "ok", "newly_offline": len(offline_doors), "published": published})


@maintenance_bp.post("/cleanup")
@qstash_required
def run_cleanup():
    return jsonify({"status": "ok", "removed": cleanup_expired_records()})


@maintenance_bp.cli.command("sync-schedules")
def sync_schedules():
    """Create/update production QStash schedules without duplicates."""
    if not enabled():
        raise click.ClickException("Configure QSTASH_TOKEN before syncing schedules.")
    for name, path, cron in (
        ("tzufguard-maintenance", "maintenance", "2-57/5 * * * *"),
        ("tzufguard-cleanup", "cleanup", "17 3 * * *"),
    ):
        destination = f"{current_app.config['PUBLIC_APP_URL']}/api/internal/{path}"
        response = requests.post(
            f"{current_app.config['QSTASH_URL']}/v2/schedules/{destination}",
            headers={
                "Authorization": f"Bearer {current_app.config['QSTASH_TOKEN']}",
                "Upstash-Cron": cron,
                "Upstash-Schedule-Id": name,
                "Upstash-Retries": "3",
                "Upstash-Timeout": "30s",
                "Content-Type": "application/json",
            },
            json={}, timeout=15,
        )
        if not response.ok:
            raise click.ClickException(f"Could not sync {name} (HTTP {response.status_code}).")
        click.echo(f"Configured {name} ({cron})")
