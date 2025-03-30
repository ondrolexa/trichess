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


@click.command(help="run game from log.")
@click.argument("slog")
def log(slog: str):
    app = AppMPL(slog=slog)
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
cli.add_command(log)
