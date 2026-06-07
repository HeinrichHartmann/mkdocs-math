import time
import validators
import re
import json
from collections import OrderedDict
from pathlib import Path

from mkdocs.plugins import BasePlugin

from .citation import CitationBlock, Citation

from .config import BibTexConfig
from .registry import SimpleRegistry
from mkdocs.exceptions import ConfigurationError


from .utils import (
    tempfile_from_url,
    log,
    get_path_relative_to_mkdocs_yaml,
)


class BibTexPlugin(BasePlugin[BibTexConfig]):
    """
    Allows the use of bibtex in markdown content for MKDocs.
    """

    def __init__(self):
        self.bib_data = None
        self.all_references = OrderedDict()
        self.last_configured = None
        self.registry = None
        self.citation_index = {}  # {citation_key: {page_url, page_title}}
        self.cache_file = Path(".cache") / "citation_index.json"

    def on_startup(self, *, command, dirty):
        """Having on_startup() tells mkdocs to keep the plugin object upon rebuilds"""
        pass

    def _load_citation_index(self):
        """Load citation index from cache file (from previous build)."""
        if not self.cache_file.exists():
            log.debug(f"Citation index not found at {self.cache_file}")
            return {}

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Error loading citation index: {e}")
            return {}

    def _save_citation_index(self):
        """Save citation index to cache file after build completes."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.citation_index, f, indent=2)
            log.info(f"Citation index saved: {len(self.citation_index)} entries")
        except Exception as e:
            log.warning(f"Error saving citation index: {e}")

    def _track_citation(self, cite_key: str, page_url: str, page_title: str):
        """Track citation usage for a specific page. Call during page processing."""
        if cite_key not in self.citation_index:
            self.citation_index[cite_key] = {
                'pages': []
            }

        # Avoid duplicate entries for same page
        page_entry = {'url': page_url, 'title': page_title}
        if page_entry not in self.citation_index[cite_key]['pages']:
            self.citation_index[cite_key]['pages'].append(page_entry)

    def _parse_bibliography_directive(self, comment: str) -> dict:
        """
        Parse HTML comment directive to extract bibliography configuration.

        Example: <!-- bibliography mode=full style=table -->

        Returns:
            Dictionary with parsed parameters (e.g., {'mode': 'full', 'style': 'table'})
        """
        params = {}
        # Extract content between <!-- and -->
        content = comment.replace("<!--", "").replace("-->", "").strip()
        if content.startswith("bibliography"):
            # Remove 'bibliography' keyword
            attrs = content[11:].strip()
            # Parse key=value pairs
            for pair in attrs.split():
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    params[key.strip()] = value.strip()
        return params

    def _replace_bibliography_placeholders(self, markdown: str) -> str:
        """
        Replace HTML comment placeholders with generated bibliography.

        Handles: <!-- bibliography mode=full style=table -->
        """
        # Pattern to find bibliography directives
        pattern = re.compile(r'<!--\s*bibliography\s+([^-]*)\s*-->')

        def replace_bibliography(match: re.Match) -> str:
            comment = match.group(0)
            params = self._parse_bibliography_directive(comment)

            # Get mode and style from parameters
            mode = params.get("mode", "full")
            style = params.get("style", "list")

            if mode == "full":
                return self._generate_bibliography_markdown(style=style)
            else:
                log.warning(f"Unknown bibliography mode: {mode}")
                return ""

        result = pattern.sub(replace_bibliography, markdown)
        return result

    def _generate_bibliography_markdown(self, style: str = "list") -> str:
        """
        Generate markdown for a full bibliography with backlinks to pages that cite each reference.

        Args:
            style: The style to use for the bibliography ("list", "table", etc.)

        Returns:
            Markdown text for the bibliography with backlinks
        """
        if not self.registry or not self.citation_index:
            return ""

        bibliography_lines = []

        # Sort citations alphabetically by key for consistent output
        for cite_key in sorted(self.registry.bib_data.entries.keys()):
            try:
                # Get the formatted reference text
                citation = Citation(key=cite_key)
                reference_text = self.registry.reference_text(citation)

                # Get the citation tag for this reference (author-year format)
                citetag = self.registry.get_citetag(cite_key)

                # Get pages that cite this reference
                pages = self.citation_index.get(cite_key, {}).get('pages', [])

                # Format the bibliography entry with backlinks
                if style == "table":
                    # Table format: cite key | reference | pages
                    page_links = "; ".join(f"[{page['title']}]({page['url']})" for page in pages)
                    bibliography_lines.append(f"| {cite_key} | {reference_text} | {page_links} |")
                else:
                    # Default list format with citation tag and inline backlinks
                    if citetag:
                        # Use citation tag (author-year format) like [TestAuthor1996]
                        entry = f"[{citetag}] {reference_text}"
                    else:
                        # Fall back to cite key if no tag available
                        entry = f"[{cite_key}] {reference_text}"

                    # Add inline backlinks if pages cited this reference (keep on same line for wrapping)
                    if pages:
                        # Use page numbers (indices) for compact display with absolute links
                        page_links = ", ".join(f"[{i+1}](/{page['url']})" for i, page in enumerate(pages))
                        entry += f" — Used in: {page_links}"

                    bibliography_lines.append(entry)
            except Exception as e:
                log.warning("Error formatting bibliography entry %s: %s", cite_key, e)

        if not bibliography_lines:
            return ""

        # Add table header if using table style
        if style == "table":
            header = "| Citation Key | Reference | Used in Pages |\n|---|---|---|\n"
            return header + "\n".join(bibliography_lines)
        else:
            # Use double newlines between entries to ensure proper paragraph separation
            return "\n\n".join(bibliography_lines)

    def _preprocess_citation_tags(self, markdown: str) -> str:
        """
        Transform [@key] → [CiteTag][@key] when citetag field exists in bib entry.
        This runs before the main bibtex processing to add visual citation tags.
        """
        # Count citation patterns in input
        citation_count = len(re.findall(r'\[@([a-zA-Z0-9_:-]+)\]', markdown))

        if citation_count == 0 or not self.registry:
            return markdown

        # Pattern: [@citekey] (single citation only, no semicolons)
        pattern = re.compile(r'\[@([a-zA-Z0-9_:-]+)\]')

        replacements = 0

        def replace_citation(match: re.Match) -> str:
            nonlocal replacements
            cite_key = match.group(1)

            # Get citetag from registry if it exists
            citetag = self.registry.get_citetag(cite_key)
            if citetag:
                replacements += 1
                # Return: [CiteTag][@key]
                return f"[{citetag}][@{cite_key}]"

            # No citetag, return original
            return match.group(0)

        result = pattern.sub(replace_citation, markdown)

        if replacements > 0:
            log.info(f"Bibtex plugin: added {replacements} citation tags")

        return result

    def _link_citation_tags_early(self, markdown: str, footnote_ids: dict) -> str:
        """
        Link citation tags to their footnotes BEFORE bibtex processing.
        Transforms [CiteTag][@key] → [CiteTag](#fn:footnote_id)[@key]
        Uses pre-computed footnote_ids from footnote_format.
        """
        if not footnote_ids or not self.registry:
            return markdown

        # Pattern: [CiteTag][@key] where CiteTag is any non-bracket content
        pattern = re.compile(r'\[([^\[\]]+)\]\[@([a-zA-Z0-9_:-]+)\]')

        links_added = 0

        def replace_with_link(match: re.Match) -> str:
            nonlocal links_added
            citetag = match.group(1)
            cite_key = match.group(2)

            # Only link if this key has a footnote ID
            if cite_key in footnote_ids:
                links_added += 1
                footnote_id = footnote_ids[cite_key]
                # Return: [[CiteTag](#fn:footnote_id)][@key] - keeps brackets visible
                return f"[[{citetag}](#fn:{footnote_id})][@{cite_key}]"

            # No footnote for this key, return original
            return match.group(0)

        result = pattern.sub(replace_with_link, markdown)

        if links_added > 0:
            log.info(f"Bibtex plugin: linked {links_added} citation tags to footnotes")

        return result

    def on_config(self, config):
        """
        Loads bibliography on load of config
        """

        # Load citation index from previous build
        self.citation_index = self._load_citation_index()

        bibfiles = []

        # Set bib_file from either url or path
        if self.config.bib_file is not None:
            is_url = validators.url(self.config.bib_file)
            # if bib_file is a valid URL, cache it with tempfile
            if is_url:
                bibfiles.append(tempfile_from_url("bib file", self.config.bib_file, ".bib"))
            else:
                bib_file = get_path_relative_to_mkdocs_yaml(self.config.bib_file, config)
                bibfiles.append(bib_file)
        else:  # pragma: no cover
            raise ConfigurationError("Must supply a bibtex file for bibtex citations")

        # Skip rebuilding bib data if all files are older than the initial config
        if self.last_configured is not None:
            if all(Path(bibfile).stat().st_mtime < self.last_configured for bibfile in bibfiles):
                log.info("BibTexPlugin: No changes in bibfiles.")
                return config

        # Clear references on reconfig
        self.all_references = OrderedDict()

        if "{key}" not in self.config.footnote_format:
            raise ConfigurationError("Must include `{key}` placeholder in footnote_format")

        self.registry = SimpleRegistry(bib_files=bibfiles, footnote_format=self.config.footnote_format)
        log.info(f"BibTexPlugin configured with {len(bibfiles)} BibTeX file(s): {bibfiles}")

        self.last_configured = time.time()
        return config

    def on_page_markdown(self, markdown, page, config, files):
        """
        Parses the markdown for each page, extracting the bibtex references
        If a local reference list is requested, this will render that list where requested

        1. Preprocess citations: Transform [@key] → [CiteTag][@key] when citetag field exists
        2. Finds all cite keys (may include multiple citation references)
        3. Convert all cite keys to citation quads:
            (full cite key,
            individual cite key,
            citation key in corresponding style,
            citation for individual cite key)
        4. Insert formatted cite keys into text
        5. Insert the bibliography into the markdown
        6. Insert the full bibliograph into the markdown
        """

        # 1. Preprocess citations with citetags: [@key] → [CiteTag](#fn:key)[@key]
        markdown = self._preprocess_citation_tags(markdown)

        # Build footnote_ids map before bibtex processes citations
        # This allows us to link the citetags correctly
        footnote_ids = {}
        citation_keys = re.findall(r'@([a-zA-Z0-9_:-]+)\]', markdown)
        for key in citation_keys:
            footnote_id = self.registry.footnote_format.format(key=key)
            footnote_ids[key] = footnote_id

        # 1b. Link citation tags to their footnotes BEFORE bibtex processing
        markdown = self._link_citation_tags_early(markdown, footnote_ids)

        # 1c. Track all citations used on this page (for citation index)
        for key in citation_keys:
            self._track_citation(key, page.url, page.title)

        # 2. Find and validate all cite blocks in the markdown
        cite_blocks = CitationBlock.from_markdown(markdown)
        log.info(f"Found {len(cite_blocks)} citation blocks on {page.file.src_path}")
        self.registry.validate_citation_blocks(cite_blocks)

        # 3. Replace the cite blocks with the inline citations
        for block in cite_blocks:
            replacement = self.registry.inline_text(block)
            markdown = markdown.replace(str(block), replacement)

        # 3. Ensure we have a bibliography if desired
        bib_command = self.config.bib_command

        if self.config.bib_by_default and markdown.count(bib_command) == 0:
            markdown += f"\n{bib_command}"

        # 4. Insert in the bibliography text into the markdown
        citations = OrderedDict()
        for block in cite_blocks:
            for citation in block.citations:
                citations[citation.key] = citation

        bibliography = []
        for citation in citations.values():
            try:
                bibliography.append(
                    "[^{}]: {}".format(
                        self.registry.footnote_format.format(key=citation.key),
                        self.registry.reference_text(citation)
                    )
                )
            except Exception as e:
                log.warning("Error formatting citation %s into footnote format %s",
                            citation.key,
                            self.registry.footnote_format,
                            exc_info=e)
                # Add error marker for missing citation
                bibliography.append(
                    "[^{}]: ❌ Missing citation key: {}".format(
                        self.registry.footnote_format.format(key=citation.key),
                        citation.key
                    )
                )

        bibliography = "\n".join(bibliography)
        log.info(f"Generated bibliography with {len(citations)} unique citations for {page.file.src_path}")
        markdown = markdown.replace(bib_command, bibliography)

        # 5. Replace bibliography placeholders with generated bibliography
        markdown = self._replace_bibliography_placeholders(markdown)

        log.debug("Markdown: \n%s", markdown)

        return markdown

    def on_post_build(self, config):
        """Save citation index after build completes."""
        self._save_citation_index()
