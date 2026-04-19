import os
import re
import glob
import asyncio
import aiohttp
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

import yt_dlp

from pyrogram import enums, types
from py_yt import Playlist, VideosSearch
from Elevenyts import config, logger
from Elevenyts.helpers import Track, utils


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COOKIE FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_cookie_file() -> Optional[str]:
    paths = [
        "Elevenyts/cookies/cookies.txt",
        "anony/cookies/cookies.txt",
        "cookies/cookies.txt",
        "cookies.txt",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  yt-dlp BASE OPTIONS — anti-bot headers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    # Pretend to be a real browser — bypasses most bot detection
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    # Use po_token workaround if available
    "extractor_args": {
        "youtube": {
            "skip": ["hls", "dash"],
            "player_skip": ["js", "configs", "webpage"],
        }
    },
    # Retry on failure
    "retries": 5,
    "fragment_retries": 5,
    "skip_unavailable_fragments": True,
    "ignoreerrors": False,
}


def _build_opts(video_id: str, video: bool, quality: str = "1080") -> dict:
    opts = dict(_BASE_OPTS)
    cookie = _get_cookie_file()
    if cookie:
        opts["cookiefile"] = cookie

    if video:
        opts["format"] = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={quality}]+bestaudio"
            f"/best[height<={quality}]/best"
        )
        opts["outtmpl"]              = f"downloads/{video_id}.%(ext)s"
        opts["merge_output_format"]  = "mp4"
        opts["postprocessor_args"]   = ["-c:v", "copy", "-c:a", "aac"]
    else:
        opts["format"] = "bestaudio/best"
        opts["outtmpl"] = f"downloads/{video_id}.%(ext)s"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]

    return opts


def _build_opts_fallback(video_id: str, video: bool) -> dict:
    """Fallback — use android client which bypasses most restrictions."""
    opts = dict(_BASE_OPTS)
    cookie = _get_cookie_file()
    if cookie:
        opts["cookiefile"] = cookie

    # Android client — no bot detection
    opts["extractor_args"] = {
        "youtube": {"player_client": ["android"]}
    }

    if video:
        opts["format"]              = "best[ext=mp4]/best"
        opts["outtmpl"]             = f"downloads/{video_id}_fb.%(ext)s"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"]  = "bestaudio/best"
        opts["outtmpl"] = f"downloads/{video_id}_fb.%(ext)s"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]

    return opts


def _build_opts_ios(video_id: str, video: bool) -> dict:
    """Last resort — iOS client."""
    opts = dict(_BASE_OPTS)
    cookie = _get_cookie_file()
    if cookie:
        opts["cookiefile"] = cookie

    opts["extractor_args"] = {
        "youtube": {"player_client": ["ios"]}
    }
    opts["format"]  = "best"
    opts["outtmpl"] = f"downloads/{video_id}_ios.%(ext)s"
    return opts


