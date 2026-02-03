from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from os import fspath

# Slither imports
from slither.slither import Slither


@dataclass(frozen=True)
class SlitherFunctionInfo:
    name: str
    signature: str
    visibility: str
    mutability: str
    modifiers: list[str]
    line: int


@dataclass(frozen=True)
class SlitherContractInfo:
    name: str
    kind: str
    file: str
    functions: list[SlitherFunctionInfo]
    has_receive: bool
    has_fallback: bool


def _fn_line(fn) -> int:
    # best-effort line number
    # slither provides source_mapping with lines often
    sm = getattr(fn, "source_mapping", None)
    if sm and getattr(sm, "lines", None):
        try:
            return int(sm.lines[0])
        except Exception:
            pass
    return 1


def build_index_with_slither(entry_path: Path) -> list[SlitherContractInfo]:
    """
    entry_path: a .sol file OR a directory.
    Slither expects a compilation target. For directories, we can point to a root .sol
    later; for now, point to the dir and let crytic-compile attempt.
    """
    s = Slither(str(entry_path))

    out: list[SlitherContractInfo] = []
    for c in s.contracts:
        # Skip duplicates from dependencies if you want later via out-of-scope filtering.
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
            if hasattr(file_path, "absolute"):
                file_path = file_path.absolute

            file_path = str(Path(fspath(file_path)).expanduser().resolve())

        has_receive = any(getattr(f, "is_receive", False) for f in c.functions)
        has_fallback = any(getattr(f, "is_fallback", False) for f in c.functions)

        funcs: list[SlitherFunctionInfo] = []
        for f in c.functions:
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
            sig = getattr(f, "full_name", None) or getattr(f, "name", "<anonymous>")
            # returns - best effort
            rets = ""
            try:
                if getattr(f, "return_type", None):
                    rets = ", ".join(str(t) for t in f.return_type)  # type strings
            except Exception:
                rets = ""

            signature = sig
            if mods:
                signature += " " + " ".join(mods)
            if rets:
                signature += f" returns ({rets})"

            funcs.append(
                SlitherFunctionInfo(
                    name=getattr(f, "name", "") or sig,
                    signature=signature,
                    visibility=vis,
                    mutability=mut,
                    modifiers=mods,
                    line=_fn_line(f),
                )
            )

        out.append(
            SlitherContractInfo(
                name=cname,
                kind=ckind,
                file=str(file_path),
                functions=sorted(funcs, key=lambda x: (x.visibility, x.name)),
                has_receive=has_receive,
                has_fallback=has_fallback,
            )
        )

    # deterministic ordering
    return sorted(out, key=lambda c: (c.file, c.name))
