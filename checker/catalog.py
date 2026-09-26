"""Item types and the checks each one needs.

Everything a visitor sees (type names, rule names, why a rule applies) comes
from this file. The language model may only *select* from these ids, so a
prompt-injected item can never make the service print arbitrary text.
"""

TYPES = {
    # 수능·모의고사 객관식
    "BLANK": "빈칸 추론",
    "SUMMARY": "요약문 완성",
    "TOPIC": "주제",
    "TITLE": "제목",
    "GIST": "요지·주장",
    "PURPOSE": "글의 목적",
    "IMPLICATION": "함축 의미",
    "MOOD": "심경·분위기",
    "ORDER": "글의 순서",
    "INSERT": "문장 삽입",
    "GRAMMAR": "어법",
    "VOCAB": "어휘",
    "IRRELEVANT": "무관한 문장",
    "MATCH": "내용 일치",
    "MISMATCH": "내용 불일치",
    "REFERENCE": "지칭 대상",
    # 내신 서술형
    "WRITE": "서술형·영작",
    "REARRANGE": "단어 배열",
    "OTHER": "기타 객관식",
}

OBJECTIVE = {t for t in TYPES if t not in ("WRITE", "REARRANGE")}

# rule id -> (label, why it matters)
RULES = {
    "answer_present": ("정답 표시", "정답이 적혀 있어야 나머지 검사를 할 수 있습니다."),
    "choice_count": ("선지 개수", "객관식은 선지 5개가 기본입니다. 모자라거나 넘치면 인쇄 전에 바로잡아야 합니다."),
    "single_answer": ("정답 하나", "'가장 적절한 것 하나'를 고르는 문제에 정답이 둘 이상이면 채점이 무너집니다."),
    "answer_in_range": ("정답 번호 범위", "정답 번호가 실제 있는 선지를 가리켜야 합니다."),
    "choice_duplicate": ("중복 선지", "같은 선지가 두 번 있으면 정답이 둘이 될 수 있습니다."),
    "length_balance": ("정답 길이 티", "정답만 유독 길면 읽지 않고도 고를 수 있습니다."),
    "blank_marker": ("빈칸 표시", "지문에 빈칸이 정확히 하나 있어야 합니다."),
    "numbered_markers": ("번호 표시 ①~⑤", "지문 안에 ①~⑤가 순서대로 한 번씩 있어야 합니다."),
    "order_segments": ("(A)(B)(C) 단락", "순서 문제는 (A)(B)(C) 세 단락이 있고, 선지는 서로 다른 배열이어야 합니다."),
    "insert_given": ("주어진 문장", "삽입 문제는 넣을 문장이 따로 있고, 지문에 ①~⑤ 자리가 있어야 합니다."),
    "summary_blanks": ("요약문 (A)(B)", "요약문에 (A)(B) 빈칸이 있고, 선지가 두 칸을 짝지어야 합니다."),
    "choice_language": ("선지 언어 통일", "선지가 한국어·영어로 섞이면 기준이 흔들립니다."),
    "passage_length": ("지문 길이", "유형에 비해 지문이 너무 짧거나 길지 않은지 봅니다."),
    "stem_clear": ("발문으로 유형 확인", "발문만 읽고 무엇을 묻는지 알 수 있어야 합니다."),
    "negative_stem": ("부정 발문 강조", "'않은·틀린·NOT'을 묻는 문제는 그 말이 눈에 띄어야 실수가 줄어듭니다."),
    "answer_skew": ("정답 번호 쏠림", "여러 문제의 정답이 한 번호에 몰리면 찍어서 맞힙니다."),
    "condition_stated": ("조건 명시", "서술형은 단어 수·포함할 말 같은 조건이 발문에 있어야 채점이 흔들리지 않습니다."),
    "model_answer": ("모범 답안", "서술형은 모범 답안이 있어야 채점할 수 있습니다."),
    "word_count_match": ("단어 수 조건", "모범 답안이 발문의 단어 수 조건을 지키는지 봅니다."),
    "rearrange_words": ("배열 단어 일치", "모범 답안이 주어진 단어를 빠짐없이, 더하지 않고 썼는지 봅니다."),
    "multi_answer": ("복수 정답 의심 (AI 풀이)", "AI가 학생처럼 세 번 풀어 봤을 때, 표시한 정답 말고도 맞다고 본 선지가 있으면 정답이 둘일 수 있습니다."),
    "independent_solve": ("다시 풀어 보기 (AI 풀이)", "출제자가 아닌 사람이 풀어도 같은 답이 나와야 좋은 문제입니다. AI가 고른 답이 표시한 정답과 다르면 다시 봐야 합니다."),
    "answer_supported": ("정답 근거 (의미 검사)", "정답 선지가 지문 내용으로 뒷받침되는지 AI 추론 모델로 봅니다."),
}

