# context and objective

This application is a RAG MCP server based on python. It enable the end user to ingest almost any files from a directory into the chroma vector database, then use the MCP server interface to make queries on the ingested data.

It uses HuggingFaceEmbedding sentence transformers for embeddings - see embedding_service.py
The embeeding model is defined in the configuration file - see config.py. 
Chunk size and overlap are defined in the code given the properties of the model - see config.py, ingestion_pipeline.py/infer_chunk_params

Even if using Huggingface provides some advantages, cold startup of the MCP is very slow due to embedding model and service initialization. This is a pain point for the end user.

The OBJECTIVE of this feature is to MIGRATE from HugginFace to Ollama, so the model is not instanciated anymore in the application but provided by the local ollama server instead.


## Migration from HuggingFaceEmbedding to Ollama

The application SHALL use Ollama as model provider for embeddings instead of HuggingFaceEmbedding.
Regarding the infer_chunk_params, since Ollama server does not provide the embedding model properties like HuggingFace, the calculation for chunks that currently exist in the source code shall be configuration in configuration parameters into config.py/config.yaml

The code shall be adapted accordingly. The comments shall be adapted as well.


