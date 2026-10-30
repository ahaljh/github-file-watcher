"""config 모듈 테스트: WATCH_TARGETS 설정 로드와 감시 대상 조회."""

from __future__ import annotations

import json

import pytest

from git_file_watcher import config
from git_file_watcher.config import WatchTarget

BASE = {"GITHUB_WEBHOOK_SECRET": "s", "SLACK_WEBHOOK_URL": "https://hooks.slack.test/x"}


def test_watch_targets() -> None:
    raw = json.dumps(
        {
            "acme/backend": {"files": ["pyproject.toml", "uv.lock"]},
            "acme/frontend": {"branch": "main", "files": "package.json, package-lock.json"},
        }
    )
    cfg = config.load({**BASE, "WATCH_TARGETS": raw})
    assert cfg.targets == (
        # branch 생략 시 develop.
        WatchTarget("acme/backend", "develop", ("pyproject.toml", "uv.lock")),
        WatchTarget("acme/frontend", "main", ("package.json", "package-lock.json")),
    )


def test_find_target() -> None:
    raw = json.dumps({"acme/backend": {"files": ["uv.lock"]}})
    cfg = config.load({**BASE, "WATCH_TARGETS": raw})
    # repo 이름은 대소문자 무시.
    assert cfg.find_target("ACME/Backend") == cfg.targets[0]
    assert cfg.find_target("acme/other") is None
    assert cfg.find_target(None) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "{}",
        '{"acme/backend": ["uv.lock"]}',
        '{"acme/backend": {}}',
        '{"acme/backend": {"files": []}}',
        '{"acme/backend": {"files": [1]}}',
        '{"acme/backend": {"files": ["uv.lock"], "branch": ""}}',
        '{" ": {"files": ["uv.lock"]}}',
    ],
)
def test_watch_targets_invalid(raw: str) -> None:
    with pytest.raises(config.ConfigError):
        config.load({**BASE, "WATCH_TARGETS": raw})


@pytest.mark.parametrize("missing", ["GITHUB_WEBHOOK_SECRET", "SLACK_WEBHOOK_URL", "WATCH_TARGETS"])
def test_missing_required(missing: str) -> None:
    env = {**BASE, "WATCH_TARGETS": '{"acme/backend": {"files": ["uv.lock"]}}'}
    del env[missing]
    with pytest.raises(config.ConfigError):
        config.load(env)
