"""
Linter for math-article markdown files.

Checks markdown source for common issues without building.

Usage:
    python -m mkdocs_math lint docs/200\\ Articles/*.md
    python -m mkdocs_math lint docs/200\\ Articles/*.md --bib meta/refs.bib
"""

import re
import sys
import click
from pathlib import Path
from typing import Optional

from .environment_regex import parse_environments, ENV_NAME


def parse_frontmatter(content: str) -> tuple[dict, str, int]:
    """Parse YAML frontmatter. Returns (meta, body, body_start_line)."""
    if not content.startswith('---'):
        return {}, content, 0
    end = content.find('\n---', 3)
    if end == -1:
        return {}, content, 0
    import yaml
    try:
        meta = yaml.safe_load(content[3:end]) or {}
    except Exception:
        meta = {}
    body = content[end + 4:]
    body_start = content[:end + 4].count('\n') + 1
    return meta, body, body_start


def load_bib_keys(bib_path: Path) -> set[str]:
    """Extract all citation keys from a .bib file."""
    keys = set()
    for match in re.finditer(r'^@\w+\{(\w+)', bib_path.read_text(), re.MULTILINE):
        keys.add(match.group(1))
    return keys


class LintResult:
    def __init__(self, path: Path):
        self.path = path
        self.warnings: list[tuple[int, str, str]] = []  # (line, code, message)

    def warn(self, line: int, code: str, msg: str):
        self.warnings.append((line, code, msg))

    @property
    def ok(self):
        return len(self.warnings) == 0


