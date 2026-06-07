from abc import ABC, abstractmethod
from .citation import Citation, CitationBlock
from .utils import log
from pybtex.database import BibliographyData, parse_file
from pybtex.backends.markdown import Backend as MarkdownBackend
from pybtex.style.formatting.plain import Style as PlainStyle


class ReferenceRegistry(ABC):
    """
    A registry of references that can be used to format citations
    """

    def __init__(self, bib_files: list[str], footnote_format: str = "{key}"):
        refs = {}
        log.info(f"Loading data from bib files: {bib_files}")
        for bibfile in bib_files:
            log.debug(f"Parsing bibtex file {bibfile}")
            bibdata = parse_file(bibfile)
            refs.update(bibdata.entries)
        self.bib_data = BibliographyData(entries=refs)
        self.footnote_format = footnote_format

        # Extract citetag field for citation tag preprocessing
        # Maps citation_key -> citetag string
        self.citetags = {}
        for key, entry in self.bib_data.entries.items():
            if 'citetag' in entry.fields:
                self.citetags[key] = entry.fields['citetag'].strip()

    def get_citetag(self, citation_key: str) -> str | None:
        """Get the citetag for a citation key, or None if not present."""
        return self.citetags.get(citation_key)

    @abstractmethod
    def validate_citation_blocks(self, citation_blocks: list[CitationBlock]) -> None:
        """Validates all citation blocks. Throws an error if any citation block is invalid"""

    @abstractmethod
    def inline_text(self, citation_block: CitationBlock) -> str:
        """Retrieves the inline citation text for a citation block"""

    @abstractmethod
    def reference_text(self, citation: Citation) -> str:
        """Retrieves the reference text for a citation"""


class SimpleRegistry(ReferenceRegistry):
    def __init__(self, bib_files: list[str], footnote_format: str = "{key}"):
        super().__init__(bib_files, footnote_format)
        self.style = PlainStyle()
        self.backend = MarkdownBackend()

    def validate_citation_blocks(self, citation_blocks: list[CitationBlock]) -> None:
        """Validates all citation blocks. Throws an error if any citation block is invalid"""
        for citation_block in citation_blocks:
            for citation in citation_block.citations:
                if citation.key not in self.bib_data.entries:
                    log.warning(f"Citing unknown reference key {citation.key}")

    def inline_text(self, citation_block: CitationBlock) -> str:
        keys = [
            self.footnote_format.format(key=citation.key)
            for citation in citation_block.citations
            if citation.key in self.bib_data.entries
        ]
        return "".join(f"[^{key}]" for key in keys)

    def reference_text(self, citation: Citation) -> str:
        entry = self.bib_data.entries[citation.key]
        log.debug(f"Converting bibtex entry {citation.key!r} without pandoc")
        formatted_entry = self.style.format_entry("", entry)
        entry_text = formatted_entry.text.render(self.backend)
        entry_text = entry_text.replace("\n", " ")
        # Clean up some common escape sequences
        entry_text = entry_text.replace("\\(", "(").replace("\\)", ")").replace("\\.", ".")
        log.debug(f"SUCCESS Converting bibtex entry {citation.key!r} without pandoc")
        return entry_text
