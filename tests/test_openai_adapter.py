import json

from system.hermes.openai_adapter import MODEL_ID, _completion_payload, _stream_events


def test_completion_payload_matches_openai_shape() -> None:
    payload = _completion_payload("hello", 123)

    assert payload["object"] == "chat.completion"
    assert payload["model"] == MODEL_ID
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert payload["choices"][0]["finish_reason"] == "stop"


def test_stream_events_match_openai_sse_shape() -> None:
    events = list(_stream_events("hello", 123))

    assert events[-1] == "data: [DONE]\n\n"
    role_chunk = json.loads(events[0].removeprefix("data: "))
    content_chunk = json.loads(events[1].removeprefix("data: "))
    final_chunk = json.loads(events[2].removeprefix("data: "))

    assert role_chunk["object"] == "chat.completion.chunk"
    assert role_chunk["choices"][0]["delta"] == {"role": "assistant"}
    assert content_chunk["choices"][0]["delta"] == {"content": "hello"}
    assert final_chunk["choices"][0]["finish_reason"] == "stop"
