from app.agent.orchestrator import TraceStep
from app.api.chat import TraceStepResponse


def test_duration_is_optional_and_defaults_to_none():
    assert TraceStep("input", "x").duration_ms is None
    assert TraceStepResponse(stage="input", detail="x").duration_ms is None
