# bot.py
import discord
import os
import asyncio
import logging
from discord.ext import commands
from dotenv import load_dotenv

# --- Basic Logging Setup ---
# Configure logging to show timestamps and log levels
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s: %(message)s"
)
logger = logging.getLogger("discord")  # Get the discord logger

# --- Load Environment Variables ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if BOT_TOKEN is None:
    logger.critical("BOT_TOKEN not found in .env file. Please ensure it is set.")
    exit()  # Exit if the token is not found

# --- Bot Intents ---
# Define the intents required for the bot.
# guilds: Access guild information.
# voice_states: Access voice channel states (joining, leaving, speaking).
# message_content: Needed for prefix commands (reading message content).
#                  If using slash commands primarily, this might not be strictly necessary
#                  depending on your other features, but often good to have.
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.voice_states = True  # Enable voice state intent
intents.guilds = True  # Enable guild intent

# --- Bot Initialization ---
# Create the Bot instance with a command prefix and the defined intents.
# Use command_prefix='!' or any prefix you prefer.
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)


# --- Bot Events ---
@bot.event
async def on_ready():
    """Event handler for when the bot logs in and is ready."""
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("Bot is ready and online.")
    logger.info("Loading cogs...")
    # Load cogs after the bot is ready
    await load_cogs()
    # You can set a custom status here if you like
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="!play | music"
        )
    )


@bot.event
async def on_command_error(ctx, error):
    """Global error handler for commands."""
    if isinstance(error, commands.CommandNotFound):
        # Silently ignore CommandNotFound errors or send a generic message
        # await ctx.send("Invalid command used.")
        pass  # Or log it if you want to track unknown commands
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"Missing required argument: `{error.param.name}`. Use `!help {ctx.command}` for details."
        )
    elif isinstance(error, commands.CommandInvokeError):
        logger.error(f"Error invoking command {ctx.command}: {error.original}")
        await ctx.send(
            f"An error occurred while executing the command: {error.original}"
        )
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You do not have the necessary permissions to use this command.")
    else:
        # Handle other errors or log them
        logger.error(f"Unhandled command error: {error}")
        await ctx.send(f"An unexpected error occurred: {error}")


# --- Cog Loading ---
async def load_cogs():
    """Finds and loads all cogs in the 'cogs' directory."""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                logger.info(f"Successfully loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}. Error: {e}")
                # You might want to print the traceback for detailed debugging
                # import traceback
                # traceback.print_exc()


# --- Run the Bot ---
async def main():
    async with bot:
        # Starting the bot
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    # Use asyncio.run() to start the asynchronous main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down.")
    except Exception as e:
        logger.critical(f"Critical error preventing bot startup: {e}")
