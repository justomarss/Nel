import math

from google import genai
from google.genai import types
from openai import OpenAI

from src.errors import ProviderError


GEMINI_MODEL_ID = "gemini-3.5-flash-lite"


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


class GeminiProvider:
    def __init__(
        self,
        model: str | None,
        api_key: str | None,
        timeout: float = 45.0,
    ):
        if (
            model != GEMINI_MODEL_ID
            or not isinstance(api_key, str)
            or not api_key.strip()
        ):
            raise ProviderError(
                "Gemini provider configuration is unavailable."
            )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ProviderError(
                "Gemini provider configuration is unavailable."
            )

        self.model = model
        try:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=round(timeout * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as exc:
            raise ProviderError(
                "Gemini provider configuration failed "
                f"({type(exc).__name__})."
            ) from None

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
    ) -> str:
        return self._generate(
            prompt,
            system_instruction=system_instruction,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        schema_name: str,
        *,
        system_instruction: str | None = None,
    ) -> str:
        del schema_name
        return self._generate(
            prompt,
            system_instruction=system_instruction,
            response_schema=schema,
        )

    def _generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        config = {
            "system_instruction": system_instruction,
        }
        if response_schema is not None:
            config.update(
                response_mime_type="application/json",
                response_json_schema=response_schema,
            )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config),
            )
            content = response.text
        except Exception as exc:
            raise ProviderError(
                f"Gemini request failed ({type(exc).__name__})."
            ) from None

        if not content or not content.strip():
            raise ProviderError("Gemini returned an empty response.")

        return content