class YouTube:
    def __init__(self):
        self.base    = "https://www.youtube.com/watch?v="
        self.api_url = getattr(config, "YOUTUBE_API_URL", "")

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

        self.search_cache        = {}
        self._download_semaphore = asyncio.Semaphore(3)
        self.AUDIO_QUALITY       = getattr(config, "AUDIO_QUALITY", "320")
        self.VIDEO_QUALITY       = getattr(config, "VIDEO_QUALITY", "1080")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _locate_file(self, video_id: str, video: bool = False) -> Optional[str]:
        # Search for any file starting with video_id
        for pattern in [
            f"downloads/{video_id}.*",
            f"downloads/{video_id}_fb.*",
            f"downloads/{video_id}_ios.*",
        ]:
            candidates = sorted([
                p for p in glob.glob(pattern)
                if not p.endswith((".part", ".ytdl", ".info.json", ".temp"))
                and not os.path.isdir(p)
            ])
            video_exts = {".mp4", ".mkv", ".webm", ".mov"}
            audio_exts = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}

            if video:
                for p in candidates:
                    if Path(p).suffix.lower() in video_exts:
                        return p
            else:
                for p in candidates:
                    if Path(p).suffix.lower() in audio_exts:
                        return p

            if candidates:
                return candidates[0]
        return None

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message_1: types.Message) -> Union[str, None]:
        messages = [message_1]
        link     = None
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""
            if message.entities:
                for entity in message.entities:
                    if entity.type == enums.MessageEntityType.URL:
                        link = text[entity.offset: entity.offset + entity.length]
                        break
            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        link = entity.url
                        break

        if link:
            return link.split("&si")[0].split("?si")[0]
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SEARCH
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def search(self, query: str, m_id: int, video: bool = False) -> Optional[Track]:
        cache_key    = f"{query}_{video}"
        current_time = asyncio.get_running_loop().time()

        if cache_key in self.search_cache:
            cached_result, ts = self.search_cache[cache_key]
            if current_time - ts < 600:
                fresh            = replace(cached_result)
                fresh.message_id = m_id
                fresh.file_path  = None
                fresh.user       = None
                fresh.time       = 0
                fresh.video      = video
                return fresh

        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
        except Exception as e:
            logger.warning(f"⚠️ YouTube search failed for '{query}': {e}")
            return None

        if results and results["result"]:
            data     = results["result"][0]
            duration = data.get("duration")
            is_live  = duration is None or duration == "LIVE"

            track = Track(
                id           = data.get("id"),
                channel_name = data.get("channel", {}).get("name"),
                duration     = duration if not is_live else "LIVE",
                duration_sec = 0 if is_live else utils.to_seconds(duration),
                message_id   = m_id,
                title        = data.get("title")[:25],
                thumbnail    = data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url          = data.get("link"),
                view_count   = data.get("viewCount", {}).get("short"),
                is_live      = is_live,
                video        = video,
            )

            self.search_cache[cache_key] = (track, current_time)
            if len(self.search_cache) > 100:
                oldest = min(self.search_cache, key=lambda k: self.search_cache[k][1])
                del self.search_cache[oldest]

            return replace(track)
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PLAYLIST
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def playlist(self, limit: int, user: str, url: str) -> list:
        try:
            plist = await Playlist.get(url)
            if not plist or "videos" not in plist or not plist["videos"]:
                return []

            tracks = []
            for data in plist["videos"][:limit]:
                try:
                    thumbnails    = data.get("thumbnails", [])
                    thumbnail_url = thumbnails[-1].get("url", "").split("?")[0] if thumbnails else ""
                    link          = data.get("link", "")
                    if "&list=" in link:
                        link = link.split("&list=")[0]

                    track = Track(
                        id           = data.get("id", ""),
                        channel_name = data.get("channel", {}).get("name", ""),
                        duration     = data.get("duration", "0:00"),
                        duration_sec = utils.to_seconds(data.get("duration", "0:00")),
                        title        = data.get("title", "Unknown")[:25],
                        thumbnail    = thumbnail_url,
                        url          = link,
                        user         = user,
                        view_count   = "",
                        is_live      = False,
                        video        = False,
                    )
                    tracks.append(track)
                except Exception:
                    continue
            return tracks

        except KeyError:
            raise Exception("Failed to parse playlist.")
        except Exception:
            raise

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DOWNLOAD — 3 fallback methods
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _yt_download_sync(self, video_id: str, video: bool = False) -> Optional[str]:
        os.makedirs("downloads", exist_ok=True)

        # Check cache
        existing = self._locate_file(video_id, video)
        if existing:
            logger.info(f"[YT] Cache hit: {existing}")
            return existing

        url = self.base + video_id

        # ── Method 1: Normal download with browser headers ─
        logger.info(f"[YT] Trying method 1 (browser headers): {video_id}")
        try:
            opts = _build_opts(video_id, video, self.VIDEO_QUALITY)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            result = self._locate_file(video_id, video)
            if result:
                size_mb = os.path.getsize(result) / (1024 * 1024)
                logger.info(f"✅ Method 1 success: {result} — {size_mb:.1f} MB")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Method 1 failed: {e}")

        # ── Method 2: Android client (bypasses bot detection) ─
        logger.info(f"[YT] Trying method 2 (android client): {video_id}")
        try:
            opts = _build_opts_fallback(video_id, video)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            result = self._locate_file(video_id, video)
            if result:
                size_mb = os.path.getsize(result) / (1024 * 1024)
                logger.info(f"✅ Method 2 success: {result} — {size_mb:.1f} MB")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Method 2 failed: {e}")

        # ── Method 3: iOS client (last resort) ────────────
        logger.info(f"[YT] Trying method 3 (iOS client): {video_id}")
        try:
            opts = _build_opts_ios(video_id, video)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            result = self._locate_file(video_id, video)
            if result:
                size_mb = os.path.getsize(result) / (1024 * 1024)
                logger.info(f"✅ Method 3 success: {result} — {size_mb:.1f} MB")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Method 3 failed: {e}")

        logger.error(f"❌ All methods failed for {video_id}")
        return None

    async def _download_ytdlp(self, video_id: str, video: bool = False) -> Optional[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._yt_download_sync, video_id, video
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LIVE STREAM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _get_live_url(self, video_id: str) -> Optional[str]:
        url  = self.base + video_id
        opts = {
            **_BASE_OPTS,
            "format": "best",
        }
        cookie = _get_cookie_file()
        if cookie:
            opts["cookiefile"] = cookie

        try:
            loop = asyncio.get_event_loop()
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get("url") or info.get("manifest_url")
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.warning(f"⚠️ Live URL extraction failed: {e}")
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PUBLIC DOWNLOAD ENTRY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def download(
        self,
        video_id: str,
        is_live: bool = False,
        video: bool = False
    ) -> Optional[str]:
        if is_live:
            stream_url = await self._get_live_url(video_id)
            return stream_url or (self.base + video_id)

        async with self._download_semaphore:
            return await self._download_ytdlp(video_id, video)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SAVE COOKIES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def save_cookies(self, url: str) -> None:
        try:
            os.makedirs("Elevenyts/cookies", exist_ok=True)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open("Elevenyts/cookies/cookies.txt", "w") as f:
                            f.write(await resp.text())
                        logger.info("[YT] Cookies saved.")
                    else:
                        logger.warning(f"[YT] Cookie fetch failed: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"[YT] Cookie save error: {e}")
        
