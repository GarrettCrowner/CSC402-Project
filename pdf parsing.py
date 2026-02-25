#need to figure out how to handle tables in pdfs 
#might need to place filters to prevent irrevelant content (like metlife address when not relevant)
#can also use coordinates to remove content like headers and footers


import os
import pandas as pd
import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer
from nltk.tokenize import sent_tokenize
import faiss
import numpy as np
import requests
from bs4 import BeautifulSoup #extract text from website


folder_path = "/Users/marissavilanova/Desktop/Chatbot Sources/"
chunk_size = 250  # words for PDF chunks
overlap = 50
documents = []

#removes newlines and white space
def clean_text(text):
    text = text.replace('\n', ' ').strip()
    text = ' '.join(text.split())
    return text

#extract text from pdf, clean it, store it with metadata
def extract_from_pdf(file_path):
    doc_texts = []
    doc = fitz.open(file_path)
    for page_number, page in enumerate(doc):
        text = page.get_text()
        text = clean_text(text)
        if len(text) > 50:
            doc_texts.append({
                "source": os.path.basename(file_path),
                "page": page_number + 1,
                "text": text
            })
    return doc_texts

def extract_from_website(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # check if the request was successful
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()  # remove script and style elements
        text = soup.get_text(separator="\n") #handles paragraphs 
        text = clean_text(text)
        return text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return ""

#needed so that faq responses provide the answer on the website, not just the question
def chunk_text(text, chunk_size, overlap):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

#extract pdfs
for filename in os.listdir(folder_path):
    if filename.endswith(".pdf"):
        file_path = os.path.join(folder_path, filename)
        print("Processing PDF:", file_path) #debugging
        pdf_docs = extract_from_pdf(file_path)
        documents.extend(pdf_docs)

#extract websites
urls = ["https://www.wcupa.edu/hr/faqs.aspx", 
        "https://www.uscis.gov/i-9-central/form-i-9-acceptable-documents",
        "https://www.passhe.edu/hr/benefits/life-events/index.html",
        "https://www.passhe.edu/hr/benefits/retirement/voluntary-retirement-plans.html",
        "https://www.wcupa.edu/hr/FMLA.aspx",
        "https://www.wcupa.edu/hr/employee-labor-relations.aspx"]

for url in urls:
    print("Processing URL:", url) #debugging
    text = extract_from_website(url)
    if len(text) > 50:
        documents.append({
            "source": url,
            "page": 1,
            "text": text
        })
print(f"Total documents extracted: {len(documents)}") #debugging

chunks = []
metadata = []

for doc in documents:
    doc_chunks = chunk_text(doc["text"], chunk_size, overlap)
    for chunk in doc_chunks:
        chunks.append(chunk)
        metadata.append({
            "source": doc["source"],
            "page": doc["page"]
        })
print(f"Total chunks created: {len(chunks)}") #debugging

#preview and output csv  
chunks_per_source = {}
for idx, meta in enumerate(metadata):
    src = meta['source']
    if src not in chunks_per_source:
        chunks_per_source[src] = []
    chunks_per_source[src].append((chunks[idx], meta['page']))


preview_rows = []
for src, chunk_list in chunks_per_source.items():
    sample_chunks = chunk_list[:5]  # take first 5 chunks, or fewer if less
    for chunk_text, page in sample_chunks:
        preview_rows.append({
            "Document": src,
            "Page/URL": page,
            "Chunk Preview": chunk_text[:200],  # first 200 characters
            "Chunk Length": len(chunk_text.split())
        })

# create DataFrame and export to CSV
df_preview = pd.DataFrame(preview_rows)
csv_filename = "Parsing Preview.csv"
df_preview.to_csv(csv_filename, index=False)

print(f"Preview CSV saved as {csv_filename}")
print(df_preview)

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = np.array(model.encode(chunks), dtype='float32')

dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

print("FAISS index created with", index.ntotal, "vectors.") #debugging

while True:
    query = input("Enter your question (or 'exit' to quit): ")
    if query.lower() == 'exit':
        break
    query_embedding = np.array(model.encode([query]), dtype='float32')
    distances, indices = index.search(query_embedding, k=5)
    print("Top 5 relevant chunks:")
    for i, idx in enumerate(indices[0]):
        print(f"{i+1}. {chunks[idx][:500]}...")
        print(f"   Source: {metadata[idx]['source']} (Page {metadata[idx]['page']})\n")

