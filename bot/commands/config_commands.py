"""Configuration commands for Shelfie bot."""

from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import get_settings
from bot.logging import logger
from bot.services.mongo_service import MongoService

COMMAND_RESPONSES_EPHEMERAL = get_settings().COMMAND_RESPONSES_EPHEMERAL


class ConfigCommands(
    commands.GroupCog, group_name="config", group_description="Configure Shelfie"
):
    """Cog for configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service

    @app_commands.command(name="feed-channel", description="Set or clear the reading feed channel")
    @app_commands.describe(channel="Text channel for reading feed (or 'none' to disable)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_feed_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set or clear the reading feed channel for this server."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)

        try:
            guild_id = interaction.guild.id

            if channel is None:
                # Clear feed channel
                await self.mongo_service.delete_one(
                    "guild_configs",
                    {"_id": guild_id}
                )
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Feed Channel Cleared",
                        description="Reading feed has been disabled for this server.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=COMMAND_RESPONSES_EPHEMERAL
                )
                return

            # Set feed channel
            guild_config = {
                "_id": guild_id,
                "feed_channel_id": channel.id,
                "updated_at": datetime.utcnow()
            }

            await self.mongo_service.update_one(
                "guild_configs",
                {"_id": guild_id},
                {"$set": guild_config},
                upsert=True
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    title="Feed Channel Set",
                    description=f"Reading feed will now be posted to {channel.mention}",
                    color=discord.Color.green()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

        except Exception as e:
            logger.error("Set feed channel error", error=str(e), guild_id=interaction.guild.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to set feed channel. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(ConfigCommands(bot))
