from __future__ import annotations

from ..indexer import IndexReport, ContractInfo, FunctionInfo

import re


def _anchor_id(prefix: str, name: str) -> str:
    """
    Generate a stable markdown anchor id.
    """
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)   # replace non-alnum with -
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not s:
        s = "item"
    return f"{prefix}-{s}"


def _fmt_fn(fi: FunctionInfo) -> str:
    vis = fi.visibility or "unknown"
    mut = fi.mutability or ""
    suffix = f" [{vis}{(' ' + mut) if mut else ''}]"
    return f"- `{fi.signature}`{suffix} - line {fi.line}"

def _toc_md(contract_entries: list[tuple[str, str]]) -> list[str]:
    """
    contract_entries: list of (display_name, anchor_id)
    returns markdown lines for TOC section.
    """
    lines: list[str] = []
    lines.append("## Table of Contents")
    lines.append("- [Directory](#directory)")
    lines.append("- [Files](#files)")
    lines.append("- [Contracts](#contracts)")
    if contract_entries:
        lines.append("  - [Contracts list](#contracts-list)")
        for display, aid in contract_entries:
            lines.append(f"  - [{display}](#{aid})")
    lines.append("")
    return lines

def _toc_entrypoints_md(contract_entries: list[tuple[str, str]]) -> list[str]:
    """
    TOC for entrypoints-only report.
    contract_entries: list of (display_name, anchor_id)
    """
    lines: list[str] = []
    lines.append("## Table of Contents")
    lines.append("- [Directory](#directory)")
    lines.append("- [Files](#files)")
    lines.append("- [Entrypoints](#entrypoints)")
    if contract_entries:
        lines.append("  - [Contracts list](#entrypoints-contracts-list)")
        for display, aid in contract_entries:
            lines.append(f"  - [{display}](#{aid})")
    lines.append("")
    return lines


def render_index_md(report: IndexReport) -> str:
    lines: list[str] = []
    lines.append("# SCARLET Index Report")
    lines.append("")

    # Precompute contract anchors for TOC
    contract_entries: list[tuple[str, str]] = []
    for c in report.contracts:
        display = f"{c.name} ({c.kind})"
        aid = _anchor_id("contract", c.name)
        contract_entries.append((display, aid))

    # TOC
    lines.extend(_toc_md(contract_entries))

    # Sections with explicit anchors
    lines.append('<a id="directory"></a>')
    lines.append("## Directory")
    lines.append(f"`{report.directory}`")
    lines.append("")

    lines.append('<a id="files"></a>')
    lines.append("## Files")
    for f in report.files:
        lines.append(f"- `{f}`")
    lines.append("")

    lines.append('<a id="contracts"></a>')
    lines.append("## Contracts")
    if not report.contracts:
        lines.append("_No contracts found._")
        lines.append("")
        return "\n".join(lines)

    # Optional: add a mini list header anchor
    lines.append('<a id="contracts-list"></a>')
    lines.append("")

    for c in report.contracts:
        aid = _anchor_id("contract", c.name)
        lines.append(f'<a id="{aid}"></a>')
        lines.append(f"### {c.name} ({c.kind})")
        lines.append(f"- file: `{c.file}`")
        lines.append(f"- receive(): {'✅' if c.has_receive else '❌'}")
        lines.append(f"- fallback(): {'✅' if c.has_fallback else '❌'}")
        lines.append("")
        lines.append("**Functions**")
        for fn in c.functions:
            lines.append(_fmt_fn(fn))
        lines.append("")

    return "\n".join(lines)

