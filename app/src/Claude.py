# pip install anthropic requests
import os
import json
from typing import List, Dict, Any, Optional
import requests
import urllib.parse
import anthropic
from dotenv import load_dotenv

load_dotenv()


class ClaudeClient:
    """
    Minimal Claude client.
    - Reads ANTHROPIC_API_KEY from env by default.
    - ask(prompt) -> str
    - ask_with_web(prompt) -> str  # enables simple web search + fetch via tools
    """

    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "claude-haiku-4-5",
            max_tokens: int = 1024,
            temperature: float = 0.0,
            request_timeout: int = 30,
            web_fetch_max_chars: int = 12000,
            tool_steps: int = 4,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Set ANTHROPIC_API_KEY in your environment or pass api_key.")
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=request_timeout)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.web_fetch_max_chars = web_fetch_max_chars
        self.tool_steps = tool_steps

    # ---------- Public API ----------

    def ask(self, prompt: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
        return self._combine_text(resp)

    def ask_with_web(self, prompt: str) -> str:
        tools = [
            {
                "name": "web_search",
                "description": "Search the public web and return up to N relevant results.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "web_get",
                "description": "Fetch a URL and return extracted readable text. Truncated to max_chars.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"},
                        "max_chars": {"type": "integer", "default": self.web_fetch_max_chars},
                    },
                    "required": ["url"],
                },
            },
        ]

        system = (
            "You can call tools to search and fetch web pages. "
            "Prefer precise queries. Cite URLs in your answer."
        )

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]

        for _ in range(self.tool_steps):
            resp = self.client.messages.create(
                model=self.model,
                system=system,
                tools=tools,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=messages,
            )

            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                return self._combine_text(resp)

            # Append assistant message that requested tools
            messages.append({"role": "assistant", "content": resp.content})

            # Execute tools
            tool_results_blocks: List[Dict[str, Any]] = []
            for tu in tool_uses:
                name = getattr(tu, "name", "")
                inp = getattr(tu, "input", {}) or {}

                try:
                    if name == "web_search":
                        q = str(inp.get("query", "")).strip()
                        lim = int(inp.get("limit", 5))
                        results = self._tool_web_search(q, lim)
                        content = json.dumps({"results": results}, ensure_ascii=False)
                        tool_results_blocks.append(
                            {"type": "tool_result", "tool_use_id": tu.id, "content": content}
                        )

                    elif name == "web_get":
                        url = str(inp.get("url"))
                        max_chars = int(inp.get("max_chars", self.web_fetch_max_chars))
                        text = self._tool_web_get(url, max_chars=max_chars)
                        payload = {"url": url, "text": text}
                        tool_results_blocks.append(
                            {"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(payload)}
                        )

                    else:
                        tool_results_blocks.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "is_error": True,
                                "content": f'Unknown tool "{name}".',
                            }
                        )
                except Exception as e:
                    tool_results_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "is_error": True,
                            "content": f"Tool error: {type(e).__name__}: {e}",
                        }
                    )

            messages.append({"role": "user", "content": tool_results_blocks})

        # Fallback if tool loop did not converge
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=messages,
        )
        return self._combine_text(resp)

    # ---------- Internals ----------

    def _combine_text(self, resp: anthropic.types.Message) -> str:
        parts: List[str] = []
        for b in resp.content:
            if getattr(b, "type", None) == "text":
                parts.append(getattr(b, "text", ""))
        return "".join(parts).strip()

    def _tool_web_search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Uses DuckDuckGo Instant Answer JSON. No API key.
        Returns a list of {'title','url'}.
        """
        if not query:
            return []
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        results: List[Dict[str, str]] = []

        def add(title: str, url: str):
            if not url:
                return
            if not title:
                title = url
            if url not in {x["url"] for x in results}:
                results.append({"title": title, "url": url})

        # Main abstract URL
        add(data.get("Heading") or "", data.get("AbstractURL") or "")

        # Related topics, possibly nested
        def walk(items: List[Dict[str, Any]]):
            for it in items:
                if "FirstURL" in it:
                    add(it.get("Text", ""), it["FirstURL"])
                if "Topics" in it and isinstance(it["Topics"], list):
                    walk(it["Topics"])

        if isinstance(data.get("RelatedTopics"), list):
            walk(data["RelatedTopics"])

        return results[: max(1, min(limit, 8))]

    def _tool_web_get(self, url: str, max_chars: int) -> str:
        """
        Fetch text via Jina Reader proxy for consistent readability.
        """
        if not url:
            return ""
        proxy = self._jina_reader_url(url)
        r = requests.get(proxy, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = r.text.strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
        return text

    @staticmethod
    def _jina_reader_url(url: str) -> str:
        u = url.strip()
        # Normalize to r.jina.ai/http://<host/...>
        if u.startswith("http://"):
            tail = u[len("http://"):]
        elif u.startswith("https://"):
            tail = u[len("https://"):]
        else:
            tail = u
        # Preserve query safely
        return "https://r.jina.ai/http://" + urllib.parse.quote(tail, safe="/:%?&=#")

# Example
if __name__ == "__main__":
    bot = ClaudeClient()
    print(bot.ask("In one sentence, what is entropy in information theory?"))
    print(bot.ask_with_web("Summarize the latest on quantum error correction and cite URLs."))
