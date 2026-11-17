import unittest
from io import BytesIO
from types import SimpleNamespace

from roboticrover_pi3.camera import CameraHandler, FrameStore, JpegParser, build_parser, ffmpeg_command


JPEG = b"\xff\xd8test-frame\xff\xd9"


class CameraTests(unittest.TestCase):
    def test_ffmpeg_defaults_are_complete_and_do_not_use_a_shell(self):
        args = build_parser().parse_args([])
        command = ffmpeg_command(args)
        self.assertIn("yuyv422", command)
        self.assertIn("640x480", command)
        self.assertEqual(command[-2:], ["image2pipe", "pipe:1"])

    def test_jpeg_markers_split_across_reads(self):
        parser = JpegParser()
        self.assertEqual(parser.feed(b"noise\xff"), [])
        self.assertEqual(parser.feed(b"\xd8test-frame\xff"), [])
        self.assertEqual(parser.feed(b"\xd9"), [JPEG])

    def test_multiple_frames_in_one_read(self):
        self.assertEqual(JpegParser().feed(JPEG * 3), [JPEG] * 3)

    def test_oversized_and_corrupt_data_are_bounded(self):
        parser = JpegParser(limit=32)
        self.assertEqual(parser.feed(b"\xff\xd8" + b"x" * 100), [])
        self.assertLessEqual(len(parser.buffer), 32)
        self.assertEqual(parser.feed(JPEG), [JPEG])
        parser.feed(b"x" * 10000)
        self.assertLessEqual(len(parser.buffer), 1)

    def test_latest_frame_skips_backlog_and_reports_staleness(self):
        now = [10.0]
        store = FrameStore(clock=lambda: now[0])
        self.assertFalse(store.status()["online"])
        self.assertIsNone(store.latest(timeout=0))
        for i in range(10):
            store.publish(JPEG + bytes([i]))
            now[0] += .1
        self.assertEqual(store.latest(timeout=0)[0], 10)
        self.assertTrue(store.status()["online"])
        self.assertAlmostEqual(store.status()["fps"], 10)
        self.assertIsNone(store.latest(after=10, timeout=0))
        now[0] += 3
        self.assertFalse(store.status()["online"])
        self.assertIsNone(store.latest(timeout=0))

    def test_failure_removes_old_frame_and_recovery_uses_new_id(self):
        store = FrameStore()
        store.publish(JPEG)
        original = store.status()["frame_id"]
        store.fail("capture_disconnected")
        self.assertIsNone(store.latest(timeout=0))
        self.assertFalse(store.status()["online"])
        store.publish(JPEG)
        self.assertTrue(store.status()["online"])
        self.assertNotEqual(original, store.status()["frame_id"])

    def handler(self, path, store):
        handler = object.__new__(CameraHandler)
        handler.path = path
        handler.headers = {"Origin": "http://127.0.0.1:1880"}
        handler.server = SimpleNamespace(frames=store, args=SimpleNamespace(
            width=640, height=480, fps=15, allowed_origin=["http://127.0.0.1:1880"]))
        handler.wfile = BytesIO()
        handler.response_headers = {}
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.send_header = lambda name, value: handler.response_headers.update({name: value})
        handler.end_headers = lambda: None
        handler.send_error = lambda status, *args: setattr(handler, "status", status)
        return handler

    def test_health_and_snapshot_return_real_frame_identity(self):
        store = FrameStore()
        store.publish(JPEG)
        handler = self.handler("/snapshot.jpg", store)
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), JPEG)
        self.assertEqual(handler.response_headers["X-Frame-Id"], store.status()["frame_id"])
        self.assertEqual(handler.response_headers["Content-Length"], str(len(JPEG)))
        self.assertEqual(handler.response_headers["Access-Control-Allow-Origin"], "http://127.0.0.1:1880")
        handler = self.handler("/health", store)
        handler.do_GET()
        self.assertEqual(handler.status, 200)

    def test_no_snapshot_or_healthy_status_when_capture_is_missing(self):
        for route in ("/health", "/snapshot.jpg", "/stream.mjpg"):
            handler = self.handler(route, FrameStore())
            handler.do_GET()
            self.assertEqual(handler.status, 503)


if __name__ == "__main__":
    unittest.main()
