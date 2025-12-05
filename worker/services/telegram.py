import mimetypes
import os
from typing import Any, Dict, Optional

import httpx
from aiogram.types import Message


class TelegramClient:
    def __init__(self, token: str, timeout: int = 20):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.client = httpx.Client(timeout=timeout)

    def close(self):
        self.client.close()

    # ------------------------- Internal helpers -------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        files: Dict[str, Any] = None,
    ):
        """Generic request wrapper."""
        url = f"{self.base_url}/{endpoint}"
        resp = self.client.request(method, url, json=json, data=data, files=files)
        resp.raise_for_status()
        return resp.json()

    # ------------------------- API actions -------------------------

    def send_message(self, chat_id: int, text: str):
        return self._request(
            "POST",
            "sendMessage",
            json={"chat_id": chat_id, "text": text},
        )

    def send_photo(self, chat_id: int, photo: str, caption: Optional[str] = None):
        """
        photo — URL or file_id
        """
        return self._request(
            "POST",
            "sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": photo,
                "caption": caption,
            },
        )

    def send_file(self, chat_id: int, file_path: str, caption: Optional[str] = None):
        """
        Universal file upload: document, image, PDF, etc.
        Telegram automatically detects file type.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File does not exist: {file_path}")

        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"

        with open(file_path, "rb") as f:
            return self._request(
                "POST",
                "sendDocument",
                data={"chat_id": chat_id, "caption": caption or ""},
                files={"document": (os.path.basename(file_path), f, mime)},
            )

    # ------------------------- File fetching -------------------------

    def get_file_path(self, file_id: str) -> str:
        """Fetch file_path by file_id via getFile."""
        result = self._request(
            "GET",
            "getFile",
            json={"file_id": file_id},
        )
        return result["result"]["file_path"]

    def download_file(self, file_path: str, dest: str) -> str:
        """Download file by file_path from Telegram CDN."""
        url = f"{self.file_url}/{file_path}"
        resp = self.client.get(url)
        resp.raise_for_status()

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(resp.content)

        return dest

    def download_all_files(self, message: Message, dest_dir: str) -> list[str]:
        os.makedirs(dest_dir, exist_ok=True)

        saved_paths = []
        file_ids = []

        if message.photo:
            for photo in message.photo:
                file_ids.append(photo.file_id)

        if message.video:
            file_ids.append(message.video.file_id)

        if message.document:
            file_ids.append(message.document.file_id)

        for file_id in file_ids:
            remote_path = self.get_file_path(file_id)
            filename = os.path.basename(remote_path)
            local_path = os.path.join(dest_dir, filename)

            self.download_file(remote_path, local_path)
            saved_paths.append(local_path)

        return saved_paths
