# 02 - Provider

**Status:** V0.1

---

## Purpose

A Provider is an external application that owns original user data.

PDI never owns the original data.

It only builds a unified World Model from Providers.

---

## Responsibilities

A Provider is responsible for:

- Creating original data.
- Managing application-specific metadata.
- Exposing data through supported interfaces.

---

## Does NOT

A Provider does NOT:

- Understand the World Model.
- Make identity decisions.
- Store semantic relationships.
- Communicate with other Providers.

---

## Examples

Current and planned Providers include:

- Nextcloud
- Google Drive
- Immich
- Git
- Jellyfin
- Home Assistant
- Email

---

## Notes

Each Provider remains independent.

PDI never modifies a Provider's internal architecture.

Every Provider communicates with PDI only through its Adapter.