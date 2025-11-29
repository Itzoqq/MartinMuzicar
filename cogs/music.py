# cogs/music.py
import discord
from discord.ext import commands
import asyncio
import logging
from utils.ytdl import YTDLSource

logger = logging.getLogger(__name__)


class Music(commands.Cog):
    """
    Music Cog: Handles all music-related commands.
    """

    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current_song = {}
        self.loop_queue = {}
        self.loop_song = {}

    # --- Helper Methods ---
    def _initialize_guild_state(self, guild_id):
        self.queues[guild_id] = asyncio.Queue()
        self.current_song[guild_id] = None
        self.loop_queue[guild_id] = False
        self.loop_song[guild_id] = False

    def _ensure_guild_state_exists(self, guild_id):
        if guild_id not in self.queues:
            self._initialize_guild_state(guild_id)

    async def _ensure_voice_client(self, ctx) -> discord.VoiceClient | None:
        """Handles connection logic."""
        guild_id = ctx.guild.id
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You must be connected to a voice channel first.")
            return None

        user_channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client

        try:
            if vc is None:
                vc = await user_channel.connect(timeout=30.0)
                self._initialize_guild_state(guild_id)
            elif not vc.is_connected() or vc.channel != user_channel:
                if vc.is_connected():
                    await vc.move_to(user_channel)
                else:
                    # Attempt reconnect
                    vc = await user_channel.connect(reconnect=True, timeout=30.0)

            self._ensure_guild_state_exists(guild_id)
            return vc
        except Exception as e:
            logger.error(f"Connection error: {e}")
            await ctx.send("❌ Could not connect to voice channel.")
            return None

    def _play_next(self, ctx):
        """Logic for playing the next song."""
        guild_id = ctx.guild.id
        vc = ctx.guild.voice_client

        if not vc or not vc.is_connected():
            asyncio.run_coroutine_threadsafe(self._cleanup(guild_id), self.bot.loop)
            return

        current = self.current_song.get(guild_id)
        next_song = None

        # Loop Logic
        if self.loop_song.get(guild_id, False) and current:
            next_song = current
        elif self.loop_queue.get(guild_id, False) and current:
            asyncio.run_coroutine_threadsafe(
                self.queues[guild_id].put(current), self.bot.loop
            )

        # Get next from queue if needed
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

        # Play
        if next_song:
            try:
                self.current_song[guild_id] = next_song

                # Use the utility to create the source
                source = YTDLSource.create_source(next_song["source"])

                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))

                embed = self._create_now_playing_embed(next_song)
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)
            except Exception as e:
                logger.error(f"Playback error: {e}")
                self._play_next(ctx)

    def play_next_after_error(self, error, ctx):
        if error:
            logger.error(f"Playback callback error: {error}")
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

    # --- Embed Helpers ---
    def _create_now_playing_embed(self, song):
        embed = discord.Embed(
            title="Now Playing 🎵",
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

        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())
        if current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{current['title']}]({current['webpage_url']})",
                inline=False,
            )

        if queue_list:
            txt = ""
            for i, s in enumerate(queue_list[:10], 1):
                txt += f"`{i}.` {s['title']}\n"
            if len(queue_list) > 10:
                txt += f"\n...and {len(queue_list)-10} more"
            embed.add_field(name="Upcoming", value=txt, inline=False)
        else:
            if not current:
                embed.description = "Queue is empty."

        return embed

    # --- Events ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id and before.channel and not after.channel:
            await self._cleanup(member.guild.id)

    # --- Commands ---

    @commands.command(name="join", aliases=["connect"])
    async def join(self, ctx):
        """
        Summons the bot to your voice channel.
        No inputs required.
        """
        if await self._ensure_voice_client(ctx):
            await ctx.send(f"👋 Joined **{ctx.guild.voice_client.channel.name}**!")

    @commands.command(name="leave", aliases=["dc"])
    async def leave(self, ctx):
        """
        Disconnects the bot and clears the queue.
        No inputs required.
        """
        await self._cleanup(ctx.guild.id)
        await ctx.send("👋 Disconnected.")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """
        Plays a song from YouTube (Link or Search).
        Inputs: <url> OR <search terms>
        """
        vc = await self._ensure_voice_client(ctx)
        if not vc:
            return

        async with ctx.typing():
            # Use the utility class to get info
            song = await YTDLSource.get_song_info(query, self.bot.loop)
            if not song:
                await ctx.send("❌ Could not find song.")
                return
            song["requester"] = ctx.author

        guild_id = ctx.guild.id
        self._ensure_guild_state_exists(guild_id)

        # 1. Always add the song to the queue first
        await self.queues[guild_id].put(song)

        # 2. If nothing is playing, kick off the player
        if not (vc.is_playing() or vc.is_paused()):
            self._play_next(ctx)

        # 3. If something IS playing, just notify the user it was added
        else:
            await ctx.send(
                embed=discord.Embed(
                    title="Added to Queue",
                    description=f"[{song['title']}]({song['webpage_url']})",
                    color=discord.Color.green(),
                )
            )

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """
        Skips the current song immediately.
        No inputs required.
        """
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.loop_song[ctx.guild.id] = False
            vc.stop()
            await ctx.message.add_reaction("⏭️")

    @commands.command(name="remove", aliases=["rm"])
    async def remove(self, ctx, *, query: str):
        """
        Removes a song from the queue.
        Inputs: <Queue Number> OR <Song Name>
        """
        guild_id = ctx.guild.id
        if guild_id not in self.queues or self.queues[guild_id].empty():
            await ctx.send("Queue is empty.")
            return

        queue_list = list(self.queues[guild_id]._queue)
        removed = None

        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(queue_list):
                removed = queue_list.pop(idx)
        else:
            matches = [
                (i, s)
                for i, s in enumerate(queue_list)
                if query.lower() in s["title"].lower()
            ]
            if len(matches) == 1:
                removed = queue_list.pop(matches[0][0])
            elif len(matches) > 1:
                await ctx.send("⚠️ Multiple matches found. Be more specific.")
                return

        if removed:
            self.queues[guild_id] = asyncio.Queue()
            for s in queue_list:
                await self.queues[guild_id].put(s)
            await ctx.send(f"🗑️ Removed **{removed['title']}**")
        else:
            await ctx.send("❌ Song not found.")

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx):
        """
        Displays the current music queue.
        No inputs required.
        """
        self._ensure_guild_state_exists(ctx.guild.id)
        await ctx.send(embed=self._create_queue_embed(ctx))

    @commands.command(name="stop")
    async def stop(self, ctx):
        """
        Stops playback and clears the queue completely.
        No inputs required.
        """
        if ctx.guild.voice_client:
            self.queues[ctx.guild.id] = asyncio.Queue()
            self.current_song[ctx.guild.id] = None
            ctx.guild.voice_client.stop()
            await ctx.send("⏹️ Stopped.")

    @commands.command(name="loop")
    async def loop(self, ctx):
        """
        Toggles looping of the ENTIRE queue.
        No inputs required.
        """
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_queue[ctx.guild.id] = not self.loop_queue[ctx.guild.id]
        if self.loop_queue[ctx.guild.id]:
            self.loop_song[ctx.guild.id] = False
        await ctx.send(
            f"🔁 Queue loop: **{'ON' if self.loop_queue[ctx.guild.id] else 'OFF'}**"
        )

    @commands.command(name="loopsong")
    async def loopsong(self, ctx):
        """
        Toggles looping of the CURRENT song.
        No inputs required.
        """
        self._ensure_guild_state_exists(ctx.guild.id)
        self.loop_song[ctx.guild.id] = not self.loop_song[ctx.guild.id]
        if self.loop_song[ctx.guild.id]:
            self.loop_queue[ctx.guild.id] = False
        await ctx.send(
            f"🔂 Song loop: **{'ON' if self.loop_song[ctx.guild.id] else 'OFF'}**"
        )


async def setup(bot):
    await bot.add_cog(Music(bot))
    logger.info("Music Cog Loaded")
