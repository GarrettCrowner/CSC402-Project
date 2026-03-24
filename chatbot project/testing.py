from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# Connect to Qdrant
qdrant = QdrantClient(host="localhost", port=6333)
collection_name = "documents"

# Load your embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Example query
query_text = "What documents do I need for I-9 verification?"
query_vector = model.encode(query_text).tolist()  # convert to list for Qdrant

# Search top 3 similar points
search_result = qdrant.search(
    collection_name,
    query_vector,
    limit=3,
    with_payload=True
)

# Print results
for i, point in enumerate(search_result):
    # point is a ScoredPoint object
    text = point.payload.get("text", "")
    source = point.payload.get("source", "unknown")
    print(f"{i+1}. Source: {source}\nText: {text}\n{'-'*80}")
