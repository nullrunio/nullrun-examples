"""
LangGraph + OpenAI + a real MCP (Model Context Protocol) server.

Walk-through of v3.31 (Разрыв 3):

  1. The MCP server is defined in this file as a Python object — no
     external process, no stdio subprocess. We use the
     ``mcp.server`` / ``mcp.types`` machinery from the official
     ``modelcontextprotocol/python-sdk`` package (whose absence
     is the only external dep — install with
     ``pip install "nullrun[langgraph,mcp]"``).
  2. The MCP server exposes THREE tools that mix the spec's
     ``readOnlyHint`` / ``destructiveHint`` / ``openWorldHint``
     annotations (MiragE-MCP-spec 2025-06-18 §tools/list):
        * ``search_issues(query)``         — read-only.
        * ``create_issue(title, body, ...)`` — destructive + open-world
          (creates an external-side-effect record).
        * ``close_issue(issue_id, reason)`` — destructive, **not**
          open-world (close-as-not-planned is a state-change in
          the local store, no external side-effect).
     The docstring's annotation set mirrors the wire enum the
     SDK adapter will stamp on every /check.
  3. The agent's loop forwards every MCP tool call to the gate
     via ``@nullrun.protect`` + ``MCPAdapter`` (Разрыв 3 SDK-side).
     The adapter stamps ``tool_class="mcp"`` + the cached
     ``mcp_annotations`` onto the contextvar path so the gate
     sees the canonical class + per-call hint.
  4. Two policy behaviors are demonstrated end-to-end:
        * Strict setting — every MCP call goes through the gate
          with the operator's ``mcp://github/*`` tool_pattern
          matching real MCP tools (and the umbrella blocking
          destructive tools when the destructive policy is
          set).
        * Bypass demonstration — the read-only tool
          (``search_issues``) is allowed by default because the
          SDK forwards ``readOnlyHint=true`` and the operator's
          policy has ``mcp_readonly_policy=allow`` (or absent).
          Switch the policy to ``mcp_readonly_policy=block`` and
          the same call is denied.

Run:

    pip install "nullrun[langgraph,mcp]" langgraph langchain-openai \
        modelcontextprotocol
    export NULLRUN_API_KEY=nr_live_...
    export NULLRUN_API_URL=https://api.nullrun.io    # optional
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_openai_mcp_demo.py

Companion policies to set on the dashboard before running
(pick ONE — the script prints which one is active):

    A. "Auto-block destructive MCP / auto-allow read-only MCP"
       (recommended production posture)
           /control-center/policies  ->  New policy
           policy_type: tool_block
           scope:       workflow = "langgraph-mcp-demo"
           (any policy without these fields on this workflow
           counts as "umbrella = unset" — falls through to
           tool_patterns only.)
           tool_patterns: []      # we don't pin specific tools
           mcp_destructive_policy: block
           mcp_readonly_policy:    allow
       Effect:
           * search_issues  -> allow (read-only + policy=allow)
           * create_issue   -> 403 MCP_DESTRUCTIVE_BLOCKED
           * close_issue    -> 403 MCP_DESTRUCTIVE_BLOCKED

    B. "Require approval for destructive MCP" (stricter)
           mcp_destructive_policy: approval
           mcp_readonly_policy:    allow
       Effect:
           * search_issues  -> allow
           * create_issue   -> 402 require_approval (operator
                                clicks Approve on the Approvals
                                page in the dashboard)
           * close_issue    -> 402 require_approval

    C. "Block everything (legacy-style wildcard)" — write
       ``tool_patterns: ["mcp://*"]`` with NO umbrella fields.
       Then ``mcp_readonly_policy`` defaults to None and the
       gate ONLY checks ``tool_patterns``, so
       ``search_issues`` is also blocked. This is how
       pre-Разрыв-3 operators would write the policy; it still
       works today.

After running this script, the dashboard at
``/control-center/mcp-servers`` will show:

    server_name:     github-mock
    drift_status:    ok                  # the destructive-verb
                                         # heuristic (delete|drop|
                                         # remove|force|refund|
                                         # destroy|kill) does NOT
                                         # match any of our 3 tool
                                         # names — create / close /
                                         # search are all "domain
                                         # verbs" rather than the
                                         # ad-hoc destructive list.
                                         # A name like delete_* or
                                         # drop_* WOULD flip this
                                         # to unannounced.
    observed_tools:  [search_issues, create_issue, close_issue]
"""

