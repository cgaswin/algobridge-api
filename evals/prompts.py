import json

from app.llm.prompts import (
    GENERATION_SYSTEM as GENERATION_SYSTEM,
    PROMPT_VERSION as PROMPT_VERSION,
    build_generation_prompt as build_generation_prompt,
)
from evals.schema import Insight, Problem

JUDGE_SYSTEM = """\
You are a strict reviewer grading AI-generated "real-world application" write-ups for algorithm problems.
Each item contains the problem, a reference answer written by an expert, and a candidate answer. Grade the candidate.

Score each dimension from 1 to 5 (3 = acceptable, 5 = as good as the reference):
- accuracy: Are the technical claims and system attributions correct? Penalize invented or misattributed product claims heavily and list each one in hallucinations.
- specificity: Concrete named systems and mechanisms (5) versus vague statements such as "used in backend services" (1).
- relevance: Does the scenario genuinely share the problem's computational core (5), or is it a loose or wrong analogy (1)?
- agreement: Does it capture the same core insight as the reference: the same kind of application and the same key technique in the explanation?
  Different but equally valid examples are fine. Judge substance, not wording.
- spoiler_free: true if use_case and system_examples avoid naming the solution technique. Only check those two fields: the explanation is supposed to name the technique and never makes this false. Terms in the problem title are allowed.

Return a JSON object {"judgments": [...]} with exactly one entry per item, using each item's slug.
Keep rationale to 1-2 sentences.
"""


def build_judge_prompt(items: list[tuple[Problem, Insight]]) -> str:
    payload = [
        {
            "slug": problem.slug,
            "title": problem.title,
            "description": problem.description,
            "reference": problem.reference.model_dump(),
            "candidate": candidate.model_dump(),
        }
        for problem, candidate in items
    ]
    return json.dumps({"items": payload}, indent=2, ensure_ascii=False)
