import argparse
import asyncio

from dotenv import load_dotenv

from evals.providers import RateLimiter, make_provider
from evals.runner import build_report, generate, judge
from evals.schema import EVALS_DIR, RESULTS_DIR, load_problems, run_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate insights for each dataset problem")
    gen.add_argument(
        "--provider", required=True, help="gemini | openrouter | reference"
    )
    gen.add_argument("--model", help="model id, required unless --provider reference")
    gen.add_argument("--temperature", type=float, default=0.3)
    gen.add_argument("--rpm", type=float, default=5, help="max requests per minute")
    gen.add_argument("--only", help="comma-separated slugs to run")
    gen.add_argument("--force", action="store_true", help="regenerate existing outputs")

    jud = sub.add_parser("judge", help="grade a run's outputs against the references")
    jud.add_argument(
        "--run", required=True, help="run directory name under evals/results"
    )
    jud.add_argument("--judge-provider", required=True)
    jud.add_argument("--judge-model", required=True)
    jud.add_argument("--rpm", type=float, default=5)
    jud.add_argument(
        "--batch-size", type=int, default=6, help="problems graded per judge call"
    )
    jud.add_argument("--only", help="comma-separated slugs to judge")
    jud.add_argument("--force", action="store_true", help="re-judge existing judgments")

    sub.add_parser("report", help="print and save the comparison table")
    return parser.parse_args()


async def main() -> None:
    load_dotenv(EVALS_DIR.parent / ".env")
    args = parse_args()

    if args.command == "report":
        report = build_report(len(load_problems()))
        (RESULTS_DIR / "report.md").parent.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / "report.md").write_text(report)
        print(report)
        return

    problems = load_problems(args.only.split(",") if args.only else None)
    limiter = RateLimiter(args.rpm)

    if args.command == "generate":
        if args.provider == "reference":
            await generate(
                problems, RESULTS_DIR / "reference", None, limiter, args.force
            )
            return
        if not args.model:
            raise SystemExit("--model is required")
        provider = make_provider(args.provider, args.model, args.temperature)
        run_dir = RESULTS_DIR / run_name(args.provider, args.model)
        await generate(problems, run_dir, provider, limiter, args.force)
        print(f"outputs in {run_dir}")
        return

    run_dir = RESULTS_DIR / args.run
    if not (run_dir / "run.json").exists():
        raise SystemExit(f"No run at {run_dir}; run `generate` first")
    if args.judge_model in args.run:
        print(
            "warning: judge model matches the candidate model; expect self-preference bias"
        )
    judge_provider = make_provider(
        args.judge_provider, args.judge_model, temperature=0.0
    )
    judge_tag = run_name(args.judge_provider, args.judge_model)
    await judge(
        problems,
        run_dir,
        judge_provider,
        judge_tag,
        limiter,
        args.batch_size,
        args.force,
    )


if __name__ == "__main__":
    asyncio.run(main())
