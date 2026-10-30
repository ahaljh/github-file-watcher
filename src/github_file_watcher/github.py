"""GitHub push webhook 처리: 서명 검증과 payload 파싱.

GitHub Action 없이 webhook만으로 동작하므로, 요청 진위 확인은 전적으로
``X-Hub-Signature-256`` HMAC 서명 검증에 의존한다.
"""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
from dataclasses import dataclass

_BRANCH_PREFIX = "refs/heads/"


def verify_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """GitHub이 보낸 ``X-Hub-Signature-256`` 헤더를 검증한다.

    서명은 반드시 전송된 **원본 바이트**(raw_body)로 계산해야 한다. JSON을 다시
    직렬화하면 바이트가 달라져 검증이 실패한다.

    Args:
        secret: webhook에 설정한 시크릿.
        raw_body: 요청 본문 원본 바이트.
        signature_header: ``sha256=...`` 형식의 헤더 값.

    Returns:
        서명이 유효하면 True.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    expected = "sha256=" + digest
    # 타이밍 공격 방지를 위해 상수시간 비교.
    return hmac.compare_digest(expected, signature_header)


def branch_name(payload: dict) -> str | None:
    """push payload의 ``ref``에서 브랜치명을 추출한다. (태그 등은 None)"""
    ref = payload.get("ref", "")
    if isinstance(ref, str) and ref.startswith(_BRANCH_PREFIX):
        return ref[len(_BRANCH_PREFIX) :]
    return None


def repo_full_name(payload: dict) -> str | None:
    """push payload에서 ``owner/repo`` 전체 이름을 추출한다."""
    repo = payload.get("repository")
    if isinstance(repo, dict):
        name = repo.get("full_name")
        if isinstance(name, str) and name:
            return name
    return None


def extract_changed_files(payload: dict) -> list[str]:
    """push에 포함된 모든 커밋에서 변경된 파일 경로의 합집합을 반환한다.

    각 커밋의 added/modified/removed 와 head_commit 을 모두 모은다.

    한계: GitHub push payload의 커밋/파일 목록은 대량 push 시 truncate될 수 있다.
    develop 일상 push에는 충분하지만, 필요하면 Compare API 폴백을 추가할 수 있다.
    """
    files: set[str] = set()

    commits = payload.get("commits")
    entries: list[dict] = list(commits) if isinstance(commits, list) else []

    head = payload.get("head_commit")
    if isinstance(head, dict):
        entries.append(head)

    for commit in entries:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            values = commit.get(key)
            if isinstance(values, list):
                files.update(str(path) for path in values)

    return sorted(files)


def match_watched(changed_files: list[str], patterns: tuple[str, ...]) -> list[str]:
    """변경 파일 중 감시 패턴(fnmatch glob)에 걸리는 것만 골라 반환한다."""
    matched: list[str] = []
    for path in changed_files:
        if any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
            matched.append(path)
    return matched


@dataclass(frozen=True)
class PushInfo:
    """알림 구성에 필요한 push 요약 정보."""

    repo: str | None
    branch: str | None
    pusher: str | None
    compare_url: str | None
    head_commit_url: str | None
    head_commit_message: str | None


def summarize(payload: dict) -> PushInfo:
    """Slack 메시지에 쓸 push 메타데이터를 payload에서 뽑아낸다."""
    pusher = None
    pusher_obj = payload.get("pusher")
    if isinstance(pusher_obj, dict):
        pusher = pusher_obj.get("name")
    if not pusher:
        sender = payload.get("sender")
        if isinstance(sender, dict):
            pusher = sender.get("login")

    head = payload.get("head_commit")
    head_url = head.get("url") if isinstance(head, dict) else None
    head_msg = head.get("message") if isinstance(head, dict) else None

    return PushInfo(
        repo=repo_full_name(payload),
        branch=branch_name(payload),
        pusher=pusher,
        compare_url=payload.get("compare"),
        head_commit_url=head_url,
        head_commit_message=head_msg,
    )
