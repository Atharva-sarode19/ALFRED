import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import ConversationState
from app.services.llm import GenerationResult, LLMProvider, ToolCallRequest
from app.tools.registry import build_default_registry


class ScriptedLLMProvider(LLMProvider):
    """A fake LLMProvider that returns a pre-scripted sequence of results.

    Lets us test the orchestrator's tool-calling loop deterministically,
    without ever touching the real Gemini API.
    """

    def __init__(self, script: list[GenerationResult]):
        self._script = list(script)
        self.calls = 0

    async def generate(self, messages, *, system_instruction=None):
        return await self._next()

    async def generate_with_tools(self, messages, tools, *, system_instruction=None):
        return await self._next()

    async def _next(self) -> GenerationResult:
        result = self._script[self.calls]
        self.calls += 1
        return result


@pytest.mark.asyncio
async def test_direct_text_response_no_tools_needed():
    llm = ScriptedLLMProvider([GenerationResult(text="The sky is blue.", tool_calls=[])])
    orchestrator = AgentOrchestrator(llm, build_default_registry(), max_iterations=8)
    state = ConversationState(session_id="s1")

    result = await orchestrator.process(state, "Why is the sky blue?")

    assert result.response_text == "The sky is blue."
    assert result.iterations_used == 1
    assert any(step.stage == "output" for step in result.trace)


@pytest.mark.asyncio
async def test_single_tool_call_then_final_answer():
    llm = ScriptedLLMProvider(
        [
            GenerationResult(
                text=None,
                tool_calls=[ToolCallRequest(id="c1", name="calculator", arguments={"expression": "17*2"})],
            ),
            GenerationResult(text="17 times 2 is 34.", tool_calls=[]),
        ]
    )
    orchestrator = AgentOrchestrator(llm, build_default_registry(), max_iterations=8)
    state = ConversationState(session_id="s2")

    result = await orchestrator.process(state, "What is 17 times 2?")

    assert result.response_text == "17 times 2 is 34."
    assert result.iterations_used == 2
    stages = [step.stage for step in result.trace]
    assert "tool_selected" in stages
    assert "tool_result" in stages


@pytest.mark.asyncio
async def test_iteration_limit_is_enforced():
    # Model keeps requesting tool calls forever -- orchestrator must stop.
    infinite_tool_call = GenerationResult(
        text=None,
        tool_calls=[ToolCallRequest(id="cX", name="calculator", arguments={"expression": "1+1"})],
    )
    llm = ScriptedLLMProvider([infinite_tool_call] * 10)
    orchestrator = AgentOrchestrator(llm, build_default_registry(), max_iterations=3)
    state = ConversationState(session_id="s3")

    result = await orchestrator.process(state, "loop forever")

    assert result.iterations_used == 3
    assert any(step.stage == "limit_reached" for step in result.trace)


@pytest.mark.asyncio
async def test_disallowed_tool_name_is_rejected_without_executing():
    llm = ScriptedLLMProvider(
        [
            GenerationResult(
                text=None,
                tool_calls=[ToolCallRequest(id="c1", name="delete_all_files", arguments={})],
            ),
            GenerationResult(text="I can't do that.", tool_calls=[]),
        ]
    )
    orchestrator = AgentOrchestrator(llm, build_default_registry(), max_iterations=8)
    state = ConversationState(session_id="s4")

    result = await orchestrator.process(state, "delete everything")

    stages = [step.stage for step in result.trace]
    assert "tool_denied" in stages
    assert result.response_text == "I can't do that."
