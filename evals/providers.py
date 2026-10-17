import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


@dataclass
class LLMResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class RetryableError(Exception):
    def __init__(self, status: int, message: str, retry_after: float | None = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.retry_after = retry_after


class Provider(Protocol):
    name: str
    model: str

    async def complete(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> LLMResult: ...


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set (add it to algobridge-api/.env)")
    return value


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, temperature: float):
        from google import genai

        self.model = model
        self.temperature = temperature
        self.client = genai.Client(api_key=_require_env("GEMINI_API_KEY"))

    async def complete(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> LLMResult:
        from google.genai import errors, types

        start = time.perf_counter()
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except errors.APIError as exc:
            if exc.code in RETRYABLE_STATUS:
                raise RetryableError(exc.code, str(exc)[:300]) from exc
            raise

        usage = response.usage_metadata
        return LLMResult(
            text=response.text or "",
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


def strict_schema(schema: dict) -> dict:
    """Close every object schema, as OpenAI-style structured outputs require."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
    for value in schema.values():
        if isinstance(value, dict):
            strict_schema(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    strict_schema(item)
    return schema


class CliProvider:
    """Uses a coding-agent CLI as a plain prompt-to-JSON model.

    Runs in an empty temp dir with a read-only sandbox so the agent has nothing to
    explore. Temperature is not configurable through these CLIs and is ignored.
    """

    name = "cli"
    timeout_s = 600.0
    prompt_via_stdin = True
    # Set for CLIs without a structured-output flag; the schema goes in the prompt.
    schema_in_prompt = False

    def __init__(self, model: str, temperature: float):
        self.model = model

    def command(self, prompt: str, schema_path: Path, out_path: Path) -> list[str]:
        raise NotImplementedError

    def parse(
        self, stdout: str, stderr: str, out_path: Path
    ) -> tuple[str, int | None, int | None]:
        raise NotImplementedError

    async def complete(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> LLMResult:
        schema_json = json.dumps(strict_schema(schema.model_json_schema()))
        prompt = f"{system}\n\n{user}\n\n"
        if self.schema_in_prompt:
            prompt += f"The JSON must match this schema, with every field present:\n{schema_json}\n\n"
        prompt += "Do not use any tools, read files, or run commands. Answer directly with the JSON object only."
        with tempfile.TemporaryDirectory(prefix="algobridge-eval-") as tmp:
            schema_path, out_path = Path(tmp) / "schema.json", Path(tmp) / "out.txt"
            schema_path.write_text(schema_json)

            start = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *self.command(prompt, schema_path, out_path),
                cwd=tmp,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode() if self.prompt_via_stdin else b""),
                    self.timeout_s,
                )
            except TimeoutError:
                proc.kill()
                raise RetryableError(
                    504, f"{self.name} timed out after {self.timeout_s:.0f}s"
                )
            latency_ms = int((time.perf_counter() - start) * 1000)

            out, err = stdout.decode(), stderr.decode()
            if proc.returncode != 0:
                message = (err or out)[-500:]
                if any(
                    s in message.lower()
                    for s in ("rate limit", "quota", "429", "resource_exhausted")
                ):
                    raise RetryableError(429, message)
                raise RuntimeError(
                    f"{self.name} exited with {proc.returncode}: {message}"
                )
            text, input_tokens, output_tokens = self.parse(out, err, out_path)

        return LLMResult(text, input_tokens, output_tokens, latency_ms)


class AntigravityProvider(CliProvider):
    name = "agy"
    prompt_via_stdin = False

    def command(self, prompt: str, schema_path: Path, out_path: Path) -> list[str]:
        return [
            "agy", "-p", prompt, "--model", self.model, "--sandbox",
            "--output-format", "json", "--json-schema", str(schema_path),
            "--print-timeout", f"{self.timeout_s:.0f}s",
        ]  # fmt: skip

    def parse(
        self, stdout: str, stderr: str, out_path: Path
    ) -> tuple[str, int | None, int | None]:
        data = json.loads(stdout)
        if data.get("status") != "SUCCESS":
            raise RuntimeError(f"agy status {data.get('status')}: {stdout[-500:]}")
        usage = data.get("usage") or {}
        structured = data.get("structured_output")
        text = (
            json.dumps(structured)
            if isinstance(structured, dict)
            else data.get("response", "")
        )
        return text, usage.get("input_tokens"), usage.get("output_tokens")


class CodexProvider(CliProvider):
    name = "codex"

    def command(self, prompt: str, schema_path: Path, out_path: Path) -> list[str]:
        return [
            "codex", "exec", "-m", self.model,
            "--ignore-user-config", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
            "--output-schema", str(schema_path), "-o", str(out_path), "-",
        ]  # fmt: skip

    def parse(
        self, stdout: str, stderr: str, out_path: Path
    ) -> tuple[str, int | None, int | None]:
        # codex only reports a combined total ("tokens used\n16,313") on stderr.
        return out_path.read_text() if out_path.exists() else "", None, None


class OpenCodeProvider(CliProvider):
    name = "opencode"
    schema_in_prompt = True

    def command(self, prompt: str, schema_path: Path, out_path: Path) -> list[str]:
        return [
            "opencode", "run", "--standalone", "-m", self.model, "--format", "json",
        ]  # fmt: skip

    def parse(
        self, stdout: str, stderr: str, out_path: Path
    ) -> tuple[str, int | None, int | None]:
        # JSON lines of events; opencode run doesn't report token usage.
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        text = "".join(
            e["part"].get("text", "") for e in events if e.get("type") == "text"
        )
        return text, None, None


PROVIDERS: dict[str, type] = {
    "gemini": GeminiProvider,
    "agy": AntigravityProvider,
    "codex": CodexProvider,
    "opencode": OpenCodeProvider,
}


def make_provider(name: str, model: str, temperature: float) -> Provider:
    if name not in PROVIDERS:
        raise SystemExit(
            f"Unknown provider {name!r}; choose from {', '.join(PROVIDERS)}"
        )
    return PROVIDERS[name](model, temperature)


class RateLimiter:
    """Spaces calls evenly so free-tier requests-per-minute limits are respected."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm
        self.last = 0.0

    async def wait(self) -> None:
        delay = self.last + self.interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.last = time.monotonic()


async def complete_with_retries(
    provider: Provider,
    limiter: RateLimiter,
    system: str,
    user: str,
    schema: type[BaseModel],
) -> LLMResult:
    for attempt in range(MAX_ATTEMPTS):
        await limiter.wait()
        try:
            return await provider.complete(system, user, schema)
        except RetryableError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = exc.retry_after or min(60.0, 5.0 * 2**attempt)
            print(f"  {exc} — retrying in {delay:.0f}s")
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")
