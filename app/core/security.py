from __future__ import annotations

from typing import Iterable


ROLE_ORDER = {"guest": 0, "employee": 1, "admin": 2}


def normalize_roles(raw_roles: str | Iterable[str] | None) -> list[str]:
    if raw_roles is None:
        return ["guest", "employee", "admin"]
    if isinstance(raw_roles, str):
        roles = [role.strip().lower() for role in raw_roles.split(",") if role.strip()]
    else:
        roles = [str(role).strip().lower() for role in raw_roles if str(role).strip()]

    unique_roles: list[str] = []
    for role in roles:
        if role in ROLE_ORDER and role not in unique_roles:
            unique_roles.append(role)
    return unique_roles or ["guest", "employee", "admin"]


def expand_role_scope(raw_roles: str | Iterable[str] | None) -> list[str]:
    expanded: set[str] = set()
    for role in normalize_roles(raw_roles):
        minimum_level = ROLE_ORDER.get(role, 0)
        for candidate, level in ROLE_ORDER.items():
            if level >= minimum_level:
                expanded.add(candidate)
    return sorted(expanded, key=lambda item: ROLE_ORDER[item])


def can_access(user_role: str, allowed_roles: str | Iterable[str] | None) -> bool:
    normalized_role = user_role.strip().lower() if user_role else "guest"
    roles = normalize_roles(allowed_roles)
    return normalized_role in roles