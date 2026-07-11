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

    Supports locators: [@key, Theorem 2.3] → \citep[Theorem 2.3]{key}

    Args:
        markdown: Markdown text with [@key] citation syntax

    Returns:
        Markdown with citations converted to \citep{} commands

    Examples:
        "See [@Smith2020] for details"           → "See \citep{Smith2020} for details"
        "[@Smith2020; @Jones2021]"                → "\citep{Smith2020,Jones2021}"
        "[@Smith2020, Theorem 2.3]"              → "\citep[Theorem 2.3]{Smith2020}"
        "[@Smith2020, p. 5; @Jones2021, Ch. 3]"  → "\citep[p. 5]{Smith2020}\citep[Ch. 3]{Jones2021}"
    """
    def parse_single_cite(text):
        """Parse 'key' or 'key, locator' into (key, locator_or_None)."""
        text = text.strip()
        if text.startswith('@'):
            text = text[1:]
        # Split on first comma: key, locator
        if ', ' in text:
            key, locator = text.split(', ', 1)
            return key.strip(), locator.strip()
        return text.strip(), None

    def replace_citation(match):
        content = match.group(1)
        # Split by semicolons for multiple citations
        parts = content.split(';')
        cites = [parse_single_cite(p) for p in parts]

        # If no locators and multiple keys, combine into one \citep
        if len(cites) > 1 and all(loc is None for _, loc in cites):
            keys = [k for k, _ in cites]
            return '\\citep{' + ','.join(keys) + '}'

        # Otherwise emit one \citep per citation
        result = []
        for key, locator in cites:
            if locator:
                result.append(f'\\citep[{locator}]{{{key}}}')
            else:
                result.append(f'\\citep{{{key}}}')
        return ''.join(result)

    # Pattern: [@...] with any content inside
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


def strip_target_blocks(markdown: str, keep: str) -> str:
    """Keep blocks for one target, strip the other.

    Blocks are delimited by HTML comments:
        <!--web-->  ... <!--/web-->   — web-only content
        <!--print--> ... <!--/print--> — print/PDF-only content

    Args:
        markdown: Markdown text with target blocks
        keep: Which target to keep ("web" or "print")
    """
    strip = 'print' if keep == 'web' else 'web'
    # Remove blocks for the stripped target
    markdown = re.sub(
        rf'<!--\s*{strip}\s*-->.*?<!--\s*/{strip}\s*-->',
        '', markdown, flags=re.DOTALL
    )
    # Remove markers for the kept target (keep the content)
    markdown = re.sub(rf'<!--\s*/?{keep}\s*-->', '', markdown)
    return markdown


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
    # 0a. Strip web-only blocks, keep print blocks
    markdown = strip_target_blocks(markdown, keep='print')
    # 0b. Strip admonitions (MkDocs-only syntax)
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