# base rules per type; the model can add more from RULES
BASE = {
    "_objective": ["answer_present", "single_answer", "choice_count", "answer_in_range", "choice_duplicate", "length_balance", "stem_clear", "negative_stem", "passage_length", "multi_answer", "independent_solve"],
    "BLANK": ["blank_marker"],
    "SUMMARY": ["summary_blanks"],
    "TOPIC": ["choice_language", "answer_supported"],
    "TITLE": ["choice_language"],
    "GIST": ["choice_language", "answer_supported"],
    "PURPOSE": ["choice_language"],
    "IMPLICATION": [],
    "MOOD": [],
    "ORDER": ["order_segments"],
    "INSERT": ["insert_given", "numbered_markers"],
    "GRAMMAR": ["numbered_markers"],
    "VOCAB": ["numbered_markers"],
    "IRRELEVANT": ["numbered_markers"],
    "MATCH": ["answer_supported"],
    "MISMATCH": [],
    "REFERENCE": [],
    "OTHER": [],
    "WRITE": ["condition_stated", "model_answer", "word_count_match"],
    "REARRANGE": ["model_answer", "rearrange_words"],
}

# 발문 keywords -> type (checked in order; first hit wins)
STEM_KEYS = [
    ("SUMMARY", ["요약"]),
    ("REARRANGE", ["배열"]),
    ("WRITE", ["쓰시오", "서술", "영작", "완성하시오", "고쳐 쓰"]),
    ("BLANK", ["빈칸"]),
    ("ORDER", ["순서"]),
    ("INSERT", ["들어가기에", "들어갈 위치", "넣기에"]),
    ("GRAMMAR", ["어법"]),
    ("VOCAB", ["낱말의 쓰임", "어휘", "문맥상 적절하지 않은 것"]),
    ("IRRELEVANT", ["무관한", "관계 없는", "관계없는"]),
    ("MISMATCH", ["일치하지 않는", "일치하지않는"]),
    ("MATCH", ["일치하는"]),
    ("IMPLICATION", ["함축", "의미하는 바"]),
    ("TITLE", ["제목"]),
    ("TOPIC", ["주제"]),
    ("GIST", ["요지", "주장"]),
    ("PURPOSE", ["목적"]),
    ("MOOD", ["심경", "분위기"]),
    ("REFERENCE", ["가리키는 대상", "가리키는 것"]),
]

PASSAGE_WORDS = {  # comfortable range of passage words per type
    "_default": (60, 380),
    "ORDER": (90, 300),
    "INSERT": (90, 300),
    "SUMMARY": (100, 350),
}

# rules that only make sense for certain types; the model may not add them elsewhere
ONLY_FOR = {
    "blank_marker": {"BLANK"},
    "summary_blanks": {"SUMMARY"},
    "numbered_markers": {"INSERT", "GRAMMAR", "VOCAB", "IRRELEVANT"},
    "order_segments": {"ORDER"},
    "insert_given": {"INSERT"},
    "condition_stated": {"WRITE"},
    "model_answer": {"WRITE", "REARRANGE"},
    "word_count_match": {"WRITE"},
    "rearrange_words": {"REARRANGE"},
    "answer_present": OBJECTIVE, "single_answer": OBJECTIVE, "multi_answer": OBJECTIVE, "independent_solve": OBJECTIVE, "choice_count": OBJECTIVE, "answer_in_range": OBJECTIVE,
    "choice_duplicate": OBJECTIVE, "length_balance": OBJECTIVE, "choice_language": OBJECTIVE,
}
