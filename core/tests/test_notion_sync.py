"""
Notion sync tests. All Notion HTTP calls are mocked at the
core.notion_sync._notion_get/_notion_post/_notion_patch boundary
(unittest.mock.patch) — no real network, no new test dependency, and no
coupling to httpx's own Response object shape.
"""
from unittest.mock import patch

import pytest

from core import notion_sync
from core.models import NotionTask
from core.tests.factories import make_notion_task

pytestmark = pytest.mark.django_db


def _schema(properties):
    return {"object": "database", "properties": properties}


def _query_result(pages, has_more=False, next_cursor=None):
    return {"object": "list", "results": pages, "has_more": has_more, "next_cursor": next_cursor}


def _page(page_id, title, status_name=None, date_start=None, project_name=None,
          last_edited="2026-09-01T12:00:00.000Z"):
    return {
        "object": "page",
        "id": page_id,
        "last_edited_time": last_edited,
        "archived": False,
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": title}]},
            "Status": {"type": "status", "status": {"name": status_name} if status_name else None},
            "Date": {"type": "date", "date": {"start": date_start} if date_start else None},
            "Project": {"type": "select", "select": {"name": project_name} if project_name else None},
        },
    }


SCHEMA_PROPERTIES = {
    "Name": {"name": "Name", "type": "title", "title": {}},
    "Status": {"name": "Status", "type": "status", "status": {}},
    "Date": {"name": "Date", "type": "date", "date": {}},
    "Project": {"name": "Project", "type": "select", "select": {}},
}


@pytest.fixture(autouse=True)
def notion_configured(settings):
    settings.NOTION_TOKEN = "fake-notion-token"
    settings.NOTION_DAILY_BOARD_DB_ID = "fake-db-id"


class TestSyncNotConfigured:
    def test_raises_503_when_not_configured(self, user, settings):
        settings.NOTION_TOKEN = ""
        with pytest.raises(notion_sync.NotionNotConfiguredError):
            notion_sync.sync_notion_tasks(user)


class TestSyncIdempotency:
    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_two_identical_calls_are_idempotent(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.return_value = _query_result(
            [_page("page-1", "Buy milk", "In Progress", "2026-09-10", "ASCEND")]
        )

        first = notion_sync.sync_notion_tasks(user)
        assert first["created"] == 1
        assert first["updated"] == 0
        assert first["unchanged"] == 0
        assert NotionTask.objects.count() == 1

        second = notion_sync.sync_notion_tasks(user)
        assert second["created"] == 0
        assert second["updated"] == 0
        assert second["unchanged"] == 1
        assert NotionTask.objects.count() == 1

    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_changed_page_reports_updated_not_unchanged(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.return_value = _query_result(
            [_page("page-1", "Buy milk", "To Do", "2026-09-10", "ASCEND", last_edited="2026-09-01T12:00:00.000Z")]
        )
        notion_sync.sync_notion_tasks(user)

        mock_post.return_value = _query_result(
            [_page("page-1", "Buy milk", "Done", "2026-09-10", "ASCEND", last_edited="2026-09-02T09:00:00.000Z")]
        )
        result = notion_sync.sync_notion_tasks(user)
        assert result["updated"] == 1
        assert result["created"] == 0
        assert NotionTask.objects.get(notion_page_id="page-1").status == "Done"


class TestSyncDuplicateTitles:
    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_two_pages_sharing_a_title_stay_two_rows(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.return_value = _query_result(
            [
                _page("page-a", "Buy milk", "To Do"),
                _page("page-b", "Buy milk", "Done"),
            ]
        )

        result = notion_sync.sync_notion_tasks(user)
        assert result["created"] == 2
        rows = NotionTask.objects.filter(title="Buy milk").order_by("notion_page_id")
        assert [r.notion_page_id for r in rows] == ["page-a", "page-b"]


class TestSyncPagination:
    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_follows_has_more_cursor(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.side_effect = [
            _query_result([_page("page-1", "First")], has_more=True, next_cursor="cursor-2"),
            _query_result([_page("page-2", "Second")], has_more=False),
        ]

        result = notion_sync.sync_notion_tasks(user)
        assert result["created"] == 2
        assert mock_post.call_count == 2
        second_call_body = mock_post.call_args_list[1].args[1]
        assert second_call_body["start_cursor"] == "cursor-2"


class TestDetectProperties:
    def test_status_typed_property(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Status": {"type": "status"},
        })
        assert result["title"] == "Name"
        assert result["status"] == "Status"

    def test_select_fallback_when_no_status_type(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Status": {"type": "select"},
        })
        assert result["status"] == "Status"

    def test_no_status_like_property_leaves_it_none(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Priority": {"type": "select"},
        })
        assert result["status"] is None

    def test_multi_select_category_candidate(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Status": {"type": "status"},
            "Tags": {"type": "multi_select"},
        })
        assert result["category"] == "Tags"

    def test_no_date_property_leaves_it_none(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Status": {"type": "status"},
        })
        assert result["date"] is None

    def test_date_property_prefers_name_matching_hint(self):
        result = notion_sync.detect_properties({
            "Name": {"type": "title"},
            "Created": {"type": "date"},
            "Due Date": {"type": "date"},
        })
        assert result["date"] == "Due Date"


