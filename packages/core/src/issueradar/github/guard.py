"""The read-only guard (ADR 0004).

Every request goes through these checks before anything is sent. A test fails
if they are weakened.
"""

from __future__ import annotations

from graphql import GraphQLSyntaxError, OperationDefinitionNode, OperationType, parse

from issueradar.brand import BRAND
from issueradar.github.errors import ReadOnlyViolation

ALLOWED_REST_METHODS = frozenset({"GET"})


def ensure_read_only_rest(method: str) -> None:
    if method.upper() not in ALLOWED_REST_METHODS:
        raise ReadOnlyViolation(
            f"Refused a {method.upper()} request: {BRAND.name} only reads from GitHub."
        )


def ensure_read_only_graphql(document: str) -> None:
    """Allow only GraphQL documents whose every operation is a query."""
    try:
        parsed = parse(document)
    except GraphQLSyntaxError as exc:
        raise ReadOnlyViolation(f"Refused a GraphQL document that does not parse: {exc}") from exc
    operations = [d for d in parsed.definitions if isinstance(d, OperationDefinitionNode)]
    if not operations:
        raise ReadOnlyViolation("Refused a GraphQL document with no operation in it.")
    for op in operations:
        if op.operation is not OperationType.QUERY:
            raise ReadOnlyViolation(
                f"Refused a GraphQL {op.operation.value}: {BRAND.name} only reads from GitHub."
            )
