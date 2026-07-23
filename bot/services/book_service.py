"""Google Books API service with caching for Shelfie bot."""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, validator

from bot.config import get_settings
from bot.logging import logger
from bot.utils.cache import Cache


def get_isbn_13(volume: Dict[str, Any]) -> Optional[str]:
    """Return the ISBN-13 value from a Google Books volume, when present."""
    identifiers = volume.get("industryIdentifiers", [])
    if not isinstance(identifiers, list):
        return None

    for identifier in identifiers:
        if identifier.get("type") == "ISBN_13":
            return identifier.get("identifier")
    return None


class BookSearchResult(BaseModel):
    """Pydantic model for Google Books API search result."""
    id: str = Field(..., description="Google Books ID")
    title: str = Field(..., description="Book title")
    authors: List[str] = Field(..., description="List of authors")
    description: Optional[str] = Field(None, description="Book description")
    page_count: Optional[int] = Field(None, description="Total pages")
    published_date: Optional[str] = Field(None, description="Publication date")
    isbn_13: Optional[str] = Field(None, description="ISBN-13")
    thumbnail_url: Optional[str] = Field(None, description="Cover thumbnail URL")
    average_rating: Optional[float] = Field(None, description="Average rating")
    ratings_count: Optional[int] = Field(None, description="Number of ratings")

    @validator("authors", "title")
    def strip_strings(cls, v):
        return [i.strip() for i in (v if isinstance(v, list) else [v])]


class GoogleBooksService:
    """Service for interacting with Google Books API."""

    def __init__(self, cache: Cache):
        self.cache = cache
        self.api_key = get_settings().GOOGLE_BOOKS_API_KEY
        self.base_url = "https://www.googleapis.com/books/v1/volumes"
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def search_books(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for books using Google Books API.

        Args:
            query: Search query string
            max_results: Maximum number of results to return (default: 5)

        Returns:
            List of book metadata dictionaries
        """
        cache_key = f"books_search:{query}:{max_results}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug("Cache hit for search", query=query)
            return cached_result

        logger.debug("Cache miss for search", query=query)
        params = {
            "q": query,
            "maxResults": max_results,
            "printType": "books",
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Google Books API error", status_code=e.response.status_code, query=query)
            raise
        except httpx.RequestError as e:
            logger.error("Google Books API request error", error=str(e), query=query)
            raise

        # Transform results to our format
        items = data.get("items", [])
        results = []
        for item in items[:max_results]:
            volume = item.get("volumeInfo", {})
            book_id = item.get("id")
            if not book_id:
                continue

            authors = volume.get("authors", [])
            description = volume.get("description")
            page_count = volume.get("pageCount")
            published_date = volume.get("publishedDate")
            isbn_13 = get_isbn_13(volume)
            thumbnail_url = volume.get("imageLinks", {}).get("thumbnail")
            average_rating = volume.get("averageRating")
            ratings_count = volume.get("ratingsCount")

            results.append({
                "id": book_id,
                "title": volume.get("title", ""),
                "authors": authors,
                "description": description,
                "page_count": page_count,
                "published_date": published_date,
                "isbn_13": isbn_13,
                "thumbnail_url": thumbnail_url,
                "average_rating": average_rating,
                "ratings_count": ratings_count,
            })

        # Cache the result for 1 hour
        await self.cache.set(cache_key, results, ttl=3600)
        logger.info("Search results cached", query=query, results_count=len(results))
        return results

    async def get_book_details(self, book_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific book.

        Args:
            book_id: Google Books ID

        Returns:
            Book metadata dictionary
        """
        cache_key = f"books_details:{book_id}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug("Cache hit for book details", book_id=book_id)
            return cached_result

        logger.debug("Cache miss for book details", book_id=book_id)
        params = {}
        if self.api_key:
            params["key"] = self.api_key

        try:
            volume_url = f"{self.base_url}/{quote(book_id, safe='')}"
            response = await self.client.get(volume_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Google Books API error (details)", status_code=e.response.status_code, book_id=book_id)
            raise
        except httpx.RequestError as e:
            logger.error("Google Books API request error (details)", error=str(e), book_id=book_id)
            raise

        volume = data.get("volumeInfo", {})
        if not volume:
            return {}
        authors = volume.get("authors", [])
        description = volume.get("description")
        page_count = volume.get("pageCount")
        published_date = volume.get("publishedDate")
        isbn_13 = get_isbn_13(volume)
        thumbnail_url = volume.get("imageLinks", {}).get("thumbnail")
        average_rating = volume.get("averageRating")
        ratings_count = volume.get("ratingsCount")

        details = {
            "id": data.get("id", book_id),
            "title": volume.get("title", ""),
            "authors": authors,
            "description": description,
            "page_count": page_count,
            "published_date": published_date,
            "isbn_13": isbn_13,
            "thumbnail_url": thumbnail_url,
            "average_rating": average_rating,
            "ratings_count": ratings_count,
        }

        await self.cache.set(cache_key, details, ttl=86400)  # Cache details for 24 hours
        logger.info("Book details cached", book_id=book_id)
        return details
