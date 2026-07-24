"""User-related slash commands for Shelfie bot."""

from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import get_settings
from bot.logging import logger
from bot.models.user_book import BookStatus, UserBook
from bot.services.mongo_service import MongoService

COMMAND_RESPONSES_EPHEMERAL = get_settings().COMMAND_RESPONSES_EPHEMERAL


class LibraryBookSelectView(discord.ui.View):
    """Dropdown for choosing one of the user's library books."""

    def __init__(
        self, cog: "UserCommands", options: list[discord.SelectOption], action: str
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.action = action
        self.book_select = discord.ui.Select(
            placeholder="Choose a book from your library…", options=options
        )
        self.book_select.callback = self._select_book
        self.add_item(self.book_select)

    async def _select_book(self, interaction: discord.Interaction) -> None:
        """Prompt for the value after a book has been selected."""
        selected = self.book_select.values[0]
        option = next(option for option in self.book_select.options if option.value == selected)
        await interaction.response.send_modal(
            LibraryBookValueModal(self.cog, self.action, selected, option.label)
        )


class LibraryBookValueModal(discord.ui.Modal):
    """Collect a page count or percentage for a selected book."""

    def __init__(
        self, cog: "UserCommands", action: str, book_id: str, book_title: str
    ):
        labels = {
            "progress": ("Update progress", "Current page", "e.g. 120"),
            "page_count": ("Set edition page count", "Total pages", "e.g. 320"),
            "progress_percent": ("Update percentage progress", "Percentage", "e.g. 37.5"),
        }
        title, label, placeholder = labels[action]
        super().__init__(title=title)
        self.cog = cog
        self.action = action
        self.book_id = book_id
        self.book_title = book_title
        self.value_input = discord.ui.TextInput(
            label=label, placeholder=placeholder, required=True, max_length=8
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate the modal input and apply it to the selected book."""
        try:
            value = (
                float(self.value_input.value)
                if self.action == "progress_percent"
                else int(self.value_input.value)
            )
        except ValueError:
            await interaction.response.send_message(
                "Enter a valid number.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return

        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL, thinking=True)
        await self.cog.apply_library_action(
            interaction, self.action, self.book_id, value
        )


class UserCommands(
    commands.GroupCog, group_name="user", group_description="Manage your library"
):
    """Cog for user-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service

    @staticmethod
    def _page_count(user_book: dict, book: dict) -> Optional[int]:
        """Prefer a user's edition page count over the Google Books value."""
        return user_book.get("page_count") or book.get("page_count")

    async def _get_library_book(
        self, interaction: discord.Interaction, book_id: str
    ) -> Optional[tuple[dict, dict]]:
        """Load a book and the requesting user's library record."""
        book_doc = await self.mongo_service.find_one("books", {"id": book_id})
        if not book_doc:
            await interaction.followup.send(
                "Book not found in the database. Please add it first.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return None

        user_book_doc = await self.mongo_service.find_one(
            "user_books", {"user_id": interaction.user.id, "book_id": book_id}
        )
        if not user_book_doc:
            await interaction.followup.send(
                "You haven't added this book to your library yet.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return None
        return book_doc, user_book_doc

    async def _show_book_selector(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        """Show a dropdown of the user's library books for a pending action."""
        user_books = await self.mongo_service.find_many(
            "user_books", {"user_id": interaction.user.id}, limit=25
        )
        if not user_books:
            await interaction.followup.send(
                "You haven't added any books yet.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return

        options = []
        for user_book in user_books:
            book = await self.mongo_service.find_one(
                "books", {"id": user_book["book_id"]}
            )
            title = (book or {}).get("title", "Unknown Book")
            page_count = self._page_count(user_book, book or {})
            description = (
                f"Page {user_book.get('current_page', 0)}"
                f" / {page_count or 'Unknown'}"
            )
            options.append(
                discord.SelectOption(
                    label=title[:100],
                    description=description[:100],
                    value=user_book["book_id"],
                )
            )

        await interaction.followup.send(
            "Choose the book you want to update.",
            view=LibraryBookSelectView(self, options, action),
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )

    async def apply_library_action(
        self, interaction: discord.Interaction, action: str, book_id: str, value: float
    ) -> None:
        """Run a dropdown-selected progress or edition action."""
        if action == "progress":
            await self._update_progress_by_page(interaction, book_id, int(value))
        elif action == "page_count":
            await self._set_page_count(interaction, book_id, int(value))
        elif action == "progress_percent":
            await self._update_progress_by_percent(interaction, book_id, value)

    async def _save_progress(
        self,
        interaction: discord.Interaction,
        book_id: str,
        user_book: dict,
        page: int,
        total_pages: Optional[int],
    ) -> bool:
        """Validate and store page progress for a library record."""
        if page < 0:
            await interaction.followup.send(
                "Page number cannot be negative.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return False
        if total_pages and page > total_pages:
            await interaction.followup.send(
                f"Page number cannot exceed total pages ({total_pages}).",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
            return False

        update_data = {"current_page": page, "updated_at": datetime.utcnow()}
        if total_pages and page >= total_pages:
            update_data.update(
                status=BookStatus.COMPLETED.value,
                completed_at=datetime.utcnow(),
            )
        elif page > 0:
            update_data["status"] = BookStatus.READING.value
            if not user_book.get("started_at"):
                update_data["started_at"] = datetime.utcnow()
        else:
            update_data.update(
                status=BookStatus.WANT_TO_READ.value,
                completed_at=None,
            )

        await self.mongo_service.update_one(
            "user_books",
            {"user_id": interaction.user.id, "book_id": book_id},
            {"$set": update_data},
        )
        return True

    async def _update_progress_by_page(
        self, interaction: discord.Interaction, book_id: str, page: int
    ) -> None:
        """Update a selected book's page progress."""
        library_book = await self._get_library_book(interaction, book_id)
        if not library_book:
            return
        book_doc, user_book_doc = library_book
        total_pages = self._page_count(user_book_doc, book_doc)
        if not await self._save_progress(
            interaction, book_id, user_book_doc, page, total_pages
        ):
            return
        await interaction.followup.send(
            embed=discord.Embed(
                title="Progress Updated",
                description=f"Updated progress for '{book_doc['title']}' to page {page}.",
                color=discord.Color.green(),
            ),
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )

    async def _set_page_count(
        self, interaction: discord.Interaction, book_id: str, page_count: int
    ) -> None:
        """Set a selected book's personal edition page count."""
        library_book = await self._get_library_book(interaction, book_id)
        if not library_book:
            return
        book_doc, user_book_doc = library_book
        if page_count < 1:
            await interaction.followup.send(
                "Page count must be at least 1.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return
        if user_book_doc.get("current_page", 0) > page_count:
            await interaction.followup.send(
                "Page count cannot be lower than your current page.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return
        await self.mongo_service.update_one(
            "user_books",
            {"user_id": interaction.user.id, "book_id": book_id},
            {"$set": {"page_count": page_count, "updated_at": datetime.utcnow()}},
        )
        await interaction.followup.send(
            f"Set your edition of '{book_doc['title']}' to {page_count} pages.",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )

    async def _update_progress_by_percent(
        self, interaction: discord.Interaction, book_id: str, percentage: float
    ) -> None:
        """Update a selected book's progress from a percentage."""
        if not 0 <= percentage <= 100:
            await interaction.followup.send(
                "Percentage must be between 0 and 100.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return
        library_book = await self._get_library_book(interaction, book_id)
        if not library_book:
            return
        book_doc, user_book_doc = library_book
        total_pages = self._page_count(user_book_doc, book_doc)
        if not total_pages:
            await interaction.followup.send(
                "Set your edition's page count with `/user page-count` first.",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
            return
        page = round(total_pages * percentage / 100)
        if not await self._save_progress(
            interaction, book_id, user_book_doc, page, total_pages
        ):
            return
        await interaction.followup.send(
            (
                f"Updated progress for '{book_doc['title']}' to {percentage:g}% "
                f"(page {page} of {total_pages})."
            ),
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )

    @app_commands.command(name="list", description="List your books")
    @app_commands.describe(status="Filter by status (e.g., READING, COMPLETED)")
    async def list_books(
        self, 
        interaction: discord.Interaction, 
        status: Optional[BookStatus] = None
    ) -> None:
        """List the user's books from their library."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)

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
                    ephemeral=COMMAND_RESPONSES_EPHEMERAL
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
                total_pages = self._page_count(ub_data, book_doc or {})
                
                status_emoji = {
                    BookStatus.WANT_TO_READ: "📖",
                    BookStatus.READING: "📚",
                    BookStatus.COMPLETED: "✅",
                    BookStatus.DNF: "❌"
                }.get(ub.status, "❓")

                embed.add_field(
                    name=f"{status_emoji} {book_title}",
                    value=(
                        f"Status: {ub.status.value} • Page: {ub.current_page}"
                        f" / {total_pages or 'Unknown'}"
                    ),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)

        except Exception as e:
            logger.error("List books error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to retrieve your library. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

    @app_commands.command(name="progress", description="Update your reading progress")
    async def update_progress(self, interaction: discord.Interaction) -> None:
        """Choose a book, then update its current page."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)

        try:
            await self._show_book_selector(interaction, "progress")

        except Exception as e:
            logger.error("Update progress error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send("An error occurred while updating progress.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)

    @app_commands.command(
        name="page-count", description="Set the page count for your edition"
    )
    async def set_page_count(self, interaction: discord.Interaction) -> None:
        """Choose a book, then set the page count for the user's edition."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        try:
            await self._show_book_selector(interaction, "page_count")
        except Exception as e:
            logger.error("Set page count error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                "Failed to update the page count.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

    @app_commands.command(
        name="progress-percent", description="Update reading progress as a percentage"
    )
    async def update_progress_percent(self, interaction: discord.Interaction) -> None:
        """Choose a book, then update its progress as a percentage."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        try:
            await self._show_book_selector(interaction, "progress_percent")
        except Exception as e:
            logger.error(
                "Update percentage progress error",
                error=str(e),
                user_id=interaction.user.id,
            )
            await interaction.followup.send(
                "An error occurred while updating progress.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

    @app_commands.command(name="stats", description="View your reading statistics")
    async def stats(self, interaction: discord.Interaction) -> None:
        """View your reading statistics."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)

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

            await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)

        except Exception as e:
            logger.error("Stats error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send("Failed to retrieve stats.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(UserCommands(bot))

