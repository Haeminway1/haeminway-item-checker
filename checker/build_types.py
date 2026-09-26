#!/usr/bin/env python3
"""Build data/types.json from the 문제당 registry (74 types) and type contracts (38).

Only public structure is taken: type names, descriptions, marker/answer/choice
counts and the Korean authoring rules ("어떻게 적는가"). No items or passages.
Re-run when the registry or contracts change.
"""
import json, os, re, sys
from pathlib import Path

M = Path(os.environ.get("MUNJAEDANG_ROOT", "../munjaedang"))  # private registry; data/types.json is the published build
REG = M / "catalog/item-types/v1/registered-v3-snapshot.json"
CON = M / "catalog/generation-guides/v1/gpa-english-item-types.json"
OUT = Path(__file__).parent / "data/types.json"
HANGUL = re.compile(r"[가-힣]")
RULE_KEYS = ["intent", "display_contract", "distinction", "target_selection_rules", "prohibitions", "selection_instruction",
             "position_rule", "a_value_rule", "pair_design", "summary_structure", "choice_structure", "paraphrase_contract",
             "open_response_contract", "exclusion_contract", "stem_contract", "choice_contract", "answer_validation", "evidence"]


def korean_strings(v, out):
    if isinstance(v, str):
        if HANGUL.search(v) and 6 <= len(v) <= 220:
            out.append(v.strip())
    elif isinstance(v, list):
        for x in v:
            korean_strings(x, out)
    elif isinstance(v, dict):
        for x in v.values():
            korean_strings(x, out)


def exact(v):
    return v.get("exact") if isinstance(v, dict) else (v if isinstance(v, int) else None)


def main():
    reg = json.loads(REG.read_text())
    contracts = json.loads(CON.read_text())["type_contracts"]
    types = reg["types"] if isinstance(reg["types"], list) else list(reg["types"].values())
    out = {}
    for t in types:
        code = t["code"]
        c = dict(contracts.get(code) or {})
        if c.get("parent") and c["parent"] in contracts:  # shallow parent merge
            c = {**contracts[c["parent"]], **c}
        rules: list[str] = []
        for k in RULE_KEYS:
            if k in c:
                korean_strings(c[k], rules)
        seen, uniq = set(), []
        for r in rules:
            if r not in seen:
                seen.add(r); uniq.append(r)
        rm = c.get("required_markers") or {}
        ac = c.get("answer_contract") or {}
        out[code] = {
            "korean": t.get("korean") or code,
            "description": t.get("description") or "",
            "has_contract": code in contracts,
            "intent": c.get("intent") if isinstance(c.get("intent"), str) else t.get("description") or "",
            "rules": uniq[:8],
            "markers_exact": exact(rm.get("count")),
            "marker_labels": rm.get("labels") or [],
            "answer_count": exact(c.get("answer_count")) or exact(ac.get("answer_count")),
            "choice_count": exact(c.get("choice_count")) or exact(ac.get("choices_count")),
            "answer_form": ac.get("form") or ("free_text" if code.startswith(("OEQ", "WBK")) else "single"),
            "auxiliary": (c.get("required_auxiliary") or {}).get("fields", []),
        }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(len(out), "types,", sum(v["has_contract"] for v in out.values()), "with contracts")


if __name__ == "__main__":
    main()
