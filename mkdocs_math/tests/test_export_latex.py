"""
Unit tests for the PDF export LaTeX generation (mkdocs_math/export.py).

These test the string-transform functions directly -- no pandoc or
pdflatex invocation needed.
"""

from mkdocs_math.export import fix_dangling_qed, wrap_latex_document


class TestFixDanglingQed:
    """fix_dangling_qed strips the blank line pandoc emits before \\end{proof},
    which otherwise force-closes the paragraph before amsthm's \\qed fires,
    orphaning the QED mark on its own line regardless of available width.
    """

    def test_strips_blank_line_before_end_proof(self):
        latex = (
            "\\begin{proof}\n"
            "\n"
            "Short sentence.\n"
            "\n"
            "\\end{proof}\n"
        )
        result = fix_dangling_qed(latex)
        assert "\n\\end{proof}" in result
        assert "\n\n\\end{proof}" not in result

    def test_leaves_unrelated_blank_lines_alone(self):
        latex = (
            "\\begin{proof}\n"
            "\n"
            "First paragraph.\n"
            "\n"
            "Second paragraph.\n"
            "\n"
            "\\end{proof}\n"
        )
        result = fix_dangling_qed(latex)
        assert "First paragraph.\n\nSecond paragraph." in result
        assert "Second paragraph.\n\\end{proof}" in result

    def test_handles_multiple_proofs(self):
        latex = (
            "\\begin{proof}\n\nOne.\n\n\\end{proof}\n\n"
            "\\begin{theorem}\nStatement.\n\\end{theorem}\n\n"
            "\\begin{proof}\n\nTwo.\n\n\\end{proof}\n"
        )
        result = fix_dangling_qed(latex)
        assert result.count("\n\n\\end{proof}") == 0
        assert result.count("\\end{proof}") == 2

    def test_proof_ending_in_a_list(self):
        # pandoc converts "1) ... 2) ..." proof bodies into \begin{enumerate};
        # the blank line still lands right before \end{proof} in that case.
        latex = (
            "\\begin{proof}\n"
            "\n"
            "\\begin{enumerate}\n"
            "\\item One.\n"
            "\\end{enumerate}\n"
            "\n"
            "\\end{proof}\n"
        )
        result = fix_dangling_qed(latex)
        assert "\\end{enumerate}\n\\end{proof}" in result

    def test_no_proof_environments_is_a_noop(self):
        latex = "Some text with no proofs at all.\n"
        assert fix_dangling_qed(latex) == latex
