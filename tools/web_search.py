from __future__ import annotations

from typing import Any

from tools import Tool, ToolContext


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    """Execute a web search using DuckDuckGo's HTML-based search (no API key needed)."""
    query = args.get("query")
    if not query:
        return 'Error: missing required argument "query".'

    max_results = min(int(args.get("maxResults", 5)), 20)

    try:
        import urllib.request
        import urllib.parse
        import re

        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parse result links from DuckDuckGo HTML
        # Look for <a rel="nofollow" class="result__a" href="...">
        results: list[dict[str, str]] = []
        # Match result blocks
        for match in re.finditer(
            r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            url_raw = match.group(1).strip()
            title_raw = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            results.append({"title": title_raw, "url": url_raw})
            if len(results) >= max_results:
                break

        if not results:
            return f'No results found for "{query}".'

        lines = [f'Web search results for: "{query}"', ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            lines.append("")

        return "\n".join(lines).strip()

    except ImportError:
        return 'Error: urllib is not available (standard library issue).'
    except Exception as exc:
        return f"Error searching the web: {exc}"


web_search_tool = Tool(
    name="web_search",
    description=(
        "Search the web for information, documentation, code examples, or "
        "troubleshooting. Uses DuckDuckGo search (no API key needed). "
        "Returns a list of relevant results with titles and URLs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "maxResults": {
                "type": "number",
                "description": "Maximum number of results to return (default: 5, max: 20)",
            },
        },
        "required": ["query"],
    },
    execute=execute,
    read_only=True,
)
