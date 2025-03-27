import click

from trichess import AppMPL, GameManager


@click.command(help="show board coords.")
def show():
    gm = GameManager()
    gm.new_game()
    app = AppMPL(gm)
    app.show_board()


@click.command(help="run board interactive.")
def run():
    gm = GameManager()
    gm.new_game()
    app = AppMPL(gm)
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
