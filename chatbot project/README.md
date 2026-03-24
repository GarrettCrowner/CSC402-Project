## LLM Integration

- For integration, you only need qdrant query.py to get the vector DB running so that the LLM can access it the points 
- "from query_qdrant import query_documents" should be able to connect to our LLM

## Running Database and Code
1. docker run -d --name qdrant -p 6333:6333 qdrant/qdrant (in terminal)
    - when you click on the port link in docker it just shows json, but i am able to view the database if we need to
2. docker ps
    - just make sure it's running
3. will need qdrant_query.py (don't run it yet/don't think you even need to)
4. pip install qdrant-client sentence-transformers numpy
    -install dependencies 
5. read LLM Integration bulletpoints
    - still need to do more research on integrating it 

## Future Progress
- need to figure out how to automatically pull sources every 6 months

