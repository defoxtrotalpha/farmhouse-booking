"""Multitenancy helpers.

The app supports multiple estates (tenants). Scoped tables carry a *nullable*
``tenant_id``. To stay backward-compatible with the test suite (which creates
rows directly without a tenant and logs in without naming one), filtering is
NULL-symmetric:

* ``tenant_id IS NULL``  -> the implicit shared single-tenant space (tests).
* ``tenant_id == <id>``  -> a real estate, fully isolated from the others.

Use :func:`tenant_clause` inside ``.filter(...)`` to scope any query by the
current user's tenant.
"""
from __future__ import annotations

import re


def tenant_clause(column, tenant_id):
    """Return a SQLAlchemy filter clause scoping ``column`` to ``tenant_id``.

    When ``tenant_id`` is ``None`` we match rows whose tenant is also NULL so
    that the single-tenant test space resolves to one estate.
    """
    if tenant_id is None:
        return column.is_(None)
    return column == tenant_id


def slugify(name: str) -> str:
    """Lower-case, hyphenate and strip a human estate name into a URL slug."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "estate"
