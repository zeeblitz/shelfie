"""Global error handler for Shelfie bot."""

import traceback
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.logging import logger


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Handle errors from slash commands."""
    # Log the error
    logger.error(
        "Slash command error",
        command=interaction.command.name if interaction.command else "unknown",
        user_id=interaction.user.id,
        guild_id=interaction.guild.id if interaction.guild else None,
        error=str(error),
        traceback=traceback.format_exc()
    )

    # Send user-friendly error message
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message(
            "❌ I don't have the required permissions to execute this command.",
            ephemeral=True
        )
    else:
        # Generic error
        await interaction.response.send_message(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )


async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """Handle errors from prefix commands (if any)."""
    logger.error(
        "Prefix command error",
        command=ctx.command.name if ctx.command else "unknown",
        user_id=ctx.author.id,
        guild_id=ctx.guild.id if ctx.guild else None,
        error=str(error),
        traceback=traceback.format_exc()
    )

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"⏳ This command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
            delete_after=5.0
        )
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.", delete_after=5.0)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have the required permissions to execute this command.", delete_after=5.0)
    else:
        await ctx.send("❌ An unexpected error occurred. Please try again later.", delete_after=5.0)