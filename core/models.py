"""
ASCEND core data model.

Every concrete model gets `created_at`/`updated_at` (TimeStampedModel) and a
nullable `owner` (OwnedModel) — there is exactly one human user, but querysets
are scoped to `request.user` from day one so this doesn't rot if that ever
changes. Seeded program scaffolding (Phase/Week/Block/CertDomain/Course/
Skill/Countdown) is created with owner=NULL and is shared; rows created
through the API are owned by the requesting user, and rows written by the
machine (ingest) token are attributed to the resolved ingest owner
(see core/auth.py).

Model-layer invariants that must raise ValidationError, not just hint in a
UI:
  * Milestone can't move to done without evidence_url            -> Milestone.clean()
  * "Shippable" queues exclude anything gated by a project        -> *.shippable() managers
  * The 21-day ghost rule is computed, never written to `stage`   -> Application.is_ghosted()
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.constants import GHOST_DAYS


# --------------------------------------------------------------------------
# Abstract bases
# --------------------------------------------------------------------------

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(models.Model):
    """
    owner=NULL means "shared program scaffolding" (seeded data) rather than
    "unowned" in the sense of orphaned. Ingest-written rows are attributed to
    a resolved user (see core.auth.resolve_ingest_owner) rather than left
    NULL, so machine-written data is still queryable per-user.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel, OwnedModel):
    class Meta:
        abstract = True


# --------------------------------------------------------------------------
# Program structure
# --------------------------------------------------------------------------

class Phase(BaseModel):
    name = models.CharField(max_length=50)
    phase_no = models.PositiveSmallIntegerField(unique=True)
    theme = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["phase_no"]

    def __str__(self):
        return f"P{self.phase_no} {self.name}"


class Week(BaseModel):
    week_no = models.PositiveSmallIntegerField(unique=True)
    phase = models.ForeignKey(Phase, on_delete=models.CASCADE, related_name="weeks")
    start_date = models.DateField()
    end_date = models.DateField()
    theme = models.CharField(max_length=200, blank=True)
    build_focus = models.CharField(max_length=200, blank=True)
    learn_focus = models.CharField(max_length=200, blank=True)
    sharpen_focus = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["week_no"]

    def __str__(self):
        return f"Week {self.week_no}"


class Block(BaseModel):
    class Category(models.TextChoices):
        BUILD = "build", "Build"
        LEARN = "learn", "Learn"
        APPLY = "apply", "Apply"
        SHARPEN = "sharpen", "Sharpen"
        FLEX = "flex", "Flex"

    code = models.CharField(max_length=4, unique=True)  # B1..B5
    label = models.CharField(max_length=50)
    category = models.CharField(max_length=10, choices=Category.choices)
    typical_minutes_min = models.PositiveSmallIntegerField()
    typical_minutes_max = models.PositiveSmallIntegerField()
    # Deliberate: NO start_time / end_time fields anywhere on this model.
    # Blocks are unordered-in-time buckets, not a schedule.

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.label}"


# --------------------------------------------------------------------------
# Daily tracking
# --------------------------------------------------------------------------

class DailyLog(BaseModel):
    log_date = models.DateField(unique=True)
    deep_work_minutes = models.PositiveIntegerField(default=0)
    # default=3 (mid-scale) rather than required: tapping a block to start
    # it (core.views.BlockActionView) auto-vivifies today's DailyLog before
    # any energy value has been logged.
    energy = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    steps_after_10 = models.PositiveIntegerField(default=0)
    gym = models.BooleanField(default=False)
    last_caffeine_at = models.TimeField(null=True, blank=True)
    mood = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-log_date"]

    def __str__(self):
        return f"DailyLog {self.log_date}"


