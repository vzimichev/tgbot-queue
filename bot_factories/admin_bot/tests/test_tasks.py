from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot_factories.admin_bot import tasks


def test_managed_bot_updates_ignores_missing_token_or_update_id(monkeypatch):
    monkeypatch.setattr(tasks, "managed_bot_token", Mock(return_value=None))

    assert tasks.managed_bot_updates.run(99, {"update_id": 1}) == {"status": "ignored"}


def test_managed_bot_updates_dispatches_valid_update_and_closes_session(monkeypatch):
    session = SimpleNamespace(close=AsyncMock())
    bot = SimpleNamespace(session=session)
    feed = AsyncMock(return_value={"status": "configured"})
    monkeypatch.setattr(tasks, "managed_bot_token", Mock(return_value="123:child"))
    monkeypatch.setattr(tasks, "Bot", Mock(return_value=bot))
    monkeypatch.setattr(tasks.managed_bot_dispatcher, "feed_update", feed)
    body = {
        "update_id": 12,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "A"},
            "text": "/start",
        },
    }

    assert tasks.managed_bot_updates.run(99, body) == {"status": "configured"}
    assert feed.await_args.kwargs["managed_bot_id"] == 99
    assert feed.await_args.kwargs["managed_update_id"] == 12
    session.close.assert_awaited_once()


def test_faceswap_task_processes_queued_media_outside_update_worker(monkeypatch):
    progress = SimpleNamespace(edit_text=AsyncMock())
    session = SimpleNamespace(close=AsyncMock())
    bot = SimpleNamespace(
        session=session,
        send_message=AsyncMock(return_value=progress),
        send_document=AsyncMock(),
    )
    monkeypatch.setattr(tasks, "managed_bot_token", Mock(return_value="123:child"))
    monkeypatch.setattr(tasks, "Bot", Mock(return_value=bot))
    monkeypatch.setattr(
        tasks,
        "save_media",
        AsyncMock(side_effect=[Path("photo.jpg"), Path("video.mp4")]),
    )
    monkeypatch.setattr(
        tasks, "process_faceswap_task", AsyncMock(return_value=Path("result.mp4"))
    )

    assert tasks.process_managed_faceswap.run(
        "123:child",
        7,
        {
            "photo_file_id": "photo-id",
            "photo_file_name": "photo.jpg",
            "video_file_id": "video-id",
            "video_file_name": "video.mp4",
        },
    ) == {"status": "complete"}
    bot.send_message.assert_awaited_once_with(7, "Face swap: 0% — preparing inputs")
    bot.send_document.assert_awaited_once()
    session.close.assert_awaited_once()
