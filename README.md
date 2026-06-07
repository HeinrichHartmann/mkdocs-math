# mkdocs-math

MkDocs plugin for mathematical typesetting and article formatting.

## Features

- **Theorem environments**: `**Definition.**`, `**Theorem (Label).**` etc. with auto-numbering and anchor links
- **LaTeX preamble injection**: Global and per-page `\newcommand` definitions
- **Citation management**: BibTeX integration with citetags and reference sections
- **Chapter outlines**: Auto-generated outline from heading structure
- **Article layout**: Frontmatter-driven article pages with abstract, outline, and references
- **PDF export**: Pandoc-based PDF generation with LaTeX

## Installation

```bash
pip install mkdocs-math
```

Or from source:

```bash
pip install git+https://github.com/HeinrichHartmann/mkdocs-math.git
```

## Usage

In `mkdocs.yml`:

```yaml
plugins:
  - mkdocs-math:
      preamble_file: "docs/preamble.tex"
      bib_file: "refs.bib"
```

## License

MIT
