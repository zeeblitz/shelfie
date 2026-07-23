"""MongoDB service for Shelfie bot using PyMongo Async."""

from typing import Any, Dict, List, Optional, Union
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import ConnectionFailure, OperationFailure
from structlog import get_logger

from bot.config import get_settings

logger = get_logger()


def without_mongo_id(document: Dict[str, Any]) -> Dict[str, Any]:
    """Remove MongoDB's internal identifier from application data."""
    return {key: value for key, value in document.items() if key != "_id"}


class MongoService:
    """Service class for MongoDB operations."""

    def __init__(self):
        self._client: Optional[AsyncMongoClient] = None
        self._db: Optional[AsyncDatabase] = None
        self._settings = get_settings()

    async def connect(self) -> None:
        """Connect to MongoDB."""
        try:
            self._client = AsyncMongoClient(self._settings.MONGODB_URI)
            await self._client.admin.command("ping")
            self._db = self._client[self._settings.MONGODB_DB_NAME]
            logger.info("Connected to MongoDB", db=self._settings.MONGODB_DB_NAME)
        except ConnectionFailure as e:
            if self._client is not None:
                await self._client.close()
                self._client = None
            logger.error("Failed to connect to MongoDB", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self._client is not None:
            await self._client.close()
            logger.info("Disconnected from MongoDB")

    async def get_collection(self, name: str) -> AsyncCollection:
        """Get a collection from the database."""
        if self._db is None:
            await self.connect()
        return self._db[name]

    async def find_one(
        self, collection: str, filter: Dict[str, Any], projection: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single document."""
        try:
            coll = await self.get_collection(collection)
            document = await coll.find_one(filter, projection)
            return without_mongo_id(document) if document else None
        except OperationFailure as e:
            logger.error("Failed to find document", collection=collection, error=str(e))
            raise

    async def find_many(
        self,
        collection: str,
        filter: Dict[str, Any] = None,
        projection: Optional[Dict] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents."""
        try:
            coll = await self.get_collection(collection)
            cursor = coll.find(filter or {}, projection)
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)
            documents = await cursor.to_list(length=limit)
            return [without_mongo_id(document) for document in documents]
        except OperationFailure as e:
            logger.error("Failed to find documents", collection=collection, error=str(e))
            raise

    async def insert_one(
        self, collection: str, document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert a single document."""
        try:
            coll = await self.get_collection(collection)
            result = await coll.insert_one(document)
            logger.info("Document inserted", collection=collection, id=str(result.inserted_id))
            return {"inserted_id": str(result.inserted_id)}
        except OperationFailure as e:
            logger.error("Failed to insert document", collection=collection, error=str(e))
            raise

    async def update_one(
        self,
        collection: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Dict[str, Any]:
        """Update a single document."""
        try:
            coll = await self.get_collection(collection)
            result = await coll.update_one(filter, update, upsert=upsert)
            logger.info(
                "Document updated",
                collection=collection,
                matched_count=result.matched_count,
                modified_count=result.modified_count,
            )
            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            }
        except OperationFailure as e:
            logger.error("Failed to update document", collection=collection, error=str(e))
            raise

    async def delete_one(self, collection: str, filter: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a single document."""
        try:
            coll = await self.get_collection(collection)
            result = await coll.delete_one(filter)
            logger.info("Document deleted", collection=collection, deleted_count=result.deleted_count)
            return {"deleted_count": result.deleted_count}
        except OperationFailure as e:
            logger.error("Failed to delete document", collection=collection, error=str(e))
            raise

    async def create_indexes(self) -> None:
        """Create necessary indexes for collections."""
        try:
            # Books collection indexes
            books_coll = await self.get_collection("books")
            await books_coll.create_index([("title", "text")])
            await books_coll.create_index("authors")
            await books_coll.create_index("isbn_13", unique=True, sparse=True)

            # User_books collection indexes
            user_books_coll = await self.get_collection("user_books")
            await user_books_coll.create_index([("user_id", 1), ("book_id", 1)], unique=True)
            await user_books_coll.create_index("user_id")
            await user_books_coll.create_index("status")
            await user_books_coll.create_index([("user_id", 1), ("status", 1)])

            logger.info("All indexes created successfully")
        except OperationFailure as e:
            logger.error("Failed to create indexes", error=str(e))
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