class SleepLog(BaseModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        SHORTCUT = "shortcut", "iPhone Shortcut"
        ESTIMATE = "estimate", "Estimate"

    # Separate model from DailyLog on purpose: bed_at belongs to the previous
    # calendar day (you go to bed at 23:40 on the 4th and wake on the 5th),
    # so this can't be a same-day field on DailyLog without corrupting that
    # attribution.
    log_date = models.DateField(unique=True)
    bed_at = models.DateTimeField(null=True, blank=True)
    wake_at = models.DateTimeField(null=True, blank=True)
    hours = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        ordering = ["-log_date"]

    def clean(self):
        super().clean()
        if self.bed_at and self.wake_at and self.wake_at <= self.bed_at:
            raise ValidationError({"wake_at": "wake_at must be after bed_at."})

    def save(self, *args, **kwargs):
        if self.bed_at and self.wake_at:
            # Route through str() before Decimal(): DecimalField's own
            # to_python() converts a bare float via Context.create_decimal_
            # from_float(), which preserves the float's exact binary value
            # (e.g. 6.22 -> Decimal('6.2199999999999997...')) and fails the
            # decimal_places=2 validator on almost any non-round duration.
            hours = round((self.wake_at - self.bed_at).total_seconds() / 3600, 2)
            self.hours = Decimal(str(hours))
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SleepLog {self.log_date}"


class BlockEntry(BaseModel):
    daily_log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="block_entries")
    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="entries")
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)  # stamped on first tap
    ended_at = models.DateTimeField(null=True, blank=True)
    elapsed_minutes = models.PositiveIntegerField(null=True, blank=True)  # derived, wall clock
    active_minutes = models.PositiveIntegerField(null=True, blank=True)  # filled by activity agent later
    what = models.TextField(blank=True)

    class Meta:
        unique_together = ("daily_log", "block")
        ordering = ["daily_log", "block__code"]

    def save(self, *args, **kwargs):
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            self.elapsed_minutes = max(0, round(delta.total_seconds() / 60))
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.daily_log.log_date} {self.block.code}"


class ActivitySample(BaseModel):
    """
    Populated later by an external agent via the ingest endpoint. Model and
    endpoint exist now; nothing writes to it in v1.
    """
    class Category(models.TextChoices):
        BUILD = "build", "Build"
        LEARN = "learn", "Learn"
        APPLY = "apply", "Apply"
        SHARPEN = "sharpen", "Sharpen"
        FLEX = "flex", "Flex"
        IDLE = "idle", "Idle"
        DISTRACTION = "distraction", "Distraction"
        UNKNOWN = "unknown", "Unknown"

    block_entry = models.ForeignKey(
        BlockEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_samples"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    app = models.CharField(max_length=200)
    window_title = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.UNKNOWN)
    active_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.app} @ {self.started_at}"


# --------------------------------------------------------------------------
# Study / certification
# --------------------------------------------------------------------------

class Course(BaseModel):
    class CredentialType(models.TextChoices):
        EXAM_CERT = "exam_cert", "Exam certification"
        CERTIFICATE = "certificate", "Certificate of completion"
        NONE = "none", "No credential"

    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=100)
    credential_type = models.CharField(max_length=12, choices=CredentialType.choices)
    url = models.URLField(blank=True)
    progress_pct = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CertDomain(BaseModel):
    cert_code = models.CharField(max_length=20)
    domain_no = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=200)
    weight_pct = models.DecimalField(max_digits=5, decimal_places=2)
    # Microsoft publishes domain weights as ranges ("15-20%"); we store a
    # point estimate and flag it so the UI can say "approximate" rather than
    # implying false precision.
    weight_is_approximate = models.BooleanField(default=True)
    mastery_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_studied = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("cert_code", "domain_no")
        ordering = ["cert_code", "domain_no"]

    def __str__(self):
        return f"{self.cert_code} D{self.domain_no} {self.name}"


class PracticeTest(BaseModel):
    cert_code = models.CharField(max_length=20)
    taken_on = models.DateField()
    score = models.PositiveIntegerField()
    max_score = models.PositiveIntegerField(default=1000)
    per_domain = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("cert_code", "taken_on")
        ordering = ["taken_on"]

    def __str__(self):
        return f"{self.cert_code} {self.taken_on} {self.score}/{self.max_score}"


class StudySession(BaseModel):
    session_date = models.DateField()
    topic = models.CharField(max_length=200)
    category = models.CharField(max_length=50, blank=True)
    minutes = models.PositiveIntegerField()
    source = models.CharField(max_length=100, blank=True)
    cert_domain = models.ForeignKey(CertDomain, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_sessions")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_sessions")

    class Meta:
        ordering = ["-session_date"]

    def __str__(self):
        return f"{self.session_date} {self.topic} ({self.minutes}m)"


# --------------------------------------------------------------------------
# Projects / milestones
# --------------------------------------------------------------------------

