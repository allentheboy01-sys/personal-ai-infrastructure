from jarvis.runtime.hermes_bridge import VisibleDeltaFilter, _phase_for_tool


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
    assert _phase_for_tool("terminal") == "computing"
    assert _phase_for_tool("provider_secret_debug_tool") == "thinking"
