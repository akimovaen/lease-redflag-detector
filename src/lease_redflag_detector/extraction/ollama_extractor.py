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
    BaseExtractor,
    Completion,
    RunConfig,
)
from lease_redflag_detector.extraction.schema import LeaseAbstract


def output_schema(max_red_flags: int | None) -> dict:
    schema = LeaseAbstract.model_json_schema()
    if max_red_flags is not None:
        schema["properties"]["red_flags"]["maxItems"] = max_red_flags
    return schema


class OllamaExtractor(BaseExtractor):
    errors = (httpx.HTTPError,)

    def __init__(self, config: RunConfig) -> None:
        super().__init__(config)
        self.schema = output_schema(config.max_red_flags)
        self.client = httpx.Client(
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            timeout=config.timeout_s,
        )

    def _post(self, request: dict) -> dict:
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

    def _complete(self, messages: list[dict]) -> Completion:
        response = self._post(
            {
                "model": self.config.model,
                "messages": [{"role": "system", "content": self.system}, *messages],
                "format": self.schema,
                "stream": False,
                "think": False,
                "options": {
                    **self.config.sampling,
                    "num_ctx": self.config.context_tokens,
                    "num_predict": self.config.max_tokens,
                },
            }
        )
        return Completion(
            raw=response["message"]["content"],
            truncated=response.get("done_reason") == "length",
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            stop_reason=response.get("done_reason"),
        )
