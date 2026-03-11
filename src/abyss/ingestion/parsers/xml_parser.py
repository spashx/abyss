# ingestion/parsers/xml_parser.py — XML parsing with 2-phase pipeline
from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llama_index.core.schema import TextNode

from .base_parser import BaseParser
from ..metadata import MetadataKeys

logger = logging.getLogger(__name__)

# Max direct children before pre-grouping (equivalent to JSON_SMALL_ARRAY_SIZE)
XML_SMALL_ELEMENT_COUNT = 10

# Elements per group when pre-chunking large child counts (equivalent to JSON_ARRAY_GROUP_SIZE)
XML_ELEMENT_GROUP_SIZE = 50


# ── Internal unit ────────────────────────────────────────────────

@dataclass
class _XmlUnit:
    """Intermediate logical unit representing one first-level XML child element."""
    tag: str               # local tag name (namespace stripped)
    xml_path: str          # e.g. "/root/ItemGroup"
    content: str           # serialised XML text of this element
    child_count: int = 0   # number of direct sub-children
    extra: dict[str, Any] = field(default_factory=dict)


# ── Parser class ─────────────────────────────────────────────────

class XmlParser(BaseParser):
    """
    Parse XML files with a 2-phase pipeline mirroring JsonParser.

    Phase 1 — _aggregate_units():
        Merge consecutive small units up to XML_CHUNK_SIZE chars.
        Units > 1.5× XML_CHUNK_SIZE are split via _split_large_unit()
        (iterates over the element's sub-children, or falls back to
        line-based splitting when the element has no children).

    Metadata per TextNode:
        xml_path        "/" | "/root/tag"
        xml_tag         local tag name
        xml_root        root element tag
        tag_count       number of XML elements in this chunk
        child_count     direct children of the element
        is_partial      True on sub-chunks from _split_large_unit
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
            MetadataKeys.LANGUAGE:   "xml",
            MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_STRUCTURED,
        }

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            logger.warning("Invalid XML %s: %s — single chunk fallback", file_path, e)
            return [TextNode(
                id_=str(uuid.uuid4()),
                text=raw,
                metadata={**base_meta, MetadataKeys.XML_PATH: "/"},
            )]

        root_tag = _local(root.tag)
        base_meta[MetadataKeys.XML_ROOT] = root_tag

        units = self._build_units(root, root_tag)
        nodes = self._aggregate_units(units, base_meta)

        logger.info("XML parsed: %s => %d chunks", file_path.name, len(nodes))
        return nodes

    # ── Phase 1 ─────────────────────────────────────────────────

    @staticmethod
    def _build_units(root: ET.Element, root_tag: str) -> list[_XmlUnit]:
        """
        Build _XmlUnit list from XML root's children.

        Small roots (≤ XML_SMALL_ELEMENT_COUNT children):
            1 unit per child.

        Large roots with homogeneous children (all same tag):
            Pre-group consecutive children into units of XML_ELEMENT_GROUP_SIZE.
            (Similar to _chunk_array in JsonParser.)

        Large roots with mixed children:
            1 unit per child (heterogeneous structure).
        """
        children = list(root)

        if len(children) <= XML_SMALL_ELEMENT_COUNT:
            return XmlParser._make_units_from_children(children, root_tag)

        # Check if all children have the same tag
        child_tags = [_local(child.tag) for child in children]
        if len(set(child_tags)) == 1:
            return XmlParser._group_children(children, root_tag, child_tags[0])

        # Mixed tags → 1 unit per child
        return XmlParser._make_units_from_children(children, root_tag)

    @staticmethod
    def _make_units_from_children(
        children: list[ET.Element], root_tag: str
    ) -> list[_XmlUnit]:
        """Create 1 _XmlUnit per child element."""
        units = []
        for child in children:
            tag = _local(child.tag)
            content = ET.tostring(child, encoding="unicode", method="xml")
            units.append(_XmlUnit(
                tag=tag,
                xml_path=f"/{root_tag}/{tag}",
                content=content,
                child_count=len(list(child)),
            ))
        return units

    @staticmethod
    def _group_children(
        children: list[ET.Element], root_tag: str, tag: str
    ) -> list[_XmlUnit]:
        """
        Pre-group consecutive children by XML_ELEMENT_GROUP_SIZE.
        Equivalent to _chunk_array in JsonParser.
        """
        units = []
        for i in range(0, len(children), XML_ELEMENT_GROUP_SIZE):
            group = children[i: i + XML_ELEMENT_GROUP_SIZE]
            end = i + len(group)
            content = "\n".join(ET.tostring(child, encoding="unicode", method="xml") for child in group)
            units.append(_XmlUnit(
                tag=tag,
                xml_path=f"/{root_tag}/{tag}_group_{i}_{end}",
                content=content,
                child_count=len(group),
                extra={"is_element_group": True, "group_start": i, "group_end": end},
            ))
        return units

    # ── Phase 2 ─────────────────────────────────────────────────

    def _aggregate_units(
        self, units: list[_XmlUnit], base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """Merge small units up to XML_CHUNK_SIZE; split oversized ones."""
        nodes: list[TextNode] = []
        bucket: list[_XmlUnit] = []
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
    def _make_node(units: list[_XmlUnit], base_meta: dict[str, Any]) -> TextNode:
        """Build a TextNode from a list of aggregated _XmlUnit."""
        content = "\n".join(u.content for u in units)
        tags = [u.tag for u in units]

        # xml_path: common prefix if same tag, else "/root/{tag1,tag2,…}"
        root = base_meta.get("xml_root", "root")
        if len(set(tags)) == 1:
            xml_path = f"/{root}/{tags[0]}"
        else:
            xml_path = f"/{root}/{{{','.join(tags)}}}"

        # Check if any unit is a group
        is_grouped = any(u.extra.get("is_element_group") for u in units)

        meta = {
            **base_meta,
            MetadataKeys.XML_PATH:    xml_path,
            MetadataKeys.XML_TAG:     tags[0] if len(set(tags)) == 1 else ",".join(tags),
            MetadataKeys.TAG_COUNT:   len(units),
            MetadataKeys.CHILD_COUNT: sum(u.child_count for u in units),
            MetadataKeys.IS_GROUPED:  is_grouped,
            MetadataKeys.START_LINE:  1,
            MetadataKeys.END_LINE:    content.count("\n") + 1,
        }
        return TextNode(id_=str(uuid.uuid4()), text=content, metadata=meta)

    def _split_large_unit(
        self, unit: _XmlUnit, base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """
        Split an oversized element:
        - Elements with children → 1 sub-chunk per child element.
        - Leaf elements          → line-based fallback.
        """
        nodes: list[TextNode] = []
        root_tag = base_meta.get("xml_root", "root")

        def _partial_node(text: str, sub_tag: str) -> TextNode:
            return TextNode(
                id_=str(uuid.uuid4()),
                text=text,
                metadata={
                    **base_meta,
                    MetadataKeys.XML_PATH:   f"/{root_tag}/{unit.tag}/{sub_tag}",
                    MetadataKeys.XML_TAG:    sub_tag,
                    MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_XML_SPLIT,
                    MetadataKeys.IS_PARTIAL: True,
                    MetadataKeys.START_LINE: 1,
                    MetadataKeys.END_LINE:   text.count("\n") + 1,
                },
            )

        try:
            element = ET.fromstring(unit.content)
        except ET.ParseError:
            return self._split_by_lines(unit, base_meta)

        children = list(element)
        if not children:
            return self._split_by_lines(unit, base_meta)

        # Aggregate children up to self.chunk_size
        bucket: list[ET.Element] = []
        bucket_size = 0

        for child in children:
            child_text = ET.tostring(child, encoding="unicode", method="xml")
            child_size = len(child_text)

            if bucket_size + child_size > self.chunk_size and bucket:
                chunk_text = "\n".join(
                    ET.tostring(e, encoding="unicode", method="xml") for e in bucket
                )
                sub_tag = _local(bucket[0].tag)
                nodes.append(_partial_node(chunk_text, sub_tag))
                bucket, bucket_size = [], 0

            bucket.append(child)
            bucket_size += child_size

        if bucket:
            chunk_text = "\n".join(
                ET.tostring(e, encoding="unicode", method="xml") for e in bucket
            )
            sub_tag = _local(bucket[0].tag)
            nodes.append(_partial_node(chunk_text, sub_tag))

        return nodes

    def _split_by_lines(
        self, unit: _XmlUnit, base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """Line-based fallback for leaf or unparseable XML elements."""
        lines = unit.content.split("\n")
        nodes: list[TextNode] = []
        current: list[str] = []
        current_size = 0
        root_tag = base_meta.get(MetadataKeys.XML_ROOT, "root")

        for line in lines:
            if current_size + len(line) > self.chunk_size and current:
                text = "\n".join(current)
                nodes.append(TextNode(
                    id_=str(uuid.uuid4()),
                    text=text,
                    metadata={
                        **base_meta,
                        MetadataKeys.XML_PATH:   f"/{root_tag}/{unit.tag}",
                        MetadataKeys.XML_TAG:    unit.tag,
                        MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_XML_SPLIT,
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
                    MetadataKeys.XML_PATH:   f"/{root_tag}/{unit.tag}",
                    MetadataKeys.XML_TAG:    unit.tag,
                    MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_XML_SPLIT,
                    MetadataKeys.IS_PARTIAL: True,
                    MetadataKeys.START_LINE: 1,
                    MetadataKeys.END_LINE:   text.count("\n") + 1,
                },
            ))

        return nodes


# ── Utility ──────────────────────────────────────────────────────

def _local(tag: str) -> str:
    """Strip Clark-notation namespace {uri} from an XML tag."""
    return tag.split("}")[-1] if "}" in tag else tag
