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


@click.command('lint')
@click.argument('files', nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option('--bib', type=click.Path(exists=True, path_type=Path), help='Bibliography file for citation checking')
def lint_cmd(files: tuple[Path], bib: Optional[Path]):
    """Lint markdown article files for common issues."""
    if not files:
        click.echo("Usage: python -m mkdocs_math lint [--bib refs.bib] FILE [FILE ...]")
        return

    bib_keys = load_bib_keys(bib) if bib else None

    total_warnings = 0
    for path in files:
        if not path.suffix == '.md':
            continue
        result = lint_file(path, bib_keys)
        if not result.ok:
            for line, code, msg in result.warnings:
                click.echo(f"{path.name}:{line}: [{code}] {msg}")
            total_warnings += len(result.warnings)

    if total_warnings:
        click.echo(f"\n{total_warnings} warning(s) in {len(files)} file(s)")
        sys.exit(1)
    else:
        click.echo(f"OK — {len(files)} file(s) checked")
