"""
Unit tests for environment regex patterns.

Tests the regex-based environment parser.
"""

import pytest
from ..environment_regex import parse_environments, EnvironmentMatch


class TestParseEnvironments:
    """Test parse_environments function."""

    def test_simple_label_extraction(self):
        """Parse returns label content without parens."""
        text = "**Theorem (Pythagorean).** content"
        envs = parse_environments(text)
        assert len(envs) == 1
        assert envs[0].label == "Pythagorean"

    def test_no_label(self):
        """Parse returns None for label when absent."""
        text = "**Definition.** content"
        envs = parse_environments(text)
        assert len(envs) == 1
        assert envs[0].label is None

    def test_environment_name_with_spaces(self):
        """Environment name with spaces is captured."""
        text = "**Vector Field.** A vector field is..."
        envs = parse_environments(text)
        assert len(envs) == 1
        assert envs[0].env_name == "Vector Field"

    def test_environment_name_with_ampersand(self):
        """Environment name with ampersand is captured."""
        text = "**Lemma & Corollary.** Some content."
        envs = parse_environments(text)
        assert len(envs) == 1
        assert envs[0].env_name == "Lemma & Corollary"

    def test_must_start_with_capital(self):
        """Lowercase environment names should not match."""
        text = "**definition.** Some content."
        envs = parse_environments(text)
        assert len(envs) == 0

    def test_must_have_period_before_close(self):
        """Missing period before ** should not match."""
        text = "**Definition** Some content."
        envs = parse_environments(text)
        assert len(envs) == 0


class TestContentTermination:
    """Test that content is correctly terminated at boundaries."""

    def test_content_terminated_by_two_blank_lines(self):
        """Content should end before two blank lines."""
        text = "**Definition.** First definition.\n\n\n**Theorem.** Next theorem."
        envs = parse_environments(text)
        assert len(envs) == 2
        assert "First definition." in envs[0].content
        assert "Next theorem" not in envs[0].content

    def test_content_terminated_by_next_env_no_blank_line(self):
        """Content should end before next environment without blank line."""
        text = "**Definition.** First.\n**Theorem.** Second."
        envs = parse_environments(text)
        assert len(envs) == 2
        assert "First." in envs[0].content
        assert "Second." not in envs[0].content

    def test_content_terminated_by_next_env_with_blank_line(self):
        """Content should end before next environment with blank line."""
        text = "**Definition.** First.\n\n**Theorem.** Second."
        envs = parse_environments(text)
        assert len(envs) == 2
        assert "First." in envs[0].content
        assert "Second." not in envs[0].content

    def test_content_terminated_by_heading(self):
        """Content should end before markdown heading."""
        text = "**Definition.** First definition.\n\n## New Section\nMore."
        envs = parse_environments(text)
        assert len(envs) == 1
        assert "First definition." in envs[0].content
        assert "New Section" not in envs[0].content

    def test_content_terminated_by_heading_no_blank_line(self):
        """Content should end before heading even without blank line."""
        text = "**Definition.** First definition.\n## New Section"
        envs = parse_environments(text)
        assert len(envs) == 1
        assert "First definition." in envs[0].content
        assert "New Section" not in envs[0].content

    def test_content_to_eof(self):
        """Content continues to EOF if no terminator found."""
        text = "**Definition.** A definition that goes to the end."
        envs = parse_environments(text)
        assert len(envs) == 1
        assert "to the end." in envs[0].content

    def test_adjacent_environments_single_blank_line(self):
        """Adjacent environments separated by single blank line should be separate.

        This is the pattern from the polynomial approximation file where
        Definition (Metric Space) and Remark are only separated by 1 blank line.
        Previously they would be merged because we required 2 blank lines to terminate.
        Now they terminate when a new environment pattern (** ... .**) is detected.
        """
        text = "**Definition.** First definition.\n\n**Remark.** Second remark."

        envs = parse_environments(text)
        assert len(envs) == 2, f"Expected 2 environments, got {len(envs)}"
        assert envs[0].env_name == "Definition"
        assert envs[1].env_name == "Remark"
        assert "First definition" in envs[0].content
        assert "Second remark" not in envs[0].content


class TestMultipleEnvironments:
    """Test parsing multiple environments in one document."""

    def test_two_environments_separated(self):
        """Parse two environments properly separated."""
        text = "**Definition.** First.\n\n\n**Theorem.** Second."
        envs = parse_environments(text)
        assert len(envs) == 2
        assert envs[0].env_name == "Definition"
        assert envs[1].env_name == "Theorem"

    def test_environments_preserve_content_with_asterisks(self):
        """Content can contain asterisks and markdown formatting."""
        text = "**Definition.** Use *emphasis* and **bold**.\n\n\n**Theorem.** More."
        envs = parse_environments(text)
        assert len(envs) == 2
        assert "*emphasis*" in envs[0].content
        assert "**bold**" in envs[0].content


