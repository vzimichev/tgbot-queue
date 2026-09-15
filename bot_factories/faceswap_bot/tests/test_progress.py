import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot_factories.faceswap_bot.repository import process_face_fusion_task


class FaceSwapProgressAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_builds_faceswap_payload_and_validates_output(self):
        captured_payload = None

        async def run_job(client, payload, progress_callback=None):
            nonlocal captured_payload
            captured_payload = payload
            Path(payload["output_path"]).write_bytes(b"video")
            return {"status": "done"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo = root / "source.jpg"
            video = root / "target.mp4"
            photo.write_bytes(b"photo")
            video.write_bytes(b"video")

            with patch("shared.job_client.HttpJobClient.run", run_job):
                output = await process_face_fusion_task(photo, video)

            self.assertEqual(output.read_bytes(), b"video")

        self.assertEqual(captured_payload["source_paths"], [str(photo.resolve())])
        self.assertEqual(captured_payload["target_path"], str(video.resolve()))
        self.assertNotIn("job_id", captured_payload)


if __name__ == "__main__":
    unittest.main()
