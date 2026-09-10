"""不联网的 Fake Provider：对固定输入返回固定候选金句。"""

from app.llm.provider import GenerationCandidate, QuoteRequest

FAKE_QUOTE = "其实，你只是还没和自己好好和解。"


class FakeQuoteProvider:
    def generate(self, request: QuoteRequest) -> GenerationCandidate:
        return GenerationCandidate(text=FAKE_QUOTE, model="fake")
