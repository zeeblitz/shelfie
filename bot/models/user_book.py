"""User book progress model for Shelfie bot."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BookStatus(str, Enum):
    """Status of a user's reading progress."""
    WANT_TO_READ = "WANT_TO_READ"
    READING = "READING"
    COMPLETED = "COMPLETED"
    DNF = "DNF"  # Did Not Finish


class UserBook(BaseModel):
    """User's relationship with a specific book."""

    user_id: int = Field(..., description="Discord User ID")
    book_id: str = Field(..., description="Google Books ID")
    status: BookStatus = Field(default=BookStatus.WANT_TO_READ)
    current_page: int = Field(default=0, ge=0)
    rating: Optional[int] = Field(None, ge=1, le=5)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        extra = "forbid"