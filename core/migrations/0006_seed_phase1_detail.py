"""
Populate the long-form detail fields added in 0005 — for Phase 1 only.

Weeks 1-4 (`build_detail`/`learn_detail`/`sharpen_detail`) and Project A's
nine milestones (`detail`). Weeks 5-13 and Projects B/C are deliberately
left NULL: that work is 10+ weeks out and will have shifted by the time
it's in front of anyone, so writing detail for it now would be guessing.

Week 1's `build_detail` is used verbatim from the program owner — it was
written and verified by hand and is not to be paraphrased. Everything else
here is concrete definition-of-done text derived from this project's
planning (WEEK_PLAN in 0002_seed_program, the Project A milestone list, and
the PROVE-phase theme "attach numbers to work already done").

Reconciliation is by natural key (`Week.week_no`, and
`Milestone.title` scoped to Project A), applied with `.update()` — additive,
idempotent, re-runnable, and a no-op on any row that isn't there. The
reverse operation sets the same fields back to NULL. Historical models
don't run `Milestone.full_clean()`, so the evidence_url gate doesn't apply
to the milestone writes here.
"""
from django.db import migrations

WEEK_1_BUILD_DETAIL = (
    "You're building a fixed set of question-and-answer pairs that becomes the exam "
    "your RAG pipeline gets scored against. Go through cases already in Case Intel and "
    "for each one write a question a real user would ask about it, paired with the "
    "verified correct answer pulled from the source document — not model-generated, "
    "hand-checked by you. Aim for 60-80 pairs, spanning your different document types, "
    "mixing easy lookups with ones requiring synthesis across a document, and including "
    "the awkward cases: dates, party names, amounts, procedural status. Store as a "
    "structured file (question, expected answer, source case id, category), versioned "
    "in the repo. No code yet — just careful, hand-verified curation."
)

