from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import os
from stat import S_IMODE
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
import pytest

import pdi.observation.nextcloud_documents as document_module
from pdi.observation import (
    EnrichmentResource,
    EnrichmentSource,
    MAX_STORED_TEXT_BYTES,
    NextcloudDOCXExtractor,
    NextcloudODTExtractor,
    NextcloudPDFExtractor,
    ObservationExtractionError,
    TRUNCATION_MARKER,
)
from pdi.observation.nextcloud_documents import (
    MAX_EXTRACTED_CHARACTERS,
    PDF_MAX_PAGES,
    PDF_MAX_SOURCE_BYTES,
    PDF_SPOOL_MEMORY_BYTES,
    ZIP_MAX_ENTRIES,
    ZIP_MAX_ENTRY_UNCOMPRESSED_BYTES,
    ZIP_MAX_SOURCE_BYTES,
    ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
    _extract_pdf_text,
    _validate_zip_inventory,
    _verified_pdf_stream,
)
from pdi.query import format_resource_ref


PDF_MIME = "application/pdf"
ODT_MIME = "application/vnd.oasis.opendocument.text"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)


class RecordingReader:
    def __init__(
        self,
        content: bytes,
        *,
        chunks: tuple[bytes, ...] | None = None,
    ) -> None:
        self.content = content
        self.chunks = chunks
        self.sources: list[EnrichmentSource] = []

    def open(self, source: EnrichmentSource):
        self.sources.append(source)
        return iter(self.chunks or (self.content,))


def _source(
    content: bytes,
    *,
    mime_type: str,
    name: str,
    source_id: str = "source-a",
    digest: str | None = None,
    size: int | None = None,
) -> EnrichmentSource:
    return EnrichmentSource(
        source_id=source_id,
        provider="nextcloud",
        metadata={"href": "/private/provider/path"},
        provider_locator="private-locator",
        blob_sha256=digest or sha256(content).hexdigest(),
        size=len(content) if size is None else size,
        mime_type=mime_type,
        path=f"documents/{name}",
        name=name,
        version_tag='"etag"',
    )


def _resource(*sources: EnrichmentSource) -> EnrichmentResource:
    return EnrichmentResource(
        format_resource_ref(uuid4()),
        tuple(sources),
    )


def _pdf(pages: list[str | None], *, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_reference}
                )
            }
        )
        escaped = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode(
                "ascii"
            )
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("not-provided", algorithm="RC4-40")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _zip(
    entries: dict[str, bytes],
    *,
    compression: int = ZIP_DEFLATED,
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=compression) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def _odt(body: str, *, manifest: str | None = None) -> bytes:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">
 <office:body><office:text>{body}</office:text></office:body>
</office:document-content>'''.encode()
    entries = {
        "mimetype": ODT_MIME.encode(),
        "content.xml": content,
    }
    if manifest is not None:
        entries["META-INF/manifest.xml"] = manifest.encode()
    return _zip(entries)


def _docx(body: str, *, extras: dict[str, bytes] | None = None) -> bytes:
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <w:body>{body}<w:sectPr/></w:body>
</w:document>'''.encode()
    entries = {"word/document.xml": document}
    entries.update(extras or {})
    return _zip(entries)


def _extract(extractor_class, content: bytes, mime_type: str, name: str):
    reader = RecordingReader(content)
    resource = _resource(
        _source(content, mime_type=mime_type, name=name)
    )
    return extractor_class(reader).extract(resource), reader


def test_pdf_golden_multipage_order_provenance_and_fingerprint() -> None:
    content = _pdf(["First page", "Second page"])
    source = _source(content, mime_type=PDF_MIME, name="sample.pdf")
    resource = _resource(source)
    reader = RecordingReader(content)
    extractor = NextcloudPDFExtractor(reader)

    batch = extractor.extract(resource)

    assert batch.generator.generator_type == "deterministic_extractor"
    assert batch.generator.generator_name == "nextcloud_pdf"
    assert batch.generator.generator_version == "1"
    assert batch.statements[0].value.value == "First page\n\nSecond page"
    assert batch.statements[0].evidence.source_kind == "resource_content"
    assert batch.statements[0].evidence.source_locator == (
        "nextcloud.webdav.content"
    )
    assert batch.input_fingerprint == sha256(
        (
            '{"blob_sha256":"'
            + sha256(content).hexdigest()
            + '","extractor_name":"nextcloud_pdf",'
            '"extractor_version":"1",'
            '"format":"pdi.nextcloud_pdf.input.v1",'
            '"mime_type":"application/pdf",'
            '"provider":"nextcloud"}'
        ).encode()
    ).hexdigest()
    assert reader.sources == [source]


