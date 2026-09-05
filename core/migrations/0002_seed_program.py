"""
Seed the program scaffolding: phases, weeks, blocks, projects + their
milestones, cert domains, courses, skills and countdowns.

All dates are derived from core.constants.PROGRAM_START / PROGRAM_END rather
than hardcoded, so the single source of truth stays in one place.

Week-13 note: weeks 1-12 are 7 days each starting 2026-09-07. Week 13 (the
explicitly-named "buffer" week) absorbs the remainder and runs 14 days,
2026-11-30 -> 2026-12-13 — this is the only way to keep every date in the
spec simultaneously true (13 x 7 days from the start lands on 2026-12-06,
but CONVERT is stated as "weeks 9-13, 2 Nov to 13 Dec").

Everything here is seeded with owner=NULL — shared program scaffolding, not
owned by a particular user (see core.models.OwnedModel).
"""
import datetime

from django.db import migrations

from core.constants import PROGRAM_START, PROGRAM_END

WEEK_PLAN = [
    # week_no, build_focus, learn_focus, sharpen_focus
    (1, "Golden dataset, 60-80 pairs", "AI-103 D1 plan and manage", "Arrays, hashing, two-pointer"),
    (2, "Metric implementation and runner", "AI-103 D2 generative AI", "Mock interview 1 (technical)"),
    (3, "Langfuse tracing on LangGraph", "LangChain Academy LangGraph", "Trees, graphs"),
    (4, "Ablation study and CI gate", "AI-103 review, practice test 1", "Mock interview 2 (behavioural)"),
    (5, "Radar: JD ingest and fit scoring", "AI-103 D2 agents and tools", "System design: RAG architecture"),
    (6, "Tool layer: tailoring, research, drafting", "HF Agents Course", "Mock interview 3 (technical)"),
    (7, "Eval harness: 40 hand-scored JDs", "AI-103 D3 and D4", "System design: agent architecture"),
    (8, "MCP packaging and public README", "Practice test 2, weak domains", "Mock 4 (final-round sim)"),
    (9, "Ops: router and fallback", "Timed full-length practice", "Mock 5 and DSA sprint"),
    (10, "Ops: cache and cost accounting", "Final cram, weak domains", "Mock 6"),
    (11, "Portfolio site", "SIT AI-103", "Live interview loops"),
    (12, "Repo polish, record demos", "DeepLearning.AI agent evals", "STAR bank finalised"),
    (13, "Buffer", "none", "Interview loops"),
]

BLOCKS = [
    ("B1", "BUILD", "build", 90, 150),
    ("B2", "LEARN", "learn", 60, 90),
    ("B3", "APPLY", "apply", 30, 45),
    ("B4", "SHARPEN", "sharpen", 60, 75),
    ("B5", "FLEX", "flex", 45, 60),
]

PROJECT_A_MILESTONES = [
    "Golden dataset",
    "Faithfulness metric",
    "Context precision and recall",
    "Answer relevancy",
    "Langfuse tracing",
    "Ablation: HyDE on/off",
    "Ablation: reranker on/off",
    "CI regression gate",
    "EVALUATION.md published",
]
PROJECT_B_MILESTONES = [
    "JD ingest",
    "Structured fit scoring",
    "Resume tailoring tool",
    "Company research tool",
    "Outreach drafting",
    "40 hand-scored JDs",
    "Correlation study",
    "MCP packaging",
]
PROJECT_C_MILESTONES = [
    "Provider router",
    "Fallback chain",
    "Semantic cache",
    "Cost accounting",
    "Budget circuit-breaker",
]

CERT_DOMAINS = [
    (1, "Plan and manage an Azure AI solution", 20),
    (2, "Implement generative AI and agentic solutions", 30),
    (3, "Implement computer vision solutions", 15),
    (4, "Implement text analysis solutions", 15),
    (5, "Implement information extraction solutions", 20),
]

COURSES = [
    ("Microsoft Learn AI-103 path", "Microsoft", "exam_cert"),
    ("Introduction to LangGraph", "LangChain Academy", "certificate"),
    ("AI Agents Course", "Hugging Face", "certificate"),
    ("Agent and RAG evaluation courses", "DeepLearning.AI", "certificate"),
    ("Claude 101 and Claude Code", "Anthropic", "certificate"),
]

SKILLS = [
    ("Python", "engineering"),
    ("Django/DRF", "engineering"),
    ("AWS", "infrastructure"),
    ("RAG and retrieval", "ai"),
    ("Agents and tool use", "ai"),
    ("LLM evaluation", "ai"),
    ("MLOps", "ai"),
    ("System design", "engineering"),
    ("DSA", "interview"),
    ("Technical writing", "communication"),
]