class TestExtractPageFields:
    def test_multi_select_category_joins_names(self):
        prop_map = {"title": "Name", "status": "Status", "date": "Date", "category": "Tags"}
        page = {
            "id": "p1",
            "last_edited_time": "2026-09-01T12:00:00.000Z",
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": "Task"}]},
                "Status": {"type": "status", "status": {"name": "Done"}},
                "Date": {"type": "date", "date": {"start": "2026-09-10T00:00:00.000Z"}},
                "Tags": {"type": "multi_select", "multi_select": [{"name": "A"}, {"name": "B"}]},
            },
        }
        fields = notion_sync.extract_page_fields(page, prop_map)
        assert fields["category"] == "A, B"
        assert fields["due_date"].isoformat() == "2026-09-10"  # time-of-day discarded

    def test_missing_properties_degrade_gracefully(self):
        prop_map = {"title": "Name", "status": None, "date": None, "category": None}
        page = {
            "id": "p2",
            "last_edited_time": "2026-09-01T12:00:00.000Z",
            "properties": {"Name": {"type": "title", "title": [{"plain_text": "Bare task"}]}},
        }
        fields = notion_sync.extract_page_fields(page, prop_map)
        assert fields["title"] == "Bare task"
        assert fields["status"] == ""
        assert fields["category"] is None
        assert fields["due_date"] is None


# --------------------------------------------------------------------------
# Part B — status_changed_at only moves when `status` actually changes
# --------------------------------------------------------------------------

