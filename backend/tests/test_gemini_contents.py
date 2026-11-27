from app.services.gemini import _to_gemini_contents
from app.services.llm import Message, Role, ToolCallRequest


def test_parallel_tool_results_are_merged_into_one_user_turn():
    calls = [ToolCallRequest("a-0", "a", {}, thought_signature=b"sig"), ToolCallRequest("b-1", "b", {})]
    messages = [
        Message(role=Role.USER, content="hi"),
        Message(role=Role.ASSISTANT, tool_calls=calls),
        Message(role=Role.TOOL, content="ra", name="a"),
        Message(role=Role.TOOL, content="rb", name="b"),
        Message(role=Role.ASSISTANT, content="done"),
    ]
    contents = _to_gemini_contents(messages)
    assert [c["role"] for c in contents] == ["user", "model", "user", "model"]
    assert len(contents[2]["parts"]) == 2
    assert contents[2]["parts"][1]["function_response"]["name"] == "b"


def test_thought_signature_is_replayed_on_the_function_call_part():
    call = ToolCallRequest("a-0", "a", {"x": 1}, thought_signature=b"sig")
    contents = _to_gemini_contents([Message(role=Role.USER, content="hi"), Message(role=Role.ASSISTANT, tool_calls=[call])])
    assert contents[1]["parts"][0]["thought_signature"] == b"sig"
