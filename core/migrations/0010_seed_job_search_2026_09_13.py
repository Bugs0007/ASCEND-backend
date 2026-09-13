"""
Seed the first real job-search data: the five applications sent on
2026-09-13 and that day's LinkedIn snapshot.

Unlike 0002/0006 (shared program scaffolding, owner=NULL), these are the
user's own rows, so they're attributed the same way an ingest write would be
(core.auth.resolve_ingest_owner: INGEST_OWNER_USERNAME, else the first
superuser). With no user yet — a fresh test database — owner stays NULL,
which every owner-scoped list endpoint still returns.

Idempotent and non-destructive: an application that already exists (matched
case-insensitively on company + role, e.g. typed in by hand before this
deployed) is left alone apart from filling a blank `channel`; an existing
snapshot for the date is not overwritten. `source` is written out per row
rather than derived from core.constants.CHANNEL_DEFAULT_SOURCE so this
migration's data stays frozen if that mapping ever changes.

The test suite strips these rows from the test database once per session
(core/tests/conftest.py) — every existing analytics test assumes it starts
with no applications.
"""
import datetime

from django.conf import settings
from django.db import migrations

SEED_DATE = datetime.date(2026, 9, 13)

# (company, role, channel, source, notes)
APPLICATIONS = [
    ("Rehlat", "Python Developer", "linkedin_easy_apply", "portal", ""),
    ("SRS Business Solutions India Pvt Ltd", "Python Developer", "linkedin_easy_apply", "portal", ""),
    ("Delaplex", "Backend Engineer", "linkedin_easy_apply", "portal", ""),
    ("Infosys", "Technology Lead", "careers_page", "direct", "Applied via the Infosys Careers portal."),
    ("Nineleaps", "Python Backend Engineer", "cutshort", "portal", ""),
]

SNAPSHOT = {
    "post_impressions": 670,
    "post_likes": 30,
    "connections": 492,
    "note": "Café Cursor meetup post",
}


def _owner(apps):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    if settings.INGEST_OWNER_USERNAME:
        user = User.objects.filter(username=settings.INGEST_OWNER_USERNAME).first()
        if user is not None:
            return user
    return User.objects.filter(is_superuser=True).order_by("id").first()


def seed_job_search(apps, schema_editor):
    Application = apps.get_model("core", "Application")
    LinkedInSnapshot = apps.get_model("core", "LinkedInSnapshot")
    owner = _owner(apps)

    for company, role, channel, source, notes in APPLICATIONS:
        existing = Application.objects.filter(company__iexact=company, role__iexact=role).first()
        if existing is None:
            Application.objects.create(
                owner=owner,
                company=company,
                role=role,
                channel=channel,
                source=source,
                applied_on=SEED_DATE,
                last_update=SEED_DATE,
                stage="applied",
                heard_back="pending",
                notes=notes,
            )
        elif not existing.channel:
            existing.channel = channel
            existing.save(update_fields=["channel"])

    LinkedInSnapshot.objects.get_or_create(
        log_date=SEED_DATE, defaults={"owner": owner, **SNAPSHOT}
    )


def unseed_job_search(apps, schema_editor):
    # Deliberately a no-op, like 0008: once deployed these are live personal
    # rows the user may have edited (stage, heard_back), and a rollback of the
    # data seed shouldn't silently delete them.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_application_channel_heard_back_linkedinsnapshot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_job_search, unseed_job_search),
    ]
