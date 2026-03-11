# ingestion/parsers/base_parser.py — Abstract base class for all parsers
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from llama_index.core.schema import TextNode


class BaseParser(ABC):
    """
    Common contract for all file parsers in the ingestion pipeline.

    Each parser is responsible for:
    - Reading a file from disk
    - Splitting it into chunks appropriate to its format
    - Returning a list of TextNode with populated metadata

    Required metadata keys per TextNode:
        file_path  (str)   : absolute path of the source file
        file_name  (str)   : file name with extension
        chunk_type (str)   : 'code' | 'document' | 'structured'
        start_line (int)   : 1-based start line (when applicable)
        end_line   (int)   : 1-based end line (when applicable)
    """

    def __init__(self, chunk_size: int = 1_000, chunk_overlap: int = 200) -> None:
        """
        Initialize the parser with chunking parameters.

        Args:
            chunk_size:    Target chunk size in characters. Derived at runtime
                           from the embedding model's max_seq_length × 4.
            chunk_overlap: Overlap in characters for text-based splitting.
                           Typically chunk_size // 5.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def parse(self, file_path: Path) -> list[TextNode]:
        """
        Parse a file and return a list of TextNode chunks.

        Args:
            file_path: Absolute path to the file to parse.

        Returns:
            List of TextNode. Empty list if the file cannot be parsed.
        """
        ...
