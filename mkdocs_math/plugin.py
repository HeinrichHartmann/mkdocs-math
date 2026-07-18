"""
MkDocs plugin for mathematical typesetting and semantic environments.
"""

import logging
import re
import time
import json
import validators
import markdown as md
from collections import OrderedDict
from pathlib import Path
from mkdocs.plugins import BasePlugin
from mkdocs.config import config_options
from mkdocs.exceptions import ConfigurationError
from .environment_regex import parse_environments
from .citations.citation import CitationBlock
from .citations.registry import SimpleRegistry
from .citations.utils import (
    tempfile_from_url,
    get_path_relative_to_mkdocs_yaml,
)

log = logging.getLogger("mkdocs.plugins.math")


# Cache the preamble content to avoid reading file multiple times
_preamble_cache = None



def convert_theorem_environments(markdown: str, **kwargs) -> str:
    """
    Convert **EnvironmentName.** or **EnvironmentName (Label).** to pymdownx.blocks HTML divs.

    Matches: **Name.** or **Name (Label).** followed by content
    Terminates on: two blank lines, next environment header, markdown heading, or EOF

    Adds sequential numbering per page: Definition 1, Proposition 2, etc.
    Proof environments are unnumbered.

    Outputs pymdownx.blocks format:
        /// html | div
            attrs: {id: 'definition-1', class: 'definition mathenvironment'}
            **(1) Definition (Label).** content...
        ///
    """
    def slugify(text: str) -> str:
        """Convert text to valid HTML ID/CSS class name.
        - Lowercase
        - Replace spaces and special chars with hyphens
        - Remove consecutive hyphens
        - Strip leading/trailing hyphens
        """
        slug = text.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars except word chars, spaces, hyphens
        slug = re.sub(r'[\s-]+', '-', slug)   # Replace consecutive spaces/hyphens with single hyphen
        slug = slug.strip('-')                 # Remove leading/trailing hyphens
        return slug

    page = kwargs.get('page')

    def make_id(env_name: str, env_num: int, label: str | None = None) -> str:
        """Generate ID from environment name, number, and optional label."""
        env_slug = slugify(env_name)

        if label:
            label_slug = label.lower().strip()
            label_slug = re.sub(r'[^\w\s-]', '', label_slug)
            label_slug = re.sub(r'[-\s]+', '-', label_slug)
            return f"{env_slug}-{label_slug}"
        else:
            return f"{env_slug}-{env_num}"

    # Parse all environments
    environments = parse_environments(markdown)
    if not environments:
        return markdown

    # Pre-assign environment numbers in document order so numbering matches appearance.
    # Proof environments are not numbered and do not advance the counter.
    numbered_envs = []
    counter = 0
    for env_match in environments:
        env_name = env_match.env_name
        if env_name.lower() == "proof":
            numbered_envs.append((env_match, None))
        else:
            counter += 1
            numbered_envs.append((env_match, counter))

    # Build result by replacing from end to start (to avoid offset issues)
    result = markdown
    for env_match, env_num in reversed(numbered_envs):
        env_name = env_match.env_name
        label = env_match.label
        content = env_match.content

        # Check if content starts with {#custom-id} and extract it
        # Allow uppercase letters in custom IDs
        custom_id_match = re.match(r'^\s*\{#([a-zA-Z0-9:\-]+)\}', content)
        custom_id = custom_id_match.group(1) if custom_id_match else None

        # Remove {#custom-id} from content if present (it's just metadata for anchor registration)
        if custom_id:
            content = re.sub(r'^\s*\{#[a-zA-Z0-9:\-]+\}', '', content)

        env_class = slugify(env_name)
        # Proofs are not numbered and do not carry a number-based ID suffix
        if env_name.lower() == "proof":
            env_id = custom_id or make_id(env_name, 0, label)
        else:
            # Use custom ID if provided, otherwise generate from numbering
            env_id = custom_id or make_id(env_name, env_num, label)

        # Calculate number string for display
        if env_name.lower() == "proof" or env_num is None:
            number_str = None
        else:
            number_str = f"{env_num}"

        # Register custom ID with plugin's anchor registry
        plugin = kwargs.get('plugin')
        if custom_id and plugin:
            env_title = f"{env_name}"
            if label:
                env_title += f" ({label})"

            plugin.anchor_registry[custom_id] = {
                'title': env_title,
                'type': 'environment',
                'theme_id': env_id,
                'number': number_str,
                'env_name': env_name
            }

        attrs_parts = []
        if env_id:
            # Use double quotes for values to avoid YAML parsing issues with colons
            attrs_parts.append(f'id: "{env_id}"')
        # Use double quotes for class as well for consistency
        attrs_parts.append(f'class: "{env_class} mathenvironment"')
        attrs_str = "{" + ", ".join(attrs_parts) + "}"

        # Header: proofs are unnumbered, other environments get "(1.2.3) Name"
        # Format: **(1.2.3) Theorem** (Label).
        if number_str is None:
            header = f"**{env_name}**"
        else:
            header = f"**({number_str}) {env_name}**"

        # Add label outside bold
        if label:
            header += f" ({label})."
        else:
            header += "."

        # Wrap header in anchor link
        header = f"[{header}](#{env_id})"

        # Build replacement text
        # If env_id contains a colon, use raw HTML instead of pymdownx.blocks
        # to avoid YAML parsing issues in the attrs line
        if env_id and ':' in env_id:
            # Use raw HTML div tags to bypass pymdownx.blocks attrs parser
            # Add markdown="1" to enable markdown processing inside HTML
            replacement = f'<div id="{env_id}" class="{env_class} mathenvironment" markdown="1">\n\n{header}{content}\n\n</div>\n'
        else:
            # Use pymdownx.blocks syntax (cleaner for simple IDs)
            replacement = f'/// html | div\n    attrs: {attrs_str}\n{header}{content}\n///\n'

        # Replace in result string
        result = result[:env_match.start] + replacement + result[env_match.end:]

    return result


