r"""
Parser for math environments in markdown.

Parses environment syntax:
  **EnvironmentName.** or **EnvironmentName (Label).**

Uses PCRE2 for recursive pattern matching to handle nested parentheses in labels.
"""

import pcre2 as re
from typing import Optional, NamedTuple


class EnvironmentMatch(NamedTuple):
    """A matched environment."""
    env_name: str
    label: Optional[str]
    content: str
    start: int
    end: int


# Pattern components
# ============================================================================

# Environment name: starts with capital letter, followed by letters, spaces, or ampersands
# Examples: "Definition", "Theorem & Proof", "Vector Field"
ENV_NAME = r'[A-Z](?:[a-zA-Z]|\s|&)*?'

# Label pattern: optional text in parentheses, supporting one level of nesting
# Handles: (Simple Label) or ($C^k(\Omega)$, description)
# Key feature: (?:[^()]|\([^)]*\))* matches either:
#   - [^()] = non-parenthesis characters
#   - \([^)]*\) = a complete parenthesis pair with no nested parens inside
# This allows one level of nesting like ($C^k(\Omega)$, text)
LABEL_PATTERN = r'(?:\(((?:[^()]|\([^)]*\))*)\))?'

# Content termination lookahead: stops matching content at any of these:
#   1. Two or more blank lines (\n\n\n)
#   2. Next environment starts: \n** ... .** pattern (on same line)
#   3. Markdown heading (any level)
#   4. End of string ($)
#
# Key improvement: detect new environments with pattern \n\*\*[^\n]*?\.\*\*
# [^\n]* ensures we only match within a single line (don't cross newlines).
# This terminates environments whenever the next line starts with **
# and ends with .**, regardless of blank lines between them.
CONTENT_TERMINATOR = (
    r'(?='
        r'\n\n\n'                           # Two+ blank lines
        r'|\n\*\*[^\n]*?\.\*\*'             # Next line: ** ... .** (single line, environment pattern)
        r'|\n#+'                            # Markdown heading
        r'|$'                               # End of string
    r')'
)


def parse_environments(markdown: str) -> list[EnvironmentMatch]:
    """Parse all math environments in markdown.

    Strategy: Chunk markdown by identifying block start positions (headings or environments),
    then extract content for each environment from its header to the next block start.

    Returns a list of EnvironmentMatch objects with:
    - env_name: The environment name (e.g., "Definition", "Theorem")
    - label: The label text (without parens) or None
    - content: The environment content
    - start: Start position in markdown
    - end: End position in markdown
    """
    matches = []

    # Pattern to find chunk starts: line start (^ or \n) followed by # (heading) or ** (environment)
    # Handles environments at document start or after newlines
    chunk_pattern = re.compile(
        r'(?:^|\n)(?:'
            r'#'                                                   # Markdown heading start
            r'|\*\*' + ENV_NAME + LABEL_PATTERN + r'\.\*\*'      # Environment header
        r')',
        re.MULTILINE | re.DOTALL
    )

    # Find all chunk boundaries (where headings or environments start)
    chunk_boundaries = [0]  # Start of file
    for match in chunk_pattern.finditer(markdown):
        # match.start() includes the ^ or \n, so we skip appropriately
        if match.group().startswith('\n'):
            chunk_boundaries.append(match.start() + 1)  # Skip the \n
        else:
            chunk_boundaries.append(match.start())  # ^ doesn't consume characters
    chunk_boundaries.append(len(markdown))  # End of file

    # Process each chunk to extract environments
    for i in range(len(chunk_boundaries) - 1):
        chunk_start = chunk_boundaries[i]
        chunk_end = chunk_boundaries[i + 1]
        chunk = markdown[chunk_start:chunk_end]

        # Check if this chunk is an environment (starts with **)
        if chunk.startswith('**'):
            # Try to match the environment header with content terminator
            env_match = re.match(
                r'\*\*(' + ENV_NAME + r')\s*' + LABEL_PATTERN + r'\.\*\*'
                r'(\s*.*?)'  # Content until terminator (lazy match)
                + CONTENT_TERMINATOR,
                chunk,
                re.DOTALL
            )

            if env_match:
                env_name = env_match.group(1).strip()
                label = env_match.group(2)
                content = env_match.group(3)

                # Strip trailing newlines if present
                if content.endswith('\n'):
                    content = content[:-1]

                # Calculate actual end position (where match ended, not chunk end)
                match_end = chunk_start + env_match.end()

                matches.append(EnvironmentMatch(
                    env_name=env_name,
                    label=label,
                    content=content,
                    start=chunk_start,
                    end=match_end,
                ))

    return matches


