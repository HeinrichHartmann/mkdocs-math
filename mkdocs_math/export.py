#!/usr/bin/env python3
"""
Export markdown articles to PDF using pandoc pipeline.

Architecture:
1. Preprocess: Convert **Theorem.** syntax to fenced divs (::: {.theorem})
2. Pandoc: Convert markdown to LaTeX using Lua filter
3. Wrap: Add LaTeX preamble and document structure
4. Compile: pdflatex + bibtex

Usage:
    python -m mkdocs_math export-tex path/to/article.md [-o output_dir]
    python -m mkdocs_math export-pdf path/to/article.md [-o output_dir]
"""

import subprocess
import sys
import tempfile
import yaml
import click
from pathlib import Path
from typing import Optional

from .preprocess_pandoc import convert_environments_to_divs


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown content."""
    if not content.startswith('---'):
        return {}, content

    lines = content.split('\n')
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return {}, content

    frontmatter_text = '\n'.join(lines[1:end_idx])
    body = '\n'.join(lines[end_idx + 1:])

    try:
        meta = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        meta = {}

    return meta, body


def preprocess_markdown(markdown: str) -> str:
    """Preprocess markdown for pandoc conversion.

    Converts custom syntax to pandoc-compatible fenced divs:
    - **Theorem (Label).** → ::: {.theorem data-label="Label"}
    """
    return convert_environments_to_divs(markdown)


def pandoc_to_latex(markdown: str, lua_filter_path: Path, bib_file: Optional[Path] = None) -> str:
    """Convert markdown to LaTeX body using pandoc.

    Args:
        markdown: Preprocessed markdown content
        lua_filter_path: Path to pandoc-environments.lua filter
        bib_file: Optional path to bibliography file for citations

    Returns:
        LaTeX body (without preamble/document structure)
    """
    # Build pandoc command
    cmd = [
        "pandoc",
        "--lua-filter", str(lua_filter_path),
        "-f", "markdown",
        "-t", "latex",
        "--shift-heading-level-by=-1",  # ## becomes \section (not \subsection)
    ]

    # Add citation processing if bibliography file provided
    # Use --natbib to generate \cite{} commands instead of processing citations
    # This lets BibTeX handle formatting with alpha-local.bst style
    if bib_file and bib_file.exists():
        cmd.extend([
            "--natbib",
            "--bibliography", str(bib_file),
        ])

    # Run pandoc
    result = subprocess.run(
        cmd,
        input=markdown,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Pandoc failed: {result.stderr}")

    return result.stdout


def wrap_latex_document(meta: dict, latex_body: str, preamble_path: Optional[Path] = None, mobile: bool = False) -> str:
    """Wrap LaTeX body in complete document with preamble."""

    # Load preamble if provided
    preamble_content = ""
    if preamble_path and preamble_path.exists():
        preamble_content = preamble_path.read_text()

    # Extract metadata
    title = meta.get('title', 'Untitled')
    tagline = meta.get('tagline', '').strip()
    author = meta.get('author', '')
    affiliation = meta.get('affiliation', '')
    email = meta.get('email', '')
    abstract = meta.get('abstract', '').strip()
    doi = meta.get('doi', '').strip()
    preamble_extra = meta.get('math',{}).get('preamble', '').strip()

    if preamble_extra:
        preamble_content += f"\n%--- Extra Preamble from Metadata ---\n{preamble_extra}\n"
        
    # Build author with ORCID and footnote for affiliation
    orcid = meta.get('orcid', '')

    # Build footnote content (affiliation, website, email)
    footnote_parts = []
    if affiliation:
        footnote_parts.append(affiliation)
    footnote_parts.append("\\href{https://heinrichhartmann.com/math}{HeinrichHartmann.com}")
    if email:
        footnote_parts.append(f"\\texttt{{{email}}}")

    footnote_content = " / ".join(footnote_parts) if footnote_parts else ""

    # Author line with ORCID and footnote
    author_line = author
    if footnote_content:
        author_line += f"\\footnote{{{footnote_content}}}"
    if orcid:
        author_line += f"\\;\\,\\orcidlink{{{orcid}}}"

    # DOI and canonical URL lines (displayed below author, centered)
    canonical_url = meta.get('canonical_url', '').strip()
    header_links = []
    if doi:
        header_links.append(f"\\href{{https://doi.org/{doi}}}{{doi:{doi}}}")
    if canonical_url:
        display_url = canonical_url.replace('https://', '').replace('http://', '')
        header_links.append(f"\\href{{{canonical_url}}}{{{display_url}}}")
    doi_line = f"\\vspace{{-3em}}\\begin{{center}}{'\\\\\\\\'.join(header_links)}\\end{{center}}\\vspace{{0.5em}}" if header_links else ""

    # Abstract section
    abstract_section = ""
    if abstract:
        abstract_section = f"""
