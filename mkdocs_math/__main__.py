"""Entry point for python -m mkdocs_math."""

import click
from .export import cli as export_cli
from .lint import lint_cmd
from .outline import outline_cmd


@click.group()
def cli():
    """mkdocs-math: tools for math article production."""
    pass


# Register export subcommands
for _name in list(export_cli.list_commands(None)):
    _cmd = export_cli.get_command(None, _name)
    if _cmd:
        cli.add_command(_cmd, _name)

# Register lint and outline
cli.add_command(lint_cmd, 'lint')
cli.add_command(outline_cmd, 'outline')


@cli.command('pdf-server')
@click.option('--port', type=int, default=8099, help='Port to listen on')
@click.option('--docs-dir', type=click.Path(exists=True), default='docs', help='Docs directory')
@click.option('--project-dir', type=click.Path(exists=True), default=None, help='Project root')
def pdf_server_cmd(port, docs_dir, project_dir):
    """Start the PDF generation server."""
    from .pdf_server import serve
    serve(port, docs_dir, project_dir)


def main():
    cli()


if __name__ == '__main__':
    exit(main())
