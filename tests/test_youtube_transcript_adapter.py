import unittest

from src.browser_engine.platform_adapters import (
    YoutubeTranscriptAdapter,
    default_registry,
)


class FakeTranscriptFetcher:
    def __init__(self, responses):
        self.responses = responses  # video_id -> list of snippet strings (or None)
        self.calls = []

    def __call__(self, video_id, languages=("en",)):
        self.calls.append((video_id, tuple(languages)))
        return self.responses.get(video_id)


class TestYoutubeTranscriptAdapter(unittest.TestCase):
    def test_can_handle_watch_shorts_embed_urls(self):
        a = YoutubeTranscriptAdapter()
        self.assertTrue(a.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(a.can_handle("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(a.can_handle("https://www.youtube.com/shorts/dQw4w9WgXcQ"))
        self.assertTrue(a.can_handle("https://www.youtube.com/embed/dQw4w9WgXcQ"))
        self.assertFalse(a.can_handle("https://vimeo.com/22439234"))
        self.assertFalse(a.can_handle("https://www.npmjs.com/package/x"))

    def test_extract_video_id(self):
        self.assertEqual(YoutubeTranscriptAdapter().extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30"), "dQw4w9WgXcQ")
        self.assertEqual(YoutubeTranscriptAdapter().extract_video_id(
            "https://youtu.be/dQw4w9WgXcQ?t=2"), "dQw4w9WgXcQ")
        self.assertIsNone(YoutubeTranscriptAdapter().extract_video_id(
            "https://www.youtube.com/watch"))

    def test_fetch_returns_markdown_transcript(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        fetch = FakeTranscriptFetcher({"dQw4w9WgXcQ": ["hello world", "second line"]})
        res = YoutubeTranscriptAdapter(fetcher=fetch).fetch(url, None)
        self.assertIsNotNone(res)
        self.assertEqual(res.adapter, "youtube-transcript")
        self.assertIn("hello world", res.markdown)
        self.assertIn("second line", res.markdown)
        self.assertEqual(res.metadata.get("video_id"), "dQw4w9WgXcQ")
        self.assertEqual(res.metadata.get("segments"), 2)

    def test_missing_transcript_returns_none_to_fall_through(self):
        url = "https://www.youtube.com/watch?v=zzzzzzzzzzz"
        fetch = FakeTranscriptFetcher({})  # no transcript -> None
        self.assertIsNone(YoutubeTranscriptAdapter(fetcher=fetch).fetch(url, None))

    def test_empty_transcript_returns_none(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        fetch = FakeTranscriptFetcher({"dQw4w9WgXcQ": []})
        self.assertIsNone(YoutubeTranscriptAdapter(fetcher=fetch).fetch(url, None))


class TestRegistryYoutubeFirst(unittest.TestCase):
    def test_youtube_transcript_before_oembed(self):
        names = [a.name for a in default_registry().adapters]
        self.assertEqual(names, ["npm", "github", "youtube-transcript", "oembed", "rss", "reddit-oauth", "wayback"])

    def test_youtube_url_routes_to_transcript_adapter(self):
        reg = default_registry()
        self.assertEqual(
            reg.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ").name,
            "youtube-transcript")


if __name__ == "__main__":
    unittest.main()
