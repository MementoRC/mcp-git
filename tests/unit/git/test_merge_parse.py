"""Pure tests for mcp_server_git.git.merge_parse (issue #210, Gap 1)."""

from mcp_server_git.git.merge_parse import (
    parse_merge_tree_output,
    render_conflict_paths,
    render_tree_hint,
)


class TestParseMergeTreeOutput:
    """Tests for parse_merge_tree_output."""

    def test_parse_merge_tree_output_extracts_oid_stage_entries_and_messages(self):
        stdout = (
            "abc1234def5678901234567890abcdef12345678\n"
            "\n"
            "100644 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 2\tsrc/app.py\n"
            "100644 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 3\tsrc/app.py\n"
            "\n"
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "CONFLICT (modify/delete): foo.txt deleted in feature\n"
        )

        result = parse_merge_tree_output(stdout)

        assert result.tree_oid == "abc1234def5678901234567890abcdef12345678"
        assert result.conflict_paths == ["src/app.py"]
        assert result.conflict_kinds == {"src/app.py": "content"}
        assert len(result.messages) == 2
        assert "src/app.py" in result.messages[0]
        assert "foo.txt" in result.messages[1]

    def test_parse_merge_tree_output_derives_paths_from_messages_when_no_stage_entries(
        self,
    ):
        stdout = (
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "CONFLICT (modify/delete): foo.txt deleted in feature\n"
        )

        result = parse_merge_tree_output(stdout)

        assert result.conflict_paths == ["src/app.py", "foo.txt"]
        assert result.conflict_kinds == {
            "src/app.py": "content",
            "foo.txt": "modify/delete",
        }

    def test_parse_merge_tree_output_handles_no_oid_first_line(self):
        stdout = "CONFLICT (content): Merge conflict in src/app.py\n"

        result = parse_merge_tree_output(stdout)

        assert result.tree_oid is None
        assert result.conflict_paths == ["src/app.py"]
        assert len(result.messages) == 1

    def test_parse_merge_tree_output_recognises_abbreviated_oid(self):
        stdout = "abc1234\n"

        result = parse_merge_tree_output(stdout)

        assert result.tree_oid == "abc1234"

    def test_parse_merge_tree_output_preserves_unrecognised_lines_when_no_oid(self):
        stdout = "some other output without conflict markers\n"

        result = parse_merge_tree_output(stdout)

        assert result.tree_oid is None
        assert result.other_lines == ["some other output without conflict markers"]


class TestRenderTreeHint:
    """Tests for render_tree_hint."""

    def test_render_tree_hint_includes_oid_and_git_show_hint(self):
        lines = render_tree_hint("abc1234")

        text = "\n".join(lines)
        assert "abc1234" in text
        assert 'git_show(revision="abc1234:<path>")' in text


class TestRenderConflictPaths:
    """Tests for render_conflict_paths."""

    def test_render_conflict_paths_emits_no_dash_bullet(self):
        result = parse_merge_tree_output(
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "CONFLICT (modify/delete): foo.txt deleted in feature\n"
        )

        rendered = render_conflict_paths(result)

        assert "  - " not in "\n".join(rendered)
        assert "src/app.py" in "\n".join(rendered)
        assert "foo.txt" in "\n".join(rendered)

    def test_render_conflict_paths_returns_empty_list_when_no_conflicts(self):
        result = parse_merge_tree_output("abc1234\n")

        assert render_conflict_paths(result) == []