def lint_file(path: Path, bib_keys: Optional[set[str]] = None) -> LintResult:
    """Lint a single markdown file."""
    result = LintResult(path)
    content = path.read_text()
    meta, body, body_start = parse_frontmatter(content)
    lines = content.split('\n')

    # ── Frontmatter checks ──────────────────────────────────────────────

    if meta.get('type') == 'math-article':
        for field in ('title', 'date', 'status'):
            if not meta.get(field):
                result.warn(1, 'F001', f'missing frontmatter field: {field}')

    # ── Environment checks ──────────────────────────────────────────────

    envs = parse_environments(body)

    for env in envs:
        # E001: environment content is suspiciously long (> 80 lines)
        # Skip proofs — they can legitimately be long
        content_lines = env.content.count('\n')
        if content_lines > 80 and env.env_name.lower() != 'proof':
            env_line = body_start + body[:env.start].count('\n')
            result.warn(env_line, 'E001',
                        f'{env.env_name} environment is {content_lines} lines long — '
                        f'likely unterminated (missing blank line or next heading?)')

        # E002: environment content contains a heading (swallowed section)
        if re.search(r'\n##+ ', env.content):
            env_line = body_start + body[:env.start].count('\n')
            result.warn(env_line, 'E002',
                        f'{env.env_name} environment contains a heading — '
                        f'environment likely swallowed the next section')

    # E003: lines that look like environments but don't parse
    # Compare line numbers of parsed environments against bold patterns in the body
    env_lines = {body_start + body[:env.start].count('\n') for env in envs}
    for i, line in enumerate(lines):
        m = re.match(r'^\*\*([A-Z][a-zA-Z ]*?)(?:\s*\(.*?\))?\.\*\*', line)
        if m and (i + 1) not in env_lines:
            result.warn(i + 1, 'E003',
                        f'looks like an environment header '
                        f'(**{m.group(1)}.**) but was not parsed as one')

    # ── Citation checks ─────────────────────────────────────────────────

    for i, line in enumerate(lines):
        # C001: removed — locators inside brackets [@key, Theorem 2] are now supported

        # C002: multiple citation keys without semicolons: [@Key1, @Key2]
        # (correct syntax uses semicolons: [@Key1; @Key2])
        for m in re.finditer(r'\[@\w+,\s*@', line):
            result.warn(i + 1, 'C002',
                        f'multiple citations with comma instead of semicolon — '
                        f'use [@key1; @key2]')

        # C003: citation key not in bib file
        if bib_keys is not None:
            for m in re.finditer(r'\[@(\w+)', line):
                key = m.group(1)
                if key not in bib_keys:
                    result.warn(i + 1, 'C003',
                                f'citation key not found in bib: @{key}')

    # ── Display math in list items ───────────────────────────────────────

    # M001: $$ inside a list item with < 4-space indent or missing blank line.
    # Python-Markdown requires 4-space indent for list continuation blocks.
    # Without it, $$ breaks out of the <li> and arithmatex won't process it,
    # causing MathJax to render it with wrong sizing.
    in_list = False
    in_display_math = False
    list_indent = 0
    for i, line in enumerate(lines):
        # Detect ordered/unordered list item start
        m = re.match(r'^(\s*)\d+\.\s', line) or re.match(r'^(\s*)[-*+]\s', line)
        if m:
            in_list = True
            list_indent = len(m.group(1)) + 4  # continuation needs 4 spaces past marker start
            continue

        # A non-blank, non-indented line ends the list context
        if in_list and line.strip() and not line.startswith(' '):
            in_list = False
            continue

        # Track $$ pairs: only check the opening $$
        if in_list and line.strip() == '$$':
            if not in_display_math:
                # Opening $$
                in_display_math = True
                actual_indent = len(line) - len(line.lstrip())
                if actual_indent < list_indent:
                    result.warn(i + 1, 'M001',
                                f'display math $$ in list item has {actual_indent}-space indent '
                                f'(need {list_indent}) — will break out of list')
                elif i > 0 and lines[i - 1].strip():
                    result.warn(i + 1, 'M001',
                                f'display math $$ in list item missing blank line before it '
                                f'— arithmatex block processor will not match')
            else:
                # Closing $$
                in_display_math = False

    # ── Line length checks ──────────────────────────────────────────────

    # L001: line exceeds hard max of 150 characters.
    # Skip frontmatter and lines that are a single URL or image reference.
    in_frontmatter = False
    for i, line in enumerate(lines):
        if i == 0 and line == '---':
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line == '---':
                in_frontmatter = False
            continue
        if len(line) > 150:
            if re.match(r'^\s*!?\[.*\]\(.*\)\s*$', line):
                continue
            result.warn(i + 1, 'L001',
                        f'line is {len(line)} characters (hard max 150)')

    # ── Cross-reference checks ──────────────────────────────────────────

    # Collect all defined anchors {#id}
    defined_ids = set(re.findall(r'\{#([a-zA-Z0-9:\-]+)\}', content))
    # Check all references [#id]
    for i, line in enumerate(lines):
        for m in re.finditer(r'\[#([a-zA-Z0-9:\-]+)\]', line):
            ref_id = m.group(1)
            if ref_id not in defined_ids:
                result.warn(i + 1, 'R001',
                            f'cross-reference [#{ref_id}] has no matching anchor {{#{ref_id}}}')

    return result


# ── Elements lint ──────────────────────────────────────────────────────

from .elements import (
    ID_PATTERN, VALID_KINDS, VALID_STATUSES, VALID_CHECKED,
    NOTATION_KINDS, build_registry, detect_extends_cycle,
    parse_node_frontmatter,
)

# Known schema fields for Elements nodes
_KNOWN_FIELDS = frozenset([
    'id', 'title', 'kind', 'status', 'depends_on', 'uses', 'notation', 'extends',
    'checked', 'published_at', 'source', 'superseded_by', 'outline_enabled',
    'outline_depth', 'hide', 'math', 'type', 'preamble',
])


def is_elements_node(path: Path, elements_dir: Optional[Path]) -> bool:
    """Check if a file is under the elements directory and has an id: field."""
    if elements_dir is None:
        return False
    try:
        path.resolve().relative_to(elements_dir.resolve())
    except ValueError:
        return False
    meta = parse_node_frontmatter(path)
    return meta is not None and 'id' in meta