\\begin{{abstract}}
{abstract}
\\end{{abstract}}
"""

    # Table of contents (unless hide: outline is set)
    hide_items = meta.get('hide', [])
    if isinstance(hide_items, str):
        hide_items = [hide_items]
    show_toc = 'outline' not in hide_items

    toc_section = ""
    if show_toc:
        toc_section = "\\tableofcontents\n"

    # Subtitle/tagline
    subtitle_block = ""
    if tagline:
        subtitle_block = f"\\\\[0.5em] \\large {tagline}"

    # Layout settings: mobile (iPhone 14) vs standard A4
    if mobile:
        docclass_opts = "8pt"
        docclass_name = "extarticle"   # extsizes: supports 8pt natively
        geometry_opts = "paperwidth=80mm,paperheight=170mm,left=4mm,right=4mm,top=3mm,bottom=4mm"
        parskip = "0.2em"
        stretch = "1.0"
        extra_layout = "\\AtBeginDocument{\\footnotesize}"  # ~6pt
    else:
        docclass_opts = "10pt,a4paper"
        docclass_name = "article"
        geometry_opts = "margin=2.5cm"
        parskip = "0.5em"
        stretch = "1.05"
        extra_layout = ""

    # Build complete document
    document = f"""%==============================================================================
% {title}
% Generated by export-pdf.py (pandoc pipeline)
%==============================================================================
\\documentclass[{docclass_opts}]{{{docclass_name}}}

%---------------------------- Encoding & Fonts -------------------------------
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{lmodern}}

%---------------------------- Layout -----------------------------------------
\\usepackage[{geometry_opts}]{{geometry}}
\\usepackage{{setspace}}
\\setstretch{{{stretch}}}
\\setlength{{\\parskip}}{{{parskip}}}
\\setlength{{\\parindent}}{{0em}}

%---------------------------- Lists ------------------------------------------
\\usepackage{{enumitem}}
% Compact list formatting with line spacing between items
\\setlist{{itemsep=0.25\\baselineskip, parsep=0pt, topsep=0.25\\baselineskip, partopsep=0pt, leftmargin=*}}

%---------------------------- Table of Contents ------------------------------
\\usepackage{{tocloft}}
\\renewcommand{{\\contentsname}}{{Outline}}  % Rename "Contents" to "Outline"
\\setlength{{\\cftbeforesecskip}}{{2pt}}  % Compact spacing between TOC entries
\\setlength{{\\cftbeforesubsecskip}}{{0pt}}

%---------------------------- Math & Theorems --------------------------------
\\usepackage{{amsmath,amssymb,mathtools,amsthm}}
\\usepackage{{longtable}}

% Swap numbering and add parentheses: (12) Definition instead of Definition 12
\\swapnumbers

\\theoremstyle{{plain}}
\\newtheorem{{theorem}}{{Theorem}}
\\newtheorem{{lemma}}[theorem]{{Lemma}}
\\newtheorem{{proposition}}[theorem]{{Proposition}}
\\newtheorem{{corollary}}[theorem]{{Corollary}}

\\theoremstyle{{definition}}
\\newtheorem{{definition}}[theorem]{{Definition}}
\\newtheorem{{example}}[theorem]{{Example}}
\\newtheorem{{remark}}[theorem]{{Remark}}

% Add parentheses around theorem numbers
\\renewcommand{{\\thetheorem}}{{(\\arabic{{theorem}})}}

