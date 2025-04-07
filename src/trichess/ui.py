from math import sqrt

import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
from matplotlib.widgets import Button

from trichess import GameAPI

player_lbs_prop = dict(
    ha="center",
    va="top",
    visible=False,
    rotation_mode="anchor",
    fontsize=12,
)


class App:
    def __init__(self, name0, name1, name2, slog):
        self.ga = GameAPI(name0=name0, name1=name1, name2=name2)
        if slog is not None:
            self.ga.replay_from_string(slog)


class AppMPL(App):
    """Run app using matplotlib"""

    # hex_colors = ["#ffffffff", "#009fffff", "#ff7171ff"]
    hex_colors = ["#a8baf0", "#f0b6a8", "#d1f0a8"]
    piece_colors = ["#000599", "#B33900", "#1D6600"]

    def __init__(self, slog=None, name0="Player 0", name1="Player 1", name2="Player 2"):
        super().__init__(name0, name1, name2, slog)
        self.selected_hex = None
        self.patch = {}
        self.piece = {}
        self.move_in_progress = {}
        self.title = None

    def get_hex_xy(self, h):
        return h.pos.q + 0.5 * h.pos.r, -h.pos.r * sqrt(3) / 2

    def get_hex_color(self, hex):
        return AppMPL.hex_colors[hex.color]

    def get_piece_color(self, piece):
        return AppMPL.piece_colors[piece.player.pid]

    def create_hex_patch(self, h, gid="_"):
        return RegularPolygon(
            self.get_hex_xy(h),
            numVertices=6,
            radius=sqrt(1 / 3),
            fc=self.get_hex_color(h),
            ec="k",
            zorder=1,
            gid=gid,
        )

    def clear_hex(self, gid):
        # reset edge color
        self.patch[gid].set_edgecolor("k")
        self.patch[gid].set_linewidth(1)
        self.patch[gid].set_zorder(1)

    def set_hex_selected(self, gid):
        if self.selected_hex is not None:
            self.clear_hex(self.selected_hex)
        self.selected_hex = gid
        # set edge color
        self.patch[gid].set_edgecolor("yellow")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(2)

    def set_hex_safe(self, gid):
        # set edge color
        self.patch[gid].set_edgecolor("green")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(3)

    def set_hex_attack(self, gid):
        # set edge color
        self.patch[gid].set_edgecolor("red")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(4)

    def update_symbol(self, gid):
        hex = self.ga.gid2hex[gid]
        self.piece[gid].set_text(hex.piece.symbol if hex.piece is not None else "")
        self.piece[gid].set_color(
            self.get_piece_color(hex.piece)
            if hex.piece is not None
            else self.get_hex_color(hex)
        )

    def show_board(self, gid=False):
        """Show board with axial coordinates"""
        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess coordinates", figsize=(8, 7))
        for h in self.ga.board:
            patch = self.create_hex_patch(h)
            ax.add_patch(patch)
            x, y = self.get_hex_xy(h)
            if gid:
                ax.text(x, y, self.ga.pos2gid[h.pos], ha="center", va="center")
            else:
                ax.text(x, y, f"{h.pos.q:g},{h.pos.r:g}", ha="center", va="center")

        # set limits to fit
        ax.set_xlim(-8, 8)
        ax.set_ylim(-8, 8)
        ax.set_aspect(1)
        # hide axes
        ax.set_axis_off()
        fig.tight_layout()
        plt.show()

    def run(self):
        """Run trichess game"""

        def update_ui(state={}):
            self.player_labels[self.ga.on_move_previous].set_visible(False)
            self.player_labels[self.ga.on_move].set_visible(True)
            self.title = ax.set_title(
                f"{self.ga.logtail(n=6)}\nMove {self.ga.move_number}"
            )
            if state:
                self.set_hex_selected(state["from"])
                if state["inmove"]:
                    for gid, color in zip(state["targets"], state["colors"]):
                        match color:
                            case "safe":
                                self.set_hex_safe(gid)
                            case "attack":
                                self.set_hex_attack(gid)
                else:
                    for gid in state["lastmove"]:
                        self.update_symbol(gid)
                    self.clear_hex(state["from"])
                    for gid in state["targets"]:
                        self.clear_hex(gid)
            fig.canvas.draw()

        def on_pick(event):
            gid = event.artist.get_gid()
            state = self.ga.gid_selected(gid)
            if state["valid_move"]:
                self.ga.make_move(*state["lastmove"])
            update_ui(state)

        def undo(event):
            self.ga.undo()
            for gid, hex in enumerate(self.ga.board):
                self.ga.gid2hex[gid] = hex
                self.update_symbol(self.ga.pos2gid[hex.pos])
            update_ui()

        def printlog(event):
            print(self.ga.log2string())

        plt.rcParams["toolbar"] = "None"
        plt.rcParams["figure.constrained_layout.use"] = True
        fig, ax = plt.subplots(num="TriChess")
        for gid, hex in enumerate(self.ga.board):
            patch = self.create_hex_patch(hex, gid=gid)
            patch.set_picker(2)
            ax.add_patch(patch)
            self.patch[gid] = patch
            self.piece[gid] = ax.text(
                *self.get_hex_xy(hex),
                hex.piece.symbol if hex.piece is not None else "",
                ha="center",
                va="center",
                size="xx-large",
                zorder=5,
            )
            self.piece[gid].set_color(
                self.get_piece_color(hex.piece)
                if hex.piece is not None
                else self.get_hex_color(hex)
            )
        # undo button
        undoax = plt.axes([0.87, 0.9, 0.1, 0.05])
        undobtn = Button(undoax, "Undo")
        undobtn.on_clicked(undo)
        # log button
        logax = plt.axes([0.87, 0.84, 0.1, 0.05])
        logbtn = Button(logax, "Log")
        logbtn.on_clicked(printlog)
        # set limits to fit
        ax.set_xlim(-8, 8)
        ax.set_ylim(-8, 8)
        ax.set_aspect(1)
        # hide axes
        ax.set_axis_off()
        self.title = ax.set_title(f"{self.ga.logtail(n=6)}\nMove {self.ga.move_number}")
        self.player_labels = [
            ax.text(0, -7.2, self.ga.players[0].name, **player_lbs_prop),
            ax.text(-7, 3.46, self.ga.players[1].name, rotation=60, **player_lbs_prop),
            ax.text(7, 3.46, self.ga.players[2].name, rotation=-60, **player_lbs_prop),
        ]
        self.player_labels[self.ga.on_move].set_visible(True)
        # connect pick event
        fig.canvas.mpl_connect("pick_event", on_pick)
        plt.show()
