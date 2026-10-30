"""Slack Incoming Webhook 알림 전송.

외부 의존성 없이 stdlib ``urllib`` 만으로 JSON을 POST 한다.
"""

from __future__ import annotations

import json
import urllib.request

from .github import PushInfo

_TIMEOUT_SECONDS = 10


def _escape(text: str) -> str:
    """Slack mrkdwn 제어 문자(&, <, >)를 이스케이프한다.

    커밋 메시지 등 외부 입력에 ``<!channel>`` 같은 멘션이나 링크 문법이
    섞여 있어도 그대로 해석되지 않도록 막는다.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(
    info: PushInfo,
    matched_files: list[str],
    watch_branch: str,
    username: str | None = None,
    icon_emoji: str | None = None,
    icon_url: str | None = None,
) -> dict:
    """Slack Incoming Webhook용 메시지 payload(Block Kit)를 만든다.

    ``username`` / ``icon_emoji`` / ``icon_url`` 은 값이 있을 때만 payload에 넣는다.
    (레거시 webhook에서만 적용되고, Slack App webhook에서는 무시된다.)
    """
    repo = _escape(info.repo or "(unknown repo)")
    branch = _escape(info.branch or watch_branch)
    files_text = "\n".join(f"• `{_escape(path)}`" for path in matched_files)

    header = f":package: [{repo}] {branch} 브랜치의 아래 파일이 변경되었습니다."

    fields = [f"*변경 파일*\n{files_text}"]
    if info.pusher:
        fields.append(f"*Pusher*\n{_escape(info.pusher)}")

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{header}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(fields)}},
    ]

    if info.head_commit_message:
        # 커밋 메시지는 첫 줄만 요약해서 표시.
        summary = _escape(info.head_commit_message.splitlines()[0])
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f":memo: {summary}"}],
            }
        )

    # push에 포함된 모든 커밋의 변경을 한 화면에서 볼 수 있도록 compare URL 우선.
    link = info.compare_url or info.head_commit_url
    if link:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{link}|변경 내용 보기>"}],
            }
        )

    # Block Kit 미지원 클라이언트를 위한 fallback 텍스트.
    fallback = f"{header}\n{files_text}"
    message: dict = {"text": fallback, "blocks": blocks}
    if username:
        message["username"] = username
    if icon_emoji:
        message["icon_emoji"] = icon_emoji
    if icon_url:
        message["icon_url"] = icon_url
    return message


def send(webhook_url: str, message: dict) -> None:
    """Slack Incoming Webhook으로 메시지를 POST 한다.

    Raises:
        urllib.error.URLError / HTTPError: 전송 실패 시. (2xx 외 응답은
            ``urlopen`` 이 HTTPError 로 던진다.)
    """
    data = json.dumps(message).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):
        pass