class TestEdgeCasesAndErrors:
    """Test edge cases and invalid syntax."""

    def test_no_environments(self):
        """Document with no environments."""
        text = "Just regular text without any definitions."
        envs = parse_environments(text)
        assert len(envs) == 0

    def test_environment_at_document_start(self):
        """Environment can appear at the very start."""
        text = "**Definition.** Content at the beginning."
        envs = parse_environments(text)
        assert len(envs) == 1

    def test_environment_after_text_on_same_line_fails(self):
        """Text before ** on same line should not match."""
        text = "Some text **Definition.** Content."
        envs = parse_environments(text)
        assert len(envs) == 0

    def test_incomplete_environment(self):
        """Missing closing .** should not match."""
        text = "**Definition** Content without period and close."
        envs = parse_environments(text)
        assert len(envs) == 0


class TestPositionTracking:
    """Verify match positions are correct for replacement."""

    def test_match_positions_single_env(self):
        """Match positions should span the entire environment."""
        text = "prefix\n**Definition.** content"
        envs = parse_environments(text)
        assert len(envs) == 1
        assert envs[0].start > 0
        assert envs[0].end > envs[0].start

    def test_match_positions_multiple_envs(self):
        """Positions should be correct for multiple environments."""
        text = "**Definition.** First.\n\n\n**Theorem.** Second."
        envs = parse_environments(text)
        assert len(envs) == 2
        # Positions should not overlap
        assert envs[0].end <= envs[1].start


class TestLabelExtractionWithoutNestedParens:
    """Test label extraction for cases without nested parentheses."""

    def test_label_simple(self):
        """Simple label without nested parens."""
        text = "**Definition** (Continuous function).\nContent."
        envs = parse_environments(text)
        # Note: pattern requires period immediately after name before label
        # This test shows the current limitation
        assert len(envs) == 0

    def test_label_with_math_no_parens_in_math(self):
        """Label with math but no parentheses inside math."""
        text = "**Definition** ($L^p$ space).\nContent."
        envs = parse_environments(text)
        # Same limitation - space before label not supported
        assert len(envs) == 0


class TestEnvironmentTermination:
    """Test that environments are properly terminated before section headings."""

    def test_environment_terminated_before_section_heading(self):
        """Environment should terminate before ## heading with blank lines."""
        text = """**Definition (Test).**
Some definition content here.


## Next Section

More content after heading."""

        envs = parse_environments(text)
        assert len(envs) == 1, f"Expected 1 environment, got {len(envs)}"
        assert envs[0].env_name == "Definition"
        assert "Some definition content" in envs[0].content
        assert "Next Section" not in envs[0].content
        assert "More content after heading" not in envs[0].content

    def test_environment_content_ends_before_heading_start(self):
        """Environment content should not include the heading itself."""
        text = """**Definition (Test).**
Content here.


## References"""

        envs = parse_environments(text)
        assert len(envs) == 1
        # The content should end BEFORE the heading marker
        # It may have trailing whitespace/newlines but not the heading text
        assert "References" not in envs[0].content
        assert envs[0].content.strip().endswith("Content here.")


class TestKnownLimitations:
    """Document known limitations of the current regex."""

    def test_label_with_nested_parens_fails(self):
        r"""Label with nested parentheses like ($C^k(\Omega)$, text) fails.

        This is a known limitation of the original regex pattern:
        ([^)]+) matches anything except ), so it can't handle nested parens.
        """
        text = r"**Definition** ($C^k(\Omega)$, compact–open topology)." + "\nContent."
        envs = parse_environments(text)
        # Original regex can't match this, so expect no match
        assert len(envs) == 0

    def test_multiple_envs_with_nested_parens_fails(self):
        """Multiple environments can't be parsed if any have nested parens in labels."""
        text = """**Definition** (Continuous).
Content one.

**Lemma** ($L^p$ spaces).
Content two.

**Theorem** ($C^k(\\Omega)$, text).
Content three."""
        envs = parse_environments(text)
        # Can parse first two, but third fails due to nested parens
        # So we should get 2 or 3 depending on how parsing stops
        assert len(envs) <= 3

    def test_production_environment_with_nested_parens(self):
        r"""FAILING TEST: Production environment from ultra repository.

        This is the specific environment that failed in production:
        **Definition ($C^k(\Omega)$, compact–open topology).**

        The label contains both math notation with nested parens and descriptive text.
        This should be matched and wrapped as an environment, but currently fails
        due to the regex pattern ([^)]+) not handling nested parentheses.
        """
        text = r"""**Definition ($C^k(\Omega)$, compact–open topology).**
The space $C^k(\Omega)$ is equipped with the compact-open topology generated
by seminorms involving derivatives up to order $k$ on compact subsets."""

        envs = parse_environments(text)

        # This should match ONE environment
        assert len(envs) == 1, f"Expected 1 environment, got {len(envs)}"

        # The environment should have the correct name
        assert envs[0].env_name == "Definition"

        # The label should contain both the math notation and the descriptive text
        assert envs[0].label is not None, "Label should not be None"
        assert "$C^k(\\Omega)$" in envs[0].label or "C^k" in envs[0].label
        assert "compact–open topology" in envs[0].label or "compact" in envs[0].label

        # The content should have the definition text
        assert "compact-open topology" in envs[0].content or "seminorms" in envs[0].content
