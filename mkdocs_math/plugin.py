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
from .elements import (
    build_registry as build_elements_registry,
    build_nav_sections,
    registry_to_json,
    compute_backlinks,
    resolve_notation_chain,
    KIND_ABBREV,
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
        ("elements_dir", config_options.Type(str, default="Elements")),
        ("lean_url", config_options.Type(str, default="")),  # deprecated, use validation_url
        ("validation_url", config_options.Type(str, default="")),
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
        # Elements registry: id -> ElementNode
        self.elements_registry = {}
        self.elements_backlinks = {}
        self.elements_dir_path = None

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

        # Inject proofs.js for collapsible proof environments
        proofs_js_src = Path(__file__).parent / "proofs.js"
        if proofs_js_src.exists():
            docs_js_dir = Path(config['docs_dir']) / 'javascript'
            docs_js_dir.mkdir(parents=True, exist_ok=True)
            dest = docs_js_dir / 'mkdocs-math-proofs.js'
            if not dest.exists() or dest.read_bytes() != proofs_js_src.read_bytes():
                import shutil
                shutil.copy2(proofs_js_src, dest)
            js_path = 'javascript/mkdocs-math-proofs.js'
            if js_path not in config.get('extra_javascript', []):
                config.setdefault('extra_javascript', []).append(js_path)

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

    def on_files(self, files, config):
        """Build elements registry from the elements directory."""
        elements_dir_name = self.config.get('elements_dir', 'Elements')
        docs_dir = Path(config['docs_dir'])
        elements_dir = docs_dir / elements_dir_name

        if not elements_dir.exists():
            log.debug(f"Elements directory not found: {elements_dir}")
            return files

        self.elements_dir_path = elements_dir
        self.elements_registry = build_elements_registry(elements_dir, docs_dir)
        self.elements_backlinks = compute_backlinks(self.elements_registry)
        self._files = files

        # ID-based permalinks: remap node destinations to <elements_dir>/<ID>/
        # (decoupled from file location and title; see adr/2026-07-19-plugin-site-boundary.md)
        for node in self.elements_registry.values():
            f = files.get_file_from_path(node.src_path)
            if f is None:
                log.warning(f"Elements: no file object for {node.src_path}")
                continue
            if config['use_directory_urls']:
                f.dest_uri = f'{elements_dir_name}/{node.id}/index.html'
            else:
                f.dest_uri = f'{elements_dir_name}/{node.id}.html'
            # Invalidate cached properties derived from dest_uri
            f.__dict__.pop('url', None)
            f.__dict__.pop('abs_dest_path', None)
            node.url = f.url

        # Generate virtual index pages for each Elements subdirectory
        from mkdocs.structure.files import File as MkDocsFile
        seen_dirs = set()
        for node in self.elements_registry.values():
            if not node.live:
                continue
            parts = Path(node.src_path).parts
            for depth in range(0, min(len(parts), 6)):
                dir_path = '/'.join(parts[:depth + 1])
                if dir_path != node.src_path:
                    seen_dirs.add(dir_path)

        self._section_index_files = {}
        for dir_path in sorted(seen_dirs):
            src_uri = f'{dir_path}/index.md'
            if files.get_file_from_path(src_uri):
                continue  # don't overwrite hand-written index.md
            section_name = re.sub(r'^\d+\s+', '', Path(dir_path).name)
            stub = f'---\noutline_enabled: false\n---\n# {section_name}\n'
            f = MkDocsFile.generated(config, src_uri, content=stub)
            files.append(f)
            self._section_index_files[src_uri] = dir_path

        log.info(f"Elements registry: {len(self.elements_registry)} nodes, "
                 f"{len(self._section_index_files)} index pages")
        return files

    def on_post_build(self, config):
        """Called after the build process."""
        log.info("mkdocs-math build complete")
        # Save caches after build completes
        self._save_citation_index()
        self._save_anchor_cache()
        # Write elements/index.json if registry is non-empty
        if self.elements_registry:
            self._write_elements_index(config)

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
                'url': meta.get('link') or rel_url,
                'description': meta.get('description', '') or meta.get('tagline', ''),
                'publications': meta.get('publications', {}),
                'status': meta.get('status', '900 Uncategorized'),
                'target': meta.get('target', ''),
                'notes_dir': notes_dir,
            })

        # Group by status, sort groups lexicographically (numeric prefix gives order)
        from collections import defaultdict
        groups = defaultdict(list)
        for art in articles:
            groups[art['status']].append(art)

        # Sort: shipped groups (9xx: Published/Parked) by date descending
        # (recency); queued groups (Active/Next/Later) ascending — planned
        # reading/writing order.
        for status, arts in groups.items():
            arts.sort(key=lambda a: a['date'], reverse=status.startswith('9'))

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
                if art.get('target'):
                    parts.append(f'<span class="article-target article-target-{art["target"]}">{art["target"]}</span>')
                if art.get('notes_dir'):
                    parts.append(f'[notes]({art["notes_dir"]})')
                if art['doi']:
                    parts.append(f'[DOI](https://doi.org/{art["doi"]})')
                for name, url in (art.get('publications') or {}).items():
                    parts.append(f'[{name}]({url})')
                line = ' · '.join(parts)
                if art.get('description'):
                    line += '<br>\n  *' + art['description'] + '*'
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
            if art.get('description'):
                line += '<br>\n  *' + art['description'] + '*'
            flat_lines.append(f'- {line}')
            flat_lines.append('')
        flat_listing = '\n'.join(flat_lines)

        if '{{FLAT_ARTICLES}}' in markdown:
            markdown = markdown.replace('{{FLAT_ARTICLES}}', flat_listing)
        if '{{ARTICLES}}' in markdown:
            markdown = markdown.replace('{{ARTICLES}}', listing)
            return markdown
        return markdown

    @staticmethod
    def _node_attr(node, key, default=None):
        """Get attribute from ElementNode or dict."""
        if isinstance(node, dict):
            return node.get(key, default)
        return getattr(node, key, default)

    def _render_node_list_item(self, node, page=None) -> str:
        """Render a single node as an HTML list item with styled pills."""
        nid = self._node_attr(node, 'id', '')
        title = self._node_attr(node, 'title', '')
        kind = self._node_attr(node, 'kind', '')
        if kind == 'environment':
            kind = 'notation'
        abbrev = KIND_ABBREV.get(kind, kind).upper()
        validation = self._node_attr(node, 'validation', {}) or {}
        published = self._node_attr(node, 'published_at', []) or []

        # Resolve link URL from registry
        href = ''
        reg_node = self.elements_registry.get(nid)
        if reg_node and reg_node.url and page:
            from mkdocs.utils import get_relative_url
            href = get_relative_url(reg_node.url, page.file.url)

        # Right-floated pills: published + validation
        right_pills = []
        if published:
            right_pills.append('<span class="el-field">published</span>')
        for vtype in ('formal', 'numeric', 'symbolic', 'ai', 'human'):
            if vtype in validation:
                right_pills.append(f'<span class="el-check">✓ {vtype}</span>')
        right_html = ' '.join(right_pills)

        if href:
            id_html = f'<a href="{href}" class="el-id">{nid}</a>'
            title_html = f'<a href="{href}" class="el-index-title">{title}</a>'
        else:
            id_html = f'<span class="el-id">{nid}</span>'
            title_html = f'<span class="el-index-title">{title}</span>'

        return (
            f'<li class="el-index-item">'
            f'{id_html}'
            f'<span class="el-kind el-kind-{kind}">{abbrev}</span>'
            f'{title_html}'
            f'<span class="el-index-right">{right_html}</span>'
            f'</li>'
        )

    def _render_section_index(self, dir_path: str, page) -> str:
        """Render a listing of all live nodes in a directory."""
        from collections import OrderedDict

        direct_nodes = []
        subsections: OrderedDict[str, list] = OrderedDict()
        prefix = dir_path + '/'
        for node in sorted(self.elements_registry.values(), key=lambda n: n.id):
            if not node.live or not node.src_path.startswith(prefix):
                continue
            rest = node.src_path[len(prefix):]
            if '/' not in rest:
                direct_nodes.append(node)
            else:
                sub_dir = rest.split('/')[0]
                sub_name = re.sub(r'^\d+\s+', '', sub_dir)
                subsections.setdefault(sub_name, []).append(node)

        lines = ['\n']
        if direct_nodes:
            lines.append('<div class="elements-metadata"><ul class="el-index-list">')
            for node in direct_nodes:
                lines.append(self._render_node_list_item(node, page))
            lines.append('</ul></div>\n')
        for sub_name, nodes in subsections.items():
            lines.append(f'## {sub_name}\n')
            lines.append('<div class="elements-metadata"><ul class="el-index-list">')
            for node in nodes:
                lines.append(self._render_node_list_item(node, page))
            lines.append('</ul></div>\n')
        return '\n'.join(lines)

    def _render_elements_overview(self, elements_dir_name: str, page) -> str:
        """Render depth-2 overview for the top-level Elements/index.md."""
        sections = build_nav_sections(self.elements_registry)
        lines = ['\n']
        for section in sections:
            lines.append(f'## {section["name"]}\n')
            lines.append('<div class="elements-metadata"><ul class="el-index-list">')
            for node in section['nodes']:
                lines.append(self._render_node_list_item(node, page))
            lines.append('</ul></div>\n')
        return '\n'.join(lines)

    def on_page_markdown(self, markdown, page, config, files):
        """Process markdown for each page."""
        # Store original markdown for outline extraction (before any modifications)
        page.math_original_markdown = markdown

        # Generate article listing for index pages
        if getattr(page, 'meta', {}).get('type') == 'article-index':
            markdown = self._generate_article_listing(markdown, page, files)

        # Elements section index pages: inject listing
        if hasattr(self, '_section_index_files') and page.file.src_path in self._section_index_files:
            dir_path = self._section_index_files[page.file.src_path]
            markdown += self._render_section_index(dir_path, page)

        # Top-level Elements/index.md: append depth-2 overview
        elements_dir_name = self.config.get('elements_dir', 'Elements')
        if (page.file.src_path == f'{elements_dir_name}/index.md'
                and hasattr(self, 'elements_registry') and self.elements_registry):
            markdown += self._render_elements_overview(elements_dir_name, page)

        # Register heading anchors first (before processing references)
        self._register_heading_anchors(markdown, page)

        # Elements: metadata header, backlinks, nav title.
        # Injected before citation processing so [@key] in the header
        # (published_at) is resolved by the citation pipeline.
        if self._is_elements_node(page):
            node_id = page.meta.get('id')
            node = self.elements_registry.get(node_id)
            if node:
                # Nav label: "E0001 . Not . Title"
                abbrev = KIND_ABBREV.get(node.kind, node.kind)
                page.meta['title'] = f'{node.id} . {abbrev} . {node.title}'
            header = self._render_elements_header(node_id, page)
            backlinks = self._render_elements_backlinks(node_id, page)
            # Normalize H1 from frontmatter (single display truth, plain
            # title); the chip row goes ABOVE the title.
            lines = markdown.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('# '):
                    if node:
                        lines[i] = f'# {node.title}'
                    insert_pos = i
                    break
            lines.insert(insert_pos, header)
            markdown = '\n'.join(lines) + backlinks

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

        # Autolink E-IDs in all pages (if registry is populated)
        if self.elements_registry:
            markdown = self._autolink_element_ids(markdown, page)

        return markdown

    def on_env(self, env, config, files):
        """Register custom Jinja filters."""
        def markdown_filter(text):
            return md.markdown(text, extensions=['pymdownx.arithmatex'], extension_configs={'pymdownx.arithmatex': {'generic': True}})
        env.filters['markdown'] = markdown_filter
        return env

    def on_page_context(self, context, page, config, nav):
        """Inject template context: Elements sidebar, article outline/references."""
        # Elements sidebar for all pages under Elements/
        elements_dir_name = self.config.get('elements_dir', 'Elements')
        if page.file.src_path.startswith(elements_dir_name + '/') and self.elements_registry:
            # Hide the left navigation sidebar (Material reads page.meta.hide)
            hide = list(page.meta.get('hide', []))
            if 'navigation' not in hide:
                hide.append('navigation')
            page.meta['hide'] = hide

            sections = build_nav_sections(self.elements_registry)
            # Relative URLs via mkdocs (correct for both use_directory_urls modes)
            from mkdocs.utils import get_relative_url
            for section in sections:
                for node in section['nodes']:
                    node_file = self._files.get_file_from_path(node['src_path'])
                    if node_file:
                        node['url'] = get_relative_url(node_file.url, page.file.url)
                    else:
                        log.warning(f"[elements-nav] no file for {node['src_path']!r}")
                        node['url'] = '#'
                # Section index link
                if section.get('dir'):
                    idx_src = f"{elements_dir_name}/{section['dir']}/index.md"
                    idx_file = self._files.get_file_from_path(idx_src)
                    if idx_file:
                        section['index_url'] = get_relative_url(idx_file.url, page.file.url)
            # Top-level Elements index link
            top_idx = self._files.get_file_from_path(f'{elements_dir_name}/index.md')
            top_url = get_relative_url(top_idx.url, page.file.url) if top_idx else ''
            context['elements_nav'] = {
                'current_id': page.meta.get('id'),
                'sections': sections,
                'index_url': top_url,
            }

        # Article-type pages: references and outline
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

    def _write_elements_index(self, config):
        """Write elements/index.json to the site directory."""
        site_dir = Path(config['site_dir'])
        out_dir = site_dir / 'elements'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / 'index.json'
        data = registry_to_json(self.elements_registry)
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        log.info(f"Wrote elements/index.json ({len(data)} entries)")

    def _is_elements_node(self, page) -> bool:
        """Check if a page is an Elements node."""
        if not self.elements_dir_path:
            return False
        meta = getattr(page, 'meta', None)
        if not meta or 'id' not in meta:
            return False
        # Check if file is under elements dir
        abs_path = Path(page.file.abs_src_path)
        try:
            abs_path.relative_to(self.elements_dir_path)
            return True
        except ValueError:
            return False

    def _element_link(self, target_id: str, page, with_title: bool = True) -> str:
        """Build a markdown link to an element node, relative to `page`.

        with_title=False renders just the bare ID as link text, with the
        node title as a tooltip.
        """
        target = self.elements_registry.get(target_id)
        if not target:
            return f'{target_id} (unresolved)'
        # Compute relative path from current page dir to target src_path
        from posixpath import relpath as posix_relpath
        page_dir = page.file.src_path.rsplit('/', 1)[0] if '/' in page.file.src_path else ''
        rel = posix_relpath(target.src_path, start=page_dir)
        # Angle-bracket target handles spaces in filenames; {.el-ref} marks
        # the link as a system reference (attr_list, styled by site CSS)
        if with_title:
            return f'[{target_id} — {target.title}](<{rel}>){{.el-ref}}'
        safe_title = target.title.replace('"', "'")
        return f'[{target_id}](<{rel}> "{safe_title}"){{.el-ref}}'

    def _render_elements_header(self, node_id: str, page) -> str:
        """Render compact badge-style metadata header for an Elements node.

        Semantic information (kind, status, verification, dependency IDs)
        is rendered as a single chip row, visually separated from prose.
        Styling hooks: .elements-metadata, .el-kind, .el-status-*, .el-check,
        .el-field (CSS lives with the consuming site).
        """
        node = self.elements_registry.get(node_id)
        if not node:
            return ''

        chips = []

        # ID badge leads the chip row: a self-link (canonical reference)
        own_name = node.src_path.rsplit('/', 1)[-1]
        chips.append(f'[{node.id}](<{own_name}>){{.el-id}}')

        # Kind chip (colored per kind via CSS class).
        # 'environment' is a legacy alias of 'notation'.
        kind = 'notation' if node.kind == 'environment' else node.kind
        chips.append(f'<span class="el-kind el-kind-{kind}">{kind}</span>')

        # Status chip: established is the norm, only flag deviations
        if node.status != 'established':
            chips.append(f'<span class="el-status el-status-{node.status}">{node.status}</span>')

        # Verification chips — derived from validation: field
        validation_url = self.config.get('validation_url', '') or self.config.get('lean_url', '')
        for vtype, vinfo in node.validation.items():
            if not isinstance(vinfo, dict):
                continue
            vfile = vinfo.get('file', '')
            anchor = vinfo.get('anchor', '')
            if vfile and validation_url:
                href = f'{validation_url.rstrip("/")}/{vfile}'
                chips.append(f'<a class="el-check" href="{href}" title="verified: {vtype}">✓ {vtype}</a>')
            elif anchor:
                chips.append(f'<a class="el-check" href="#{anchor}" title="verified: {vtype}">✓ {vtype}</a>')
            else:
                chips.append(f'<a class="el-check" title="verified: {vtype}">✓ {vtype}</a>')

        # depends_on: not shown in the header (gets long); covered by prose
        # references and the generated "Used by" section.

        if node.notation:
            chain = resolve_notation_chain(self.elements_registry, node_id)
            links = ' → '.join(self._element_link(cid, page, with_title=False) for cid in chain)
            chips.append(f'<span class="el-field">notation {links}</span>')

        # published_at: cite via the citation pipeline ([@key] -> linked citetag)
        if node.published_at:
            cites = ' '.join(f'[@{key}]' for key in node.published_at)
            chips.append(f'<span class="el-field">published {cites}</span>')

        lines = []
        lines.append('')
        # Superseded warning stays a prominent blockquote above the chip row
        if node.status == 'superseded' and node.superseded_by:
            link = self._element_link(node.superseded_by, page)
            lines.append(f'> **Superseded** by {link}')
            lines.append('')
        lines.append('<div class="elements-metadata" markdown="1">')
        lines.append(' '.join(chips))
        lines.append('</div>')
        lines.append('')
        return '\n'.join(lines)

    def _render_elements_backlinks(self, node_id: str, page) -> str:
        """Render 'Used by' backlinks section for a node."""
        used_by = self.elements_backlinks.get(node_id, [])
        if not used_by:
            return ''

        lines = []
        # Two blank lines (\n\n\n) terminate any open theorem environment,
        # so the backlinks section never leaks into it.
        lines.append('')
        lines.append('')
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('**Used by:**')
        lines.append('')
        for uid in sorted(used_by):
            lines.append(f'- {self._element_link(uid, page)}')
        lines.append('')
        return '\n'.join(lines)

    def _autolink_element_ids(self, markdown: str, page) -> str:
        """Replace E-ID references in prose with links. Skip code/math/headings."""
        if not self.elements_registry:
            return markdown

        # Determine own node ID (don't self-link)
        own_id = None
        if self._is_elements_node(page):
            own_id = getattr(page, 'meta', {}).get('id')

        from posixpath import relpath as posix_relpath
        page_dir = page.file.src_path.rsplit('/', 1)[0] if '/' in page.file.src_path else ''

        def make_link(eid):
            target = self.elements_registry.get(eid)
            if not target:
                return None
            rel = posix_relpath(target.src_path, start=page_dir)
            safe_title = target.title.replace('"', "'")
            return f'[{eid}](<{rel}> "{safe_title}"){{.el-ref}}'

        lines = markdown.split('\n')
        result = []
        in_code_block = False
        in_math_block = False

        for line in lines:
            # Track fenced code blocks
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
            if line.strip() == '$$':
                in_math_block = not in_math_block

            if in_code_block or in_math_block:
                result.append(line)
                continue

            # Skip heading lines (don't linkify H1 title etc.)
            if line.lstrip().startswith('#'):
                result.append(line)
                continue

            # Skip HTML lines (index listings already have <a> links)
            if line.lstrip().startswith('<'):
                result.append(line)
                continue

            # First pass: replace bracketed bare-ID references [E0004]
            # These are the prose convention in real nodes.
            # Only match [E0004] NOT followed by ( or [ (which would be a link already)
            def replace_bracketed(m):
                eid = m.group(1)
                if eid == own_id:
                    return m.group(0)
                link = make_link(eid)
                return link if link else m.group(0)

            line = re.sub(r'\[(E[0-9]{4})\](?!\(|\[)', replace_bracketed, line)

            # Second pass: replace bare E-IDs not already inside links or code spans
            def replace_eid(m):
                eid = m.group(0)
                if eid == own_id:
                    return eid
                start = m.start()
                before = line[:start]
                # Skip if inside link target ](...)
                if before.endswith('(') or before.endswith('/'):
                    return eid
                # Skip if inside code span
                if before.count('`') % 2 == 1:
                    return eid
                # Skip if inside inline math
                if before.count('$') % 2 == 1:
                    return eid
                # Skip if preceded by [ (already part of a link text or bracketed ref)
                if start > 0 and line[start-1] == '[':
                    return eid
                # Skip if followed by ] (part of link text)
                end = m.end()
                if end < len(line) and line[end] == ']':
                    return eid
                # Skip if inside balanced brackets (part of existing link)
                bracket_depth = 0
                for c in before:
                    if c == '[':
                        bracket_depth += 1
                    elif c == ']':
                        bracket_depth -= 1
                if bracket_depth > 0:
                    return eid
                # Skip if preceded by <( (inside an angle-bracket link target)
                if before.endswith('<'):
                    return eid

                link = make_link(eid)
                return link if link else eid

            line = re.sub(r'\bE[0-9]{4}\b', replace_eid, line)
            result.append(line)

        return '\n'.join(result)

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