# week_no -> {field: text}
WEEK_DETAIL = {
    1: {
        "build_detail": WEEK_1_BUILD_DETAIL,
        "learn_detail": (
            "Work the AI-103 'Plan and manage an Azure AI solution' path on Microsoft "
            "Learn end to end — the 20%-weight domain. Cover: picking the right Azure AI "
            "service for a task, provisioning and securing resources (keys, endpoints, "
            "Entra ID / managed identity, private endpoints, diagnostic logging), "
            "responsible-AI and content-safety considerations, container deployment, and "
            "cost/throughput planning (pricing tiers, rate limits, quotas). Done = every "
            "module checked off with each knowledge check passed, plus a note on the "
            "provisioning/security details that differ from what you already know on AWS."
        ),
        "sharpen_detail": (
            "Drill the arrays / hashing / two-pointer pattern to automatic. ~15-20 "
            "LeetCode problems across the three: hash-map lookups (two-sum family, group "
            "anagrams, top-k), sliding window (longest substring without repeats, minimum "
            "window substring), two-pointer on sorted input (3sum, container with most "
            "water, sort colors). Done = you can take a clean medium in this pattern from "
            "statement to working code in under 25 minutes, stating time/space complexity "
            "before writing anything, no hints."
        ),
    },
    2: {
        "build_detail": (
            "Implement the four scoring metrics against week 1's golden set: faithfulness, "
            "context precision, context recall, answer relevancy. Each is a pure function "
            "`(question, contexts, answer, expected) -> float` in [0,1] with a docstring "
            "stating exactly what it measures and how it's computed. Build a runner that "
            "loads the golden file, runs the current RAG pipeline over every pair, computes "
            "all four per item, and writes a timestamped results file (per-item scores + "
            "aggregate mean per metric). Done = `python -m eval.run` produces a scored "
            "report over all 60-80 pairs and the numbers hold up on a hand-checked sample "
            "of 5."
        ),
        "learn_detail": (
            "Start AI-103 'Implement generative AI and agentic solutions' (30%, the "
            "biggest domain) — the generative-AI half this week: Azure OpenAI provisioning, "
            "prompt engineering and inference parameters, the chat completions API, "
            "function calling / structured outputs, the 'on your data' RAG pattern with "
            "Azure AI Search, and content filtering. Done = the generative-AI modules "
            "complete with knowledge checks passed, plus a one-page table mapping each "
            "Azure concept to its equivalent in the stack you already run."
        ),
        "sharpen_detail": (
            "Full timed technical mock, 45-60 min, with a real interviewer or a realistic "
            "proxy — one DSA medium with follow-ups, or a medium + an easy. Record it. "
            "Done = the recording is reviewed and you've written down three concrete, "
            "specific fixes (e.g. 'state brute force before optimising', 'stop narrating "
            "once you start typing', 'test the empty-input case unprompted'). The "
            "deliverable is the fix list, not the pass/fail."
        ),
    },
    3: {
        "build_detail": (
            "Instrument the Case Intel RAG pipeline with Langfuse so every eval run and "
            "every production query emits a full trace: retrieval (query, retrieved chunk "
            "ids + scores), rerank, prompt assembly, LLM call (tokens, latency, cost), "
            "final answer. Attach the week-2 metric scores back onto their traces as "
            "Langfuse scores. Done = one eval run shows up as 60-80 traces, each drillable "
            "from question to retrieved chunks to answer, per-trace faithfulness/relevancy "
            "attached, aggregate latency and cost visible on the dashboard."
        ),
        "learn_detail": (
            "Finish LangChain Academy 'Introduction to LangGraph': the graph / state / "
            "node / edge model, conditional edges, cycles, persistence and checkpointing, "
            "human-in-the-loop interrupts, streaming. Done = course complete and one real "
            "Case Intel flow (retrieve-then-generate, or a query-rewrite loop) refactored "
            "into an explicit LangGraph graph and committed, with a short note on what the "
            "graph model bought over plain function calls."
        ),
        "sharpen_detail": (
            "Drill trees and graphs until BFS/DFS are muscle memory. ~15-20 problems: tree "
            "recursion (max depth, lowest common ancestor, path sum, level-order), BST "
            "operations, graph traversal (number of islands, clone graph, course schedule "
            "/ topological sort, word ladder). Done = you can write iterative and recursive "
            "DFS and a queue-based BFS from scratch with no reference and reach for the "
            "right one on a medium in under 30 minutes."
        ),
    },
    4: {
        "build_detail": (
            "Run the ablation: full eval (all four metrics over the golden set) under four "
            "pipeline configs — HyDE on/off crossed with reranker on/off — and produce a "
            "table of aggregate scores per config with the deltas called out, plus a short "
            "write-up of which component earns its latency/cost. Then wire the CI gate: a "
            "GitHub Actions job that runs the eval on a fixed subset on every PR and fails "
            "the build if faithfulness or context recall drops more than a set threshold "
            "below the committed baseline. Done = the ablation table is in the repo and a "
            "deliberately-worsened prompt makes CI go red."
        ),
        "learn_detail": (
            "Consolidate AI-103 domains 1-2 and take the first full practice test. Review "
            "your notes, then sit a timed full-length practice exam (MeasureUp or the "
            "official practice assessment). Done = a score recorded with a per-domain "
            "breakdown, every wrong answer worked through until you know why the right "
            "answer is right, and a ranked list of the 3-4 weakest sub-topics to target in "
            "weeks 5-8."
        ),
        "sharpen_detail": (
            "Full behavioural mock, 45 min, covering the standard set — 'tell me about "
            "yourself', a conflict, a failure, a time you led, why this role — answers in "
            "STAR form. Record it. Done = the recording is reviewed, you have a written "
            "STAR bullet for at least 6 stories, and two delivery fixes noted (rambling, "
            "burying the result, no metrics)."
        ),
    },
}

