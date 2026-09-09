"""
Mirror of the user's Notion "Daily Board" database into NotionTask, pulled
in by POST /api/sync/notion/ (core/views.py). Mostly one-directional:
title/category/due_date are read-only mirrors. The one write path back to
Notion is write_status_to_notion() — PATCH /api/notion-tasks/<id>/ pushes a
status change onto the Notion page and updates the local row in the same
request, so the board reflects it without waiting for the next cron sync.

Mirrors core/ingest.py's shape: the view is a one-line call into
sync_notion_tasks() / write_status_to_notion(); everything else here is
plain, independently-testable functions. The three HTTP wrappers
(_notion_get/_notion_post/_notion_patch) are the mock boundary for tests —
patch those, never httpx itself, so tests don't depend on httpx's Response
object shape.

Schema introspection (detect_properties) never assumes field names — a
Notion database only guarantees exactly one property of type "title"; status
and date and category properties are located by type (with a name-based
preference only to break ties among multiple candidates), and gracefully
left unmapped (None) if nothing matches, rather than raising. See
docs/NOTION_SYNC.md.
"""
import re

import httpx
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import APIException

from core.models import NotionTask

NOTION_API_BASE = "https://api.notion.com/v1"
# Pinned, stable Notion API version string (not a version we control or need
# to bump proactively — Notion documents this as a point-in-time API
# contract snapshot, not a rolling "latest").
NOTION_VERSION = "2022-06-28"


class NotionNotConfiguredError(APIException):
    status_code = 503
    default_detail = "NOTION_TOKEN / NOTION_DAILY_BOARD_DB_ID are not configured yet. See docs/NOTION_SYNC.md."
    default_code = "notion_not_configured"


class NotionAPIError(APIException):
    status_code = 502
    default_detail = "The Notion API returned an error."
    default_code = "notion_api_error"


class NotionStatusError(APIException):
    # Client error, not a gateway error: the requested status isn't a real
    # option on the board (or the board has no status property to write to),
    # so there is nothing to retry — the caller sent a bad value.
    status_code = 400
    default_detail = "That status is not a valid option on the Notion board."
    default_code = "notion_invalid_status"


def _require_notion_config():
    # Checked at call time, not at settings-load time (see ascend/settings.py
    # comment) — this app is already live serving real traffic, and a
    # required-no-default config() call would crash every request at boot
    # the instant this code deploys, until the var is set on Render.
    if not settings.NOTION_TOKEN or not settings.NOTION_DAILY_BOARD_DB_ID:
        raise NotionNotConfiguredError()


