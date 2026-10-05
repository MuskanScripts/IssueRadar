"""GitHub webhook deliveries.

Each delivery is checked against the shared secret (HMAC-SHA256), stored once
(GitHub may deliver the same one twice), and handed to the worker. Nothing is
done inline, so GitHub always gets a fast answer.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import Jobs, get_db, get_jobs, get_settings
from firstpr_api.settings import Settings
from firstpr_platform.db import WebhookEvent

router = APIRouter()
MAX_BYTES = 5 * 1024 * 1024


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@router.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Response:
    secret = settings.github_webhook_secret.get_secret_value()
    if not secret:
        raise HTTPException(503, "Webhooks are not set up on this server")
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(413, "Payload too large")
    if not signature_ok(secret, body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Bad signature")

    event = request.headers.get("x-github-event", "")
    delivery = request.headers.get("x-github-delivery", "")
    if not event or not delivery:
        raise HTTPException(400, "Missing GitHub event headers")
    if event == "ping":
        return Response(status_code=200)
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Body is not JSON") from None

    if await db.get(WebhookEvent, delivery) is not None:
        return Response(status_code=202)  # already have it
    repo = (payload.get("repository") or {}).get("full_name")
    sender = (payload.get("sender") or {}).get("id")
    db.add(
        WebhookEvent(
            delivery_id=delivery[:64],
            event=event[:50],
            action=(payload.get("action") or None),
            repo_full_name=repo,
            sender_github_id=int(sender) if sender is not None else None,
            payload=body.decode("utf-8", errors="replace"),
        )
    )
    await db.commit()
    await jobs.enqueue_job("handle_webhook", delivery, _job_id=f"webhook:{delivery}")
    return Response(status_code=202)
