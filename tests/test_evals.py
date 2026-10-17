import json
from collections import Counter

import pytest

from evals.prompts import PROMPT_VERSION
from evals.providers import (
    AntigravityProvider,
    LLMResult,
    OpenCodeProvider,
    RateLimiter,
    strict_schema,
)
from evals.runner import build_report, generate, judge
from evals.schema import (
    Insight,
    JudgmentBatch,
    find_spoilers,
    load_problems,
    parse_json_text,
    structural_issues,
)


def test_dataset_has_two_problems_per_neetcode_topic():
    problems = load_problems()
    topics = Counter(p.topic for p in problems)

    assert len(problems) == 36
    assert len(topics) == 18
    assert set(topics.values()) == {2}


def test_references_are_structurally_valid_and_spoiler_free():
    for problem in load_problems():
        assert structural_issues(problem.reference, problem) == [], problem.slug


def test_find_spoilers_allows_terms_in_title():
    insight = Insight(
        use_case="Uses a heap and a trie to rank results",
        system_examples=["A", "B"],
        explanation="",
    )

    assert find_spoilers(insight, "Implement Trie (Prefix Tree)") == ["heap"]


def test_find_spoilers_matches_plurals_but_not_the_verb_tries():
    insight = Insight(
        use_case="Keeps two heaps balanced and tries again on failure",
        system_examples=["Uses two pointers", "B"],
        explanation="",
    )

    assert find_spoilers(insight, "Find Median") == ["two pointer", "heap"]


def test_parse_json_text_strips_markdown_fences():
    assert parse_json_text('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = iter(responses)

    async def complete(self, system, user, schema):
        return LLMResult(next(self.responses), 10, 20, 1500)


@pytest.mark.anyio
async def test_generate_judge_report_pipeline(tmp_path):
    problems = load_problems(["3sum", "lru-cache"])
    limiter = RateLimiter(rpm=60_000)
    run_dir = tmp_path / "fake__fake-model"

    candidate = problems[0].reference.model_dump()
    await generate(
        problems,
        run_dir,
        FakeProvider([json.dumps(candidate), "not json"]),
        limiter,
    )

    outputs = {
        p.stem: json.loads(p.read_text()) for p in (run_dir / "outputs").glob("*.json")
    }
    assert outputs["3sum"]["parsed"] == candidate
    assert outputs["lru-cache"]["parsed"] is None
    assert outputs["lru-cache"]["schema_error"]

    verdict = {
        "judgments": [
            {
                "slug": "3sum",
                "accuracy": 5,
                "specificity": 4,
                "relevance": 5,
                "agreement": 4,
                "spoiler_free": True,
                "hallucinations": [],
                "rationale": "Matches the reference.",
            }
        ]
    }
    await judge(
        problems,
        run_dir,
        FakeProvider([json.dumps(verdict)]),
        "fake__judge",
        limiter,
        batch_size=6,
    )

    report = build_report(load_problems(), results_dir=tmp_path)
    assert (
        "| fake__fake-model | fake__judge | 1/36 | 1/36 | 1/1 | 1/1 | 1/1 "
        "| 5.00 | 4.00 | 5.00 | 4.00 | 4.50 | 1.5s | 20 |" in report
    )


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_report_reruns_structural_checks_on_saved_outputs(tmp_path):
    problem = load_problems(["3sum"])[0]
    run_dir = tmp_path / "old__run"
    _write(run_dir / "run.json", {"prompt_version": PROMPT_VERSION})
    # Saved before the checks existed: one example and a plural spoiler, no issues recorded.
    parsed = {
        "use_case": "Balance two heaps of ledger entries",
        "system_examples": ["Only one"],
        "explanation": "x",
    }
    _write(
        run_dir / "outputs" / "3sum.json",
        {
            "slug": problem.slug,
            "latency_ms": 0,
            "output_tokens": None,
            "parsed": parsed,
            "issues": [],
        },
    )

    report = build_report([problem], results_dir=tmp_path)

    assert "| old__run | – | 0 | 1/1 | 0/1 | 0/1 |" in report


@pytest.mark.anyio
async def test_generate_refuses_to_resume_with_a_different_prompt_version(tmp_path):
    problems = load_problems(["3sum"])
    _write(tmp_path / "run.json", {"prompt_version": "v0"})

    with pytest.raises(SystemExit, match="--force"):
        await generate(problems, tmp_path, None, RateLimiter(rpm=60_000))


@pytest.mark.anyio
async def test_regenerating_an_output_drops_its_stale_judgments(tmp_path):
    problems = load_problems(["3sum", "lru-cache"])
    limiter = RateLimiter(rpm=60_000)
    await generate(problems, tmp_path, None, limiter)
    for slug in ("3sum", "lru-cache"):
        _write(tmp_path / "judgments" / "some__judge" / f"{slug}.json", {})

    await generate(problems[:1], tmp_path, None, limiter, force=True)

    output = json.loads((tmp_path / "outputs" / "3sum.json").read_text())
    assert output["prompt_version"] == PROMPT_VERSION
    assert not (tmp_path / "judgments" / "some__judge" / "3sum.json").exists()
    assert (tmp_path / "judgments" / "some__judge" / "lru-cache.json").exists()


def test_strict_schema_closes_nested_objects():
    schema = strict_schema(JudgmentBatch.model_json_schema())
    judgment = schema["$defs"]["Judgment"]

    assert schema["additionalProperties"] is False
    assert judgment["additionalProperties"] is False
    assert set(judgment["required"]) == set(judgment["properties"])


def test_antigravity_parse_prefers_structured_output(tmp_path):
    stdout = json.dumps(
        {
            "status": "SUCCESS",
            "response": "prose",
            "structured_output": {"use_case": "x"},
            "usage": {"input_tokens": 100, "output_tokens": 7},
        }
    )

    text, input_tokens, output_tokens = AntigravityProvider("m", 0).parse(
        stdout, "", tmp_path / "unused"
    )

    assert json.loads(text) == {"use_case": "x"}
    assert (input_tokens, output_tokens) == (100, 7)


def test_opencode_parse_joins_text_events(tmp_path):
    events = [
        {"type": "step_start", "part": {}},
        {"type": "text", "part": {"text": '{"use_case": '}},
        {"type": "text", "part": {"text": '"x"}'}},
    ]
    stdout = "\n".join(json.dumps(e) for e in events) + "\n"

    text, input_tokens, output_tokens = OpenCodeProvider("m", 0).parse(
        stdout, "", tmp_path / "unused"
    )

    assert json.loads(text) == {"use_case": "x"}
    assert (input_tokens, output_tokens) == (None, None)
