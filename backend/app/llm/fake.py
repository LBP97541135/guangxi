"""不联网的 Fake Provider：对固定输入返回固定候选金句。"""

from app.llm.provider import GenerationCandidate, QuoteRequest

FAKE_QUOTE = "其实，你只是还没和自己好好和解。"

FAKE_CHAT_REPLIES = (
    "嗯，我在听。",
    "听到了。",
    "嗯嗯。",
    "我没走开。",
    "可以说慢一点，也可以停一下。",
)


def canned_chat_reply(history: list[dict]) -> str:
    """无模型/模型失败时的兜底陪伴语；按对话长度轮换，保证确定性。"""
    return FAKE_CHAT_REPLIES[len(history) % len(FAKE_CHAT_REPLIES)]


class FakeQuoteProvider:
    def generate(self, request: QuoteRequest) -> GenerationCandidate:
        return GenerationCandidate(text=FAKE_QUOTE, model="fake")

    def generate_chat_reply(self, history: list[dict]) -> str:
        return canned_chat_reply(history)