from __future__ import annotations

from _env import load_env

load_env()  # noqa: F401  — populates os.environ from examples/.env

import asyncio
import json
import os
import sys

# Lazily import the official MCP Python SDK only when the demo
# actually needs it (the in-process mock client we build by hand
# below does not transitively need it for the happy path — but
# ``build_mcp_server()`` does, and keeping the import inside that
# function means ``pip install modelcontextprotocol`` is OPTIONAL
# for running this example). See the trailing docstring for what
# changes once the SDK is installed.
def _import_mcp_sdk():
    """Local import — defers the MCP SDK as an optional dep."""
    from mcp.server import Server  # noqa: F401  (re-exported)
    from mcp.server.stdio import stdio_server  # noqa: F401
    from mcp.types import Tool, ToolAnnotations  # noqa: F401

    return Server, stdio_server, Tool, ToolAnnotations


MCP_SERVER_NAME = "github-mock"


async def mcp_dispatch(name: str, arguments: dict) -> list:
    """The MCP server's tool dispatcher. One branch per tool."""

    if name == "search_issues":
        # Read-only: the spec annotation readOnlyHint=True tells
        # the SDK to stamp {"read_only": true} on every call.
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "issues": [
                            {
                                "number": 1,
                                "title": f"hit for {arguments.get('query', '?')!r}",
                                "state": "open",
                            }
                        ]
                    }
                ),
            }
        ]
    if name == "create_issue":
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "ok": True,
                        "created": {
                            "number": 42,
                            "title": arguments.get("title"),
                            "body": arguments.get("body"),
                            "labels": arguments.get("labels", []),
                        },
                    }
                ),
            }
        ]
    if name == "close_issue":
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "ok": True,
                        "closed": {
                            "number": arguments.get("issue_id"),
                            "reason": arguments.get("reason"),
                        },
                    }
                ),
            }
        ]
    raise ValueError(f"unknown mcp tool {name!r}")


