"""Extraction with a local model served by Ollama.

The output schema is enforced by Ollama's structured outputs (`format`), which
constrains decoding to the JSON schema. `max_red_flags` in the config adds
`maxItems` to that schema: small models can loop on the list until they run out
of tokens, and the grammar then closes the list instead. Connection errors and
timeouts are retried with exponential backoff.
"""

import os
import time

import httpx

from lease_redflag_detector.extraction.extractor import (
    Extraction,
    RunConfig,
    load_prompt,
    validate_output,
)
from lease_redflag_detector.extraction.schema import LeaseAbstract


def output_schema(max_red_flags: int | None) -> dict:
    schema = LeaseAbstract.model_json_schema()
    if max_red_flags is not None:
        schema["properties"]["red_flags"]["maxItems"] = max_red_flags
    return schema


class OllamaExtractor:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.system = load_prompt(config.prompt)
        self.schema = output_schema(config.max_red_flags)
        self.client = httpx.Client(
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            timeout=config.timeout_s,
        )

    def _chat(self, text: str) -> dict:
        request = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": f"<lease>\n{text}\n</lease>"},
            ],
            "format": self.schema,
            "stream": False,
            "think": False,
            "options": {
                **self.config.sampling,
                "num_ctx": self.config.context_tokens,
                "num_predict": self.config.max_tokens,
            },
        }
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.post("/api/chat", json=request)
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == self.config.max_retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def extract(self, text: str) -> Extraction:
        start = time.perf_counter()
        try:
            response = self._chat(text)
        except httpx.HTTPError as e:
            return Extraction(
                status="failed",
                raw="",
                error=f"{type(e).__name__}: {e}",
                latency_s=time.perf_counter() - start,
            )
        latency = time.perf_counter() - start

        raw = response["message"]["content"]
        if response.get("done_reason") == "length":
            output, error = None, "output truncated at max_tokens"
        else:
            output, error = validate_output(raw)
        return Extraction(
            status="ok" if output else "failed",
            raw=raw,
            output=output,
            error=error,
            latency_s=latency,
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            extra={"stop_reason": response.get("done_reason")},
        )
