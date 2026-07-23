"""Tests for book-search interaction controls."""

from bot.commands.book_commands import create_book_options


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
