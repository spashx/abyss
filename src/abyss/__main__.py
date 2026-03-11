# __main__.py — MCP Server entry point
import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from mcp.server.stdio import stdio_server

from .config import (
    ABYSS_LOG_LEVEL,
    CHROMADB_LOG_LEVEL,
    HTTPX_LOG_LEVEL,
    LLAMA_INDEX_LOG_LEVEL,
)
from .server import create_server


async def _run():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def _parse_log_level(level_string: str) -> int:
    """
    Convert a logging level string to a logging module constant.
    
    Args:
        level_string: One of "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    
    Returns:
        Corresponding logging level constant (e.g., logging.INFO)
    """
    return getattr(logging, level_string.upper(), logging.INFO)


def main():
    # ── Configure root logger (controls stderr output) ────────────────────────────
    # The ABYSS_LOG_LEVEL from config.yaml determines verbosity of all logs
    # (file_handler below logs everything at DEBUG regardless of this setting)
    abyss_log_level = _parse_log_level(ABYSS_LOG_LEVEL)
    
    logging.basicConfig(
        level=abyss_log_level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    # ── Silence noisy dependencies (per-logger configuration) ─────────────────────
    # Each of these loggers can be independently controlled via config.yaml:
    #   chromadb_log_level, httpx_log_level, llama_index_log_level
    # By default, they're set to INFO to suppress DEBUG-level spam.
    
    chromadb_level = _parse_log_level(CHROMADB_LOG_LEVEL)
    logging.getLogger("chromadb").setLevel(chromadb_level)
    
    httpx_level = _parse_log_level(HTTPX_LOG_LEVEL)
    logging.getLogger("httpx").setLevel(httpx_level)
    
    llama_index_level = _parse_log_level(LLAMA_INDEX_LOG_LEVEL)
    logging.getLogger("llama_index.core.node_parser.node_utils").setLevel(llama_index_level)

    # ── Configure file logging (always DEBUG) ──────────────────────────────────────
    # File handler always writes DEBUG and above, independent of stderr log level.
    # 10MB rotating files with 5 backups: abyss.log, abyss.log.1, abyss.log.2, ...
    # The log file is truncated on each startup (see below).
    
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", "abyss.log")
    
    # Clear the log file on startup (fresh session)
    open(log_file, 'w').close()
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(abyss_log_level)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    logging.getLogger().addHandler(file_handler)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
