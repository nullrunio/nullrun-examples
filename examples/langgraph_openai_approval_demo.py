"""LangGraph + OpenAI: trigger an approval rule 3 times in a row.

The script stands up a small LangGraph agent that exposes ONE
``refund_customer`` tool annotated with a Phase 1 / MVP 1.0
``@sensitive`` extractor. The agent is asked to issue three
refunds in a single run ($100, $50.99, $499 USD). Once the
operator configures an approval rule of the form

    when amount > $50 USD  ->  require approval

on the workflow, every refund call that exceeds the threshold
is supposed to land on the Approvals page as a PENDING row.
The agent waits for the operator to Approve / Deny (via the
WebSocket push) before completing the next leg.

The deliberate structure:

  * The tool is a plain Python function decorated with
    ``@nullrun.sensitive(impact=money_outflow(...))`` and
    ``@nullrun.protect``. ``@protect`` is the gate boundary that
    fires the /check pre-flight on every call; the
    ``money_outflow`` extractor turns the keyword argument into
    a typed ``BusinessImpact`` whose SHA-256 digest is folded
    into the ``action_predicate``-match on the backend.
  * The LangGraph is a single ``agent`` node that:
      - Calls Chat Completions with ``tools=[...]``.
      - On a `tool_calls` response, invokes the matching local
        ``@protect`` function (which routes through the gate).
      - Appends the result to the message list and loops.
      - Eventually stops once the LLM emits a non-tool reply.
  * The `with workflow(...)` block scopes the API key so the
    backend can resolve the operator's approval rules for that
    workflow. The CLI prints the chat history at the end so the
    operator can see the three refunds fire in order.

Run:
    pip install "nullrun[langgraph]" langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_openai_approval_demo.py

Then on the dashboard:

    /control-center/policies/approval-rules
        -> New rule
        -> Workflow: langgraph-approval-demo
        -> Tool patterns: refund_customer
        -> Typed condition: Money amount
        -> When amount exceeds 50.00 USD
        -> Priority: 100
        -> Timeout: 300
        -> Save

The script is then runnable a second time and every refund
above $50 will pop up on the Approvals page one row at a time.
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import json

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

import nullrun
from nullrun import init_or_die, shutdown, workflow
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow
from nullrun.toolbox.langgraph import wrapper

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing

llm = ChatOpenAI(model="gpt-4o-mini")


# ──────────────────────────────────────────────────────────────────────────────
# 1. The tool the agent will call.
#
# The decorator stack is the canonical Phase 1 / MVP 1.0 form:
#
#   @nullrun.sensitive(impact=money_outflow(argument="refund_amount",
#                                            currency="USD",
#                                            units="major"))
#   @nullrun.protect
#
# ``money_outflow`` is the typed-impact extractor. The argument
# name ``refund_amount`` is the keyword the LLM will pass at
# call time; ``units="major"`` means the agent talks in major
# units (e.g. 50.99 means $50.99) and the SDK converts to
# integer minor units (5099 cents) without rounding. The
# backend's predicate evaluator then either matches the rule
# (action_predicate on the workflow) and returns
# ``require_approval``, or returns allow and the body runs.
#
# ``@protect`` is the gate boundary. On every call it fires
# /check with the live tool name and (through the sensitive
# extractor) the live amount. The backend's response is then
# materialized as NullRunBlockedException / runtime halt so
# the agent can recover.
# ──────────────────────────────────────────────────────────────────────────────
@sensitive(impact=money_outflow(
    argument="refund_amount",
    currency="USD",
    units="major",
))
@protect
def refund_customer(refund_amount: float, customer_id: str) -> str:
    """Issue a refund for ``customer_id`` of ``refund_amount`` USD.

    The body runs only after the gate has returned ``allow``.
    Phase 1 / MVP 1.0 guarantees that re-eval after the
    operator approves the matching row fits the same digest
    (the SDK computes the digest from the same arguments the
    LLM passed here), so the operator cannot accidentally
    approve a different tool call than the one that was
    requested.
    """
    # 50.99 -> 5099 cents happens inside the @sensitive
    # extractor; the body just sees the original Decimal.
    print(
        f"  [refund] customer_id={customer_id!r} "
        f"refund_amount={refund_amount} USD -> ok"
    )
    return json.dumps(
        {
            "status": "ok",
            "customer_id": customer_id,
            "refund_amount": refund_amount,
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. OpenAI tool schema.
#
# Must match the local function signature 1:1 so the LLM emits
# the matching keyword arguments. The schema is the standard
# Chat Completions `tools` payload — see
# https://platform.openai.com/docs/guides/function-calling.
# ──────────────────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "refund_customer",
            "description": (
                "Issue a refund to a customer. Use this when the "
                "caller asks for a refund. Pass the amount in "
                "USD and the customer id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "The customer id.",
                    },
                    "refund_amount": {
                        "type": "number",
                        "description": (
                            "Refund amount in USD. Use major "
                            "units, e.g. 50.99 means $50.99."
                        ),
                    },
                },
                "required": ["customer_id", "refund_amount"],
            },
        },
    }
]


# ──────────────────────────────────────────────────────────────────────────────
# 3. The agent node.
#
# State is plain `MessagesState`; the node is a single ``chat``
# step that loops on tool calls until the LLM emits a non-tool
# reply. Tool calls are routed through the protected
# ``refund_customer`` so the gate fires on every call. The
# body only ever runs after the gate returned allow.
# ──────────────────────────────────────────────────────────────────────────────
# LangGraph maps the tool name to a Python function. We just
# support the one tool in this example.
TOOL_FUNCTIONS = {
    "refund_customer": refund_customer,
}


def run_tool_call(tool_call: dict) -> str:
    """Dispatch a single LangGraph tool_call through the gate.

    LangGraph's ``AIMessage.tool_calls`` (returned by
    ``ChatOpenAI.invoke(..., tools=...)`` after the
    LangChain LangGraph adapter) uses a flatter shape than
    the raw OpenAI Chat Completions payload:

        {"name": "refund_customer",
         "args": {"refund_amount": 100.0, "customer_id": "cust-demo"},
         "id": "call_123",
         "type": "tool_call"}

    The body of the local ``refund_customer`` is annotated
    ``@sensitive @protect`` so the gate fires on the way in;
    the ``json.loads`` step is gone because LangGraph
    already parsed the OpenAI JSON arguments into a dict.
    Returns the function's result as a JSON-encoded string
    so the matching LangGraph ``ToolMessage`` carries a
    single-string ``content`` payload.
    """
    fn_name = tool_call["name"]
    args = tool_call["args"]
    fn = TOOL_FUNCTIONS[fn_name]
    # Note: ``@protect`` swallows the gate's block into
    # NullRunBlockedException; the agent's outer
    # ``with nullrun.handle()`` block surfaces it as a clean
    # failure if the operator chose Deny.
    return fn(**args)


def agent(state: MessagesState) -> dict:
    """One step of the agent loop.

    Sends the current message list to Chat Completions with
    ``tools=[...]`` attached. If the response carries
    ``tool_calls`` (an LLM decided to invoke a tool), each
    tool call is executed through the gate-protected local
    function, the result is appended as a ``tool`` message,
    and the loop iterates. If the LLM emits a plain text
    reply, the loop ends.
    """
    messages = state["messages"]
    while True:
        response = llm.invoke(messages, tools=TOOLS)
        if not response.tool_calls:
            # Plain text answer — return it once, then the
            # graph edges chat -> END and the loop exits.
            return {"messages": [response]}

        # Append the LLM's ``assistant`` message first so the
        # tool messages that follow are correctly anchored.
        messages.append(response)

        for tool_call in response.tool_calls:
            # ``run_tool_call`` hits the gate; if the gate
            # returns ``require_approval`` the ``@protect``
            # wrapper blocks via WS push until the operator
            # approves. If Deny, the wrapper raises
            # NullRunBlockedException which propagates through
            # ``nullrun.handle()`` to the CLI.
            result = run_tool_call(tool_call)
            # OpenAI tool messages need the original tool_call
            # id to be threaded back into the conversation.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )
        # Loop again — the next LLM call sees the tool
        # results and either decides to call another tool or
        # to emit a final answer.


graph = StateGraph(MessagesState)
graph.add_node("agent", agent)
graph.add_edge("agent", END)
graph.set_entry_point("agent")
app = wrapper(graph.compile())


# ──────────────────────────────────────────────────────────────────────────────
# 4. Main.
#
# The system prompt explicitly asks the agent to issue three
# refunds in a single run, in order: $100, $50.99, $499. The
# second amount is below the example rule threshold ($50) so it
# is expected to bypass the approval rule; the first and third
# are above and should both be Approve/Deny prompts.
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a customer-support agent. The user is going to "
    "ask you to issue three refunds in a single conversation. "
    "Call the tool `refund_customer` exactly three times, in "
    "order, with the amounts they specify. Use customer_id "
    "\"cust-demo\" for all three. After all three calls "
    "return, write a single short summary line listing the "
    "three refunds in order."
)

USER_PROMPT = (
    "Please issue three refunds in order: $100, then $50.99, "
    "then $499. Use customer_id \"cust-demo\" for all three."
)


if __name__ == "__main__":
    try:
        with nullrun.handle():
            with workflow("langgraph-approval-demo"):
                result = app.invoke(
                    {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": USER_PROMPT},
                        ],
                    },
                )
                # Print the final reply so the operator sees
                # the summary the agent composed after the
                # three calls.
                final = result["messages"][-1]
                if isinstance(final, dict):
                    print("\n[agent] final:", final.get("content", ""))
                else:
                    print("\n[agent] final:", getattr(final, "content", ""))
    finally:
        shutdown()
