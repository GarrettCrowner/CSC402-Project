## Database Collection
- PDFS -> fitz
- URLs -> requests + BeautifulSoup or newspaper3k (need to do research on these)

## Parsing
- NLTK 
    - right now i'm splitting into sentences bc that's what i've done in past
    - need to work on cleaning pdfs and deciding if splitting by sentences is best
    - might also do chunks instead of sentences

## Embeddings
- SentenceTransformer
    - just converts each sentence into a vector representation
    - if sentences have similar meanings their vectors will be closer

## Vector Database
- FAISS 
    - using right now just for testing pdf parsing accuracy, won't work with LLM
- *Chroma -> python friendly, easy to use with LLM, and allows for metadata [link](https://www.trychroma.com/)
 - Pinecone -> cloud-based 
- Weavite -> open-source and can store metadata if we want to do that 
- *PostgresSQL + pgvector -> SQL based and might be better than Chroma; we would have to use pgvector as an extension for vector search; really good for metadata, has security control, and SQL is more flexible (believe this to be the best option)
- MongoDB 
- should ask if the university or IS&T/CSM has a preference for our vector database 


## Metadata
- would allow us to filter by source and would be needed i believe if rammy responds with links corresponding to his answers
- saves the source file of the sentence and page number which might be helpful for citation reasons in responses
but also might just be really unnecessary 
- haven't added it in pdf parsing file but it should be easy to implement if we wanted

