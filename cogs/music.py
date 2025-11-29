# cogs/music.py
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
import os
import platform
import pathlib

# --- FFmpeg Path Logic ---
project_root = pathlib.Path(__file__).parent.parent
ffmpeg_folder_name = "ffmpeg"
if platform.system() == "Windows":
    ffmpeg_executable_name = "ffmpeg.exe"
else:
    ffmpeg_executable_name = "ffmpeg"

ffmpeg_path_in_bin = project_root / ffmpeg_folder_name / "bin" / ffmpeg_executable_name
ffmpeg_path_direct = project_root / ffmpeg_folder_name / ffmpeg_executable_name

FFMPEG_EXECUTABLE_PATH = None
if ffmpeg_path_in_bin.is_file():
    FFMPEG_EXECUTABLE_PATH = str(ffmpeg_path_in_bin)
elif ffmpeg_path_direct.is_file():
    FFMPEG_EXECUTABLE_PATH = str(ffmpeg_path_direct)

logger = logging.getLogger(__name__)

if FFMPEG_EXECUTABLE_PATH:
    logger.info(f"Using FFmpeg executable at: {FFMPEG_EXECUTABLE_PATH}")
else:
    logger.warning("FFmpeg not found in project. Falling back to system PATH.")
    FFMPEG_EXECUTABLE_PATH = "ffmpeg"

