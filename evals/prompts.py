import json

from evals.schema import Insight, Problem

PROMPT_VERSION = "v2"

GENERATION_SYSTEM = """\
You are a senior software engineer. People practising algorithm problems use your answers to see where each problem shows up in real production systems.

Write three fields:

1. use_case: 1-2 sentences describing a concrete real-world scenario with the same computational core as the problem.
2. system_examples: 2-4 strings, each formatted "Named system or product — how the problem appears there".
   Only cite systems where the pattern genuinely and verifiably appears. Prefer 2 accurate examples over 4 speculative ones.
   If no well-known product applies, name a realistic category of system instead of inventing a product claim.
3. explanation: 2-3 sentences for someone who has already solved it: the key technique, its complexity compared with the naive approach, and why it matters in production.
   If the problem is mostly a teaching exercise with few direct industry uses, say so honestly.

The reader may not have solved the problem yet. use_case and system_examples must NOT name the solution technique
(for example hash map, two pointers, sliding window, binary search, heap, DFS/BFS, dynamic programming, greedy,
backtracking, trie, union-find, topological sort) unless that term is part of the problem title. explanation may name it.

Return only a JSON object with the keys use_case, system_examples, explanation.
"""

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


def build_generation_prompt(problem: Problem) -> str:
    return (
        f"Problem: {problem.title}\n"
        f"Difficulty: {problem.difficulty}\n"
        f"Tags: {', '.join(problem.tags)}\n"
        f"Description: {problem.description}\n"
    )


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
