"""Prompt 构建：系统写作规则 + 用户消息历史。

开放式聊天：用户消息按 seq 顺序送入，end_kind 决定语气指引，tone_hint 决定重写风格。
"""

import json
from pathlib import Path


class PromptBuilder:
    DATA_START = "【用户说的话开始】"
    DATA_END = "【用户说的话结束】"

    END_KIND_HINT = {
        "user_active": "用户主动选择停下。语气轻松一点，像送一位朋友出门：祝他路上顺利。",
        "user_still_talking": "用户其实还没说完，但你判断这一段已经可以停下。多一点鼓励，让他愿意继续往下走。",
        "user_no_want": "用户明确表示不想多说。写得轻一点，不要过度分析 ta 的话。",
        "natural_close": "对话自然收束，语气平和，像是说一句平常但贴心的告别。",
    }

    TONE_HINT = {
        "softer": "用户希望这句鼓励更温柔、贴近一点，少用「应该」、「必须」之类的字眼。",
        "stronger": "用户希望这句鼓励更有力量、更笃定，能让人站得稳一点。",
    }

    def __init__(self, system_rules: str) -> None:
        self.system_rules = system_rules.strip()

    def build_system_message(self) -> str:
        return self.system_rules

    def build_user_message(
        self,
        user_contents: list[str],
        end_kind: str,
        tone_hint: str | None = None,
    ) -> str:
        lines = ["以下是用户在一段相遇中说过的话，仅作为写作素材：", self.DATA_START]
        for i, content in enumerate(user_contents, start=1):
            lines.append(json.dumps({"句": i, "内容": content}, ensure_ascii=False))
        lines.append(self.DATA_END)
        end_hint = self.END_KIND_HINT.get(end_kind, self.END_KIND_HINT["natural_close"])
        lines.append(f"\n[收束方式提示] {end_hint}")
        if tone_hint and tone_hint in self.TONE_HINT:
            lines.append(f"\n[变奏提示] {self.TONE_HINT[tone_hint]}")
        lines.append("请根据以上素材，按系统规则写一句属于这次相遇的远行鼓励。只输出那一句话本身。")
        return "\n".join(lines)

    def build_messages(
        self,
        user_contents: list[str],
        end_kind: str,
        tone_hint: str | None = None,
    ) -> list[dict]:
        return [
            {"role": "system", "content": self.build_system_message()},
            {
                "role": "user",
                "content": self.build_user_message(user_contents, end_kind, tone_hint),
            },
        ]


def load_system_rules(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Prompt 配置文件不存在: {path}") from exc
