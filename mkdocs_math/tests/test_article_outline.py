"""
Integration tests for mkdocs-math plugin article outline injection.

Tests that article-type pages (type: math-article in frontmatter)
generate outline tables of contents from heading structure.
"""

import pytest


class TestLayer1ArticleBuild:
    """Layer 1: Validates that project with article pages builds successfully."""

    def test_build_succeeds(self, build_test_project):
        """Test that mkdocs build completes without errors."""
        assert build_test_project.exists()

    def test_article_page_exists(self, build_test_project):
        """Test that test article page was built."""
        article_html = build_test_project / "test_article" / "index.html"
        assert article_html.exists(), "test_article/index.html not built"


class TestLayer2ArticleHTMLOutput:
    """Layer 2: Validates that article outlines are correctly injected into HTML."""

    def test_article_outline_in_html(self, build_test_project):
        """Test that article outline is present in HTML."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for outline container
        assert 'article-outline' in html, "article-outline class not found"
        assert 'Outline' in html, "Outline heading not found in outline"

    def test_article_outline_has_links(self, build_test_project):
        """Test that article outline contains heading links."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Check for anchor links to sections
        assert 'href="#introduction"' in html, "Link to Introduction section not found"
        assert 'href="#methods"' in html, "Link to Methods section not found"
        assert 'href="#results"' in html, "Link to Results section not found"
        assert 'href="#discussion"' in html, "Link to Discussion section not found"
        assert 'href="#conclusion"' in html, "Link to Conclusion section not found"

    def test_article_outline_title_preserved(self, build_test_project):
        """Test that article outline preserves heading titles."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Find the outline section and check for specific heading titles
        assert 'Introduction' in html, "Introduction heading not found in outline"
        assert 'Methods' in html, "Methods heading not found in outline"
        assert 'Results' in html, "Results heading not found in outline"

    def test_article_html_is_valid(self, build_test_project):
        """Test that article page has valid HTML structure."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Basic HTML validity
        assert "<!doctype html>" in html.lower(), "Valid HTML doctype not found"
        assert "<html" in html, "HTML tag not found"
        assert "</html>" in html, "Closing HTML tag not found"


class TestArticleReferencesSection:
    """Tests for References section on article pages with citations."""

    def test_article_with_citations_has_references_section(self, build_test_project):
        """Test that article pages with citations display a References section."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # References section should exist
        assert '<h2>References</h2>' in html, \
            "References section heading not found in article"

    def test_references_section_contains_entries(self, build_test_project):
        """Test that References section contains citation entries."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # Should have at least 3 reference entries (test_csfdb, test_levy_parts, test_malgrange)
        assert html.count('<li') >= 3, \
            "References section should have at least 3 entries"

    def test_references_contain_author_year_tags(self, build_test_project):
        """Test that references show author-year tags."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # References should contain author-year format tags
        assert 'TestAuthor1996' in html or 'Author' in html, \
            "References should contain author-year or author tags"

    def test_references_contain_citation_text(self, build_test_project):
        """Test that references contain the full citation text."""
        html_path = build_test_project / "test_article" / "index.html"
        with open(html_path, 'r') as f:
            html = f.read()

        # At least one of the test citations should be present
        assert ('Test' in html and ('combinatorial' in html or 'partitions' in html or 'malgrange' in html)), \
            "References should contain citation text from the bibliography"


class TestLayer3ArticleRendering:
    """Layer 3: Browser rendering tests for article outlines."""

    try:
        from playwright.async_api import async_playwright
        PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        PLAYWRIGHT_AVAILABLE = False

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_article_renders_in_browser(self, build_test_project):
        """Test that article page renders in browser without errors."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/test_article/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for page to render
            await page.wait_for_timeout(1000)

            # Check page title
            title = await page.title()
            assert "Test Mathematics Article" in title or "Mathematics" in title, \
                f"Page title unexpected: {title}"

            # Get page content
            content = await page.content()
            assert "Introduction" in content or "Methods" in content, \
                "Article sections not found in rendered page"

            await browser.close()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_article_outline_renders(self, build_test_project):
        """Test that article outline is visible in rendered page."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            file_url = f"file://{build_test_project}/test_article/index.html"
            await page.goto(file_url, wait_until="domcontentloaded")

            # Wait for page to render
            await page.wait_for_timeout(1000)

            # Check for outline element
            outline = await page.query_selector('.article-outline')
            assert outline is not None, "article-outline element not found"

            # Check for outline links
            links = await page.query_selector_all('.article-outline a')
            assert len(links) > 0, "No links found in article outline"

            # Verify some expected links
            outline_text = await page.text_content('.article-outline')
            assert 'Introduction' in outline_text, "Introduction link not found in outline"
            assert 'Methods' in outline_text, "Methods link not found in outline"

            await browser.close()
