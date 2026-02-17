from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from os import fspath

# Slither imports
from slither.slither import Slither

# This module provides a fallback indexing layer for SCARLET.
# It is intentionally best-effort and does NOT guarantee parity with solc AST parsing.
# The goal is to recover a usable contract/function map even when solc compilation fails.

@dataclass(frozen=True)
class SlitherFunctionInfo:
    # Mirrors FunctionInfo from indexer.py but based on Slither objects.
    # Kept separate to avoid mixing solc-specific and slither-specific assumptions.
    name: str
    signature: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int
    src_start: int = 0
    src_len: int = 0
    src_file: str = ""  # file where function is defined (best-effort)


@dataclass(frozen=True)
class SlitherContractInfo:
    # Lightweight normalized representation of Slither contracts.
    # Designed so the CLI layer can later re-filter by scope and visibility
    #   without needing direct Slither objects.
    name: str
    kind: str
    file: str
    functions: list[SlitherFunctionInfo]
    has_receive: bool
    has_fallback: bool


def _fn_line(fn) -> int:
    # best-effort line number
    #   slither provides source_mapping with lines often
    #
    # Line numbers in Slither can be incomplete depending on compilation backend
    #   (crytic-compile, foundry, etc.). Returning 1 as fallback keeps reports valid
    #   and avoids None values propagating into renderers.
    sm = getattr(fn, "source_mapping", None)
    if sm and getattr(sm, "lines", None):
        try:
            return int(sm.lines[0])
        except Exception:
            pass
    return 1

def _fn_src_info(fn) -> tuple[int, int, str]:
    # Extract raw offset/length/file from Slither source_mapping.
    # These values are best-effort and may differ from solc AST offsets.
    #
    # SCARLET keeps them to preserve future compatibility with:
    #   - code excerpts
    #   - cross-linking
    #   - diff-based analysis
    sm = getattr(fn, "source_mapping", None)
    if not sm:
        return (0, 0, "")
    start = int(getattr(sm, "start", 0) or 0)
    length = int(getattr(sm, "length", 0) or 0)

    file_path = (
        getattr(sm, "filename_absolute", None)
        or getattr(sm, "filename", None)
        or getattr(sm, "filename_short", None)
        or ""
    )
    try:
        if hasattr(file_path, "absolute"):
            file_path = file_path.absolute
        # Slither may return custom filename objects (not plain str).
        # Normalizing to resolved absolute path ensures:
        #   - deterministic comparisons in CLI scope filtering
        #   - consistent JSON output across environments
        file_path = str(Path(fspath(file_path)).expanduser().resolve()) if file_path else ""
    except Exception:
        file_path = ""

    return (start, length, file_path)

def build_index_with_slither(entry_path: Path) -> list[SlitherContractInfo]:
    """
    entry_path: a .sol file OR a directory.
    Slither expects a compilation target. For directories, we can point to a root .sol
    later; for now, point to the dir and let crytic-compile attempt.
    """
    
    # IMPORTANT:
    # Slither works best when entry_path is a project root (foundry/hardhat),
    #   because crytic-compile can resolve remappings and dependencies.
    # Passing individual files may lead to partial or duplicated results.

    s = Slither(str(entry_path))

    out: list[SlitherContractInfo] = []
    for c in s.contracts:
        # Slither may include dependency contracts (lib/, node_modules/, etc.).
        # SCARLET does NOT filter here; filtering is done at CLI level after
        #   scope resolution, to keep separation of concerns.
        cname = c.name
        ckind = "contract"
        if getattr(c, "is_interface", False):
            ckind = "interface"
        elif getattr(c, "is_library", False):
            ckind = "library"

        # filename
        file_path = ""
        try:
            sm = getattr(c, "source_mapping", None)
            if sm:
                file_path = (
                    getattr(sm, "filename_absolute", None)
                    or getattr(sm, "filename", None)
                    or getattr(sm, "filename_short", None)
                    or ""
                )
        except Exception:
            file_path = ""

        if file_path:
            # Slither may return a Filename(...) object, not a str
            #
            # Normalizing here ensures that later filtering by absolute Path
            # (in CLI layer) behaves the same way as solc-based indexing.
            if hasattr(file_path, "absolute"):
                file_path = file_path.absolute

            file_path = str(Path(fspath(file_path)).expanduser().resolve())

        has_receive = any(getattr(f, "is_receive", False) for f in c.functions)
        has_fallback = any(getattr(f, "is_fallback", False) for f in c.functions)

        funcs: list[SlitherFunctionInfo] = []
        for f in c.functions:
            # Slither's function model already includes inherited functions.
            # SCARLET intentionally keeps them, because inherited public/external
            #   functions are still part of the effective attack surface.

            # public/external/internal/private
            vis = getattr(f, "visibility", "") or ""
            mut = getattr(f, "state_mutability", "") or ""
            # modifiers
            mods = []
            try:
                mods = [m.name for m in getattr(f, "modifiers", []) or [] if getattr(m, "name", None)]
            except Exception:
                mods = []

            # signature
            # Slither has full_name like "foo(uint256)"
            #
            # This is NOT the canonical ABI signature (no selector computation here).
            # It is intended for human-readable reporting only.
            sig = getattr(f, "full_name", None) or getattr(f, "name", "<anonymous>")
            # returns - best effort
            rets = ""
            try:
                if getattr(f, "return_type", None):
                    rets = ", ".join(str(t) for t in f.return_type)  # type strings
            except Exception:
                rets = ""

            signature = sig
            # Modifier names are appended for readability.
            # Complex modifier arguments are intentionally not serialized,
            # to avoid unstable or overly verbose output.
            if mods:
                signature += " " + " ".join(mods)
            if rets:
                signature += f" returns ({rets})"

            start, length, fn_file = _fn_src_info(f)

            funcs.append(
                SlitherFunctionInfo(
                    name=getattr(f, "name", "") or sig,
                    signature=signature,
                    visibility=vis,
                    mutability=mut,
                    modifiers=mods,
                    line=_fn_line(f),
                    src_start=start,
                    src_len=length,
                    src_file=fn_file,
                )
            )

        out.append(
            SlitherContractInfo(
                name=cname,
                kind=ckind,
                file=str(file_path),
                functions=sorted(funcs, key=lambda x: (x.visibility, x.name)),
                # Sorting here is simpler than solc-based path.
                # The goal is determinism, not auditor-optimized ordering.
                # Final presentation adjustments can still be done in higher layers.
                has_receive=has_receive,
                has_fallback=has_fallback,
            )
        )

    # deterministic ordering
    # Deterministic ordering is critical for:
    #   - stable JSON outputs
    #   - reproducible CI artifacts
    #   - meaningful git diffs between runs
    return sorted(out, key=lambda c: (c.file, c.name))
