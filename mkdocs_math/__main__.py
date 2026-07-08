"""Entry point for python -m mkdocs_math."""

import click
from .export import cli as export_cli
from .lint import lint_cmd


@click.group()
def cli():
    """mkdocs-math: tools for math article production."""
    pass


# Register export subcommands
for _name in list(export_cli.list_commands(None)):
    _cmd = export_cli.get_command(None, _name)
    if _cmd:
        cli.add_command(_cmd, _name)

# Register lint
cli.add_command(lint_cmd, 'lint')


def main():
    cli()


if __name__ == '__main__':
    exit(main())
