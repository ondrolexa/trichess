"""
trichess log BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJGOKGBGDINFMFKGCKDIHGOGIJDNEMDEIJNBLBBOCMIJKIODNFFOGLKIGIOHKLINJMGIGDOBKDEODNGBIDNEJGCNELIDOANFMECKALOAIDMEHODOCNBHBJHOMEDLEKBJALNALCCMDKAHCHMELEAODOHGLENDLEDKFJCIDINCMDCNAOFCGEKJJKDNDIAIBIKDHADIDFEDFCKLKHDFLBCHKH
"""

import click

from trichess.ui import AppMPL


@click.command(help="show board coords.")
@click.option("--gid", default=False)
@click.option("--name0", default="James")
@click.option("--name1", default="Mary")
@click.option("--name2", default="Michael")
@click.option("--view_player", default=0)
def show(gid: bool, name0: str, name1: str, name2: str, view_player: int):
    app = AppMPL(name0=name0, name1=name1, name2=name2, view_player=view_player)
    app.show_board(show_gid=gid)


@click.command(help="run board interactive.")
@click.option("--name0", default="James")
@click.option("--name1", default="Mary")
@click.option("--name2", default="Michael")
@click.option("--view_player", default=0)
def run(name0: str, name1: str, name2: str, view_player: int):
    app = AppMPL(name0=name0, name1=name1, name2=name2, view_player=view_player)
    app.run()


@click.command(help="run game from log.")
@click.argument("slog")
@click.option("--name0", default="James")
@click.option("--name1", default="Mary")
@click.option("--name2", default="Michael")
@click.option("--view_player", default=0)
def log(slog: str, name0: str, name1: str, name2: str, view_player: int):
    app = AppMPL(
        slog=slog, name0=name0, name1=name1, name2=name2, view_player=view_player
    )
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
cli.add_command(log)