@pytest.mark.parametrize("pages", [[], [None]])
def test_pdf_empty_and_image_only_like_complete_with_zero_statements(
    pages,
) -> None:
    batch, _ = _extract(
        NextcloudPDFExtractor,
        _pdf(pages),
        PDF_MIME,
        "empty.pdf",
    )

    assert batch.statements == ()
    assert batch.covered_predicates == ("document.text_excerpt",)


def test_pdf_encrypted_fails_without_password() -> None:
    content = _pdf(["private"], encrypted=True)

    with pytest.raises(ObservationExtractionError) as captured:
        _extract(
            NextcloudPDFExtractor,
            content,
            PDF_MIME,
            "encrypted.pdf",
        )

    assert captured.value.code == "encrypted_document"
    assert "not-provided" not in str(captured.value)


def test_pdf_malformed_and_page_limit_are_bounded() -> None:
    with pytest.raises(ObservationExtractionError) as malformed:
        _extract(
            NextcloudPDFExtractor,
            b"not a pdf",
            PDF_MIME,
            "broken.pdf",
        )
    assert malformed.value.code == "invalid_document"

    content = _pdf([None] * (PDF_MAX_PAGES + 1))
    with pytest.raises(ObservationExtractionError) as too_many:
        _extract(
            NextcloudPDFExtractor,
            content,
            PDF_MIME,
            "many-pages.pdf",
        )
    assert too_many.value.code == "document_too_large"


def test_pdf_non_strict_xref_repair_remains_readable() -> None:
    content = _pdf(["xref repair"]).replace(
        b"xref\n0 ",
        b"xref\n1 ",
        1,
    )

    batch, _ = _extract(
        NextcloudPDFExtractor,
        content,
        PDF_MIME,
        "xref.pdf",
    )

    assert batch.statements[0].value.value == "xref repair"


def test_pdf_character_ceiling_and_unicode_truncation(monkeypatch) -> None:
    class Page:
        def __init__(self, value):
            self.value = value

        def extract_text(self):
            return self.value

    class Reader:
        is_encrypted = False
        pages = [Page("中" * (MAX_EXTRACTED_CHARACTERS + 10))]

    monkeypatch.setattr(
        "pdi.observation.nextcloud_documents.PdfReader",
        lambda stream, strict: Reader(),
    )

    extracted = _extract_pdf_text(BytesIO(b"verified elsewhere"))

    assert len(extracted) == MAX_EXTRACTED_CHARACTERS
    assert extracted == "中" * MAX_EXTRACTED_CHARACTERS


def test_pdf_source_bounds_digest_and_secure_spooling() -> None:
    small = _pdf(["small"])
    reader = RecordingReader(small)
    wrong = _source(
        small,
        mime_type=PDF_MIME,
        name="changed.pdf",
        digest="a" * 64,
    )
    with pytest.raises(ObservationExtractionError) as changed:
        NextcloudPDFExtractor(reader).extract(_resource(wrong))
    assert changed.value.code == "content_changed_since_sync"

    declared = _source(
        small,
        mime_type=PDF_MIME,
        name="large.pdf",
        size=PDF_MAX_SOURCE_BYTES + 1,
    )
    untouched = RecordingReader(small)
    with pytest.raises(ObservationExtractionError) as too_large:
        NextcloudPDFExtractor(untouched).extract(_resource(declared))
    assert too_large.value.code == "document_too_large"
    assert untouched.sources == []

    spooled = b"x" * (PDF_SPOOL_MEMORY_BYTES + 1)
    source = _source(spooled, mime_type=PDF_MIME, name="spooled.pdf")
    with _verified_pdf_stream(RecordingReader(spooled), source) as stream:
        assert stream.read(1) == b"x"
        assert getattr(stream, "_rolled") is True
        assert S_IMODE(os.fstat(stream.fileno()).st_mode) & 0o077 == 0


