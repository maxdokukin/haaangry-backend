# pip install anthropic python-dotenv
import os
from typing import Optional, List
from dotenv import load_dotenv
import anthropic

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

    def ask_with_web(self, prompt: str) -> str:
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
                "max_uses": 5,
                # optional: "allowed_domains": ["example.com"], "blocked_domains": [...]
                # optional: "user_location": {"type":"approximate","city":"San Francisco","region":"California","country":"US","timezone":"America/Los_Angeles"}
            },
            {
                "type": "web_fetch_20250910",
                "name": "web_fetch",
                "max_uses": 5,
                "citations": {"enabled": True},
                # optional: "allowed_domains": ["example.com"], "blocked_domains": [...]
                # optional: "max_content_tokens": 100000
            },
        ]

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            # Required for web_fetch beta per docs
            extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        )
        return self._combine_text(resp)

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
