"""
Elements registry: scan elements directory, parse frontmatter, build ID registry.

The registry is the single source of truth for all E-ID resolution.
"""

import re
import logging
from pathlib import Path

import yaml

log = logging.getLogger("mkdocs.plugins.math.elements")

# Schema constants
ID_PATTERN = re.compile(r'^E[0-9]{4}$')
VALID_KINDS = frozenset([
    'environment', 'notation', 'definition', 'lemma',
    'proposition', 'theorem', 'corollary', 'example',
])
VALID_STATUSES = frozenset(['draft', 'established', 'superseded'])
VALID_CHECKED = frozenset(['numeric', 'adversarial', 'lean'])
NOTATION_KINDS = frozenset(['notation', 'environment'])

# Nav-label abbreviations per kind ('environment' is a legacy alias of 'notation')
KIND_ABBREV = {
    'environment': 'Not',
    'notation': 'Not',
    'definition': 'Def',
    'lemma': 'Lem',
    'proposition': 'Prop',
    'theorem': 'Thm',
    'corollary': 'Cor',
    'example': 'Ex',
}

# First body environment marker (e.g. "**Theorem.**", "**Notation (Sets).**")
# used to infer kind: when frontmatter omits it.
_ENV_MARKER = re.compile(r'^\*\*(Theorem|Proposition|Lemma|Corollary|Definition|Notation|Example)\b', re.M)


def infer_kind_from_body(path: Path) -> str | None:
    """Infer node kind from the first environment marker in the body."""
    try:
        content = path.read_text(encoding='utf-8')
    except OSError:
        return None
    m = _ENV_MARKER.search(content)
    return m.group(1).lower() if m else None


class ElementNode:
    """A single Elements node parsed from frontmatter."""

    def __init__(self, path: Path, meta: dict, src_path: str):
        self.path = path
        self.meta = meta
        self.src_path = src_path  # relative to docs_dir
        self.id = meta.get('id', '')
        self.title = meta.get('title', '')
        # kind: explicit in frontmatter, else inferred from the first
        # environment marker in the body (**Theorem.** -> theorem)
        self.kind = meta.get('kind') or infer_kind_from_body(path) or ''
        self.status = meta.get('status', '')
        # depends_on: (formerly uses:) — accept both during transition
        self.depends_on = meta.get('depends_on') or meta.get('uses') or []
        self.notation = meta.get('notation')
        self.extends = meta.get('extends')
        self.checked = meta.get('checked') or []
        self.published_at = meta.get('published_at') or []
        self.source = meta.get('source') or []
        self.superseded_by = meta.get('superseded_by')


def parse_node_frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter from a markdown file. Returns None if no frontmatter."""
    content = path.read_text(encoding='utf-8')
    if not content.startswith('---'):
        return None
    end = content.find('\n---', 3)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(content[3:end])
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    return meta


def build_registry(elements_dir: Path, docs_dir: Path) -> dict[str, ElementNode]:
    """Scan elements_dir recursively for nodes and build ID -> ElementNode registry.

    Raises RuntimeError on duplicate IDs.
    """
    registry = {}
    if not elements_dir.exists():
        return registry

    for md_file in sorted(elements_dir.rglob('*.md')):
        if md_file.name == 'index.md':
            continue
        meta = parse_node_frontmatter(md_file)
        if meta is None or 'id' not in meta:
            continue
        src_path = str(md_file.relative_to(docs_dir))
        node = ElementNode(md_file, meta, src_path)

        if node.id in registry:
            existing = registry[node.id]
            raise RuntimeError(
                f"Duplicate element ID {node.id}: "
                f"{existing.path.name} and {md_file.name}"
            )
        registry[node.id] = node

    return registry


def registry_to_json(registry: dict[str, ElementNode]) -> dict:
    """Convert registry to JSON-serializable dict for elements/index.json."""
    result = {}
    for eid, node in sorted(registry.items()):
        # URL: convert src_path to site URL (strip .md, add /)
        url = node.src_path.replace('\\', '/')
        if url.endswith('.md'):
            url = url[:-3] + '/'
        result[eid] = {
            'url': url,
            'title': node.title,
            'kind': node.kind,
            'status': node.status,
            'depends_on': node.depends_on,
        }
    return result


def detect_extends_cycle(registry: dict[str, ElementNode]) -> list[str] | None:
    """Detect cycles in extends: chains. Returns cycle path or None."""
    for start_id, node in registry.items():
        if not node.extends:
            continue
        visited = [start_id]
        current = node.extends
        while current:
            if current in visited:
                return visited[visited.index(current):] + [current]
            visited.append(current)
            target = registry.get(current)
            if not target:
                break
            current = target.extends
    return None


def resolve_notation_chain(registry: dict[str, ElementNode], node_id: str) -> list[str]:
    """Resolve the notation/extends chain for a node. Returns list of node IDs."""
    chain = []
    node = registry.get(node_id)
    if not node or not node.notation:
        return chain

    current = node.notation
    seen = set()
    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        target = registry.get(current)
        if not target or not target.extends:
            break
        current = target.extends
    return chain


def compute_backlinks(registry: dict[str, ElementNode]) -> dict[str, list[str]]:
    """Compute 'depended on by' backlinks: target_id -> [source_ids that depend on it]."""
    backlinks = {}
    for eid, node in registry.items():
        for dep_id in node.depends_on:
            backlinks.setdefault(dep_id, []).append(eid)
        if node.notation:
            backlinks.setdefault(node.notation, []).append(eid)
    return backlinks
