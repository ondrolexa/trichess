from math import sqrt

import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
from matplotlib.widgets import Button

from trichess import GameAPI, Hex

player_lbs_prop = dict(
    ha="center",
    va="top",
    visible=False,
    rotation_mode="anchor",
    fontsize=12,
)


class App:
    def __init__(self, api=None):
        if api is None:
            self.ga = GameAPI()
            self.ga.new_game()
        else:
            self.ga = api


class AppMPL(App):
    """Run app using matplotlib"""

    colors = ["#ffffffff", "#009fffff", "#ff7171ff"]

    def __init__(self, api=None):
        super().__init__(api=None)
        self.selected_hex = None
        self.patch = {}
        self.piece = {}
        self.move_in_progress = {}
        self.title = None

    def get_hex_xy(self, h):
        return h.pos.q + 0.5 * h.pos.r, -h.pos.r * sqrt(3) / 2

    def get_hex_color(self, h):
        return AppMPL.colors[h.color]

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

    def clear_hex(self, hex):
        # reset edge color
        self.patch[hex.gid].set_edgecolor("k")
        self.patch[hex.gid].set_linewidth(1)
        self.patch[hex.gid].set_zorder(1)

    def set_hex_selected(self, hex):
        if self.selected_hex is not None:
            self.clear_hex(self.selected_hex)
        self.selected_hex = hex
        # set edge color
        self.patch[hex.gid].set_edgecolor("yellow")
        self.patch[hex.gid].set_linewidth(3)
        self.patch[hex.gid].set_zorder(2)

    def set_hex_safe(self, hex):
        # set edge color
        self.patch[hex.gid].set_edgecolor("green")
        self.patch[hex.gid].set_linewidth(3)
        self.patch[hex.gid].set_zorder(3)

    def set_hex_attack(self, hex):
        # set edge color
        self.patch[hex.gid].set_edgecolor("red")
        self.patch[hex.gid].set_linewidth(3)
        self.patch[hex.gid].set_zorder(4)

    def update_symbol(self, hex):
        self.piece[hex.gid].set_text(hex.piece.symbol if hex.piece is not None else "")

    def show_board(self):
        """Show board with axial coordinates"""
        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess coordinates", figsize=(8, 7))
        for h in self.ga.board:
            patch = self.create_hex_patch(h)
            ax.add_patch(patch)
            x, y = self.get_hex_xy(h)
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

        def on_pick(event):
            gid = event.artist.get_gid()
            h = self.ga.board[gid]
            if self.move_in_progress:
                if h in self.move_in_progress["targets"]:
                    self.player_labels[self.ga.on_move].set_visible(False)
                    self.ga.make_move(self.move_in_progress["from"], h)
                    self.update_symbol(self.move_in_progress["from"])
                    self.update_symbol(h)
                self.clear_hex(self.move_in_progress["from"])
                for nh in self.move_in_progress["targets"]:
                    self.clear_hex(nh)
                self.move_in_progress = {}
            else:
                self.set_hex_selected(h)
                ok, moves = self.ga.get_moves(h)
                if ok and moves:
                    self.move_in_progress["from"] = h
                    self.move_in_progress["targets"] = []
                    for pos in moves:
                        if not self.ga.board[pos].has_piece:
                            self.set_hex_safe(self.ga.board[pos])
                            self.move_in_progress["targets"].append(self.ga.board[pos])
                        else:
                            if h.piece.special_attack:
                                if pos.code == "a":
                                    self.set_hex_attack(self.ga.board[pos])
                                    self.move_in_progress["targets"].append(
                                        self.ga.board[pos]
                                    )
                            else:
                                self.set_hex_attack(self.ga.board[pos])
                                self.move_in_progress["targets"].append(
                                    self.ga.board[pos]
                                )
            self.player_labels[self.ga.on_move].set_visible(True)
            self.title.set_text(f"Move: {self.ga.move_number}")
            fig.canvas.draw()

        def undo(event):
            self.player_labels[self.ga.on_move].set_visible(False)
            self.ga.undo()
            self.player_labels[self.ga.on_move].set_visible(True)
            self.title.set_text(f"Move: {self.ga.move_number}")
            for h in self.ga.board:
                self.update_symbol(h)
            fig.canvas.draw()

        plt.rcParams["toolbar"] = "None"
        plt.rcParams["figure.constrained_layout.use"] = True
        fig, ax = plt.subplots(num="TriChess")
        for h in self.ga.board:
            patch = self.create_hex_patch(h, gid=h.gid)
            patch.set_picker(2)
            ax.add_patch(patch)
            self.patch[h.gid] = patch
            self.piece[h.gid] = ax.text(
                *self.get_hex_xy(h),
                h.piece.symbol if h.piece is not None else "",
                ha="center",
                va="center",
                size="xx-large",
                zorder=5,
            )
        # undo button
        btnax = plt.axes([0.85, 0.9, 0.1, 0.05])
        btn = Button(btnax, "Undo")
        btn.on_clicked(undo)
        # set limits to fit
        ax.set_xlim(-8, 8)
        ax.set_ylim(-8, 8)
        ax.set_aspect(1)
        # hide axes
        ax.set_axis_off()
        self.title = ax.set_title(f"Move: {self.ga.move_number}")
        self.player_labels = [
            ax.text(0, -7.2, self.ga.players[0].name, **player_lbs_prop),
            ax.text(-7, 3.46, self.ga.players[1].name, rotation=60, **player_lbs_prop),
            ax.text(7, 3.46, self.ga.players[2].name, rotation=-60, **player_lbs_prop),
        ]
        self.player_labels[self.ga.on_move].set_visible(True)
        # connect pick event
        fig.canvas.mpl_connect("pick_event", on_pick)
        plt.show()
