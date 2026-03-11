# scip/scip_loader.py — Loading of the SCIP index and construction of the call graph
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import scip_pb2

logger = logging.getLogger(__name__)

# Bit 0 of the symbol_roles field = Definition
DEFINITION_ROLE = 0x1


@dataclass
class SymbolInfo:
    """Information extracted from SCIP for a symbol."""
    symbol: str                             # ex: "csharp . Orders/OrderService#ValidateOrder()."
    file_path: str                          # ex: "src/Orders/OrderService.cs"
    start_line: int = 0
    end_line: int = 0
    display_name: str = ""                  # ex: "ValidateOrder"
    kind: str = ""                          # ex: "method", "class", "property"
    documentation: list[str] = field(default_factory=list)
    enclosing: Optional[str] = None         # parent symbol (class)
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)


class ScipIndex:
    """
    Load an index.scip file (protobuf) and expose:
      - get(symbol) → SymbolInfo
      - get_by_file_line(file_path, line) → most specific SymbolInfo
      - symbols: complete dict symbol → SymbolInfo

    The call graph is reconstructed from occurrences:
      - Each non-Definition occurrence in a method = call
      - The enclosing method = caller, the referenced symbol = callee
    """

    def __init__(self, scip_path: str | Path):
        self._index = self._load(str(scip_path))
        self.symbols: dict[str, SymbolInfo] = {}
        self._build_symbol_map()
        self._build_call_graph()
        logger.info(
            "SCIP loaded: %s => %d symbols, %d documents",
            scip_path, len(self.symbols), len(self._index.documents),
        )

    # ── Loading the protobuf file ─────────────────────────────────
    @staticmethod
    def _load(path: str) -> scip_pb2.Index:
        idx = scip_pb2.Index()
        with open(path, "rb") as f:
            idx.ParseFromString(f.read())
        return idx

    # ── Building the symbol → SymbolInfo map ─────────────────────
    def _build_symbol_map(self) -> None:
        for doc in self._index.documents:
            file_path = doc.relative_path

            # 1. Create SymbolInfo from declarations
            for sym_info in doc.symbols:
                kind = self._kind_label(sym_info.kind)
                # scip-dotnet often sets kind=0; infer from symbol identifier
                if kind == "unknown":
                    kind = self._infer_kind_from_symbol(sym_info.symbol)
                info = SymbolInfo(
                    symbol=sym_info.symbol,
                    file_path=file_path,
                    display_name=sym_info.display_name or self._extract_name(sym_info.symbol),
                    kind=kind,
                    documentation=list(sym_info.documentation),
                    enclosing=sym_info.enclosing_symbol or None,
                )
                self.symbols[sym_info.symbol] = info

            # 2. Fill start_line / end_line from Definition occurrences
            for occ in doc.occurrences:
                if not (occ.symbol_roles & DEFINITION_ROLE):
                    continue
                if occ.symbol not in self.symbols:
                    continue
                r = occ.range
                sym = self.symbols[occ.symbol]
                sym.start_line = r[0]
                # range = [startLine, startChar, endLine, endChar]  (4 elements)
                # or      [startLine, startChar, endChar]           (3 elements, same line)
                sym.end_line = r[2] if len(r) == 4 else r[0]

    # ── Building the call graph ───────────────────────────────────
    def _build_call_graph(self) -> None:
        """
        Algorithm:
        1. For each document, sort Definitions by line
        2. For each non-Definition occurrence (= reference/call):
           a. Find the enclosing Definition (= caller)
           b. The referenced symbol = callee
        3. Link caller.callees ← callee, callee.callers ← caller
        """
        for doc in self._index.documents:
            # Definitions sorted by line for enclosing search
            defs = sorted(
                [o for o in doc.occurrences if o.symbol_roles & DEFINITION_ROLE],
                key=lambda o: o.range[0],
            )

            for occ in doc.occurrences:
                # Skip definitions themselves
                if occ.symbol_roles & DEFINITION_ROLE:
                    continue

                callee = occ.symbol
                caller = self._find_enclosing_symbol(defs, occ.range[0])

                if not caller or not callee or caller == callee:
                    continue

                # Link caller → callee
                if caller in self.symbols:
                    if callee not in self.symbols[caller].callees:
                        self.symbols[caller].callees.append(callee)

                # Link callee ← caller
                if callee in self.symbols:
                    if caller not in self.symbols[callee].callers:
                        self.symbols[callee].callers.append(caller)

    def _find_enclosing_symbol(
        self,
        sorted_defs: list,
        line: int,
    ) -> Optional[str]:
        """
        Return the symbol of the last Definition
        starting before or at the given line.
        """
        candidate = None
        for occ in sorted_defs:
            if occ.range[0] <= line:
                candidate = occ.symbol
            else:
                break
        return candidate

    # ── Public API ───────────────────────────────────────────────

    def get(self, symbol: str) -> Optional[SymbolInfo]:
        """Return symbol information by its SCIP identifier."""
        return self.symbols.get(symbol)

    def get_by_file_line(
        self,
        file_path: str,
        line: int,
        end_line: int = 0,
    ) -> Optional[SymbolInfo]:
        """
        Return the most specific symbol for a chunk spanning line..end_line.
        Matches if the SCIP symbol definition falls within [line, end_line],
        or if end_line==0, finds the closest symbol at or just before line.
        """
        # Normalize path (SCIP uses relative paths)
        file_candidates = [
            s for s in self.symbols.values()
            if self._path_match(s.file_path, file_path)
        ]

        if not file_candidates:
            return None

        if end_line > 0:
            # Strategy 1: find symbols whose definition falls within the chunk range
            candidates = [
                s for s in file_candidates
                if line <= s.start_line <= end_line
            ]
            if candidates:
                # Return the first symbol (earliest definition in the chunk)
                return min(candidates, key=lambda s: s.start_line)

        # Strategy 2: find the closest symbol at or just before the given line
        before = [
            s for s in file_candidates
            if s.start_line <= line
        ]
        if before:
            return max(before, key=lambda s: s.start_line)

        # Strategy 3: find the nearest symbol after the line
        after = [
            s for s in file_candidates
            if s.start_line > line
        ]
        if after:
            return min(after, key=lambda s: s.start_line)

        return None

    # ── Utilities ────────────────────────────────────────────────

    @staticmethod
    def _path_match(scip_path: str, query_path: str) -> bool:
        """Check if a SCIP relative path matches the query (absolute or relative) path.
        Compares as a suffix of normalized path segments to avoid false matches
        on files with the same name in different directories.
        """
        norm_scip = scip_path.replace("\\", "/").lower()
        norm_query = query_path.replace("\\", "/").lower()
        # Check if query path ends with the SCIP relative path
        return norm_query.endswith(norm_scip) or norm_scip.endswith(
            norm_query.rsplit("/", 1)[-1]
        )

    @staticmethod
    def _extract_name(symbol: str) -> str:
        """Extract a readable name from a SCIP identifier."""
        # e.g.: "csharp . Orders/OrderService#ValidateOrder()." → "ValidateOrder"
        parts = symbol.rstrip(".").rstrip("()").split("#")
        if len(parts) > 1:
            return parts[-1].split("/")[-1]
        return parts[-1].split("/")[-1]

    @staticmethod
    def _kind_label(kind_int: int) -> str:
        """Convert SymbolInformation.Kind enum to readable label."""
        mapping = {
            1:  "namespace",   2:  "package",
            3:  "class",       4:  "method",
            5:  "property",    6:  "field",
            7:  "constructor", 8:  "enum",
            9:  "interface",   10: "function",
            11: "variable",    12: "constant",
        }
        return mapping.get(kind_int, "unknown")

    @staticmethod
    def _infer_kind_from_symbol(symbol: str) -> str:
        """Infer kind from SCIP symbol identifier when protobuf kind is 0.
        scip-dotnet symbols follow patterns like:
          - 'scip-dotnet nuget . . Namespace/Class#'         -> class
          - 'scip-dotnet nuget . . Namespace/Class#Method().' -> method
          - 'scip-dotnet nuget . . Namespace/Class#Property.' -> property
          - 'scip-dotnet nuget . . Namespace/Class#field.'    -> field
        """
        stripped = symbol.rstrip()
        if stripped.endswith("()."):
            return "method"
        # Class symbols end with '#' (no trailing member)
        if stripped.endswith("#"):
            return "class"
        # Check for uppercase first letter after '#' (likely property) vs lowercase (field)
        parts = stripped.split("#")
        if len(parts) >= 2 and parts[-1].rstrip("."):
            member = parts[-1].rstrip(".")
            if member and member[0].isupper():
                return "property"
            return "field"
        return "unknown"
