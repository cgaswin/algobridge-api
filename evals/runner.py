import json
import statistics
from pathlib import Path

from pydantic import ValidationError

from evals.prompts import (
    GENERATION_SYSTEM,
    JUDGE_SYSTEM,
    PROMPT_VERSION,
    build_generation_prompt,
    build_judge_prompt,
)
from evals.providers import Provider, RateLimiter, RetryableError, complete_with_retries
from evals.schema import (
    RESULTS_DIR,
    Insight,
    JudgmentBatch,
    Problem,
    parse_json_text,
    structural_issues,
)

SCORE_FIELDS = ("accuracy", "specificity", "relevance", "agreement")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


async def generate(
    problems: list[Problem],
    run_dir: Path,
    provider: Provider | None,
    limiter: RateLimiter,
    force: bool = False,
) -> None:
    """Generate one output per problem. provider=None writes the references (pipeline check)."""
    _write_json(
        run_dir / "run.json",
        {
            "provider": provider.name if provider else "reference",
            "model": provider.model if provider else "reference",
            "prompt_version": PROMPT_VERSION,
        },
    )

    for problem in problems:
        path = run_dir / "outputs" / f"{problem.slug}.json"
        if path.exists() and not force:
            continue

        if provider is None:
            raw, latency_ms, input_tokens, output_tokens = (
                problem.reference.model_dump_json(),
                0,
                None,
                None,
            )
        else:
            print(f"generate {problem.slug}")
            try:
                result = await complete_with_retries(
                    provider,
                    limiter,
                    GENERATION_SYSTEM,
                    build_generation_prompt(problem),
                    Insight,
                )
            except RetryableError as exc:
                print(
                    f"Stopped: {exc}. Likely a rate limit or daily quota; rerun the same command later to resume."
                )
                return
            raw, latency_ms = result.text, result.latency_ms
            input_tokens, output_tokens = result.input_tokens, result.output_tokens

        parsed, schema_error, issues = None, None, []
        try:
            parsed = Insight.model_validate(parse_json_text(raw))
            issues = structural_issues(parsed, problem)
        except (ValueError, ValidationError) as exc:
            schema_error = str(exc)[:500]

        _write_json(
            path,
            {
                "slug": problem.slug,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "raw": raw,
                "parsed": parsed.model_dump() if parsed else None,
                "schema_error": schema_error,
                "issues": issues,
            },
        )


async def judge(
    problems: list[Problem],
    run_dir: Path,
    judge_provider: Provider,
    judge_tag: str,
    limiter: RateLimiter,
    batch_size: int,
    force: bool = False,
) -> None:
    by_slug = {p.slug: p for p in problems}
    judge_dir = run_dir / "judgments" / judge_tag

    pending: list[tuple[Problem, Insight]] = []
    for path in sorted((run_dir / "outputs").glob("*.json")):
        output = _read_json(path)
        slug = output["slug"]
        if slug not in by_slug or output["parsed"] is None:
            continue
        if (judge_dir / f"{slug}.json").exists() and not force:
            continue
        pending.append((by_slug[slug], Insight.model_validate(output["parsed"])))

    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        print(f"judge {', '.join(p.slug for p, _ in batch)}")
        try:
            result = await complete_with_retries(
                judge_provider,
                limiter,
                JUDGE_SYSTEM,
                build_judge_prompt(batch),
                JudgmentBatch,
            )
        except RetryableError as exc:
            print(f"Stopped: {exc}. Rerun the same command later to resume.")
            return

        try:
            judgments = JudgmentBatch.model_validate(
                parse_json_text(result.text)
            ).judgments
        except (ValueError, ValidationError) as exc:
            print(
                f"  judge returned invalid output, will retry this batch next run: {str(exc)[:200]}"
            )
            continue

        expected = {p.slug for p, _ in batch}
        for judgment in judgments:
            if judgment.slug in expected:
                _write_json(judge_dir / f"{judgment.slug}.json", judgment.model_dump())
                expected.discard(judgment.slug)
        if expected:
            print(
                f"  judge skipped {', '.join(sorted(expected))}; rerun to fill them in"
            )


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _fmt(value: float | None, pattern: str = "{:.2f}") -> str:
    return "–" if value is None else pattern.format(value)


def build_report(total_problems: int, results_dir: Path = RESULTS_DIR) -> str:
    header = (
        "| run | judge | judged | schema ok | spoiler ok | accuracy | specificity | relevance "
        "| agreement | overall | p50 latency | avg out tokens |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for run_dir in sorted(p.parent for p in results_dir.glob("*/run.json")):
        outputs = [_read_json(p) for p in sorted((run_dir / "outputs").glob("*.json"))]
        valid = [o for o in outputs if o["parsed"] is not None]
        spoiler_ok = [
            o for o in valid if not any(i.startswith("spoiler") for i in o["issues"])
        ]
        latencies = [o["latency_ms"] / 1000 for o in outputs if o["latency_ms"]]
        out_tokens = [o["output_tokens"] for o in outputs if o["output_tokens"]]
        base = [
            f"{len(valid)}/{total_problems}",
            f"{len(spoiler_ok)}/{len(valid)}" if valid else "–",
        ]
        tail = [
            _fmt(statistics.median(latencies) if latencies else None, "{:.1f}s"),
            _fmt(_mean(out_tokens), "{:.0f}"),
        ]

        judge_dirs = sorted(p for p in (run_dir / "judgments").glob("*") if p.is_dir())
        if not judge_dirs:
            rows.append([run_dir.name, "–", "0", *base, *["–"] * 5, *tail])
        for judge_dir in judge_dirs:
            judgments = [_read_json(p) for p in judge_dir.glob("*.json")]
            means = [_mean([j[f] for j in judgments]) for f in SCORE_FIELDS]
            overall = _mean([m for m in means if m is not None])
            rows.append(
                [
                    run_dir.name,
                    judge_dir.name,
                    f"{len(judgments)}/{total_problems}",
                    *base,
                    *(_fmt(m) for m in means),
                    _fmt(overall),
                    *tail,
                ]
            )

    return header + "".join("| " + " | ".join(row) + " |\n" for row in rows)
