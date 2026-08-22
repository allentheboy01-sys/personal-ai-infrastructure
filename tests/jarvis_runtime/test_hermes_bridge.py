import json

import pytest

from jarvis.runtime.hermes_bridge import (
    MAX_PDI_RESULT_PARSE_BYTES,
    ResourceResultCollector,
    ToolTelemetry,
    VisibleDeltaFilter,
    _extract_presentation_refs,
    _phase_for_tool,
    _tool_descriptor,
)


REFS = tuple(f"pdi:resource:00000000-0000-4000-8000-{index:012d}" for index in range(1, 12))


def _result(structured: object, *, text: str = "ignored") -> str:
    return json.dumps({"result": text, "structuredContent": structured})


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


@pytest.mark.parametrize(
    ("tool", "structured", "expected"),
    [
        ("pdi_list_recent_resources", {"ok": True, "resources": [{"resource_ref": REFS[0]}]}, (REFS[0],)),
        ("pdi_search_resources", {"ok": True, "resources": [{"resource_ref": REFS[1]}]}, (REFS[1],)),
        ("pdi_retrieve_resources", {"ok": True, "hits": [{"resource": {"resource_ref": REFS[2]}}]}, (REFS[2],)),
        ("pdi_rich_retrieve_resources", {"ok": True, "hits": [{"resource": {"resource_ref": REFS[3]}}]}, (REFS[3],)),
    ],
)
def test_presentation_tools_extract_only_their_fixed_structured_path(tool: str, structured: object, expected: tuple[str, ...]) -> None:
    assert _extract_presentation_refs(_result(structured), tool) == expected


def test_namespaced_pdi_tool_uses_the_same_exact_presentation_schema() -> None:
    collector = ResourceResultCollector()
    name = "mcp_pdi_pdi_search_resources"
    collector.start("private", name)
    collector.complete("private", name, _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    assert collector.snapshot() == (REFS[0],)


@pytest.mark.parametrize(
    ("tool", "structured"),
    [
        ("pdi_get_resource", {"ok": True, "resource": {"resource_ref": REFS[0]}}),
        ("pdi_get_resource_observations", {"ok": True, "observations": [{"subject_resource_ref": REFS[0]}]}),
        ("pdi_aggregate_resources", {"ok": True, "total_count": 1, "buckets": [{"key": "file", "count": 1}]}),
    ],
)
def test_nonpresentation_pdi_tools_never_allocate_a_snapshot(tool: str, structured: object) -> None:
    collector = ResourceResultCollector()
    collector.start("private", tool)
    collector.complete("private", tool, _result(structured))
    assert collector.snapshot() == ()


def test_extraction_ignores_text_and_arbitrary_nested_resource_refs() -> None:
    fake = REFS[0]
    structured = {"ok": True, "resources": [{"nested": {"resource_ref": fake}}, {"note": fake}]}
    assert _extract_presentation_refs(_result(structured, text=fake), "pdi_search_resources") == ()


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        json.dumps({"result": "ignored", "structuredContent": []}),
        _result({"ok": False, "resources": [{"resource_ref": REFS[0]}]}),
        _result({"ok": 1, "resources": [{"resource_ref": REFS[0]}]}),
        _result({"ok": True}),
    ],
)
def test_malformed_or_unsuccessful_result_is_not_a_successful_snapshot(raw: str) -> None:
    assert _extract_presentation_refs(raw, "pdi_search_resources") is None


def test_oversized_callback_result_is_ignored_before_json_parsing() -> None:
    raw = "{" + "x" * MAX_PDI_RESULT_PARSE_BYTES + "}"
    assert _extract_presentation_refs(raw, "pdi_search_resources") is None


def test_unencodable_callback_result_is_ignored_safely() -> None:
    assert _extract_presentation_refs("\ud800", "pdi_search_resources") is None


def test_deeply_nested_callback_result_is_ignored_safely() -> None:
    raw = "[" * 2_000 + "]" * 2_000
    assert _extract_presentation_refs(raw, "pdi_search_resources") is None


def test_ref_validation_dedupe_source_order_and_collector_bound() -> None:
    values = [REFS[2], "pdi:resource:NOT-CANONICAL", REFS[0], REFS[2], "pdi:resource:not-a-uuid", *REFS[3:]]
    rows = [{"resource_ref": value} for value in values]
    assert _extract_presentation_refs(_result({"ok": True, "resources": rows}), "pdi_list_recent_resources") == (
        REFS[2], REFS[0], *REFS[3:9]
    )


def test_latest_successful_start_ordinal_wins_even_when_callbacks_complete_out_of_order() -> None:
    collector = ResourceResultCollector()
    collector.start("first", "pdi_search_resources")
    collector.start("second", "pdi_search_resources")
    collector.complete("second", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[1]}]}))
    collector.complete("first", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    assert collector.snapshot() == (REFS[1],)


def test_later_successful_operation_replaces_earlier_success_in_normal_completion_order() -> None:
    collector = ResourceResultCollector()
    collector.start("first", "pdi_search_resources")
    collector.complete("first", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    collector.start("second", "pdi_retrieve_resources")
    collector.complete("second", "pdi_retrieve_resources", _result({"ok": True, "hits": [{"resource": {"resource_ref": REFS[1]}}]}))
    assert collector.snapshot() == (REFS[1],)


def test_newer_successful_empty_snapshot_replaces_prior_results() -> None:
    collector = ResourceResultCollector()
    collector.start("first", "pdi_search_resources")
    collector.complete("first", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    collector.start("second", "pdi_search_resources")
    collector.complete("second", "pdi_search_resources", _result({"ok": True, "resources": []}))
    assert collector.snapshot() == ()


def test_newer_malformed_result_does_not_replace_prior_success() -> None:
    collector = ResourceResultCollector()
    collector.start("first", "pdi_search_resources")
    collector.complete("first", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    collector.start("second", "pdi_search_resources")
    collector.complete("second", "pdi_search_resources", "malformed")
    assert collector.snapshot() == (REFS[0],)


def test_unmatched_or_mismatched_completion_is_suppressed() -> None:
    collector = ResourceResultCollector()
    collector.complete("missing", "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[0]}]}))
    collector.start("private", "pdi_search_resources")
    collector.complete("private", "pdi_retrieve_resources", _result({"ok": True, "hits": [{"resource": {"resource_ref": REFS[1]}}]}))
    assert collector.snapshot() == ()


def test_private_result_ordering_is_independent_of_telemetry_limit() -> None:
    writer = RecordingWriter()
    telemetry = ToolTelemetry(writer, clock=lambda: 1.0)  # type: ignore[arg-type]
    collector = ResourceResultCollector()
    for index in range(33):
        raw_id = f"private-{index}"
        telemetry.start(raw_id, "pdi_search_resources")
        collector.start(raw_id, "pdi_search_resources")
        telemetry.complete(raw_id)
        collector.complete(raw_id, "pdi_search_resources", _result({"ok": True, "resources": [{"resource_ref": REFS[index % len(REFS)]}]}))
    assert len([record for record in writer.records if record["type"] == "tool.started"]) == 32
    assert collector.snapshot() == (REFS[32 % len(REFS)],)