def inject_chapter_outline(markdown: str, **kwargs) -> str:
    """
    Inject an outline environment right after the first h1 heading.

    Scans the markdown for h1 and subsequent headings up to outline_depth.
    Can be disabled per-file via frontmatter: outline_enabled: false
    Can override depth per-file via frontmatter: outline_depth: 3

    Generates a pymdownx.blocks outline environment with anchor links.
    """
    page = kwargs.get('page')
    outline_enabled = True
    outline_depth = 2

    # Check frontmatter for overrides
    if page and hasattr(page, 'meta') and page.meta:
        meta = page.meta
        # Explicit per-page toggle
        if 'outline_enabled' in meta:
            outline_enabled = meta['outline_enabled']
        # Honor hide: [outline] convention used elsewhere
        hide = meta.get('hide', [])
        if isinstance(hide, list) and 'outline' in hide:
            outline_enabled = False
        if 'outline_depth' in meta:
            try:
                outline_depth = int(meta['outline_depth'])
                outline_depth = max(1, min(outline_depth, 6))
            except (ValueError, TypeError):
                log.warning(f"Invalid outline_depth in {page.file.src_path}: {meta['outline_depth']}")

    if not outline_enabled:
        return markdown

    lines = markdown.split('\n')
    h1_index = None
    sections = []

    # Find first h1 and collect headings up to outline_depth
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Find first h1
        if h1_index is None and stripped.startswith('# '):
            h1_index = i
            continue

        # After h1 found, collect headings (stop at next h1)
        if h1_index is not None:
            if stripped.startswith('# '):
                break

            # Check for headings up to outline_depth
            for level in range(2, outline_depth + 2):
                heading_marker = '#' * level + ' '
                if stripped.startswith(heading_marker):
                    title = stripped[level:].rstrip('#').strip()
                    sections.append((level, title))
                    break

    # Only inject outline if we found h1 and at least one heading
    if h1_index is None or not sections:
        return markdown

    # Generate outline as a bare environment header + list.
    # convert_theorem_environments will style it as a numbered environment.
    outline_lines = ['**Outline.**', '']

    for level, section in sections:
        # Calculate indentation based on heading level
        indent_level = level - 2
        indent = '    ' * indent_level

        # Generate anchor from section title
        anchor = section.lower()
        anchor = re.sub(r'[^\w\s-]', '', anchor)
        anchor = re.sub(r'[\s-]+', '-', anchor)
        anchor = anchor.strip('-')

        outline_lines.append(f"{indent}- [{section}](#{anchor})")

    outline_lines.append('')

    # Insert outline lines after the h1 heading
    for i, outline_line in enumerate(outline_lines):
        lines.insert(h1_index + 1 + i, outline_line)

    return '\n'.join(lines)


