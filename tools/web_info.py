"""
Information, Productivity, Weather, Translation, and Math Tools for VAX.
Provides fast online information retrieval and offline calculation.
"""

import ast
import operator
import datetime
import urllib.parse
import logging
from typing import List, Dict, Any, Optional
import httpx

from vax.tools import tool
from vax.safety import RiskLevel

logger = logging.getLogger("VAX.Tools.WebInfo")

# Safe math operators
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_ast_node(node):
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    else:
        raise ValueError(f"Unsupported AST expression: {type(node)}")


@tool(description="Performs an instant web search and returns relevant search summaries and links.", risk_level=RiskLevel.SAFE)
def web_search(query: str, max_results: int = 4) -> str:
    """Searches the web via DuckDuckGo HTML."""
    try:
        from bs4 import BeautifulSoup

        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        data = {"q": query}

        with httpx.Client(timeout=10.0) as client:
            res = client.post(url, data=data, headers=headers)
            if res.status_code != 200:
                return f"Search service returned status {res.status_code}."

            soup = BeautifulSoup(res.text, "html.parser")
            results = []
            for r in soup.select(".result")[:max_results]:
                title_elem = r.select_one(".result__title a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    link = title_elem.get("href", "")
                    results.append(f"• **{title}**\n  {snippet}\n  Link: {link}")

            if not results:
                return f"No search results found for '{query}'."

            return "\n\n".join(results)
    except Exception as e:
        logger.error("Web search error: %s", e)
        return f"Web search failed: {e}"


@tool(description="Gets the current weather report and temperature for a city (e.g. 'Dhaka', 'Kolkata', 'London').", risk_level=RiskLevel.SAFE)
def get_weather(city: str = "") -> str:
    """Retrieves current weather from wttr.in."""
    loc = urllib.parse.quote_plus(city.strip()) if city else ""
    url = f"https://wttr.in/{loc}?format=%l:+%C+%t+(feels+like+%f),+humidity:+%h,+wind:+%w"
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.get(url, headers={"User-Agent": "curl/7.68.0"})
            if res.status_code == 200:
                return res.text.strip()
            return f"Weather service responded with status {res.status_code}."
    except Exception as e:
        return f"Failed to retrieve weather: {e}"


@tool(description="Gets the current date, time, day of the week, and local timezone.", risk_level=RiskLevel.SAFE)
def get_time_date() -> str:
    """Returns formatted current local date and time."""
    now = datetime.datetime.now()
    return now.strftime("Current local time is %I:%M:%S %p on %A, %B %d, %Y.")


@tool(description="Safely computes a mathematical expression (e.g. '25 * 4 + 100', '2 ** 8').", risk_level=RiskLevel.SAFE)
def calculate(expression: str) -> str:
    """Evaluates mathematical expression safely."""
    try:
        # Clean expression
        clean_expr = expression.replace("^", "**").strip()
        parsed = ast.parse(clean_expr, mode="eval")
        result = _eval_ast_node(parsed.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Calculation error: {e}"


@tool(description="Translates text between languages (e.g. English to Bangla 'bn', or Bangla to English 'en').", risk_level=RiskLevel.SAFE)
def translate_text(text: str, target_lang: str = "bn", source_lang: str = "auto") -> str:
    """Translates text via Google Translator."""
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        translated = translator.translate(text)
        return translated
    except Exception as e:
        return f"Translation error: {e}"