def lint_elements_node(path: Path, registry: dict, bib_keys: Optional[set[str]] = None) -> LintResult:
    """Lint an Elements node against the E-* checks from the ADR."""
    result = LintResult(path)
    meta = parse_node_frontmatter(path)
    if meta is None:
        return result

    node_id = meta.get('id', '')

    # E-ID-FORMAT: id matches ^E[0-9]{4}$
    if not ID_PATTERN.match(str(node_id)):
        result.warn(1, 'E-ID-FORMAT', f'id "{node_id}" does not match ^E[0-9]{{4}}$')

    # E-ID-UNIQUE: checked at registry level (duplicate = build error)
    # We detect it here by counting occurrences
    id_count = sum(1 for nid, n in registry.items() if nid == node_id)
    # Registry enforces uniqueness at build time; we still flag for clarity
    if id_count == 0 and ID_PATTERN.match(str(node_id)):
        result.warn(1, 'E-ID-UNIQUE', f'id {node_id} not found in registry (duplicate or conflict)')

    # E-ID-FILENAME: filename starts with "<id> - "
    expected_prefix = f"{node_id} - "
    if not path.name.startswith(expected_prefix):
        result.warn(1, 'E-ID-FILENAME', f'filename should start with "{expected_prefix}"')

    # E-SCHEMA: required fields, enum validation
    for field in ('id', 'title', 'kind', 'status'):
        if not meta.get(field):
            result.warn(1, 'E-SCHEMA', f'missing required field: {field}')

    kind = meta.get('kind', '')
    if kind and kind not in VALID_KINDS:
        result.warn(1, 'E-SCHEMA', f'invalid kind: "{kind}" (allowed: {", ".join(sorted(VALID_KINDS))})')

    status = meta.get('status', '')
    if status and status not in VALID_STATUSES:
        result.warn(1, 'E-SCHEMA', f'invalid status: "{status}" (allowed: {", ".join(sorted(VALID_STATUSES))})')

    checked = meta.get('checked') or []
    if isinstance(checked, list):
        for c in checked:
            if c not in VALID_CHECKED:
                result.warn(1, 'E-SCHEMA', f'invalid checked value: "{c}" (allowed: {", ".join(sorted(VALID_CHECKED))})')

    # Unknown fields warning
    for key in meta:
        if key not in _KNOWN_FIELDS:
            result.warn(1, 'E-SCHEMA', f'unknown frontmatter field: "{key}" (may be fine if schema evolves)')

    # E-REF-RESOLVE: depends_on, notation, extends, superseded_by must exist in registry
    depends_on = meta.get('depends_on') or meta.get('uses') or []
    if isinstance(depends_on, list):
        for uid in depends_on:
            if str(uid) not in registry:
                result.warn(1, 'E-REF-RESOLVE', f'depends_on: {uid} not found in registry')

    notation = meta.get('notation')
    if notation and str(notation) not in registry:
        result.warn(1, 'E-REF-RESOLVE', f'notation: {notation} not found in registry')

    extends = meta.get('extends')
    if extends and str(extends) not in registry:
        result.warn(1, 'E-REF-RESOLVE', f'extends: {extends} not found in registry')

    superseded_by = meta.get('superseded_by')
    if superseded_by and str(superseded_by) not in registry:
        result.warn(1, 'E-REF-RESOLVE', f'superseded_by: {superseded_by} not found in registry')

    # E-REF-KIND: notation target must be notation/environment; extends only on notation/environment
    if notation and str(notation) in registry:
        target = registry[str(notation)]
        if target.kind not in NOTATION_KINDS:
            result.warn(1, 'E-REF-KIND',
                        f'notation: {notation} targets kind "{target.kind}" '
                        f'(must be notation or environment)')

    if extends:
        if kind not in NOTATION_KINDS:
            result.warn(1, 'E-REF-KIND',
                        f'extends: only allowed on notation/environment nodes (this is {kind})')
        if str(extends) in registry:
            target = registry[str(extends)]
            if target.kind not in NOTATION_KINDS:
                result.warn(1, 'E-REF-KIND',
                            f'extends: {extends} targets kind "{target.kind}" '
                            f'(must be notation or environment)')

    # E-SUPERSEDED: status: superseded iff superseded_by is set
    if status == 'superseded' and not superseded_by:
        result.warn(1, 'E-SUPERSEDED', 'status is "superseded" but superseded_by is not set')
    if superseded_by and status != 'superseded':
        result.warn(1, 'E-SUPERSEDED', f'superseded_by is set but status is "{status}" (should be "superseded")')

    # E-CITE-RESOLVE: published_at citekeys must exist in bib
    if bib_keys is not None:
        published_at = meta.get('published_at') or []
        if isinstance(published_at, list):
            for key in published_at:
                if str(key) not in bib_keys:
                    result.warn(1, 'E-CITE-RESOLVE', f'published_at citekey not in bib: {key}')

    # E-PROSE-REF: E-IDs in body that don't resolve
    content = path.read_text(encoding='utf-8')
    _, body, body_start = parse_frontmatter(content)
    for i, line in enumerate(body.split('\n')):
        for m in re.finditer(r'\bE[0-9]{4}\b', line):
            eid = m.group(0)
            if eid != node_id and eid not in registry:
                result.warn(body_start + i + 1, 'E-PROSE-REF',
                            f'E-ID {eid} in prose does not resolve in registry')

    return result


