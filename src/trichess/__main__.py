import click

from trichess import AppMPL


"""
trichess log BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJGOKGBGDINFMFKGCKDIHGOGIJDNEMDEIJNBLBBOCMIJKIODNFFOGLKIGIOHKLINJMGIGDOBKDEODNGBIDNEJGCNELIDOANFMECKALOAIDMEHODOCNBHBJHOMEDLEKBJALNALCCMDKAHCHMELEAODOHGLENDLEDKFJCIDINCMDCNAOFCGEKJJKDNDIAIBIKDHADIDFEDFCKLKHDFLBCHKH
"""


@click.command(help="show board coords.")
@click.argument("gid", required=False)
def show(gid=False):
    app = AppMPL()
    app.show_board(gid=gid)


@click.command(help="run board interactive.")
@click.argument("name0", default="James")
@click.argument("name1", default="Mary")
@click.argument("name2", default="Michael")
def run(name0: str, name1: str, name2: str):
    app = AppMPL(name0=name0, name1=name1, name2=name2)
    app.run()


@click.command(help="run game from log.")
@click.argument("slog")
@click.argument("name0", default="James")
@click.argument("name1", default="Mary")
@click.argument("name2", default="Michael")
def log(slog: str, name0: str, name1: str, name2: str):
    app = AppMPL(slog=slog, name0=name0, name1=name1, name2=name2)
    app.run()


@click.group()
def cli():
    pass


cli.add_command(show)
cli.add_command(run)
cli.add_command(log)