def test_pdf_stream_overflow_is_detected_before_parsing(monkeypatch) -> None:
    monkeypatch.setattr(document_module, "PDF_MAX_SOURCE_BYTES", 8)
    source = replace(
        _source(
            b"12345678",
            mime_type=PDF_MIME,
            name="overflow.pdf",
        ),
        size=None,
    )
    reader = RecordingReader(
        b"",
        chunks=(b"12345678", b"overflow"),
    )

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudPDFExtractor(reader).extract(_resource(source))

    assert captured.value.code == "document_too_large"


def test_odt_golden_body_order_unicode_structure_and_exclusions() -> None:
    body = '''
<text:h>Heading</text:h>
<text:p>Hello <text:a>世界</text:a><text:s text:c="2"/><text:tab/><text:line-break/>End<office:annotation>secret</office:annotation></text:p>
<table:table><table:table-row>
 <table:table-cell><text:p>A</text:p></table:table-cell>
 <table:table-cell><text:p>B</text:p></table:table-cell>
</table:table-row></table:table>
<text:tracked-changes><text:p>tracked secret</text:p></text:tracked-changes>
'''
    batch, _ = _extract(
        NextcloudODTExtractor,
        _odt(body),
        ODT_MIME,
        "sample.odt",
    )

    assert batch.generator.generator_name == "nextcloud_odt"
    assert batch.statements[0].value.value == (
        "Heading\nHello 世界  \t\nEnd\nA\tB"
    )


def test_odt_empty_and_encrypted_manifest_semantics() -> None:
    empty, _ = _extract(
        NextcloudODTExtractor,
        _odt("<text:p> \t </text:p>"),
        ODT_MIME,
        "empty.odt",
    )
    assert empty.statements == ()

    manifest = '''
<manifest:manifest
 xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
 <manifest:file-entry manifest:full-path="content.xml">
  <manifest:encryption-data/>
 </manifest:file-entry>
</manifest:manifest>'''
    content = _odt("<text:p>secret</text:p>", manifest=manifest)
    with pytest.raises(ObservationExtractionError) as encrypted:
        _extract(
            NextcloudODTExtractor,
            content,
            ODT_MIME,
            "encrypted.odt",
        )
    assert encrypted.value.code == "encrypted_document"

    missing = _zip({"styles.xml": b"<styles/>"})
    with pytest.raises(ObservationExtractionError) as invalid:
        _extract(
            NextcloudODTExtractor,
            missing,
            ODT_MIME,
            "missing.odt",
        )
    assert invalid.value.code == "invalid_document"


def test_docx_golden_body_order_unicode_tables_and_exclusions() -> None:
    body = '''
<w:p><w:r><w:t>Hello </w:t></w:r>
 <w:hyperlink r:id="r1"><w:r><w:t>世界</w:t></w:r></w:hyperlink>
 <w:r><w:tab/><w:t>tab</w:t><w:br/><w:t>line</w:t></w:r>
 <w:ins><w:r><w:t>tracked</w:t></w:r></w:ins>
 <w:drawing><w:txbxContent><w:p><w:r><w:t>box</w:t></w:r></w:p>
 </w:txbxContent></w:drawing></w:p>
<w:tbl><w:tr>
 <w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>
  <w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
 <w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc>
</w:tr></w:tbl>
'''
    extras = {
        "word/header1.xml": b"<w:t>header secret</w:t>",
        "word/footer1.xml": b"<w:t>footer secret</w:t>",
        "word/comments.xml": b"<w:t>comment secret</w:t>",
        "word/footnotes.xml": b"<w:t>footnote secret</w:t>",
    }
    batch, _ = _extract(
        NextcloudDOCXExtractor,
        _docx(body, extras=extras),
        DOCX_MIME,
        "sample.docx",
    )

    assert batch.generator.generator_name == "nextcloud_docx"
    assert batch.statements[0].value.value == (
        "Hello 世界\ttab\nline\nA\tB"
    )


