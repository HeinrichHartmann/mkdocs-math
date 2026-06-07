# mkdocs-math

MkDocs plugin for mathematical typesetting and article formatting.

## Features

- **Theorem environments**: auto-numbered with anchor links
- **LaTeX preamble injection**: global and per-page `\newcommand` definitions
- **Citation management**: BibTeX integration with citetags and reference sections
- **Chapter outlines**: auto-generated outline from heading structure
- **Article layout**: frontmatter-driven article pages with abstract, outline, and references
- **PDF export**: pandoc-based PDF generation with LaTeX

## Theorem Environments

Write theorem-like environments using bold markdown headers:

```markdown
**Definition.** A *group* is a set $G$ with a binary operation satisfying...

**Theorem (Cayley).** Every group is isomorphic to a subgroup of a symmetric group.

**Proof.** Let $G$ act on itself by left multiplication...
```

Renders as auto-numbered environments with anchor links:

> **(1) Definition.** A *group* is a set $G$ with a binary operation satisfying...
>
> **(2) Theorem** (Cayley). Every group is isomorphic to a subgroup of a symmetric group.
>
> **Proof.** Let $G$ act on itself by left multiplication...

Supported environment names: Definition, Theorem, Proposition, Lemma, Corollary, Remark, Example, Exercise, Conjecture, and any capitalized word. Proofs are unnumbered.

## Installation

Add as a dependency in `pyproject.toml`:

```toml
dependencies = [
    "mkdocs-math @ git+https://github.com/HeinrichHartmann/mkdocs-math.git",
]
```

Then:

```bash
uv sync
```

Or add directly:

```bash
uv add "mkdocs-math @ git+https://github.com/HeinrichHartmann/mkdocs-math.git"
```

## Usage

In `mkdocs.yml`:

```yaml
plugins:
  - mkdocs-math:
      preamble_file: "docs/preamble.tex"
      bib_file: "refs.bib"
```

## Development

```bash
git clone https://github.com/HeinrichHartmann/mkdocs-math.git
cd mkdocs-math
make install
make test
```

## License

MIT
