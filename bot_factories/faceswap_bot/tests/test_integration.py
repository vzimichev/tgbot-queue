import asyncio
import os
import unittest
from pathlib import Path

from bot_factories.faceswap_bot.repository import process_face_fusion_task


@unittest.skipUnless(
    os.getenv("RUN_FACESWAP_INTEGRATION") == "1",
    "set RUN_FACESWAP_INTEGRATION=1 to run the local FaceFusion integration test",
)
class FaceSwapIntegrationTest(unittest.TestCase):
    def test_photo_and_video_fixtures_produce_mp4(self):
        fixtures_dir = Path(__file__).resolve().parent / "data"
        photo_path = Path(
            os.getenv(
                "FACESWAP_TEST_PHOTO",
                fixtures_dir / "2025-11-28 19.10.21.jpg",
            )
        )
        video_path = Path(
            os.getenv(
                "FACESWAP_TEST_VIDEO",
                fixtures_dir
                / "mixkit_portrait_of_woman_outdoors_while_snowing_33511_hd_ready.mp4",
            )
        )

        self.assertTrue(photo_path.is_file(), f"Missing photo: {photo_path}")
        self.assertTrue(video_path.is_file(), f"Missing video: {video_path}")

        output_path = asyncio.run(
            asyncio.wait_for(
                process_face_fusion_task(
                    photo_path=photo_path,
                    video_path=video_path,
                ),
                timeout=float(os.getenv("FACESWAP_TEST_TIMEOUT", "3600")),
            )
        )

        self.assertTrue(output_path.is_file(), f"Missing output: {output_path}")
        self.assertGreater(output_path.stat().st_size, 0, "Output video is empty")
        self.assertEqual(output_path.suffix.lower(), ".mp4")


if __name__ == "__main__":
    unittest.main()
