"""Book model for Shelfie bot."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Book(BaseModel):
    """Book model representing book metadata from Google Books API."""

    id: str = Field(..., description="Google Books ID")
    title: str = Field(..., description="Book title")
    authors: List[str] = Field(..., description="List of book authors")
    publisher: Optional[str] = Field(None, description="Book publisher")
    description: Optional[str] = Field(None, description="Book description")
    page_count: Optional[int] = Field(None, description="Total number of pages")
    published_date: Optional[str] = Field(None, description="Publication date")
    isbn_13: Optional[str] = Field(None, description="ISBN-13")
    isbn_10: Optional[str] = Field(None, description="ISBN-10")
    thumbnail_url: Optional[str] = Field(None, description="Book cover thumbnail URL")
    categories: List[str] = Field(default_factory=list, description="Book categories")
    average_rating: Optional[float] = Field(None, description="Average rating")
    ratings_count: Optional[int] = Field(None, description="Number of ratings")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        extra = "forbid"  # Prevent extra fields