class TestStatusChangedAt:
    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_set_on_creation(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.return_value = _query_result([_page("page-1", "Task", "To Do")])

        notion_sync.sync_notion_tasks(user)

        row = NotionTask.objects.get(notion_page_id="page-1")
        assert row.status_changed_at is not None
        # Same timezone.now() call inside upsert sets both.
        assert row.status_changed_at == row.synced_at

    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_unchanged_status_across_two_syncs_leaves_it_alone(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        # First sync creates the row.
        mock_post.return_value = _query_result(
            [_page("page-1", "Task", "To Do", last_edited="2026-09-01T12:00:00.000Z")]
        )
        notion_sync.sync_notion_tasks(user)
        original = NotionTask.objects.get(notion_page_id="page-1").status_changed_at

        # Second sync: same status, but a different last_edited and a
        # different title — a real edit that isn't a status change.
        mock_post.return_value = _query_result(
            [_page("page-1", "Task renamed", "To Do", last_edited="2026-09-02T08:00:00.000Z")]
        )
        result = notion_sync.sync_notion_tasks(user)

        row = NotionTask.objects.get(notion_page_id="page-1")
        assert result["updated"] == 1  # the title change registered as an update
        assert row.status_changed_at == original  # ...but status_changed_at didn't move
        assert row.synced_at > original  # synced_at did

    @patch("core.notion_sync._notion_post")
    @patch("core.notion_sync._notion_get")
    def test_changed_status_advances_it(self, mock_get, mock_post, user):
        mock_get.return_value = _schema(SCHEMA_PROPERTIES)
        mock_post.return_value = _query_result(
            [_page("page-1", "Task", "To Do", last_edited="2026-09-01T12:00:00.000Z")]
        )
        notion_sync.sync_notion_tasks(user)
        original = NotionTask.objects.get(notion_page_id="page-1").status_changed_at

        mock_post.return_value = _query_result(
            [_page("page-1", "Task", "Done", last_edited="2026-09-03T09:00:00.000Z")]
        )
        notion_sync.sync_notion_tasks(user)

        row = NotionTask.objects.get(notion_page_id="page-1")
        assert row.status == "Done"
        assert row.status_changed_at > original


# --------------------------------------------------------------------------
# Part C — write status back to Notion
# --------------------------------------------------------------------------

def _status_schema(prop_type="status", options=("To Do", "In Progress", "Done")):
    """A GET /v1/databases/{id} schema whose Status property is `prop_type`
    (either the native "status" type or a "select" named Status) and carries
    real options."""
    container = {"options": [{"name": n, "id": n.lower().replace(" ", "-")} for n in options]}
    return _schema({
        "Name": {"name": "Name", "type": "title", "title": {}},
        "Status": {"name": "Status", "type": prop_type, prop_type: container},
    })


class TestBuildStatusPatch:
    def test_status_typed_property_shape(self):
        assert notion_sync.build_status_patch("Status", "status", "Done") == {
            "properties": {"Status": {"status": {"name": "Done"}}}
        }

    def test_select_typed_property_shape(self):
        assert notion_sync.build_status_patch("Status", "select", "Done") == {
            "properties": {"Status": {"select": {"name": "Done"}}}
        }


class TestWriteStatusToNotion:
    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_status_typed_board_builds_status_payload(self, mock_get, mock_patch):
        mock_get.return_value = _status_schema(prop_type="status")
        task = make_notion_task("page-1", status="To Do")

        notion_sync.write_status_to_notion(task, "Done")

        path, body = mock_patch.call_args.args
        assert path == "/pages/page-1"
        assert body == {"properties": {"Status": {"status": {"name": "Done"}}}}

    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_select_typed_board_builds_select_payload(self, mock_get, mock_patch):
        mock_get.return_value = _status_schema(prop_type="select")
        task = make_notion_task("page-2", status="To Do")

        notion_sync.write_status_to_notion(task, "In Progress")

        _, body = mock_patch.call_args.args
        assert body == {"properties": {"Status": {"select": {"name": "In Progress"}}}}

    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_rejects_status_not_in_board_options(self, mock_get, mock_patch):
        mock_get.return_value = _status_schema(options=("To Do", "Done"))
        task = make_notion_task("page-3", status="To Do")

        with pytest.raises(notion_sync.NotionStatusError):
            notion_sync.write_status_to_notion(task, "Archived")

        mock_patch.assert_not_called()
        task.refresh_from_db()
        assert task.status == "To Do"  # untouched

    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_success_updates_local_row_immediately(self, mock_get, mock_patch):
        mock_get.return_value = _status_schema()
        task = make_notion_task("page-4", status="To Do", status_changed_at=None)

        notion_sync.write_status_to_notion(task, "Done")

        row = NotionTask.objects.get(notion_page_id="page-4")
        assert row.status == "Done"
        assert row.status_changed_at is not None
        assert row.status_changed_at == row.synced_at
        assert mock_patch.call_count == 1

    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_notion_failure_propagates_and_leaves_row_unchanged(self, mock_get, mock_patch):
        mock_get.return_value = _status_schema()
        mock_patch.side_effect = notion_sync.NotionAPIError("Notion said no")
        task = make_notion_task("page-5", status="To Do")

        with pytest.raises(notion_sync.NotionAPIError):
            notion_sync.write_status_to_notion(task, "Done")

        assert NotionTask.objects.get(notion_page_id="page-5").status == "To Do"


class TestWriteBackEndpoint:
    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_patch_updates_status(self, mock_get, mock_patch, auth_client, user):
        mock_get.return_value = _status_schema()
        task = make_notion_task("page-1", status="To Do", owner=user)

        resp = auth_client.patch(
            f"/api/notion-tasks/{task.id}/", {"status": "Done"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "Done"
        assert resp.data["status_changed_at"] is not None
        task.refresh_from_db()
        assert task.status == "Done"

    @patch("core.notion_sync._notion_patch")
    @patch("core.notion_sync._notion_get")
    def test_patch_rejects_invalid_status_with_400(self, mock_get, mock_patch, auth_client, user):
        mock_get.return_value = _status_schema(options=("To Do", "Done"))
        task = make_notion_task("page-1", status="To Do", owner=user)

        resp = auth_client.patch(
            f"/api/notion-tasks/{task.id}/", {"status": "Nonsense"}, format="json"
        )
        assert resp.status_code == 400
        mock_patch.assert_not_called()

    def test_patch_rejects_unknown_body_field(self, auth_client, user):
        task = make_notion_task("page-1", owner=user)
        resp = auth_client.patch(
            f"/api/notion-tasks/{task.id}/", {"status": "Done", "title": "hax"}, format="json"
        )
        assert resp.status_code == 400

    def test_patch_rejects_ingest_token(self, ingest_client, user):
        task = make_notion_task("page-1", owner=user)
        resp = ingest_client.patch(
            f"/api/notion-tasks/{task.id}/", {"status": "Done"}, format="json"
        )
        assert resp.status_code in (401, 403)

    def test_patch_requires_auth(self, api_client, user):
        task = make_notion_task("page-1", owner=user)
        resp = api_client.patch(
            f"/api/notion-tasks/{task.id}/", {"status": "Done"}, format="json"
        )
        assert resp.status_code == 401
