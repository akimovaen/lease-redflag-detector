"""Extraction with Claude through the Anthropic API.

The output schema is enforced with structured outputs. The response is validated
here rather than by `messages.parse`, so the raw output is kept when it fails.
Rate limits, server errors and timeouts are retried by the SDK client.
"""

import time

import anthropic

from lease_redflag_detector.extraction.extractor import (
    Extraction,
    RunConfig,
    load_prompt,
    validate_output,
)
from lease_redflag_detector.extraction.schema import LeaseAbstract

OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": anthropic.transform_schema(LeaseAbstract.model_json_schema()),
}


class AnthropicExtractor:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.system = load_prompt(config.prompt)
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )

    def extract(self, text: str) -> Extraction:
        start = time.perf_counter()
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=self.system,
                messages=[{"role": "user", "content": f"<lease>\n{text}\n</lease>"}],
                output_config={"format": OUTPUT_FORMAT, **self.config.sampling},
            )
        except anthropic.APIError as e:
            return Extraction(
                status="failed",
                raw="",
                error=f"{type(e).__name__}: {e}",
                latency_s=time.perf_counter() - start,
            )
        latency = time.perf_counter() - start

        raw = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens":
            output, error = None, "output truncated at max_tokens"
        else:
            output, error = validate_output(raw)
        return Extraction(
            status="ok" if output else "failed",
            raw=raw,
            output=output,
            error=error,
            latency_s=latency,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            extra={"stop_reason": response.stop_reason},
        )
