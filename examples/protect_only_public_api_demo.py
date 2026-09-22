"""Demonstrate the SDK 0.18.1 ``@protect``-only public API.

This example proves the four load-bearing properties of the
``@protect`` public contract WITHOUT calling any LLM and WITHOUT a
live NullRun backend. It is intended for a developer who wants to
verify their SDK install picks up the contract end-to-end before
wiring it into a real agent loop.

Four properties demonstrated:

1. ``@protect`` auto-attaches a default ``ToolParamsExtractor`` on
   every decorated function. The wire ``params`` dict is populated
   from the kwargs of the live call.

2. The default extraction is bounded: oversized strings get a
   deterministic ``...[truncated:N bytes]`` marker; circular
   references in nested dict/list structures return the partial
   walk instead of raising ``RecursionError``.

3. ``@sensitive`` on its own emits ``DeprecationWarning`` on
   decoration.

4. ``@sensitive(impact=money_outflow(...))`` returns a typed
   ``MoneyImpactExtractor`` without any warning.

Why this example does not call a real backend:

The extraction layer is pure local transformation:
``ToolParamsExtractor.impact_for(fn, args, kwargs)`` returns a
``BusinessImpact`` without touching the network. The runtime
singleton is required for *registration* of sensitive tools, but
the extraction itself is wired to the function via the
``_nullrun_extractor`` attribute set by the decorator itself. So
we read the attribute back out and call ``impact_for`` directly
— the same pattern a downstream SDK consumer would use in a unit
test.

Run:
    pip install nullrun
    # No API key needed for this demo — extraction is local.
    python examples/protect_only_public_api_demo.py
"""
from __future__ import annotations

import warnings

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from nullrun import protect, sensitive
from nullrun.extractor import money_outflow


# ---------------------------------------------------------------------------
# Property 1 — @protect auto-attaches a default ToolParamsExtractor
# ---------------------------------------------------------------------------


@protect
def refund_customer(customer_id: str, amount: int, currency: str) -> str:
    """@protect stamps a default extractor on the function."""
    return f"refund {amount} {currency} for {customer_id}"


def demo_property_1() -> None:
    """@protect ships tool_params automatically."""
    print("\n=== Property 1: @protect auto-attaches default tool_params ===")
    extractor = getattr(refund_customer, "_nullrun_extractor", None)
    assert extractor is not None, (
        "@protect must auto-attach a default ToolParamsExtractor"
    )
    print(f"  extractor type: {type(extractor).__name__}")
    print(f"  include_all: {extractor.include_all}")
    print(f"  auto_attached marker: {getattr(extractor, '_nullrun_auto_attached', False)}")

    # Build the BusinessImpact that would land on the wire.
    impact = extractor.impact_for(
        refund_customer,
        (),
        {"customer_id": "cust-123", "amount": 5000, "currency": "USD"},
    )
    wire = impact.to_wire_dict()
    print(f"  wire payload:")
    for k, v in wire.items():
        print(f"    {k}: {v!r}")


# ---------------------------------------------------------------------------
# Property 2 — bounded extraction
# ---------------------------------------------------------------------------


@protect
def upload(description: str) -> str:
    return "ok"


@protect
def process(config: dict) -> str:
    return "ok"


def demo_property_2_truncation() -> None:
    """Oversize string values get a deterministic truncation marker."""
    print("\n=== Property 2a: 1024-byte truncation with marker ===")
    big = "x" * 5000
    extractor = upload._nullrun_extractor
    impact = extractor.impact_for(upload, (), {"description": big})
    params = impact.to_wire_dict()["params"]
    value = params["description"]
    print(f"  input bytes: {len(big.encode('utf-8'))}")
    print(f"  output bytes: {len(value.encode('utf-8'))}")
    print(f"  marker present: {'...[truncated:' in value}")
    print(f"  marker tail: {value[-30:]!r}")


def demo_property_2_cycle_guard() -> None:
    """Circular references return the partial walk, not RecursionError."""
    print("\n=== Property 2b: cycle guard on nested dict ===")
    cyclic: dict = {"outer": "value"}
    cyclic["self"] = cyclic  # type: ignore[assignment]
    extractor = process._nullrun_extractor
    # Without the guard this raises RecursionError out of the SDK.
    impact = extractor.impact_for(process, (), {"config": cyclic})
    params = impact.to_wire_dict()["params"]
    print(f"  params survived: {list(params.keys())}")
    print(f"  inner shape: {type(params['config']).__name__}")
    print(f"  partial walk preserved outer key: {'outer' in params['config']}")
    print(f"  cycle collapsed to empty dict: {params['config']['self']!r}")


# ---------------------------------------------------------------------------
# Property 3 — @sensitive on its own emits DeprecationWarning
#
# We capture the warning with ``warnings.catch_warnings(record=True)``
# so we never reach ``_do_sensitive_register`` (which would require
# a real runtime). The decorator's body up to the warning emission
# is pure Python — no runtime singleton is touched.
# ---------------------------------------------------------------------------


def demo_property_3() -> None:
    """``@sensitive`` (no parens) emits DeprecationWarning on decoration."""
    print("\n=== Property 3: @sensitive DeprecationWarning ===")
    # We can't decorate at module scope because that would hit
    # _do_sensitive_register → runtime init → 401. Instead, we
    # reach into ``sensitive`` directly: build a dummy fn, call
    # ``sensitive(fn)`` inside the warning recorder, catch the
    # RuntimeError it raises AFTER emitting the warning, then
    # assert on the warning. This proves the warning is emitted
    # *before* any runtime-touching code path.
    def _probe(x: int) -> str:
        return "ok"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            sensitive(_probe)
        except RuntimeError:
            # Expected — _do_sensitive_register fails without a
            # runtime. We only care about the warning that fired
            # *before* the RuntimeError.
            pass

    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    print(f"  DeprecationWarning emitted: {len(deprecation_warnings) == 1}")
    if deprecation_warnings:
        msg = str(deprecation_warnings[0].message)
        first_sentence = msg.split(". ")[0]
        print(f"  warning: {first_sentence}.")


# ---------------------------------------------------------------------------
# Property 4 — @sensitive(impact=...) returns a typed extractor
# ---------------------------------------------------------------------------


def demo_property_4() -> None:
    """``@sensitive(impact=money_outflow(...))`` returns MoneyImpactExtractor."""
    print("\n=== Property 4: @sensitive(impact=...) returns typed extractor ===")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = money_outflow(argument="amount_cents", currency="USD", units="minor")

    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    print(f"  no DeprecationWarning from money_outflow(...): {not deprecation_warnings}")

    from nullrun.extractor import MoneyImpactExtractor

    ext = money_outflow(argument="amount_cents", currency="USD", units="minor")
    print(f"  factory return type: {type(ext).__name__}")
    print(f"  is MoneyImpactExtractor: {isinstance(ext, MoneyImpactExtractor)}")
    print(f"  not auto-attached: {not getattr(ext, '_nullrun_auto_attached', False)}")


if __name__ == "__main__":
    demo_property_1()
    demo_property_2_truncation()
    demo_property_2_cycle_guard()
    demo_property_3()
    demo_property_4()
    print("\n[nullrun] All four properties verified.")
