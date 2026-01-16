from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

class QdrantStorage:
    def __init__(self, url="http://localhost:6333", collection="docs", dim=3072):
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection
        
        # Fixed typo: self.cient -> self.client
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids, vectors, payloads):
        points = [
            PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) 
            for i in range(len(ids))
        ]
        self.client.upsert(self.collection, points=points)

    def search(self, query_vector, top_k: int = 5):
        # Use query_points instead of search for qdrant-client v1.10+
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            with_payload=True,
            limit=top_k
        )
        
        # In the new API, the hits are located in the .points attribute
        results = response.points

        contexts = []
        sources = set()

        for r in results:
            # The payload is directly accessible on the point object
            payload = r.payload or {}
            text = payload.get("text", "")
            source = payload.get("source", "unknown") 
            
            if text:
                contexts.append(text)
                sources.add(source)

        # Note: Changed key to 'sources' to match your main.py expectations
        return {"contexts": contexts, "sources": list(sources)}