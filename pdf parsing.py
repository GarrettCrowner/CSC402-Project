import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer # converts sentences to embeddings
from nltk.tokenize import sent_tokenize # splits text into sentences
import faiss # stores embeddings in vector database for fast similarity search
import numpy as np

#open pdf and extract text
doc = fitz.open("/Users/marissavilanova/Desktop/sshe-summary.pdf")
text = ""
for page in doc:
    text += page.get_text()

# split into sentences
sentences = sent_tokenize(text)
#need to add more parsing steps to clean up sentences like removing headers and whitespace 

# create embeddings
#pre-trained model that converts sentences to 384-dimensional vectors (got model from chatgpt suggestion, will do research on more bc this one isn't too good)
model = SentenceTransformer('all-MiniLM-L6-v2') 
embeddings = np.array(model.encode(sentences), dtype='float32') #float 32 is required for FAISS

#  build FAISS index
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

print(f"Indexed {len(sentences)} sentences from PDF.")

# test
while True:
    query = input("\nAsk a question (or type 'exit'): ")
    if query.lower() == 'exit':
        break

    # convert question to embedding
    query_embedding = np.array(model.encode([query]), dtype='float32') 

    # find top 3 relevant sentences
    distances, indices = index.search(query_embedding, k=3)

    print("\nTop 3 relevant sentences:")
    for i, idx in enumerate(indices[0]):
        print(f"{i+1}. {sentences[idx]}")

