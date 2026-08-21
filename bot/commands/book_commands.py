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
from bot.commands.user_commands import UserCommands

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


class ReviewModal(discord.ui.Modal):
    """Create or update a completed reader's rating and optional review."""

    def __init__(self, cog: "BookCommands", book_id: str, title: str):
        super().__init__(title="Rate this book")
        self.cog = cog
        self.book_id = book_id
        self.book_title = title
        self.rating_input = discord.ui.TextInput(
            label="Rating (1–5 stars)", placeholder="e.g. 4", max_length=1
        )
        self.review_input = discord.ui.TextInput(
            label="Review (optional)", style=discord.TextStyle.paragraph,
            placeholder="What did you think?", required=False, max_length=2000,
        )
        self.add_item(self.rating_input)
        self.add_item(self.review_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rating = int(self.rating_input.value)
            if not 1 <= rating <= 5:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Rating must be a whole number from 1 to 5.",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
            return
        await interaction.response.defer(
            ephemeral=COMMAND_RESPONSES_EPHEMERAL, thinking=True
        )
        saved = await self.cog.save_review(
            interaction, self.book_id, rating, self.review_input.value.strip() or None
        )
        if saved:
            await interaction.followup.send(
                f"Saved your {rating}★ rating for '{self.book_title}'.",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )


class ReviewPromptView(discord.ui.View):
    """Optional rating prompt presented after completion."""

    def __init__(self, cog: "BookCommands", book_id: str, title: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.book_id = book_id
        self.book_title = title

    @discord.ui.button(label="Rate this book", style=discord.ButtonStyle.primary)
    async def rate(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            ReviewModal(self.cog, self.book_id, self.book_title)
        )


class LibraryBookActionView(discord.ui.View):
    """Library dropdown used by book information and review commands."""

    def __init__(
        self, cog: "BookCommands", action: str, options: List[discord.SelectOption]
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
        book_id = self.book_select.values[0]
        if self.action in {"review", "rating"}:
            book = await self.cog.mongo_service.find_one("books", {"id": book_id})
            await interaction.response.send_modal(
                ReviewModal(self.cog, book_id, (book or {}).get("title", "Book"))
            )
            return
        await interaction.response.defer(
            ephemeral=COMMAND_RESPONSES_EPHEMERAL, thinking=True
        )
        await self.cog.run_library_action(interaction, self.action, book_id)


class BookCommands(
    commands.GroupCog, group_name="book", group_description="Manage books"
):
    """Cog for book-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_service: MongoService = bot.mongo_service
        self.library_commands = UserCommands(bot)

    async def rating_summary(self, book_id: str) -> tuple[float, int, list[dict]]:
        """Return the community rating aggregate and review records for a book."""
        records = await self.mongo_service.find_many("user_books", {"book_id": book_id})
        reviews = [record for record in records if record.get("rating") is not None]
        if not reviews:
            return 0.0, 0, []
        return sum(record["rating"] for record in reviews) / len(reviews), len(reviews), reviews

    async def save_review(
        self, interaction: discord.Interaction, book_id: str, rating: int, review: str | None
    ) -> bool:
        """Save one completed user's rating and optional review."""
        user_book = await self.mongo_service.find_one(
            "user_books", {"user_id": interaction.user.id, "book_id": book_id}
        )
        if not user_book or user_book.get("status") != BookStatus.COMPLETED.value:
            await interaction.followup.send(
                "You can rate a book after marking it as completed.",
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )
            return False
        await self.mongo_service.update_one(
            "user_books",
            {"user_id": interaction.user.id, "book_id": book_id},
            {"$set": {"rating": rating, "review": review, "reviewed_at": datetime.utcnow()}},
        )
        return True

    async def book_info_embed(self, book_id: str) -> discord.Embed | None:
        """Build the book info card enriched with local community ratings."""
        book = await self.mongo_service.find_one("books", {"id": book_id})
        if not book:
            return None
        embed = create_book_preview_embed(book)
        average, count, _ = await self.rating_summary(book_id)
        rating_text = f"⭐ {average:.1f} ({count} review{'s' if count != 1 else ''})" if count else "No community ratings yet"
        embed.add_field(name="Community Rating", value=rating_text, inline=False)
        embed.set_footer(text="Use /book review after completing this book.")
        return embed

    async def _open_review_modal(
        self, interaction: discord.Interaction, book_id: str
    ) -> None:
        """Open the review editor after confirming that the book exists."""
        book = await self.mongo_service.find_one("books", {"id": book_id})
        if not book:
            await interaction.response.send_message(
                "Book not found in your library.", ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return
        await interaction.response.send_modal(ReviewModal(self, book_id, book["title"]))

    async def _show_library_selector(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        """Show only the caller's relevant library books for an action."""
        records = await self.mongo_service.find_many(
            "user_books", {"user_id": interaction.user.id}, limit=25
        )
        if action in {"review", "rating"}:
            records = [
                record for record in records
                if record.get("status") == BookStatus.COMPLETED.value
            ]
        elif action == "delete_review":
            records = [record for record in records if record.get("rating") is not None]
        if not records:
            message = {
                "review": "Complete a book before adding a review.",
                "rating": "Complete a book before adding a rating.",
                "delete_review": "You have no reviews to delete.",
            }.get(action, "You haven't added any books yet.")
            await interaction.followup.send(
                message, ephemeral=COMMAND_RESPONSES_EPHEMERAL
            )
            return
        options = []
        for record in records:
            book = await self.mongo_service.find_one("books", {"id": record["book_id"]})
            title = (book or {}).get("title", "Unknown Book")
            options.append(
                discord.SelectOption(
                    label=_truncate(title),
                    description=_truncate(
                        record.get("status", "").replace("_", " ").title()
                    ),
                    value=record["book_id"],
                )
            )
        await interaction.followup.send(
            "Choose a book.",
            view=LibraryBookActionView(self, action, options),
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )

    async def run_library_action(
        self, interaction: discord.Interaction, action: str, book_id: str
    ) -> None:
        """Perform an action selected from a library dropdown."""
        if action == "delete_review":
            result = await self.mongo_service.update_one(
                "user_books",
                {"user_id": interaction.user.id, "book_id": book_id, "rating": {"$ne": None}},
                {"$unset": {"rating": "", "review": "", "reviewed_at": ""}},
            )
            message = "Deleted your review." if result["matched_count"] else "You have no review for this book."
            await interaction.followup.send(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        elif action == "reviews":
            await self._send_reviews(interaction, book_id)
        elif action == "info":
            embed = await self.book_info_embed(book_id)
            await interaction.followup.send(
                embed=embed if embed else discord.Embed(description="Book not found."),
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
            )

    async def _send_reviews(self, interaction: discord.Interaction, book_id: str) -> None:
        """Send the community review summary for a selected book."""
        book = await self.mongo_service.find_one("books", {"id": book_id})
        if not book:
            await interaction.followup.send("Book not found.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
            return
        average, count, reviews = await self.rating_summary(book_id)
        embed = discord.Embed(title=f"Reviews for {book['title']}", color=discord.Color.gold())
        embed.description = f"⭐ {average:.1f} from {count} review{'s' if count != 1 else ''}" if count else "No reviews yet."
        for index, review in enumerate(reviews[:10], 1):
            text = review.get("review") or "No written review."
            embed.add_field(name=f"Reader {index} • {'⭐' * review['rating']}", value=_truncate(text, 1_024), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)

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

            response_kwargs: dict[str, Any] = {
                "embed": discord.Embed(
                    title="Book Added",
                    description=(
                        f"'{book_data['title']}' has been added to your library "
                        f"as **{status.value.replace('_', ' ').title()}**!"
                    ),
                    color=discord.Color.green(),
                ),
                "ephemeral": COMMAND_RESPONSES_EPHEMERAL,
            }
            if status == BookStatus.COMPLETED:
                response_kwargs["view"] = ReviewPromptView(
                    self, book_id, book_data["title"]
                )
            await interaction.followup.send(**response_kwargs)

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

    @app_commands.command(name="review", description="Add or edit your rating and review")
    async def review(self, interaction: discord.Interaction) -> None:
        """Open a review form for a completed library book."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await self._show_library_selector(interaction, "review")

    @app_commands.command(name="delete-review", description="Delete your rating and review")
    async def delete_review(self, interaction: discord.Interaction) -> None:
        """Delete the caller's review without deleting their library entry."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await self._show_library_selector(interaction, "delete_review")

    @app_commands.command(
        name="community-reviews", description="View community reviews for a book"
    )
    async def reviews(self, interaction: discord.Interaction) -> None:
        """Show ratings and written reviews without exposing Discord user IDs."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await self._show_library_selector(interaction, "reviews")

    @app_commands.command(
        name="details", description="Show book details and community rating"
    )
    async def info(self, interaction: discord.Interaction) -> None:
        """Show stored book metadata, cover, synopsis, and community rating."""
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await self._show_library_selector(interaction, "info")

    @app_commands.command(name="library", description="View the books in your library")
    @app_commands.describe(status="Filter by status, such as READING or COMPLETED")
    async def library(
        self,
        interaction: discord.Interaction,
        status: BookStatus | None = None,
    ) -> None:
        """List the invoking member's library."""
        await self.library_commands.list_books(interaction, status)

    @app_commands.command(
        name="update-progress", description="Update a book's current page"
    )
    async def update_progress(self, interaction: discord.Interaction) -> None:
        """Choose a book and update its current page."""
        await self.library_commands.update_progress(interaction)

    @app_commands.command(
        name="set-page-count", description="Set the page count for your edition"
    )
    async def set_page_count(self, interaction: discord.Interaction) -> None:
        """Choose a book and set its edition-specific page count."""
        await self.library_commands.set_edition_pages(interaction)

    @app_commands.command(
        name="update-progress-percent",
        description="Update a book's reading progress as a percentage",
    )
    async def update_progress_percent(self, interaction: discord.Interaction) -> None:
        """Choose a book and update its progress as a percentage."""
        await self.library_commands.update_progress_percent(interaction)

    @app_commands.command(
        name="remove-from-library", description="Remove a book from your library"
    )
    async def remove_from_library(self, interaction: discord.Interaction) -> None:
        """Choose and confirm a book to remove from the invoking member's library."""
        await self.library_commands.remove_book(interaction)

    @app_commands.command(name="stats", description="View your reading statistics")
    async def stats(self, interaction: discord.Interaction) -> None:
        """Show reading statistics for the invoking member."""
        await self.library_commands.stats(interaction)


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(BookCommands(bot))
