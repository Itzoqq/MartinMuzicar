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
# Determines the correct path for the FFmpeg executable based on the OS.
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

# --- Configuration ---
# Suppress noisy bug reports from yt_dlp
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


class Music(commands.Cog):
    """
    Music Cog: Handles all music-related commands (play, skip, queue, etc.).
    """

    def __init__(self, bot):
        self.bot = bot
        # Dictionaries to store state per guild (server)
        self.queues = {}
        self.current_song = {}
        self.loop_queue = {}
        self.loop_song = {}

    def _initialize_guild_state(self, guild_id):
        """Initializes empty state variables for a specific guild."""
        self.queues[guild_id] = asyncio.Queue()
        self.current_song[guild_id] = None
        self.loop_queue[guild_id] = False
        self.loop_song[guild_id] = False

    def _ensure_guild_state_exists(self, guild_id):
        """Ensures that state dictionaries have entries for the guild to prevent KeyErrors."""
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
        """
        Connects the bot to the user's voice channel.
        Handles moving channels, reconnection logic, and permission errors.

        Returns:
            discord.VoiceClient or None if connection failed.
        """
        guild_id = ctx.guild.id

        # Check if user is in a channel
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You must be connected to a voice channel first.")
            return None

        user_channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client

        try:
            # Case 1: Bot is not connected anywhere
            if vc is None:
                vc = await user_channel.connect(timeout=30.0)
                self._initialize_guild_state(guild_id)

            # Case 2: Bot is connected but maybe in a weird state or different channel
            elif not vc.is_connected():
                try:
                    await vc.move_to(user_channel)
                except asyncio.TimeoutError:
                    # Attempt full reconnect
                    vc = await user_channel.connect(reconnect=True, timeout=30.0)
                self._ensure_guild_state_exists(guild_id)

            # Case 3: Bot is connected to a different channel
            elif vc.channel != user_channel:
                await vc.move_to(user_channel)
                self._ensure_guild_state_exists(guild_id)

            # Final state check
            self._ensure_guild_state_exists(guild_id)
            return vc

        except asyncio.TimeoutError:
            logger.error(f"Timeout while connecting to voice in guild {guild_id}")
            await ctx.send("⏱️ Connection timed out. Please try again.")
            await self._cleanup(guild_id)
            return None

        except discord.Forbidden:
            logger.error(
                f"Missing permissions to join {user_channel.name} in guild {guild_id}"
            )
            await ctx.send("⛔ I don't have permission to join your voice channel.")
            return None

        except Exception as e:
            logger.error(f"Unexpected connection error in guild {guild_id}: {e}")
            await ctx.send(f"An unexpected connection error occurred: {e}")
            await self._cleanup(guild_id)
            return None

    async def _get_song_info(self, query):
        """
        Uses yt-dlp to fetch audio stream information for a given query (URL or search term).
        Running in an executor to prevent blocking the bot's event loop.
        """
        loop = asyncio.get_event_loop()
        try:
            # If not a URL, treat as a search query
            if not query.startswith("http"):
                query = f"ytsearch:{query}"

            logger.info(f"Processing query: {query}")

            # Run blocking code in executor
            data = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(
                    query, download=False
                ),
            )

            # Handle search results (take the first result)
            if "entries" in data:
                data = data["entries"][0]

            if not data:
                logger.warning("yt-dlp returned no data for query.")
                return None

            # Extract relevant fields
            return {
                "source": data["url"],
                "title": data.get("title", "Unknown Title"),
                "webpage_url": data.get("webpage_url", ""),
                "thumbnail": data.get("thumbnail"),
                "duration": data.get("duration"),
                "requester": None,  # Will be set in the command
            }
        except Exception as e:
            logger.error(f"yt-dlp processing error: {e}")
            return None

    def _play_next(self, ctx):
        """
        Logic for playing the next song in the queue.
        Handles looping logic and cleans up if the queue is empty.
        """
        guild_id = ctx.guild.id
        vc = ctx.guild.voice_client

        if not vc or not vc.is_connected():
            logger.info(f"Voice client disconnected in {guild_id}, cleaning up.")
            asyncio.run_coroutine_threadsafe(self._cleanup(guild_id), self.bot.loop)
            return

        current = self.current_song.get(guild_id)
        next_song = None

        # Logic for Song Loop
        if self.loop_song.get(guild_id, False) and current:
            next_song = current

        # Logic for Queue Loop (Re-add current song to back of queue)
        elif self.loop_queue.get(guild_id, False) and current:
            asyncio.run_coroutine_threadsafe(
                self.queues[guild_id].put(current), self.bot.loop
            )

        # Retrieve next song if not looping the specific song
        if not next_song:
            if not self.queues[guild_id].empty():
                try:
                    next_song = self.queues[guild_id].get_nowait()
                    self.queues[guild_id].task_done()
                except asyncio.QueueEmpty:
                    pass
            else:
                # Queue empty
                self.current_song[guild_id] = None
                return

        # Attempt to play the song
        if next_song:
            try:
                self.current_song[guild_id] = next_song

                # Fallback: Ensure executable path is valid
                exe_path = (
                    FFMPEG_EXECUTABLE_PATH if FFMPEG_EXECUTABLE_PATH else "ffmpeg"
                )

                source = discord.FFmpegPCMAudio(
                    next_song["source"],
                    executable=exe_path,
                    **FFMPEG_OPTIONS,
                )

                # The 'after' callback triggers when the song ends or errors
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))

                # Send "Now Playing" embed
                embed = self._create_now_playing_embed(next_song)
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)

                logger.info(f"Playing song: {next_song['title']} in {guild_id}")

            except Exception as e:
                logger.error(f"Playback error in _play_next: {e}")
                # Try next song if this one fails
                self._play_next(ctx)

    def play_next_after_error(self, error, ctx):
        """Callback function used by Discord's voice client when audio finishes."""
        if error:
            logger.error(f"Playback error in callback: {error}")

        # If not looping single song, clear current so we can grab next
        if not self.loop_song.get(ctx.guild.id, False):
            self.current_song[ctx.guild.id] = None

        # Recursive call to play the next song
        self._play_next(ctx)

    async def _cleanup(self, guild_id):
        """Resets the state for a guild and disconnects the bot."""
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            await guild.voice_client.disconnect(force=True)

        self.queues.pop(guild_id, None)
        self.current_song.pop(guild_id, None)
        self.loop_queue.pop(guild_id, None)
        self.loop_song.pop(guild_id, None)
        logger.info(f"Cleaned up state for guild {guild_id}")

    def _create_now_playing_embed(self, song, title_prefix="Now Playing"):
        """Helper to create the rich embed for playing songs."""
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
        """Helper to create the rich embed for the queue display."""
        guild_id = ctx.guild.id
        queue_list = list(self.queues.get(guild_id, asyncio.Queue())._queue)
        current = self.current_song.get(guild_id)

        if not current and not queue_list:
            return discord.Embed(
                description="Queue is empty.", color=discord.Color.greyple()
            )

        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())

        # Add currently playing
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

        # Add upcoming songs
        if queue_list:
            txt = ""
            for i, s in enumerate(queue_list[:10], 1):
                req = f" ({s['requester'].mention})" if s.get("requester") else ""
                txt += f"`{i}.` {s['title']}{req}\n"
            if len(queue_list) > 10:
                txt += f"\n...and {len(queue_list)-10} more"
            embed.add_field(name="Upcoming", value=txt, inline=False)

        # Add status footer
        footer = []
        if self.loop_queue.get(guild_id):
            footer.append("Queue Loop: ON")
        if self.loop_song.get(guild_id):
            footer.append("Song Loop: ON")
        embed.set_footer(
            text=" | ".join(footer) if footer else f"Songs in Queue: {len(queue_list)}"
        )
        return embed

    # --- Events ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Listener:
        1. Cleans up if the bot is kicked/disconnected.
        2. Auto-disconnects if the bot is left alone in a channel for 60s.
        """
        # Bot was disconnected manually or kicked
        if member.id == self.bot.user.id and before.channel and not after.channel:
            logger.info(f"Bot disconnected from {before.channel.name}. Cleaning up.")
            await self._cleanup(member.guild.id)
            return

        # Auto-Leave Logic (If bot is left alone)
        if before.channel is not None:
            guild = before.channel.guild
            vc = guild.voice_client

            # If the channel change involves the channel the bot is currently in
            if vc and vc.channel == before.channel:
                humans = [m for m in vc.channel.members if not m.bot]

                if not humans:
                    logger.info(f"Bot is alone in {vc.channel.name}. Waiting 60s...")
                    await asyncio.sleep(60)

                    # Re-check state after sleep
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
        """Summons the bot to your voice channel."""
        vc = await self._ensure_voice_client(ctx)
        if vc:
            await ctx.send(f"👋 Joined **{vc.channel.name}**!")

    @commands.command(name="leave", aliases=["dc"])
    async def leave(self, ctx):
        """Disconnects the bot and clears the queue."""
        if ctx.guild.voice_client:
            await self._cleanup(ctx.guild.id)
            await ctx.send("👋 Disconnected.")
        else:
            await ctx.send("I am not connected to a voice channel.")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """
        Plays a song from YouTube.
        Usage: .play <url> or .play <search terms>
        """
        vc = await self._ensure_voice_client(ctx)
        if not vc:
            # _ensure_voice_client handles sending error messages
            return

        async with ctx.typing():
            song = await self._get_song_info(query)
            if not song:
                await ctx.send(
                    "❌ Could not find song (or content is age-restricted/blocked)."
                )
                return
            song["requester"] = ctx.author

        guild_id = ctx.guild.id

        # If already playing, add to queue
        if vc.is_playing() or vc.is_paused():
            self._ensure_guild_state_exists(guild_id)
            await self.queues[guild_id].put(song)

            embed = discord.Embed(
                title="Added to Queue",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=song["thumbnail"])
            await ctx.send(embed=embed)
        else:
            # Start playing immediately
            self._ensure_guild_state_exists(guild_id)
            self.current_song[guild_id] = song
            try:
                # Fallback executable check
                exe_path = (
                    FFMPEG_EXECUTABLE_PATH if FFMPEG_EXECUTABLE_PATH else "ffmpeg"
                )

                source = discord.FFmpegPCMAudio(
                    song["source"], executable=exe_path, **FFMPEG_OPTIONS
                )
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))

                await ctx.send(embed=self._create_now_playing_embed(song))
            except Exception as e:
                logger.error(f"Play error: {e}")
                await ctx.send("❌ Error starting playback. Please check logs.")
                self._cleanup(guild_id)

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """Skips the current song."""
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            # Disable song loop so we actually skip
            self.loop_song[ctx.guild.id] = False
            vc.stop()
            await ctx.message.add_reaction("⏭️")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command(name="remove", aliases=["rm", "delete"])
    async def remove(self, ctx, *, query: str):
        """
        Removes a song from the queue by index or name.
        Usage: .remove 2  OR  .remove song name
        """
        guild_id = ctx.guild.id
        # Access the internal queue list properly
        if guild_id not in self.queues or self.queues[guild_id].empty():
            await ctx.send("The queue is empty.")
            return

        # Convert queue to a list to manipulate it
        queue_list = list(self.queues[guild_id]._queue)
        removed_song = None

        # Scenario 1: Remove by Index (Number)
        if query.isdigit():
            index = int(query) - 1  # Convert 1-based user index to 0-based
            if 0 <= index < len(queue_list):
                removed_song = queue_list.pop(index)
            else:
                await ctx.send(
                    f"❌ Invalid index. Please choose between 1 and {len(queue_list)}."
                )
                return

        # Scenario 2: Remove by Name (Substring)
        else:
            query = query.lower()
            matches = []

            # Find all potential matches
            for i, song in enumerate(queue_list):
                if query in song["title"].lower():
                    matches.append((i, song))

            if len(matches) == 0:
                await ctx.send(f"❌ Could not find any song matching '{query}'.")
                return
            elif len(matches) > 1:
                # Safety check: Prevent deleting if multiple songs match
                match_list = "\n".join([f"`{i+1}.` {s['title']}" for i, s in matches])
                await ctx.send(
                    f"⚠️ Found multiple songs matching '{query}'. Please be more specific or use the ID:\n{match_list}"
                )
                return
            else:
                # Exactly one match found - remove it
                index, removed_song = matches[0]
                queue_list.pop(index)

        # Reconstruct the asyncio.Queue with the song removed
        self.queues[guild_id] = asyncio.Queue()
        for song in queue_list:
            await self.queues[guild_id].put(song)

        # Confirm removal
        if removed_song:
            embed = discord.Embed(
                description=f"🗑️ Removed **[{removed_song['title']}]({removed_song['webpage_url']})** from the queue.",
                color=discord.Color.red(),
            )
            if removed_song.get("requester"):
                embed.set_footer(
                    text=f"Requested by: {removed_song['requester'].display_name}"
                )
            await ctx.send(embed=embed)

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx):
        """Displays the current music queue."""
        self._ensure_guild_state_exists(ctx.guild.id)
        await ctx.send(embed=self._create_queue_embed(ctx))

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stops playback and clears the queue."""
        vc = ctx.guild.voice_client
        if vc:
            self.queues[ctx.guild.id] = asyncio.Queue()
            self.current_song[ctx.guild.id] = None
            vc.stop()
            await ctx.send("⏹️ Stopped and cleared queue.")

    @commands.command(name="loop")
    async def loop(self, ctx):
        """Toggles looping of the entire queue."""
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_queue[ctx.guild.id] = not self.loop_queue[ctx.guild.id]

        # If enabling queue loop, disable song loop to avoid confusion
        if self.loop_queue[ctx.guild.id]:
            self.loop_song[ctx.guild.id] = False

        status = "ON" if self.loop_queue[ctx.guild.id] else "OFF"
        await ctx.send(f"🔁 Queue loop: **{status}**")

    @commands.command(name="loopsong")
    async def loopsong(self, ctx):
        """Toggles looping of the currently playing song."""
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_song[ctx.guild.id] = not self.loop_song[ctx.guild.id]

        # If enabling song loop, disable queue loop
        if self.loop_song[ctx.guild.id]:
            self.loop_queue[ctx.guild.id] = False

        status = "ON" if self.loop_song[ctx.guild.id] else "OFF"
        await ctx.send(f"🔂 Song loop: **{status}**")


async def setup(bot):
    await bot.add_cog(Music(bot))
    logger.info("Music Cog Loaded")
