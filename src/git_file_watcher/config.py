"""환경변수 기반 설정 로드.

Lambda 환경변수로 동작을 제어한다. 시크릿/URL 같은 민감 정보는 코드에 두지 않고
모두 환경변수로 주입한다. 감시 대상은 ``WATCH_TARGETS`` 에 repo별 브랜치/파일 패턴을
JSON으로 지정한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

_DEFAULT_BRANCH = "develop"
_DEFAULT_SLACK_USERNAME = "github-file-watcher"
_DEFAULT_SLACK_ICON_EMOJI = ":owl:"


class ConfigError(RuntimeError):
    """필수 환경변수가 없거나 잘못된 경우 발생."""


@dataclass(frozen=True)
class WatchTarget:
    """감시 대상 하나(repo + 브랜치 + 파일 패턴)."""

    repo: str
    branch: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    """실행에 필요한 설정 값 모음."""

    github_webhook_secret: str
    slack_webhook_url: str
    targets: tuple[WatchTarget, ...]
    log_level: str
    # Slack 발신자 표시. 레거시 "Incoming WebHooks" 통합에서만 적용되고,
    # Slack App에서 발급한 webhook이면 Slack이 무시하고 App 설정을 따른다.
    slack_username: str | None = None
    slack_icon_emoji: str | None = None
    slack_icon_url: str | None = None

    def find_target(self, repo: str | None) -> WatchTarget | None:
        """payload의 repo(``owner/repo``)에 해당하는 감시 대상을 찾는다.

        GitHub repo 이름은 대소문자를 구분하지 않으므로 대소문자 무시로 비교한다.
        """
        if not repo:
            return None
        key = repo.casefold()
        return next((t for t in self.targets if t.repo.casefold() == key), None)


def _parse_files(raw: object) -> tuple[str, ...]:
    """파일 패턴(리스트 또는 콤마 구분 문자열)을 정규화된 튜플로 변환."""
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        items = raw
    else:
        return ()
    return tuple(item.strip() for item in items if item.strip())


def _parse_targets(raw: str) -> tuple[WatchTarget, ...]:
    """``WATCH_TARGETS`` JSON을 파싱한다.

    형식::

        {
          "acme/backend":  {"branch": "develop", "files": ["pyproject.toml", "uv.lock"]},
          "acme/frontend": {"files": ["package.json", "package-lock.json"]}
        }

    ``branch`` 를 생략하면 develop 을 쓴다.
    ``files`` 는 리스트 또는 콤마 구분 문자열 모두 허용한다.
    """
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(f"WATCH_TARGETS JSON 파싱 실패: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ConfigError("WATCH_TARGETS 는 비어 있지 않은 JSON 객체여야 합니다.")

    targets: list[WatchTarget] = []
    for repo, spec in data.items():
        repo = repo.strip()
        if not repo:
            raise ConfigError("WATCH_TARGETS 의 repo 이름이 비어 있습니다.")
        if not isinstance(spec, dict):
            raise ConfigError(f"WATCH_TARGETS[{repo}] 는 JSON 객체여야 합니다.")

        branch = spec.get("branch", _DEFAULT_BRANCH)
        if not isinstance(branch, str) or not branch.strip():
            raise ConfigError(f"WATCH_TARGETS[{repo}].branch 가 올바르지 않습니다.")

        files = _parse_files(spec.get("files"))
        if not files:
            raise ConfigError(f"WATCH_TARGETS[{repo}].files 에 최소 하나의 파일 패턴이 필요합니다.")

        targets.append(WatchTarget(repo=repo, branch=branch.strip(), files=files))

    return tuple(targets)


def load(env: dict[str, str] | None = None) -> Config:
    """환경변수에서 설정을 로드한다.

    Args:
        env: 테스트용으로 주입할 환경 매핑. 기본값은 ``os.environ``.

    Raises:
        ConfigError: 필수 값이 없거나 감시 대상 설정이 잘못됐을 때.
    """
    env = os.environ if env is None else env

    secret = env.get("GITHUB_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise ConfigError("GITHUB_WEBHOOK_SECRET 환경변수가 필요합니다.")

    slack_url = env.get("SLACK_WEBHOOK_URL", "").strip()
    if not slack_url:
        raise ConfigError("SLACK_WEBHOOK_URL 환경변수가 필요합니다.")

    raw_targets = env.get("WATCH_TARGETS", "").strip()
    if not raw_targets:
        raise ConfigError("WATCH_TARGETS 환경변수가 필요합니다.")

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    slack_icon_url = env.get("SLACK_ICON_URL", "").strip() or None
    slack_icon_emoji = env.get("SLACK_ICON_EMOJI", "").strip() or None
    if slack_icon_emoji is None and slack_icon_url is None:
        # icon_url만 설정한 경우엔 이모지가 우선 적용돼 URL이 묻히므로 기본 이모지를 넣지 않는다.
        slack_icon_emoji = _DEFAULT_SLACK_ICON_EMOJI

    return Config(
        github_webhook_secret=secret,
        slack_webhook_url=slack_url,
        targets=_parse_targets(raw_targets),
        log_level=log_level,
        slack_username=env.get("SLACK_USERNAME", "").strip() or _DEFAULT_SLACK_USERNAME,
        slack_icon_emoji=slack_icon_emoji,
        slack_icon_url=slack_icon_url,
    )
