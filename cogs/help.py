# cogs/help.py
import discord
from discord.ext import commands


class Help(commands.Cog):
    """
    Custom Help Command to display commands nicely.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h"])
    async def help_command(self, ctx, *, command_name: str = None):
        """
        Displays available commands or details for a specific command.
        Usage: .help  OR  .help play
        """

        # --- Scenario 1: Help for a Specific Command (e.g. ".help play") ---
        if command_name:
            cmd = self.bot.get_command(command_name)
            if not cmd or cmd.hidden:
                await ctx.send(f"❌ Command `{command_name}` not found.")
                return

            # Create a detailed embed
            embed = discord.Embed(
                title=f"📖 Command: {cmd.name.capitalize()}",
                description=cmd.help or "No description provided.",
                color=discord.Color.blue(),
            )

            # Show Syntax
            syntax = f"{ctx.prefix}{cmd.name} {cmd.signature}"
            embed.add_field(name="Usage", value=f"`{syntax}`", inline=False)

            # Show Aliases
            if cmd.aliases:
                aliases_list = ", ".join([f"`{ctx.prefix}{a}`" for a in cmd.aliases])
                embed.add_field(name="Aliases", value=aliases_list, inline=False)

            await ctx.send(embed=embed)

        # --- Scenario 2: General Help Menu (List all) ---
        else:
            embed = discord.Embed(
                title="🤖 MartinMuzicar Commands",
                description=f"Here are the available commands.\nType `{ctx.prefix}help <command>` for more details.",
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

            # Iterate through all Cogs (Categories)
            for cog_name, cog in self.bot.cogs.items():
                if cog_name.lower() == "help":
                    continue  # Skip the help section itself

                command_lines = []
                for cmd in cog.get_commands():
                    if not cmd.hidden:
                        # 1. Get the signature (arguments)
                        params = []
                        for key, value in cmd.clean_params.items():
                            if value.default is not value.empty:
                                params.append(f"[{key}]")  # Optional
                            else:
                                params.append(f"<{key}>")  # Required

                        param_str = " ".join(params)
                        full_syntax = f"{ctx.prefix}{cmd.name} {param_str}"

                        # 2. Get Aliases (New Logic)
                        alias_info = ""
                        if cmd.aliases:
                            alias_list = ", ".join(cmd.aliases)
                            alias_info = f" [{alias_list}]"

                        # 3. Get Description
                        doc = cmd.help.split("\n")[0] if cmd.help else "No description."

                        # 4. Format nicely
                        # Result: > **`.play <query>`** [p]
                        line = f"> **`{full_syntax}`**{alias_info}\n> {doc}"
                        command_lines.append(line)

                if command_lines:
                    embed.add_field(
                        name=f"📂 {cog_name}",
                        value="\n\n".join(command_lines),
                        inline=False,
                    )

            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
