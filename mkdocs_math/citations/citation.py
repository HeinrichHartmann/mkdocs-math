from dataclasses import dataclass
import logging
import re

log = logging.getLogger("mkdocs.plugins.math")

CITATION_REGEX = re.compile(r"@(?P<key>[\w-]+)")
CITATION_BLOCK_REGEX = re.compile(r"\[(.*?)\]")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@dataclass
class Citation:
    """Represents a citation in raw markdown without formatting"""

    key: str

    def __str__(self) -> str:
        """String representation of the citation"""
        return f"@{self.key}"

    @classmethod
    def from_markdown(cls, markdown: str) -> list["Citation"]:
        """Extracts citations from a markdown string"""
        citations = []

        pos_citations = markdown.split(";")
        pos_citations = [citation for citation in pos_citations if EMAIL_REGEX.match(citation) is None]

        for citation in pos_citations:
            match = CITATION_REGEX.search(citation)

            if match:
                citations.append(Citation(key=match.group("key")))
        return citations


@dataclass
class CitationBlock:
    citations: list[Citation]
    raw: str = ""

    def __str__(self) -> str:
        """String representation of the citation block"""
        if self.raw != "":
            return f"[{self.raw}]"
        return "[" + "; ".join(str(citation) for citation in self.citations) + "]"

    @classmethod
    def from_markdown(cls, markdown: str) -> list["CitationBlock"]:
        """Extracts citation blocks from a markdown string"""
        """
        Given a markdown string
        1. Find all cite blocks by looking for square brackets
        2. For each cite block, try to extract the citations
            - if this errors there are no citations in this block and we move on
            - if this succeeds we have a list of citations
        """
        citation_blocks = []
        for match in CITATION_BLOCK_REGEX.finditer(markdown):
            try:
                citations = Citation.from_markdown(match.group(1))
                if len(citations) > 0:
                    citation_blocks.append(CitationBlock(raw=match.group(1), citations=citations))
            except Exception as e:
                log.warning(f"Error extracting citations from block: {e}")
        return citation_blocks
