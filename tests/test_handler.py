"""handler.lambda_handler end-to-end 테스트 (Slack 전송은 monkeypatch)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
from pathlib import Path

import pytest

from git_file_watcher import handler, slack

FIXTURE = Path(__file__).parent / "fixtures" / "push_event.json"
SECRET = "s3cr3t"


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setenv("WATCH_BRANCH", "develop")
    monkeypatch.setenv("WATCH_FILES", "pyproject.toml,uv.lock")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """slack.send 호출을 가로채 전송 메시지를 수집한다."""
    captured: list[dict] = []
    monkeypatch.setattr(slack, "send", lambda url, message: captured.append(message))
    return captured


def _event(body: bytes, event_type: str = "push", *, secret: str = SECRET, base64_encode: bool = False) -> dict:
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "headers": {"X-GitHub-Event": event_type, "X-Hub-Signature-256": sig},
        "body": base64.b64encode(body).decode() if base64_encode else body.decode(),
        "isBase64Encoded": base64_encode,
    }


def test_push_with_watched_files_notifies(sent: list[dict]) -> None:
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "notified"
    assert len(sent) == 1


def test_base64_encoded_body(sent: list[dict]) -> None:
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body, base64_encode=True))
    assert resp["statusCode"] == 200
    assert len(sent) == 1


def test_invalid_signature_rejected(sent: list[dict]) -> None:
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body, secret="wrong"))
    assert resp["statusCode"] == 401
    assert sent == []


def test_ping_event(sent: list[dict]) -> None:
    body = b'{"zen": "hi"}'
    resp = handler.lambda_handler(_event(body, event_type="ping"))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "pong"
    assert sent == []


def test_other_branch_ignored(sent: list[dict]) -> None:
    payload = json.loads(FIXTURE.read_bytes())
    payload["ref"] = "refs/heads/main"
    body = json.dumps(payload).encode()
    resp = handler.lambda_handler(_event(body))
    assert json.loads(resp["body"])["status"] == "ignored"
    assert sent == []


def test_no_watched_file_ignored(sent: list[dict]) -> None:
    payload = json.loads(FIXTURE.read_bytes())
    for commit in payload["commits"]:
        commit["modified"] = ["README.md"]
    payload["head_commit"]["modified"] = ["README.md"]
    body = json.dumps(payload).encode()
    resp = handler.lambda_handler(_event(body))
    assert json.loads(resp["body"])["status"] == "ignored"
    assert sent == []


def test_repo_mismatch_ignored(monkeypatch: pytest.MonkeyPatch, sent: list[dict]) -> None:
    monkeypatch.setenv("WATCH_REPO", "acme/other-repo")
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body))
    assert json.loads(resp["body"])["status"] == "ignored"
    assert sent == []


def test_slack_failure_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(url: str, message: dict) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(slack, "send", fail)
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body))
    assert resp["statusCode"] == 502
    assert json.loads(resp["body"])["status"] == "slack delivery failed"


def test_missing_config_returns_500(monkeypatch: pytest.MonkeyPatch, sent: list[dict]) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL")
    body = FIXTURE.read_bytes()
    resp = handler.lambda_handler(_event(body))
    assert resp["statusCode"] == 500
    assert json.loads(resp["body"])["status"] == "configuration error"
    assert sent == []
