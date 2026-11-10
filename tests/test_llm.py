import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from pagewise import llm
from pagewise.chunk import Chunk
from pagewise.llm import ClaudeJudge, ModelUnavailable, build_message
from pagewise.retrieve import Hit

HITS = [
    Hit(Chunk("a", "https://x.test/menu/", "Menu", "Breads", "Sourdough costs 28 shekels."), 0.9, 0.9, 1.0),
    Hit(Chunk("b", "https://x.test/", "Home", "Hours", "Open Sunday to Friday."), 0.5, 0.5, 0.5),
]


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def reply(text, stop_reason="end_turn", input_tokens=1200, output_tokens=80):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=usage)


def judge_with(messages):
    return ClaudeJudge(client=SimpleNamespace(messages=messages), model="test-model")


def test_message_numbers_the_sources_and_keeps_the_question_separate():
    message = build_message("How much?", HITS)
    assert '<source id="1" page="Menu" section="Breads">' in message
    assert '<source id="2" page="Home" section="Hours">' in message
    assert message.rstrip().endswith("<question>\nHow much?\n</question>")


def test_a_correction_is_passed_to_the_model_in_its_own_block():
    message = build_message("How much?", HITS, correction="Your answer states ['35'].")
    assert message.endswith("<correction>\nYour answer states ['35'].\n</correction>")
    assert "<correction>" not in build_message("How much?", HITS)


def test_request_asks_for_structured_json_with_the_rules_in_the_system_prompt():
    messages = FakeMessages(reply(json.dumps({"answerable": True, "answer": "28 shekels.", "source_ids": [1]})))
    verdict = judge_with(messages).judge("How much?", HITS)
    assert verdict == {"answerable": True, "answer": "28 shekels.", "source_ids": [1],
                       "usage": {"input_tokens": 1200, "output_tokens": 80}}
    sent = messages.kwargs
    assert sent["model"] == "test-model" and sent["system"] == llm.SYSTEM_PROMPT
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": llm.SCHEMA}
    assert "untrusted" in llm.SYSTEM_PROMPT and "never guess" in llm.SYSTEM_PROMPT.lower()
    assert "thinking" not in sent  # the model's own adaptive thinking default is used


@pytest.mark.parametrize(
    "response",
    [
        reply("{}", stop_reason="refusal"),
        reply("{}", stop_reason="max_tokens"),
        reply("not json"),
        reply(json.dumps({"answerable": True})),  # missing fields
        SimpleNamespace(stop_reason="end_turn", content=[]),
    ],
)
def test_unusable_model_output_raises_model_unavailable(response):
    with pytest.raises(ModelUnavailable):
        judge_with(FakeMessages(response)).judge("How much?", HITS)


def test_api_errors_become_model_unavailable():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)
    with pytest.raises(ModelUnavailable):
        judge_with(FakeMessages(error=error)).judge("How much?", HITS)


def test_a_missing_api_key_is_a_model_failure_not_a_crash():
    with pytest.raises(ModelUnavailable):
        judge_with(FakeMessages(error=anthropic.AnthropicError("Could not resolve authentication method"))).judge("q", HITS)


def test_no_credentials_at_all_is_also_a_model_failure():
    error = TypeError('"Could not resolve authentication method. Expected one of api_key or auth_token to be set."')
    with pytest.raises(ModelUnavailable):
        judge_with(FakeMessages(error=error)).judge("q", HITS)


def test_a_failed_call_still_reports_the_tokens_it_used():
    for response in (reply("{}", stop_reason="refusal"), reply("{}", stop_reason="max_tokens"), reply("not json")):
        with pytest.raises(ModelUnavailable) as caught:
            judge_with(FakeMessages(response)).judge("q", HITS)
        assert caught.value.usage == {"input_tokens": 1200, "output_tokens": 80}
    with pytest.raises(ModelUnavailable) as no_usage:  # a call that never reached the API used nothing
        judge_with(FakeMessages(error=TypeError("no credentials"))).judge("q", HITS)
    assert no_usage.value.usage == {}