%---------------------------- Bibliography -----------------------------------
\\usepackage[numbers,sort&compress]{{natbib}}

%---------------------------- Hyperlinks -------------------------------------
\\usepackage{{url}}
\\usepackage{{hyperref}}
\\hypersetup{{hidelinks}}
\\urlstyle{{same}}
\\renewcommand{{\\UrlFont}}{{\\small\\ttfamily}}

%---------------------------- Author/Affiliation -----------------------------
\\usepackage{{authblk}}
\\usepackage{{orcidlink}}

%---------------------------- Citations (natbib) -----------------------------
% Citations use natbib + alpha-local.bst style via BibTeX

%---------------------------- Custom Preamble --------------------------------
{preamble_content}

%---------------------------- Title ------------------------------------------
\\title{{{title}{subtitle_block}}}
\\author{{{author_line}}}
\\date{{}}

%==============================================================================
\\begin{{document}}
{extra_layout}
\\maketitle
{doi_line}
{abstract_section}
{toc_section}
{latex_body}

\\bibliographystyle{{alpha-local}}
\\bibliography{{refs}}

\\end{{document}}
"""
    return document


def compile_pdf(tex_file: Path, output_pdf: Path, working_dir: Path, meta_dir: Optional[Path] = None):
    """Compile LaTeX to PDF using pdflatex + bibtex.

    Args:
        tex_file: Path to .tex file
        output_pdf: Desired output PDF path
        working_dir: Directory containing refs.bib and .bst files
    """
    stem = tex_file.stem

    # Copy refs.bib and .bst files to working directory if needed
    if meta_dir is None:
        meta_dir = Path("meta")

    if not (working_dir / "refs.bib").exists():
        (working_dir / "refs.bib").write_text((meta_dir / "refs.bib").read_text())

    for bst_file in meta_dir.glob("*.bst"):
        if not (working_dir / bst_file.name).exists():
            (working_dir / bst_file.name).write_text(bst_file.read_text())

    # Run pdflatex + bibtex pipeline
    # Note: pdflatex can return non-zero even on success (warnings), so we check PDF existence instead
    for cmd in [
        ["pdflatex", "-interaction=nonstopmode", tex_file.name],
        ["bibtex", stem],
        ["pdflatex", "-interaction=nonstopmode", tex_file.name],
        ["pdflatex", "-interaction=nonstopmode", tex_file.name],
    ]:
        subprocess.run(cmd, cwd=working_dir, capture_output=True)

    # Check if PDF was successfully created
    pdf_file = working_dir / f"{stem}.pdf"
    if not pdf_file.exists():
        raise RuntimeError(f"PDF not created. Check {working_dir}/{stem}.log for errors")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_file.read_bytes())


def find_project_root(start: Path) -> Path:
    """Find project root by walking up from start looking for mkdocs.yml or meta/refs.bib."""
    d = start.resolve()
    if d.is_file():
        d = d.parent
    while d != d.parent:
        if (d / "mkdocs.yml").exists() or (d / "meta" / "refs.bib").exists():
            return d
        d = d.parent
    return start.resolve().parent


def export_markdown(input_file: Path, output_dir: Path, compile_to_pdf: bool = False, mobile: bool = False, project_dir: Optional[Path] = None):
    """Core export function."""
    # Validate input
    if not input_file.exists():
        click.echo(f"Error: Input file '{input_file}' not found", err=True)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    # Output paths
    basename = input_file.stem
    output_tex = output_dir / f"{basename}.tex"
    output_pdf = output_dir / f"{basename}.pdf"

    # Paths
    lua_filter = Path(__file__).parent / "pandoc-environments.lua"

    if project_dir is None:
        project_dir = find_project_root(input_file)
    click.echo(f"Project root: {project_dir}")
    bib_file = project_dir / "meta" / "refs.bib"

    if not lua_filter.exists():
        click.echo(f"Error: Lua filter not found: {lua_filter}", err=True)
        return 1

    # Read and parse input
    click.echo(f"Reading: {input_file}")
    content = input_file.read_text()
    meta, body = parse_frontmatter(content)

    # Step 1: Preprocess markdown
    click.echo("Preprocessing markdown...")
    preprocessed = preprocess_markdown(body)

    # Step 2: Convert to LaTeX via pandoc
    click.echo("Converting to LaTeX via pandoc...")
    latex_body = pandoc_to_latex(preprocessed, lua_filter, bib_file)

    # Step 3: Wrap in complete document
    click.echo("Wrapping in LaTeX document...")

    preamble_path = project_dir / 'docs' / 'preamble.tex'
    if preamble_path.exists():
        click.echo(f"Using preamble: {preamble_path}")
    else:
        click.echo("No preamble.tex found; using default settings")
        preamble_path = None

    # Construct canonical_url from mkdocs.yml canonical_base + slug
    if not meta.get('canonical_url') and meta.get('slug'):
        mkdocs_yml = project_dir / 'mkdocs.yml'
        if mkdocs_yml.exists():
            import yaml
            with open(mkdocs_yml) as f:
                mkdocs_config = yaml.safe_load(f)
            canonical_base = (mkdocs_config.get('extra', {}) or {}).get('canonical_base', '')
            if canonical_base:
                meta['canonical_url'] = canonical_base + meta['slug']

    latex_document = wrap_latex_document(meta, latex_body, preamble_path, mobile=mobile)

    # Step 4: Save .tex file
    output_tex.write_text(latex_document)
    click.echo(f"Created: {output_tex}")

    # Step 5: Compile to PDF (if requested)
    if compile_to_pdf:
        click.echo("Compiling PDF...")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / f"{basename}.tex"
            tex_file.write_text(latex_document)

            compile_pdf(tex_file, output_pdf, tmp_path, meta_dir=project_dir / "meta")

        click.echo(f"Created: {output_pdf}")

    return 0


@click.group()
def cli():
    """Export markdown articles to LaTeX and PDF."""
    pass


@cli.command('export-tex')
@click.argument('input', type=click.Path(exists=True, path_type=Path))
@click.option('-o', '--output-dir', type=click.Path(path_type=Path), help='Output directory (default: build/pdf)')
@click.option('-p', '--project-dir', type=click.Path(exists=True, path_type=Path), help='Project root (default: auto-detect from input)')
def export_tex(input: Path, output_dir: Optional[Path], project_dir: Optional[Path]):
    """Export to LaTeX (.tex) only."""
    if not output_dir:
        root = project_dir or find_project_root(input)
        output_dir = root / "build" / "pdf"

    sys.exit(export_markdown(input, output_dir, compile_to_pdf=False, project_dir=project_dir))


@cli.command('export-pdf')
@click.argument('input', type=click.Path(exists=True, path_type=Path))
@click.option('-o', '--output-dir', type=click.Path(path_type=Path), help='Output directory (default: build/pdf)')
@click.option('-p', '--project-dir', type=click.Path(exists=True, path_type=Path), help='Project root (default: auto-detect from input)')
def export_pdf(input: Path, output_dir: Optional[Path], project_dir: Optional[Path]):
    """Export to both LaTeX (.tex) and PDF."""
    if not output_dir:
        root = project_dir or find_project_root(input)
        output_dir = root / "build" / "pdf"

    sys.exit(export_markdown(input, output_dir, compile_to_pdf=True, project_dir=project_dir))


@cli.command('export-pdf-mobile')
@click.argument('input', type=click.Path(exists=True, path_type=Path))
@click.option('-o', '--output-dir', type=click.Path(path_type=Path), help='Output directory (default: build/pdf-mobile)')
@click.option('-p', '--project-dir', type=click.Path(exists=True, path_type=Path), help='Project root (default: auto-detect from input)')
def export_pdf_mobile(input: Path, output_dir: Optional[Path], project_dir: Optional[Path]):
    """Export to PDF optimized for iPhone 14 screen (80×170mm, 8pt)."""
    if not output_dir:
        root = project_dir or find_project_root(input)
        output_dir = root / "build" / "pdf-mobile"

    sys.exit(export_markdown(input, output_dir, compile_to_pdf=True, mobile=True, project_dir=project_dir))


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    exit(main())
