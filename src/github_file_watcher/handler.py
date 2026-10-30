"""AWS Lambda 진입점 — GitHub webhook(Function URL) 처리.

흐름:
1. Function URL 이벤트에서 raw body와 헤더를 꺼낸다(필요 시 base64 디코드).
2. HMAC 서명을 검증한다.
3. push 이벤트인지, 감시 브랜치인지, 감시 파일이 변경됐는지 확인한다.
4. 조건을 만족하면 Slack으로 알림을 보낸다.
"""

from __future__ import annotations

import base64
import json
import logging

from . import config, github, slack

logger = logging.getLogger("git_file_watcher")


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level, logging.INFO))
    logger.setLevel(getattr(logging, level, logging.INFO))


def _response(status: int, body: dict) -> dict:
    """Function URL(payload v2.0) 형식의 응답을 만든다."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _raw_body(event: dict) -> bytes:
    """이벤트에서 원본 바이트 본문을 추출한다.

    Function URL은 본문을 base64로 인코딩해 전달할 수 있다. HMAC 검증을 위해
    반드시 인코딩 이전의 원본 바이트를 복원해야 한다.
    """
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _headers(event: dict) -> dict[str, str]:
    """헤더 키를 소문자로 정규화해 반환한다."""
    headers = event.get("headers") or {}
    return {str(k).lower(): v for k, v in headers.items()}


def lambda_handler(event: dict, context: object = None) -> dict:
    """Lambda 핸들러 진입점."""
    try:
        cfg = config.load()
    except config.ConfigError:
        # 설정 오류는 배포 문제이므로 GitHub에 5xx로 알리고 로그로 원인을 남긴다.
        logger.exception("설정 로드 실패")
        return _response(500, {"status": "configuration error"})
    _setup_logging(cfg.log_level)

    raw = _raw_body(event)
    headers = _headers(event)
    github_event = headers.get("x-github-event", "")
    signature = headers.get("x-hub-signature-256")

    # 1) 서명 검증 — 실패 시 즉시 거부.
    if not github.verify_signature(cfg.github_webhook_secret, raw, signature):
        logger.warning("서명 검증 실패 (event=%s)", github_event)
        return _response(401, {"status": "invalid signature"})

    # ping 이벤트(연결 테스트)는 서명만 확인하고 200으로 응답.
    if github_event == "ping":
        return _response(200, {"status": "pong"})

    if github_event != "push":
        logger.info("push 아닌 이벤트 무시: %s", github_event)
        return _response(200, {"status": "ignored", "reason": "not a push event"})

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("payload JSON 파싱 실패")
        return _response(400, {"status": "invalid payload"})

    # 2) repo에 해당하는 감시 대상 선택.
    repo = github.repo_full_name(payload)
    target = cfg.find_target(repo)
    if target is None:
        logger.info("대상 repo 아님: %s", repo)
        return _response(200, {"status": "ignored", "reason": "repo mismatch"})

    # 3) 브랜치 필터.
    branch = github.branch_name(payload)
    if branch != target.branch:
        logger.info("대상 브랜치 아님: %s (repo=%s)", branch, repo)
        return _response(200, {"status": "ignored", "reason": "branch mismatch"})

    # 4) 변경 파일 매칭.
    changed = github.extract_changed_files(payload)
    matched = github.match_watched(changed, target.files)
    if not matched:
        logger.info("감시 파일 변경 없음 (repo=%s, 변경 %d개)", repo, len(changed))
        return _response(200, {"status": "ignored", "reason": "no watched files changed"})

    # 5) Slack 알림.
    info = github.summarize(payload)
    message = slack.build_message(
        info,
        matched,
        target.branch,
        username=cfg.slack_username,
        icon_emoji=cfg.slack_icon_emoji,
        icon_url=cfg.slack_icon_url,
    )
    try:
        slack.send(cfg.slack_webhook_url, message)
    except OSError:
        # URLError/HTTPError/타임아웃 모두 OSError 하위 클래스.
        # 웹훅 URL(시크릿)은 로그에 남기지 않는다.
        logger.exception("Slack 알림 전송 실패: %s", matched)
        return _response(502, {"status": "slack delivery failed", "matched": matched})
    logger.info("Slack 알림 전송: %s", matched)

    return _response(200, {"status": "notified", "matched": matched})
