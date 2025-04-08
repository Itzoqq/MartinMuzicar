# cogs/music.py
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
import os
import platform
import pathlib

# --- FFmpeg Path, Options, Logger (Keep as before) ---
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
    logger.info(f"Using FFmpeg executable found at: {FFMPEG_EXECUTABLE_PATH}")
else:
    logger.warning(
        f"FFmpeg executable not found in expected project locations. "
        f"Falling back to searching system PATH. Playback might fail if not in PATH."
    )
    FFMPEG_EXECUTABLE_PATH = "ffmpeg"

yt_dlp.utils.bug_reports_message = lambda: ''
YDL_OPTIONS = {
    'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True,
    'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True,
    'default_search': 'auto', 'source_address': '0.0.0.0'
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.voice_clients = {} # We'll rely more on ctx.guild.voice_client now
        self.queues = {}
        self.current_song = {}
        self.loop_queue = {}
        self.loop_song = {}

    # --- NEW: Helper to initialize or ensure state exists ---
    def _initialize_guild_state(self, guild_id):
        """Initializes all state dictionaries for a guild."""
        self.queues[guild_id] = asyncio.Queue()
        self.current_song[guild_id] = None
        self.loop_queue[guild_id] = False
        self.loop_song[guild_id] = False
        logger.debug(f"Initialized state for guild {guild_id}")

    def _ensure_guild_state_exists(self, guild_id):
        """Ensures state dictionaries exist, initializing if necessary."""
        if guild_id not in self.queues: self.queues[guild_id] = asyncio.Queue()
        if guild_id not in self.current_song: self.current_song[guild_id] = None
        if guild_id not in self.loop_queue: self.loop_queue[guild_id] = False
        if guild_id not in self.loop_song: self.loop_song[guild_id] = False
        # logger.debug(f"Ensured state exists for guild {guild_id}") # Optional debug log

    # --- REFACTORED: _ensure_voice_client ---
    async def _ensure_voice_client(self, ctx: commands.Context) -> discord.VoiceClient | None:
        """
        Ensures the bot is connected to the user's voice channel.
        Returns the VoiceClient or None if connection failed.
        Relies on ctx.guild.voice_client as the source of truth.
        """
        guild_id = ctx.guild.id

        # 1. Check if user is in a voice channel
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be connected to a voice channel to use this command.")
            return None
        user_channel = ctx.author.voice.channel

        # 2. Get the bot's current voice client in this guild (managed by discord.py)
        vc = ctx.guild.voice_client

        try:
            if vc is None:
                # Not connected anywhere in the guild, try to connect
                logger.info(f"Not connected in guild {guild_id}. Attempting to join {user_channel.name}.")
                vc = await user_channel.connect(timeout=30.0) # Add timeout
                self._initialize_guild_state(guild_id) # Initialize state on fresh connect
                logger.info(f"Successfully connected to {user_channel.name}.")

            elif not vc.is_connected():
                 # It exists but reports not connected (potential stale state)
                 logger.warning(f"Voice client for guild {guild_id} exists but reports not connected. Attempting reconnect/move.")
                 # Try moving first, as connect might fail with "already connected"
                 try:
                     await vc.move_to(user_channel)
                     logger.info(f"Successfully moved to {user_channel.name} after stale state detected.")
                 except asyncio.TimeoutError:
                      logger.error(f"Timeout moving to {user_channel.name}. Attempting full reconnect.")
                      # If move fails, try forcing a new connection attempt
                      vc = await user_channel.connect(reconnect=True, timeout=30.0) # Force reconnect
                      logger.info(f"Successfully reconnected to {user_channel.name} after stale state detected.")

                 self._ensure_guild_state_exists(guild_id) # Ensure state is present after reconnect/move

            elif vc.channel != user_channel:
                # Connected, but in the wrong channel, try to move
                logger.info(f"Connected to {vc.channel.name}, moving to {user_channel.name}.")
                await vc.move_to(user_channel)
                self._ensure_guild_state_exists(guild_id) # Ensure state exists after move
                logger.info(f"Successfully moved to {user_channel.name}.")

            # else: vc exists, is connected, and is in the correct channel - state is good

            # Ensure our state dictionaries are initialized (should be by now, but double-check)
            self._ensure_guild_state_exists(guild_id)
            return vc # Return the potentially updated vc object

        except asyncio.TimeoutError:
            await ctx.send(f"Connecting or moving to channel '{user_channel.name}' timed out.")
            logger.error(f"Timeout connecting/moving in guild {guild_id}.")
            await self._cleanup(guild_id) # Clean up if connection fails badly
            return None
        except discord.errors.ClientException as e:
            # This might still catch specific issues like permissions or rare "already connected" races
            await ctx.send(f"Error connecting to voice channel: {e}")
            logger.error(f"ClientException connecting/moving in guild {guild_id}: {e}")
            # Don't cleanup here necessarily, state might be recoverable on next command
            return None
        except Exception as e:
            await ctx.send(f"An unexpected error occurred with the voice connection: {e}")
            logger.error(f"Unexpected connection/move error in guild {guild_id}: {e}", exc_info=True)
            await self._cleanup(guild_id) # Clean up on unexpected errors
            return None


    # --- Helper Functions (_get_song_info - keep as before) ---
    async def _get_song_info(self, query):
        # ... (no changes needed here) ...
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(query, download=False))
        except yt_dlp.utils.DownloadError as e: logger.error(f"yt-dlp download error: {e}"); return None
        except Exception as e: logger.error(f"Unexpected yt-dlp error: {e}"); return None
        if 'entries' in data: data = data['entries'][0] if data['entries'] else None
        if not data: logger.warning("yt-dlp returned no usable data."); return None
        # Simplified URL finding logic (adjust if needed based on previous version)
        stream_url = data.get('url')
        if not stream_url:
             formats = data.get('formats', [])
             best_audio = next((f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url')), None)
             if best_audio: stream_url = best_audio['url']; logger.info("Using URL from 'formats'.")
             else: logger.error("Could not find a suitable stream URL."); return None

        song_info = {
            'source': stream_url, 'title': data.get('title', 'Unknown Title'),
            'webpage_url': data.get('webpage_url', '#'), 'thumbnail': data.get('thumbnail'),
            'duration': data.get('duration'), 'requester': None }
        return song_info


    # --- REFACTORED: _play_next (Minor changes to use vc reliably) ---
    def _play_next(self, ctx):
        guild_id = ctx.guild.id
        # Get the current VC using the reliable way
        vc = ctx.guild.voice_client

        # Check if VC is still valid before proceeding
        if not vc or not vc.is_connected():
            logger.warning(f"Play_next called but VC not connected/valid in guild {guild_id}. Cleaning up.")
            # Use run_coroutine_threadsafe for cleanup from non-async context
            asyncio.run_coroutine_threadsafe(self._cleanup(guild_id), self.bot.loop)
            return

        # --- (Looping logic and queue fetching remains largely the same) ---
        current = self.current_song.get(guild_id)
        song_info_to_play = None # Use a temporary variable

        if self.loop_song.get(guild_id, False) and current:
             song_info_to_play = current # Loop current song
             logger.info(f"Looping song: {song_info_to_play['title']} in guild {guild_id}")

        elif self.loop_queue.get(guild_id, False) and current:
            # Re-add current song to end of queue for queue loop
            try:
                # Need to run this in the event loop
                async def add_to_queue():
                    await self.queues[guild_id].put(current)
                asyncio.run_coroutine_threadsafe(add_to_queue(), self.bot.loop)
                logger.info(f"Re-added to queue for loop: {current['title']} in guild {guild_id}")
            except Exception as e:
                logger.error(f"Error re-adding song to queue for looping: {e}")
            # Fall through to get the next item normally

        # --- (Get next song if not looping single song or after re-adding for queue loop) ---
        if song_info_to_play is None: # If we are not looping the current song
             if not self.queues[guild_id].empty():
                 try:
                     # Get from queue (this needs to be thread-safe)
                     future = asyncio.run_coroutine_threadsafe(self.queues[guild_id].get(), self.bot.loop)
                     song_info_to_play = future.result(timeout=5.0) # Wait for result
                     self.queues[guild_id].task_done()
                 except asyncio.TimeoutError:
                      logger.error(f"Timeout getting song from queue in guild {guild_id}")
                 except Exception as e:
                      logger.error(f"Error getting song from queue in guild {guild_id}: {e}")
             else:
                  logger.info(f"Queue finished in guild {guild_id}")
                  self.current_song[guild_id] = None # Clear current song
                  # Optional: Add inactivity timer start here
                  return # Stop playback cycle

        # --- (Play the determined song) ---
        if song_info_to_play:
            try:
                self.current_song[guild_id] = song_info_to_play # Update current song state
                source = discord.FFmpegPCMAudio(
                    song_info_to_play['source'],
                    executable=FFMPEG_EXECUTABLE_PATH,
                    **FFMPEG_OPTIONS
                )
                # Play using the validated vc
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))

                # Send 'Now Playing' message (thread-safe)
                embed = self._create_now_playing_embed(song_info_to_play)
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)
                logger.info(f"Playing next song: {song_info_to_play['title']} in guild {guild_id}")

            except discord.errors.ClientException as e:
                logger.error(f"Error starting playback (ClientException) in guild {guild_id}: {e}")
                self.current_song[guild_id] = None
                self._play_next(ctx) # Try next song immediately
            except FileNotFoundError:
                logger.critical(f"CRITICAL: FFmpeg executable not found at '{FFMPEG_EXECUTABLE_PATH}'.")
                asyncio.run_coroutine_threadsafe(ctx.send(f"Error: FFmpeg not found."), self.bot.loop)
                self.current_song[guild_id] = None
                asyncio.run_coroutine_threadsafe(self._cleanup(guild_id), self.bot.loop)
            except Exception as e:
                logger.error(f"Error starting playback (General Exception) in guild {guild_id}: {e}", exc_info=True)
                self.current_song[guild_id] = None
                asyncio.run_coroutine_threadsafe(ctx.send(f"Error playing song."), self.bot.loop)
                self._play_next(ctx) # Try next song


    # --- play_next_after_error (Keep as before, ensures _play_next is called) ---
    def play_next_after_error(self, error, ctx):
        guild_id = ctx.guild.id
        if error:
            logger.error(f'Error during playback in guild {guild_id}: {error}')
            # Optionally send message about the error
            # asyncio.run_coroutine_threadsafe(ctx.send(f"Playback error: {error}"), self.bot.loop)

        # Clear current song only if not looping that specific song
        if not self.loop_song.get(guild_id, False):
            self.current_song[guild_id] = None

        # Always attempt to play the next thing (or handle loop)
        self._play_next(ctx)


    # --- REFACTORED: _cleanup ---
    async def _cleanup(self, guild_id):
        """Cleans up voice client and state for a guild."""
        # Use guild.voice_client for disconnect if available
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            logger.info(f"Disconnecting voice client in guild {guild_id}.")
            await guild.voice_client.disconnect(force=True) # Force disconnect
            # No need to delete from self.voice_clients as we aren't using it

        # Clear our state dictionaries reliably
        self.queues.pop(guild_id, None)
        self.current_song.pop(guild_id, None)
        self.loop_queue.pop(guild_id, None)
        self.loop_song.pop(guild_id, None)
        logger.info(f"Cleaned up state for guild {guild_id}")

    # --- Embed Helpers (_create_now_playing_embed, _create_queue_embed - Keep as before) ---
    def _create_now_playing_embed(self, song_info, title_prefix="Now Playing"):
        # ... (no changes needed) ...
        embed = discord.Embed(title=f"{title_prefix} 🎵", description=f"[{song_info['title']}]({song_info['webpage_url']})", color=discord.Color.blue())
        if song_info.get('thumbnail'): embed.set_thumbnail(url=song_info['thumbnail'])
        duration = song_info.get('duration')
        if duration: embed.add_field(name="Duration", value=f"{int(duration//60)}:{int(duration%60):02d}", inline=True)
        if song_info.get('requester'): embed.add_field(name="Requested by", value=song_info['requester'].mention, inline=True)
        return embed

    def _create_queue_embed(self, ctx):
        # ... (no changes needed) ...
        guild_id = ctx.guild.id
        # Ensure queue exists before accessing _queue
        queue_list = list(self.queues.get(guild_id, asyncio.Queue())._queue)
        current = self.current_song.get(guild_id)
        # ... rest of queue embed logic ...
        if not current and not queue_list: return discord.Embed(description="The queue is empty.", color=discord.Color.greyple())
        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())
        if current:
            field_value = f"[{current['title']}]({current['webpage_url']})"
            if current.get('requester'): field_value += f" (Req by: {current['requester'].mention})"
            embed.add_field(name="▶️ Now Playing", value=field_value, inline=False)
        if queue_list:
            queue_text = ""
            for i, song in enumerate(queue_list[:10], start=1):
                queue_text += f"`{i}.` [{song['title']}]({song['webpage_url']})"
                if song.get('requester'): queue_text += f" (Req by: {song['requester'].mention})"
                queue_text += "\n"
            if len(queue_list) > 10: queue_text += f"\n...and {len(queue_list) - 10} more."
            embed.add_field(name="Upcoming", value=queue_text or "No songs in queue.", inline=False)
        loop_status = ""
        if self.loop_queue.get(guild_id, False): loop_status += "🔁 Queue Loop: Enabled\n"
        if self.loop_song.get(guild_id, False): loop_status += "🔂 Song Loop: Enabled\n"
        if loop_status: embed.add_field(name="Loop Status", value=loop_status.strip(), inline=False)
        embed.set_footer(text=f"Total songs in queue: {len(queue_list)}")
        return embed


    # --- Cog Event Listener (on_voice_state_update - REFACTORED) ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Check if the update is for the bot itself
        if member.id == self.bot.user.id:
            # If the bot was disconnected (manually, kicked, channel deleted)
            if before.channel and after.channel is None:
                logger.info(f"Bot disconnected from voice channel {before.channel.name} in guild {before.guild.id}. Triggering cleanup.")
                await self._cleanup(before.guild.id)
            return # Don't process bot's own state updates further for auto-leave

        # Check if the update involves a channel the bot is in
        if before.channel:
            vc = before.guild.voice_client
            # Check if the bot is connected *and* was in the channel the user left/moved from
            if vc and vc.channel == before.channel:
                # Count *human* members remaining in the bot's channel
                human_members = [m for m in vc.channel.members if not m.bot]
                if not human_members:
                    logger.info(f"Bot is alone in channel {vc.channel.name}. Scheduling check for disconnect.")
                    # Wait a bit before disconnecting to handle quick rejoin/moves
                    await asyncio.sleep(60) # 60 seconds inactivity timeout
                    # Re-check state after delay, ensuring VC is still valid
                    vc = before.guild.voice_client # Get potentially updated VC object
                    if vc and vc.is_connected() and vc.channel == before.channel:
                        # Re-count humans after the delay
                        human_members_after_delay = [m for m in vc.channel.members if not m.bot]
                        if not human_members_after_delay:
                            logger.info(f"Disconnecting from {vc.channel.name} due to inactivity.")
                            await self._cleanup(before.guild.id)
                        else:
                             logger.info(f"User re-joined {vc.channel.name} during inactivity check. Cancelling disconnect.")
                    else:
                        logger.info(f"Bot state changed during inactivity check (disconnected/moved?). Cancelling disconnect.")


    # --- Music Commands ---

    # --- join (REFACTORED) ---
    @commands.command(name='join', aliases=['connect'])
    async def join(self, ctx):
        """Connects the bot to your current voice channel."""
        vc = await self._ensure_voice_client(ctx)
        if vc and vc.is_connected(): # Check connection status after ensuring
            await ctx.send(f"Joined **{vc.channel.name}**!")
        elif not vc:
             # Error message already sent by _ensure_voice_client
             pass

    # --- leave (REFACTORED) ---
    @commands.command(name='leave', aliases=['disconnect', 'dc'])
    async def leave(self, ctx):
        """Disconnects the bot from the voice channel and clears the queue."""
        guild_id = ctx.guild.id
        vc = ctx.guild.voice_client

        if vc and vc.is_connected():
            logger.info(f"Leave command called in guild {guild_id}. Disconnecting.")
            await self._cleanup(guild_id) # Cleanup handles disconnect and state clearing
            await ctx.send("Disconnected and cleared queue.")
        else:
            await ctx.send("I'm not currently in a voice channel.")
            # Optional: Still try to cleanup state just in case
            await self._cleanup(guild_id)

    # --- play (Minor changes to use new _ensure_voice_client) ---
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Plays a song or adds it to the queue."""
        vc = await self._ensure_voice_client(ctx)
        if not vc or not vc.is_connected(): # Check connection status
            # Error/status messages handled by _ensure_voice_client
            return

        guild_id = ctx.guild.id

        async with ctx.typing():
            song_info = await self._get_song_info(query)
            if not song_info:
                await ctx.send("Could not find or process the song.")
                return
            song_info['requester'] = ctx.author

        # Check if playing or paused *after* ensuring connection
        if vc.is_playing() or vc.is_paused():
            # Add to queue
            try:
                # Ensure queue exists before putting item
                self._ensure_guild_state_exists(guild_id)
                await self.queues[guild_id].put(song_info)
                embed = discord.Embed(title="Added to Queue 🎵", description=f"[{song_info['title']}]({song_info['webpage_url']})", color=discord.Color.green())
                if song_info.get('thumbnail'): embed.set_thumbnail(url=song_info['thumbnail'])
                await ctx.send(embed=embed)
                logger.info(f"Added to queue: {song_info['title']} in guild {guild_id}")
            except asyncio.QueueFull: await ctx.send("Queue is full!"); logger.warning(f"Queue full in guild {guild_id}")
            except Exception as e: await ctx.send(f"Error adding song: {e}"); logger.error(f"Error adding to queue: {e}", exc_info=True)
        else:
            # Play immediately
            try:
                # Ensure state exists
                self._ensure_guild_state_exists(guild_id)
                self.current_song[guild_id] = song_info # Set current song *before* playing starts _play_next logic
                source = discord.FFmpegPCMAudio(
                    song_info['source'], executable=FFMPEG_EXECUTABLE_PATH, **FFMPEG_OPTIONS
                )
                vc.play(source, after=lambda e: self.play_next_after_error(e, ctx))
                embed = self._create_now_playing_embed(song_info)
                await ctx.send(embed=embed)
                logger.info(f"Started playing: {song_info['title']} in guild {guild_id}")
            # Keep existing exception handling for playback start
            except discord.errors.ClientException as e: await ctx.send(f"Error starting playback: {e}"); logger.error(f"Playback ClientException: {e}"); self.current_song[guild_id] = None; # Don't cleanup necessarily
            except FileNotFoundError: logger.critical(f"FFmpeg not found at '{FFMPEG_EXECUTABLE_PATH}'."); await ctx.send(f"Error: FFmpeg not found."); self.current_song[guild_id] = None; await self._cleanup(guild_id)
            except Exception as e: await ctx.send(f"Unexpected playback error: {e}"); logger.error(f"Playback setup error: {e}", exc_info=True); self.current_song[guild_id] = None; await self._cleanup(guild_id)

    # --- pause, resume, skip, stop, queue, clear, nowplaying, loop, loopsong (REFACTORED where necessary) ---

    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pauses the current song."""
        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("⏸️ Playback paused.")
            logger.info(f"Playback paused in guild {ctx.guild.id}")
        elif vc and vc.is_paused():
             await ctx.send("Playback is already paused.")
        else:
            await ctx.send("Nothing is currently playing.")

    @commands.command(name='resume', aliases=['unpause'])
    async def resume(self, ctx):
        """Resumes paused playback."""
        vc = ctx.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("▶️ Playback resumed.")
            logger.info(f"Playback resumed in guild {ctx.guild.id}")
        elif vc and vc.is_playing():
             await ctx.send("Playback is already playing.")
        else:
            await ctx.send("Nothing was paused.")

    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skips the current song."""
        vc = ctx.guild.voice_client
        guild_id = ctx.guild.id
        if vc and (vc.is_playing() or vc.is_paused()):
            # Ensure single song loop is off before stopping
            self.loop_song[guild_id] = False
            logger.info(f"Skipping song in guild {guild_id}")
            vc.stop() # Triggers 'after' callback (_play_next)
            await ctx.send("⏭️ Song skipped.")
            # _play_next will handle playing the actual next song
        else:
            await ctx.send("Nothing is currently playing to skip.")

    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stops playback completely and clears the queue."""
        vc = ctx.guild.voice_client
        guild_id = ctx.guild.id
        if vc and vc.is_connected():
            logger.info(f"Stop command called in guild {guild_id}. Stopping and clearing.")
            # Clear state *before* disconnecting
            self.queues[guild_id] = asyncio.Queue()
            self.current_song[guild_id] = None
            self.loop_queue[guild_id] = False
            self.loop_song[guild_id] = False
            # Stop playback if occurring
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            # No need to disconnect here, _cleanup will be called by leave or inactivity
            await ctx.send("⏹️ Playback stopped and queue cleared.")
        else:
            await ctx.send("Nothing is currently playing.")


    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Displays the current song queue."""
        # Ensure state exists before creating embed
        self._ensure_guild_state_exists(ctx.guild.id)
        embed = self._create_queue_embed(ctx)
        await ctx.send(embed=embed)

    @commands.command(name='clear', aliases=['clr'])
    async def clear(self, ctx):
        """Clears all songs from the queue."""
        guild_id = ctx.guild.id
        if guild_id in self.queues and not self.queues[guild_id].empty():
             self.queues[guild_id] = asyncio.Queue() # Reset queue
             await ctx.send("🗑️ Queue cleared.")
             logger.info(f"Queue cleared in guild {guild_id}")
        else:
            await ctx.send("The queue is already empty or inactive.")


    @commands.command(name='nowplaying', aliases=['np', 'current'])
    async def nowplaying(self, ctx):
        """Shows the currently playing song."""
        guild_id = ctx.guild.id
        vc = ctx.guild.voice_client
        current = self.current_song.get(guild_id)
        # Check if vc exists, is playing/paused, *and* we have a current song record
        if vc and (vc.is_playing() or vc.is_paused()) and current:
            embed = self._create_now_playing_embed(current)
            await ctx.send(embed=embed)
        else:
            await ctx.send("Nothing is currently playing.")


    @commands.command(name='loop')
    async def loop(self, ctx):
        """Toggles looping the entire queue."""
        guild_id = ctx.guild.id
        # Ensure state exists before toggling
        self._ensure_guild_state_exists(guild_id)
        self.loop_queue[guild_id] = not self.loop_queue[guild_id]
        status = "enabled" if self.loop_queue[guild_id] else "disabled"
        if self.loop_queue[guild_id]: self.loop_song[guild_id] = False # Turn off other loop
        await ctx.send(f"🔁 Queue loop {status}.")
        logger.info(f"Queue loop {status} in guild {guild_id}")


    @commands.command(name='loopsong', aliases=['loopone', 'repeat'])
    async def loopsong(self, ctx):
        """Toggles looping the current song."""
        guild_id = ctx.guild.id
        # Ensure state exists
        self._ensure_guild_state_exists(guild_id)
        self.loop_song[guild_id] = not self.loop_song[guild_id]
        status = "enabled" if self.loop_song[guild_id] else "disabled"
        if self.loop_song[guild_id]: self.loop_queue[guild_id] = False # Turn off other loop
        await ctx.send(f"🔂 Current song loop {status}.")
        logger.info(f"Song loop {status} in guild {guild_id}")


# --- Setup Function for the Cog (Keep as before) ---
async def setup(bot):
    await bot.add_cog(Music(bot))
    logger.info("Music Cog Loaded")