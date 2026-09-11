"""Wire tracer for /gate, /execute, /track, /cancel, /heartbeat, etc.

Monkey-patches the SDK's ``Transport._client.post`` (the httpx
client shared by every wire call) and the auth probe path so the
caller sees the full URL + request body + response body for every
HTTP call. Useful for spotting where the SDK sends a client-
generated id where the backend expects a server-minted one (or
vice versa).

Usage::

    import _wire_tracer
    _wire_tracer.install()

    # ... run the example ...

    _wire_tracer.dump()  # print all captured exchanges

The tracer is intentionally a passive observer — it does NOT alter
the bodies. It logs bodies through ``json.dumps(sort_keys=True)``
so diffs are stable across runs.

WebSocket frames are NOT captured by this tracer (httpx-ws uses
a different code path). For WS payloads see
``_ws_tracer.py``.
"""

from __future__ import annotations

import json
from typing import Any

_ORIGINAL_POST: Any = None
_ORIGINAL_GET: Any = None
_CAPTURE: list[dict[str, Any]] = []
_INSTALLED = False


def install() -> None:
    """Patch every existing ``Transport._client.post`` / ``.get`` instance.

    The SDK creates ``Transport._client`` lazily inside ``__init__``,
    so the patch must reach into each instance, not the class. We
    also monkey-patch ``Transport.__init__`` so a later runtime
    (init_or_die runs AFTER install()) gets the tracer automatically.

    Safe to call multiple times — second+ calls are no-ops.
    """
    global _ORIGINAL_POST, _ORIGINAL_GET, _INSTALLED
    if _INSTALLED:
        return

    from nullrun.transport import Transport

    # Per-instance original methods — captured BEFORE wrapping so the
    # tracer can call back into the real httpx client without recursion.
    _originals: dict[int, tuple[Any, Any]] = {}

    def _traced_post(client_self, url, **kwargs):  # noqa: ANN001
        body = kwargs.get("content") or kwargs.get("json") or kwargs.get("data")
        decoded_body: Any
        if isinstance(body, (bytes, bytearray)):
            try:
                decoded_body = json.loads(body.decode("utf-8"))
            except Exception:
                decoded_body = body.decode("utf-8", errors="replace")
        else:
            decoded_body = body
        orig_post, _ = _originals[id(client_self)]
        # ``orig_post`` is a bound method — call with (url, **kwargs).
        response = orig_post(url, **kwargs)
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text
        _CAPTURE.append(
            {
                "method": "POST",
                "url": url,
                "request": decoded_body,
                "response_status": response.status_code,
                "response": response_body,
            }
        )
        return response

    def _traced_get(client_self, url, **kwargs):  # noqa: ANN001
        _, orig_get = _originals[id(client_self)]
        response = orig_get(url, **kwargs)
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text
        _CAPTURE.append(
            {
                "method": "GET",
                "url": url,
                "response_status": response.status_code,
                "response": response_body,
            }
        )
        return response

    def _wrap(client: Any) -> None:
        """Replace client.post / client.get with tracer wrappers."""
        if id(client) in _originals:
            return  # already wrapped
        # Capture the REAL bound methods BEFORE we overwrite them on
        # the instance. These are already bound to ``client`` (not
        # ``(self, url, **kwargs)``), so the wrapper calls them with
        # ``(url, **kwargs)`` only.
        orig_post = client.post
        orig_get = client.get
        _originals[id(client)] = (orig_post, orig_get)

        def post(self, url, **kwargs):  # noqa: ANN001
            return _traced_post(self, url, **kwargs)

        def get(self, url, **kwargs):  # noqa: ANN001
            return _traced_get(self, url, **kwargs)

        client.post = post.__get__(client, type(client))
        client.get = get.__get__(client, type(client))

    # Patch Transport.__init__ so every Transport created AFTER install()
    # gets its _client wrapped automatically.
    _real_transport_init = Transport.__init__

    def _patched_init(self, *args, **kwargs):  # noqa: ANN001
        _real_transport_init(self, *args, **kwargs)
        if hasattr(self, "_client") and self._client is not None:
            _wrap(self._client)

    Transport.__init__ = _patched_init  # type: ignore[assignment]

    # Patch any Transport already created (e.g. via a prior init_or_die).
    import gc

    for obj in gc.get_objects():
        try:
            if isinstance(obj, Transport) and hasattr(obj, "_client"):
                _wrap(obj._client)
        except Exception:
            pass

    _ORIGINAL_POST = None
    _ORIGINAL_GET = None
    _INSTALLED = True


def dump() -> list[dict[str, Any]]:
    """Print every captured exchange + return the captured list.

    Bodies are pretty-printed with stable key ordering so the
    reader can spot field-name mismatches between request and
    response at a glance (server-minted vs client-minted,
    required vs optional, etc.).
    """
    print(f"=== captured {_CAPTURE.__len__()} wire exchanges ===")
    for i, entry in enumerate(_CAPTURE, 1):
        print(
            f"\n[{i:03d}] {entry['method']} {entry['url']} "
            f"-> {entry['response_status']}"
        )
        if "request" in entry:
            print(
                "  request:",
                json.dumps(entry["request"], indent=2, sort_keys=True, default=str),
            )
        print(
            "  response:",
            json.dumps(entry["response"], indent=2, sort_keys=True, default=str),
        )
    return list(_CAPTURE)


def captured() -> list[dict[str, Any]]:
    """Return the captured exchanges without printing."""
    return list(_CAPTURE)


def reset() -> None:
    """Clear the captured buffer. Useful between sub-tests."""
    _CAPTURE.clear()
