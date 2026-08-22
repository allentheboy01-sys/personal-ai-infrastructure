from jarvis.runtime.hermes_bridge import ToolTelemetry, VisibleDeltaFilter, _phase_for_tool, _tool_descriptor


def test_reasoning_tags_never_enter_visible_deltas_even_when_split() -> None:
    visible: list[str] = []
    filter_ = VisibleDeltaFilter(visible.append)
    for chunk in ("answer <thi", "nk>private reasoning", "</thi", "nk> final"):
        filter_.feed(chunk)
    filter_.finish()
    assert "".join(visible) == "answer  final"
    assert "private reasoning" not in "".join(visible)


def test_unclosed_reasoning_is_suppressed() -> None:
    visible: list[str] = []
    filter_ = VisibleDeltaFilter(visible.append)
    filter_.feed("safe<think>never visible")
    filter_.finish()
    assert "".join(visible) == "safe"


def test_tool_phase_mapping_never_exposes_tool_name() -> None:
    assert _phase_for_tool("pdi_search_resources") == "searching"
    assert _phase_for_tool("pdi_get_resource") == "reviewing"
    assert _phase_for_tool("jarvis_exec_python") == "computing"
    assert _phase_for_tool("terminal") == "thinking"
    assert _phase_for_tool("provider_secret_debug_tool") == "thinking"


def test_exact_tool_mapping_covers_frozen_pdi_and_exec_surfaces() -> None:
    expected = {
        "pdi_list_recent_resources": ("pdi", "search_personal_resources"),
        "pdi_search_resources": ("pdi", "search_personal_resources"),
        "pdi_retrieve_resources": ("pdi", "search_personal_resources"),
        "pdi_rich_retrieve_resources": ("pdi", "search_personal_resources"),
        "pdi_get_resource": ("pdi", "read_personal_resource"),
        "pdi_get_resource_observations": ("pdi", "read_personal_resource"),
        "pdi_aggregate_resources": ("pdi", "review_personal_resources"),
        "jarvis_exec_python": ("exec", "run_python"),
        "jarvis_workspace_write_text": ("exec", "write_workspace"),
        "jarvis_workspace_read_text": ("exec", "read_workspace"),
        "jarvis_workspace_list": ("exec", "manage_workspace"),
        "jarvis_workspace_delete": ("exec", "manage_workspace"),
    }
    for name, descriptor in expected.items():
        assert _tool_descriptor(name)[:2] == descriptor
        server = "pdi" if name.startswith("pdi_") else "jarvis_exec"
        assert _tool_descriptor(f"mcp_{server}_{name}")[:2] == descriptor
    assert _tool_descriptor("pdi_search_resources_backup")[:2] == ("other", "use_tool")


class RecordingWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def emit(self, kind: str, **values: object) -> None:
        self.records.append({"type": kind, **values})


def test_tool_telemetry_matches_privately_and_emits_only_sanitized_fields() -> None:
    writer = RecordingWriter()
    clock = iter((10.0, 10.125)).__next__
    telemetry = ToolTelemetry(writer, clock=clock)  # type: ignore[arg-type]
    telemetry.start("raw-private-id", "mcp_pdi_pdi_search_resources")
    telemetry.complete("raw-private-id")

    assert writer.records == [
        {"type": "tool.started", "operation_id": 1, "category": "pdi", "capability": "search_personal_resources"},
        {"type": "tool.completed", "operation_id": 1, "category": "pdi", "capability": "search_personal_resources", "duration_ms": 125},
    ]
    serialized = repr(writer.records)
    assert "raw-private-id" not in serialized
    assert "mcp_pdi" not in serialized


def test_tool_telemetry_is_bounded_and_unmatched_completion_is_suppressed() -> None:
    writer = RecordingWriter()
    telemetry = ToolTelemetry(writer, clock=lambda: 1.0)  # type: ignore[arg-type]
    for index in range(35):
        telemetry.start(f"private-{index}", "jarvis_exec_python")
    telemetry.complete("not-started")
    for index in range(35):
        telemetry.complete(f"private-{index}")

    assert len([record for record in writer.records if record["type"] == "tool.started"]) == 32
    assert len([record for record in writer.records if record["type"] == "tool.completed"]) == 32
    assert {record["operation_id"] for record in writer.records} == set(range(1, 33))


def test_tool_duration_is_clamped_without_inspecting_results() -> None:
    writer = RecordingWriter()
    clock = iter((10.0, 700.0)).__next__
    telemetry = ToolTelemetry(writer, clock=clock)  # type: ignore[arg-type]
    telemetry.start("private", "unknown")
    telemetry.complete("private")
    assert writer.records[-1] == {
        "type": "tool.completed",
        "operation_id": 1,
        "category": "other",
        "capability": "use_tool",
        "duration_ms": 600_000,
    }
