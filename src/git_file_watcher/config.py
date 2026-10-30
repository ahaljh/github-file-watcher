"""환경변수 기반 설정 로드.

Lambda 환경변수로 동작을 제어한다. 시크릿/URL 같은 민감 정보는 코드에 두지 않고
모두 환경변수로 주입한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """필수 환경변수가 없거나 잘못된 경우 발생."""


@dataclass(frozen=True)
class Config:
    """실행에 필요한 설정 값 모음."""

    github_webhook_secret: str
    slack_webhook_url: str
    watch_branch: str
    watch_files: tuple[str, ...]
    watch_repo: str | None
    log_level: str


def _split_files(raw: str) -> tuple[str, ...]:
    """콤마로 구분된 파일 패턴 문자열을 정규화된 튜플로 변환."""
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def load(env: dict[str, str] | None = None) -> Config:
    """환경변수에서 설정을 로드한다.

    Args:
        env: 테스트용으로 주입할 환경 매핑. 기본값은 ``os.environ``.

    Raises:
        ConfigError: 필수 값이 없거나 감시 파일 목록이 비어 있을 때.
    """
    env = os.environ if env is None else env

    secret = env.get("GITHUB_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise ConfigError("GITHUB_WEBHOOK_SECRET 환경변수가 필요합니다.")

    slack_url = env.get("SLACK_WEBHOOK_URL", "").strip()
    if not slack_url:
        raise ConfigError("SLACK_WEBHOOK_URL 환경변수가 필요합니다.")

    watch_branch = env.get("WATCH_BRANCH", "develop").strip() or "develop"

    watch_files = _split_files(env.get("WATCH_FILES", "pyproject.toml,uv.lock"))
    if not watch_files:
        raise ConfigError("WATCH_FILES 에 최소 하나의 파일 패턴이 필요합니다.")

    watch_repo = env.get("WATCH_REPO", "").strip() or None
    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return Config(
        github_webhook_secret=secret,
        slack_webhook_url=slack_url,
        watch_branch=watch_branch,
        watch_files=watch_files,
        watch_repo=watch_repo,
        log_level=log_level,
    )
