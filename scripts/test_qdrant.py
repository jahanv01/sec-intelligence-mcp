"""Smoke test: creates a test collection in Qdrant, inserts one vector, retrieves it."""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

COLLECTION = "test_collection"


def main() -> None:
    client = QdrantClient("localhost", port=6333)

    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )

    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4], payload={"name": "test"})],
    )

    points = client.retrieve(collection_name=COLLECTION, ids=[1])
    assert len(points) == 1, "expected 1 point back"
    assert points[0].payload["name"] == "test"
    print("OK: Qdrant round-trip succeeded ->", points[0])

    client.delete_collection(COLLECTION)


if __name__ == "__main__":
    main()
