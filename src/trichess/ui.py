from math import sqrt
import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon


class App:
    def __init__(self, board):
        self.board = board


class AppMPL(App):
    """Run app using matplotlib"""

    colors = ["#ffffffff", "#009fffff", "#ff7171ff"]

    def __init__(self, board):
        super().__init__(board)
        self.selected_patch = None
        self.move_arrows = {}

    def get_hex_xy(self, h):
        return h.pos.q + 0.5 * h.pos.r, -h.pos.r * sqrt(3) / 2

    def get_hex_color(self, h):
        return AppMPL.colors[h.color]

    def get_hex_patch(self, h, gid="_"):
        patch = RegularPolygon(
            self.get_hex_xy(h),
            numVertices=6,
            radius=sqrt(1 / 3),
            fc=self.get_hex_color(h),
            ec="k",
        )
        patch.set_gid(gid)
        return patch

    def reset_patch(self, patch):
        gid = patch.get_gid()
        # clear move hints
        while self.move_arrows[gid]:
            self.move_arrows[gid].pop().remove()
        # reset edge color
        patch.set_edgecolor("k")
        patch.set_linewidth(1)
        patch.set_zorder(1)

    def select_patch(self, patch):
        gid = patch.get_gid()
        # set edge color
        patch.set_edgecolor("yellow")
        patch.set_linewidth(3)
        patch.set_zorder(2)
        return gid

    def show_board(self):
        """Show board with axial coordinates"""
        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess coordinates")
        for h in self.board:
            patch = self.get_hex_patch(h)
            ax.add_patch(patch)
            x, y = self.get_hex_xy(h)
            ax.text(x, y, f"{h.qr.real:g},{h.qr.imag:g}", ha="center", va="center")

        # set limits to fit
        ax.set_xlim(-8, 8)
        ax.set_ylim(-8, 8)
        ax.set_aspect(1)
        # hide axes
        ax.set_axis_off()
        fig.tight_layout()
        plt.show()

    def run(self):
        """Show board and possible moves for selected Piece"""

        def on_pick(event):
            if self.selected_patch is not None:
                self.reset_patch(self.selected_patch)
            self.selected_patch = event.artist
            gid = self.select_patch(self.selected_patch)
            h = self.board.gid[gid]
            if h.piece is not None:
                for nh in self.board.hexs_from_piece(h.piece):
                    self.move_arrows[gid].append(
                        ax.annotate(
                            "",
                            xytext=self.get_hex_xy(h),
                            xy=self.get_hex_xy(nh),
                            arrowprops=dict(arrowstyle="->"),
                        )
                    )
            fig.canvas.draw()

        plt.rcParams["toolbar"] = "None"
        fig, ax = plt.subplots(num="TriChess")
        for h in self.board:
            patch = self.get_hex_patch(h, gid=h.gid)
            self.move_arrows[h.gid] = []
            patch.set_picker(2)
            ax.add_patch(patch)
            x, y = self.get_hex_xy(h)
            # Draw piece label
            if h.piece is not None:
                ax.text(x, y, h.piece.label, ha="center", va="center")

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
