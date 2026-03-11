# ingestion/parsers/json_parser.py — JSON parsing with 2-phase pipeline
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llama_index.core.schema import TextNode

from .base_parser import BaseParser
from ..metadata import MetadataKeys

logger = logging.getLogger(__name__)

# Max items kept together in a top-level array
JSON_SMALL_ARRAY_SIZE = 10

# Items per group when chunking a large top-level array
JSON_ARRAY_GROUP_SIZE = 50


# ── Internal unit (equivalent to CodeUnit in context-lens) ──────

@dataclass
class _JsonUnit:
    """Intermediate logical unit before aggregation."""
    name: str                          # key name, "array", "root", …
    content: str                       # JSON-serialised text of this unit
    json_type: str                     # "dict" | "list" | "scalar"
    is_array: bool = False
    is_object: bool = False
    array_length: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # array_chunk metadata


# ── Parser class ─────────────────────────────────────────────────

class JsonParser(BaseParser):
    """
    Parse JSON files with a 2-phase pipeline inspired by context-lens JSONParser.

    Phase 1 — _build_units():
        dict  → 1 _JsonUnit per top-level key
        list  → groups of JSON_ARRAY_GROUP_SIZE items
                (arrays ≤ JSON_SMALL_ARRAY_SIZE → single unit)
        scalar→ 1 "root" unit containing the whole file

    Phase 2 — _aggregate_units():
        Merge consecutive small units up to self.chunk_size chars.
        Units > 1.5× self.chunk_size are split via _split_large_unit()
        before being emitted.

    Metadata per TextNode:
        json_path      "$" | "$.key" | "$.array[n:m]"
        json_key       key name (absent on array / root chunks)
        json_type      value type name
        is_array       bool (serialised as str for ChromaDB)
        is_object      bool
        keys           comma-separated key names in this chunk
        is_partial     True on sub-chunks from _split_large_unit
        start_line / end_line  (best-effort line count)
    """

    def parse(self, file_path: Path) -> list[TextNode]:
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Unable to read %s: %s", file_path, e)
            return []

        base_meta = {
            MetadataKeys.FILE_PATH:  str(file_path),
            MetadataKeys.FILE_NAME:  file_path.name,
            MetadataKeys.LANGUAGE:   "json",
            MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_STRUCTURED,
        }

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON %s: %s — single chunk fallback", file_path, e)
            return [TextNode(
                id_=str(uuid.uuid4()),
                text=raw,
                metadata={**base_meta, MetadataKeys.JSON_PATH: "$"},
            )]

        units = self._build_units(data, raw)
        nodes = self._aggregate_units(units, base_meta)

        logger.info("JSON parsed: %s => %d chunks", file_path.name, len(nodes))
        return nodes

    # ── Phase 1 ─────────────────────────────────────────────────

    def _build_units(self, data: Any, raw: str) -> list[_JsonUnit]:
        """Decompose the parsed JSON value into logical _JsonUnit list."""
        if isinstance(data, dict):
            units = []
            for key, value in data.items():
                content = json.dumps({key: value}, indent=2, ensure_ascii=False)
                units.append(_JsonUnit(
                    name=key,
                    content=content,
                    json_type=type(value).__name__,
                    is_array=isinstance(value, list),
                    is_object=isinstance(value, dict),
                    array_length=len(value) if isinstance(value, (list, dict)) else None,
                ))
            return units

        if isinstance(data, list):
            return self._chunk_array(data, "array")

        # Scalar root
        return [_JsonUnit(name="root", content=raw, json_type=type(data).__name__)]

    def _chunk_array(self, array: list[Any], name: str) -> list[_JsonUnit]:
        """Split a top-level JSON array into manageable units."""
        if len(array) <= JSON_SMALL_ARRAY_SIZE:
            content = json.dumps(array, indent=2, ensure_ascii=False)
            return [_JsonUnit(
                name=name,
                content=content,
                json_type="list",
                is_array=True,
                array_length=len(array),
            )]

        units = []
        for i in range(0, len(array), JSON_ARRAY_GROUP_SIZE):
            chunk_items = array[i: i + JSON_ARRAY_GROUP_SIZE]
            content = json.dumps(chunk_items, indent=2, ensure_ascii=False)
            end = i + len(chunk_items)
            units.append(_JsonUnit(
                name=f"{name}_items_{i}_{end}",
                content=content,
                json_type="list",
                is_array=True,
                array_length=len(chunk_items),
                extra={"is_array_chunk": True, "chunk_start": i, "chunk_end": end},
            ))
        return units

    # ── Phase 2 ─────────────────────────────────────────────────

    def _aggregate_units(
        self, units: list[_JsonUnit], base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """Merge small units up to JSON_CHUNK_SIZE; split oversized ones."""
        nodes: list[TextNode] = []
        bucket: list[_JsonUnit] = []
        bucket_size = 0

        for unit in units:
            unit_size = len(unit.content)

            if unit_size > self.chunk_size * 1.5:
                if bucket:
                    nodes.append(self._make_node(bucket, base_meta))
                    bucket, bucket_size = [], 0
                nodes.extend(self._split_large_unit(unit, base_meta))
                continue

            if bucket_size + unit_size > self.chunk_size and bucket:
                nodes.append(self._make_node(bucket, base_meta))
                bucket, bucket_size = [], 0

            bucket.append(unit)
            bucket_size += unit_size

        if bucket:
            nodes.append(self._make_node(bucket, base_meta))

        return nodes

    @staticmethod
    def _make_node(units: list[_JsonUnit], base_meta: dict[str, Any]) -> TextNode:
        """Build a TextNode from a list of aggregated _JsonUnit."""
        # Re-merge into a single JSON object if all units are dict-key units
        combined: dict[str, Any] = {}
        for u in units:
            try:
                parsed = json.loads(u.content)
                if isinstance(parsed, dict):
                    combined.update(parsed)
            except json.JSONDecodeError:
                pass

        if combined:
            content = json.dumps(combined, indent=2, ensure_ascii=False)
        else:
            content = "\n".join(u.content for u in units)

        keys = [u.name for u in units]
        json_path = "$.{" + ",".join(keys) + "}" if len(keys) > 1 else f"$.{keys[0]}"

        meta = {
            **base_meta,
            MetadataKeys.JSON_PATH:  json_path,
            MetadataKeys.JSON_KEYS:  ",".join(keys),
            MetadataKeys.JSON_TYPE:  units[0].json_type,
            MetadataKeys.IS_ARRAY:   str(units[0].is_array),
            MetadataKeys.IS_OBJECT:  str(units[0].is_object),
            MetadataKeys.START_LINE: 1,
            MetadataKeys.END_LINE:   content.count("\n") + 1,
        }
        if len(keys) == 1:
            meta[MetadataKeys.JSON_KEY] = keys[0]

        return TextNode(id_=str(uuid.uuid4()), text=content, metadata=meta)

    def _split_large_unit(
        self, unit: _JsonUnit, base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """
        Split an oversized unit:
        - dict  → iterate over keys, flush when >= JSON_CHUNK_SIZE
        - list  → groups of 20 items
        - other → line-based fallback
        """
        nodes: list[TextNode] = []

        def _partial_node(text: str, extra_meta: dict[str, Any]) -> TextNode:
            return TextNode(
                id_=str(uuid.uuid4()),
                text=text,
                metadata={
                    **base_meta,
                    MetadataKeys.JSON_PATH:  f"$.{unit.name}",
                    MetadataKeys.JSON_KEY:   unit.name,
                    MetadataKeys.IS_PARTIAL: True,
                    MetadataKeys.START_LINE: 1,
                    MetadataKeys.END_LINE:   text.count("\n") + 1,
                    **extra_meta,
                },
            )

        try:
            data = json.loads(unit.content)
        except json.JSONDecodeError:
            return self._split_by_lines(unit, base_meta)

        if isinstance(data, dict):
            chunk_data: dict[str, Any] = {}
            bucket_size = 0
            for key, value in data.items():
                entry = json.dumps({key: value}, ensure_ascii=False)
                if bucket_size + len(entry) > self.chunk_size and chunk_data:
                    nodes.append(_partial_node(
                        json.dumps(chunk_data, indent=2, ensure_ascii=False),
                        {MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_JSON_SPLIT},
                    ))
                    chunk_data, bucket_size = {}, 0
                chunk_data[key] = value
                bucket_size += len(entry)
            if chunk_data:
                nodes.append(_partial_node(
                    json.dumps(chunk_data, indent=2, ensure_ascii=False),
                    {MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_JSON_SPLIT},
                ))

        elif isinstance(data, list):
            group = 20
            for i in range(0, len(data), group):
                items = data[i: i + group]
                nodes.append(_partial_node(
                    json.dumps(items, indent=2, ensure_ascii=False),
                    {MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_JSON_ARRAY_SPLIT, "array_range": f"{i}-{i+len(items)}"},
                ))
        else:
            return self._split_by_lines(unit, base_meta)

        return nodes

    def _split_by_lines(
        self, unit: _JsonUnit, base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """Line-based fallback for invalid/unparseable JSON units."""
        lines = unit.content.split("\n")
        nodes: list[TextNode] = []
        current: list[str] = []
        current_size = 0

        for line in lines:
            if current_size + len(line) > self.chunk_size and current:
                text = "\n".join(current)
                nodes.append(TextNode(
                    id_=str(uuid.uuid4()),
                    text=text,
                    metadata={
                        **base_meta,
                        MetadataKeys.JSON_PATH:  f"$.{unit.name}",
                        MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_JSON_SPLIT,
                        MetadataKeys.IS_PARTIAL: True,
                        MetadataKeys.START_LINE: 1,
                        MetadataKeys.END_LINE:   text.count("\n") + 1,
                    },
                ))
                current, current_size = [line], len(line)
            else:
                current.append(line)
                current_size += len(line)

        if current:
            text = "\n".join(current)
            nodes.append(TextNode(
                id_=str(uuid.uuid4()),
                text=text,
                metadata={
                    **base_meta,
                    MetadataKeys.JSON_PATH:  f"$.{unit.name}",
                    MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_JSON_SPLIT,
                    MetadataKeys.IS_PARTIAL: True,
                    MetadataKeys.START_LINE: 1,
                    MetadataKeys.END_LINE:   text.count("\n") + 1,
                },
            ))

        return nodes
