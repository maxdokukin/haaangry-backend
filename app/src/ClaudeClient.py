# pip install anthropic python-dotenv
import os
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import anthropic

load_dotenv()


class ClaudeClient:
    """
    Minimal Claude client with optional web tools and JSON enforcement.

    Constructor args:
      - prompt: default prompt to use if methods are called without overrides
      - model: default model
      - json_schema: optional JSON Schema dict used by ask_enforce_json()
      - api_key: overrides ANTHROPIC_API_KEY env
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        json_schema: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        request_timeout: int = 30,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ):
        self.model = model
        self.json_schema = json_schema
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Set ANTHROPIC_API_KEY in your environment or pass api_key.")
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=request_timeout)
        self.max_tokens = max_tokens
        self.temperature = temperature

    # ---------- Public API ----------

    def ask(self, prompt: Optional[str] = None) -> str:
        """Plain ask. No web tools. Free-form text."""
        p = prompt if prompt is not None else self.prompt
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": p}],
        )
        return self._combine_text(resp)

    def ask_web(self, prompt: Optional[str] = None) -> str:
        """
        Ask with Anthropic server tools:
          - web_search_20250305
          - web_fetch_20250910 (beta header required)
        Claude decides when to call them.
        """
        p = prompt if prompt is not None else self.prompt
        tools = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
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
            messages=[{"role": "user", "content": p}],
            tools=tools,
            extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        )
        return self._combine_text(resp)

    def ask_enforce_json(self, prompt: Optional[str] = None) -> str:
        """
        Ask with JSON enforcement. No web.
        Uses a dummy client tool + tool_choice to force a tool_use payload
        that matches json_schema if provided. Falls back to brace-slicing.
        Returns minified JSON string.
        """
        p = prompt if prompt is not None else self.prompt

        # If schema not provided, allow any-object to reduce failures.
        schema = (
            self.json_schema
            if isinstance(self.json_schema, dict)
            else {"type": "object", "additionalProperties": True}
        )

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=(
                f"Task: Gather and transform data. "
                f"Return JSON only that matches any reasonable object shape for the task. "
                f"No commentary. No code fences. No prefixes or suffixes."
                f"SAMPLE JSON SCHEMA REQUIRED: {schema}"
            ),
            messages=[{"role": "user", "content": p}],
        )
        print("CLAUDE OUT ", self._extract_minified_json(self._combine_text(resp)))

        return "[" + self._extract_minified_json(self._combine_text(resp)) + "]"

    def ask_web_enforce_json(self, prompt: Optional[str] = None) -> str:
        """
        Ask with web tools and enforce JSON by slicing the first {...} block,
        then minify. Adds strict instructions to avoid non-JSON output.
        """
        p = prompt if prompt is not None else self.prompt
        print("CLAUDE IN ", prompt)
        schema = (
            self.json_schema
            if isinstance(self.json_schema, dict)
            else {"type": "object", "additionalProperties": True}
        )
        tools = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
            {
                "type": "web_fetch_20250910",
                "name": "web_fetch",
                "max_uses": 2,
                "citations": {"enabled": True},
            }
        ]
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=(
                f"Task: Gather and transform data. "
                f"Return JSON only that matches any reasonable object shape for the task. "
                f"No commentary. No code fences. No prefixes or suffixes."
                f"SAMPLE JSON SCHEMA REQUIRED: {schema}"
            ),
            messages=[{"role": "user", "content": p}],
            tools=tools,
            extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        )
        print("CLAUDE OUT ", self._extract_minified_json(self._combine_text(resp)))
        return "[" + self._extract_minified_json(self._combine_text(resp)) + "]"

    # ---------- Internals ----------

    def _combine_text(self, resp: anthropic.types.Message) -> str:
        parts: List[str] = []
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
        return "".join(parts).strip()

    def _first_tool_input(self, resp: anthropic.types.Message) -> Optional[Dict[str, Any]]:
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                return getattr(block, "input", None)
        return None

    def _extract_minified_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return "{}"
        raw = text[start : end + 1]
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":"))
        except Exception:
            # Best-effort cleanup if model returned nearly-valid JSON
            compact = "".join(ch for ch in raw if ch not in ["\n", "\r", "\t"])
            return compact.strip() or "{}"


# Example usage
if __name__ == "__main__":
    bot = ClaudeClient()
    print("ASK:", bot.ask("In one sentence, what is entropy in information theory?"))
    print("ASK_WEB:", bot.ask_web("Summarize today's big LLM news and cite sources."))
    print("ASK_JSON:", bot.ask_enforce_json("Return {a:1, b: [2,3]} but valid JSON keys and values."))
    print("ASK_WEB_JSON:", bot.ask_web_enforce_json("Find two fresh AI funding rounds and output as an array of objects."))