class ProjectQuerySet(models.QuerySet):
    def shippable(self):
        """Shipped projects with nothing gating publication."""
        return self.filter(status=Project.Status.SHIPPED, publish_gate__isnull=True).exclude(publish_gate="")


class Project(BaseModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        SHIPPED = "shipped", "Shipped"
        PARKED = "parked", "Parked"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)
    one_liner = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    repo_url = models.URLField(blank=True)
    demo_url = models.URLField(blank=True)
    tech = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    # Non-null means: hold this out of any shippable/publish queue no matter
    # its status, e.g. "Advocate sign-off at dad's office" pending.
    publish_gate = models.TextField(null=True, blank=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["code"]

    def is_gated(self):
        return bool(self.publish_gate)

    def __str__(self):
        return f"{self.code} {self.name}"


class MilestoneQuerySet(models.QuerySet):
    def shippable(self):
        """
        Completed milestones ready to surface in a publish/content queue —
        excluding anything whose project has a non-null publish_gate.
        """
        return self.filter(status=Milestone.Status.DONE).exclude(
            project__publish_gate__isnull=False
        ).exclude(project__publish_gate="")

    def open(self):
        return self.exclude(status__in=[Milestone.Status.DONE, Milestone.Status.DROPPED])


class Milestone(BaseModel):
    class Category(models.TextChoices):
        PROJECT = "project", "Project"
        CERT = "cert", "Certification"
        CONTENT = "content", "Content"
        CAREER = "career", "Career"
        ADMIN = "admin", "Admin"

    class Status(models.TextChoices):
        TODO = "todo", "To do"
        DOING = "doing", "Doing"
        DONE = "done", "Done"
        DROPPED = "dropped", "Dropped"

    title = models.CharField(max_length=300)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name="milestones")
    phase = models.ForeignKey(Phase, on_delete=models.SET_NULL, null=True, blank=True, related_name="milestones")
    week_no = models.PositiveSmallIntegerField(null=True, blank=True)
    category = models.CharField(max_length=10, choices=Category.choices)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    completed_on = models.DateField(null=True, blank=True)
    evidence_url = models.URLField(blank=True)
    post_angle = models.TextField(blank=True)

    objects = MilestoneQuerySet.as_manager()

    class Meta:
        ordering = ["due_date", "title"]

    def clean(self):
        super().clean()
        if self.status == self.Status.DONE and not self.evidence_url:
            raise ValidationError(
                {"evidence_url": "A milestone cannot move to done without an evidence_url."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# --------------------------------------------------------------------------
# Job search
# --------------------------------------------------------------------------

class Application(BaseModel):
    class Source(models.TextChoices):
        REFERRAL = "referral", "Referral"
        DIRECT = "direct", "Direct"
        PORTAL = "portal", "Portal"
        OUTREACH = "outreach", "Outreach"

    class Stage(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREEN = "screen", "Recruiter screen"
        OA = "oa", "Online assessment"
        TECH = "tech", "Technical round"
        FINAL = "final", "Final round"
        OFFER = "offer", "Offer"
        REJECTED = "rejected", "Rejected"
        GHOSTED = "ghosted", "Ghosted (manually marked)"

    # Stages counted as "in flight" for the computed 21-day ghost rule.
    # Deliberately excludes offer/rejected/ghosted — those are resolved.
    IN_FLIGHT_STAGES = {Stage.APPLIED, Stage.SCREEN, Stage.OA, Stage.TECH, Stage.FINAL}

    company = models.CharField(max_length=200)
    role = models.CharField(max_length=200)
    source = models.CharField(max_length=10, choices=Source.choices)
    applied_on = models.DateField()
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.APPLIED)
    last_update = models.DateField()
    last_email_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    contact = models.CharField(max_length=200, blank=True)
    company_domain = models.CharField(max_length=200, blank=True)  # for email matching

    class Meta:
        unique_together = ("company", "role")
        ordering = ["-last_update"]

    def is_ghosted(self, as_of=None):
        """
        Computed-only: an in-flight application with no last_update movement
        for >= GHOST_DAYS is *reported* as ghosted by analytics. This never
        mutates `stage` — that field only changes when the user (or an
        ingest payload) explicitly sets it.
        """
        if self.stage not in self.IN_FLIGHT_STAGES:
            return False
        as_of = as_of or timezone.localdate()
        reference = self.last_update or self.applied_on
        if reference is None:
            return False
        return (as_of - reference).days >= GHOST_DAYS

    def furthest_stage(self):
        """
        The furthest pipeline stage this application is known to have
        reached, for funnel/conversion purposes. For a terminal application
        with a logged postmortem, the postmortem's round_reached is more
        informative than the bare 'rejected'/'ghosted' stage value.
        """
        if self.stage in (self.Stage.REJECTED, self.Stage.GHOSTED):
            postmortem = self.postmortems.order_by("-logged_on").first()
            if postmortem and postmortem.round_reached:
                return postmortem.round_reached
            return self.Stage.APPLIED
        return self.stage

    def __str__(self):
        return f"{self.company} — {self.role}"


class EmailEvent(BaseModel):
    class Classification(models.TextChoices):
        REJECTION = "rejection", "Rejection"
        INTERVIEW_INVITE = "interview_invite", "Interview invite"
        OA_LINK = "oa_link", "OA link"
        ACKNOWLEDGEMENT = "acknowledgement", "Acknowledgement"
        OTHER = "other", "Other"

    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_events")
    gmail_message_id = models.CharField(max_length=200, unique=True)
    received_at = models.DateTimeField()
    from_address = models.CharField(max_length=200)
    subject = models.CharField(max_length=500, blank=True)
    classified_as = models.CharField(max_length=20, choices=Classification.choices, default=Classification.OTHER)
    # Unmatched events are a review queue, not a guess: `matched` records
    # whether an application FK was resolved automatically, and `resolved`
    # records whether the 22:00 task's question about it has been answered.
    matched = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.subject} ({self.gmail_message_id})"


class LossPostmortem(BaseModel):
    class Cause(models.TextChoices):
        TAKE_HOME = "take_home", "Take-home / OA"
        SYSTEM_DESIGN = "system_design", "System design"
        DSA = "dsa", "DSA / algorithms"
        BEHAVIORAL = "behavioral", "Behavioral"
        DOMAIN_KNOWLEDGE = "domain_knowledge", "Domain knowledge"
        COMMUNICATION = "communication", "Communication"
        CULTURE_FIT = "culture_fit", "Culture fit"
        COMP_MISMATCH = "comp_mismatch", "Compensation mismatch"
        GHOSTED_BY_THEM = "ghosted_by_them", "They went silent"
        OTHER = "other", "Other"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="postmortems")
    round_reached = models.CharField(max_length=20, blank=True)
    cause = models.CharField(max_length=20, choices=Cause.choices, default=Cause.OTHER)
    what_happened = models.TextField(blank=True)
    logged_on = models.DateField()

    class Meta:
        # Natural key for ingest idempotency: one postmortem per application
        # per round reached.
        unique_together = ("application", "round_reached")
        ordering = ["-logged_on"]

    def __str__(self):
        return f"{self.application} @ {self.round_reached}"


