# 3rd party imports
from mkdocs.config import base, config_options


class BibTexConfig(base.Config):
    """Configuration of the BibTex pluging for mkdocs.

    Options:
        bib_file (string): path or url to a single bibtex file for entries,
                           url example: https://api.zotero.org/*/items?format=bibtex
        bib_command (string): command to place a bibliography relevant to just that file
                              defaults to \bibliography
        bib_by_default (bool): automatically appends bib_command to markdown pages
                               by default, defaults to true
        footnote_format (string): format for the footnote number, defaults to "{key}"
    """

    # Input files
    bib_file = config_options.Optional(config_options.Type(str))

    # Commands
    bib_command = config_options.Type(str, default="\\bibliography")

    # Settings
    bib_by_default = config_options.Type(bool, default=True)
    footnote_format = config_options.Type(str, default="{key}")
