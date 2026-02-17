from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .solc_ast import SolcAstResult

from .analyzers.entrypoints import collect_entrypoints
from .analyzers.sinks import collect_sinks

# SCARLET indexer builds a *presentation-friendly* model of the Solidity codebase.
# The goal is not full semantic analysis, but a stable, readable "map" of contracts
#   and their surfaces (functions, entrypoints, sinks) that downstream renderers can
#   consume without needing solc/slither objects.

@dataclass(frozen=True)
class FunctionInfo:
    name: str
    signature: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int  # 1-based
    # Offsets are kept to allow later features (e.g., excerpts/highlights, navigation)
    # without re-parsing AST. These values come from solc "src" field.
    src_start: int = 0
    src_len: int = 0


@dataclass(frozen=True)
class ContractInfo:
    name: str
    kind: str  # contract/interface/library
    file: str
    functions: list[FunctionInfo]
    has_receive: bool
    has_fallback: bool

@dataclass(frozen=True)
class EntrypointInfo:
    # EntrypointInfo is intentionally "flat" (no nested AST objects).
    # This makes JSON stable and keeps markdown renderers independent from solc/slither
    #   internal representations.
    contract: str
    contract_kind: str
    file: str
    signature: str
    name: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int  # 1-based
    tags: list[str]

    # future
    is_inherited: bool = False
    origin_contract: str | None = None
    state_writes: list[str] | None = None

@dataclass(frozen=True)
class SinkInfo:
    # SinkInfo follows the same "flat + stable" philosophy as EntrypointInfo.
    # It is designed as a durable data contract between analyzers and reporters.
    contract: str
    contract_kind: str
    file: str
    signature: str
    name: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int  # 1-based
    tags: list[str]

@dataclass(frozen=True)
class IndexReport:
    directory: str
    files: list[str]
    contracts: list[ContractInfo]
    entrypoints: list[EntrypointInfo] = field(default_factory=list)
    sinks: list[SinkInfo] = field(default_factory=list)


def _offset_to_line(src_text: str, offset: int) -> int:
    # 1-based line number
    # SCARLET uses line numbers as the primary UX anchor in reports.
    # Mapping offset -> line via text scan is cheap and avoids requiring solc source maps
    #   consumers to implement their own mapping logic.
    if offset <= 0:
        return 1
    return src_text.count("\n", 0, min(offset, len(src_text))) + 1


def _walk(node: Any):
    # Generic AST walk:
    #   solc AST is a nested mix of dict/list. A single robust walker keeps the rest of
    #   the code simple and reduces risk of missing nodes when solc changes schema slightly.
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for it in node:
            yield from _walk(it)


def _parse_src_field(src: str) -> tuple[int, int]:
    # solc encodes source locations as "start:length:fileIndex".
    # SCARLET only needs (start, length) here; fileIndex is ignored because the caller
    #   already knows which file's AST is being processed.
    try:
        start_s, len_s, _file_s = src.split(":")
        return int(start_s), int(len_s)
    except Exception:
        return 0, 0



def _fmt_params(params_node: dict[str, Any]) -> str:
    # Build a human-readable parameter list for signatures.
    # Important nuance: type info can appear in different places depending on solc version
    #   and the node shape. SCARLET attempts several fallbacks to keep output stable.
    params = params_node.get("parameters", []) if isinstance(params_node, dict) else []
    parts: list[str] = []
    for p in params:
        t = (p.get("typeName") or {}).get("name") or (p.get("typeName") or {}).get("typeDescriptions", {}).get("typeString")
        if not t:
            t = (p.get("typeDescriptions") or {}).get("typeString") or "unknown"
        n = p.get("name") or ""
        parts.append(f"{t} {n}".strip())
    return ", ".join(parts)


def _fmt_returns(ret_node: dict[str, Any]) -> str:
    # Returns formatting mirrors params formatting to keep signatures consistent.
    # A consistent signature string is critical because it acts as a stable identifier
    #   in reports and later (possible) cross-referencing features.
    params = ret_node.get("parameters", []) if isinstance(ret_node, dict) else []
    if not params:
        return ""
    parts: list[str] = []
    for p in params:
        t = (p.get("typeName") or {}).get("name") or (p.get("typeName") or {}).get("typeDescriptions", {}).get("typeString")
        if not t:
            t = (p.get("typeDescriptions") or {}).get("typeString") or "unknown"
        n = p.get("name") or ""
        parts.append(f"{t} {n}".strip())
    return ", ".join(parts)


def _is_receive(fn: dict[str, Any]) -> bool:
    return fn.get("kind") == "receive"

def _is_fallback(fn: dict[str, Any]) -> bool:
    return fn.get("kind") == "fallback"


