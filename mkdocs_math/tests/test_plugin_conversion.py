"""
Tests for plugin markdown conversion.

Tests the convert_theorem_environments function to ensure proper
pymdownx.blocks syntax generation.
"""

import pytest
from ..plugin import convert_theorem_environments


class TestConvertTheoremEnvironments:
    """Test the convert_theorem_environments plugin function."""

    def test_environment_closing_marker_on_own_line(self):
        """Environment closing /// should be on its own line followed by newline."""
        markdown = """**Definition (Test).**
Some content here.


## References"""

        result = convert_theorem_environments(markdown)

        # Check that closing /// is followed by at least one newline before ##
        # (blank lines that terminated the environment are preserved)
        assert result.count("///") == 2, f"Should have opening and closing ///. Got: {repr(result)}"
        assert "##" in result, f"Should preserve heading. Got: {repr(result)}"
        # Should NOT have /// directly followed by ##
        assert "///##" not in result, f"Closing /// should not be directly followed by ##. Got: {repr(result)}"

    def test_marker_balance(self):
        """Open and closing markers should be balanced."""
        markdown = """**Definition (Test1).**
Content 1.


**Theorem (Test2).**
Content 2.


## References"""

        result = convert_theorem_environments(markdown)

        open_count = result.count("/// html | div")
        close_count = result.count("\n///\n")

        # Account for final closing that may not have another line after
        if result.rstrip().endswith("///"):
            close_count += 1

        assert open_count == close_count, (
            f"Unbalanced markers: {open_count} opens vs {close_count} closes. "
            f"Result: {repr(result[-200:])}"
        )

    def test_environment_before_heading(self):
        """When environment is followed by heading, structure should be valid."""
        markdown = """**Example (Test).**
Let $x$ be something.


## Next Section"""

        result = convert_theorem_environments(markdown)

        # Should have proper block structure
        assert "/// html | div" in result
        assert "\n///\n" in result or result.rstrip().endswith("///")
        # The heading should come after the closing ///
        lines = result.split('\n')
        closing_index = None
        heading_index = None
        for i, line in enumerate(lines):
            if line == "///":
                closing_index = i
            if line.startswith("## Next Section"):
                heading_index = i

        assert closing_index is not None, "Should have closing marker"
        assert heading_index is not None, "Should have heading"
        assert closing_index < heading_index, "Closing marker should come before heading"
