"""github 모듈 단위 테스트: 서명 검증, 브랜치/파일 파싱, 매칭."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from github_file_watcher import github

FIXTURE = Path(__file__).parent / "fixtures" / "push_event.json"


@pytest.fixture
def raw_body() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def payload(raw_body: bytes) -> dict:
    return json.loads(raw_body)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --- 서명 검증 ---------------------------------------------------------------

def test_verify_signature_valid(raw_body: bytes) -> None:
    secret = "s3cr3t"
    assert github.verify_signature(secret, raw_body, _sign(secret, raw_body))


def test_verify_signature_tampered_body(raw_body: bytes) -> None:
    secret = "s3cr3t"
    sig = _sign(secret, raw_body)
    assert not github.verify_signature(secret, raw_body + b"x", sig)


def test_verify_signature_wrong_secret(raw_body: bytes) -> None:
    assert not github.verify_signature("other", raw_body, _sign("s3cr3t", raw_body))


@pytest.mark.parametrize("header", [None, "", "abc123", "sha1=deadbeef"])
def test_verify_signature_missing_or_malformed(raw_body: bytes, header: str | None) -> None:
    assert not github.verify_signature("s3cr3t", raw_body, header)


# --- 브랜치 / repo -----------------------------------------------------------

def test_branch_name(payload: dict) -> None:
    assert github.branch_name(payload) == "develop"


def test_branch_name_tag_returns_none() -> None:
    assert github.branch_name({"ref": "refs/tags/v1.0"}) is None


def test_repo_full_name(payload: dict) -> None:
    assert github.repo_full_name(payload) == "acme/ai-agent"


# --- 변경 파일 추출 / 매칭 ---------------------------------------------------

def test_extract_changed_files(payload: dict) -> None:
    files = github.extract_changed_files(payload)
    assert "pyproject.toml" in files
    assert "uv.lock" in files
    assert "src/agent/client.py" in files


def test_match_watched_default_patterns(payload: dict) -> None:
    files = github.extract_changed_files(payload)
    matched = github.match_watched(files, ("pyproject.toml", "uv.lock"))
    assert matched == ["pyproject.toml", "uv.lock"]


def test_match_watched_no_match() -> None:
    matched = github.match_watched(["README.md", "src/x.py"], ("pyproject.toml", "uv.lock"))
    assert matched == []


def test_match_watched_glob() -> None:
    files = ["services/api/pyproject.toml", "README.md"]
    matched = github.match_watched(files, ("**/pyproject.toml",))
    assert matched == ["services/api/pyproject.toml"]


# --- summarize ---------------------------------------------------------------

def test_summarize(payload: dict) -> None:
    info = github.summarize(payload)
    assert info.repo == "acme/ai-agent"
    assert info.branch == "develop"
    assert info.pusher == "hong-gildong"
    assert info.head_commit_url is not None
