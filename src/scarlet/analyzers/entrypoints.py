from __future__ import annotations

from typing import Dict, List, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..indexer import ContractInfo, FunctionInfo, EntrypointInfo

# SCARLET entrypoints analyzer is a triage tool:
#   it labels externally reachable functions and adds lightweight security-relevant tags.
# Tags are intentionally heuristic and should be treated as "signals" (prioritize review),
#   not as proof of correctness or authorization guarantees.

GUARD_TOKENS = (
    "only", "auth", "role", "owner", "admin", "govern", "paus",
    "whitelist", "allowlist", "restricted", "operator", "keeper", "guardian",
)

ADMINISH_PREFIXES = (
    "set", "update", "upgrade", "initialize", "init", "configure", "config",
    "grant", "revoke", "authorize", "pause", "unpause", "rescue", "sweep",
)

CALLS_OUT_MARKERS = (
    ".call(", ".call{", ".delegatecall(", ".staticcall(",
)

#INLINE_GUARD_MARKERS = (
#    "msg.sender==", "msg.sender !=", "msg.sender!=", "msg.sender ==",
#    "onlyowner", "owner()", "admin", "operator", "minter", "governor"
#)


def _is_entrypoint(fi: "FunctionInfo") -> bool:
    # Entrypoint = user-reachable surface:
    #   - public/external functions
    #   - receive/fallback (implicit ETH entrypoints)
    #
    # Note: internal/private are excluded by design, even if reachable via delegatecall,
    #   because SCARLET focuses on the explicit external interface for first-pass triage.
    return fi.visibility in ("public", "external") or fi.name in ("receive", "fallback")

def _is_guarded(mods: Sequence[str]) -> bool:
    # Modifier-based guard detection is heuristic:
    #   it flags common ACL patterns (onlyOwner/onlyRole/etc.) by substring matching.
    # False positives are possible (e.g., "onlyOnce"), and false negatives too
    #   (custom ACL with unrelated names). The goal is fast prioritization.
    low = [m.lower() for m in mods]
    return any(any(tok in m for tok in GUARD_TOKENS) for m in low)

def _adminish_tag(fn_name: str) -> bool:
    # "admin-ish" is a naming heuristic: setters/upgraders/granters are often privileged.
    # This is used to highlight endpoints that deserve extra attention even if ACL
    #   detection fails (e.g., inline checks or custom modifiers).
    n = (fn_name or "").lower()
    return any(n.startswith(p) for p in ADMINISH_PREFIXES)

def _slice_src(src: str, start: int, length: int) -> str:
    # Extract a function's source slice by byte/char offset.
    # Offsets come from the parser layer:
    #   - solc AST usually provides accurate "src" start/len
    #   - slither fallback may provide best-effort offsets
    # If slicing fails, downstream tags that rely on fn_src become unavailable.
    if start <= 0 or length <= 0:
        return ""
    if start >= len(src):
        return ""
    end = min(len(src), start + length)
    return src[start:end]

def _detect_calls_out(fn_src: str) -> Tuple[bool, bool]:
    # Detect "calls-out" as a rough proxy for external interaction risk
    #   (reentrancy surfaces, trust boundaries, callbacks).
    # This is text-based and can miss cases (e.g., interfaces, assembly) or overmatch.
    if not fn_src:
        return (False, False)
    low = fn_src.lower()
    calls_out = any(m in low for m in CALLS_OUT_MARKERS)
    has_delegate = ".delegatecall(" in low
    return calls_out, has_delegate

def _has_inline_sender_guard(fn_src: str) -> bool:
    # Inline guard detection tries to catch ACL implemented via require/if checks,
    #   not via modifiers (common in minimal contracts).
    #
    # This intentionally does NOT attempt full parsing; it checks for "msg.sender"
    #   combined with control-flow keywords. It can miss complex patterns
    #   (e.g., role checks via helper functions), and can misclassify comparisons
    #   that are not authorization-related.
    if not fn_src:
        return False
    # strip whitespace for easier matching
    s = "".join(fn_src.split()).lower()
    # quick gates
    if "msg.sender" not in s:
        return False
    if "require(" not in s and "revert" not in s and "if(" not in s:
        return False
    # sender comparison patterns
    return ("msg.sender==" in s) or ("msg.sender!=" in s) or ("msg.sender<" in s) or ("msg.sender>" in s)


