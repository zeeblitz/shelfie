"""Configuration commands for Shelfie bot."""

from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import get_settings
from bot.logging import logger
from bot.services.mongo_service import MongoService

COMMAND_RESPONSES_EPHEMERAL = get_settings().COMMAND_RESPONSES_EPHEMERAL
FEED_CHANNEL_TYPES = {
    discord.ChannelType.text,
    discord.ChannelType.news,
    discord.ChannelType.forum,
}


class FeedChannelTransformer(app_commands.Transformer):
    """Accept supported feed channels without requiring a local guild cache."""

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.channel

    @property
    def channel_types(self) -> list[discord.ChannelType]:
        return list(FEED_CHANNEL_TYPES)

    async def transform(
        self, interaction: discord.Interaction, value: app_commands.AppCommandChannel
    ) -> app_commands.AppCommandChannel:
        return value


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class ConfigCommands(
    commands.GroupCog, group_name="config", group_description="Configure Shelfie"
):
    """Cog for configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service

    @app_commands.command(name="feed-channel", description="Set the reading feed channel")
    @app_commands.describe(
        channel="Text or Forum channel for the reading feed"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_feed_channel(
        self,
        interaction: discord.Interaction,
        channel: app_commands.Transform[
            app_commands.AppCommandChannel, FeedChannelTransformer
        ],
    ) -> None:
        """Set or clear the reading feed channel for this server."""
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if channel.type not in FEED_CHANNEL_TYPES:
            await interaction.response.send_message(
                "Choose a text, announcement, or Forum channel for the reading feed.",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
            return

        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        try:
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
            logger.error(
                "Set feed channel error", error=str(e), guild_id=guild_id
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to set feed channel. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

    @app_commands.command(
        name="remove-feed-channel", description="Disable the reading feed"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_feed_channel(self, interaction: discord.Interaction) -> None:
        """Disable reading-feed posts for this server."""
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        try:
            await self.mongo_service.delete_one(
                "guild_configs", {"_id": guild_id}
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Feed Channel Removed",
                    description="Reading feed posts have been disabled for this server.",
                    color=discord.Color.orange(),
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
        except Exception as error:
            logger.error(
                "Remove feed channel error",
                error=str(error),
                guild_id=guild_id,
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to remove the feed channel. Please try again later.",
                    color=discord.Color.red(),
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(ConfigCommands(bot))
