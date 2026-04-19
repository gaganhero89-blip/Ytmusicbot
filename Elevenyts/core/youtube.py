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
#  yt-dlp OPTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _audio_opts(video_id: str) -> dict:
    """Best audio quality — 320kbps MP3."""
    return {
        "format": "bestaudio/best",
        "outtmpl": f"downloads/{video_id}.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cookiefile": _get_cookie_file(),
    }


def _video_opts(video_id: str, quality: str = "1080") -> dict:
    """Best video quality — up to 1080p MP4, audio+video merged."""
    return {
        # Best video up to quality + best audio, merged into mp4
        "format": (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={quality}]+bestaudio"
            f"/bestvideo[height<={quality}]/best[height<={quality}]/best"
        ),
        "outtmpl": f"downloads/{video_id}.%(ext)s",
        "merge_output_format": "mp4",
        "postprocessor_args": ["-c:v", "copy", "-c:a", "aac"],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cookiefile": _get_cookie_file(),
    }


def _get_cookie_file() -> Optional[str]:
    """Return cookie file path if exists."""
    paths = [
        "Elevenyts/cookies/cookies.txt",
        "cookies/cookies.txt",
        "cookies.txt",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


class YouTube:
    def __init__(self):
        self.base    = "https://www.youtube.com/watch?v="
        self.api_url = getattr(config, "YOUTUBE_API_URL", "")

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

        self.search_cache = {}
        self._download_semaphore = asyncio.Semaphore(3)

        # Quality settings (override in config if needed)
        self.AUDIO_QUALITY = getattr(config, "AUDIO_QUALITY", "320")
        self.VIDEO_QUALITY = getattr(config, "VIDEO_QUALITY", "1080")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _locate_download_file(self, video_id: str, video: bool = False) -> Optional[str]:
        pattern    = f"downloads/{video_id}*"
        candidates = sorted([
            p for p in glob.glob(pattern)
            if not p.endswith((".part", ".ytdl", ".info.json", ".temp"))
        ])
        video_exts = {".mp4", ".mkv", ".webm", ".mov"}
        audio_exts = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}

        if video:
            for p in candidates:
                if not os.path.isdir(p) and Path(p).suffix.lower() in video_exts:
                    return p
        else:
            for p in candidates:
                if not os.path.isdir(p) and Path(p).suffix.lower() in audio_exts:
                    return p

        for p in candidates:
            if not os.path.isdir(p):
                return p
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
    #  DOWNLOAD — yt-dlp direct (best quality)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _yt_download_sync(self, video_id: str, video: bool = False) -> Optional[str]:
        """
        Synchronous yt-dlp download — runs in executor.
        Audio: 320kbps MP3
        Video: best quality up to VIDEO_QUALITY (default 1080p) merged MP4
        """
        os.makedirs("downloads", exist_ok=True)

        # Check cache first
        existing = self._locate_download_file(video_id, video)
        if existing:
            logger.info(f"[YT] Cache hit: {existing}")
            return existing

        url  = self.base + video_id
        opts = _video_opts(video_id, self.VIDEO_QUALITY) if video else _audio_opts(video_id)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            # Find downloaded file
            result = self._locate_download_file(video_id, video)
            if result:
                size_mb = os.path.getsize(result) / (1024 * 1024)
                logger.info(
                    f"✅ Downloaded: {result} "
                    f"({'video ' + self.VIDEO_QUALITY + 'p' if video else 'audio 320kbps'}) "
                    f"— {size_mb:.1f} MB"
                )
                return result
            else:
                logger.error(f"❌ yt-dlp finished but file not found for {video_id}")
                return None

        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "Sign in" in err or "bot" in err.lower():
                logger.error(f"❌ YouTube bot detection for {video_id} — update cookies!")
            else:
                logger.error(f"❌ yt-dlp DownloadError for {video_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Download error for {video_id}: {e}")
            return None

    async def _download_ytdlp(self, video_id: str, video: bool = False) -> Optional[str]:
        """Run yt-dlp download in thread executor (non-blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._yt_download_sync,
            video_id,
            video
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LIVE STREAM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _get_live_url(self, video_id: str) -> Optional[str]:
        """Extract live stream URL using yt-dlp."""
        url  = self.base + video_id
        opts = {
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "cookiefile": _get_cookie_file(),
        }
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
        """
        Main download function.
        Audio  → 320kbps MP3 via yt-dlp
        Video  → best quality up to 1080p MP4 via yt-dlp
        Live   → direct stream URL
        """
        if is_live:
            stream_url = await self._get_live_url(video_id)
            return stream_url or (self.base + video_id)

        async with self._download_semaphore:
            return await self._download_ytdlp(video_id, video)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  COOKIES (original method preserved)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def save_cookies(self, url: str) -> None:
        """Download and save cookies from URL."""
        try:
            os.makedirs("Elevenyts/cookies", exist_ok=True)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        cookie_data = await resp.text()
                        with open("Elevenyts/cookies/cookies.txt", "w") as f:
                            f.write(cookie_data)
                        logger.info("[YT] Cookies saved in Elevenyts/cookies.")
                    else:
                        logger.warning(f"[YT] Failed to fetch cookies: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"[YT] Cookie save error: {e}")
                
