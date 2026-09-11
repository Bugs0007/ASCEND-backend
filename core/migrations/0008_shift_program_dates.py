"""
Re-derive the seeded schedule from core.constants.PROGRAM_START/_END after a
start-date change (2026-09-07 -> 2026-09-11, PROGRAM_END shifted by the same
+4 days so the program's length is unchanged).

0002_seed_program wrote Phase/Week start_date/end_date and the "Program end"
Countdown from PROGRAM_START/_END *as they stood at seed time*. Editing those
constants in constants.py does not retroactively touch those already-written
rows — migrations run once, not on every deploy. This migration re-applies
0002's exact week_bounds()/phase-boundary formula against whatever
PROGRAM_START/_END hold *right now*, so the stored schedule matches the
constants again. Every other seeded row (Blocks, Projects, CertDomains,
Courses, Skills, the other two Countdowns) is date-independent and untouched.

Safe to re-run if the dates ever move again — it's a pure recomputation, not
additive.
"""
import datetime

from django.db import migrations

from core.constants import PROGRAM_END, PROGRAM_START


def _week_bounds(week_no):
    # Identical to 0002_seed_program.week_bounds — weeks 1-12 are 7 days from
    # PROGRAM_START, week 13 (the buffer) absorbs whatever remains up to
    # PROGRAM_END.
    if week_no <= 12:
        start = PROGRAM_START + datetime.timedelta(weeks=week_no - 1)
        end = start + datetime.timedelta(days=6)
    else:
        start = PROGRAM_START + datetime.timedelta(weeks=12)
        end = PROGRAM_END
    return start, end


# Phase -> (first week, last week), matching 0002_seed_program's PROVE/SHIP/
# CONVERT split.
_PHASE_WEEK_RANGE = {1: (1, 4), 2: (5, 8), 3: (9, 13)}


def shift_program_dates(apps, schema_editor):
    Week = apps.get_model("core", "Week")
    Phase = apps.get_model("core", "Phase")
    Countdown = apps.get_model("core", "Countdown")

    for week in Week.objects.all():
        week.start_date, week.end_date = _week_bounds(week.week_no)
        week.save(update_fields=["start_date", "end_date"])

    for phase in Phase.objects.all():
        week_range = _PHASE_WEEK_RANGE.get(phase.phase_no)
        if week_range is None:
            continue  # unknown phase_no — leave it alone rather than guess
        first_week, last_week = week_range
        phase.start_date, _ = _week_bounds(first_week)
        _, phase.end_date = _week_bounds(last_week)
        phase.save(update_fields=["start_date", "end_date"])

    # editable=False in the app layer (core.views.CountdownDetailView); this
    # is the migration path for the one legitimate reason to move it anyway.
    Countdown.objects.filter(label="Program end").update(target_date=PROGRAM_END)


def unshift_program_dates(apps, schema_editor):
    # Not meaningfully reversible — we don't know the PROGRAM_START/_END this
    # migration overwrote. A no-op keeps `migrate core 0007` from erroring
    # rather than pretending to restore the prior schedule.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_backlogitem_dailyrecommendation_todayselection"),
    ]

    operations = [
        migrations.RunPython(shift_program_dates, unshift_program_dates),
    ]
