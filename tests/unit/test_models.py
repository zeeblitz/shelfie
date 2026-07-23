"""Unit tests for Shelfie bot models."""

import pytest
from datetime import datetime

from bot.models.user_book import BookStatus, UserBook
from bot.services.mongo_service import without_mongo_id


def test_user_book_enum():
    """Test BookStatus enum values."""
    assert BookStatus.WANT_TO_READ.value == "WANT_TO_READ"
    assert BookStatus.READING.value == "READING"
    assert BookStatus.COMPLETED.value == "COMPLETED"
    assert BookStatus.DNF.value == "DNF"


def test_user_book_defaults():
    """Test UserBook default values."""
    ub = UserBook(user_id=12345, book_id="test_book_id")
    assert ub.user_id == 12345
    assert ub.book_id == "test_book_id"
    assert ub.status == BookStatus.WANT_TO_READ
    assert ub.current_page == 0
    assert ub.rating is None
    assert ub.started_at is None
    assert ub.completed_at is None
    assert ub.updated_at is not None


def test_user_book_validation():
    """Test UserBook validation."""
    # Test rating bounds
    ub = UserBook(
        user_id=12345, 
        book_id="test_book_id", 
        rating=3
    )
    assert ub.rating == 3
    
    # Should fail if rating out of bounds
    with pytest.raises(ValueError):
        UserBook(
            user_id=12345, 
            book_id="test_book_id", 
            rating=6  # Invalid rating
        )


def test_user_book_status_enum():
    """Test UserBook status assignment."""
    ub = UserBook(
        user_id=12345, 
        book_id="test_book_id", 
        status=BookStatus.READING
    )
    assert ub.status == BookStatus.READING


def test_mongo_documents_exclude_internal_id_before_model_validation():
    document = {
        "_id": "database-only-id",
        "user_id": 12345,
        "book_id": "test_book_id",
    }

    user_book = UserBook(**without_mongo_id(document))

    assert user_book.user_id == 12345


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
