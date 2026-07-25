"""Tests for book-search interaction controls."""

import pytest

from bot.commands.book_commands import create_book_options, create_book_preview_embed
from bot.commands.user_commands import LibraryPaginationView
from bot.models.user_book import BookStatus


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


@pytest.mark.asyncio
async def test_library_pagination_splits_entries_into_pages():
    entries = [
        {
            "book_id": str(index),
            "title": f"Book {index}",
            "status": BookStatus.READING,
            "current_page": 10,
            "page_count": 100,
        }
        for index in range(6)
    ]

    view = LibraryPaginationView(entries, "Reader")

    assert view.total_pages == 2
    assert len(view.current_embed().fields) == 5
