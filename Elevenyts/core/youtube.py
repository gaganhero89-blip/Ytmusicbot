import os
import re
import glob
import asyncio
import aiohttp
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from pyrogram import enums, types
from py_yt import Playlist, VideosSearch
from Elevenyts import config, logger
from Elevenyts.helpers import Track, utils


class YouTube:
    def __init__(self):
        """Initialize YouTube handler with API configuration."""
        self.base = "https://www.youtube.com/watch?v="
        self.api_url = config.YOUTUBE_API_URL

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

        self.search_cache = {}
        self.cache_time = {}

        self._download_semaphore = asyncio.Semaphore(5)
        self._max_video_height = getattr(config, "VIDEO_MAX_HEIGHT", 1080)

        # ── Quality settings ──────────────────────────────
        # Audio: highest bitrate available (320kbps / best)
        self.AUDIO_QUALITY = getattr(config, "AUDIO_QUALITY", "best")   # "best" | "320" | "128"
        # Video: max resolution (1080p default, set lower if server is weak)
        self.VIDEO_QUALITY = getattr(config, "VIDEO_QUALITY", "1080")   # "1080" | "720" | "480"

    def _locate_download_file(self, video_id: str, video: bool = False) -> Optional[str]:
        """Locate any completed download file for a video id."""
        pattern = f"downloads/{video_id}*"
        candidates = sorted([
            path for path in glob.glob(pattern)
            if not path.endswith((".part", ".ytdl", ".info.json", ".temp"))
        ])

        video_exts = {".mp4", ".mkv", ".webm", ".mov"}
        audio_exts = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}

        if video:
            for path in candidates:
                if os.path.isdir(path):
                    continue
                if Path(path).suffix.lower() in video_exts:
                    return path
        else:
            for path in candidates:
                if os.path.isdir(path):
                    continue
                if Path(path).suffix.lower() in audio_exts:
                    return path

        for path in candidates:
            if os.path.isdir(path):
                continue
            return path
        return None

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message_1: types.Message) -> Union[str, None]:
        messages = [message_1]
        link = None
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

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        """Search for a video on YouTube."""
        cache_key = f"{query}_{video}"
        current_time = asyncio.get_running_loop().time()

        if cache_key in self.search_cache:
            cached_result, cache_timestamp = self.search_cache[cache_key]
            if current_time - cache_timestamp < 600:
                fresh = replace(cached_result)
                fresh.message_id = m_id
                fresh.file_path = None
                fresh.user = None
                fresh.time = 0
                fresh.video = video
                return fresh

        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
        except Exception as e:
            logger.warning(f"⚠️ YouTube search failed for '{query}': {e}")
            return None

        if results and results["result"]:
            data = results["result"][0]
            duration = data.get("duration")
            is_live = duration is None or duration == "LIVE"

            track = Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=duration if not is_live else "LIVE",
                duration_sec=0 if is_live else utils.to_seconds(duration),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                is_live=is_live,
                video=video,
            )

            self.search_cache[cache_key] = (track, current_time)
            if len(self.search_cache) > 100:
                oldest_key = min(self.search_cache.keys(),
                                 key=lambda k: self.search_cache[k][1])
                del self.search_cache[oldest_key]

            return replace(track)
        return None

    async def playlist(self, limit: int, user: str, url: str) -> list[Track]:
        """Extract playlist tracks."""
        try:
            plist = await Playlist.get(url)
            tracks = []

            if not plist or "videos" not in plist or not plist["videos"]:
                return []

            for data in plist["videos"][:limit]:
                try:
                    thumbnails = data.get("thumbnails", [])
                    thumbnail_url = ""
                    if thumbnails:
                        thumbnail_url = thumbnails[-1].get("url", "").split("?")[0]

                    link = data.get("link", "")
                    if "&list=" in link:
                        link = link.split("&list=")[0]

                    track = Track(
                        id=data.get("id", ""),
                        channel_name=data.get("channel", {}).get("name", ""),
                        duration=data.get("duration", "0:00"),
                        duration_sec=utils.to_seconds(data.get("duration", "0:00")),
                        title=(data.get("title", "Unknown")[:25]),
                        thumbnail=thumbnail_url,
                        url=link,
                        user=user,
                        view_count="",
                        is_live=False,
                        video=False,
                    )
                    tracks.append(track)
                except Exception:
                    continue

            return tracks
        except KeyError:
            raise Exception("Failed to parse playlist. YouTube may have changed their structure.")
        except Exception:
            raise

    async def _download_via_api(self, video_id: str, video: bool = False) -> Optional[str]:
        """
        Download audio/video using external API with BEST quality.

        Audio: requests highest bitrate (320kbps or best available)
        Video: requests highest resolution up to VIDEO_QUALITY setting
        """
        file_type = "video" if video else "audio"
        ext       = "mp4"   if video else "mp3"
        file_path = os.path.join("downloads", f"{video_id}.{ext}")

        if os.path.exists(file_path):
            return file_path

        downloads_dir = Path("downloads")
        if not downloads_dir.exists():
            try:
                downloads_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"❌ Cannot create downloads directory: {e}")
                return None

        # ── Build quality params ──────────────────────────
        # These are passed to the API — most APIs support these params.
        # If your API uses different param names, adjust accordingly.
        quality_params: dict = {"url": video_id, "type": file_type}

        if video:
            # Request best video quality up to configured max (default 1080p)
            quality_params["quality"]    = self.VIDEO_QUALITY   # e.g. "1080"
            quality_params["resolution"] = self.VIDEO_QUALITY   # fallback param name
            quality_params["format"]     = (
                f"bestvideo[height<={self.VIDEO_QUALITY}]+bestaudio"
                f"/bestvideo[height<={self.VIDEO_QUALITY}]/best"
            )
        else:
            # Request best audio quality (320kbps or best available)
            quality_params["quality"]      = self.AUDIO_QUALITY  # "best" or "320"
            quality_params["audio_quality"] = "320"              # kbps hint
            quality_params["format"]        = (
                "bestaudio[abr>=128]/bestaudio/best"
            )

        try:
            async with aiohttp.ClientSession() as session:

                # ── Step 1: Get download token ────────────
                async with session.get(
                    f"{self.api_url}/download",
                    params=quality_params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ API token request failed: HTTP {response.status}")
                        return None

                    data           = await response.json()
                    download_token = data.get("download_token")

                    if not download_token:
                        logger.error("❌ No download token received from API")
                        return None

                # ── Step 2: Stream the file ───────────────
                stream_url = (
                    f"{self.api_url}/stream/{video_id}"
                    f"?type={file_type}&token={download_token}"
                    f"&quality={self.VIDEO_QUALITY if video else self.AUDIO_QUALITY}"
                )

                async with session.get(
                    stream_url,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as file_response:

                    if file_response.status == 302:
                        redirect_url = file_response.headers.get("Location")
                        if redirect_url:
                            async with session.get(redirect_url) as final:
                                if final.status != 200:
                                    logger.error(f"❌ Redirect failed: HTTP {final.status}")
                                    return None
                                with open(file_path, "wb") as f:
                                    async for chunk in final.content.iter_chunked(16384):
                                        f.write(chunk)
                    elif file_response.status == 200:
                        with open(file_path, "wb") as f:
                            async for chunk in file_response.content.iter_chunked(16384):
                                f.write(chunk)
                    else:
                        logger.error(f"❌ Download failed: HTTP {file_response.status}")
                        return None

                # ── Step 3: Verify ────────────────────────
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    logger.info(
                        f"✅ Downloaded {video_id}.{ext} "
                        f"({'video ' + self.VIDEO_QUALITY + 'p' if video else 'audio ' + self.AUDIO_QUALITY + 'kbps'}) "
                        f"— {size_mb:.1f} MB"
                    )
                    return file_path
                else:
                    logger.error(f"❌ Downloaded file is empty: {file_path}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"❌ Download timeout for {video_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Download error for {video_id}: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            return None

    async def download(
        self,
        video_id: str,
        is_live: bool = False,
        video: bool = False
    ) -> Optional[str]:
        """
        Download audio/video with best quality.

        Audio → 320kbps MP3 (or best available)
        Video → up to 1080p MP4 (configurable via VIDEO_QUALITY in config)
        """
        url = self.base + video_id

        if is_live:
            try:
                async with aiohttp.ClientSession() as session:
                    params = {"url": video_id, "type": "live"}
                    async with session.get(
                        f"{self.api_url}/live",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            data       = await response.json()
                            stream_url = data.get("stream_url")
                            if stream_url:
                                return stream_url
            except Exception as e:
                logger.warning(f"⚠️ Failed to get live stream URL: {e}")
            return url

        async with self._download_semaphore:
            return await self._download_via_api(video_id, video)
        
