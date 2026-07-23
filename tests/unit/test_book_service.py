"""Tests for Google Books result normalization."""

import httpx
import pytest

from bot.services.book_service import GoogleBooksService, get_isbn_13
from bot.utils.cache import Cache


def test_get_isbn_13_reads_google_books_identifier_list():
    volume = {
        "industryIdentifiers": [
            {"type": "ISBN_10", "identifier": "0451524934"},
            {"type": "ISBN_13", "identifier": "9780451524935"},
        ]
    }

    assert get_isbn_13(volume) == "9780451524935"


def test_get_isbn_13_handles_missing_or_invalid_identifiers():
    assert get_isbn_13({}) is None
    assert get_isbn_13({"industryIdentifiers": {}}) is None


@pytest.mark.asyncio
async def test_get_book_details_uses_volume_id_path():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/books/v1/volumes/SJnHBAAAQBAJ"
        return httpx.Response(
            200,
            json={
                "id": "SJnHBAAAQBAJ",
                "volumeInfo": {
                    "title": "Example Book",
                    "authors": ["Example Author"],
                },
            },
        )

    service = GoogleBooksService(Cache())
    await service.close()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    details = await service.get_book_details("SJnHBAAAQBAJ")

    assert details["id"] == "SJnHBAAAQBAJ"
    assert details["title"] == "Example Book"
    await service.close()
