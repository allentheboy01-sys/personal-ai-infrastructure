# 10 - Capability

**Status:** V0.1

---

## Purpose

A Capability provides reusable operations required by different parts of PDI.

Capabilities are invoked only when needed.

---

## Why

Some operations should not belong to any single module.

Keeping them independent avoids duplicated logic and unnecessary coupling.

---

## Responsibilities

A Capability is responsible for:

- Performing reusable operations.
- Returning deterministic results.
- Remaining independent from business logic.

---

## Does NOT

A Capability does NOT:

- Make identity decisions.
- Access the World Model.
- Store data.
- Execute synchronization.

---

## Current Capability

Current implementation:

- SHA256 Hash

---

## Future Capability

Examples include:

- OCR
- EXIF Extraction
- Text Extraction
- Embedding Generation
- Thumbnail Generation
- Audio Transcription

---

## Notes

Any module may request a Capability when required.

Capabilities should remain reusable, independent and stateless.