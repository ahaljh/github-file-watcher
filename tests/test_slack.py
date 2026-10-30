"""slack 메시지 구성 테스트."""

from __future__ import annotations

from git_file_watcher import slack
from git_file_watcher.github import PushInfo


def test_build_message_contains_files_and_repo() -> None:
    info = PushInfo(
        repo="acme/ai-agent",
        branch="develop",
        pusher="hong-gildong",
        compare_url="https://github.com/acme/ai-agent/compare/a...b",
        head_commit_url="https://github.com/acme/ai-agent/commit/b",
        head_commit_message="chore: lock deps\n\n본문",
    )
    message = slack.build_message(info, ["pyproject.toml", "uv.lock"], "develop")

    assert "acme/ai-agent" in message["text"]
    assert "pyproject.toml" in message["text"]
    assert "uv.lock" in message["text"]
    assert message["blocks"], "block이 비어 있으면 안 됨"

    # 커밋 메시지는 첫 줄만 요약되어야 한다.
    dumped = str(message)
    assert "chore: lock deps" in dumped
    assert "본문" not in dumped


def test_build_message_escapes_mrkdwn() -> None:
    info = PushInfo(
        repo="acme/ai-agent",
        branch="develop",
        pusher=None,
        compare_url=None,
        head_commit_url=None,
        head_commit_message="fix: <!channel> a & b > c",
    )
    message = slack.build_message(info, ["uv.lock"], "develop")

    # 멘션/링크 문법이 해석되지 않도록 이스케이프되어야 한다.
    dumped = str(message["blocks"])
    assert "<!channel>" not in dumped
    assert "&lt;!channel&gt; a &amp; b &gt; c" in dumped


def _link_text(message: dict) -> str:
    """'변경 내용 보기' 링크가 담긴 context 블록의 텍스트를 반환한다."""
    texts = [
        el["text"]
        for block in message["blocks"]
        if block["type"] == "context"
        for el in block["elements"]
        if "변경 내용 보기" in el["text"]
    ]
    assert len(texts) == 1
    return texts[0]


def test_build_message_links_compare_url() -> None:
    info = PushInfo(
        repo="acme/ai-agent",
        branch="develop",
        pusher=None,
        compare_url="https://github.com/acme/ai-agent/compare/a...b",
        head_commit_url="https://github.com/acme/ai-agent/commit/b",
        head_commit_message=None,
    )
    message = slack.build_message(info, ["uv.lock"], "develop")
    assert _link_text(message) == "<https://github.com/acme/ai-agent/compare/a...b|변경 내용 보기>"


def test_build_message_falls_back_to_head_commit_url() -> None:
    info = PushInfo(
        repo="acme/ai-agent",
        branch="develop",
        pusher=None,
        compare_url=None,
        head_commit_url="https://github.com/acme/ai-agent/commit/b",
        head_commit_message=None,
    )
    message = slack.build_message(info, ["uv.lock"], "develop")
    assert _link_text(message) == "<https://github.com/acme/ai-agent/commit/b|변경 내용 보기>"


def test_build_message_sender_fields() -> None:
    info = PushInfo("acme/ai-agent", "develop", None, None, None, None)

    # 미설정 시 payload에 키 자체가 없어야 한다.
    plain = slack.build_message(info, ["uv.lock"], "develop")
    assert set(plain) == {"text", "blocks"}

    custom = slack.build_message(
        info, ["uv.lock"], "develop",
        username="github-file-watcher", icon_emoji=":owl:", icon_url="https://x/i.png",
    )
    assert custom["username"] == "github-file-watcher"
    assert custom["icon_emoji"] == ":owl:"
    assert custom["icon_url"] == "https://x/i.png"
