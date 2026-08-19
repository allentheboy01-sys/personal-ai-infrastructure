from jarvis.pdi_client.projection import provider_detail, project_providers, project_resource, project_resource_detail, project_resource_page


def source(provider="immich", mime="image/jpeg", size=1200):
    return {"provider": provider, "location": "must-not-leak", "name": "external", "mime_type": mime, "size_bytes": size, "is_active": True}


def resource(resource_type="file", provider="immich", mime="image/jpeg"):
    return {"resource_ref": "pdi:resource:11111111-1111-4111-8111-111111111111", "resource_type": resource_type, "display_name": "Safe title", "pdi_first_observed_at": "2026-01-01T00:00:00+00:00", "sources": [source(provider, mime)], "raw_observations": {"secret": "never"}, "checksum": "never"}


def test_resource_renderers_and_capabilities_are_content_driven():
    image = project_resource(resource())
    document = project_resource(resource(provider="nextcloud", mime="application/pdf"))
    message = project_resource(resource("message", "gmail", "message/rfc822"))
    generic = project_resource(resource(provider="nextcloud", mime="application/octet-stream"))
    assert [image.presentation_kind, document.presentation_kind, message.presentation_kind, generic.presentation_kind] == ["image", "document", "message", "generic"]
    assert image.capabilities.preview is True
    assert document.capabilities.preview is message.capabilities.preview is False


def test_detail_is_allowlisted_and_message_body_is_unavailable():
    raw = resource("message", "gmail", "message/rfc822")
    raw["body"] = "private body"
    detail = project_resource_detail({"ok": True, "resource": raw})
    serialized = repr(detail)
    assert "private body" not in serialized and "must-not-leak" not in serialized and "never" not in serialized
    assert detail.notice and "metadata only" in detail.notice


def test_page_preserves_transport_cursor_without_raw_payload():
    page = project_resource_page({"ok": True, "resources": [resource()], "next_cursor": "opaque"})
    assert page.next_cursor == "opaque" and len(page.resources) == 1


def pipeline(key, status="succeeded", success="2026-01-01T00:00:00+00:00", valid=True):
    return {"pipeline_key": key, "latest_status": status, "last_success_at": success, "validated_after_dependencies": valid}


def test_provider_projection_uses_one_snapshot_and_supports_five_states():
    rows = [
        pipeline("provider.gmail.sync", success=None), pipeline("enrichment.gmail_metadata", success=None),
        pipeline("provider.immich.sync"), pipeline("enrichment.file_metadata"), pipeline("enrichment.immich_geo"), pipeline("enrichment.immich_metadata"), pipeline("enrichment.immich_ocr"),
        pipeline("provider.nextcloud.sync"), pipeline("enrichment.nextcloud_text"), pipeline("enrichment.nextcloud_documents"),
    ]
    raw_aggregate = {"ok": True, "buckets": [{"key": "gmail", "count": 2}, {"key": "immich", "count": 3}, {"key": "nextcloud", "count": 4}]}
    providers = project_providers(raw_aggregate, {"ok": True, "pipelines": rows})
    assert [p.provider_ref for p in providers] == ["gmail", "immich", "nextcloud"]
    assert providers[0].operational_state == "not_synced"
    assert providers[1].operational_state == "ready"
    rows[2]["latest_status"] = "running"
    assert project_providers(raw_aggregate, {"ok": True, "pipelines": rows})[1].operational_state == "syncing"
    rows[2]["latest_status"] = "succeeded"; rows[3]["latest_status"] = "running"
    assert project_providers(raw_aggregate, {"ok": True, "pipelines": rows})[1].operational_state == "processing"
    rows[3]["latest_status"] = "failed"
    assert project_providers(raw_aggregate, {"ok": True, "pipelines": rows})[1].operational_state == "attention"
    assert "manually managed" in provider_detail(providers[0]).description
    disabled = project_providers(raw_aggregate, {"ok": True, "pipelines": rows}, configured={"gmail": False, "immich": True, "nextcloud": True})[0]
    assert disabled.configured is False and disabled.operational_state == "not_synced" and disabled.last_success_at is None
