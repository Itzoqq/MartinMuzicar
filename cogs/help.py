# cogs/help.py
import discord
from discord.ext import commands


class Help(commands.Cog):
    """
    General commands for the bot.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h"])
    async def help_command(self, ctx):
        """
        Displays this help message showing all available commands.
        """
        embed = discord.Embed(
            title="🤖 MartinMuzicar Help",
            description=f"List of available commands. Prefix: `{ctx.prefix}`",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # Iterate through all loaded Cogs
        for cog_name, cog in self.bot.cogs.items():
            command_list = []
            for command in cog.get_commands():
                if not command.hidden:
                    command_list.append(f"`{ctx.prefix}{command.name}`")

            if command_list:
                commands_str = ", ".join(command_list)
                embed.add_field(name=cog_name, value=commands_str, inline=False)

        embed.set_footer(
            text=f"Type {ctx.prefix}help <command> for more info on a specific command."
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