# --------------------------------------------------------------------------
# Content / skills / reflection / countdowns
# --------------------------------------------------------------------------

class ContentPost(BaseModel):
    class Platform(models.TextChoices):
        LINKEDIN = "linkedin", "LinkedIn"
        GITHUB = "github", "GitHub"
        BLOG = "blog", "Blog"

    platform = models.CharField(max_length=10, choices=Platform.choices)
    title = models.CharField(max_length=300)
    url = models.URLField(blank=True)
    posted_on = models.DateField()
    impressions = models.PositiveIntegerField(default=0)
    reactions = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name="content_posts")

    class Meta:
        ordering = ["-posted_on"]

    def __str__(self):
        return self.title


class Skill(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, blank=True)
    level = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    target = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Reflection(BaseModel):
    log_date = models.DateField(unique=True)
    went_well = models.TextField(blank=True)
    blocked_by = models.TextField(blank=True)
    one_thing_tomorrow = models.TextField(blank=True)

    class Meta:
        ordering = ["-log_date"]

    def __str__(self):
        return f"Reflection {self.log_date}"


class Countdown(BaseModel):
    label = models.CharField(max_length=200)
    target_date = models.DateField(null=True, blank=True)  # null = TBD (e.g. exam date)
    editable = models.BooleanField(default=True)

    class Meta:
        ordering = ["target_date"]

    def __str__(self):
        return self.label
