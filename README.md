# Seller Support Inbox Agent

[![eval](https://github.com/becominggiant/seller-support-agent/actions/workflows/eval.yml/badge.svg)](https://github.com/becominggiant/seller-support-agent/actions/workflows/eval.yml)

A **LangGraph** multi-step agent that triages buyer messages for a Whatnot-style resale shop:
**classify → call order/inventory tools → draft a reply → confidence gate**. Only low-risk,
high-confidence replies are marked `auto_send`; refunds, spam, unclear messages, failed lookups and
anything that looks like prompt injection are **escalated to a human**.

Runs fully offline (no API key) in CI, with golden-case evals and a regression gate.

## What it demonstrates
- **Tool-calling agent graph** (LangGraph `StateGraph`, 4 nodes, conditional edge)
- **Confidence routing + human-in-the-loop**: code, not the model, decides what ships
- **Prompt-injection defenses**: deterministic detector before any LLM call; flagged messages skip tool access entirely
- **Evals as CI**: category accuracy, decision accuracy, injection catch rate, unsafe auto-sends, latency — fails on regression vs. `reports/baseline.json`
- **Two backends**: rule-based `fixture` (deterministic) and optional `openai` (structured outputs + tool calling)

## Architecture

```mermaid
flowchart LR
    M[Inbound message] --> C[classify<br/>category + confidence<br/>+ injection detector]
    C -->|clean & not spam| T[tools<br/>lookup_order / check_inventory / list_inventory]
    C -->|injection flags or spam| D
    T --> D[draft<br/>reply from tool results]
    D --> G{gate}
    G -->|shipping or product_question<br/>AND conf >= 0.85<br/>AND no flags<br/>AND all lookups ok| A[auto_send]
    G -->|otherwise| H[escalate to human]
```

| File | Role |
|---|---|
| `support/graph.py` | LangGraph graph, nodes, gate logic |
| `support/state.py` | `SupportState` (message, category, confidence, injection_flags, tool_results, draft, decision, reason, traces) |
| `support/injection.py` | Regex detector: instruction override, system-prompt leak, role hijack, exfil to non-shop email, bulk data dump, fake authority |
| `support/tools/ops_client.py` | Tools + MCP-*style* registry (JSON schemas). In-process sample data mirroring [whatnot-automation-agent](https://github.com/becominggiant/whatnot-automation-agent); `WHATNOT_OPS_URL` switches inventory reads to that FastAPI service |
| `support/agents/fixture.py` | Keyword/regex classifier, tool planner, templated drafts |
| `support/agents/openai_agent.py` | Optional: JSON-schema structured output for classify, native tool calling for plan, LLM draft |
| `support/eval/runner.py` | Golden-case runner, metrics, markdown/JSON reports, regression check |

## Results (real fixture run, 14 cases)

| metric | fixture |
|---|---|
| category accuracy | 1.00 |
| decision accuracy | 1.00 |
| injection catch rate (4 attacks) | 1.00 |
| unsafe auto-sends | 0 |
| latency p50 | ~1 ms |

Full per-case table: [`reports/latest.md`](reports/latest.md). Honest caveats: the case set is small and
I wrote it alongside the rules, so 100% here means "the rules cover the cases", not "generalizes".
The first run actually auto-sent `prod-03` (a compatibility question our data can't answer); I added a
rule that caps confidence for unanswerable attributes. The `openai` backend has **not** been benchmarked —
no numbers are reported for it.

## Design notes / tradeoffs
- **Refunds always escalate.** Money movement is irreversible and a classic injection target ("send the refund to attacker@evil.com"). Rules for money, models for words.
- **Gate is code, not a prompt.** Even with the OpenAI backend the model only proposes category/confidence/tools; it can't vote itself into `auto_send`.
- **Injected messages get no tools.** The conditional edge routes flagged messages straight to draft, so an attacker can't use the agent to read order data.
- **Tool allow-list.** Only registry tools execute; unknown tool names from the model are dropped.
- **Failed lookups escalate** (e.g. unknown `ord-999`) rather than letting the draft guess.
- **Precision over recall on auto-send.** False escalations cost a human minute; false auto-sends cost trust.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m support.run --message "Where is order ord-001?" --agent fixture
python -m support.eval --agent fixture --cases cases/      # exits 1 on regression
pytest -q
# optional
pip install openai && export OPENAI_API_KEY=... && python -m support.run --message "Is sku-1001 in stock?" --agent openai
```

## Deploy & ops
- `Dockerfile` runs the eval by default; swap `CMD` for `support.run` or wrap `run_message()` in a FastAPI route next to the ops API.
- Point at a live ops service with `WHATNOT_OPS_URL=http://localhost:8000` (inventory reads; orders stay on sample data because the upstream API has no GET-by-id order route).
- Every node appends to `traces` (node, ms, decision info) — ready to ship to a tracing backend.
- CI: `.github/workflows/eval.yml` runs pytest + eval vs baseline on push/PR to `main` and uploads `reports/` as an artifact. Update the baseline deliberately with `--write-baseline`.

## Status
| | |
|---|---|
| ✅ Implemented | LangGraph graph, 3 tools, injection detector, fixture backend, OpenAI backend (code path), golden cases, eval runner, CI regression gate |
| 🔜 Planned | Gmail / Whatnot DM ingest, Slack approve/edit button for escalations, Langfuse traces, real MCP server for the tools, larger + held-out case set, OpenAI benchmark |

This is **not** connected to a real inbox and does not send email. The tool registry is MCP-*style* (name + JSON schema), not an MCP server.

## Related
- [whatnot-automation-agent](https://github.com/becominggiant/whatnot-automation-agent) — the ops API these tools mirror
- [agent-eval-harness](https://github.com/becominggiant/agent-eval-harness) — the eval/CI gating pattern
- [prompt-engineering-portfolio](https://github.com/becominggiant/prompt-engineering-portfolio) — source of the attack ideas

Built by Chanel Chatham (Minneapolis) · MIT
