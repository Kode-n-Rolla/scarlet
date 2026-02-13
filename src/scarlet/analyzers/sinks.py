# scarlet/analyzers/sinks.py
from __future__ import annotations

import re
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer import ContractInfo, FunctionInfo, SinkInfo

CALLS_OUT_MARKERS = (
    ".call(", ".call{", ".delegatecall(", ".staticcall(",
)

def _slice_src(src: str, start: int, length: int) -> str:
    if start <= 0 or length <= 0:
        return ""
    if start >= len(src):
        return ""
    end = min(len(src), start + length)
    return src[start:end]

def _detect_calls_out(fn_src: str) -> tuple[bool, bool]:
    if not fn_src:
        return (False, False)
    low = fn_src.lower()
    calls_out = any(m in low for m in CALLS_OUT_MARKERS)
    has_delegate = ".delegatecall(" in low
    return calls_out, has_delegate

def _detect_balanceof(fn_src: str) -> tuple[bool, bool]:
    if not fn_src:
        return (False, False)
    low = fn_src.lower()
    has = "balanceof(" in low
    compact = re.sub(r"\s+", "", low)
    self_ = "balanceof(address(this))" in compact
    return has, self_

def collect_sinks(contracts: "List[ContractInfo]", src_by_file: "Dict[str, str]") -> "List[SinkInfo]":
    from ..indexer import SinkInfo

    out: List[SinkInfo] = []

    for c in contracts:
        for fi in c.functions:
            start = getattr(fi, "src_start", 0)
            length = getattr(fi, "src_len", 0)
            decl_file = getattr(fi, "src_file", "") or c.file

            src = src_by_file.get(decl_file, "")
            fn_src = _slice_src(src, start, length)

            tags: List[str] = []

            calls_out, has_delegate = _detect_calls_out(fn_src)
            if calls_out:
                tags.append("calls-out")
            if has_delegate:
                tags.append("delegatecall")

            has_bal, has_bal_self = _detect_balanceof(fn_src)
            if has_bal:
                tags.append("balanceOf")
            if has_bal_self:
                tags.append("balanceOf:self")

            if not tags:
                continue

            out.append(
                SinkInfo(
                    contract=c.name,
                    contract_kind=c.kind,
                    file=decl_file,
                    signature=fi.signature,
                    name=fi.name,
                    visibility=fi.visibility,
                    mutability=fi.mutability,
                    modifiers=fi.modifiers,
                    line=fi.line,
                    tags=tags,
                )
            )

    return sorted(out, key=lambda s: (s.file, s.contract, s.line, s.name))
