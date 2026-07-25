"""Book-related slash commands for Shelfie bot."""

from datetime import datetime
from typing import Any, Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import get_settings
from bot.logging import logger
from bot.models.book import Book
from bot.models.user_book import BookStatus, UserBook
from bot.services.book_service import GoogleBooksService
from bot.services.mongo_service import MongoService
from bot.utils.cache import Cache

COMMAND_RESPONSES_EPHEMERAL = get_settings().COMMAND_RESPONSES_EPHEMERAL

cache = Cache()
book_service = GoogleBooksService(cache)


def _truncate(text: str, length: int = 100) -> str:
    """Limit text to Discord select-option field limits."""
    return text if len(text) <= length else f"{text[: length - 1]}…"


def create_book_options(results: List[Dict[str, Any]]) -> List[discord.SelectOption]:
    """Create dropdown options that retain each result's hidden Google Books ID."""
    options = []
    for book in results:
        title = _truncate(book.get("title") or "Untitled")
        authors = ", ".join(book.get("authors", [])) or "Unknown author"
        options.append(
            discord.SelectOption(
                label=title,
                description=_truncate(authors),
                value=book["id"],
            )
        )
    return options


def create_search_embed(query: str, results: List[Dict[str, Any]]) -> discord.Embed:
    """Build the summary embed shown before a book is selected."""
    embed = discord.Embed(
        title=f"Search Results for '{query}'", color=discord.Color.blue()
    )
    for index, book in enumerate(results, 1):
        authors = ", ".join(book.get("authors", [])) or "Unknown"
        pages = book.get("page_count") or "Unknown"
        publisher = book.get("publisher") or "Unknown"
        embed.add_field(
            name=f"{index}. {book['title']}",
            value=f"by {authors} • {pages} pages\nPublisher: {publisher}",
            inline=False,
        )
    return embed


