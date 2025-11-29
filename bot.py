# bot.py
import discord
import os
import asyncio
import logging
from discord.ext import commands
from dotenv import load_dotenv

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("discord")

# --- Load Environment Variables ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if BOT_TOKEN is None:
    logger.critical("BOT_TOKEN not found in .env file. Please ensure it is set.")
    exit()

# --- Bot Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# --- Bot Initialization ---
bot = commands.Bot(
    command_prefix=".", intents=intents, case_insensitive=True, help_command=None
)


# --- Bot Events ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("Bot is ready and online.")
    logger.info("Loading cogs...")

    await load_cogs()

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, name=".play | music"
        )
    )


@bot.event
async def on_command_error(ctx, error):
    """
    Global error handler.
    """
    if isinstance(error, commands.CommandNotFound):
        # CHANGED: Invoke the help command if the command is unknown
        logger.info(f"Unknown command used by {ctx.author}: {ctx.message.content}")
        await ctx.send(f"❌ Unknown command: `{ctx.message.content}`")

        # Trigger the help command manually
        help_cmd = bot.get_command("help")
        if help_cmd:
            await ctx.invoke(help_cmd)
        return

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"❌ Missing required argument: `{error.param.name}`.\n"
            f"Usage: `{ctx.prefix}help {ctx.command}`"
        )

    elif isinstance(error, commands.CommandInvokeError):
        logger.error(f"Error invoking command {ctx.command}: {error.original}")
        await ctx.send(
            "An error occurred while executing the command. Please check the logs."
        )

    elif isinstance(error, commands.CheckFailure):
        await ctx.send(
            "⛔ You do not have the necessary permissions to use this command."
        )

    else:
        logger.error(f"Unhandled command error: {error}")
        await ctx.send("An unexpected error occurred.")


# --- Cog Loading ---
async def load_cogs():
    if not os.path.exists("./cogs"):
        logger.warning("No 'cogs' directory found.")
        return

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                logger.info(f"Successfully loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}. Error: {e}")


# --- Run the Bot ---
async def main():
    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Critical error preventing bot startup: {e}")
