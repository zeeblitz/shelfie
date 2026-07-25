"""Tests for book-search interaction controls."""

from bot.commands.book_commands import create_book_options, create_book_preview_embed


def test_book_search_options_keep_book_ids_and_display_metadata():
    options = create_book_options(
        [
            {
                "id": "SJnHBAAAQBAJ",
                "title": "A Book Title",
                "authors": ["Author One", "Author Two"],
            }
        ]
    )

    assert options[0].value == "SJnHBAAAQBAJ"
    assert options[0].label == "A Book Title"
    assert options[0].description == "Author One, Author Two"


def test_book_preview_embed_shows_cover_and_synopsis():
    embed = create_book_preview_embed(
        {
            "title": "A Book Title",
            "authors": ["Author One"],
            "publisher": "Example Press",
            "page_count": 250,
            "description": "A short synopsis.",
            "thumbnail_url": "https://example.com/cover.jpg",
        }
    )

    assert embed.title == "A Book Title"
    assert embed.description == "A short synopsis."
    assert embed.image.url == "https://example.com/cover.jpg"
