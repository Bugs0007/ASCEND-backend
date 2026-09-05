"""
Program-wide constants. Single source of truth — models, migrations, analytics
and tests all import from here rather than hardcoding numbers.
"""
import datetime

# --- Program dates ---
PROGRAM_START = datetime.date(2026, 9, 7)   # Day 1, PROVE begins
PROGRAM_END = datetime.date(2026, 12, 13)   # End of CONVERT / week 13 buffer
PROGRAM_TOTAL_WEEKS = 13

# --- Blocks / green day ---
# A day is "green" once at least this many of the 5 blocks are completed.
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
