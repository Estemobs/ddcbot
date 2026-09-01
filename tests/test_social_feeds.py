import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest

from social_feeds import (
    FeedItem, KINDS, extract_youtube_channel_id, feed_url, new_items,
    parse_atom, parse_feed, parse_kick, parse_rss,
)

# Extraits reels, tronques : YouTube et Reddit servent tous deux de l'Atom.
YOUTUBE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>MrBeast</title>
  <entry>
    <id>yt:video:5mU6SRS2Bxo</id>
    <yt:videoId>5mU6SRS2Bxo</yt:videoId>
    <title>World's Largest Tennis Match</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=5mU6SRS2Bxo"/>
    <author><name>MrBeast</name></author>
    <published>2026-08-23T16:00:04+00:00</published>
    <media:group>
      <media:thumbnail url="https://i2.ytimg.com/vi/5mU6SRS2Bxo/hqdefault.jpg"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:AAAAAAAAAAA</id>
    <yt:videoId>AAAAAAAAAAA</yt:videoId>
    <title>Video precedente</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=AAAAAAAAAAA"/>
    <author><name>MrBeast</name></author>
    <published>2026-08-16T16:00:04+00:00</published>
  </entry>
</feed>
"""

REDDIT_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Nouveautes de r/france</title>
  <entry>
    <id>t3_1abcdef</id>
    <title>Un titre de post</title>
    <link href="https://www.reddit.com/r/france/comments/1abcdef/un_titre/"/>
    <author><name>/u/quelquun</name></author>
    <updated>2026-08-31T10:00:00+00:00</updated>
  </entry>
</feed>
"""

PODCAST_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Darknet Diaries</title>
    <item>
      <guid>prx_7057_82aaba05</guid>
      <title>179: The Courthouse</title>
      <link>https://darknetdiaries.com/episode/179/</link>
      <pubDate>Tue, 05 Aug 2026 07:00:00 -0000</pubDate>
      <itunes:image href="https://cdn/cover.jpg"/>
    </item>
    <item>
      <guid>prx_7056_aaaa</guid>
      <title>178: Un autre</title>
      <link>https://darknetdiaries.com/episode/178/</link>
      <pubDate>Tue, 01 Jul 2026 07:00:00 -0000</pubDate>
    </item>
  </channel>
