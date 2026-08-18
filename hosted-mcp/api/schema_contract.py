"""The schema-opacity rule, shared by the test suite and the live verifier.

One source of truth on purpose: the local gate (test_packaging.py) and the
post-deploy live check (scripts/verify_live_contract.py) import this same
function, so the rule cannot drift between what CI enforces and what
production is measured against. That split is exactly how the 2026-08-17
defect survived locally-green: the local schema generator rendered a
TypedDict fully while the hosted runtime degraded it to a bare object.
"""

from __future__ import annotations


def opaque_input_nodes(schema: object, path: str = "$") -> list[str]:
    """Return the paths of every input-schema node a caller cannot fill in.

    A node is opaque when it admits arbitrary keys while naming none:
    ``type: object`` with no ``properties`` and ``additionalProperties`` not
    pinned to ``false``. That is exactly what ``dict[str, Any]`` publishes,
    and it is how nymrel_golf_bag_gap shipped uncallable: the upstream
    demanded ``name`` + ``carry_distance_yards`` and the schema showed
    neither, so every caller guessed and every guess was rejected.

    Output schemas are exempt - they describe what the API returns, not what
    a caller must produce.
    """
    found: list[str] = []
    if isinstance(schema, dict):
        if (
            schema.get("type") == "object"
            and not schema.get("properties")
            and schema.get("additionalProperties") is not False
        ):
            found.append(path)
        for key, value in schema.items():
            found.extend(opaque_input_nodes(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            found.extend(opaque_input_nodes(value, f"{path}[{i}]"))
    return found