def inject_preamble_markdown(markdown: str, **kwargs) -> str:
    """
    Inject preamble file content plus any local preamble from frontmatter.

    Local preamble is defined in frontmatter (parsed by MkDocs 'meta' extension):
    ---
    math:
      preamble: |
        \\newcommand{\\Tr}{\\mathrm{Tr}}
    ---

    Preamble is injected as a hidden HTML div containing display math ($$...$$).
    The HTML div is block-level so it won't be wrapped in <p> tags by markdown processor.
    MathJax processes the math but the div is hidden from users via style="display:none".
    Inserts after the title line (if present) or at the beginning.

    Only injects if preamble_file is configured in the plugin settings.
    """
    global _preamble_cache

    page = kwargs.get('page')
    preamble_file = kwargs.get('preamble_file', '')

    # Only proceed if preamble_file is configured
    if not preamble_file:
        return markdown

    # Read global preamble file once and cache it
    if _preamble_cache is None:
        try:
            with open(preamble_file, 'r', encoding='utf-8') as f:
                preamble_content = f.read()
            _preamble_cache = preamble_content
            log.info(f"Loaded preamble from {preamble_file} ({len(preamble_content)} chars)")
        except FileNotFoundError:
            log.debug(f"Preamble file not found at {preamble_file}")
            _preamble_cache = ""
            return markdown

    # Collect preamble parts
    preamble_parts = []

    # Add global preamble
    if _preamble_cache:
        preamble_parts.append(_preamble_cache)

    # Add local preamble from frontmatter
    if page and page.meta:
        if isinstance(page.meta.get('math'), dict):
            if 'preamble' in page.meta['math']:
                math_preamble = page.meta['math']['preamble']
                if math_preamble:
                    preamble_parts.append(str(math_preamble))
        elif 'preamble' in page.meta:
            # Fallback for direct preamble field (old format)
            preamble = page.meta.get('preamble')
            if preamble:
                preamble_parts.append(str(preamble))

    if not preamble_parts:
        return markdown

    combined_preamble = '\n'.join(preamble_parts)

    # Create HTML div for preamble injection
    # The div is block-level and won't be wrapped in <p> tags by markdown processor
    # style="display:none" hides it from users
    # class="arithmatex" signals to MathJax to process the math
    # $$...$ contains the LaTeX preamble commands
    preamble_div = f'''<div class="arithmatex" style="display:none">
$$
{combined_preamble}
$$
</div>

'''

    # Split markdown into lines to find insertion point
    lines = markdown.split('\n')

    # Find first non-empty line
    insert_pos = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            # If first non-empty line is a heading, insert after it
            if stripped.startswith('#'):
                insert_pos = i + 1
            break

    # Insert preamble div as a single HTML element at the determined position
    lines.insert(insert_pos, preamble_div)

    return '\n'.join(lines)