# Project A milestone title -> detail. Titles match PROJECT_A_MILESTONES in
# 0002_seed_program.py exactly.
PROJECT_A_MILESTONE_DETAIL = {
    "Golden dataset": (
        "The versioned Q&A file from week 1 exists in the repo: 60-80 hand-verified pairs "
        "as structured records (question, expected_answer, source_case_id, category), "
        "spanning every document type in Case Intel, mixing single-lookup and "
        "cross-document-synthesis questions, covering the awkward categories (dates, party "
        "names, amounts, procedural status). Every expected answer is quoted or derived "
        "from the source document and checked by you, not model-generated. Done = "
        "committed, loads clean in the runner, and a second pass over a 10-pair sample "
        "finds no wrong answers."
    ),
    "Faithfulness metric": (
        "`faithfulness(answer, contexts) -> [0,1]` implemented and documented: how much of "
        "the generated answer is actually supported by the retrieved contexts (grounded vs "
        "hallucinated claims). Done = runs over the whole golden set in the runner with "
        "per-item + aggregate output, scores a hand-planted hallucination case low, and "
        "the docstring states the method (claim decomposition + entailment check)."
    ),
    "Context precision and recall": (
        "Both retrieval metrics implemented against the golden set's `source_case_id` / "
        "chunk-level ground truth: recall = did retrieval surface the chunk(s) holding the "
        "answer; precision = how high they ranked vs noise. Done = both run in the runner "
        "with per-item + aggregate output and move in the expected direction on a "
        "known-easy vs known-hard case."
    ),
    "Answer relevancy": (
        "`answer_relevancy` implemented: how directly the answer addresses the question "
        "asked, independent of factual correctness (penalises evasive, padded, off-topic "
        "answers). Done = runs over the golden set with per-item + aggregate scores; a "
        "deliberately waffly answer to a sharp question scores low, a crisp correct one "
        "scores high."
    ),
    "Langfuse tracing": (
        "Mirrors week 3's build block: pipeline fully instrumented in Langfuse (retrieval, "
        "rerank, prompt, LLM call with tokens/latency/cost, answer) and eval-run metric "
        "scores attached to their traces. Done = one eval run appears as 60-80 drillable "
        "traces with scores and aggregate cost/latency, and a production query also shows "
        "up traced."
    ),
    "Ablation: HyDE on/off": (
        "Full eval run with HyDE (hypothetical-document-embedding query expansion) on and "
        "off, all else fixed, over the golden set. Done = a committed before/after table "
        "of all four metrics with deltas, plus a one-paragraph call on whether HyDE's "
        "retrieval gain justifies its extra LLM call per query."
    ),
    "Ablation: reranker on/off": (
        "Same for the cross-encoder reranker stage: full eval with it in and out. Done = "
        "committed metric table with deltas (expect context precision to move most), plus "
        "a call on whether the added latency is worth it and at what top-k."
    ),
    "CI regression gate": (
        "A GitHub Actions workflow runs the eval on a fixed golden subset on every PR and "
        "fails if faithfulness or context recall falls more than the agreed threshold "
        "below the committed baseline. Done = baseline checked in, a green run on main, "
        "and a PR that regresses a prompt turns the check red with a readable diff of "
        "which metric dropped."
    ),
    "EVALUATION.md published": (
        "A repo doc a hiring manager can read in five minutes: what the golden dataset is "
        "and how it was built, each metric and what it measures, current baseline numbers, "
        "the two ablation tables with conclusions, how to run the eval locally and read "
        "the CI gate. Done = EVALUATION.md committed, linked from the README, real numbers "
        "not placeholders. (Public publication stays gated on advocate sign-off — "
        "repo-ready is the milestone.)"
    ),
}


def populate_phase1_detail(apps, schema_editor):
    Week = apps.get_model("core", "Week")
    Milestone = apps.get_model("core", "Milestone")
    Project = apps.get_model("core", "Project")

    for week_no, fields in WEEK_DETAIL.items():
        Week.objects.filter(week_no=week_no).update(**fields)

    project_a = Project.objects.filter(code="A").first()
    if project_a is not None:
        for title, detail in PROJECT_A_MILESTONE_DETAIL.items():
            Milestone.objects.filter(project=project_a, title=title).update(detail=detail)


def clear_phase1_detail(apps, schema_editor):
    Week = apps.get_model("core", "Week")
    Milestone = apps.get_model("core", "Milestone")
    Project = apps.get_model("core", "Project")

    Week.objects.filter(week_no__in=list(WEEK_DETAIL)).update(
        build_detail=None, learn_detail=None, sharpen_detail=None
    )
    project_a = Project.objects.filter(code="A").first()
    if project_a is not None:
        Milestone.objects.filter(
            project=project_a, title__in=list(PROJECT_A_MILESTONE_DETAIL)
        ).update(detail=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_week_detail_milestone_detail_notion_status_changed"),
    ]

    operations = [
        migrations.RunPython(populate_phase1_detail, clear_phase1_detail),
    ]