# --- Suppress bug reports ---
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
    # 'cookiefile': 'cookies.txt',
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current_song = {}
        self.loop_queue = {}
        self.loop_song = {}

    def _initialize_guild_state(self, guild_id):
        self.queues[guild_id] = asyncio.Queue()
        self.current_song[guild_id] = None
        self.loop_queue[guild_id] = False
        self.loop_song[guild_id] = False

    def _ensure_guild_state_exists(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
        if guild_id not in self.current_song:
            self.current_song[guild_id] = None
        if guild_id not in self.loop_queue:
            self.loop_queue[guild_id] = False
        if guild_id not in self.loop_song:
            self.loop_song[guild_id] = False

    async def _ensure_voice_client(
        self, ctx: commands.Context
    ) -> discord.VoiceClient | None:
        guild_id = ctx.guild.id
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be connected to a voice channel.")
            return None

        user_channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client

        try:
            if vc is None:
                vc = await user_channel.connect(timeout=30.0)
                self._initialize_guild_state(guild_id)
            elif not vc.is_connected():
                try:
                    await vc.move_to(user_channel)
                except asyncio.TimeoutError:
                    vc = await user_channel.connect(reconnect=True, timeout=30.0)
                self._ensure_guild_state_exists(guild_id)
            elif vc.channel != user_channel:
                await vc.move_to(user_channel)
                self._ensure_guild_state_exists(guild_id)

            self._ensure_guild_state_exists(guild_id)
            return vc

        except asyncio.TimeoutError:
            await ctx.send("Connection timed out.")
            await self._cleanup(guild_id)
            return None
        except Exception as e:
            await ctx.send(f"Connection error: {e}")
            await self._cleanup(guild_id)
            return None

    async def _get_song_info(self, query):
        loop = asyncio.get_event_loop()
        try:
            if not query.startswith("http"):
                query = f"ytsearch:{query}"

            data = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(
                    query, download=False
                ),
            )

            if "entries" in data:
                data = data["entries"][0]

            if not data:
                logger.warning("yt-dlp returned no data.")
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

    def _play_next(self, ctx):
        guild_id = ctx.guild.id
        vc = ctx.guild.voice_client

        if not vc or not vc.is_connected():
            asyncio.run_coroutine_threadsafe(self._cleanup(guild_id), self.bot.loop)
            return

        current = self.current_song.get(guild_id)
        next_song = None

        if self.loop_song.get(guild_id, False) and current:
            next_song = current
        elif self.loop_queue.get(guild_id, False) and current:
            asyncio.run_coroutine_threadsafe(
                self.queues[guild_id].put(current), self.bot.loop
            )

        if not next_song:
            if not self.queues[guild_id].empty():
                try:
                    next_song = self.queues[guild_id].get_nowait()
                    self.queues[guild_id].task_done()
                except asyncio.QueueEmpty:
                    pass
            else:
                self.current_song[guild_id] = None
                return

        if next_song:
            try:
                self.current_song[guild_id] = next_song
                source = discord.FFmpegPCMAudio(
                    next_song["source"],
                    executable=FFMPEG_EXECUTABLE_PATH,
                    **FFMPEG_OPTIONS,
                )
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))

                embed = self._create_now_playing_embed(next_song)
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)
            except Exception as e:
                logger.error(f"Playback error: {e}")
                self._play_next(ctx)

    def play_next_after_error(self, error, ctx):
        if error:
            logger.error(f"Playback error in callback: {error}")
        if not self.loop_song.get(ctx.guild.id, False):
            self.current_song[ctx.guild.id] = None
        self._play_next(ctx)

    async def _cleanup(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            await guild.voice_client.disconnect(force=True)
        self.queues.pop(guild_id, None)
        self.current_song.pop(guild_id, None)
        self.loop_queue.pop(guild_id, None)
        self.loop_song.pop(guild_id, None)

    def _create_now_playing_embed(self, song, title_prefix="Now Playing"):
        embed = discord.Embed(
            title=f"{title_prefix} 🎵",
            description=f"[{song['title']}]({song['webpage_url']})",
            color=discord.Color.blue(),
        )
        if song.get("thumbnail"):
            embed.set_thumbnail(url=song["thumbnail"])
        if song.get("requester"):
            embed.add_field(name="Requested by", value=song["requester"].mention)
        return embed

    def _create_queue_embed(self, ctx):
        guild_id = ctx.guild.id
        queue_list = list(self.queues.get(guild_id, asyncio.Queue())._queue)
        current = self.current_song.get(guild_id)

        if not current and not queue_list:
            return discord.Embed(
                description="Queue is empty.", color=discord.Color.greyple()
            )

        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())
        if current:
            req = (
                f" (Req: {current['requester'].mention})"
                if current.get("requester")
                else ""
            )
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{current['title']}]({current['webpage_url']}){req}",
                inline=False,
            )

        if queue_list:
            txt = ""
            for i, s in enumerate(queue_list[:10], 1):
                req = f" ({s['requester'].mention})" if s.get("requester") else ""
                txt += f"`{i}.` {s['title']}{req}\n"
            if len(queue_list) > 10:
                txt += f"\n...and {len(queue_list)-10} more"
            embed.add_field(name="Upcoming", value=txt, inline=False)

        footer = []
        if self.loop_queue.get(guild_id):
            footer.append("Queue Loop: ON")
        if self.loop_song.get(guild_id):
            footer.append("Song Loop: ON")
        embed.set_footer(
            text=" | ".join(footer) if footer else f"Songs: {len(queue_list)}"
        )
        return embed

    # --- Events ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Triggered when a user joins/leaves/moves."""

        # FIX: Handle bot self-disconnect correctly (using member.guild.id)
        if member.id == self.bot.user.id and before.channel and not after.channel:
            await self._cleanup(member.guild.id)
            return

        # Auto-Leave Logic (If bot is left alone)
        if before.channel is not None:
            guild = before.channel.guild
            vc = guild.voice_client

            if vc and vc.channel == before.channel:
                humans = [m for m in vc.channel.members if not m.bot]

                if not humans:
                    logger.info(f"Bot is alone in {vc.channel.name}. Waiting 60s...")
                    await asyncio.sleep(60)

                    vc = guild.voice_client
                    if vc and vc.is_connected() and vc.channel == before.channel:
                        humans_now = [m for m in vc.channel.members if not m.bot]
                        if not humans_now:
                            logger.info("Still alone. Disconnecting.")
                            await self._cleanup(guild.id)
                        else:
                            logger.info("Someone rejoined. Cancelling disconnect.")

    # --- Commands ---

    @commands.command(name="join", aliases=["connect"])
    async def join(self, ctx):
        vc = await self._ensure_voice_client(ctx)
        if vc:
            await ctx.send(f"Joined {vc.channel.name}!")

    @commands.command(name="leave", aliases=["dc"])
    async def leave(self, ctx):
        await self._cleanup(ctx.guild.id)
        await ctx.send("Disconnected.")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        vc = await self._ensure_voice_client(ctx)
        if not vc:
            return

        async with ctx.typing():
            song = await self._get_song_info(query)
            if not song:
                await ctx.send(
                    "Could not find song (or blocked by YouTube). Check logs."
                )
                return
            song["requester"] = ctx.author

        guild_id = ctx.guild.id
        if vc.is_playing() or vc.is_paused():
            self._ensure_guild_state_exists(guild_id)
            await self.queues[guild_id].put(song)
            embed = discord.Embed(
                title="Added to Queue",
                description=song["title"],
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)
        else:
            self._ensure_guild_state_exists(guild_id)
            self.current_song[guild_id] = song
            try:
                source = discord.FFmpegPCMAudio(
                    song["source"], executable=FFMPEG_EXECUTABLE_PATH, **FFMPEG_OPTIONS
                )
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))
                await ctx.send(embed=self._create_now_playing_embed(song))
            except Exception as e:
                logger.error(f"Play error: {e}")
                await ctx.send("Error starting playback.")

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.loop_song[ctx.guild.id] = False
            vc.stop()
            # REMOVED: await ctx.send("Skipped.") as requested

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx):
        self._ensure_guild_state_exists(ctx.guild.id)
        await ctx.send(embed=self._create_queue_embed(ctx))

    @commands.command(name="stop")
    async def stop(self, ctx):
        vc = ctx.guild.voice_client
        if vc:
            self.queues[ctx.guild.id] = asyncio.Queue()
            self.current_song[ctx.guild.id] = None
            vc.stop()
            await ctx.send("Stopped and cleared.")

    @commands.command(name="loop")
    async def loop(self, ctx):
        """Toggle Queue Loop"""
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_queue[ctx.guild.id] = not self.loop_queue[ctx.guild.id]
        if self.loop_queue[ctx.guild.id]:
            self.loop_song[ctx.guild.id] = False
        await ctx.send(
            f"Queue loop: {'ON' if self.loop_queue[ctx.guild.id] else 'OFF'}"
        )

    @commands.command(name="loopsong")
    async def loopsong(self, ctx):
        """Toggle Current Song Loop"""
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_song[ctx.guild.id] = not self.loop_song[ctx.guild.id]
        if self.loop_song[ctx.guild.id]:
            self.loop_queue[ctx.guild.id] = False
        await ctx.send(f"Song loop: {'ON' if self.loop_song[ctx.guild.id] else 'OFF'}")


async def setup(bot):
    await bot.add_cog(Music(bot))
    logger.info("Music Cog Loaded")
