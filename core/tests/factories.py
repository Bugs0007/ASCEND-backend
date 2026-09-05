"""
Plain factory functions for tests — no factory_boy dependency, just thin
wrappers around model creation with sensible defaults. The seed migration
(0002_seed_program) already populates Phase/Week/Block/Project/CertDomain/
Course/Skill/Countdown in the test database (migrations run for every test
run), so these factories look those up rather than re-creating them.
"""
import datetime

from core.models import (
    Application,
    Block,
    BlockEntry,
    CertDomain,
    Course,
    DailyLog,
    EmailEvent,
    LossPostmortem,
    Milestone,
    PracticeTest,
    Project,
    Reflection,
    SleepLog,
    StudySession,
)


def make_daily_log(log_date, **kwargs):
    defaults = dict(deep_work_minutes=120, energy=3, steps_after_10=6000, gym=False)
    defaults.update(kwargs)
    return DailyLog.objects.create(log_date=log_date, **defaults)


def make_sleep_log(log_date, bed_at=None, wake_at=None, **kwargs):
    return SleepLog.objects.create(log_date=log_date, bed_at=bed_at, wake_at=wake_at, **kwargs)


def make_block_entry(daily_log, block_code="B1", completed=True, **kwargs):
    block = Block.objects.get(code=block_code)
    return BlockEntry.objects.create(daily_log=daily_log, block=block, completed=completed, **kwargs)


def make_green_day(log_date, blocks_completed=4, **daily_log_kwargs):
    """A DailyLog with `blocks_completed` of its 5 BlockEntry rows completed."""
    log = make_daily_log(log_date, **daily_log_kwargs)
    codes = ["B1", "B2", "B3", "B4", "B5"]
    for i, code in enumerate(codes):
        make_block_entry(log, block_code=code, completed=(i < blocks_completed))
    return log


def make_application(company="Acme Corp", role="Backend Engineer", **kwargs):
    defaults = dict(
        source=Application.Source.DIRECT,
        applied_on=datetime.date(2026, 9, 10),
        stage=Application.Stage.APPLIED,
        last_update=datetime.date(2026, 9, 10),
    )
    defaults.update(kwargs)
    return Application.objects.create(company=company, role=role, **defaults)


def make_loss_postmortem(application, **kwargs):
    defaults = dict(
        round_reached="tech",
        cause=LossPostmortem.Cause.DSA,
        logged_on=datetime.date(2026, 9, 20),
    )
    defaults.update(kwargs)
    return LossPostmortem.objects.create(application=application, **defaults)


def make_practice_test(cert_code="AI-103", taken_on=None, score=650, max_score=1000, **kwargs):
    taken_on = taken_on or datetime.date(2026, 9, 15)
    return PracticeTest.objects.create(
        cert_code=cert_code, taken_on=taken_on, score=score, max_score=max_score, **kwargs
    )


def make_milestone(title="Test milestone", **kwargs):
    defaults = dict(category=Milestone.Category.PROJECT, status=Milestone.Status.TODO)
    defaults.update(kwargs)
    return Milestone.objects.create(title=title, **defaults)


def make_email_event(gmail_message_id, **kwargs):
    defaults = dict(
        received_at=datetime.datetime(2026, 9, 15, 9, 0, tzinfo=datetime.timezone.utc),
        from_address="noreply@example.com",
        subject="Update on your application",
    )
    defaults.update(kwargs)
    return EmailEvent.objects.create(gmail_message_id=gmail_message_id, **defaults)


def make_study_session(session_date=None, topic="AI-103 D1", minutes=60, **kwargs):
    session_date = session_date or datetime.date(2026, 9, 10)
    return StudySession.objects.create(session_date=session_date, topic=topic, minutes=minutes, **kwargs)


def make_reflection(log_date, **kwargs):
    return Reflection.objects.create(log_date=log_date, **kwargs)


def get_project(code="A"):
    return Project.objects.get(code=code)


def get_cert_domain(cert_code="AI-103", domain_no=1):
    return CertDomain.objects.get(cert_code=cert_code, domain_no=domain_no)


def get_course(name="Microsoft Learn AI-103 path"):
    return Course.objects.get(name=name)
