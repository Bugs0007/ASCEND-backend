"""
Notion sync tests. All Notion HTTP calls are mocked at the
core.notion_sync._notion_get/_notion_post boundary (unittest.mock.patch) —
no real network, no new test dependency, and no coupling to httpx's own
Response object shape.
"""
from unittest.mock import patch

import pytest

from core import notion_sync
from core.models import NotionTask

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