def build_mcp_server() -> Server:
    """Construct the in-process MCP server with all three tools
    plus their MCP-spec annotations."""

    Server, _stdio_server, Tool, ToolAnnotations = _import_mcp_sdk()

    server = Server(MCP_SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        # Annotations mirror the upstream MCP convention — read
        # the spec's `tools/list` schema example for context.
        return [
            Tool(
                name="search_issues",
                description=(
                    "Search GitHub-style issues for a query string. "
                    "Read-only — never mutates external state."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
                annotations=ToolAnnotations(readOnlyHint=True),
            ),
            Tool(
                name="create_issue",
                description=(
                    "Create a new GitHub-style issue. Opens an "
                    "external-side-effect record. Sometimes "
                    "triggers notifications."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "body"],
                },
                # Mix of destructive + open-world — explicit
                # annotations so the SDK can stamp them on
                # every call to /check.
                annotations=ToolAnnotations(
                    destructiveHint=True,
                    openWorldHint=True,
                ),
            ),
            Tool(
                name="close_issue",
                description=(
                    "Close an existing issue as 'not planned'. "
                    "Destructive — cannot be undone without a "
                    "state-change RPC downstream."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["issue_id"],
                },
                annotations=ToolAnnotations(
                    destructiveHint=True,
                ),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        # The official MCP Python SDK validates inputs against the
        # inputSchema we set on ``list_tools``; in practice the
        # dispatcher only sees valid calls. We don't double-validate
        # here — that's the server-side contract.
        return await mcp_dispatch(name, arguments)

    return server


async def run_mcp_server_stdio() -> None:
    """Run the MCP server on stdio until cancelled.

    This is the ``stdio`` transport — exactly what an ``mcp://*``
    stdio subprocess would expose to a remote agent. We use it as
    a model so the example is self-contained (no need for a
    separate MCP server process); the SDK-side MCPAdapter code path
    is identical whether the transport is stdio or Streamable
    HTTP.
    """

    Server, stdio_server, _Tool, _ToolAnn = _import_mcp_sdk()
    server = build_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. The agent.
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from nullrun import shutdown
from nullrun.decorators import protect
from nullrun.toolbox.mcp import MCPAdapter

# ``NULLRUN_API_KEY`` is verified at the first gate call, not at
# module load — an unset key surfaces as a four-line developer
# report inside ``nullrun.handle()`` rather than at startup.
if not os.environ.get("OPENAI_API_KEY"):
    sys.stderr.write(
        "OPENAI_API_KEY is not set — export it before running this"
        " example.\n"
    )

# We construct the LLM here (no network call yet — `invoke` is
# where the network actually happens) so any import-time LLM
# configuration errors surface before main() runs.
llm = ChatOpenAI(model="gpt-4o-mini")


@dataclass
class MCPDemoState:
    """Tiny state object that survives a single agent invocation.

    The demo's manual loop below doesn't need the state-machine
    machinery of LangGraph for the MCP-specific bits — we keep
    the conversation log on a single dict and use ChatOpenAI's
    ``bind_tools`` to drive function-calling, then dispatch to
    the MCPAdapter. This is a single-shot demo, not a
    graph-based one.
    """

    messages: list[dict]


# 2a. Set up the MCP adapter that the gate sees.
#
# We can't talk to the in-process MCP server over stdio from within
# the same Python process without a subprocess dance. Instead we
# use the official Python MCP SDK's in-memory transport — when the
# server is started in a background ``asyncio`` task on the same
# event loop, the client side uses an in-memory pipe pair. To keep
# this example portable, we wrap the MCP server's tool list into
def build_mcp_client():
    """Hand-rolled in-memory MCP client — no asyncio dance required.

    The MCPAdapter's contract on ``mcp_client`` is intentionally
    thin — any object exposing ``list_tools()`` and
    ``call_tool(name, args, **kw)`` works. We pre-build a static
    inventory matching the server's ``list_tools`` decorator
    output above so the demo doesn't need to spin up the server
    on a separate thread or stdin pipe.

    Uses the same lazy import as ``build_mcp_server`` — when
    the official ``modelcontextprotocol`` SDK isn't installed,
    the demo prints a clear fallback message instead of
    crashing on import.
    """

    try:
        _, _, Tool, ToolAnnotations = _import_mcp_sdk()
    except ImportError:
        # The demo won't actually run without the MCP SDK on this
        # branch either — the agent's MCPAdapter requires real
        # Tool objects. Fail loudly so the operator installs the
        # missing dep.
        sys.stderr.write(
            "[demo] FATAL: the official MCP Python SDK isn't "
            "installed. Run `pip install modelcontextprotocol` to "
            "use this example. The SDK is the source of `Tool` /\n"
            "`ToolAnnotations` we use to seed the in-memory MCP\n"
            "client and (optionally) to start a stdio MCP server.\n"
        )
        raise

    inventory = [
        Tool(
            name="search_issues",
            description="Search GitHub-style issues for a query string.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
        Tool(
            name="create_issue",
            description="Create a new GitHub-style issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "body"],
            },
            annotations=ToolAnnotations(
                destructiveHint=True,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="close_issue",
            description="Close an existing issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["issue_id"],
            },
            annotations=ToolAnnotations(destructiveHint=True),
        ),
    ]

    class _InMemoryMCPClient:
        """In-memory MCP client — MCPAdapter-friendly surface."""

        def __init__(self, tools):
            self._tools = {t.name: t for t in tools}
            self.calls: list[tuple[str, dict]] = []

        def list_tools(self):
            return list(self._tools.values())

        def call_tool(self, name, arguments, **kwargs):
            self.calls.append((name, arguments))
            # The actual MCP server dispatcher is async. The
            # MCPAdapter's contract is synchronous
            # (call_tool returns the value, not a coroutine),
            # so we bridge via ``asyncio.run`` — which creates
            # a fresh event loop per call, runs the coroutine to
            # completion, and tears the loop down. The dedicated
            # subprocess / stdio / Streamable HTTP transports
            # handle the bridge for real; this in-process path is
            # only used by the demo (one call per tool per demo
            # run, so the per-call loop cost is in the noise).
            return asyncio.run(mcp_dispatch(name, arguments))

    return _InMemoryMCPClient(inventory)


# 2b. Construct the adapter — note this is the v3.31 SDK helper.
adapter = MCPAdapter(server_name=MCP_SERVER_NAME, mcp_client=build_mcp_client())
print(
    f"[demo] MCPAdapter ready — "
    f"{len(adapter.list_cached_tools())} tools cached: "
    f"{adapter.list_cached_tools()}"
)


# 2c. The @protect boundary. Each MCP tool call goes through
# this decorator so the gate sees `tool_class="mcp"` plus the
# cached annotations.
#
# IMPORTANT: this function NEVER runs the MCP server's body
# locally — it delegates to the adapter, which (a) stamps
# contextvars, then (b) calls the underlying client (our in-memory
# mock here).
@protect
def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Run a MCP tool call through the gate + adapter.

    Returns a parsed JSON dict so the agent can reason about it.
    The adapter has already stamped tool_class + annotations on
    the runtime's contextvars by the time we reach the underlying
    client.call_tool() call.
    """

    raw = adapter.call_tool(tool_name, arguments)
    # raw is a list of content blocks from MCP Python SDK;
    # for our mock it returns a list with a single ``{"type":
    # "text", "text": "<json>"}`` block per the dispatcher.
    text = raw[0]["text"] if isinstance(raw, list) else raw
    return json.loads(text) if isinstance(text, str) else raw


# 2d. OpenAI tool schema — mirrors the MCP server's tool list
# verbatim so the LLM can pick the right tool.
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "call_mcp_tool",
            "description": (
                "Invoke an MCP server tool. Use 'tool_name' to "
                "pick the server tool, and 'arguments' for its "
                "kwargs. Returns the parsed JSON result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "enum": [
                            "search_issues",
                            "create_issue",
                            "close_issue",
                        ],
                    },
                    "arguments": {
                        "type": "object",
                        "description": (
                            "Per-tool kwargs as documented by the "
                            "MCP server. Empty {} when the tool "
                            "takes no args."
                        ),
                    },
                },
                "required": ["tool_name"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 3. The driver.
# ─────────────────────────────────────────────────────────────────────────────

DEMO_PROMPTS = [
    "Search the github-mock MCP for issues mentioning 'login bug'. "
    "Use tool_name='search_issues'.",
    "Create a high-priority bug titled 'login fails on Safari' with "
    "body 'reproduce: clear cookies, hit /login, watch 500' and "
    "labels ['bug', 'safari']. Use tool_name='create_issue'.",
    "Close issue #42 as 'fixed in 0.14.4'. Use "
    "tool_name='close_issue'.",
]


def chat_with_tool_calling(messages: list[dict]) -> dict | None:
    """Run one LLM turn + dispatch any tool calls.

    Returns the latest message dict, or None on a transport
    error we want to swallow so the demo can continue.
    """

    bound = llm.bind_tools(OPENAI_TOOLS)
    response = bound.invoke(messages)
    messages.append(
        response.model_dump(exclude_none=True, exclude_unset=False)
    )
    return response


def dispatch_tool_call(message: dict, state: MCPDemoState) -> None:
    """If the latest assistant message has tool_calls, run them
    through the gate via @protect. Append the tool result to
    the conversation log."""

    for tc in message.get("tool_calls") or []:
        # FIX 2026-08-06 (DEF-SDKWRAP-LANGRAPH-MCP-DISPATCH-BLOCK-01,
        # Session 6 TC-SDKWRAP-14): LangChain's ChatOpenAI returns
        # tool_calls in PARSED format (``{name, args, id, type}`` at
        # the top level) — not the OpenAI raw wire format
        # (``{function: {name, arguments}}``) the previous code read.
        # Pre-fix ``fn = tc.get("function") or {}`` always returned
        # ``{}`` for LangChain-parsed tool_calls, ``name = fn.get(
        # "name")`` was None, and every tool call hit the
        # ``if not name: continue`` skip branch — so the MCP wire
        # payload (``tool_class="mcp"``, ``mcp://`` namespace,
        # ``mcp_annotations``) was never verified end-to-end (3/3
        # demo MCP calls silently dropped before @protect fired).
        #
        # Resolution order: LangChain-parsed first (the actual
        # format ChatOpenAI returns), OpenAI-raw fallback for any
        # future stack that re-surfaces the raw wire dict. Both
        # shapes are documented in the LangChain/OpenAI SDKs and a
        # robust dispatcher should handle either. ``args`` in the
        # LangChain format is already a dict (not a JSON string),
        # so no ``json.loads`` round-trip is needed there — only the
        # OpenAI-raw branch parses.
        name = tc.get("name")
        args = tc.get("args")
        if name is None:
            # OpenAI raw format fallback — ``tc.function.{name,
            # arguments}``.
            fn = tc.get("function") or {}
            name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
        # OpenAI occasionally returns malformed tool_call entries
        # (e.g. partial streaming) where the function name is
        # missing. Skip them rather than crashing the demo — a
        # real agent would log a structured error and re-plan.
        if not name:
            print(
                f"[demo] !! tool_call missing function name: {tc!r}"
            )
            continue
        if not isinstance(args, dict):
            args = {}
        print(f"[demo] -> gate: tool={name!r} args={args}")
        result = call_mcp_tool(tool_name=name, arguments=args)
        print(f"[demo] <- gate: {result!r}")
        state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "name": name,
                "content": json.dumps(result),
            }
        )


def main() -> int:
    # The first @protect call inside the demo loop creates the
    # runtime. If NULLRUN_API_KEY is missing, the first gate call
    # raises ``NullRunConfigError`` which the demo's
    # ``except Exception`` arm surfaces with the four-line developer
    # report. We intentionally do not pre-init here so a missing key
    # doesn't kill the process before the user can read the
    # OPENAI_API_KEY warning above.

    state = MCPDemoState(messages=[])
    for prompt in DEMO_PROMPTS:
        state.messages.append({"role": "user", "content": prompt})
        try:
            response = chat_with_tool_calling(state.messages)
            if response is None:
                continue
            dispatch_tool_call(response.model_dump(), state)
            # One extra model turn to acknowledge the tool result.
            ack = chat_with_tool_calling(state.messages)
            if ack is None:
                continue
        except Exception as exc:  # noqa: BLE001
            # The gate returns ``WorkflowKilledInterrupt`` (or
            # similar) on 403/402 — the demo's job is to surface
            # those clearly without aborting the whole script.
            # A real agent would re-plan; for a single-shot
            # walk-through we just print + continue.
            print(f"[demo] !! tool call blocked: {type(exc).__name__}: {exc}")
            continue
    print("\n[demo] finished — full conversation log:\n")
    for m in state.messages:
        if m.get("content"):
            print(f"  {m['role']:>7}: {m['content']!r}")
        if m.get("tool_calls"):
            for tc in m["tool_calls"]:
                print(f"  {m['role']:>7} calls: {tc}")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        # Always shut down the runtime so the SDK's background
        # flush + websocket teardown is clean.
        try:
            shutdown()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
