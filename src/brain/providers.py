from openai import OpenAI


class NvidiaNimProvider:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 30.0,
    ):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            error_type = type(exc).__name__
            raise RuntimeError(
                f"NVIDIA NIM request failed ({error_type})."
            ) from exc

        if not response.choices:
            raise RuntimeError("NVIDIA NIM returned an empty response.")

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("NVIDIA NIM returned an empty response.")

        return content
