"""Service-to-service auth for Pi → Open WebUI tool dispatch.

The data-analysis tool functions are normally invoked by Open WebUI's native
chat completion middleware, which injects ``__user__`` from the session token.
When the Pi runtime drives the agent loop instead, it calls the same tool
functions over HTTP and identifies the end-user via ``X-User-Id``. The HTTP
endpoints accept only requests carrying ``X-Pi-Service-Token`` matching
``AOH_PI_SHARED_SECRET``; this is intentionally mutually exclusive with the
browser-facing session auth so the surface area is small and explicit.

If the secret is not configured, every service endpoint returns 503. This
fails closed: a misconfigured deployment cannot accidentally expose tool
execution to unauthenticated callers.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException


def _service_secret() -> str | None:
    raw = os.environ.get('AOH_PI_SHARED_SECRET') or ''
    raw = raw.strip()
    return raw or None


def verify_pi_service_token(
    x_pi_service_token: Annotated[str | None, Header(alias='X-Pi-Service-Token')] = None,
    x_user_id: Annotated[str | None, Header(alias='X-User-Id')] = None,
) -> dict:
    """FastAPI dependency for Pi service-to-service tool calls.

    Returns ``{user_id: ...}`` on success.

    - 503 if ``AOH_PI_SHARED_SECRET`` is not set on this hub.
    - 401 if the supplied token is missing or does not match.
    - 400 if ``X-User-Id`` is missing.
    """
    secret = _service_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail='Pi service integration is not configured on this hub')
    if not x_pi_service_token or x_pi_service_token != secret:
        raise HTTPException(status_code=401, detail='Invalid or missing X-Pi-Service-Token')
    user_id = (x_user_id or '').strip()
    if not user_id:
        raise HTTPException(status_code=400, detail='X-User-Id header is required for service calls')
    return {'user_id': user_id}
