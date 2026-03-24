import os
from minio import Minio

pdf_folder = "/Users/marissavilanova/Desktop/Chatbot Sources"
bucket_name = "documents"

## minio connection
minio_client = Minio(
    access_key="minioadmin",
    secret_key="minioadmin",
    secure = False
)

if not minio_client.bucket_exists(bucket_name):
    minio_client.make_bucket(bucket_name)

## upload pdfs to minio
print("Uploading PDFs to Minio...")
for filename in os.listdir(pdf_folder):
    if filename.endswith(".pdf"):
        file_path = os.path.join(pdf_folder, filename)
        with open(file_path, "rb") as f:
            minio_client.put_object(bucket_name, filename, data=f, length=os.path.getsize(file_path), content_type="application/pdf")
print("Upload complete.")





