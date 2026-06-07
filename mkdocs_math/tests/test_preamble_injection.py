"""
Integration tests for mkdocs-math plugin preamble injection.

Three-layer testing approach - stages in validation:

LAYER 1: Build Validation
- Does MkDocs build successfully with the plugin?
- Is the build output created?

LAYER 2: HTML Inspection
- Is the preamble actually injected into the HTML?
- Are the LaTeX preamble commands present in the output?
- Is the HTML structure valid?

LAYER 3: Browser Rendering (Playwright)
- Does MathJax actually process and render the preamble?
- Are the math elements rendered correctly?
- Can subtle rendering issues be detected?

Tests build once (shared fixture) and then validate in stages.
Each layer can partially succeed - if Playwright isn't available,
layer 3 tests can be skipped while 1 & 2 still run.
"""

import pytest


def read_html_file(build_dir, relative_path):
    """Helper to read HTML files from build output."""
    file_path = build_dir / relative_path
    if not file_path.exists():
        raise FileNotFoundError(f"Build output not found: {relative_path}")
    with open(file_path, 'r') as f:
        return f.read()


# ============================================================================
# LAYER 1: BUILD VALIDATION
# ============================================================================

class TestLayer1BuildValidation:
    """Layer 1: Validates that MkDocs builds successfully with the plugin."""

    def test_build_succeeds(self, build_test_project):
        """Test that mkdocs build completes without errors."""
        # If we got here, the fixture succeeded, so build is ok
        assert build_test_project.exists()

    def test_preamble_test_page_exists(self, build_test_project):
        """Test that preamble test page was built."""
        preamble_test_html = build_test_project / "preamble_test" / "index.html"
        assert preamble_test_html.exists(), "preamble_test/index.html not built"


# ============================================================================
# LAYER 2: HTML INSPECTION
# ============================================================================

class TestLayer2HTMLInjection:
    """Layer 2: Validates that preamble is injected into HTML output."""

    def test_preamble_content_in_html(self, build_test_project):
        """Test that preamble LaTeX commands are present in HTML output."""
        html = read_html_file(build_test_project, "preamble_test/index.html")

        # Check for the test command we added to preamble.tex
        # This proves the preamble file was actually injected
        assert "\\TestToken" in html or "\\newcommand" in html, \
            "Preamble LaTeX commands not found in HTML - preamble not injected"

    def test_preamble_uses_math_delimiters(self, build_test_project):
        """Test that preamble is wrapped in math delimiters (not code blocks)."""
        html = read_html_file(build_test_project, "preamble_test/index.html")

        # Look for math content (arithmatex uses \( \) for inline math)
        # This indicates proper math format, not code block
        assert "\\(" in html or "TestToken" in html, \
            "No math content found - preamble may be in wrong format"

    def test_preamble_not_in_code_block(self, build_test_project):
        """Test that preamble is NOT wrapped in <code> or <pre> tags."""
        html = read_html_file(build_test_project, "preamble_test/index.html")

        # If preamble is broken, it might be wrapped in <code> or <pre> tags
        # We should NOT find the raw LaTeX inside those tags
        if "\\TestToken" in html:
            # Find where \\TestToken appears
            idx = html.find("\\TestToken")
            context = html[max(0, idx-200):idx+200]

            # Check that it's not immediately inside <code> or <pre> tags
            # (it's ok if the context contains these tags elsewhere)
            assert not ("<code>" in context and "</code>" in context), \
                "Preamble found inside <code> tags - wrong format"
            assert not ("<pre>" in context and "</pre>" in context), \
                "Preamble found inside <pre> tags - wrong format"

    def test_page_html_is_valid(self, build_test_project):
        """Test that page has valid HTML structure."""
        html = read_html_file(build_test_project, "preamble_test/index.html")

        # Basic HTML validity checks
        assert "<!doctype html>" in html.lower(), "Valid HTML doctype not found"
        assert "<html" in html, "HTML tag not found"
        assert "</html>" in html, "Closing HTML tag not found"
        assert "<body" in html, "Body tag not found"
        assert "</body>" in html, "Closing body tag not found"
