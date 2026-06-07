r"""
Preprocessing for pandoc conversion.

Converts custom markdown syntax to pandoc-compatible fenced divs:
  **Theorem (Label).** content... → ::: {.theorem data-label="Label"} content... :::

Converts citations to LaTeX before environment parsing:
  [@cite] → \citep{cite}
"""

import re
from .environment_regex import parse_environments, EnvironmentMatch


def convert_citations_to_latex(markdown: str) -> str:
    r"""Convert all [@cite] citations to \citep{cite} LaTeX commands.

    This runs before environment parsing so citations in labels, content,
    and everywhere else get uniformly converted to LaTeX.

    Args:
        markdown: Markdown text with [@key] citation syntax

    Returns:
        Markdown with citations converted to \citep{} commands

    Examples:
        Input:  "See [@Smith2020] for details"
        Output: "See \citep{Smith2020} for details"

        Input:  "[@Smith2020; @Jones2021]"
        Output: "\citep{Smith2020,Jones2021}"
    """
    def replace_citation(match):
        content = match.group(1)
        # Extract all keys from the citation block
        # Note: content is like "key1; @key2" because outer pattern matched [@
        # So first key doesn't have @, but subsequent ones do
        keys = []
        for part in content.split(';'):
            part = part.strip()
            if part.startswith('@'):
                keys.append(part[1:])  # Remove @ prefix
            elif part:  # First key (no @ prefix)
                keys.append(part)

        if keys:
            return '\\citep{' + ','.join(keys) + '}'
        return match.group(0)  # Return unchanged if no keys found

    # Pattern: [@...] with any content inside
    # Use [^\]] to properly escape the ] in the character class
    return re.sub(r'\[@([^\]]+)\]', replace_citation, markdown)


def convert_labels_to_latex(markdown: str) -> str:
    r"""Convert custom anchor IDs {#id} to \label{id} for LaTeX.

    Args:
        markdown: Markdown text with {#custom-id} patterns

    Returns:
        Markdown with {#id} converted to \label{id}

    Example:
        Input:  "**Proposition.** {#HKA}\nContent here"
        Output: "**Proposition.** \label{HKA}\nContent here"
    """
    # Convert {#id} to \label{id}
    return re.sub(r'\{#([a-zA-Z0-9:\-]+)\}', r'\\label{\1}', markdown)


def convert_references_to_latex(markdown: str) -> str:
    r"""Convert cross-references [#id] to \ref{id} for LaTeX.

    Args:
        markdown: Markdown text with [#anchor-id] cross-reference patterns

    Returns:
        Markdown with [#id] converted to \ref{id}

    Example:
        Input:  "See Proposition [#HKA] for details"
        Output: "See Proposition \ref{HKA} for details"
    """
    # Convert [#id] to \ref{id}
    return re.sub(r'\[#([a-zA-Z0-9:\-]+)\]', r'\\ref{\1}', markdown)


def strip_admonitions(markdown: str) -> str:
    """Remove MkDocs admonition blocks (!!! type ...) for PDF export."""
    lines = markdown.split('\n')
    result = []
    i = 0
    while i < len(lines):
        if re.match(r'^!!!\s+\w+', lines[i]):
            # Skip the admonition marker and all indented content following it
            i += 1
            while i < len(lines) and (lines[i].startswith('    ') or lines[i].strip() == ''):
                # Stop at empty line only if next non-empty line is not indented
                if lines[i].strip() == '':
                    # Look ahead for more indented content
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == '':
                        j += 1
                    if j < len(lines) and lines[j].startswith('    '):
                        i += 1
                        continue
                    else:
                        break
                i += 1
        else:
            result.append(lines[i])
            i += 1
    return '\n'.join(result)


def convert_environments_to_divs(markdown: str) -> str:
    """Convert **Theorem.** syntax to fenced divs for pandoc.

    Args:
        markdown: Markdown text with **Environment.** or **Environment (Label).** syntax

    Returns:
        Markdown with fenced div syntax (::: {.environment} ... :::)

    Example:
        Input:  **Theorem (Fundamental).** Every polynomial has roots.
        Output: ::: {.theorem data-label="Fundamental"}
                Every polynomial has roots.
                :::
    """
    # Preprocessing steps (order matters):
    # 0. Strip admonitions (MkDocs-only syntax)
    markdown = strip_admonitions(markdown)

    # 1. Convert citations [@key] → \citep{key}
    markdown = convert_citations_to_latex(markdown)

    # 2. Convert cross-references [#id] → \ref{id}
    markdown = convert_references_to_latex(markdown)

    # 3. Convert label definitions {#id} → \label{id}
    markdown = convert_labels_to_latex(markdown)

    # 4. Parse environments
    environments = parse_environments(markdown)

    # Process in reverse order to preserve string positions during replacement
    for env in reversed(environments):
        # Build fenced div syntax
        div_start = f"::: {{.{env.env_name.lower()}"
        if env.label:
            div_start += f' data-label="{env.label}"'
        div_start += "}\n"

        div_end = "\n:::\n"

        # Check if content starts with a list
        content = env.content.lstrip()

        # Detect list markers at the start of content:
        # - Unordered: "- ", "* ", "+ "
        # - Ordered: "1. ", "2. ", etc. (digit(s) followed by ". ")
        starts_with_list = (
            content.startswith('- ') or
            content.startswith('* ') or
            content.startswith('+ ') or
            bool(re.match(r'^\d+\.\s', content))
        )

        # Add line break before lists so they don't start on same line as header in PDF
        # Use blank line (for pandoc list detection) with \leavevmode (forces new line without paragraph spacing)
        if starts_with_list:
            replacement = div_start + "\\leavevmode\n\n" + content + div_end
        else:
            replacement = div_start + content + div_end

        # Replace in markdown (working backwards preserves positions)
        markdown = markdown[:env.start] + replacement + markdown[env.end:]

    return markdown
