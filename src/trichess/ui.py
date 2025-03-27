from math import sqrt

import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon


class App:
    def __init__(self, gm):
        self.gm = gm


class AppMPL(App):
    """Run app using matplotlib"""

    colors = ["#ffffffff", "#009fffff", "#ff7171ff"]

    def __init__(self, gm):
        super().__init__(gm)
        self.selected_patch = None
        self.patch = {}
        self.piece = {}
        self.ongoing = {}
        self.move_arrows = {}

    def get_hex_xy(self, h):
        return h.pos.q + 0.5 * h.pos.r, -h.pos.r * sqrt(3) / 2

    def get_hex_color(self, h):
        return AppMPL.colors[h.color]

    def get_hex_patch(self, h, gid="_"):
        return RegularPolygon(
            self.get_hex_xy(h),
            numVertices=6,
            radius=sqrt(1 / 3),
            fc=self.get_hex_color(h),
            ec="k",
            zorder=1,
            gid=gid,
        )

    def clear_patch(self, gid):
        # reset edge color
        self.patch[gid].set_edgecolor("k")
        self.patch[gid].set_linewidth(1)
        self.patch[gid].set_zorder(1)

    def set_patch_selected(self, gid):
        if self.selected_patch is not None:
            self.clear_patch(self.selected_patch)
        self.selected_patch = gid
        # set edge color
        self.patch[gid].set_edgecolor("yellow")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(2)

    def set_patch_safe(self, gid):
        # set edge color
        self.patch[gid].set_edgecolor("green")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(3)

    def set_patch_attack(self, gid):
        # set edge color
        self.patch[gid].set_edgecolor("red")
        self.patch[gid].set_linewidth(3)
        self.patch[gid].set_zorder(3)

    def update_label(self, hex):
        self.piece[hex.gid].set_text(hex.piece.label if hex.piece is not None else "")

    def show_board(self):
        """Show board with axial coordinates"""
        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess coordinates", figsize=(8, 7))
        for h in self.gm.board:
            patch = self.get_hex_patch(h)
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
            h = self.gm.board.gid[gid]
            if self.ongoing:
                if h in self.ongoing["targets"]:
                    self.gm.finish_move(self.ongoing["from"], h)
                    self.update_label(self.ongoing["from"])
                    self.update_label(h)
                self.clear_patch(self.ongoing["from"].gid)
                for nh in self.ongoing["targets"]:
                    self.clear_patch(nh.gid)
                self.ongoing = {}
            else:
                self.set_patch_selected(gid)
                ok, moves = self.gm.prepare_move(h)
                if ok and moves:
                    self.ongoing["from"] = h
                    self.ongoing["targets"] = moves
                    for nh in moves:
                        if not nh.has_piece:
                            self.set_patch_safe(nh.gid)
                        else:
                            self.set_patch_attack(nh.gid)
            fig.canvas.draw()

        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess")
        for h in self.gm.board:
            patch = self.get_hex_patch(h, gid=h.gid)
            self.move_arrows[h.gid] = []
            patch.set_picker(2)
            ax.add_patch(patch)
            self.patch[h.gid] = patch
            self.piece[h.gid] = ax.text(
                *self.get_hex_xy(h),
                h.piece.label if h.piece is not None else "",
                ha="center",
                va="center",
            )

        # set limits to fit
        ax.set_xlim(-8, 8)
        ax.set_ylim(-8, 8)
        ax.set_aspect(1)
        # hide axes
        ax.set_axis_off()
        fig.tight_layout()
        # connect pick event
        fig.canvas.mpl_connect("pick_event", on_pick)
        plt.show()
