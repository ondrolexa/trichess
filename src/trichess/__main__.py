import click

from trichess import AppMPL


@click.command(help="show board coords.")
def show():
    app = AppMPL()
    app.show_board()


@click.command(help="run board interactive.")
def run():
    app = AppMPL()
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
