"""Feed service for Shelfie bot to post updates to configured channels."""

from datetime import datetime, timedelta
from typing import Optional

import discord
from bot.logging import logger
from bot.models.user_book import BookStatus
from bot.services.mongo_service import MongoService
from bot.utils.cache import Cache

cache = Cache()


class FeedService:
    """Service to handle posting reading updates to configured feed channels."""

    def __init__(self, bot: discord.Client, mongo_service: MongoService):
        self.bot = bot
        self.mongo_service = mongo_service
        self.last_post_times = {}  # Track last post times per user/book to prevent spam

    async def post_update(self, user_id: int, book_id: str, status: BookStatus, page: Optional[int] = None) -> None:
        """
        Post an update to the configured feed channel if enabled for the guild.

        Args:
            user_id: Discord user ID
            book_id: Google Books ID
            status: Current reading status
            page: Current page (if applicable)
        """
        guild_id = await self._get_guild_id(user_id)
        if not guild_id:
            return

        # Check rate limiting
        key = f"feed_post:{user_id}:{book_id}"
        last_post = await cache.get(key)
        if last_post and (datetime.utcnow() - last_post) < timedelta(hours=1):
            return  # Rate limit - wait 1 hour between posts

        # Get feed channel
        guild_config = await self.mongo_service.find_one(
            "guild_configs", {"_id": guild_id}
        )
        if not guild_config or not guild_config.get("feed_channel_id"):
            return

        channel = self.bot.get_channel(guild_config["feed_channel_id"])
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(guild_config["feed_channel_id"])
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Feed channel unavailable",
                    channel_id=guild_config["feed_channel_id"],
                )
                return
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            return

        # Build embed
        embed = discord.Embed(
            title=f"Reading Update",
            color=discord.Color.blue()
        )

        # Get user and book details
        user = self.bot.get_user(user_id)
        user_name = user.display_name if user else "Unknown User"
        book_doc = await self.mongo_service.find_one("books", {"id": book_id})
        book_title = book_doc.get("title", "Unknown Book") if book_doc else "Unknown Book"

        # Status-specific message
        if status == BookStatus.READING:
            message = f"{user_name} is currently reading '{book_title}' (page {page})."
        elif status == BookStatus.COMPLETED:
            message = f"{user_name} has completed reading '{book_title}'!"
        else:
            return  # Don't post for other status changes

        embed.description = message
        embed.timestamp = datetime.utcnow()

        # Post to channel
        try:
            if isinstance(channel, discord.ForumChannel):
                await channel.create_thread(
                    name=f"Reading update: {book_title}"[:100], embed=embed
                )
            else:
                await channel.send(embed=embed)
            # Cache the post time
            await cache.set(key, datetime.utcnow(), ttl=3600)
            logger.info("Feed post successful", user_id=user_id, book_id=book_id)
        except discord.Forbidden:
            logger.warning("Feed post forbidden", user_id=user_id, book_id=book_id)
        except Exception as e:
            logger.error("Feed post error", error=str(e), user_id=user_id, book_id=book_id)

    async def _get_guild_id(self, user_id: int) -> Optional[int]:
        """Get the guild ID from user's guilds (simplified for now)."""
        for guild in self.bot.guilds:
            if guild.get_member(user_id):
                return guild.id
        return None
