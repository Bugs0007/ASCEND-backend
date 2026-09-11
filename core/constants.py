"""
Program-wide constants. Single source of truth — models, migrations, analytics
and tests all import from here rather than hardcoding numbers.
"""
import datetime

# --- Program dates ---
# These two are independent constants, NOT one derived from the other —
# changing PROGRAM_START alone does not move PROGRAM_END or the program's
# length. Moved together 2026-09-11 (was 2026-09-07): both shifted by the
# same +4 days so the length (97 days) is unchanged. Also: editing either
# constant does NOT retroactively update rows 0002_seed_program already
# wrote (Phase/Week start_date/end_date, the "Program end" Countdown) —
# migrations run once. See migrations/0008_shift_program_dates.py, which
# re-derives those rows from whatever these constants hold when it runs.
PROGRAM_START = datetime.date(2026, 9, 11)   # Day 1, PROVE begins
PROGRAM_END = datetime.date(2026, 12, 17)   # End of CONVERT / week 13 buffer
PROGRAM_TOTAL_WEEKS = 13

# --- Green day / streak ---
# A day is "green" once at least ceil(planned * NUMERATOR / DENOMINATOR) of
# that day's TodaySelection tasks are done, with a minimum of one planned
# task. Replaces the old fixed "4 of 5 blocks" rule now that a day's task
# list is any length. ceil(n * 2 / 3): 1->1, 2->2, 3->2, 4->3, 5->4 (the old
# bar), 6->4. See core/analytics/streaks.py.
GREEN_DAY_DONE_NUMERATOR = 2
GREEN_DAY_DONE_DENOMINATOR = 3
# Legacy: the BlockEntry-era green-day bar. The block model is retained but no
# longer drives the streak; kept here only so nothing importing it breaks.
GREEN_DAY_BLOCK_THRESHOLD = 4

# --- Steps target (DailyLog.steps_after_10) ---
STEPS_TARGET = 6000

# --- Applications / funnel ---
# An Application with no last_update movement for this many days (or more) is
# reported as "ghosted" by the analytics layer. >= boundary: day 20 not
# ghosted, day 21 ghosted. Never mutates the stored `stage`.
GHOST_DAYS = 21
# Stages counted as "reached an interview" for interview-rate-per-source.
INTERVIEW_STAGES = {"screen", "oa", "tech", "final", "offer"}
# Canonical stage ordering, used to resolve "furthest stage reached" and for
# funnel stage-to-stage conversion.
STAGE_ORDER = ["applied", "screen", "oa", "tech", "final", "offer"]
TERMINAL_STAGES = {"rejected", "ghosted"}

# --- Correlations ---
# Median deep-work split threshold (hours), per spec.
DEEP_WORK_SPLIT_HOURS = 6.5

# --- Decay ---
# Projects, cert domains and applications untouched for this many days surface
# in /api/analytics/decay/.
DECAY_DAYS = 14

# --- Cert exam ---
AI103_PASS_MARK = 700
AI103_MAX_SCORE = 1000

# --- Observations ---
# Below this many days of DailyLog history, /api/analytics/observations/
# returns an empty list rather than generating something misleading.
MIN_DAYS_FOR_OBSERVATIONS = 7
MIN_OBSERVATIONS = 3
MAX_OBSERVATIONS = 6

# --- Losses ---
# Minimum postmortems in a cause bucket before it's named as "dominant".
MIN_POSTMORTEMS_FOR_DOMINANT_CAUSE = 3
