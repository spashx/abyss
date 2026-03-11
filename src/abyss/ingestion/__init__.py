# ingestion/__init__.py — Public API of the ingestion package
from .ingestion_pipeline import IngestionPipeline
from .file_discovery import FileDiscovery
from .embed_builder import EmbedBuilder
from .scip_enricher import ScipEnricher

__all__ = [
    "IngestionPipeline",
    "FileDiscovery",
    "EmbedBuilder",
    "ScipEnricher",
]
