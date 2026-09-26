"""Parse pasted exam items and run the deterministic checks.

No model is involved here. Every message a visitor reads is built from
catalog labels plus numbers and short spans measured in code.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from catalog import BASE, OBJECTIVE, ONLY_FOR, PASSAGE_WORDS, RULES, STEM_KEYS, TYPES

CIRCLED = "①②③④⑤⑥⑦⑧"
PAREN_CHOICE_RE = re.compile(r"^\s*(?:\(([1-5a-e])\)|([1-5a-e])\))\s*(.+)$", re.I)
ANSWER_RE = re.compile(r"^\s*(?:\[?정답\]?|답|answer|모범\s*답안|예시\s*답안)\s*[:：)\]]?\s*(.+)$", re.I)
NUM_RE = re.compile(r"^\s*(?:\[\s*(\d{1,3})\s*\]|(\d{1,3})\s*[.)번]|문제\s*(\d{1,3}))\s*")
BLANK_RE = re.compile(r"_{3,}|\(\s{2,}\)|（\s*）|\[\s{2,}\]|□")
SEG_RE = re.compile(r"^\s*\(([ABC])\)\s*(.+)$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


@dataclass
class Item:
    number: str = ""
    stem: str = ""
    passage: str = ""
    given: str = ""
    summary: str = ""
    choices: list[str] = field(default_factory=list)
    answer_raw: str = ""
    answer_index: int | None = None
    lines: list[str] = field(default_factory=list)
    judge: dict | None = None


def split_items(text: str) -> list[list[str]]:
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    groups: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        m = NUM_RE.match(ln)
        is_new = bool(m) and any(k in ln for kw in STEM_KEYS for k in kw[1]) or (bool(m) and "?" in ln)
        if is_new and any(x.strip() for x in cur):
            groups.append(cur)
            cur = []
        cur.append(ln)
    if any(x.strip() for x in cur):
        groups.append(cur)
    return groups


def answer_to_index(raw: str) -> int | None:
    raw = raw.strip()
    for i, c in enumerate(CIRCLED):
        if raw.startswith(c):
            return i
    m = re.match(r"^\(?([1-8])\)?(?:번)?\b", raw)
    if m:
        return int(m.group(1)) - 1
    m = re.match(r"^\(?([a-e])\)", raw, re.I)
    if m:
        return "abcde".index(m.group(1).lower())
    return None


def parse(lines: list[str]) -> Item:
    it = Item(lines=lines)
    body: list[str] = []
    stem_done = False
    for ln in lines:
        s = ln.strip()
        if not s:
            body.append("")
            continue
        m = ANSWER_RE.match(s)
        if m:
            it.answer_raw = m.group(1).strip()
            it.answer_index = answer_to_index(it.answer_raw)
            continue
        if not stem_done:
            nm = NUM_RE.match(s)
            if nm:
                it.number = next(g for g in nm.groups() if g)
                s = s[nm.end():].strip()
            if "?" in s or s.endswith("시오") or s.endswith("시오.") or any(k in s for _, ks in STEM_KEYS for k in ks):
                it.stem = s
                stem_done = True
                continue
        # a line that starts with ① is a choice line (passages also hold ①~⑤ markers mid-text)
        if s[0] in CIRCLED and len(s) < 240:
            parts = re.split(r"[①②③④⑤⑥⑦⑧]", s)[1:]
            it.choices.extend(p.strip() for p in parts if p.strip())
            continue
        pm = PAREN_CHOICE_RE.match(s)
        if pm and len(s) < 160 and not SEG_RE.match(s):
            it.choices.append(pm.group(3).strip())
            continue
        if "→" in s or "⇒" in s or (s.startswith("[요약]")):
            it.summary = s
            continue
        body.append(s)
    text = "\n".join(body).strip()
    # 문장 삽입: the given sentence is the first short paragraph before the passage
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) > 1 and len(paras[0]) < 260 and not any(c in paras[0] for c in CIRCLED):
        it.given = paras[0]
    it.passage = text
    return it


def detect_type(stem: str) -> str | None:
    for t, keys in STEM_KEYS:
        if any(k in stem for k in keys):
            if t == "BLANK" and "(A)" in stem and "(B)" in stem:
                return "SUMMARY"
            return t
    return None


def words(s: str) -> list[str]:
    return WORD_RE.findall(s)


# ---------------------------------------------------------------- checks
def _res(status: str, detail: str) -> tuple[str, str]:
    return status, detail


def check(rule: str, it: Item, typ: str) -> tuple[str, str]:
    ch = it.choices
    if rule == "answer_present":
        return _res("pass", f"정답: {it.answer_raw[:20]}") if it.answer_raw else _res("fail", "'정답: ③'처럼 정답 줄을 넣어 주세요.")
    if rule == "single_answer":
        if not it.answer_raw:
            return _res("skip", "정답이 없어 건너뜀")
        marks = re.findall(r"[①②③④⑤]|\b[1-5]\b", it.answer_raw)
        allow_multi = re.search(r"모두 고르|2개|두 개|있는 대로", it.stem)
        if len(marks) > 1 and not allow_multi:
            return _res("fail", f"정답이 {len(marks)}개 표시됨 ({', '.join(marks)}) — 발문은 하나를 고르게 함")
        return _res("pass", "정답 1개")
    if rule == "choice_count":
        n = len(ch)
        if n == 5:
            return _res("pass", "선지 5개")
        if n == 0:
            return _res("fail", "선지를 찾지 못했습니다. ①~⑤로 시작하는 줄로 적어 주세요.")
        return _res("warn" if n == 4 else "fail", f"선지 {n}개")
    if rule == "answer_in_range":
        if it.answer_index is None:
            return _res("warn", "정답 번호를 읽지 못했습니다.") if it.answer_raw else _res("skip", "정답이 없어 건너뜀")
        return _res("pass", f"{it.answer_index + 1}번 선지") if it.answer_index < len(ch) else _res("fail", f"정답 {it.answer_index + 1}번인데 선지는 {len(ch)}개")
    if rule == "choice_duplicate":
        norm = [re.sub(r"\s+", " ", c.lower()) for c in ch]
        dup = [c for c, n in Counter(norm).items() if n > 1]
        return _res("fail", f"같은 선지 {len(dup)}쌍") if dup else _res("pass", "중복 없음")
    if rule == "length_balance":
        if it.answer_index is None or it.answer_index >= len(ch) or len(ch) < 3:
            return _res("skip", "정답·선지가 부족해 건너뜀")
        lens = [len(c) for c in ch]
        others = [l for i, l in enumerate(lens) if i != it.answer_index]
        avg = sum(others) / len(others)
        ratio = lens[it.answer_index] / avg if avg else 1
        if ratio >= 1.5 and lens[it.answer_index] == max(lens):
            return _res("warn", f"정답이 다른 선지 평균보다 {ratio:.1f}배 깁니다")
        return _res("pass", f"정답 길이 / 평균 = {ratio:.1f}")
    if rule == "blank_marker":
        n = len(BLANK_RE.findall(it.passage))
        return _res("pass", "빈칸 1개") if n == 1 else _res("fail", f"빈칸 {n}개 (____ 로 표시)")
    if rule == "numbered_markers":
        seq = [c for c in it.passage if c in "①②③④⑤"]
        if seq == list("①②③④⑤"):
            return _res("pass", "①~⑤ 순서대로 한 번씩")
        return _res("fail", f"지문 속 번호: {''.join(seq) or '없음'}")
    if rule == "order_segments":
        segs = [m.group(1) for ln in it.passage.split("\n") if (m := SEG_RE.match(ln))]
        ok_segs = sorted(set(segs)) == ["A", "B", "C"]
        perms = [re.sub(r"[^ABC]", "", c.upper()) for c in ch]
        ok_perm = all(sorted(p) == ["A", "B", "C"] for p in perms) and len(set(perms)) == len(perms)
        if ok_segs and ok_perm:
            return _res("pass", "단락 3개, 선지 배열 모두 다름")
        return _res("fail", ("단락 " + "".join(sorted(set(segs))) if segs else "(A)(B)(C) 단락 없음") + ("" if ok_perm else " · 선지 배열 오류"))
    if rule == "insert_given":
        return _res("pass", "주어진 문장 있음") if it.given else _res("fail", "넣을 문장을 지문 앞에 한 단락으로 따로 적어 주세요.")
    if rule == "summary_blanks":
        s = it.summary or it.passage
        has = "(A)" in s and "(B)" in s
        pairs = all(re.search(r"[-–—·,/…]", c) for c in ch) if ch else False
        if has and pairs:
            return _res("pass", "(A)(B) 빈칸, 선지 짝 형식")
        return _res("fail", ("요약문에 (A)(B) 없음" if not has else "") + ("" if pairs else " 선지가 'A - B' 짝이 아님"))
    if rule == "choice_language":
        ko = [bool(re.search(r"[가-힣]", c)) for c in ch]
        if not ch:
            return _res("skip", "선지 없음")
        return _res("pass", "한국어" if all(ko) else "영어") if all(ko) or not any(ko) else _res("warn", f"한국어 {sum(ko)}개 · 영어 {len(ko) - sum(ko)}개")
    if rule == "passage_length":
        n = len(words(it.passage))
        lo, hi = PASSAGE_WORDS.get(typ, PASSAGE_WORDS["_default"])
        if n == 0:
            return _res("skip", "지문 없음")
        return _res("pass", f"{n}단어") if lo <= n <= hi else _res("warn", f"{n}단어 (보통 {lo}~{hi})")
    if rule == "stem_clear":
        return _res("pass", "발문으로 유형을 알 수 있음") if detect_type(it.stem) else _res("warn", "발문에 유형을 알려 주는 말이 없습니다")
    if rule == "negative_stem":
        neg = re.search(r"않은|않는|틀린|아닌|NOT|없는", it.stem)
        if not neg:
            return _res("pass", "부정 발문 아님")
        return _res("warn", f"'{neg.group(0)}' — 인쇄할 때 굵게·밑줄로 강조하세요")
    if rule == "condition_stated":
        cond = re.search(r"(\d+)\s*(?:단어|words?)|조건|반드시|포함|사용하여|활용하여", it.stem + it.passage)
        return _res("pass", "조건 있음") if cond else _res("warn", "단어 수·포함할 말 같은 조건이 보이지 않습니다")
    if rule == "model_answer":
        return _res("pass", "모범 답안 있음") if it.answer_raw else _res("fail", "'모범 답안: …' 줄을 넣어 주세요.")
    if rule == "word_count_match":
        m = re.search(r"(\d+)\s*(?:단어|words?)", it.stem + it.passage)
        if not m:
            return _res("skip", "단어 수 조건 없음")
        if not it.answer_raw:
            return _res("skip", "모범 답안 없음")
        need, got = int(m.group(1)), len(words(it.answer_raw))
        tail = (it.stem + it.passage)[m.end():m.end() + 6]
        if re.match(r"\s*(이내|이하|까지|내외)", tail):
            return _res("pass", f"{got}단어 (조건 {need}단어 이내)") if got <= need else _res("fail", f"조건 {need}단어 이내, 모범 답안 {got}단어")
        if re.match(r"\s*이상", tail):
            return _res("pass", f"{got}단어 (조건 {need}단어 이상)") if got >= need else _res("fail", f"조건 {need}단어 이상, 모범 답안 {got}단어")
        return _res("pass", f"{got}단어") if need == got else _res("fail", f"조건 {need}단어, 모범 답안 {got}단어")
    if rule == "rearrange_words":
        box = re.search(r"[<(\[{]([^>)\]}]*[A-Za-z][^>)\]}]*)[>)\]}]", it.passage)
        if not box or not it.answer_raw:
            return _res("skip", "주어진 단어 묶음이나 모범 답안이 없음")
        given = Counter(w.lower() for w in re.split(r"[\s/,]+", box.group(1)) if w)
        used = Counter(w.lower() for w in words(it.answer_raw))
        missing = sum((given - used).values())
        extra = sum((used - given).values())
        if missing == 0 and extra == 0:
            return _res("pass", "주어진 단어 그대로 사용")
        return _res("warn", f"빠진 단어 {missing}개 · 더한 단어 {extra}개 (어형 변화 허용이면 무시)")
    if rule in ("multi_answer", "independent_solve"):
        j = it.judge
        if not j:
            return _res("skip", "AI 풀이를 쓸 수 없어 건너뜀")
        if it.answer_index is None or it.answer_index >= len(j["correct"]):
            return _res("skip", "정답 표시가 없어 건너뜀")
        v, a = j["votes"], it.answer_index
        if rule == "multi_answer":
            if re.search(r"않은|않는|틀린|아닌|NOT|없는", it.stem):
                return _res("skip", "'틀린 것·않은 것'을 고르는 문제는 AI가 판단을 뒤집기 쉬워 아래 '다시 풀어 보기'로만 봅니다")
            # strict: it was actually picked as the answer at least once and called correct in two runs
            others = [i for i, c in enumerate(j["correct"]) if i != a and j["best"][i] >= 1 and c >= 2]
            if others:
                nums = ", ".join(CIRCLED[i] for i in others)
                return _res("warn", f"AI {v}번 풀이에서 {nums}도 정답으로 봤습니다 — 표시한 정답 {CIRCLED[a]}과 함께 다시 확인하세요")
            return _res("pass", f"AI {v}번 풀이에서 다른 선지를 확실한 정답으로 본 적 없음")
        top = max(range(len(j["best"])), key=lambda i: j["best"][i])
        if top == a:
            return _res("pass", f"AI도 {CIRCLED[a]}을 골랐습니다 ({j['best'][a]}/{v})")
        return _res("warn", f"AI는 {CIRCLED[top]}을 더 많이 골랐습니다 ({j['best'][top]}/{v}) — 표시한 정답은 {CIRCLED[a]}")
    if rule == "answer_supported":
        return _res("skip", "의미 검사는 서버 여유가 있을 때만 돕니다")
    return _res("skip", "")


REG = __import__("json").loads((__import__("pathlib").Path(__file__).parent / "data/types.json").read_text())
FAMILY_DEFAULT = {"BLANK": "BLK", "SUMMARY": "SUM", "TOPIC": "MNI_TPC", "TITLE": "MNI_TIT", "GIST": "MNI_GST",
                  "PURPOSE": "PUR", "IMPLICATION": "IMP", "MOOD": "MOD", "ORDER": "SEQ", "INSERT": "INS",
                  "GRAMMAR": "GRM", "VOCAB": "VOC", "IRRELEVANT": "IRR", "MATCH": "CON", "MISMATCH": "CON",
                  "REFERENCE": "LPS_REF", "WRITE": "OEQ_ANS", "REARRANGE": "SNT_ORD", "OTHER": "OTHER"}
PREFIX_FAMILY = [("BLK", "BLANK"), ("SUM", "SUMMARY"), ("MNI_TPC", "TOPIC"), ("MNI_TIT", "TITLE"), ("LPS_TIT", "TITLE"),
                 ("MNI_", "GIST"), ("PUR", "PURPOSE"), ("IMP", "IMPLICATION"), ("MOD", "MOOD"), ("SNT_ORD", "REARRANGE"),
                 ("SEQ", "ORDER"), ("LPS_SEQ", "ORDER"), ("INS", "INSERT"), ("GRM", "GRAMMAR"), ("VOC", "VOCAB"),
                 ("LPS_VOC", "VOCAB"), ("IRR", "IRRELEVANT"), ("CON", "MATCH"), ("LPS_CON", "MATCH"), ("NOT", "MATCH"),
                 ("CHT", "MATCH"), ("LPS_REF", "REFERENCE"), ("OEQ", "WRITE"), ("WBK", "WRITE")]


def family_of(code: str, stem: str) -> str:
    for pre, fam in PREFIX_FAMILY:
        if code.startswith(pre):
            if fam == "MATCH" and re.search(r"않는|않은|NOT", stem):
                return "MISMATCH"
            return fam
    return "WRITE" if REG.get(code, {}).get("answer_form") == "free_text" else "OTHER"


def _row(rid, label, why, status, detail, ai=False):
    return {"id": rid, "label": label, "why": why, "status": status, "detail": detail, "added_by_ai": ai}


def contract_rows(it: Item, code: str, fam: str) -> list[dict]:
    """Mechanical checks read straight from the type contract."""
    info = REG.get(code) or {}
    rows = []
    n = info.get("markers_exact")
    labels = info.get("marker_labels") or []
    if isinstance(n, int) and n > 0:
        pool = labels or list("①②③④⑤⑥⑦⑧⑨⑩")
        found = [c for c in it.passage if c in pool]
        rows.append(_row("contract_markers", f"표시 {n}개 (유형 규격)", "문제당 유형 규격이 정한 지문 속 표시 개수입니다.",
                         "pass" if len(found) == n else "fail", f"규격 {n}개 · 지문 {len(found)}개"))
    if info.get("answer_form") == "free_text":
        text = "\n".join(it.lines)
        has_var = re.search(r"허용\s*답|다른\s*정답|인정\s*답|accepted", text, re.I)
        has_note = re.search(r"채점\s*기준|채점\s*메모|부분\s*점수|감점", text)
        aux = info.get("auxiliary") or []
        if "accepted_variants" in aux:
            rows.append(_row("aux_variants", "허용 답안 (유형 규격)", "서술형은 모범 답안 말고도 인정할 답을 미리 적어 둬야 채점이 흔들리지 않습니다.",
                             "pass" if has_var else "warn", "허용 답안 있음" if has_var else "'허용 답안: …' 줄이 없습니다"))
        if "grading_note" in aux:
            rows.append(_row("aux_note", "채점 기준 (유형 규격)", "만점·부분 점수의 경계를 적어 둬야 채점자마다 점수가 달라지지 않습니다.",
                             "pass" if has_note else "warn", "채점 기준 있음" if has_note else "'채점 기준: …' 줄이 없습니다"))
    return rows


def ai_rows(it: Item, code: str, review: dict | None) -> list[dict]:
    info = REG.get(code) or {}
    if not review:
        return [_row("ai_review", "AI 검토", "AI가 직접 풀고 유형 규격으로 검토합니다.", "skip", "AI 검토를 쓸 수 없어 규칙 검사만 했습니다")]
    rows = []
    a = it.answer_index
    if "choice_verdicts" in review:
        v, best = review["choice_verdicts"], review.get("best", 0) - 1
        negative = bool(re.search(r"않은|않는|틀린|아닌|NOT|없는|부적절", it.stem))
        if a is not None and a < len(v) and negative:
            # "which is NOT/incorrect" items: per-choice verdicts flip easily, so only compare the final pick
            if 0 <= best < len(v):
                rows.append(_row("independent_solve", "다시 풀어 보기", RULES["independent_solve"][1],
                                 "pass" if best == a else "fail",
                                 f"AI도 {CIRCLED[a]}을 골랐습니다" if best == a else f"AI는 {CIRCLED[best]}을 골랐습니다 — 표시한 정답은 {CIRCLED[a]}", True))
        elif a is not None and a < len(v):
            others = [i for i, x in enumerate(v) if i != a and x == "correct"]
            arguable = [i for i, x in enumerate(v) if i != a and x == "debatable"]
            if v[a] == "wrong":
                # the marked answer itself is wrong: that is an answer error, not a multiple-answer item
                alt = others or ([best] if 0 <= best < len(v) and best != a else [])
                rows.append(_row("answer_wrong", "정답 오류 의심", "AI가 직접 풀어 보니 표시한 정답이 틀렸습니다.", "fail",
                                 f"표시한 정답 {CIRCLED[a]}은 틀렸고, {', '.join(CIRCLED[i] for i in alt)}이 정답으로 보입니다" if alt
                                 else f"표시한 정답 {CIRCLED[a]}을 정답이 아니라고 봤습니다", True))
            else:
                if others:
                    rows.append(_row("multi_answer", "복수 정답 의심", RULES["multi_answer"][1], "fail",
                                     f"표시한 정답 {CIRCLED[a]} 말고 {', '.join(CIRCLED[i] for i in others)}도 정답으로 보입니다", True))
                elif arguable:
                    rows.append(_row("multi_answer", "복수 정답 의심", RULES["multi_answer"][1], "warn",
                                     f"{', '.join(CIRCLED[i] for i in arguable)}도 논란의 여지가 있습니다", True))
                else:
                    rows.append(_row("multi_answer", "복수 정답 의심", RULES["multi_answer"][1], "pass", "다른 선지는 정답이 아니라고 봤습니다", True))
                if 0 <= best < len(v):
                    flagged = best in others or best in arguable
                    rows.append(_row("independent_solve", "다시 풀어 보기", RULES["independent_solve"][1],
                                     "pass" if best == a or flagged else "warn",
                                     f"AI도 {CIRCLED[a]}을 골랐습니다" if best == a else f"AI는 {CIRCLED[best]}을 골랐습니다 — 표시한 정답은 {CIRCLED[a]}", True))
    else:
        ac = review.get("answer_correct")
        rows.append(_row("model_answer_ok", "모범 답안 정확성", "AI가 직접 풀어 보고 모범 답안이 맞는지 봅니다.",
                         {"yes": "pass", "no": "fail", "unsure": "warn", "no_answer": "skip"}[ac],
                         {"yes": "모범 답안이 맞다고 봤습니다", "no": "모범 답안이 틀렸다고 봤습니다", "unsure": "판단이 애매합니다 — 직접 확인하세요", "no_answer": "모범 답안이 없어 건너뜀"}[ac], True))
        cm = review.get("conditions_met")
        if cm != "no_conditions":
            rows.append(_row("conditions_ai", "조건 충족", "발문의 조건(단어 수, 써야 할 말, 형태)을 모범 답안이 지키는지 봅니다.",
                             "pass" if cm == "yes" else "fail", "조건을 지킴" if cm == "yes" else "조건을 지키지 않았다고 봤습니다", True))
        oa = review.get("other_answers_acceptable")
        rows.append(_row("other_answers", "다른 정답 가능성", "서술형은 다른 표현도 만점일 수 있습니다. 미리 허용 답안에 넣어 두세요.",
                         "pass" if oa == "none" else "warn",
                         "다른 답은 만점이 어렵다고 봤습니다" if oa == "none" else ("다른 표현도 정답이 될 수 있다고 봤습니다 — 허용 답안을 적어 두세요" if oa == "some" else "정답이 될 표현이 많다고 봤습니다 — 조건을 더 좁히세요"), True))
    if review.get("stem_clear") == "no":
        rows.append(_row("stem_ai", "발문 명확성", "발문만 읽고 무엇을 묻는지 알 수 있어야 합니다.", "warn", "AI가 발문이 모호하다고 봤습니다", True))
    rules = info.get("rules") or [info.get("intent") or info.get("description", "")]
    for k, (text, vd) in enumerate(zip(rules, review.get("rule_verdicts", []))):
        short = text if len(text) <= 42 else text[:41] + "…"
        rows.append(_row(f"contract_rule_{k + 1}", short, text, {"met": "pass", "violated": "warn", "unsure": "skip"}[vd],
                         {"met": "유형 규격을 지킴", "violated": "유형 규격에 어긋난다고 봤습니다", "unsure": "판단 보류"}[vd], True))
    return rows


def run(text: str, ai=None) -> dict:
    """ai: module with classify(item) and judge(item, code), or None for rule checks only."""
    groups = split_items(text)[:10]
    items = [parse(g) for g in groups]
    out = []
    for n, it in enumerate(items, 1):
        fam = detect_type(it.stem)
        code, source = (FAMILY_DEFAULT.get(fam) if fam else None), "발문"
        if ai:
            c = ai.classify(it)
            if c:
                code, source = c, "AI 분류"
        if not code or code not in REG and code != "OTHER":
            code, source = ("OTHER" if it.choices else "OEQ_ANS"), "형식"
        fam = family_of(code, it.stem) if code in REG else (fam or ("OTHER" if it.choices else "WRITE"))
        base = (BASE["_objective"] if fam in OBJECTIVE else []) + BASE.get(fam, [])
        base = [r for r in base if r not in ("multi_answer", "independent_solve", "answer_supported")]
        rows = []
        for r in base:
            status, detail = check(r, it, fam)
            label, why = RULES[r]
            rows.append(_row(r, label, why, status, detail))
        crows = contract_rows(it, code, fam)
        if any(r["id"] == "contract_markers" for r in crows):
            rows = [r for r in rows if r["id"] != "numbered_markers"]  # the contract count is the authority
        rows += crows
        if ai and code in REG:
            rows += ai_rows(it, code, ai.judge(it, code))
        info = REG.get(code, {})
        out.append({"index": n, "number": it.number, "type": code, "type_label": info.get("korean", TYPES.get(fam, "기타")),
                    "type_intent": info.get("intent", ""), "type_source": source, "has_contract": info.get("has_contract", False),
                    "stem": it.stem[:140], "choices": len(it.choices), "words": len(words(it.passage)), "rules": rows})
    idx = [it.answer_index for it in items if it.answer_index is not None]
    skew = None
    if len(idx) >= 5:
        top, cnt = Counter(idx).most_common(1)[0]
        share = cnt / len(idx)
        skew = {"label": RULES["answer_skew"][0], "why": RULES["answer_skew"][1],
                "status": "warn" if share >= 0.4 else "pass",
                "detail": f"{top + 1}번이 {cnt}/{len(idx)}문항" + (" — 섞어 주세요" if share >= 0.4 else ""),
                "spread": [idx.count(i) for i in range(5)]}
    tally = Counter(r["status"] for x in out for r in x["rules"])
    return {"items": out, "cross": skew, "tally": {k: tally.get(k, 0) for k in ("pass", "warn", "fail", "skip")}}
