# Insight evals

Compares LLMs on the job the API does: turning a LeetCode problem into a real-world use case, system examples, and an explanation.

## Dataset

`dataset/` holds 36 problems from NeetCode 150, two per topic (18 topics). Each file has the problem metadata, a short paraphrased description, and a hand-written `reference` answer:

```json
{
  "use_case": "1-2 sentence real-world scenario, no solution technique named",
  "system_examples": ["Named system — how the problem appears there", "..."],
  "explanation": "Technique, complexity vs naive, why it matters in production"
}
```

`use_case` and `system_examples` must not name the solution technique (hash map, heap, DP, ...) unless it is in the problem title, so users who haven't solved the problem yet don't get spoilers. `explanation` may name it.

## Flow

1. **generate** – runs a model over every problem with the prompt in `prompts.py` (`PROMPT_VERSION`). It records the raw output, the parsed JSON, schema errors, latency, tokens, and deterministic issues (wrong example count, spoiler terms).
2. **judge** – an LLM grades each valid output against the reference, scoring 1–5 for accuracy (including hallucinated product claims), specificity, relevance and agreement, plus a spoiler flag.
3. **report** – builds a comparison table and writes it to `results/report.md`.

Every step is resumable. Existing outputs and judgments are skipped, so after a rate limit or an exhausted daily quota you can rerun the same command.

## Usage

Providers:

- `gemini` and `openrouter` call the APIs directly. Set `GEMINI_API_KEY` / `OPENROUTER_API_KEY` in `algobridge-api/.env`.
- `agy` (Antigravity CLI) and `codex` (Codex CLI) run each prompt through the locally logged-in CLI, in an empty temp dir with a read-only sandbox. This uses your subscription instead of an API key. Each call carries about 16–28k tokens of agent overhead, and temperature can't be set. `agy models` lists the model IDs.

```bash
# Pipeline check: copies the references as a "run"; costs no API calls
uv run python -m evals generate --provider reference

# Candidates
uv run python -m evals generate --provider gemini --model gemini-3-flash-preview
uv run python -m evals generate --provider gemini --model gemini-3.1-flash-lite-preview
uv run python -m evals generate --provider openrouter --model meta-llama/llama-3.3-70b-instruct:free
uv run python -m evals generate --provider agy --model gemini-3.8-flash-medium --rpm 30
uv run python -m evals generate --provider codex --model gpt-6-luna --rpm 30

# Grade each run (directory names come from evals/results/)
uv run python -m evals judge --run gemini__gemini-3-flash-preview --judge-provider gemini --judge-model gemini-2.5-pro

uv run python -m evals report
```

Useful flags: `--only two-sum,lru-cache` (subset), `--rpm 5` (pacing), `--force` (redo), `--batch-size 6` (problems per judge call).

## Budget

One full candidate run takes 36 generate calls plus 6 judge calls (at the default batch size of 6). Free-tier daily limits are small and change often, so check the AI Studio dashboard. A run that hits the limit stops cleanly and resumes the next day.

Use a judge from a different model family than the candidate where you can. Models tend to rate their own outputs higher, and the CLI warns when the names match.
