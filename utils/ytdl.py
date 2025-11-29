# utils/ytdl.py
import yt_dlp
import asyncio
import logging
import pathlib
import platform
import discord
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)

# --- FFmpeg Path Logic ---
project_root = pathlib.Path(__file__).parent.parent
ffmpeg_folder_name = "ffmpeg"
if platform.system() == "Windows":
    ffmpeg_executable_name = "ffmpeg.exe"
else:
    ffmpeg_executable_name = "ffmpeg"

ffmpeg_path_in_bin = project_root / ffmpeg_folder_name / "bin" / ffmpeg_executable_name
ffmpeg_path_direct = project_root / ffmpeg_folder_name / ffmpeg_executable_name

FFMPEG_EXECUTABLE_PATH = "ffmpeg"  # Default fallback
if ffmpeg_path_in_bin.is_file():
    FFMPEG_EXECUTABLE_PATH = str(ffmpeg_path_in_bin)
elif ffmpeg_path_direct.is_file():
    FFMPEG_EXECUTABLE_PATH = str(ffmpeg_path_direct)

# --- Configuration ---
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class YTDLSource:
    @staticmethod
    def sanitize_url(url):
        """
        Cleans YouTube URLs to remove playlist parameters if a specific video is present.
        """
        try:
            parsed = urlparse(url)
            if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
                query = parse_qs(parsed.query)
                if "v" in query:
                    new_query = urlencode({"v": query["v"][0]})
                    new_url = urlunparse(
                        (
                            parsed.scheme,
                            parsed.netloc,
                            parsed.path,
                            parsed.params,
                            new_query,
                            parsed.fragment,
                        )
                    )
                    logger.info(f"Sanitized URL: {new_url}")
                    return new_url
        except Exception as e:
            logger.warning(f"URL sanitization failed: {e}")
        return url

    @classmethod
    async def get_song_info(cls, query, loop=None):
        """Uses yt-dlp to fetch info."""
        loop = loop or asyncio.get_event_loop()
        try:
            if query.startswith("http"):
                query = cls.sanitize_url(query)
            else:
                query = f"ytsearch:{query}"

            logger.info(f"Processing query: {query}")

            data = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(
                    query, download=False
                ),
            )

            if "entries" in data:
                data = data["entries"][0]

            if not data:
                return None

            return {
                "source": data["url"],
                "title": data.get("title", "Unknown Title"),
                "webpage_url": data.get("webpage_url", ""),
                "thumbnail": data.get("thumbnail"),
                "duration": data.get("duration"),
                "requester": None,
            }
        except Exception as e:
            logger.error(f"yt-dlp processing error: {e}")
            return None

    @staticmethod
    def create_source(url):
        """Creates the FFmpeg audio source with volume control."""
        source = discord.FFmpegPCMAudio(
            url, executable=FFMPEG_EXECUTABLE_PATH, **FFMPEG_OPTIONS
        )
        # Wrap in PCMVolumeTransformer to enable volume changing
        return discord.PCMVolumeTransformer(source, volume=0.5)
