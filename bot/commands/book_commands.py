"""Book-related slash commands for Shelfie bot."""

import discord
from discord import app_commands
from discord.ext import commands

from bot.logging import logger
from bot.models.book import Book
from bot.models.user_book import BookStatus, UserBook
from bot.services.book_service import GoogleBooksService
from bot.services.mongo_service import MongoService
from bot.utils.cache import Cache

cache = Cache()
book_service = GoogleBooksService(cache)


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
        await interaction.response.defer(ephemeral=True)

        try:
            results = await book_service.search_books(query, max_results=5)
            if not results:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="No Results",
                        description=f"No books found for '{query}'. Try a different search term.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Build embed with search results
            embed = discord.Embed(
                title=f"Search Results for '{query}'",
                color=discord.Color.blue()
            )

            for i, book in enumerate(results, 1):
                authors = ", ".join(book.get("authors", [])) or "Unknown"
                pages = book.get("page_count", "Unknown")
                embed.add_field(
                    name=f"{i}. {book['title']}",
                    value=(
                        f"by {authors} • {pages} pages\n"
                        f"Book ID: `{book['id']}`"
                    ),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error("Search error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to search for books. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @app_commands.command(name="add", description="Add a book to your library")
    @app_commands.describe(book_id="Google Books ID (from /search)")
    async def add(self, interaction: discord.Interaction, book_id: str) -> None:
        """Add a book to the user's library."""
        await interaction.response.defer(ephemeral=True)

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
                    ephemeral=True
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
                    ephemeral=True
                )
                return

            # Create user book record
            user_book = UserBook(
                user_id=interaction.user.id,
                book_id=book_id,
                status=BookStatus.READING,
                current_page=0,
                started_at=None
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
                    description=f"'{book_data['title']}' has been added to your library!",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

        except Exception as e:
            logger.error("Add book error", error=str(e), user_id=interaction.user.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to add book. Please try again later.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(BookCommands(bot))