def _headers():
    return {
        "Authorization": f"Bearer {settings.NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _notion_get(path):
    try:
        resp = httpx.get(f"{NOTION_API_BASE}{path}", headers=_headers(), timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise NotionAPIError(f"Notion API error on GET {path}: {exc}") from exc
    return resp.json()


def _notion_post(path, json_body):
    try:
        resp = httpx.post(f"{NOTION_API_BASE}{path}", headers=_headers(), json=json_body, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise NotionAPIError(f"Notion API error on POST {path}: {exc}") from exc
    return resp.json()


def _notion_patch(path, json_body):
    try:
        resp = httpx.patch(f"{NOTION_API_BASE}{path}", headers=_headers(), json=json_body, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise NotionAPIError(f"Notion API error on PATCH {path}: {exc}") from exc
    return resp.json()


def detect_properties(properties: dict) -> dict:
    """
    properties: the "properties" dict from GET /v1/databases/{id}.
    Returns {"title": <property name or None>, "status": ..., "date": ...,
    "category": ...} — values are Notion property NAMES (dict keys into a
    page's own "properties"), not our field names.

    Detected by property TYPE, never by assuming a specific name. Ties
    (more than one candidate of the same type) are broken by sorting
    candidate names alphabetically first, since Notion doesn't document
    property order in its API response as stable, and only then preferring
    one whose name matches a small hint pattern. No match at all -> None,
    meaning that field is left null/blank for every synced row rather than
    failing the whole sync — a board missing one of these properties is a
    legitimate layout, not an error.
    """
    def names_of_type(*types):
        return sorted(name for name, spec in properties.items() if spec.get("type") in types)

    def preferred(candidates, pattern):
        if not candidates:
            return None
        matches = [n for n in candidates if re.search(pattern, n, re.IGNORECASE)]
        return matches[0] if matches else candidates[0]

    title_candidates = names_of_type("title")  # Notion guarantees exactly one
    title = title_candidates[0] if title_candidates else None

    status_candidates = names_of_type("status")
    if not status_candidates:
        status_candidates = [n for n in names_of_type("select") if re.search(r"status", n, re.IGNORECASE)]
    status = status_candidates[0] if status_candidates else None

    date_candidates = names_of_type("date")
    date = preferred(date_candidates, r"due|date|when")

    category_candidates = [n for n in names_of_type("select", "multi_select") if n != status]
    category = preferred(category_candidates, r"project|category|type")

    return {"title": title, "status": status, "date": date, "category": category}


def extract_page_fields(page: dict, prop_map: dict) -> dict:
    """One Notion page-object dict -> our field dict (still plain Python
    values, not yet a NotionTask instance)."""
    props = page.get("properties", {})

    def prop(field_key):
        name = prop_map.get(field_key)
        return props.get(name) if name else None

    title_prop = prop("title")
    title = "".join(t.get("plain_text", "") for t in (title_prop or {}).get("title", [])) if title_prop else ""

    status_prop = prop("status")
    status = ""
    if status_prop:
        # type=="status" -> key "status"; type=="select" fallback -> key "select".
        status_obj = status_prop.get("status") or status_prop.get("select")
        if status_obj:
            status = status_obj.get("name") or ""

    date_prop = prop("date")
    due_date = None
    if date_prop:
        date_obj = date_prop.get("date")
        if date_obj and date_obj.get("start"):
            # Notion's date "start" may carry a time-of-day; due_date is a
            # DateField, so the time component is deliberately discarded.
            due_date = parse_date(date_obj["start"].split("T")[0])

    category_prop = prop("category")
    category = None
    if category_prop:
        if category_prop.get("type") == "multi_select":
            names = [o.get("name", "") for o in (category_prop.get("multi_select") or [])]
            joined = ", ".join(n for n in names if n)
            category = joined or None
        else:
            select_obj = category_prop.get("select")
            category = select_obj.get("name") if select_obj else None

    return {
        "notion_page_id": page["id"],
        "title": title,
        "status": status,
        "category": category,
        "due_date": due_date,
        "notion_last_edited": parse_datetime(page["last_edited_time"]),
    }


def _iter_database_pages(database_id):
    """Generator hiding has_more/next_cursor pagination — yields one raw
    Notion page-object dict at a time. Archived/trashed pages are skipped
    defensively, though Notion's query endpoint already excludes them by
    default."""
    body = {"page_size": 100}
    while True:
        data = _notion_post(f"/databases/{database_id}/query", body)
        for page in data.get("results", []):
            if page.get("archived"):
                continue
            yield page
        if not data.get("has_more"):
            break
        body = {"page_size": 100, "start_cursor": data["next_cursor"]}


def upsert_notion_task(fields: dict, owner):
    """Upsert keyed strictly on notion_page_id, never title — two Notion
    pages sharing a title must stay two separate rows here."""
    now = timezone.now()
    content_fields = {
        "title": fields["title"],
        "status": fields["status"],
        "category": fields["category"],
        "due_date": fields["due_date"],
        "notion_last_edited": fields["notion_last_edited"],
    }

    existing = NotionTask.objects.filter(notion_page_id=fields["notion_page_id"]).first()
    if existing is None:
        obj = NotionTask.objects.create(
            notion_page_id=fields["notion_page_id"],
            owner=owner,
            synced_at=now,
            status_changed_at=now,
            **content_fields,
        )
        return obj, "created"

    # Compare status BEFORE the setattr loop overwrites it. status_changed_at
    # only moves when the value genuinely differs — an edit to any other
    # field, or a no-op re-sync, leaves it alone (that's the whole point of
    # the field vs notion_last_edited / synced_at).
    status_changed = existing.status != fields["status"]
    changed = any(getattr(existing, key) != value for key, value in content_fields.items())
    for key, value in content_fields.items():
        setattr(existing, key, value)
    existing.synced_at = now
    if status_changed:
        existing.status_changed_at = now
    existing.save()
    return existing, ("updated" if changed else "unchanged")


def sync_notion_tasks(owner) -> dict:
    """The only function core.views.NotionSyncView calls."""
    _require_notion_config()

    schema = _notion_get(f"/databases/{settings.NOTION_DAILY_BOARD_DB_ID}")
    prop_map = detect_properties(schema.get("properties", {}))

    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for page in _iter_database_pages(settings.NOTION_DAILY_BOARD_DB_ID):
        fields = extract_page_fields(page, prop_map)
        _, status = upsert_notion_task(fields, owner)
        counts[status] += 1

    return {**counts, "matched_properties": prop_map}


# --------------------------------------------------------------------------
# Write-back: PATCH /api/notion-tasks/<id>/ -> Notion page status
# --------------------------------------------------------------------------

def _status_option_names(prop_spec: dict) -> list:
    """Valid option names for a status- or select-typed property, read from
    its spec in GET /v1/databases/{id}. Both types nest their options the
    same way: spec[spec["type"]]["options"] -> [{"name": ...}, ...] (a
    "status" property also has "groups", which we don't need). Returns []
    for anything else."""
    options = (prop_spec.get(prop_spec.get("type")) or {}).get("options") or []
    return [o["name"] for o in options if o.get("name")]


def build_status_patch(prop_name: str, prop_type: str, new_status: str) -> dict:
    """The PATCH-page body for a status change. Notion's payload shape
    differs by property type:
        status  -> {"properties": {<name>: {"status": {"name": ...}}}}
        select  -> {"properties": {<name>: {"select": {"name": ...}}}}
    Anything that isn't a native "status" property is treated as "select"
    (matches detect_properties' own select fallback)."""
    key = "status" if prop_type == "status" else "select"
    return {"properties": {prop_name: {key: {"name": new_status}}}}


def write_status_to_notion(task, new_status: str):
    """Push `new_status` onto the Notion page backing `task`, then update the
    local row. Validates against the board's real status options first — an
    arbitrary string is a 400 (NotionStatusError), never written to Notion.
    A Notion API failure raises NotionAPIError (502); the local row is only
    touched after Notion confirms the write."""
    _require_notion_config()

    schema = _notion_get(f"/databases/{settings.NOTION_DAILY_BOARD_DB_ID}")
    properties = schema.get("properties", {})
    status_prop_name = detect_properties(properties).get("status")
    if not status_prop_name:
        raise NotionStatusError(
            "This Notion board has no status-typed (or status-named select) "
            "property to write to."
        )

    prop_spec = properties.get(status_prop_name, {})
    prop_type = prop_spec.get("type")
    valid_options = _status_option_names(prop_spec)
    if new_status not in valid_options:
        raise NotionStatusError(
            f"{new_status!r} is not a valid option on the board's "
            f"{status_prop_name!r} property. Valid options: {valid_options}."
        )

    _notion_patch(
        f"/pages/{task.notion_page_id}",
        build_status_patch(status_prop_name, prop_type, new_status),
    )

    now = timezone.now()
    task.status = new_status
    task.status_changed_at = now
    task.synced_at = now
    task.save()
    return task
