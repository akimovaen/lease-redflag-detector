"""Extraction with Claude through the Anthropic API.

The output schema is enforced with structured outputs. The response is validated
by `BaseExtractor` rather than by `messages.parse`, so the raw output is kept when
it fails. Rate limits, server errors and timeouts are retried by the SDK client.
"""

import anthropic

from lease_redflag_detector.extraction.extractor import (
    BaseExtractor,
    Completion,
    RunConfig,
)
from lease_redflag_detector.extraction.schema import LeaseAbstract

OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": anthropic.transform_schema(LeaseAbstract.model_json_schema()),
}


class AnthropicExtractor(BaseExtractor):
    errors = (anthropic.APIError,)

    def __init__(self, config: RunConfig) -> None:
        super().__init__(config)
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )

    def _complete(self, messages: list[dict]) -> Completion:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self.system,
            messages=messages,
            output_config={"format": OUTPUT_FORMAT, **self.config.sampling},
        )
        return Completion(
            raw="".join(b.text for b in response.content if b.type == "text"),
            truncated=response.stop_reason == "max_tokens",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
