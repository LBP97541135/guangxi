"""金句校验器：非空、前缀、字数、禁词与分类式表达。

候选金句必须全部通过才可保存。校验失败原因用于日志辨识。
"""

import re


class QuoteValidator:
    PREFIX = "其实，你"

    MBTI_TYPES = (
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP",
    )

    FORBIDDEN_WORDS = (
        "MBTI",
        "九型人格",
        "人格类型",
        "白羊座", "金牛座", "双子座", "巨蟹座",
        "狮子座", "处女座", "天秤座", "天蝎座",
        "射手座", "摩羯座", "水瓶座", "双鱼座",
        "E人", "I人",
    )

    CLASSIFICATION_PATTERNS = (
        re.compile(r"你属于"),
        re.compile(r"你是.{0,6}型的人"),
        re.compile(r"你是.{0,6}类人"),
    )

    def __init__(self, max_chars: int = 50) -> None:
        self.max_chars = max_chars

    def validate(self, text: str | None) -> tuple[bool, str]:
        """返回 (是否合格, 失败原因)。"""
        if text is None or not text.strip():
            return False, "empty"
        value = text.strip()

        if not value.startswith(self.PREFIX):
            return False, "prefix"

        if len(value) > self.max_chars:
            return False, f"too_long:{len(value)}>{self.max_chars}"

        upper = value.upper()
        for token in self.MBTI_TYPES:
            if token in upper:
                return False, f"forbidden:{token}"
        for word in self.FORBIDDEN_WORDS:
            if word.upper() in upper:
                return False, f"forbidden:{word}"
        for pattern in self.CLASSIFICATION_PATTERNS:
            if pattern.search(value):
                return False, f"classification:{pattern.pattern}"

        return True, ""