def test_docx_empty_missing_and_ole_encrypted_semantics() -> None:
    empty, _ = _extract(
        NextcloudDOCXExtractor,
        _docx("<w:p/>"),
        DOCX_MIME,
        "empty.docx",
    )
    assert empty.statements == ()

    missing = _zip({"word/styles.xml": b"<styles/>"})
    with pytest.raises(ObservationExtractionError) as invalid:
        _extract(
            NextcloudDOCXExtractor,
            missing,
            DOCX_MIME,
            "missing.docx",
        )
    assert invalid.value.code == "invalid_document"

    encrypted = bytes.fromhex("D0CF11E0A1B11AE1") + b"opaque"
    with pytest.raises(ObservationExtractionError) as captured:
        _extract(
            NextcloudDOCXExtractor,
            encrypted,
            DOCX_MIME,
            "encrypted.docx",
        )
    assert captured.value.code == "encrypted_document"


@pytest.mark.parametrize(
    "name",
    ("/absolute", "../escape", "safe/../escape", "C:/drive", "a\\b"),
)
def test_zip_rejects_unsafe_entry_names(name) -> None:
    content = _zip(
        {
            "word/document.xml": (
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                b'wordprocessingml/2006/main"><w:body/></w:document>'
            ),
            name: b"unsafe",
        }
    )

    with pytest.raises(ObservationExtractionError) as captured:
        _extract(
            NextcloudDOCXExtractor,
            content,
            DOCX_MIME,
            "unsafe.docx",
        )

    assert captured.value.code == "invalid_document"


def test_zip_inventory_limits_and_encryption_flag() -> None:
    too_many = [ZipInfo(f"entry-{index}") for index in range(
        ZIP_MAX_ENTRIES + 1
    )]
    with pytest.raises(ObservationExtractionError) as entries:
        _validate_zip_inventory(too_many)
    assert entries.value.code == "archive_limit_exceeded"

    individual = ZipInfo("large")
    individual.file_size = ZIP_MAX_ENTRY_UNCOMPRESSED_BYTES + 1
    individual.compress_size = individual.file_size
    with pytest.raises(ObservationExtractionError) as entry:
        _validate_zip_inventory([individual])
    assert entry.value.code == "archive_limit_exceeded"

    total_a = ZipInfo("a")
    total_a.file_size = ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES // 2 + 1
    total_a.compress_size = total_a.file_size
    total_b = ZipInfo("b")
    total_b.file_size = ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES // 2 + 1
    total_b.compress_size = total_b.file_size
    with pytest.raises(ObservationExtractionError) as total:
        _validate_zip_inventory([total_a, total_b])
    assert total.value.code == "archive_limit_exceeded"

    encrypted = ZipInfo("encrypted")
    encrypted.flag_bits |= 0x1
    with pytest.raises(ObservationExtractionError) as encryption:
        _validate_zip_inventory([encrypted])
    assert encryption.value.code == "encrypted_document"


def test_zip_compression_bomb_crc_and_malformed_are_rejected() -> None:
    bomb = _zip(
        {
            "word/document.xml": b"a" * 200_000,
        }
    )
    with pytest.raises(ObservationExtractionError) as ratio:
        _extract(
            NextcloudDOCXExtractor,
            bomb,
            DOCX_MIME,
            "bomb.docx",
        )
    assert ratio.value.code == "archive_limit_exceeded"

    stored = _zip(
        {
            "word/document.xml": b"UNIQUE-CONTENT-FOR-CRC",
        },
        compression=ZIP_STORED,
    )
    corrupt = stored.replace(
        b"UNIQUE-CONTENT-FOR-CRC",
        b"BROKEN-CONTENT-FOR-CRC",
        1,
    )
    with pytest.raises(ObservationExtractionError) as crc:
        _extract(
            NextcloudDOCXExtractor,
            corrupt,
            DOCX_MIME,
            "crc.docx",
        )
    assert crc.value.code == "invalid_document"

    with pytest.raises(ObservationExtractionError) as malformed:
        _extract(
            NextcloudODTExtractor,
            b"not-a-zip",
            ODT_MIME,
            "broken.odt",
        )
    assert malformed.value.code == "invalid_document"