def render_index_md_from_dict(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# SCARLET Index Report")
    lines.append("")

    contracts = payload.get("contracts", [])

    # Precompute contract anchors for TOC
    contract_entries: list[tuple[str, str]] = []
    for c in contracts:
        name = c.get("name", "")
        kind = c.get("kind", "contract")
        display = f"{name} ({kind})"
        aid = _anchor_id("contract", name)
        contract_entries.append((display, aid))

    # TOC
    lines.extend(_toc_md(contract_entries))

    lines.append('<a id="directory"></a>')
    lines.append("## Directory")
    lines.append(f"`{payload.get('directory','')}`")
    lines.append("")

    lines.append('<a id="files"></a>')
    lines.append("## Files")
    for f in payload.get("files", []):
        lines.append(f"- `{f}`")
    lines.append("")

    lines.append('<a id="contracts"></a>')
    lines.append("## Contracts")
    if not contracts:
        lines.append("_No contracts found._")
        return "\n".join(lines)

    lines.append('<a id="contracts-list"></a>')
    lines.append("")

    for c in contracts:
        name = c.get("name", "")
        kind = c.get("kind", "contract")
        aid = _anchor_id("contract", name)

        lines.append(f'<a id="{aid}"></a>')
        lines.append(f"### {name} ({kind})")
        lines.append(f"- file: `{c.get('file','')}`")
        lines.append(f"- receive(): {'✅' if c.get('has_receive') else '❌'}")
        lines.append(f"- fallback(): {'✅' if c.get('has_fallback') else '❌'}")
        lines.append("")
        lines.append("**Functions**")
        for fn in c.get("functions", []):
            sig = fn.get("signature", "")
            vis = fn.get("visibility", "unknown")
            mut = fn.get("mutability", "")
            line_no = fn.get("line", 1)
            suffix = f" [{vis}{(' ' + mut) if mut else ''}]"
            lines.append(f"- `{sig}`{suffix} - line {line_no}")
        lines.append("")

    return "\n".join(lines)

def render_entrypoints_md_from_dict(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# SCARLET Entrypoints Report")
    lines.append("")

    entrypoints = payload.get("entrypoints", []) or []

    # Precompute contract anchors for TOC (group by contract/kind)
    # display: "Name (kind)"
    contract_entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ep in entrypoints:
        name = ep.get("contract", "") or "<unknown>"
        kind = ep.get("contract_kind", "contract") or "contract"
        display = f"{name} ({kind})"
        aid = _anchor_id("entrypoints-contract", name)
        key = f"{name}|{kind}"
        if key not in seen:
            seen.add(key)
            contract_entries.append((display, aid))

    # TOC
    lines.extend(_toc_entrypoints_md(contract_entries))

    # Directory / Files (same anchors as index report)
    lines.append('<a id="directory"></a>')
    lines.append("## Directory")
    lines.append(f"`{payload.get('directory','')}`")
    lines.append("")

    lines.append('<a id="files"></a>')
    lines.append("## Files")
    for f in payload.get("files", []):
        lines.append(f"- `{f}`")
    lines.append("")

    lines.append('<a id="entrypoints"></a>')
    lines.append("## Entrypoints")
    if not entrypoints:
        lines.append("_No entrypoints found._")
        return "\n".join(lines)

    # Mini list anchor
    lines.append('<a id="entrypoints-contracts-list"></a>')
    lines.append("")

    def bucket(ep: dict) -> int:
        # 0: receive/fallback, 1: payable, 2: nonpayable/unknown, 3: view/pure, 4: other
        name = (ep.get("name") or "")
        mut = (ep.get("mutability") or "")
        if name in ("receive", "fallback"):
            return 0
        if mut == "payable":
            return 1
        if mut in ("view", "pure"):
            return 3
        if mut in ("nonpayable", ""):
            return 2
        return 4

    # Sort: file, contract, bucket, line
    entrypoints_sorted = sorted(
        entrypoints,
        key=lambda ep: (
            ep.get("file") or "",
            ep.get("contract") or "",
            bucket(ep),
            ep.get("line") or 0,
            ep.get("name") or "",
        ),
    )

    # Render grouped by contract
    cur_key = None
    for ep in entrypoints_sorted:
        c_name = ep.get("contract", "") or "<unknown>"
        c_kind = ep.get("contract_kind", "contract") or "contract"
        fpath = ep.get("file", "") or ""

        key = (fpath, c_name, c_kind)
        if key != cur_key:
            cur_key = key
            aid = _anchor_id("entrypoints-contract", c_name)
            lines.append(f'<a id="{aid}"></a>')
            lines.append(f"### {c_name} ({c_kind})")
            if fpath:
                lines.append(f"- file: `{fpath}`")
            lines.append("")

        sig = ep.get("signature", "") or ""
        vis = ep.get("visibility", "unknown") or "unknown"
        mut = ep.get("mutability", "") or ""
        line_no = ep.get("line", None)

        suffix = f" [{vis}{(' ' + mut) if mut else ''}]"
        loc = f" - line {line_no}" if line_no else ""
        lines.append(f"- `{sig}`{suffix}{loc}")

        tags = ep.get("tags", []) or []
        if tags:
            lines.append("  - tags: " + ", ".join(f"`{t}`" for t in tags))

        mods = ep.get("modifiers", []) or []
        if mods:
            lines.append("  - modifiers: " + ", ".join(f"`{m}`" for m in mods))
        else:
            lines.append("  - modifiers: -")

        lines.append("")

    return "\n".join(lines)
