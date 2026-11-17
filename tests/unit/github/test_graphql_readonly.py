"""Read-only GraphQL guard and github_graphql_query tool (#355)."""

import json
from unittest.mock import MagicMock

import pytest

from mcp_server_git.github.client import GraphQLError
from mcp_server_git.github.graphql_query import MAX_CHARS, github_graphql_query
from mcp_server_git.github.graphql_readonly import read_only_violation
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import call

ALLOWED = {
    "shorthand": "{ viewer { login } }",
    "named_query": 'query Q($n: Int = 1) { repository(owner: "o") { issues(first: $n) { totalCount } } }',
    "query_and_fragment": 'query { node(id: "x") { ...F } } fragment F on Issue { title }',
    "fragment_first": 'fragment F on Issue { title } query { node(id: "x") { ...F } }',
    "directive_header": "query Q @cached(ttl: 5) { viewer { login } }",
    "mutation_in_string": 'query { search(query: "mutation { x }", type: ISSUE) { issueCount } }',
    "mutation_in_block_string": 'query { search(query: """\nmutation {\n}""", type: ISSUE) { issueCount } }',
    "block_string_escaped_quotes": 'query { search(query: """a \\""" mutation""", type: ISSUE) { issueCount } }',
    "string_escaped_quote": r'query { search(query: "a \" mutation {", type: ISSUE) { issueCount } }',
    "mutation_in_comment": "# mutation { x }\n{ viewer { login } }",
    "mutation_as_alias": "{ mutation: viewer { subscription: login } }",
    "mutation_as_enum_default": "query Q($m: Kind = mutation) { viewer { login } }",
    "multiple_queries": "query A { viewer { id } } query B { viewer { login } }",
    "comment_ends_at_crlf": "# c\r\n{a}",
    "comment_ends_at_lone_cr": "# c\r{a}",
    "leading_bom": "﻿{a}",
    "keyword_prefix_field_names": "{ mutationX _mutation subscriptionY }",
    "block_string_escaped_triple_quote": 'query { a(b: """x \\""" y""") }',
    "block_string_backslash_then_escaped_triple_quote": 'query { a(b: """x \\\\""" y""") }',
    "nested_input_object_default": "query Q($a: In = {x: {y: 1}}) {a}",
    "exponent_and_negative_numbers": "{ a(x: 1e5, y: -1) }",
}

REJECTED = {
    "mutation": ("mutation { addStar(input: {}) { clientMutationId } }", "mutation"),
    "mutation_no_space": ("mutation{addStar(input:{}){clientMutationId}}", "mutation"),
    "named_mutation": ("mutation M { x }", "mutation"),
    "subscription": ("subscription { x }", "subscription"),
    "query_then_mutation": ("query{a}mutation{b}", "mutation"),
    "query_then_spaced_mutation": ("query A { a }\n\nmutation B { b }", "mutation"),
    "mutation_after_fragment": ("fragment F on T { a } mutation { b }", "mutation"),
    "mutation_in_header": ("query A mutation { b }", "mutation"),
    "unclosed_brace": ("{ viewer { login }", "unbalanced"),
    "extra_closing_brace": ("{ viewer { login } } }", "unexpected top-level"),
    "mismatched_brackets": ("{ a(b: [1) }", "unbalanced"),
    "unclosed_paren": ("query Q($a: Int { x }", "unbalanced"),
    "unterminated_string": ('{ a(b: "oops) }', "unterminated string"),
    "unterminated_block_string": ('{ a(b: """oops) }', "unterminated block string"),
    "string_swallows_newline": ('{ a(b: "x\n") }', "unterminated string"),
    "empty": ("", "empty"),
    "whitespace_only": (" \n\t, ", "empty"),
    "comment_only": ("# just a comment", "empty"),
    "garbage": ("hello world", "unexpected top-level"),
    "unknown_keyword": ("type Foo { a: Int }", "unexpected top-level"),
    "stray_symbol": ("%%%", "unexpected character"),
    "header_without_body": ("query Q", "incomplete"),
    "top_level_string": ('"desc" { a }', "unexpected top-level"),
    "cr_ends_comment_hiding_mutation": (
        'fragment F on Mutation { addStar(input:{starrableId:"X"}) { clientMutationId } }'
        " #\r mutation { ...F }",
        "mutation",
    ),
    "cr_ends_comment_before_mutation": ("{a} #\r mutation{b}", "mutation"),
    "lf_ends_comment_before_mutation": ("{a} # x\n mutation{b}", "mutation"),
    "crlf_ends_comment_before_mutation": ("{a} # x\r\n mutation{b}", "mutation"),
    "bom_inside_keyword": ("mut﻿ation{a}", "unexpected top-level"),
    "bom_between_definitions": ("{a}﻿ mutation{b}", "byte order mark"),
    "bom_inside_selection": ("{ a﻿ }", "byte order mark"),
    "non_ascii_name": ("{ é }", "unexpected character"),
    "nul_byte": ("{ a\x00 }", "unexpected character"),
    "number_prefixed_keyword": ("1mutation{a}", "mutation"),
    "string_escape_swallows_cr": ('{ a(b: "x\\\r") }', "unterminated string"),
    # Known, intentional false rejections: the guard is keyword-based and
    # fail-closed, so a forbidden keyword used as a name is refused too.
    "false_rejection_query_named_mutation": ("query mutation {a}", "mutation"),
    "false_rejection_fragment_named_subscription": (
        "fragment subscription on T {a}",
        "subscription",
    ),
}


