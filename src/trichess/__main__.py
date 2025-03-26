import click
from trichess import Board, AppMPL


@click.command(help="show board coords.")
def show():
    board = Board()
    app = AppMPL(board)
    app.show_board()


@click.command(help="run board interactive.")
def run():
    board = Board()
    app = AppMPL(board)
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