@pytest.mark.parametrize(
    "attack",
    (
        '<!DOCTYPE x [<!ENTITY x "expanded">]>',
        '<!DOCTYPE x SYSTEM "file:///etc/passwd">',
        '<!DOCTYPE x [<!ENTITY x SYSTEM "https://example.invalid/x">]>',
    ),
)
def test_xml_dtd_entity_and_external_references_are_rejected(attack) -> None:
    content = _zip(
        {
            "content.xml": (
                f'''<?xml version="1.0"?>{attack}
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:text><text:p>&x;</text:p></office:text></office:body>
</office:document-content>'''
            ).encode()
        }
    )

    with pytest.raises(ObservationExtractionError) as captured:
        _extract(
            NextcloudODTExtractor,
            content,
            ODT_MIME,
            "attack.odt",
        )

    assert captured.value.code == "invalid_document"


def test_common_truncation_keeps_utf8_boundary_and_exact_marker() -> None:
    body = "<text:p>" + ("中" * 10_000) + "</text:p>"
    content_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:text>{body}</office:text></office:body>
</office:document-content>'''.encode()
    content = _zip(
        {"mimetype": ODT_MIME.encode(), "content.xml": content_xml},
        compression=ZIP_STORED,
    )
    batch, _ = _extract(
        NextcloudODTExtractor,
        content,
        ODT_MIME,
        "large.odt",
    )
    value = batch.statements[0].value.value

    assert value.endswith(TRUNCATION_MARKER)
    assert len(value.encode("utf-8")) <= MAX_STORED_TEXT_BYTES
    value.encode().decode()


def test_mime_eligibility_fallback_and_contradiction() -> None:
    pdf = _pdf(["eligible"])
    fallback = _source(
        pdf,
        mime_type="application/octet-stream",
        name="eligible.pdf",
    )
    contradiction = _source(
        pdf,
        mime_type="image/jpeg",
        name="misleading.pdf",
    )

    assert NextcloudPDFExtractor.is_eligible(_resource(fallback)) is True
    assert (
        NextcloudPDFExtractor.is_eligible(_resource(contradiction)) is False
    )


def test_same_blob_collapses_and_different_blobs_fail_before_read() -> None:
    content = _docx("<w:p><w:r><w:t>same</w:t></w:r></w:p>")
    earlier = _source(
        content,
        mime_type=DOCX_MIME,
        name="same.docx",
        source_id="source-a",
    )
    later = _source(
        content,
        mime_type=DOCX_MIME,
        name="same.docx",
        source_id="source-z",
    )
    reader = RecordingReader(content)
    batch = NextcloudDOCXExtractor(reader).extract(
        _resource(later, earlier)
    )
    assert batch.statements[0].value.value == "same"
    assert reader.sources == [earlier]

    first = _source(
        content,
        mime_type=DOCX_MIME,
        name="first.docx",
        source_id="first",
    )
    other_content = _docx("<w:p><w:r><w:t>other</w:t></w:r></w:p>")
    second = _source(
        other_content,
        mime_type=DOCX_MIME,
        name="second.docx",
        source_id="second",
    )
    untouched = RecordingReader(content)
    with pytest.raises(ObservationExtractionError) as ambiguous:
        NextcloudDOCXExtractor(untouched).input_fingerprint(
            _resource(first, second)
        )
    assert ambiguous.value.code == "ambiguous_active_nextcloud_content"
    assert untouched.sources == []


def test_zip_source_declared_limit_fails_without_provider_read() -> None:
    content = _odt("<text:p>small</text:p>")
    source = _source(
        content,
        mime_type=ODT_MIME,
        name="large.odt",
        size=ZIP_MAX_SOURCE_BYTES + 1,
    )
    reader = RecordingReader(content)

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudODTExtractor(reader).extract(_resource(source))

    assert captured.value.code == "document_too_large"
    assert reader.sources == []


def test_zip_stream_overflow_is_detected_before_container_parse(
    monkeypatch,
) -> None:
    monkeypatch.setattr(document_module, "ZIP_MAX_SOURCE_BYTES", 8)
    source = replace(
        _source(
            b"12345678",
            mime_type=ODT_MIME,
            name="overflow.odt",
        ),
        size=None,
    )
    reader = RecordingReader(
        b"",
        chunks=(b"12345678", b"overflow"),
    )

    with pytest.raises(ObservationExtractionError) as captured:
        NextcloudODTExtractor(reader).extract(_resource(source))

    assert captured.value.code == "document_too_large"
