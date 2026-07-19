"""
Tests for Elements support: registry, lint, rendering, and integration.
"""

import json
import pytest
from pathlib import Path

from ..elements import (
    build_registry, registry_to_json, detect_extends_cycle,
    resolve_notation_chain, compute_backlinks, ID_PATTERN,
    VALID_KINDS, VALID_STATUSES, parse_node_frontmatter,
)
from ..lint import lint_elements_node, lint_elements_global, is_elements_node

FIXTURES = Path(__file__).parent / "fixtures" / "elements"
FIXTURES_CYCLE = Path(__file__).parent / "fixtures" / "elements_cycle"
FIXTURES_DUP = Path(__file__).parent / "fixtures" / "elements_duplicate"


class TestRegistry:
    """Test the elements registry builder."""

    def test_build_registry_happy_path(self):
        """Registry builds from valid fixture nodes."""
        registry = build_registry(FIXTURES, FIXTURES)
        # Should find all nodes with valid E-IDs
        assert 'E0001' in registry
        assert 'E0002' in registry
        assert 'E0003' in registry
        assert 'E0005' in registry
        assert 'E0006' in registry

    def test_registry_node_fields(self):
        """Registry nodes have correct fields."""
        registry = build_registry(FIXTURES, FIXTURES)
        node = registry['E0001']
        assert node.title == 'Valid Node'
        assert node.kind == 'definition'
        assert node.status == 'established'
        assert node.depends_on == []
        assert node.validation == {'numeric': {'file': 'validation/python/E0001_test.py'}}

    def test_registry_depends_on_field(self):
        """depends_on: field is parsed correctly."""
        registry = build_registry(FIXTURES, FIXTURES)
        node = registry['E0002']
        assert node.depends_on == ['E0001']
        assert node.notation == 'E0001'

    def test_legacy_uses_field_accepted(self, tmp_path):
        """Old 'uses:' field is accepted as fallback for depends_on:."""
        node_file = tmp_path / "E0099 - Legacy.md"
        node_file.write_text("---\nid: E0099\ntitle: Legacy\nkind: lemma\nstatus: established\nuses: [E0001]\n---\n# E0099\n")
        registry = build_registry(tmp_path, tmp_path)
        assert registry['E0099'].depends_on == ['E0001']

    def test_duplicate_id_raises(self):
        """Duplicate IDs raise RuntimeError."""
        with pytest.raises(RuntimeError, match="Duplicate element ID"):
            build_registry(FIXTURES_DUP, FIXTURES_DUP)

    def test_registry_to_json(self):
        """JSON export contains expected structure."""
        registry = build_registry(FIXTURES, FIXTURES)
        data = registry_to_json(registry)
        assert 'E0001' in data
        assert data['E0001']['title'] == 'Valid Node'
        assert data['E0001']['kind'] == 'definition'
        assert 'url' in data['E0001']

    def test_bad_id_not_in_registry(self):
        """Files with non-E-format IDs are still loaded (id: field present)."""
        registry = build_registry(FIXTURES, FIXTURES)
        # X9999 has id: X9999 which is not valid E-format but still gets into registry
        assert 'X9999' in registry


class TestExtendsCycle:
    """Test extends: cycle detection."""

    def test_cycle_detected(self):
        """Mutual extends: creates a cycle."""
        registry = build_registry(FIXTURES_CYCLE, FIXTURES_CYCLE)
        cycle = detect_extends_cycle(registry)
        assert cycle is not None
        assert 'E0001' in cycle or 'E0002' in cycle

    def test_no_cycle_in_valid(self):
        """No cycle in valid fixtures."""
        registry = build_registry(FIXTURES, FIXTURES)
        cycle = detect_extends_cycle(registry)
        assert cycle is None


class TestNotationChain:
    """Test notation chain resolution."""

    def test_simple_notation(self):
        """E0002 has notation: E0001, chain is just [E0001]."""
        registry = build_registry(FIXTURES, FIXTURES)
        chain = resolve_notation_chain(registry, 'E0002')
        assert chain == ['E0001']

    def test_no_notation(self):
        """E0001 has no notation field, empty chain."""
        registry = build_registry(FIXTURES, FIXTURES)
        chain = resolve_notation_chain(registry, 'E0001')
        assert chain == []


