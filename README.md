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

### Basic syntax

An environment starts with `**Name.**` at the beginning of a line and ends at the next environment, heading, or **two blank lines**:

```markdown
**Definition.**
A *group* is a set $G$ with a binary operation satisfying
associativity, identity, and inverses.


**Theorem (Cayley).**
Every group is isomorphic to a subgroup of a symmetric group.


**Proof.**
Let $G$ act on itself by left multiplication. The resulting
homomorphism $G \to \mathrm{Sym}(G)$ is injective.

```

Renders as:

> **(1) Definition.** A *group* is a set $G$ with a binary operation satisfying associativity, identity, and inverses.
>
> **(2) Theorem** (Cayley). Every group is isomorphic to a subgroup of a symmetric group.
>
> **Proof.** Let $G$ act on itself by left multiplication. The resulting homomorphism $G \to \mathrm{Sym}(G)$ is injective.

### Environment names

Any word starting with a capital letter is recognized: Definition, Theorem, Proposition, Lemma, Corollary, Remark, Example, Exercise, Conjecture, etc. Multi-word names with spaces or `&` are supported (e.g. `**Theorem & Proof.**`).

Proofs are unnumbered. All other environments get sequential numbering per page.

### Labels

Optional labels go in parentheses before the closing dot:

```markdown
**Theorem (Cayley-Hamilton).**
Every square matrix satisfies its own characteristic polynomial.
```

Labels appear in the rendered output: **(3) Theorem** (Cayley-Hamilton).

### Critical: environment termination

Environments are terminated by any of:

1. **Two blank lines** (the most common way)
2. **The next environment header** (`**Name.**` on a new line)
3. **A markdown heading** (`##`, `###`, etc.)
4. **End of file**

**Two blank lines means two empty lines — not one.** This is the most common mistake. A single blank line is normal paragraph spacing *within* an environment. Two blank lines ends it.

```markdown
**Proposition.**
First paragraph of the proposition.

Still part of the proposition (single blank line).


This paragraph is OUTSIDE the proposition (two blank lines above).
```

### Custom anchors

Add `{#custom-id}` at the start of the environment content to set a stable anchor ID:

```markdown
**Theorem (Main result).**
{#thm:main}
The regulator profile of $f \circ g$ is bounded by the star product
of the individual profiles.
```

This creates an anchor `#thm:main` that won't change if environments are reordered. Without a custom ID, the plugin generates one from the environment name and number (e.g. `#theorem-3`). Labeled environments get an ID from the label (e.g. `#theorem-main-result`).

### Cross-references

Reference any anchored environment with `[#id]`:

```markdown
By [#thm:main], the composition is bounded.
```

This renders as a numbered link: [(3) 🔗](#thm:main). If the anchor isn't found, it renders as [❌](#thm:main).

Headings can also have custom anchors using the standard `attr_list` syntax:

```markdown
## Regulators {#sec:regulators}
```

These can be cross-referenced the same way: `[#sec:regulators]`.

## LaTeX Preamble

Global preamble commands are loaded from a `.tex` file:

```yaml
plugins:
  - mkdocs-math:
      preamble_file: "docs/preamble.tex"
```

Per-page preamble via frontmatter:

```yaml
---
math:
  preamble: |
    \newcommand{\Tr}{\mathrm{Tr}}
---
```

Both are injected as a hidden MathJax block. Commands are available in all math expressions on the page.

## Article Layout

Pages with `type: math-article` in frontmatter get a special template with title, author/date, abstract, outline, and references section:

```yaml
---
type: "math-article"
title: "My Article"
author: "Name"
date: "2026-01-01"
abstract: |
  One paragraph summary.
bibliography: "refs.bib"
---
```

The template renders the title from frontmatter — do **not** add a `# h1` heading in the body.

## Configuration

```yaml
plugins:
  - mkdocs-math:
      preamble_file: "docs/preamble.tex"   # LaTeX preamble file path (relative to mkdocs.yml)
      bib_file: "refs.bib"                 # BibTeX file for citations (optional)
      bib_command: "\\bibliography"         # Command that triggers bibliography insertion
      bib_by_default: true                  # Auto-add bibliography to pages with citations
      footnote_format: "{key}"             # Format for citation footnote keys
      outline_enabled: true                # Inject chapter outlines after h1 headings
      outline_depth: 2                     # Heading depth for outlines (2 = h2 only, 3 = h2+h3)
```

Per-page frontmatter overrides:

- `outline_enabled: false` — disable outline for this page
- `outline_depth: 3` — show deeper heading levels in outline
- `hide: [outline]` — alternative way to disable outline

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

## Development

```bash
git clone https://github.com/HeinrichHartmann/mkdocs-math.git
cd mkdocs-math
make install
make test
```

## License

MIT
