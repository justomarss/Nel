from openai import OpenAI

from src.errors import ProviderError


class NvidiaNimProvider:
    def __init__(
        self,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
        timeout: float = 45.0,
    ):
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (model, api_key, base_url)
        ):
            raise ProviderError(
                "NVIDIA NIM provider configuration is unavailable."
            )
        self.model = model
        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
            )
        except Exception as exc:
            raise ProviderError(
                "NVIDIA NIM provider configuration failed "
                f"({type(exc).__name__})."
            ) from None

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        schema_name: str,
    ) -> str:
        return self._generate(
            prompt,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )

    def _generate(
        self,
        prompt: str,
        response_format: dict | None = None,
    ) -> str:
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if response_format is not None:
            request["response_format"] = response_format

        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            error_type = type(exc).__name__
            raise ProviderError(
                f"NVIDIA NIM request failed ({error_type})."
            ) from None

        if not response.choices:
            raise ProviderError("NVIDIA NIM returned an empty response.")

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ProviderError("NVIDIA NIM returned an empty response.")

        return content
