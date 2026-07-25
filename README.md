# Shelfie 📚

Shelfie is a lightweight, Discord-native book tracking bot. It allows members of a Discord server to search for books, add them to their personal library, and track their reading progress.

## 🚀 Features (MVP)

- **Book Search**: Search for books via Google Books API using slash commands.
- **Library Management**: Add books to your library and track your reading status.
- **Progress Tracking**: Update your current page and mark books as completed.
- **Reading Stats**: View your reading statistics (books completed, currently reading, total pages read).
- **Reading Feed**: Configurable reading feed channel to share updates with your server.

## 🛠️ Tech Stack

- **Language**: Python 3.12+
- **Discord Library**: `discord.py` 2.x
- **Database**: MongoDB Atlas (via `pymongo.asynchronous`)
- **API**: Google Books API
- **Configuration**: `pydantic-settings`
- **Logging**: `structlog`
- **Dependency Management**: `uv` (recommended)

## 🛠️ Setup & Installation

### Prerequisites

- Python 3.12 or higher
- A MongoDB Atlas cluster (Free Tier)
- A Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd shelfie
   ```

2. **Install dependencies:**
   Using `uv`:
   ```bash
   uv sync
   ```
   Or using `pip`:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Configure environment variables:**
   Create a `.env` file in the root directory based on `.env.example`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your credentials:
   - `DISCORD_TOKEN`: Your bot token.
   - `MONGODB_URI`: Your MongoDB Atlas connection string.
   - `GOOGLE_BOOKS_API_KEY`: (Optional) Your Google Books API key.
   - `COMMAND_RESPONSES_EPHEMERAL`: Set to `false` to make command responses
     visible to everyone while testing (defaults to `true`).

4. **Run the bot:**
   ```bash
   python -m bot.bot
   ```

## ⌨️ Commands

### Book Commands
- `/book search <query>`: Search for books on Google Books, then select a result
  from the dropdown to add it to your library.
- `/book add <book_id>`: Add a book by its Google Books ID (optional fallback).
- `/book info`: Choose a library book to view its metadata and community rating.
- `/book review`: Choose a completed book to add or edit a rating and review.
- `/book rating`: Choose a completed book to add or edit a 1–5 star rating.
- `/book delete-review`: Choose one of your reviewed books to delete its review.
- `/book reviews`: Choose a library book to view community ratings and reviews.

### User Commands
- `/user list`: List your books.
- `/user progress`: Choose a book, then enter the current page.
- `/user edition-pages`: Choose a book, then set your edition's page count.
- `/user progress-percent`: Choose a book, then enter progress as a percentage.
- `/user remove`: Choose and confirm removal of a book from your library.
- `/user stats`: View your reading statistics.

### Configuration Commands
- `/config feed-channel <channel>`: Set or clear the reading feed channel.

## 🛡️ License

This project is licensed under the MIT License.
