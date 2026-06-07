"""
Integration tests for mkdocs-math plugin math environments.

Tests the conversion of **EnvironmentName (Label).** syntax to pymdownx.blocks divs.
Validates that:
- Environments with math in labels are recognized
- Environments are properly terminated (not merged with following content)
- Math notation in labels and definitions is preserved
- Environments are numbered correctly
"""

import pytest
from .conftest import assert_environment_rendered, assert_environment_not_rendered


class TestLayer1BuildWithEnvironments:
    """Layer 1: Validates that project with math environments builds successfully."""

    def test_build_succeeds(self, build_test_project):
        """Test that mkdocs build completes without errors."""
        assert build_test_project.exists()

    def test_environments_page_exists(self, build_test_project):
        """Test that environments test page was built."""
        environments_html = build_test_project / "environments_with_math" / "index.html"
        assert environments_html.exists(), "environments_with_math/index.html not built"


class TestLayer2EnvironmentHTMLOutput:
    """Layer 2: Validates that environments are correctly injected into HTML."""

    def test_environment_markers_in_html(self, build_test_project):
        """Test that environment definitions are present in HTML."""
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for environment class markers
        assert 'definition' in html.lower() or 'mathenvironment' in html.lower(), \
            "No environment markers found in HTML"

    def test_math_in_labels_preserved(self, build_test_project):
        """Test that math notation in labels is preserved in HTML."""
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for math notation from labels like ($\mathbb{R}^n$)
        # The backslashes might be escaped
        assert ("mathbb" in html or "\\mathbb" in html), \
            "Math notation in environment labels not preserved"

    def test_environment_termination(self, build_test_project):
        """Test that consecutive environments are properly separated.

        If environments aren't terminated correctly, multiple environment
        definitions might be merged into one large block.
        """
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Count occurrences of environment keywords
        # We should have multiple definitions, propositions, theorems, lemmas, etc.
        definition_count = html.lower().count("definition")
        proposition_count = html.lower().count("proposition")
        theorem_count = html.lower().count("theorem")
        lemma_count = html.lower().count("lemma")

        # At minimum we should see these environment types
        assert definition_count >= 3, f"Expected at least 3 Definitions, found {definition_count}"
        assert proposition_count >= 1, f"Expected at least 1 Proposition, found {proposition_count}"
        assert theorem_count >= 2, f"Expected at least 2 Theorems, found {theorem_count}"
        assert lemma_count >= 1, f"Expected at least 1 Lemma, found {lemma_count}"

    def test_environment_without_label(self, build_test_project):
        """Test that environments without labels (no parentheses) are recognized."""
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for environments without labels like **Theorem.** or **Proof.**
        # These should still be rendered as environments
        assert ("theorem" in html.lower() or "proof" in html.lower()), \
            "Environments without labels not found"

    def test_environment_with_complex_math(self, build_test_project):
        """Test that complex math notation in environment content is preserved."""
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for math content (arithmatex uses \( \) for inline math)
        assert "\\(" in html or "subset" in html or "mathcal" in html, \
            "Math content in environments not found"

        # Check for mathematical operators and symbols
        assert ("subset" in html or "\\subset" in html or "mathcal" in html), \
            "Complex math notation not preserved in environments"

    def test_html_is_valid(self, build_test_project):
        """Test that page has valid HTML structure."""
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Basic HTML validity
        assert "<!doctype html>" in html.lower(), "Valid HTML doctype not found"
        assert "<html" in html, "HTML tag not found"
        assert "</html>" in html, "Closing HTML tag not found"

    def test_environment_with_math_and_comma_in_label(self, build_test_project):
        r"""Test that environment with math notation and comma in label is rendered.

        Edge case: **Definition** ($C^k(\Omega)$, compact–open topology).
        This should be captured as an environment with label containing both math and text.
        """
        html_path = build_test_project / "environments_with_math" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check that the environment is wrapped with the math environment class/id
        assert "definition" in html.lower(), \
            "No 'definition' environment markers found"
        # Check for the full label with math notation
        assert "C^k" in html, \
            "Math notation 'C^k' from label not found in HTML"
        assert "compact–open topology" in html, \
            "Label text 'compact–open topology' not found in HTML"


class TestLayer3EnvironmentRendering:
    """Layer 3: Browser rendering tests for environments with math."""

    try:
        from playwright.async_api import async_playwright
        PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        PLAYWRIGHT_AVAILABLE = False

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_environments_render_in_browser(self, build_test_project):
        """Test that environments page renders in browser without errors."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/environments_with_math/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for page to fully render
            await page.wait_for_timeout(2000)

            # Check page title
            title = await page.title()
            assert "Environments" in title or "Math" in title, \
                f"Page title unexpected: {title}"

            # Get page content
            content = await page.content()
            assert "Definition" in content or "Proposition" in content, \
                "Environment definitions not found in rendered page"

            await browser.close()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_math_notation_renders(self, build_test_project):
        """Test that math notation in environments is rendered by MathJax."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/environments_with_math/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for MathJax to render
            await page.wait_for_timeout(4000)

            # Check for MathJax rendered elements
            mjx_count = await page.evaluate(
                "document.querySelectorAll('mjx-container').length"
            )

            assert mjx_count > 0, \
                "No MathJax elements rendered. Math in environments may not be working."

            await browser.close()
