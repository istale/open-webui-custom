"""Unit tests for the Pi service-to-service auth dependency.

We exercise the dependency directly (it is just a function) instead of
booting a FastAPI app, so the assertions stay focused on the auth logic
itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from open_webui.utils.data_analysis.service_auth import verify_pi_service_token


@pytest.fixture(autouse=True)
def _clear_secret(monkeypatch):
    monkeypatch.delenv('AOH_PI_SHARED_SECRET', raising=False)
    yield


def test_503_when_secret_not_configured():
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token='anything', x_user_id='alice')
    assert exc.value.status_code == 503


def test_401_when_token_missing(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', 's3cret')
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token=None, x_user_id='alice')
    assert exc.value.status_code == 401


def test_401_when_token_mismatch(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', 's3cret')
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token='wrong', x_user_id='alice')
    assert exc.value.status_code == 401


def test_400_when_user_id_missing(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', 's3cret')
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token='s3cret', x_user_id=None)
    assert exc.value.status_code == 400


def test_400_when_user_id_blank(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', 's3cret')
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token='s3cret', x_user_id='   ')
    assert exc.value.status_code == 400


def test_returns_user_id_on_success(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', 's3cret')
    ctx = verify_pi_service_token(x_pi_service_token='s3cret', x_user_id='alice')
    assert ctx == {'user_id': 'alice'}


def test_secret_with_surrounding_whitespace_is_trimmed(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', '  s3cret  ')
    ctx = verify_pi_service_token(x_pi_service_token='s3cret', x_user_id='alice')
    assert ctx == {'user_id': 'alice'}


def test_empty_string_secret_treated_as_unset(monkeypatch):
    monkeypatch.setenv('AOH_PI_SHARED_SECRET', '   ')
    with pytest.raises(HTTPException) as exc:
        verify_pi_service_token(x_pi_service_token='anything', x_user_id='alice')
    assert exc.value.status_code == 503