</rss>
"""

KICK_LIVE = {
    "slug": "otplol", "user": {"username": "OTPLOL"},
    "livestream": {"id": 12345, "session_title": "LCK finale", "is_live": True,
                   "viewer_count": 6950, "thumbnail": {"url": "https://cdn/thumb.jpg"},
                   "start_time": "2026-08-31 10:00:00"},
}
KICK_OFFLINE = {"slug": "xqc", "user": {"username": "xQc"}, "livestream": None}


class TestFeedUrls(unittest.TestCase):
    def test_youtube_uses_the_official_atom_feed(self):
        self.assertEqual(
            feed_url("youtube", "UCX6OQ3DkcsbYNE6H8uQQuVA"),
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA",
        )

    def test_reddit_uses_rss_not_json(self):
        """Le .json de Reddit renvoie 403 depuis un hebergeur, le flux RSS non."""
        url = feed_url("reddit", "france")
        self.assertIn("/r/france/new.rss", url)
        self.assertNotIn(".json", url)

    def test_reddit_accepts_the_r_prefix(self):
        self.assertEqual(feed_url("reddit", "r/france"), feed_url("reddit", "france"))

    def test_kick_is_lowercased(self):
        self.assertEqual(feed_url("kick", "XQc"), "https://kick.com/api/v2/channels/xqc")

    def test_rss_is_passed_through(self):
        self.assertEqual(feed_url("rss", "https://exemple/flux.xml"), "https://exemple/flux.xml")


class TestYoutubeChannelId(unittest.TestCase):
    def test_a_plain_id_is_returned(self):
        self.assertEqual(
            extract_youtube_channel_id("UCX6OQ3DkcsbYNE6H8uQQuVA"),
            "UCX6OQ3DkcsbYNE6H8uQQuVA",
        )

    def test_id_is_read_from_the_channel_page(self):
        page = '<link rel="alternate" href="...channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA">'
        self.assertEqual(extract_youtube_channel_id(page), "UCX6OQ3DkcsbYNE6H8uQQuVA")

    def test_recommended_channels_do_not_win(self):
        """"channelId" apparait aussi pour les videos recommandees, souvent avant."""
        page = ('{"channelId":"UCAiLfjNXkNv24uhpzUgPa6A"}'
                '...channel_id=UCX6OQ3DkcsbYNE6H8uQQuVA')
        self.assertEqual(extract_youtube_channel_id(page), "UCX6OQ3DkcsbYNE6H8uQQuVA")

    def test_external_id_is_used_as_fallback(self):
        self.assertEqual(
            extract_youtube_channel_id('{"externalId":"UCBJycsmduvYEL83R_U4JriQ"}'),
            "UCBJycsmduvYEL83R_U4JriQ",
        )

    def test_no_id_found(self):
        self.assertIsNone(extract_youtube_channel_id("page sans identifiant"))
        self.assertIsNone(extract_youtube_channel_id(""))
        self.assertIsNone(extract_youtube_channel_id(None))


class TestAtom(unittest.TestCase):
    def test_youtube_entries_are_parsed(self):
        items = parse_atom(YOUTUBE_ATOM)
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.uid, "5mU6SRS2Bxo")
        self.assertEqual(first.title, "World's Largest Tennis Match")
        self.assertEqual(first.url, "https://www.youtube.com/watch?v=5mU6SRS2Bxo")
        self.assertEqual(first.author, "MrBeast")
        self.assertTrue(first.thumbnail.endswith("hqdefault.jpg"))

    def test_reddit_entries_are_parsed_by_the_same_code(self):
        items = parse_atom(REDDIT_ATOM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].uid, "t3_1abcdef")
        self.assertEqual(items[0].title, "Un titre de post")
        self.assertIn("reddit.com", items[0].url)

    def test_entries_are_most_recent_first(self):
        items = parse_atom(YOUTUBE_ATOM)
        self.assertEqual([i.uid for i in items], ["5mU6SRS2Bxo", "AAAAAAAAAAA"])


class TestRss(unittest.TestCase):
    def test_podcast_items_are_parsed(self):
        items = parse_rss(PODCAST_RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].uid, "prx_7057_82aaba05")
        self.assertEqual(items[0].title, "179: The Courthouse")
        self.assertEqual(items[0].thumbnail, "https://cdn/cover.jpg")

    def test_author_falls_back_to_the_channel_title(self):
        self.assertEqual(parse_rss(PODCAST_RSS)[0].author, "Darknet Diaries")


class TestParseFeedDispatch(unittest.TestCase):
    def test_atom_and_rss_are_both_recognised(self):
        self.assertEqual(len(parse_feed(YOUTUBE_ATOM)), 2)
        self.assertEqual(len(parse_feed(PODCAST_RSS)), 2)

    def test_garbage_yields_no_items(self):
        for body in ("", "pas du xml", "<html><body>404</body></html>"):
            with self.subTest(body=body[:12]):
                self.assertEqual(parse_feed(body), [])


class TestKick(unittest.TestCase):
    def test_live_channel(self):
        item = parse_kick(KICK_LIVE)
        self.assertIsNotNone(item)
        self.assertEqual(item.uid, "12345")
        self.assertEqual(item.title, "LCK finale")
        self.assertEqual(item.url, "https://kick.com/otplol")
        self.assertEqual(item.thumbnail, "https://cdn/thumb.jpg")

    def test_offline_channel_yields_none(self):
        self.assertIsNone(parse_kick(KICK_OFFLINE))

    def test_is_live_false_yields_none(self):
        payload = dict(KICK_LIVE)
        payload["livestream"] = dict(KICK_LIVE["livestream"], is_live=False)
        self.assertIsNone(parse_kick(payload))

    def test_garbage_yields_none(self):
        self.assertIsNone(parse_kick(None))
        self.assertIsNone(parse_kick("pas un dict"))
        self.assertIsNone(parse_kick({}))


class TestNewItems(unittest.TestCase):
    """Ce qui evite d'inonder un salon a l'ajout d'une source."""

    def setUp(self):
        self.items = parse_atom(YOUTUBE_ATOM)

    def test_first_run_announces_nothing(self):
        self.assertEqual(new_items(self.items, None), [])

    def test_nothing_new_when_the_marker_is_the_latest(self):
        self.assertEqual(new_items(self.items, "5mU6SRS2Bxo"), [])

    def test_only_items_after_the_marker(self):
        fresh = new_items(self.items, "AAAAAAAAAAA")
        self.assertEqual([i.uid for i in fresh], ["5mU6SRS2Bxo"])

    def test_oldest_first_so_the_channel_reads_chronologically(self):
        items = [FeedItem("c"), FeedItem("b"), FeedItem("a")]
        self.assertEqual([i.uid for i in new_items(items, "a")], ["b", "c"])

    def test_burst_is_capped(self):
        items = [FeedItem(str(i)) for i in range(20)]
        self.assertEqual(len(new_items(items, "19", limit=3)), 3)

    def test_unknown_marker_is_capped_too(self):
        """Marqueur disparu du flux : on ne rejoue pas tout l'historique."""
        items = [FeedItem(str(i)) for i in range(20)]
        self.assertEqual(len(new_items(items, "inconnu")), 3)

    def test_empty_feed(self):
        self.assertEqual(new_items([], "a"), [])


class TestKinds(unittest.TestCase):
    def test_all_kinds_have_a_url_builder(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertTrue(feed_url(kind, "cible"))


if __name__ == "__main__":
    unittest.main()
