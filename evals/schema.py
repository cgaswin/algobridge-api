import json
import re
from pathlib import Path

from pydantic import BaseModel, model_validator

EVALS_DIR = Path(__file__).parent
DATASET_DIR = EVALS_DIR / "dataset"
RESULTS_DIR = EVALS_DIR / "results"

# Terms that give away the solution technique. They must not appear in
# use_case / system_examples unless they are part of the problem title.
SPOILER_TERMS = (
    "hash map",
    "hashmap",
    "hash table",
    "hash set",
    "two pointer",
    "two-pointer",
    "sliding window",
    "binary search",
    "heap",
    "priority queue",
    "dynamic programming",
    "memoization",
    "depth-first",
    "breadth-first",
    "dfs",
    "bfs",
    "backtracking",
    "greedy",
    "monotonic stack",
    "union-find",
    "union find",
    "disjoint set",
    "topological sort",
    "dijkstra",
    "prim's",
    "kruskal",
    "bellman-ford",
    "trie",
    "bit manipulation",
    "xor",
    "minimum spanning tree",
    "prefix sum",
)


class Insight(BaseModel):
    use_case: str
    system_examples: list[str]
    explanation: str


class Problem(BaseModel):
    slug: str
    title: str
    difficulty: str
    topic: str
    tags: list[str]
    url: str
    description: str
    reference: Insight


class Judgment(BaseModel):
    slug: str
    accuracy: int
    specificity: int
    relevance: int
    agreement: int
    spoiler_free: bool
    hallucinations: list[str]
    rationale: str

    @model_validator(mode="after")
    def scores_in_range(self) -> "Judgment":
        for name in ("accuracy", "specificity", "relevance", "agreement"):
            if not 1 <= getattr(self, name) <= 5:
                raise ValueError(f"{name} must be between 1 and 5")
        return self


class JudgmentBatch(BaseModel):
    judgments: list[Judgment]


def load_problems(slugs: list[str] | None = None) -> list[Problem]:
    problems = [
        Problem.model_validate_json(path.read_text())
        for path in sorted(DATASET_DIR.glob("*.json"))
    ]
    if slugs:
        wanted = set(slugs)
        unknown = wanted - {p.slug for p in problems}
        if unknown:
            raise SystemExit(f"Unknown slugs: {', '.join(sorted(unknown))}")
        problems = [p for p in problems if p.slug in wanted]
    return problems


def find_spoilers(insight: Insight, title: str) -> list[str]:
    text = " ".join([insight.use_case, *insight.system_examples]).lower()
    allowed = title.lower()
    return [
        term
        for term in SPOILER_TERMS
        if term not in allowed and re.search(rf"\b{re.escape(term)}\b", text)
    ]


def structural_issues(insight: Insight, problem: Problem) -> list[str]:
    issues = []
    if not insight.use_case.strip():
        issues.append("empty use_case")
    if not insight.explanation.strip():
        issues.append("empty explanation")
    if not 2 <= len(insight.system_examples) <= 4:
        issues.append(
            f"expected 2-4 system_examples, got {len(insight.system_examples)}"
        )
    issues.extend(f"spoiler: {term}" for term in find_spoilers(insight, problem.title))
    return issues


def parse_json_text(text: str) -> dict:
    """Parse model output, tolerating markdown fences or prose around the JSON."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start : end + 1])


def run_name(provider: str, model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{provider}__{model}")