@pytest.mark.parametrize("document", ALLOWED.values(), ids=ALLOWED.keys())
def test_read_only_violation_returns_none_when_document_is_a_query(document):
    assert read_only_violation(document) is None


@pytest.mark.parametrize(("document", "reason"), REJECTED.values(), ids=REJECTED.keys())
def test_read_only_violation_returns_reason_when_document_is_unsafe(document, reason):
    violation = read_only_violation(document)

    assert violation is not None
    assert reason in violation


def test_read_only_violation_allows_deeply_nested_input_when_balanced():
    document = "{a" * 5000 + "}" * 5000

    assert read_only_violation(document) is None


def test_github_graphql_query_schema_has_no_operation_name_property():
    iface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())
    schema = iface.get_tool_spec("github_graphql_query")["schema"]

    assert not {"operationName", "operation_name"} & set(schema["properties"])


class FakeGraphQL:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        if self.error:
            raise self.error
        return self.result


async def _run(client, query, variables=None):
    return await call(github_graphql_query, client, "o", "r", query, variables)


@pytest.mark.asyncio
@pytest.mark.parametrize("document", [v[0] for v in REJECTED.values()])
async def test_github_graphql_query_fails_without_network_call_when_document_unsafe(
    document,
):
    client = FakeGraphQL(result={})

    result = await _run(client, document)

    assert isinstance(result, ToolFailure)
    assert "Rejected GraphQL document" in result
    assert client.calls == []


@pytest.mark.asyncio
async def test_github_graphql_query_returns_compact_data_when_query_allowed():
    client = FakeGraphQL(result={"viewer": {"login": "me"}})

    result = await _run(client, "{ viewer { login } }", {"a": 1})

    assert not isinstance(result, ToolFailure)
    assert result == '{"viewer":{"login":"me"}}'
    assert client.calls == [("{ viewer { login } }", {"a": 1})]


@pytest.mark.asyncio
async def test_github_graphql_query_truncates_with_marker_when_data_too_large():
    client = FakeGraphQL(result={"blob": "x" * (MAX_CHARS * 2)})

    result = await _run(client, "{ viewer { login } }")

    assert "[truncated: showing first 20000 of" in result
    assert len(result) < MAX_CHARS + 200


@pytest.mark.asyncio
async def test_github_graphql_query_returns_data_untruncated_when_within_limit():
    client = FakeGraphQL(result={"n": "x" * 100})

    result = await _run(client, "{ viewer { login } }")

    assert json.loads(result) == {"n": "x" * 100}


@pytest.mark.asyncio
async def test_github_graphql_query_fails_with_message_when_graphql_errors():
    error = GraphQLError([{"message": "Field 'x' doesn't exist"}])
    client = FakeGraphQL(error=error)

    result = await _run(client, "{ x }")

    assert isinstance(result, ToolFailure)
    assert "Field 'x' doesn't exist" in result
