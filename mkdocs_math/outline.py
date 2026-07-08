"""
Structural outline of math-article markdown files.

Extracts headings, environments, and citations from the parsed state
without replicating the parser — reuses environment_regex directly.

Usage:
    python -m mkdocs_math outline article.md
    python -m mkdocs_math outline --json article.md
"""

import re
import json
import click
from pathlib import Path

from .environment_regex import parse_environments
from .lint import parse_frontmatter


def extract_outline(path: Path) -> dict:
    """Extract structural outline from a markdown article."""
    content = path.read_text()
    meta, body, body_start = parse_frontmatter(content)

    # ── Parse environments (reuses the real parser) ─────────────────────
    envs = parse_environments(body)

    # ── Extract headings ────────────────────────────────────────────────
    headings = []
    for m in re.finditer(r'^(#{2,6})\s+(.+)', body, re.MULTILINE):
        pos = m.start()
        line = body_start + body[:pos].count('\n')
        level = len(m.group(1))
        title = m.group(2).strip()
        headings.append({
            'type': 'heading',
            'level': level,
            'title': title,
            'line': line,
            'pos': pos,
        })

    # ── Extract citations ───────────────────────────────────────────────
    citations = set()
    for m in re.finditer(r'\[@(\w+)', body):
        citations.add(m.group(1))

    # ── Build environment entries ───────────────────────────────────────
    env_entries = []
    for env in envs:
        line = body_start + body[:env.start].count('\n')
        content_lines = env.content.count('\n') + 1
        # Extract citations within this environment
        env_cites = set(m.group(1) for m in re.finditer(r'\[@(\w+)', env.content))

        # Extract anchor {#id} from the environment header line
        anchor_match = re.search(r'\{#([a-zA-Z0-9:\-]+)\}', env.content[:200])
        anchor = anchor_match.group(1) if anchor_match else None

        entry = {
            'type': 'environment',
            'env_name': env.env_name,
            'label': env.label,
            'anchor': anchor,
            'lines': content_lines,
            'line': line,
            'pos': env.start,
        }
        if env_cites:
            entry['citations'] = sorted(env_cites)
        env_entries.append(entry)

    # ── Interleave by position ──────────────────────────────────────────
    elements = sorted(headings + env_entries, key=lambda e: e['pos'])
    # Remove pos (internal)
    for e in elements:
        del e['pos']

    # ── Metadata summary ───────────────────────────────────────────────
    meta_summary = {}
    for k in ('title', 'author', 'date', 'status', 'doi', 'slug'):
        if meta.get(k):
            meta_summary[k] = meta[k]

    return {
        'file': path.name,
        'meta': meta_summary,
        'citations': sorted(citations),
        'elements': elements,
    }


def format_outline_text(outline: dict) -> str:
    """Format outline as readable text."""
    lines = []

    # Meta
    meta = outline['meta']
    if meta.get('title'):
        lines.append(f"# {meta['title']}")
    parts = []
    for k in ('author', 'date', 'status', 'doi'):
        if meta.get(k):
            parts.append(f"{k}={meta[k]}")
    if parts:
        lines.append('  ' + ', '.join(parts))
    lines.append('')

    # Elements
    for el in outline['elements']:
        if el['type'] == 'heading':
            indent = '  ' * (el['level'] - 2)
            lines.append(f"{indent}{'#' * el['level']} {el['title']}  (L{el['line']})")

        elif el['type'] == 'environment':
            label = f" ({el['label']})" if el.get('label') else ''
            anchor = f"  {{#{el['anchor']}}}" if el.get('anchor') else ''
            cites = f"  [{', '.join(el['citations'])}]" if el.get('citations') else ''
            lines.append(f"    {el['env_name']}{label}{anchor}  (L{el['line']}+{el['lines']}){cites}")

    # Citations summary
    if outline['citations']:
        lines.append('')
        lines.append(f"Citations ({len(outline['citations'])}): {', '.join(outline['citations'])}")

    return '\n'.join(lines)


@click.command('outline')
@click.argument('file', type=click.Path(exists=True, path_type=Path))
@click.option('--json-output', '--json', 'use_json', is_flag=True, help='Output as JSON')
def outline_cmd(file: Path, use_json: bool):
    """Show structural outline of a math article."""
    outline = extract_outline(file)
    if use_json:
        click.echo(json.dumps(outline, indent=2))
    else:
        click.echo(format_outline_text(outline))
