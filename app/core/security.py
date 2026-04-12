from __future__ import annotations

from typing import Iterable


ROLE_ORDER = {
    "guest": 0,
    "business": 0,
    "employee": 1,
    "manager": 1,
    "procurement": 1,
    "legal": 1,
    "admin": 2,
}

ROLE_ALIASES = {
    "guest": ["business"],
    "employee": ["manager", "procurement", "legal", "admin"],
    "business": ["business"],
    "manager": ["manager"],
    "procurement": ["procurement"],
    "legal": ["legal"],
    "admin": ["admin"],
}

DEFAULT_ROLES = ["business", "manager", "procurement", "legal", "admin"]


def normalize_roles(raw_roles: str | Iterable[str] | None) -> list[str]:
    if raw_roles is None:
        return list(DEFAULT_ROLES)
    if isinstance(raw_roles, str):
        roles = [role.strip().lower() for role in raw_roles.split(",") if role.strip()]
    else:
        roles = [str(role).strip().lower() for role in raw_roles if str(role).strip()]

    unique_roles: list[str] = []
    for role in roles:
        for candidate in ROLE_ALIASES.get(role, [role]):
            if candidate in ROLE_ORDER and candidate not in unique_roles:
                unique_roles.append(candidate)
    return unique_roles or list(DEFAULT_ROLES)


def expand_role_scope(raw_roles: str | Iterable[str] | None) -> list[str]:
    expanded: set[str] = set()
    for role in normalize_roles(raw_roles):
        minimum_level = ROLE_ORDER.get(role, 0)
        for candidate, level in ROLE_ORDER.items():
            if level >= minimum_level:
                expanded.update(ROLE_ALIASES.get(candidate, [candidate]))
    return sorted(expanded, key=lambda item: ROLE_ORDER[item])


def can_access(user_role: str, allowed_roles: str | Iterable[str] | None) -> bool:
    normalized_role = user_role.strip().lower() if user_role else "business"
    roles = normalize_roles(allowed_roles)
    return normalized_role in roles or normalized_role == "admin"