def build_index(scope_dir: Path, files: list[Path], ast_res: SolcAstResult, entrypoints: bool = False, sinks: bool = False) -> IndexReport:
    # Core pipeline:
    #   1) read source text (for line mapping + analyzers that may need raw code)
    #   2) traverse solc AST for ContractDefinition/FunctionDefinition nodes
    #   3) normalize into SCARLET dataclasses (stable schema)
    #   4) optionally run analyzers (entrypoints/sinks) on the normalized model
    contracts: list[ContractInfo] = []
    src_by_file: dict[str, str] = {}

    for f in files:
        src_text = f.read_text(encoding="utf-8")
        src_by_file[f.as_posix()] = src_text
        ast = ast_res.ast_by_file.get(f.resolve())
        if not ast:
            continue
        # Missing AST for a file is treated as "skip" rather than "fatal".
        # This allows partial indexing in mixed repos (some files might fail to compile),
        #   and keeps SCARLET useful as a recon/triage tool even under imperfect setups.

        # collect per-file
        contract_nodes = [
            n for n in _walk(ast)
            if isinstance(n, dict) and n.get("nodeType") == "ContractDefinition"
        ]

        for c in contract_nodes:
            cname = c.get("name") or "<unnamed>"
            ckind = c.get("contractKind") or "contract"

            fn_nodes = [
                n for n in _walk(c)
                if isinstance(n, dict) and n.get("nodeType") == "FunctionDefinition"
            ]
            # solc represents constructor/receive/fallback as FunctionDefinition nodes too.
            # SCARLET keeps them in the same list to preserve the full external surface area
            #   and to simplify downstream sorting/rendering logic.

            has_receive = any(_is_receive(fn) for fn in fn_nodes)
            has_fallback = any(_is_fallback(fn) for fn in fn_nodes)

            funcs: list[FunctionInfo] = []
            for fn in fn_nodes:
                kind = fn.get("kind")  # function, constructor, receive, fallback
                name = fn.get("name") or ""
                # display_name is used in the signature and UI.
                # Using explicit names for constructor/receive/fallback avoids confusing
                #   empty names and matches how auditors think about these entrypoints.
                if kind == "constructor":
                    display_name = "constructor"
                elif kind == "receive":
                    display_name = "receive"
                elif kind == "fallback":
                    display_name = "fallback"
                else:
                    display_name = name or "<anonymous>"

                visibility = fn.get("visibility") or ""
                mutability = fn.get("stateMutability") or ""

                modifiers = []
                for m in fn.get("modifiers", []) or []:
                    mn = (m.get("modifierName") or {}).get("name")
                    if mn:
                        modifiers.append(mn)
                # Only modifier names are stored (not full expressions) to keep the
                #   report compact and stable. Complex modifier arguments can be added later
                #   once there is a clear UX need for them.

                params = _fmt_params(fn.get("parameters") or {})
                rets = _fmt_returns(fn.get("returnParameters") or {})

                sig = f"{display_name}({params})"
                if modifiers:
                    sig += " " + " ".join(modifiers)
                if rets:
                    sig += f" returns ({rets})"
                # Signature here is "human signature", not canonical ABI signature.
                # It is meant for reading and quick triage, not for calldata generation.

                src_field = fn.get("src") or "0:0:0"
                start, length = _parse_src_field(src_field)
                line = _offset_to_line(src_text, start)

                funcs.append(
                    FunctionInfo(
                        name=display_name,
                        signature=sig,
                        visibility=visibility,
                        mutability=mutability,
                        modifiers=modifiers,
                        line=line,
                        src_start=start,
                        src_len=length
                    )
                )

            # sort: visibility order + payable/nonpayable + mutability-ish
            vis_order = {"external": 0, "public": 1, "internal": 2, "private": 3}
            def sort_key(fi: FunctionInfo):
                # Sorting is a UX decision:
                #   - external/public first: attack surface
                #   - payable prioritized: value-flow is often high risk
                #   - view/pure next: read-only endpoints are useful for understanding state
                # This ordering makes the report feel closer to an auditor's workflow.
                v = vis_order.get(fi.visibility, 99)
                payable = 0 if fi.mutability == "payable" else 1
                # view/pure earlier (read-only), then others
                mut_rank = {"payable": 0, "view": 1, "pure": 2}.get(fi.mutability, 3)
                return (v, payable, mut_rank, fi.name)

            funcs = sorted(funcs, key=sort_key)

            contracts.append(
                ContractInfo(
                    name=cname,
                    kind=ckind,
                    file=f.as_posix(),
                    functions=funcs,
                    has_receive=has_receive,
                    has_fallback=has_fallback,
                )
            )

    eps: list[EntrypointInfo] = []
    if entrypoints:
        # Entrypoints analyzer runs on the normalized ContractInfo model + raw source.
        # Keeping analyzers on top of the normalized layer makes them reusable across
        #   different parsers (solc AST vs slither fallback).
        eps = collect_entrypoints(contracts=contracts, src_by_file=src_by_file)

    sks: list[SinkInfo] = []
    if sinks:
        # Sinks require richer context (AST-first path), but the analyzer interface
        #   stays the same to keep the rest of SCARLET pipeline consistent.
        sks = collect_sinks(contracts=contracts, src_by_file=src_by_file)

    return IndexReport(
        directory=str(scope_dir),
        files=[p.as_posix() for p in files],
        contracts=sorted(contracts, key=lambda c: (c.file, c.name)),
        entrypoints=eps,
        sinks=sks,
    )


def to_dict(report: IndexReport) -> dict[str, Any]:
    # dataclasses -> dict (nested)
    # SCARLET uses dataclasses as an internal schema boundary; converting once here
    #   keeps reporters simple and avoids leaking dataclass types into renderers/tests.
    return asdict(report)