def create_book_preview_embed(book: Dict[str, Any]) -> discord.Embed:
    """Build a rich preview from Google Books metadata."""
    authors = ", ".join(book.get("authors", [])) or "Unknown author"
    synopsis = book.get("description") or "No synopsis is available for this book."
    embed = discord.Embed(
        title=_truncate(book.get("title") or "Untitled", 256),
        description=_truncate(synopsis, 4_096),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Author", value=_truncate(authors, 1_024), inline=True)
    embed.add_field(
        name="Publisher",
        value=_truncate(book.get("publisher") or "Unknown", 1_024),
        inline=True,
    )
    embed.add_field(
        name="Pages", value=str(book.get("page_count") or "Unknown"), inline=True
    )
    if thumbnail_url := book.get("thumbnail_url"):
        embed.set_image(url=thumbnail_url)
    embed.set_footer(text="Choose a reading status to add this book to your library.")
    return embed


class SearchResultsView(discord.ui.View):
    """Dropdown that opens a preview for a selected search result."""

    def __init__(
        self, cog: "BookCommands", query: str, results: List[Dict[str, Any]]
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.query = query
        self.results = results
        self.book_select = discord.ui.Select(
            placeholder="Choose a book to add to your library…",
            options=create_book_options(results),
        )
        self.book_select.callback = self._show_selected_book
        self.add_item(self.book_select)

    async def _show_selected_book(self, interaction: discord.Interaction) -> None:
        """Show the rich preview and status actions for the selected book."""
        selected_id = self.book_select.values[0]
        book = next(book for book in self.results if book["id"] == selected_id)
        await interaction.response.edit_message(
            embed=create_book_preview_embed(book),
            view=BookPreviewView(self.cog, self.query, self.results, book),
        )


class BookPreviewView(discord.ui.View):
    """Preview actions for a selected book."""

    def __init__(
        self,
        cog: "BookCommands",
        query: str,
        results: List[Dict[str, Any]],
        book: Dict[str, Any],
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.query = query
        self.results = results
        self.book = book

    async def _add_with_status(
        self, interaction: discord.Interaction, status: BookStatus
    ) -> None:
        """Add the previewed book with the status chosen by the user."""
        await interaction.response.defer(
            ephemeral=COMMAND_RESPONSES_EPHEMERAL, thinking=True
        )
        await self.cog.add_book_to_library(interaction, self.book["id"], status)

    @discord.ui.button(label="Want to Read", style=discord.ButtonStyle.secondary)
    async def want_to_read(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._add_with_status(interaction, BookStatus.WANT_TO_READ)

    @discord.ui.button(label="Reading", style=discord.ButtonStyle.primary)
    async def reading(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._add_with_status(interaction, BookStatus.READING)

    @discord.ui.button(label="Completed", style=discord.ButtonStyle.success)
    async def completed(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._add_with_status(interaction, BookStatus.COMPLETED)

    @discord.ui.button(label="Back to results", style=discord.ButtonStyle.secondary)
    async def back_to_results(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=create_search_embed(self.query, self.results),
            view=SearchResultsView(self.cog, self.query, self.results),
        )


class BookCommands(
    commands.GroupCog, group_name="book", group_description="Manage books"
):
    """Cog for book-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service

    @app_commands.command(name="search", description="Search for books on Google Books")
    @app_commands.describe(query="Search query (title, author, or ISBN)")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        """Search for books using Google Books API."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)

        try:
            results = await book_service.search_books(query, max_results=5)
            if not results:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="No Results",
                        description=f"No books found for '{query}'. Try a different search term.",
                        color=discord.Color.red()
                    ),
                    ephemeral=COMMAND_RESPONSES_EPHEMERAL
                )
                return

            await interaction.followup.send(
                embed=create_search_embed(query, results),
                view=SearchResultsView(self, query, results),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )

        except Exception as e:
            logger.error("Search error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to search for books. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

    @app_commands.command(name="add", description="Add a book to your library")
    @app_commands.describe(
        book_id="Google Books ID (from /search)",
        status="Reading status to set when adding the book",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        book_id: str,
        status: BookStatus = BookStatus.READING,
    ) -> None:
        """Add a book to the user's library."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await self.add_book_to_library(interaction, book_id, status)

    async def add_book_to_library(
        self,
        interaction: discord.Interaction,
        book_id: str,
        status: BookStatus = BookStatus.READING,
    ) -> None:
        """Add a book by ID after an interaction response has been deferred."""

        try:
            # Get book details
            book_data = await book_service.get_book_details(book_id)
            if not book_data:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Error",
                        description="Book not found. Please verify the book ID.",
                        color=discord.Color.red()
                    ),
                    ephemeral=COMMAND_RESPONSES_EPHEMERAL
                )
                return

            # Check if book already exists in database
            existing_book = await self.mongo_service.find_one("books", {"id": book_id})
            if not existing_book:
                # Save book to database
                book = Book(**book_data)
                await self.mongo_service.insert_one("books", book.model_dump())
                logger.info("Book saved to database", book_id=book_id)

            # Check if user already has this book
            existing_user_book = await self.mongo_service.find_one(
                "user_books",
                {"user_id": interaction.user.id, "book_id": book_id}
            )
            if existing_user_book:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Already Added",
                        description=f"'{book_data['title']}' is already in your library.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=COMMAND_RESPONSES_EPHEMERAL
                )
                return

            # Create user book record
            now = datetime.utcnow()
            user_book = UserBook(
                user_id=interaction.user.id,
                book_id=book_id,
                status=status,
                current_page=0,
                started_at=now if status in (BookStatus.READING, BookStatus.COMPLETED) else None,
                completed_at=now if status == BookStatus.COMPLETED else None,
            )
            await self.mongo_service.insert_one("user_books", user_book.model_dump())

            logger.info(
                "Book added to user library",
                user_id=interaction.user.id,
                book_id=book_id,
                title=book_data['title']
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    title="Book Added",
                    description=(
                        f"'{book_data['title']}' has been added to your library "
                        f"as **{status.value.replace('_', ' ').title()}**!"
                    ),
                    color=discord.Color.green()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )

        except Exception as e:
            logger.error("Add book error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to add book. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(BookCommands(bot))
