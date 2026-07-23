"""Main entry point for Shelfie Discord bot."""

from typing import Optional

from aiohttp import web
import discord
from discord.ext import commands

from bot.config import get_settings
from bot.logging import configure_logging, logger
from bot.services.mongo_service import MongoService

# Configure logging
settings = get_settings()
configure_logging(settings.LOG_LEVEL)

# Health check endpoint
async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint for monitoring."""
    return web.json_response({"status": "healthy"})


async def create_health_app() -> web.Application:
    """Create health check application."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    return app


class ShelfieBot(commands.Bot):
    """Shelfie Discord bot."""

    def __init__(self):
        # Enable intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,  # Disable default help command
        )

        # Setup services
        self.mongo_service = MongoService()
        self.health_runner: Optional[web.AppRunner] = None

    async def setup_hook(self) -> None:
        """Setup hook called before the bot starts."""
        # Connect to MongoDB
        await self.mongo_service.connect()

        # Create indexes
        await self.mongo_service.create_indexes()

        # Load slash-command cogs. commands.Bot already provides self.tree.
        for extension in (
            "bot.commands.book_commands",
            "bot.commands.user_commands",
            "bot.commands.config_commands",
        ):
            await self.load_extension(extension)

        # Start the health server before connecting to Discord.
        health_app = await create_health_app()
        self.health_runner = web.AppRunner(health_app)
        await self.health_runner.setup()
        site = web.TCPSite(
            self.health_runner, settings.HEALTH_HOST, settings.HEALTH_PORT
        )
        await site.start()
        logger.info(
            "Health check server started",
            host=settings.HEALTH_HOST,
            port=settings.HEALTH_PORT,
        )

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        logger.info("Bot is ready", username=self.user, id=self.user.id)
        await self.tree.sync()
        logger.info("Slash commands synced")

    async def close(self) -> None:
        """Clean shutdown."""
        await self.mongo_service.disconnect()
        if self.health_runner:
            await self.health_runner.cleanup()
            self.health_runner = None
        await super().close()


# Entry point
if __name__ == "__main__":
    bot = ShelfieBot()
    try:
        bot.run(settings.DISCORD_TOKEN.get_secret_value())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Bot crashed", error=str(e))
        raise
