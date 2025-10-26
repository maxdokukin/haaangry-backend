# pip install anthropic python-dotenv
import os
from typing import Optional, List
from dotenv import load_dotenv
import anthropic
import json

load_dotenv()


class ClaudeClient:
    """
    Minimal Claude client with optional web tools.
    - Reads ANTHROPIC_API_KEY from env by default.
    - ask(prompt) -> str
    - ask_with_web(prompt) -> str  # uses Anthropic server-side web_search + web_fetch
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-haiku-4-5",  # change if you prefer Sonnet 4.5
        max_tokens: int = 1024,
        temperature: float = 0.0,
        request_timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Set ANTHROPIC_API_KEY in your environment or pass api_key.")
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=request_timeout)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    # ---------- Public API ----------

    def ask(self, prompt: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._combine_text(resp)

    def ask_with_web_json(self, prompt: str) -> str:
        """
        Uses Anthropic's server tools:
        - web_search_20250305
        - web_fetch_20250910  (requires beta header)
        Claude decides when to call them. You just pass the tools.
        """
        tools = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 2,
            },
            {
                "type": "web_fetch_20250910",
                "name": "web_fetch",
                "max_uses": 2,
                "citations": {"enabled": True},
            },
        ]

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=(
                "Your task is to take the information provided and convert it into a well-organized JSON format. "
                "Identify the main entities, attributes, or categories and use them as keys in the JSON object. "
                "Ensure that the data is accurately represented and properly formatted within the JSON structure."
            ),
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        )

        text = self._combine_text(resp)

        # Keep only JSON: remove everything before first '{' and after last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return ""

        json_str = text[start: end + 1].strip()

        # Normalize if possible; else return the raw slice
        try:
            return json.dumps(json.loads(json_str), ensure_ascii=False)
        except Exception:
            return json_str

    # ---------- Internals ----------

    def _combine_text(self, resp: anthropic.types.Message) -> str:
        parts: List[str] = []
        for block in resp.content:
            # Concatenate only text blocks; server tool metadata is ignored.
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
        return "".join(parts).strip()


# Example
if __name__ == "__main__":
    bot = ClaudeClient()
    print(bot.ask("In one sentence, what is entropy in information theory?"))
    print(bot.ask_with_web("Summarize today's big LLM news and cite sources."))
