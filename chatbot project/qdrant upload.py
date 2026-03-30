import io
import fitz
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams
from minio import Minio

## minio connection
minio_client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure = False
)

bucket_name = "documents"

## qdrant connection
qdrant = QdrantClient("localhost", port=6333)
collection = "documents"

#embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

#text chunks
def chunk_text(text, chunk_size=300, overlap=50):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks

website_urls = ["https://www.wcupa.edu/hr/faqs.aspx", 
        "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",
        "https://www.passhe.edu/hr/benefits/life-events/index.html",
        "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
        "https://www.wcupa.edu/hr/FMLA.aspx",
        "https://www.wcupa.edu/hr/employee-labor-relations.aspx"]

## process each pdf
points = []
id_counter = 0

#process urls
for url in website_urls:
    print(f"Processing {url}...")
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    text = ' '.join([p.get_text() for p in soup.find_all('p')])
    
    chunks = chunk_text(text)
    embeddings = model.encode(chunks)

    for i, chunk in enumerate(chunks):
        points.append(
            PointStruct(
                id=id_counter,
                vector=embeddings[i].tolist(),
                payload={"text": chunk, "source": url}
            )
        )
        id_counter += 1

#process pdfs from minio
objects = minio_client.list_objects(bucket_name)
for obj in objects:
    if obj.object_name.endswith(".pdf"):
        print(f"Processing {obj.object_name}...")
        response = minio_client.get_object(bucket_name, obj.object_name)
        pdf_bytes = io.BytesIO(response.read())
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        text = ""
        for page in doc:
            text += page.get_text()
        
        chunks = chunk_text(text)
        embeddings = model.encode(chunks)
        for i, chunk in enumerate(chunks):
            points.append(
                PointStruct(
                    id=id_counter,
                    vector=embeddings[i].tolist(),
                    payload={"text": chunk, "source": obj.object_name}
                )
            )
            id_counter += 1

## create/recreate collection if doesn't exist/missing points and upload points
if not qdrant.collection_exists(collection):
    qdrant.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=len(points[0].vector), distance=Distance.COSINE)
    )
else:
    print(f"Collection '{collection}' already exists. New points will be appended.")

BATCH_SIZE = 50  # getting error when trying to upload all points at once, so uploading in batches instead

for i in range(0, len(points), BATCH_SIZE):
    batch = points[i:i + BATCH_SIZE]
    qdrant.upsert(collection_name=collection, points=batch)
    print(f"Uploaded points {i}–{i+len(batch)}")