class Plugin(BasePlugin):
    """
    A MkDocs plugin for mathematical typesetting and semantic environments.

    Configuration options:
    - proofs: Settings for proof environments
    - environments: Settings for theorem environments
    - preamble: Global LaTeX preamble
    """

    config_scheme = (
        ("preamble_file", config_options.Type(str, default="docs/preamble.tex")),
        ("outline_enabled", config_options.Type(bool, default=True)),
        ("outline_depth", config_options.Type(int, default=2)),
        ("bib_file", config_options.Optional(config_options.Type(str))),
        ("bib_command", config_options.Type(str, default="\\bibliography")),
        ("bib_by_default", config_options.Type(bool, default=True)),
        ("footnote_format", config_options.Type(str, default="{key}")),
    )

    def __init__(self):
        """Initialize plugin state."""
        super().__init__()
        self.registry = None
        self.last_configured = None
        self.all_references = OrderedDict()
        self.citation_index = {}
        self.citation_cache_file = Path(".cache") / "citation_index.json"
        # Anchor registry: {anchor_id: {title, type, theme_id, number, env_name}}
        self.anchor_registry = {}
        self.anchor_cache_file = Path(".cache") / "anchor_registry.json"

    def on_startup(self, *, command, dirty):
        """Having on_startup() tells mkdocs to keep the plugin object upon rebuilds."""
        global _preamble_cache
        _preamble_cache = None  # Invalidate so preamble is re-read on each build

    def on_config(self, config):
        """Initialize plugin configuration, including citation registry if bib_file is configured."""
        log.info("mkdocs-math plugin initialized")
        log.debug(f"Config: proofs={self.config.get('proofs')}, environments={self.config.get('environments')}")

        # Register plugin's template directory so main.html is found by mkdocs
        templates_dir = str(Path(__file__).parent / "templates")
        if templates_dir not in config['theme'].dirs:
            config['theme'].dirs.insert(0, templates_dir)

        # Load caches from disk
        self.citation_index = self._load_citation_index()
        self.anchor_registry = self._load_anchor_cache()

        # Initialize citation registry if bib_file is configured
        if self.config.get('bib_file'):
            bibfiles = []
            bib_file = self.config.get('bib_file')
            is_url = validators.url(bib_file)

            if is_url:
                bibfiles.append(tempfile_from_url("bib file", bib_file, ".bib"))
            else:
                bib_file_path = get_path_relative_to_mkdocs_yaml(bib_file, config)
                bibfiles.append(bib_file_path)

            # Skip rebuilding if files haven't changed
            if self.last_configured is not None:
                if all(Path(bibfile).stat().st_mtime < self.last_configured for bibfile in bibfiles):
                    log.info("BibTexPlugin: No changes in bibfiles.")
                    return config

            # Validate footnote_format
            if "{key}" not in self.config.get('footnote_format', '{key}'):
                raise ConfigurationError("Must include `{key}` placeholder in footnote_format")

            self.registry = SimpleRegistry(
                bib_files=bibfiles,
                footnote_format=self.config.get('footnote_format', '{key}')
            )
            log.info(f"Citation registry initialized with {len(bibfiles)} BibTeX file(s): {bibfiles}")
            self.last_configured = time.time()

        return config

    def on_post_build(self, config):
        """Called after the build process."""
        log.info("mkdocs-math build complete")
        # Save caches after build completes
        self._save_citation_index()
        self._save_anchor_cache()

    def _generate_article_listing(self, markdown, page, files):
        """Generate arxiv-style article listing for article-index pages.

        Scans all files for math-article pages, collects frontmatter,
        and appends a listing sorted by date (newest first).
        """
        import yaml

        articles = []
        for f in files:
            if not f.src_path.endswith('.md'):
                continue
            # Only scan direct children, not subdirectories
            import os
            parent = os.path.dirname(f.src_path)
            if os.path.dirname(parent):
                # More than one level deep from docs root — skip
                # We want "200 Articles/foo.md" but not "200 Articles/foo.d/bar.md"
                parts = f.src_path.replace('\\', '/').split('/')
                if len(parts) > 2:
                    continue
            try:
                content = Path(f.abs_src_path).read_text(encoding='utf-8')
            except Exception:
                continue
            if not content.startswith('---'):
                continue
            # Parse frontmatter
            end = content.find('\n---', 3)
            if end == -1:
                continue
            try:
                meta = yaml.safe_load(content[3:end])
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            if meta.get('type') != 'math-article':
                continue
            # Compute relative URL from the index page to this article
            from posixpath import relpath as posix_relpath
            rel_url = posix_relpath(f.url, start=page.file.url.rsplit('/', 1)[0] if '/' in page.file.url else '')
            # Check if a .d/ notes folder exists
            src_stem = Path(f.abs_src_path).stem
            src_dir = Path(f.abs_src_path).parent
            notes_dir = None
            for d in src_dir.iterdir():
                if d.is_dir() and d.name.startswith(src_stem) and d.name.endswith('.d'):
                    # Build notes URL relative to the listing page, using the article's parent dir
                    article_parent = f.src_path.rsplit('/', 1)[0] if '/' in f.src_path else ''
                    notes_src = article_parent + '/' + d.name + '/' if article_parent else d.name + '/'
                    notes_dir = posix_relpath(notes_src, start=page.file.url.rsplit('/', 1)[0] if '/' in page.file.url else '')
                    break
            articles.append({
                'title': meta.get('title', 'Untitled'),
                'date': str(meta.get('date', '')),
                'doi': meta.get('doi', ''),
                'abstract': meta.get('abstract', '').strip(),
                'author': meta.get('author', ''),
                'url': rel_url,
                'tagline': meta.get('tagline', ''),
                'publications': meta.get('publications', {}),
                'status': meta.get('status', '900 Uncategorized'),
                'notes_dir': notes_dir,
            })

        # Group by status, sort groups lexicographically (numeric prefix gives order)
        from collections import defaultdict
        groups = defaultdict(list)
        for art in articles:
            groups[art['status']].append(art)

        # Sort each group by date descending
        for arts in groups.values():
            arts.sort(key=lambda a: a['date'], reverse=True)

        # Sort status keys lexicographically
        sorted_statuses = sorted(groups.keys())

        # Strip numeric prefix for display: "100 Published" -> "Published"
        import re
        def strip_prefix(status):
            return re.sub(r'^\d+\s+', '', status)

        # Generate listing with status headers
        lines = []
        for status in sorted_statuses:
            display_status = strip_prefix(status)
            lines.append(f'**{display_status}**')
            lines.append('')
            for art in groups[status]:
                year = art['date'][:4] if art['date'] else ''
                parts = [f'**[{art["title"]}]({art["url"]})** ({year})']
                if art.get('notes_dir'):
                    parts.append(f'[notes]({art["notes_dir"]})')
                if art['doi']:
                    parts.append(f'[DOI](https://doi.org/{art["doi"]})')
                for name, url in (art.get('publications') or {}).items():
                    parts.append(f'[{name}]({url})')
                line = ' · '.join(parts)
                if art.get('tagline'):
                    line += '<br>\n  *' + art['tagline'] + '*'
                lines.append(f'- {line}')
            lines.append('')

        listing = '\n'.join(lines)

        # {{FLAT_ARTICLES}}: chronological list without status headers
        flat_lines = []
        all_articles = sorted(
            [a for group in groups.values() for a in group],
            key=lambda a: a['date'], reverse=True
        )
        for art in all_articles:
            year = art['date'][:4] if art['date'] else ''
            parts = [f'**[{art["title"]}]({art["url"]})** ({year})']
            if art.get('notes_dir'):
                parts.append(f'[notes]({art["notes_dir"]})')
            if art['doi']:
                parts.append(f'[DOI](https://doi.org/{art["doi"]})')
            for name, url in (art.get('publications') or {}).items():
                parts.append(f'[{name}]({url})')
            line = ' · '.join(parts)
            if art.get('tagline'):
                line += '<br>\n  *' + art['tagline'] + '*'
            flat_lines.append(f'- {line}')
            flat_lines.append('')
        flat_listing = '\n'.join(flat_lines)

        if '{{FLAT_ARTICLES}}' in markdown:
            markdown = markdown.replace('{{FLAT_ARTICLES}}', flat_listing)
        if '{{ARTICLES}}' in markdown:
            markdown = markdown.replace('{{ARTICLES}}', listing)
            return markdown
        return markdown

    def on_page_markdown(self, markdown, page, config, files):
        """Process markdown for each page."""
        # Store original markdown for outline extraction (before any modifications)
        page.math_original_markdown = markdown

        # Generate article listing for index pages
        if getattr(page, 'meta', {}).get('type') == 'article-index':
            markdown = self._generate_article_listing(markdown, page, files)

        # Register heading anchors first (before processing references)
        self._register_heading_anchors(markdown, page)

        # Process citations first (before theorem environments)
        markdown = self._process_citations(markdown, page)

        # Inject outline (configurable via outline_enabled and outline_depth)
        markdown = inject_chapter_outline(markdown, page=page, config=config)

        # Strip print-only blocks, keep web blocks
        from .preprocess_pandoc import strip_target_blocks
        markdown = strip_target_blocks(markdown, keep='web')

        # Inject preamble (using configured preamble_file, resolved relative to mkdocs.yml)
        preamble_file = self.config.get('preamble_file', '')
        if preamble_file:
            preamble_file = str(get_path_relative_to_mkdocs_yaml(preamble_file, config))
        markdown = inject_preamble_markdown(markdown, page=page, config=config, preamble_file=preamble_file)

        # Convert theorem environments (registers anchors with their numbers)
        markdown = convert_theorem_environments(markdown, page=page, config=config, plugin=self)

        # Resolve anchor references [#...] to numbered links
        markdown = self._resolve_anchor_references(markdown)


        return markdown

    def on_env(self, env, config, files):
        """Register custom Jinja filters."""
        def markdown_filter(text):
            return md.markdown(text, extensions=['pymdownx.arithmatex'], extension_configs={'pymdownx.arithmatex': {'generic': True}})
        env.filters['markdown'] = markdown_filter
        return env

    def on_page_context(self, context, page, config, nav):
        """Inject outline and references data into template context for article pages."""
        # Only process article-type pages
        if page.meta.get('type') != 'math-article':
            return context

        # Add references to template context if they were collected
        if hasattr(page, 'math_references'):
            context['math_references'] = page.math_references

        # Check if outline is enabled (default True, can be overridden per-file)
        # Support both outline_enabled: false and hide: [outline] conventions
        outline_enabled = page.meta.get('outline_enabled', True)
        hide_list = page.meta.get('hide', [])
        if not outline_enabled or (isinstance(hide_list, list) and 'outline' in hide_list):
            return context

        # Get outline depth (default 2, can be overridden per-file)
        outline_depth = page.meta.get('outline_depth', 2)
        try:
            outline_depth = int(outline_depth)
            outline_depth = max(1, min(outline_depth, 6))
        except (ValueError, TypeError):
            outline_depth = 2

        # Extract outline from the rendered HTML content (page.content is available here)
        outline = self._extract_outline_from_content(page.content, outline_depth)

        if outline:
            context['math_outline'] = outline

        return context

    def _extract_outline_from_content(self, html_content: str, max_depth: int) -> list:
        """Extract heading structure from HTML content to build outline.

        Returns list of dicts with 'level', 'title', and 'id' keys.
        Filters to headings h2 and below (h1 is the article title).
        """
        import re

        outline = []
        # Match heading tags: <h2 id="...">Title</h2>, etc.
        pattern = re.compile(r'<h([2-6])\s+id="([^"]+)">([^<]+)</h\1>', re.IGNORECASE)

        for match in pattern.finditer(html_content):
            level = int(match.group(1))
            heading_id = match.group(2)
            title = match.group(3)

            # Strip any HTML tags from title
            title = re.sub(r'<[^>]+>', '', title)

            if level - 2 <= max_depth:  # level 2 = depth 1, level 3 = depth 2, etc.
                outline.append({
                    'level': level,
                    'title': title,
                    'id': heading_id,
                })

        return outline

    def _load_citation_index(self):
        """Load citation index from cache file (from previous build)."""
        if not self.citation_cache_file.exists():
            log.debug(f"Citation index not found at {self.citation_cache_file}")
            return {}

        try:
            with open(self.citation_cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Error loading citation index: {e}")
            return {}

    def _save_citation_index(self):
        """Save citation index to cache file after build completes."""
        self.citation_cache_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.citation_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.citation_index, f, indent=2)
            log.info(f"Citation index saved: {len(self.citation_index)} entries")
        except Exception as e:
            log.warning(f"Error saving citation index: {e}")

    def _load_anchor_cache(self):
        """Load anchor registry from cache file (from previous build)."""
        if not self.anchor_cache_file.exists():
            log.debug(f"Anchor cache not found at {self.anchor_cache_file}")
            return {}

        try:
            with open(self.anchor_cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Error loading anchor cache: {e}")
            return {}

    def _save_anchor_cache(self):
        """Save anchor registry to cache file after build completes."""
        self.anchor_cache_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.anchor_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.anchor_registry, f, indent=2)
            log.info(f"Anchor registry saved: {len(self.anchor_registry)} anchors")
        except Exception as e:
            log.warning(f"Error saving anchor cache: {e}")

    def _register_heading_anchors(self, markdown: str, page) -> None:
        """Register heading anchors with custom IDs {#...} in the anchor registry.

        Headings use attr_list extension: ## Title {#custom-id}
        The custom ID becomes the element ID directly.
        """
        # Pattern: heading (1-6 #'s) + text + {#custom-id}
        pattern = re.compile(
            r'^(#{1,6})\s+(.+?)\s+\{#([a-zA-Z0-9:\-]+)\}\s*$',
            re.MULTILINE
        )

        for match in pattern.finditer(markdown):
            heading_text = match.group(2).strip()
            custom_id = match.group(3)

            # For headings, the custom ID is used directly as the element ID
            self.anchor_registry[custom_id] = {
                'title': heading_text,
                'type': 'heading',
                'theme_id': custom_id,
                'number': None,  # Headings don't have numbers
                'env_name': None
            }

    def _resolve_anchor_references(self, markdown: str) -> str:
        """Resolve [#anchor-id] references to numbered links with chain icon.

        Converts:
        - [#HKF] → [(12) 🔗](#HKF) if anchor HKF is environment with number 12
        - [#HKF] → [Definition (Heat kernel) 🔗](#HKF) if no number
        - [#HKF] → [❌](#HKF) if anchor not found
        """
        # Pattern: [#anchor-id] (allow uppercase in IDs)
        pattern = re.compile(r'\[#([a-zA-Z0-9:\-]+)\]')

        def resolve_ref(match: re.Match) -> str:
            anchor_id = match.group(1)

            # Look up the anchor in registry
            if anchor_id in self.anchor_registry:
                entry = self.anchor_registry[anchor_id]
                target_id = entry.get('theme_id', anchor_id)
                env_name = entry.get('env_name', '')
                number = entry.get('number')

                # Format link text based on what we have
                if number:
                    # Show only number with parentheses and icon (like LaTeX \ref), not environment type
                    link_text = f"({number}) 🔗"
                else:
                    link_text = f"{entry.get('title', anchor_id)} 🔗"

                return f"[{link_text}](#{target_id})"
            else:
                # Anchor not found - keep broken chain icon to stand out
                return f"[❌](#{anchor_id})"

        return pattern.sub(resolve_ref, markdown)

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
        """Parse HTML comment directive to extract bibliography configuration."""
        params = {}
        content = comment.replace("<!--", "").replace("-->", "").strip()
        if content.startswith("bibliography"):
            attrs = content[11:].strip()
            for pair in attrs.split():
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    params[key.strip()] = value.strip()
        return params

    def _replace_bibliography_placeholders(self, markdown: str) -> str:
        """Replace bibliography directive placeholders with generated bibliography."""
        if not self.registry:
            return markdown

        # Find all bibliography directives and remove them for now.
        # Global bibliography generation is handled by the vendored citations plugin.
        pattern = r'<!--\s*bibliography[^>]*-->'
        directives = re.findall(pattern, markdown)

        for directive in directives:
            # For now, we just replace with empty since we handle it via bib_command
            markdown = markdown.replace(directive, '')

        return markdown

    def _link_citation_tags_to_references(self, markdown: str) -> str:
        """
        Link citation tags to the References section.

        After _preprocess_citation_tags has transformed [@key] → [CiteTag][@key],
        rewrite these patterns as [[CiteTag](#ref-key)][@key] so that the visible
        citation tag links directly to the corresponding entry in the References
        section (<li id="ref-key">…</li> in overrides/main.html).
        """
        if not self.registry:
            return markdown

        # Match patterns of the form [CiteTag][@key]
        pattern = re.compile(r'\[([^\[\]]+)\]\[@([a-zA-Z0-9_:-]+)\]')

        def replace_with_link(match: re.Match) -> str:
            citetag = match.group(1)
            cite_key = match.group(2)
            # Link tag text to the reference list entry id="ref-{key}"
            return f"[[{citetag}](#ref-{cite_key})][@{cite_key}]"

        return pattern.sub(replace_with_link, markdown)

    def _preprocess_citation_tags(self, markdown: str) -> str:
        """
        Transform [@key] → [CiteTag][@key] when citetag field exists in bib entry.
        This runs before the main citation processing to add visual citation tags.
        """
        if not self.registry:
            return markdown

        # Count citation patterns in input
        citation_count = len(re.findall(r'\[@([a-zA-Z0-9_:-]+)\]', markdown))

        if citation_count == 0:
            return markdown

        # Pattern: [@citekey] or [@citekey, locator text]
        pattern = re.compile(r'\[@([a-zA-Z0-9_:-]+)(?:,\s*([^\]]+))?\]')

        replacements = 0

        def replace_citation(match: re.Match) -> str:
            nonlocal replacements
            cite_key = match.group(1)
            locator = match.group(2)

            # Get citetag from registry if it exists
            citetag = self.registry.get_citetag(cite_key)
            if citetag:
                replacements += 1
                # Append locator to the visible tag: [CiteTag, Theorem 2.3][@key]
                if locator:
                    return f"[{citetag}, {locator.strip()}][@{cite_key}]"
                return f"[{citetag}][@{cite_key}]"

            # No citetag, return original
            return match.group(0)

        result = pattern.sub(replace_citation, markdown)

        if replacements > 0:
            log.info(f"Math plugin: added {replacements} citation tags")

        return result

    def _process_citations(self, markdown: str, page) -> str:
        """Process citations in markdown if registry is configured."""
        if not self.registry:
            return markdown

        is_article = getattr(page, "meta", {}).get("type") == "math-article"

        # Step 1: Preprocess citations with citetags: [@key] → [CiteTag][@key]
        markdown = self._preprocess_citation_tags(markdown)

        # Step 1b: For article pages, link citation tags to the References section.
        # This converts [CiteTag][@key] to [[CiteTag](#ref-key)][@key],
        # matching the <li id="ref-key"> anchors used in overrides/main.html.
        if is_article:
            markdown = self._link_citation_tags_to_references(markdown)

        # Extract citation keys for tracking
        citation_keys = re.findall(r'@([a-zA-Z0-9_:-]+)\]', markdown)
        for key in citation_keys:
            self._track_citation(key, page.url, page.title)

        # Find and validate citation blocks
        cite_blocks = CitationBlock.from_markdown(markdown)
        log.info(f"Found {len(cite_blocks)} citation blocks on {page.file.src_path}")
        self.registry.validate_citation_blocks(cite_blocks)

        # Replace citation blocks with footnote markers (non-article pages)
        # or remove them (article pages) since we use inline citetags + References section.
        for block in cite_blocks:
            if is_article:
                # Drop [@key] blocks; the visible [CiteTag](#ref-key) link
                # was already injected by _preprocess_citation_tags + _link_citation_tags_to_references.
                replacement = ""
            else:
                replacement = self.registry.inline_text(block)
            markdown = markdown.replace(str(block), replacement)

        # Ensure we have a bibliography section for non-article pages
        bib_command = self.config.get('bib_command', '\\bibliography')
        if (not is_article) and self.config.get('bib_by_default', True) and markdown.count(bib_command) == 0:
            markdown += f"\n{bib_command}"

        # Collect all citations
        citations = OrderedDict()
        for block in cite_blocks:
            for citation in block.citations:
                citations[citation.key] = citation

        # Generate bibliography footnote definitions for non-article pages
        bibliography = []
        for citation in citations.values():
            try:
                if not is_article:
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
                if not is_article:
                    bibliography.append(
                        "[^{}]: ❌ Missing citation key: {}".format(
                            self.registry.footnote_format.format(key=citation.key),
                            citation.key
                        )
                    )

        if not is_article:
            bibliography_text = "\n".join(bibliography)
            log.info(f"Generated bibliography with {len(citations)} unique citations for {page.file.src_path}")
            markdown = markdown.replace(bib_command, bibliography_text)

        # Replace bibliography placeholders
        markdown = self._replace_bibliography_placeholders(markdown)

        # Store citations for article pages (to be used in template for References section)
        if page.meta.get('type') == 'math-article' and len(citations) > 0:
            references = []
            for citation in citations.values():
                try:
                    citetag = self.registry.get_citetag(citation.key)
                    ref_text = self.registry.reference_text(citation)
                    # Convert Markdown-formatted reference text to inline HTML
                    # so that titles and links render correctly in the template.
                    ref_html = md.markdown(ref_text)
                    if ref_html.startswith("<p>") and ref_html.endswith("</p>"):
                        ref_html = ref_html[3:-4]
                    references.append({
                        'key': citation.key,
                        'citetag': citetag or citation.key,
                        'text': ref_html
                    })
                except Exception as e:
                    log.warning(f"Error formatting reference for {citation.key}: {e}")

            page.math_references = references
            log.info(f"Stored {len(references)} references for article page")

        return markdown
