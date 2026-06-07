"""
Browser-based rendering tests for mkdocs-math plugin preamble injection.

LAYER 3: Browser Rendering Validation

Uses Playwright to run a headless browser and validate that:
1. MathJax actually processes and renders the preamble
2. Math elements are rendered (mjx-container elements exist)
3. Preamble commands are properly available in math expressions
4. Rendering doesn't have subtle breakage

These tests render actual HTML pages in a real browser with JavaScript execution,
allowing us to detect rendering issues that pure HTML inspection cannot catch.

If Playwright is not installed or configured, these tests will be skipped
while Layer 1 and Layer 2 tests still run successfully.
"""

import pytest

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


pytestmark = pytest.mark.slow


class TestLayer3BrowserRendering:
    """Layer 3: Browser rendering tests with MathJax validation."""

    @pytest.mark.asyncio
    async def test_mathjax_renders_math_elements(self, build_test_project):
        """Test that MathJax has rendered math elements on the page.

        Validates that mjx-container elements exist, which proves MathJax
        has processed and rendered mathematical expressions.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/preamble_test/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for MathJax to render
            await page.wait_for_timeout(3000)

            # Count mjx-container elements (proof MathJax rendered)
            mjx_count = await page.evaluate(
                "document.querySelectorAll('mjx-container').length"
            )

            assert mjx_count > 0, \
                f"No mjx-container elements found ({mjx_count}). " \
                "MathJax did not render any math."

            await browser.close()

    @pytest.mark.asyncio
    async def test_preamble_commands_render_as_math(self, build_test_project):
        """Test that preamble-defined commands actually render via MathJax.

        The preamble defines \\newcommand{\\TestToken}{TEST}.
        The markdown uses $\\TestToken$ which should be processed.

        This test verifies that:
        1. MathJax containers exist (math was rendered)
        2. The raw LaTeX command \\TestToken is NOT in the final text
           (meaning it was processed by MathJax, not left as code)

        FAILURE MODE: If preamble is broken (rendered as code block),
        the \\TestToken will not be processed by MathJax and will appear
        as raw LaTeX text instead of being rendered.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/preamble_test/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for MathJax to process and render
            await page.wait_for_timeout(4000)

            # Get information about mjx-container elements
            mjx_containers = await page.evaluate(
                """
                Array.from(document.querySelectorAll('mjx-container')).map(el => ({
                    hasChildren: el.children.length > 0,
                    childTags: Array.from(el.children).map(c => c.tagName).join(','),
                    textContent: el.textContent,
                    ariaLabel: el.getAttribute('aria-label')
                }))
                """
            )

            assert len(mjx_containers) > 0, \
                "No mjx-container elements found. " \
                "MathJax did not render any math. " \
                "Check if preamble is in a code block instead of math."

            # Verify containers have actual content (rendered output)
            containers_with_content = [c for c in mjx_containers if c['hasChildren']]
            assert len(containers_with_content) > 0, \
                "mjx-container elements exist but are empty. " \
                "MathJax rendering may have failed or timed out."

            # Show what's in containers for debugging
            if mjx_containers:
                sample_container = mjx_containers[0]
                assert sample_container['childTags'], \
                    f"First mjx-container has no child tags: {sample_container}"

            # Get all arithmatex elements and their rendered content
            math_elements = await page.evaluate(
                """
                Array.from(document.querySelectorAll('.arithmatex')).map(el => ({
                    innerHTML: el.innerHTML,
                    textContent: el.textContent,
                    hasMjxChild: Array.from(el.querySelectorAll('mjx-container')).length > 0
                }))
                """
            )

            assert len(math_elements) > 0, "No .arithmatex elements found on page"

            # Verify at least one math element contains rendered output
            math_with_mjx = [m for m in math_elements if m['hasMjxChild']]
            assert len(math_with_mjx) > 0, \
                "No .arithmatex elements contain mjx-container. " \
                "MathJax rendering not found in math elements."

            # Check for raw LaTeX that shouldn't be there
            all_text = ' '.join([m['textContent'] for m in math_elements])

            # MathJax should have processed \\TestToken
            # If preamble failed, we'd see raw "\\TestToken" text instead
            assert "\\TestToken" not in all_text, \
                "Raw LaTeX command \\TestToken found in rendered text. " \
                "Preamble not processed by MathJax - it's being rendered as code."

            await browser.close()