def _bucket_ep(name: str, mut: str) -> int:
    # Bucketing is purely for report readability (prioritization order), not severity.
    # 0: receive/fallback, 1: payable, 2: nonpayable/unknown, 3: view/pure, 4: other
    if name in ("receive", "fallback"):
        return 0
    if mut == "payable":
        return 1
    if mut in ("view", "pure"):
        return 3
    if mut in ("nonpayable", ""):
        return 2
    return 4

def collect_entrypoints(
    contracts: "List[ContractInfo]",
    src_by_file: "Dict[str, str]",
) -> "List[EntrypointInfo]":
    # Import here to avoid circular import at module load time
    from ..indexer import EntrypointInfo  # safe: indexer already loaded when calling function

    eps: List[EntrypointInfo] = []

    for c in contracts:
        for fi in c.functions:
            if not _is_entrypoint(fi):
                continue

            tags: List[str] = []

            guarded = _is_guarded(fi.modifiers)
            tags.append("guarded" if guarded else "for-all")

            if fi.mutability == "payable":
                tags.append("value")

            # --- inline guard needs fn_src, so compute it BEFORE admin-ish tagging ---
            start = getattr(fi, "src_start", 0)
            length = getattr(fi, "src_len", 0)
            
            # If analyzer knows the real file where the function is defined (slither),
            # use it. Otherwise fall back to contract file (solc path).
            decl_file = getattr(fi, "src_file", "") or c.file

            # MVP: drop inherited noise if we know function is declared in a different file
            if decl_file and c.file and decl_file != c.file:
                # Inherited functions can dominate output in large codebases.
                # For MVP, SCARLET focuses on functions declared in the contract's own file.
                # This can hide inherited entrypoints; users should switch to "full" mode
                #   or rely on solc-based indexing when inheritance accuracy is required.
                continue

            src = src_by_file.get(decl_file, "")
            fn_src = _slice_src(src, start, length)

            # Heuristic: if we can't slice function source from this contract file,
            # it's likely inherited (from a base contract in another file).
            if start > 0 and length > 0 and not fn_src:
                # skip inherited noise for MVP
                # Source slicing failure is treated as "not reliable enough to tag".
                # Skipping avoids attaching misleading inline-guard/calls-out tags.
                continue

            inline_guard = _has_inline_sender_guard(fn_src)
            if inline_guard and ("for-all" in tags):
                tags[tags.index("for-all")] = "guarded-inline"

            # --- admin-ish tagging (use guarded OR inline_guard) ---
            if _adminish_tag(fi.name):
                if guarded or inline_guard:
                    tags.append("admin-ish")
                else:
                    tags.append("admin-ish (no-guard)")
                    # This tag is intentionally alarming: it highlights endpoints that
                    #   *look* privileged by name but have no obvious ACL signal.

            calls_out, has_delegate = _detect_calls_out(fn_src)
            if calls_out:
                tags.append("calls-out")
            if has_delegate:
                tags.append("delegatecall")

            eps.append(
                EntrypointInfo(
                    contract=c.name,
                    contract_kind=c.kind,
                    file=c.file,
                    signature=fi.signature,
                    name=fi.name,
                    visibility=fi.visibility,
                    mutability=fi.mutability,
                    modifiers=fi.modifiers,
                    line=fi.line,
                    tags=tags,
                )
            )

    return sorted(
        # Deterministic sorting improves diff quality between runs and makes reports
        #   easier to scan (file -> contract -> priority bucket -> line).
        eps,
        key=lambda ep: (ep.file, ep.contract, _bucket_ep(ep.name, ep.mutability), ep.line, ep.name),
    )
