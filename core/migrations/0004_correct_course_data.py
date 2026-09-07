"""
Data-only correction of the five Course rows seeded by 0002_seed_program.

0002 seeded courses before the real links had been researched. Now that
they have been:

  * "Claude 101 and Claude Code" was one row for two separate real courses
    (two URLs, two completion badges) -> split into "Claude 101" and
    "Claude Code 101", both already complete.
  * DeepLearning.AI's short-course credential is an "Accomplishment", which
    their own platform states is NOT an official certificate -> the two
    DeepLearning.AI courses move from credential_type "certificate" to
    "none". The vague "Agent and RAG evaluation courses" row was also two
    distinct courses -> split into "Evaluating AI Agents" and "Building and
    Evaluating Advanced RAG".
  * LangChain Academy's "Introduction to LangGraph" certificate status
    could not be confirmed either way -> credential_type "none" for now
    rather than asserting something unverified (correctable later).
  * Every other row just needed its real url filled in.

No schema change — Course.url and every field touched here already exist.
The existing seed migration is deliberately left untouched.

Reconciliation is by NAME, not by assuming a pristine 5-row table: each
target row is matched on its canonical name first, then on any older name
it might still be stored under (`aliases`), and only created if neither is
found. Any obsolete combined row a rename didn't consume is deleted at the
end. Running this twice is a no-op and never produces a duplicate.

The reverse operation restores the post-0002 state (the 5 combined rows,
blank urls, progress 0). It is best-effort — a data correction is
inherently lossy to reverse.
"""
from django.db import migrations


# Final desired state: 9 rows. `fields` are applied over whatever the row
# currently holds; `aliases` are older names the row may still be stored
# under, so we rename rather than duplicate. progress_pct is set only where
# the correction spec gives a number — rows corrected in place keep the
# progress they already have.
TARGET_COURSES = [
    {
        "name": "Claude 101",
        "aliases": ["Claude 101 and Claude Code"],
        "fields": {
            "provider": "Anthropic",
            "credential_type": "certificate",
            "url": "https://academy.claude.com/courses/claude-101",
            "progress_pct": 100,
        },
    },
    {
        "name": "Claude Code 101",
        "fields": {
            "provider": "Anthropic",
            "credential_type": "certificate",
            "url": "https://academy.claude.com/courses/claude-code-101",
            "progress_pct": 100,
        },
    },
    {
        "name": "Claude Platform 101",
        "fields": {
            "provider": "Anthropic",
            "credential_type": "certificate",
            "url": "https://academy.claude.com/courses/claude-platform-101",
            "progress_pct": 0,
        },
    },
    {
        "name": "Introduction to LangGraph",
        "fields": {
            "provider": "LangChain Academy",
            "credential_type": "none",
            "url": "https://academy.langchain.com/courses/intro-to-langgraph",
        },
    },
    {
        "name": "AI Agents Course",
        "fields": {
            "provider": "Hugging Face",
            "credential_type": "certificate",
            "url": "https://huggingface.co/learn/agents-course",
        },
    },
    {
        "name": "Hugging Face MCP Course",
        "fields": {
            "provider": "Hugging Face",
            "credential_type": "certificate",
            "url": "https://huggingface.co/learn/mcp-course/en/unit0/introduction",
            "progress_pct": 0,
        },
    },
    {
        "name": "Evaluating AI Agents",
        "aliases": ["Agent and RAG evaluation courses"],
        "fields": {
            "provider": "DeepLearning.AI",
            "credential_type": "none",
            "url": "https://www.deeplearning.ai/courses/evaluating-ai-agents",
        },
    },
    {
        "name": "Building and Evaluating Advanced RAG",
        "fields": {
            "provider": "DeepLearning.AI",
            "credential_type": "none",
            "url": "https://www.deeplearning.ai/courses/building-evaluating-advanced-rag",
        },
    },
    {
        "name": "Microsoft Learn AI-103 path",
        "fields": {
            "provider": "Microsoft",
            "credential_type": "exam_cert",
            "url": (
                "https://learn.microsoft.com/en-us/credentials/certifications/"
                "azure-ai-apps-and-agents-developer-associate/"
            ),
        },
    },
]

OBSOLETE_COMBINED_NAMES = [
    "Claude 101 and Claude Code",
    "Agent and RAG evaluation courses",
]

# Post-0002 state, for the reverse operation.
ORIGINAL_COURSES = [
    ("Microsoft Learn AI-103 path", "Microsoft", "exam_cert"),
    ("Introduction to LangGraph", "LangChain Academy", "certificate"),
    ("AI Agents Course", "Hugging Face", "certificate"),
    ("Agent and RAG evaluation courses", "DeepLearning.AI", "certificate"),
    ("Claude 101 and Claude Code", "Anthropic", "certificate"),
]


def correct_course_data(apps, schema_editor):
    Course = apps.get_model("core", "Course")
    seen_pks = set()

    for spec in TARGET_COURSES:
        name = spec["name"]
        row = Course.objects.filter(name=name).first()
        if row is None:
            for alias in spec.get("aliases", ()):
                row = Course.objects.filter(name=alias).first()
                if row is not None:
                    break
        if row is None:
            # owner stays NULL — shared program scaffolding, like 0002.
            row = Course(name=name, active=True)

        row.name = name
        for field, value in spec["fields"].items():
            setattr(row, field, value)
        row.save()
        seen_pks.add(row.pk)

    # A rename above consumes at most one combined row per pair; if both
    # halves of a split somehow already existed, the combined row is still
    # here and now redundant.
    Course.objects.filter(name__in=OBSOLETE_COMBINED_NAMES).exclude(pk__in=seen_pks).delete()


def restore_course_data(apps, schema_editor):
    Course = apps.get_model("core", "Course")
    Course.objects.filter(name__in=[spec["name"] for spec in TARGET_COURSES]).delete()
    for name, provider, credential_type in ORIGINAL_COURSES:
        Course.objects.get_or_create(
            name=name,
            defaults={
                "provider": provider,
                "credential_type": credential_type,
                "url": "",
                "progress_pct": 0,
                "active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_notiontask"),
    ]

    operations = [
        migrations.RunPython(correct_course_data, restore_course_data),
    ]