class TestBacklinks:
    """Test backlinks computation."""

    def test_used_by(self):
        """E0001 is used by E0002."""
        registry = build_registry(FIXTURES, FIXTURES)
        backlinks = compute_backlinks(registry)
        assert 'E0001' in backlinks
        assert 'E0002' in backlinks['E0001']


class TestLint:
    """Test Elements lint checks."""

    def test_valid_node_no_errors(self):
        """Valid node passes lint (except maybe E-PROSE-REF on E0001 text)."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0001 - Valid Node.md"
        result = lint_elements_node(path, registry)
        # Should have no errors for core schema checks
        error_codes = [code for _, code, _ in result.warnings if not code.startswith('E-PROSE')]
        assert error_codes == []

    def test_bad_id_format(self):
        """X9999 ID triggers E-ID-FORMAT."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0010 - Bad ID.md"
        result = lint_elements_node(path, registry)
        codes = [code for _, code, _ in result.warnings]
        assert 'E-ID-FORMAT' in codes

    def test_bad_enum_values(self):
        """Invalid kind/status/validation type trigger E-SCHEMA."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0004 - Bad Enum.md"
        result = lint_elements_node(path, registry)
        codes = [code for _, code, _ in result.warnings]
        assert codes.count('E-SCHEMA') >= 3  # kind, status, validation type

    def test_unresolvable_depends_on(self):
        """Non-existent IDs in depends_on: trigger E-REF-RESOLVE."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0005 - Unresolvable Uses.md"
        result = lint_elements_node(path, registry)
        codes = [code for _, code, _ in result.warnings]
        assert 'E-REF-RESOLVE' in codes
        # E9999, E8888 in depends_on, E7777 in notation = 3 unresolvable refs
        assert codes.count('E-REF-RESOLVE') == 3

    def test_superseded_consistency(self):
        """status: superseded without superseded_by triggers E-SUPERSEDED."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0006 - Superseded Bad.md"
        result = lint_elements_node(path, registry)
        codes = [code for _, code, _ in result.warnings]
        assert 'E-SUPERSEDED' in codes

    def test_filename_warning(self):
        """Filename not starting with id triggers E-ID-FILENAME."""
        registry = build_registry(FIXTURES, FIXTURES)
        path = FIXTURES / "E0010 - Bad ID.md"
        result = lint_elements_node(path, registry)
        codes = [code for _, code, _ in result.warnings]
        # The file is named "E0010 - Bad ID.md" but id is X9999
        assert 'E-ID-FILENAME' in codes

    def test_extends_cycle_global(self):
        """Global lint detects extends cycle."""
        registry = build_registry(FIXTURES_CYCLE, FIXTURES_CYCLE)
        issues = lint_elements_global(registry)
        codes = [code for code, _, _ in issues]
        assert 'E-REF-ACYCLIC' in codes

    def test_is_elements_node_detection(self):
        """is_elements_node correctly identifies nodes."""
        path = FIXTURES / "E0001 - Valid Node.md"
        assert is_elements_node(path, FIXTURES) is True

    def test_is_elements_node_outside(self):
        """File outside elements dir is not a node."""
        path = Path(__file__)
        assert is_elements_node(path, FIXTURES) is False


class TestIDPattern:
    """Test ID pattern regex."""

    def test_valid_ids(self):
        for eid in ['E0000', 'E0001', 'E9999', 'E0042']:
            assert ID_PATTERN.match(eid), f"{eid} should match"

    def test_invalid_ids(self):
        for eid in ['E001', 'E00001', 'X0001', 'e0001', 'E000A', '0001']:
            assert not ID_PATTERN.match(eid), f"{eid} should not match"


# ── Integration tests (use shared build_test_project fixture) ──────────

class TestElementsBuildIntegration:
    """Integration tests: elements build into the shared test project."""

    def test_build_succeeds(self, build_test_project):
        """Build succeeds with Elements dir present."""
        assert build_test_project.exists()

    def test_elements_index_json_created(self, build_test_project):
        """elements/index.json is written to the site."""
        index_json = build_test_project / "elements" / "index.json"
        assert index_json.exists(), f"Missing: {index_json}"
        data = json.loads(index_json.read_text())
        assert "E0001" in data
        assert "E0002" in data
        assert "E0003" in data
        assert data["E0001"]["title"] == "Base Environment"
        assert data["E0001"]["kind"] == "environment"
        assert data["E0002"]["depends_on"] == ["E0001"]

    def test_node_page_exists(self, build_test_project):
        """Element node pages are built."""
        pages = list(build_test_project.rglob("*E0001*"))
        assert pages, "E0001 page not found in build output"

    def test_id_based_permalinks(self, build_test_project):
        """Node pages are published at Elements/<ID>/, decoupled from
        filename and section directory."""
        for eid in ("E0001", "E0002", "E0003"):
            assert (build_test_project / "Elements" / eid / "index.html").exists(), \
                f"Expected ID-based permalink Elements/{eid}/index.html"
        # No title-based paths in the output
        assert not list(build_test_project.rglob("*Base Environment*"))
        # index.json carries the same URLs
        data = json.loads((build_test_project / "elements" / "index.json").read_text())
        assert data["E0001"]["url"] == "Elements/E0001/"

    def test_node_page_has_metadata(self, build_test_project):
        """Node pages get rendered metadata header with kind/status."""
        html_file = self._find_node_html(build_test_project, "E0002")
        assert html_file, "E0002 HTML not found"
        content = html_file.read_text()
        assert "proposition" in content.lower()
        assert "established" in content.lower()

    def test_node_page_has_backlinks(self, build_test_project):
        """E0001 should have 'Used by' mentioning E0002 and E0003."""
        html_file = self._find_node_html(build_test_project, "E0001")
        assert html_file, "E0001 HTML not found"
        content = html_file.read_text()
        assert "Used by" in content
        assert "E0002" in content
        assert "E0003" in content

    def test_autolink_in_prose(self, build_test_project):
        """E-IDs in prose get autolinked."""
        html_file = self._find_node_html(build_test_project, "E0003")
        assert html_file, "E0003 HTML not found"
        content = html_file.read_text()
        # The prose mentions E0001 and E0002 — they should appear as links
        assert "E0001" in content
        assert "E0002" in content

    def test_node_h1_is_plain_title(self, build_test_project):
        """H1 is the plain frontmatter title; the ID lives in the chip row
        as a self-link (class el-id), not in the heading."""
        html_file = self._find_node_html(build_test_project, "E0001")
        assert html_file, "E0001 HTML not found"
        content = html_file.read_text()
        import re
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
        assert h1_match, "No H1 found"
        h1_content = h1_match.group(1)
        # H1 shows the title without the ID
        assert 'E0001' not in h1_content
        # The ID badge is a self-link in the metadata chip row
        assert re.search(r'<a[^>]*class="el-id"[^>]*>E0001</a>', content)

    def test_links_are_relative_paths(self, build_test_project):
        """Generated links use relative file paths, not bare IDs."""
        html_file = self._find_node_html(build_test_project, "E0002")
        assert html_file, "E0002 HTML not found"
        content = html_file.read_text()
        # Links to E0001 should contain a path with .md-derived URL, not just "E0001"
        # MkDocs converts .md links to proper URLs
        assert 'href="E0001"' not in content

    def test_non_elements_page_unaffected(self, build_test_project):
        """Non-elements pages still build normally."""
        index_html = build_test_project / "index.html"
        assert index_html.exists()

    @staticmethod
    def _find_node_html(build_dir: Path, node_id: str) -> Path | None:
        """Find the built HTML for a node by ID."""
        for candidate in build_dir.rglob(f"*{node_id}*"):
            if candidate.suffix == '.html':
                return candidate
            if candidate.is_dir():
                idx = candidate / "index.html"
                if idx.exists():
                    return idx
        return None
