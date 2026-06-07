"""
Unit tests for the PEG-based environment parser.

Tests verify that the parser correctly identifies and extracts:
- Environment names
- Optional labels with math notation and special characters
- Content with proper termination
"""

import pytest
from ..environment_regex import parse_environments


class TestBasicEnvironments:
    """Test parsing of basic environment syntax."""

    def test_simple_environment_no_label(self):
        """Test: **Definition.** content"""
        markdown = "**Definition.** This is a definition."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Definition"
        assert envs[0].label is None
        assert "This is a definition." in envs[0].content

    def test_simple_environment_with_label(self):
        """Test: **Theorem (Pythagorean).** content"""
        markdown = "**Theorem (Pythagorean).** The sum of squares..."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Theorem"
        assert envs[0].label == "Pythagorean"
        assert "The sum of squares" in envs[0].content

    def test_environment_multiline_name(self):
        """Test environment name with spaces: **Vector Field.** content"""
        markdown = "**Vector Field.** A vector field..."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Vector Field"
        assert envs[0].label is None


class TestLabelsWithMathNotation:
    """Test edge case: labels containing math notation and special characters."""

    def test_label_with_math_simple(self):
        r"""Test: **Definition ($C^k(\Omega)$).**"""
        markdown = r"**Definition ($C^k(\Omega)$).** Content here."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Definition"
        assert envs[0].label is not None
        assert r"$C^k(\Omega)$" in envs[0].label

    def test_label_with_math_and_comma(self):
        r"""Test edge case: **Definition ($C^k(\Omega)$, compact–open topology).**"""
        markdown = r"**Definition ($C^k(\Omega)$, compact–open topology).** Content here."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Definition"
        assert envs[0].label is not None
        assert r"$C^k(\Omega)$" in envs[0].label
        assert "compact–open topology" in envs[0].label

    def test_label_with_nested_parens(self):
        r"""Test label with nested parentheses: **Lemma (property (local)).**"""
        markdown = r"**Lemma (property (local)).** Content here."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Lemma"
        assert envs[0].label is not None
        assert "property (local)" in envs[0].label

    def test_label_with_multiple_math_expressions(self):
        r"""Test label with multiple math expressions: **Definition ($L^p$ spaces, $p > 1$).**"""
        markdown = r"**Definition ($L^p$ spaces, $p > 1$).** Content."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Definition"
        assert envs[0].label is not None
        assert r"$L^p$" in envs[0].label
        assert "$p > 1$" in envs[0].label


class TestContentTermination:
    """Test that content is correctly terminated at boundaries."""

    def test_content_terminated_by_blank_lines(self):
        """Content should end before two blank lines."""
        markdown = """**Definition.** First definition.


**Theorem.** Next theorem."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert "First definition." in envs[0].content
        assert "Next theorem" not in envs[0].content

    def test_content_terminated_by_next_environment(self):
        """Content should end before next environment without blank line."""
        markdown = """**Definition.** First definition.
**Theorem.** Next theorem."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert "First definition." in envs[0].content
        assert "Next theorem" not in envs[0].content

    def test_content_terminated_by_heading(self):
        """Content should end before heading."""
        markdown = """**Definition.** First definition.

## New Section
More content."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "First definition." in envs[0].content
        assert "New Section" not in envs[0].content

    def test_content_terminated_by_heading_no_blank_line(self):
        """Content should end before heading even without blank line."""
        markdown = """**Definition.** First definition.
## New Section"""
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "First definition." in envs[0].content
        assert "New Section" not in envs[0].content

    def test_content_to_eof(self):
        """Content continues to end of file if no terminator found."""
        markdown = "**Definition.** A definition that goes to the end."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "A definition that goes to the end." in envs[0].content


