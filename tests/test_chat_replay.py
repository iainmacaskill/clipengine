import json

import httpx
import pytest

from clipengine.ingest import chat_replay
from clipengine.ingest.chat_replay import ChatReplayError, download_chat, iter_chat


def _node(offset, user, fragments, comment_id="c"):
    return {
        "id": comment_id,
        "contentOffsetSeconds": offset,
        "commenter": {"displayName": user} if user else None,
        "message": {"fragments": fragments},
    }


def _page(edges, has_next):
    return {
        "data": {
            "video": {
                "comments": {
                    "edges": edges,
                    "pageInfo": {"hasNextPage": has_next},
                }
            }
        }
    }


def _mock_client(pages, requests_log=None):
    """httpx client whose GQL endpoint serves `pages` in sequence."""
    state = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if requests_log is not None:
            requests_log.append(json.loads(request.content))
        page = pages[state["i"]]
        state["i"] = min(state["i"] + 1, len(pages) - 1)
        return httpx.Response(200, json=page)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_single_page_parses_messages():
    pages = [
        _page(
            [
                {"cursor": "a", "node": _node(12.5, "alice", [{"text": "KEKW"}])},
                {"cursor": "b", "node": _node(13.0, "bob", [{"text": "no "}, {"text": "way"}])},
            ],
            has_next=False,
        )
    ]
    msgs = list(iter_chat("123", client=_mock_client(pages)))
    assert len(msgs) == 2
    assert msgs[0].offset == 12.5 and msgs[0].user == "alice" and msgs[0].text == "KEKW"
    assert msgs[1].text == "no way"  # fragments joined


def test_pagination_uses_cursor_from_last_edge():
    log = []
    pages = [
        _page([{"cursor": "CUR1", "node": _node(1, "a", [{"text": "x"}])}], has_next=True),
        _page([{"cursor": "CUR2", "node": _node(2, "b", [{"text": "y"}])}], has_next=False),
    ]
    msgs = list(iter_chat("123", client=_mock_client(pages, log), page_pause_s=0))
    assert [m.offset for m in msgs] == [1.0, 2.0]
    assert "contentOffsetSeconds" in log[0]["variables"]
    assert log[1]["variables"].get("cursor") == "CUR1"


def test_deleted_commenter_and_empty_fragments():
    pages = [
        _page([{"cursor": "a", "node": _node(5, None, [])}], has_next=False)
    ]
    msgs = list(iter_chat("123", client=_mock_client(pages)))
    assert msgs[0].user == "" and msgs[0].text == ""


def test_missing_video_raises():
    pages = [{"data": {"video": None}}]
    with pytest.raises(ChatReplayError, match="no video"):
        list(iter_chat("999", client=_mock_client(pages)))


def test_gql_error_raises_after_retries(monkeypatch):
    monkeypatch.setattr(chat_replay.time, "sleep", lambda s: None)
    pages = [{"errors": [{"message": "PersistedQueryNotFound"}]}]
    with pytest.raises(ChatReplayError, match="PersistedQueryNotFound"):
        list(iter_chat("123", client=_mock_client(pages)))


def test_download_chat_writes_pipeline_jsonl(tmp_path):
    pages = [
        _page(
            [
                {"cursor": "a", "node": _node(1.0, "a", [{"text": "hello"}])},
                {"cursor": "b", "node": _node(2.0, "b", [{"text": "LUL"}])},
            ],
            has_next=False,
        )
    ]
    out = tmp_path / "chat.jsonl"
    count = download_chat("123", str(out), client=_mock_client(pages))
    assert count == 2
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert lines[0] == {"offset": 1.0, "user": "a", "text": "hello"}

    # round-trip: the detector's parser accepts the downloader's output
    from clipengine.detect.chat import parse_chat_jsonl

    msgs = parse_chat_jsonl(str(out))
    assert len(msgs) == 2 and msgs[1].text == "LUL"