def seed_program(apps, schema_editor):
    Phase = apps.get_model("core", "Phase")
    Week = apps.get_model("core", "Week")
    Block = apps.get_model("core", "Block")
    Project = apps.get_model("core", "Project")
    Milestone = apps.get_model("core", "Milestone")
    CertDomain = apps.get_model("core", "CertDomain")
    Course = apps.get_model("core", "Course")
    Skill = apps.get_model("core", "Skill")
    Countdown = apps.get_model("core", "Countdown")

    def week_bounds(week_no):
        if week_no <= 12:
            start = PROGRAM_START + datetime.timedelta(weeks=week_no - 1)
            end = start + datetime.timedelta(days=6)
        else:
            start = PROGRAM_START + datetime.timedelta(weeks=12)
            end = PROGRAM_END
        return start, end

    # --- Phases ---
    prove_start, _ = week_bounds(1)
    _, prove_end = week_bounds(4)
    ship_start, _ = week_bounds(5)
    _, ship_end = week_bounds(8)
    convert_start, _ = week_bounds(9)
    _, convert_end = week_bounds(13)

    phase_prove = Phase.objects.create(
        name="PROVE", phase_no=1, theme="Attach numbers to work already done",
        start_date=prove_start, end_date=prove_end,
    )
    phase_ship = Phase.objects.create(
        name="SHIP", phase_no=2, theme="Build and measure an agent",
        start_date=ship_start, end_date=ship_end,
    )
    phase_convert = Phase.objects.create(
        name="CONVERT", phase_no=3, theme="Sit the exam, close the loop, interview",
        start_date=convert_start, end_date=convert_end,
    )
    phase_by_week = {}
    for wn in range(1, 5):
        phase_by_week[wn] = phase_prove
    for wn in range(5, 9):
        phase_by_week[wn] = phase_ship
    for wn in range(9, 14):
        phase_by_week[wn] = phase_convert

    # --- Weeks ---
    for week_no, build_focus, learn_focus, sharpen_focus in WEEK_PLAN:
        start, end = week_bounds(week_no)
        Week.objects.create(
            week_no=week_no,
            phase=phase_by_week[week_no],
            start_date=start,
            end_date=end,
            theme=phase_by_week[week_no].name,
            build_focus=build_focus,
            learn_focus=learn_focus,
            sharpen_focus=sharpen_focus,
        )

    # --- Blocks ---
    for code, label, category, tmin, tmax in BLOCKS:
        Block.objects.create(
            code=code, label=label, category=category,
            typical_minutes_min=tmin, typical_minutes_max=tmax,
        )

    # --- Projects + milestones ---
    project_a = Project.objects.create(
        code="A", name="Case Intel Eval Harness",
        one_liner="Attach measured retrieval quality to a live legal RAG platform.",
        status="active", tech=[],
        publish_gate="Advocate sign-off at dad's office",
    )
    for title in PROJECT_A_MILESTONES:
        Milestone.objects.create(title=title, project=project_a, category="project", status="todo")

    project_b = Project.objects.create(
        code="B", name="Recruiter Radar (MCP)",
        one_liner="An agent that scores job fit, tailors resumes and drafts outreach, "
                   "with a measured accuracy number.",
        status="planned", tech=[],
    )
    for title in PROJECT_B_MILESTONES:
        Milestone.objects.create(title=title, project=project_b, category="project", status="todo")

    project_c = Project.objects.create(
        code="C", name="LLM Ops Layer",
        one_liner="Provider routing, semantic cache and cost circuit-breaker across three providers.",
        status="planned", tech=[],
    )
    for title in PROJECT_C_MILESTONES:
        Milestone.objects.create(title=title, project=project_c, category="project", status="todo")

    # --- Cert domains (AI-103) ---
    for domain_no, name, weight_pct in CERT_DOMAINS:
        CertDomain.objects.create(
            cert_code="AI-103", domain_no=domain_no, name=name,
            weight_pct=weight_pct, weight_is_approximate=True, mastery_pct=0,
        )

    # --- Courses ---
    for name, provider, credential_type in COURSES:
        Course.objects.create(name=name, provider=provider, credential_type=credential_type, active=True)

    # --- Skills, all at level 0 ---
    for name, category in SKILLS:
        Skill.objects.create(name=name, category=category, level=0, target=0)

    # --- Countdowns ---
    Countdown.objects.create(label="AI-103 exam", target_date=None, editable=True)
    Countdown.objects.create(label="Program end", target_date=PROGRAM_END, editable=False)
    Countdown.objects.create(label="AWS credit runway", target_date=datetime.date(2026, 10, 17), editable=True)


def unseed_program(apps, schema_editor):
    for model_name in (
        "Countdown", "Skill", "Course", "CertDomain", "Milestone", "Project",
        "Block", "Week", "Phase",
    ):
        apps.get_model("core", model_name).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_program, unseed_program),
    ]
