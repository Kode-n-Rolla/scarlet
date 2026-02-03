from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .solc_ast import SolcAstResult


@dataclass(frozen=True)
class FunctionInfo:
    name: str  # includes special: constructor/receive/fallback
    signature: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int  # 1-based


@dataclass(frozen=True)
class ContractInfo:
    name: str
    kind: str  # contract/interface/library
    file: str
    functions: list[FunctionInfo]
    has_receive: bool
    has_fallback: bool


@dataclass(frozen=True)
class IndexReport:
    directory: str
    files: list[str]
    contracts: list[ContractInfo]


def _offset_to_line(src_text: str, offset: int) -> int:
    # 1-based line number
    if offset <= 0:
        return 1
    return src_text.count("\n", 0, min(offset, len(src_text))) + 1


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for it in node:
            yield from _walk(it)


def _parse_src_field(src: str) -> int:
    # "start:length:fileIndex"
    try:
        start_s, _len_s, _file_s = src.split(":")
        return int(start_s)
    except Exception:
        return 0


def _fmt_params(params_node: dict[str, Any]) -> str:
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


def build_index(scope_dir: Path, files: list[Path], ast_res: SolcAstResult) -> IndexReport:
    contracts: list[ContractInfo] = []

    for f in files:
        src_text = f.read_text(encoding="utf-8")
        ast = ast_res.ast_by_file.get(f.resolve())
        if not ast:
            continue

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

            has_receive = any(_is_receive(fn) for fn in fn_nodes)
            has_fallback = any(_is_fallback(fn) for fn in fn_nodes)

            funcs: list[FunctionInfo] = []
            for fn in fn_nodes:
                kind = fn.get("kind")  # function, constructor, receive, fallback
                name = fn.get("name") or ""
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

                params = _fmt_params(fn.get("parameters") or {})
                rets = _fmt_returns(fn.get("returnParameters") or {})

                sig = f"{display_name}({params})"
                if modifiers:
                    sig += " " + " ".join(modifiers)
                if rets:
                    sig += f" returns ({rets})"

                src_field = fn.get("src") or "0:0:0"
                start = _parse_src_field(src_field)
                line = _offset_to_line(src_text, start)

                funcs.append(
                    FunctionInfo(
                        name=display_name,
                        signature=sig,
                        visibility=visibility,
                        mutability=mutability,
                        modifiers=modifiers,
                        line=line,
                    )
                )

            # sort: visibility order + payable/nonpayable + mutability-ish
            vis_order = {"external": 0, "public": 1, "internal": 2, "private": 3}
            def sort_key(fi: FunctionInfo):
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

    return IndexReport(
        directory=str(scope_dir),
        files=[p.as_posix() for p in files],
        contracts=sorted(contracts, key=lambda c: (c.file, c.name)),
    )


def to_dict(report: IndexReport) -> dict[str, Any]:
    # dataclasses -> dict (nested)
    return asdict(report)
