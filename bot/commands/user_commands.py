"""User-related slash commands for Shelfie bot."""

from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.logging import logger
from bot.models.user_book import BookStatus, UserBook
from bot.services.mongo_service import MongoService


class UserCommands(
    commands.GroupCog, group_name="user", group_description="Manage your library"
):
    """Cog for user-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service

    @app_commands.command(name="list", description="List your books")
    @app_commands.describe(status="Filter by status (e.g., READING, COMPLETED)")
    async def list_books(
        self, 
        interaction: discord.Interaction, 
        status: Optional[BookStatus] = None
    ) -> None:
        """List the user's books from their library."""
        await interaction.response.defer(ephemeral=True)

        try:
            query = {"user_id": interaction.user.id}
            if status:
                query["status"] = status.value

            user_books = await self.mongo_service.find_many("user_books", query)

            if not user_books:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Your Library",
                        description="You haven't added any books yet.",
                        color=discord.Color.light_grey()
                    ),
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"{interaction.user.display_name}'s Library",
                color=discord.Color.blue()
            )

            for ub_data in user_books:
                # Convert dict to UserBook model
                ub = UserBook(**ub_data)
                
                # Fetch book details to get title
                book_doc = await self.mongo_service.find_one("books", {"id": ub.book_id})
                book_title = book_doc.get("title", "Unknown Book") if book_doc else "Unknown Book"
                
                status_emoji = {
                    BookStatus.WANT_TO_READ: "📖",
                    BookStatus.READING: "📚",
                    BookStatus.COMPLETED: "✅",
                    BookStatus.DNF: "❌"
                }.get(ub.status, "❓")

                embed.add_field(
                    name=f"{status_emoji} {book_title}",
                    value=f"Status: {ub.status.value} • Page: {ub.current_page}",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error("List books error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to retrieve your library. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @app_commands.command(name="progress", description="Update your reading progress")
    @app_commands.describe(book_id="Google Books ID (from /search)")
    async def update_progress(
        self, 
        interaction: discord.Interaction, 
        book_id: str, 
        page: int
    ) -> None:
        """Update the current page for a book."""
        await interaction.response.defer(ephemeral=True)

        try:
            # 1. Get book details to check total pages
            book_doc = await self.mongo_service.find_one("books", {"id": book_id})
            if not book_doc:
                await interaction.followup.send("Book not found in database. Please add it first.", ephemeral=True)
                return
            
            total_pages = book_doc.get("page_count")

            # 2. Get user's current progress
            user_book_doc = await self.mongo_service.find_one(
                "user_books", 
                {"user_id": interaction.user.id, "book_id": book_id}
            )

            if not user_book_doc:
                await interaction.followup.send("You haven't added this book to your library yet.", ephemeral=True)
                return

            # 3. Validation
            if page < 0:
                await interaction.followup.send("Page number cannot be negative.", ephemeral=True)
                return
            
            if total_pages and page > total_pages:
                await interaction.followup.send(f"Page number cannot exceed total pages ({total_pages}).", ephemeral=True)
                return

            # 4. Update progress
            update_data = {
                "current_page": page,
                "updated_at": datetime.utcnow()
            }

            # Check if completed
            if total_pages and page >= total_pages:
                update_data["status"] = BookStatus.COMPLETED.value
                update_data["completed_at"] = datetime.utcnow()
                # Note: In a real app, we'd also ask for rating here via a modal
            elif page > 0:
                update_data["status"] = BookStatus.READING.value
                update_data["started_at"] = datetime.utcnow()

            await self.mongo_service.update_one(
                "user_books",
                {"user_id": interaction.user.id, "book_id": book_id},
                {"$set": update_data}
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    title="Progress Updated",
                    description=f"Updated progress for '{book_doc['title']}' to page {page}.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

        except Exception as e:
            logger.error("Update progress error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send("An error occurred while updating progress.", ephemeral=True)

    @app_commands.command(name="stats", description="View your reading statistics")
    async def stats(self, interaction: discord.Interaction) -> None:
        """View your reading statistics."""
        await interaction.response.defer(ephemeral=True)

        try:
            user_books = await self.mongo_service.find_many("user_books", {"user_id": interaction.user.id})
            
            completed_count = len([ub for ub in user_books if ub['status'] == BookStatus.COMPLETED.value])
            reading_count = len([ub for ub in user_books if ub['status'] == BookStatus.READING.value])
            total_pages_read = sum([ub.get('current_page', 0) for ub in user_books])

            embed = discord.Embed(
                title=f"{interaction.user.display_name}'s Reading Stats",
                color=discord.Color.gold()
            )
            embed.add_field(name="Books Completed", value=str(completed_count), inline=True)
            embed.add_field(name="Currently Reading", value=str(reading_count), inline=True)
            embed.add_field(name="Total Pages Read", value=str(total_pages_read), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error("Stats error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send("Failed to retrieve stats.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(UserCommands(bot))
