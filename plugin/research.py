"""Turns one Account into an OpportunityBrief grounded in real, current public
signals, via a Claude tool-use loop with two tools:

- web_search (Anthropic server-side tool): primary discovery, no code needed.
- fetch_url (our custom client-side tool, plugin/fetch.py): lets Claude pull
  the full text of one specific URL it already found, for higher-trust
  verification beyond a search snippet (e.g. the company's own newsroom page).
"""
from __future__ import annotations

import json
import os
import re
import time

from .fetch import fetch_and_extract
from .schema import Account, OpportunityBrief, Source

MODEL = os.environ.get("OPPORTUNITY_RADAR_MODEL", "claude-sonnet-4-5")
MAX_TOOL_ROUNDS = 4

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}

_FETCH_TOOL_TEMPLATE = {
    "name": "fetch_url",
    "description": (
        "Fetch and extract the main readable text of ONE specific web page URL you already "
        "have (e.g. a company's own newsroom or press-release page), for verification beyond "
        "a search snippet. {limit} Not for open-ended browsing - use "
        "web_search for discovery, and this only to read a specific page in full."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "A specific http(s) URL"}},
        "required": ["url"],
    },
}

SYSTEM_PROMPT = """You are a GTM research analyst for a Canadian media/advertising sales team.
For the given account, use web search to find REAL, CURRENT public signals relevant to a
media/advertising sales pitch: product launches, campaign or agency reviews/wins, market
expansion, leadership changes, RFPs, sustainability or brand initiatives, earnings commentary.

You have two tools:
- web_search: use this first, for discovery. It returns snippets with citations.
- fetch_url: use this only on a specific URL you already found via web_search, when you want
  to verify or read a claim in full from an authoritative source (e.g. the company's own
  newsroom/press-release page) rather than relying on the snippet alone. {fetch_rule} Don't use
  it for general browsing.

You will also be given SYNTHETIC internal CRM context (deal stage, rep notes, relationship
notes). This internal context is fictional/synthetic — never treat it as a real public fact,
never cite it as a "signal", and never repeat it back as if you discovered it via search. Use
it to shape recommended_action and warm_path, and keep it clearly separated from the real,
web-sourced signal_summary.

Warm path: also use web_search to look for a real route in, such as the named executive or
marketing/brand lead for this account, its agency of record or a recent agency change, a past
partnership or sponsorship with a publisher or media company, or a shared board/industry-event
connection. Only report a web-found route if a source you found supports it, and add that
source to "sources"; never invent or guess people, titles or relationships. Write warm_path as
one short string and label where each part came from, e.g. "CRM: <note>. Web: <route> (see
source)". If there is neither a CRM note nor a supported web finding, set warm_path to null.

Once you are done researching, respond with ONLY a single JSON object (no markdown fences, no
commentary, no further tool calls) matching exactly:
{
  "tier": "A" | "B" | "C",
  "urgency": "High" | "Medium" | "Low",
  "signal_summary": string,
  "why_now": string,
  "recommended_action": string,
  "warm_path": string | null,
  "sources": [{"title": string, "url": string}],
  "confidence": "High" | "Medium" | "Low"
}

Tier guidance: A = large/strategic + strong active signal, B = solid mid-funnel or moderate
signal, C = early/speculative or no strong signal found. If web search returns nothing
substantive, say so honestly, set confidence to "Low", and still return valid JSON.
"""

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _max_fetch() -> int | None:
    """MAX_FETCH env var: max fetch_url page extractions per account. Unset, blank or
    invalid means no cap (limited only by MAX_TOOL_ROUNDS). Read per call so it can change
    without a re-import."""
    raw = os.environ.get("MAX_FETCH", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _system_prompt(max_fetch: int | None) -> str:
    rule = (
        f"Use it at most {max_fetch} time(s) per account."
        if max_fetch is not None
        else "Use it as many times as you need."
    )
    return SYSTEM_PROMPT.replace("{fetch_rule}", rule)


def _fetch_tool(max_fetch: int | None) -> dict:
    limit = (
        f"Use at most {max_fetch} time(s) per account."
        if max_fetch is not None
        else "Use as many times as needed."
    )
    return {**_FETCH_TOOL_TEMPLATE, "description": _FETCH_TOOL_TEMPLATE["description"].replace("{limit}", limit)}


def _account_prompt(account: Account) -> str:
    lines = [
        f"Account: {account.name}",
        f"Industry: {account.industry}",
        f"Synthetic deal stage: {account.deal_stage}",
    ]
    if account.deal_size_cad:
        lines.append(f"Synthetic deal size (CAD): {account.deal_size_cad}")
    if account.last_activity:
        lines.append(f"Synthetic last activity: {account.last_activity}")
    if account.rep_notes:
        lines.append(f"Synthetic rep notes: {account.rep_notes}")
    if account.market_signal_hint:
        lines.append(f"Synthetic hint (not a real fact, verify/replace via search): {account.market_signal_hint}")
    if account.relationship_context:
        lines.append(f"Synthetic relationship context: {account.relationship_context}")
    lines.append(
        "\nSearch the web for real, current signals about this company relevant to a "
        "media/advertising sale, then return the JSON object described in the system prompt."
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:500]!r}")
    return json.loads(match.group(0))


def _run_tool_loop(client, account: Account) -> str:
    """Drives the Claude <-> tool conversation until it stops calling fetch_url,
    then returns the concatenated text of the final response.
    """
    messages = [{"role": "user", "content": _account_prompt(account)}]
    max_fetch = _max_fetch()
    system = _system_prompt(max_fetch)
    tools = [WEB_SEARCH_TOOL, _fetch_tool(max_fetch)]
    fetched = 0

    for _round in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=system,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        fetch_calls = [
            block
            for block in response.content
            if getattr(block, "type", None) == "tool_use" and block.name == "fetch_url"
        ]
        if not fetch_calls:
            return "\n".join(b.text for b in response.content if getattr(b, "type", None) == "text")

        tool_results = []
        for call in fetch_calls:
            url = (call.input or {}).get("url", "")
            if max_fetch is not None and fetched >= max_fetch:
                # Enforced here, not just in the prompt: no page is fetched past the cap.
                extracted = f"[fetch skipped: MAX_FETCH limit of {max_fetch} reached for this account]"
            else:
                fetched += 1
                extracted = fetch_and_extract(url)
            tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": extracted})
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"exceeded {MAX_TOOL_ROUNDS} tool-use rounds without a final answer")


def research_account(account: Account, *, max_retries: int = 2, sleep_s: float = 1.5) -> OpportunityBrief:
    """One account -> one grounded OpportunityBrief, via Claude + web_search + fetch_url."""
    import anthropic  # imported lazily so --mock runs need no SDK/key at all

    client = anthropic.Anthropic()

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            final_text = _run_tool_loop(client, account)
            payload = _extract_json(final_text)

            sources = [Source(**s) for s in payload.get("sources", []) if s.get("url")]

            return OpportunityBrief(
                account=account.name,
                industry=account.industry,
                tier=payload["tier"],
                urgency=payload["urgency"],
                signal_summary=payload["signal_summary"],
                why_now=payload["why_now"],
                recommended_action=payload["recommended_action"],
                warm_path=payload.get("warm_path"),
                sources=sources,
                confidence=payload.get("confidence", "Medium"),
                data_mode="live",
            )
        except Exception as exc:  # noqa: BLE001 - broad on purpose, we retry/report
            last_err = exc
            if attempt < max_retries:
                time.sleep(sleep_s * (attempt + 1))
    raise RuntimeError(f"research_account failed for {account.name!r} after retries") from last_err