class TestMultipleEnvironments:
    """Test parsing multiple environments in one document."""

    def test_two_environments_separated_by_blank_lines(self):
        """Parse multiple environments properly."""
        markdown = """**Definition.** First definition.


**Theorem.** A theorem."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert envs[0].env_name == "Definition"
        assert envs[1].env_name == "Theorem"

    def test_three_environments_mixed(self):
        r"""Parse three environments with different label patterns."""
        markdown = r"""**Definition (Continuous function).** A function is continuous if...


**Lemma ($L^p$ spaces).** For $p > 1$...


**Theorem (Hahn-Banach).** Extension property."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 3
        assert envs[0].label == "Continuous function"
        assert "$L^p$ spaces" in envs[1].label
        assert envs[2].label == "Hahn-Banach"

    def test_environments_with_content_containing_asterisks(self):
        """Content can contain asterisks without breaking parsing."""
        markdown = """**Definition.** Use *emphasis* and **bold** in content.


**Theorem.** Use * and ** freely here."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert "*emphasis*" in envs[0].content
        assert "**bold**" in envs[0].content


class TestPositionTracking:
    """Test that positions are correctly tracked for replacement."""

    def test_start_and_end_positions(self):
        """Verify start and end positions are correct."""
        markdown = "**Definition.** content"
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].start == 0  # Position of first **
        assert envs[0].end > envs[0].start

    def test_positions_multiple_envs(self):
        """Positions should be correctly tracked for multiple environments."""
        markdown = "**Definition.** First.\n\n**Theorem.** Second."
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert envs[0].start < envs[1].start
        assert envs[0].end <= envs[1].start


class TestComplexLabels:
    """Test various complex label formats."""

    def test_label_with_special_chars(self):
        """Test label with dashes and special unicode."""
        markdown = "**Lemma (Cauchy–Schwarz inequality).** Content."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].label is not None
        assert "Cauchy–Schwarz" in envs[0].label

    def test_label_with_ampersand(self):
        """Test label with ampersand in name."""
        markdown = "**Lemma & Corollary.** Content."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert envs[0].env_name == "Lemma & Corollary"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_no_environments(self):
        """Document with no environments."""
        markdown = "Just regular text without any definitions or theorems."
        envs = list(parse_environments(markdown))

        assert len(envs) == 0

    def test_incomplete_environment_start(self):
        """Text that looks like environment but isn't complete."""
        markdown = "**Definition without closing"
        envs = list(parse_environments(markdown))

        assert len(envs) == 0

    def test_missing_period_before_closing(self):
        """Environment must have period before closing **"""
        markdown = "**Definition** content"
        envs = list(parse_environments(markdown))

        assert len(envs) == 0

    def test_environment_with_empty_content(self):
        """Environment with empty content (terminates immediately)."""
        markdown = "**Definition.** \n\n**Theorem.** Content"
        envs = list(parse_environments(markdown))

        assert len(envs) == 2
        assert "Definition" in envs[0].env_name
        assert "Theorem" in envs[1].env_name

    def test_environment_name_must_start_with_capital(self):
        """Environment name must start with capital letter."""
        markdown = "**definition.** content"
        envs = list(parse_environments(markdown))

        assert len(envs) == 0


class TestPreservationOfContent:
    """Test that content is preserved correctly."""

    def test_content_with_math_notation(self):
        """Math notation in content is preserved."""
        markdown = """**Definition.** Let $f(x) = x^2 + 2x + 1$ and consider $$\\int_0^1 f(x)\\,dx$$."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "$f(x) = x^2 + 2x + 1$" in envs[0].content
        assert "$$\\int_0^1 f(x)\\,dx$$" in envs[0].content

    def test_content_with_custom_id(self):
        """Custom ID metadata in content is preserved."""
        markdown = "**Definition.** {#my-def}\nSome content here."
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "{#my-def}" in envs[0].content

    def test_multiline_content_preserved(self):
        """Multiline content is preserved exactly."""
        markdown = """**Definition.** First line
of definition continues
on multiple lines."""
        envs = list(parse_environments(markdown))

        assert len(envs) == 1
        assert "First line" in envs[0].content
        assert "multiple lines" in envs[0].content
