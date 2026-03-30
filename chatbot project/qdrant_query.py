from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

## qdrant connection
qdrant = QdrantClient("localhost", port=6333)
collection = "documents"

#embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

def query_documents(query_text, top_k=5):
    query_vector = model.encode(query_text).tolist()  # convert to list
    search_result = qdrant.search(
        collection=collection,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True
    )
    
    results = []
    for point in search_result:
        text = point.payload.get("text", "")
        source = point.payload.get("source", "unknown")
        results.append({"text": text, "source": source})
    
    return results