def lint_elements_global(registry: dict) -> list[tuple[str, str, str]]:
    """Run global (cross-file) element checks. Returns list of (code, id, message)."""
    issues = []

    # E-REF-ACYCLIC: check extends cycles
    cycle = detect_extends_cycle(registry)
    if cycle:
        issues.append(('E-REF-ACYCLIC', cycle[0],
                       f'extends: cycle detected: {" → ".join(cycle)}'))

    return issues


@click.command('lint')
@click.argument('files', nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option('--bib', type=click.Path(exists=True, path_type=Path), help='Bibliography file for citation checking')
@click.option('--elements-dir', type=click.Path(exists=True, path_type=Path),
              help='Elements directory for node linting (auto-detected if not set)')
def lint_cmd(files: tuple[Path], bib: Optional[Path], elements_dir: Optional[Path]):
    """Lint markdown article files for common issues."""
    if not files:
        click.echo("Usage: python -m mkdocs_math lint [--bib refs.bib] FILE [FILE ...]")
        return

    bib_keys = load_bib_keys(bib) if bib else None

    # Auto-detect elements_dir if not explicitly provided
    if elements_dir is None:
        for f in files:
            # Walk up to find docs/Elements pattern
            for parent in f.resolve().parents:
                candidate = parent / 'Elements'
                if candidate.is_dir():
                    elements_dir = candidate
                    break
                # Also check if we're inside an Elements dir
                if parent.name == 'Elements':
                    elements_dir = parent
                    break
            if elements_dir:
                break

    # Build elements registry if we have an elements dir
    elements_registry = {}
    if elements_dir and elements_dir.exists():
        # Determine docs_dir (parent of elements_dir)
        docs_dir = elements_dir.parent
        try:
            elements_registry = build_registry(elements_dir, docs_dir)
        except RuntimeError as e:
            click.echo(f"FATAL: {e}", err=True)
            sys.exit(2)

    total_warnings = 0
    for path in files:
        if not path.suffix == '.md':
            continue

        # Run standard article lint
        result = lint_file(path, bib_keys)

        # Run elements lint if this is a node
        if elements_dir and is_elements_node(path, elements_dir):
            elem_result = lint_elements_node(path, elements_registry, bib_keys)
            # Merge warnings
            result.warnings.extend(elem_result.warnings)

        if not result.ok:
            for line, code, msg in result.warnings:
                click.echo(f"{path.name}:{line}: [{code}] {msg}")
            total_warnings += len(result.warnings)

    # Global element checks
    if elements_registry:
        global_issues = lint_elements_global(elements_registry)
        for code, eid, msg in global_issues:
            click.echo(f"[{code}] {msg}")
            total_warnings += 1

    if total_warnings:
        click.echo(f"\n{total_warnings} warning(s) in {len(files)} file(s)")
        sys.exit(1)
    else:
        click.echo(f"OK — {len(files)} file(s) checked")
