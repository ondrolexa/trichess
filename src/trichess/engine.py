from typing import Self

STEP = {
    0: {
        "FL": 0 - 1j,
        "FR": 1 - 1j,
        "SL": -1 + 0j,
        "DF": 1 - 2j,
        "DL": -1 - 1j,
        "DR": 2 - 1j,
    },
    1: {
        "FL": -1 + 1j,
        "FR": -1 + 0j,
        "SL": 0 + 1j,
        "DF": -2 + 1j,
        "DL": -1 + 2j,
        "DR": -1 - 1j,
    },
    2: {
        "FL": 1 + 0j,
        "FR": 0 + 1j,
        "SL": 1 - 1j,
        "DF": 1 + 1j,
        "DL": 2 - 1j,
        "DR": -1 + 2j,
    },
}


class Pos:
    def __init__(self, q, r):
        self.value = complex(q, r)

    def __eq__(self, another):
        return hasattr(another, "value") and self.value == another.value

    def __hash__(self):
        return hash((self.value, abs(self.value)))

    def __repr__(self) -> str:
        return f"Pos({self.q:g},{self.r:g})"

    @property
    def q(self) -> float:
        return self.value.real

    @property
    def r(self) -> float:
        return self.value.imag

    def from_deltas(self, deltas) -> Self:
        res = self.value + sum(deltas)
        return Pos(res.real, res.imag)


class Move:
    def __init__(self, *args):
        self.steps = args


class Piece:
    def __init__(self, label, player, **kwargs):
        self.label = label
        self.player = player
        self.used = kwargs.get("used", 0)
        self.hex = kwargs.get("hex", None)
        self.jump = kwargs.get("jump", False)

    def __repr__(self) -> str:
        if self.hex is None:
            return f"{self.label}{self.player} (not placed)"
        else:
            return f"{self.label}{self.player} {self.hex.pos}"

    @property
    def pos(self) -> Pos:
        if self.hex is not None:
            return self.hex.pos

    def moves(self) -> list[Pos]:
        if self.hex is not None:
            return [self.player.pos_from_move(self.pos, move) for move in self._moves]


class Pawn(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("P", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        moves = [Move("FL"), Move("FR")]
        if not self.used:
            moves.extend(
                [
                    Move("FL", "FL"),
                    Move("FR", "FR"),
                ]
            )
        return moves


class Knight(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("K", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        moves = [
            Move("SL", "SL", "FRr"),
            Move("SL", "SL", "FL"),
            Move("FL", "FL", "SL"),
            Move("FL", "FL", "FR"),
            Move("FR", "FR", "FL"),
            Move("FR", "FR", "SLr"),
            Move("SLr", "SLr", "FR"),
            Move("SLr", "SLr", "FLr"),
            Move("FLr", "FLr", "SLr"),
            Move("FLr", "FLr", "FRr"),
            Move("FRr", "FRr", "FLr"),
            Move("FRr", "FRr", "SL"),
        ]
        return moves


class Player:
    def __init__(self, pid, **kwargs):
        self.pid = pid
        self.name = kwargs.get("name", f"Player {pid}")

    def __repr__(self) -> str:
        return f"[{self.name}]"

    def step(self, step) -> complex:
        match step:
            case "FL":
                return STEP[self.pid]["FL"]
            case "FLr":
                return -STEP[self.pid]["FL"]
            case "FR":
                return STEP[self.pid]["FR"]
            case "FRr":
                return -STEP[self.pid]["FR"]
            case "SL":
                return STEP[self.pid]["SL"]
            case "SLr":
                return -STEP[self.pid]["SL"]
            case "DF":
                return STEP[self.pid]["DF"]
            case "DFr":
                return -STEP[self.pid]["DF"]
            case "DL":
                return STEP[self.pid]["DL"]
            case "DLr":
                return -STEP[self.pid]["DL"]
            case "DR":
                return STEP[self.pid]["DR"]
            case "DRr":
                return -STEP[self.pid]["DR"]
            case "_":
                raise ValueError(f"Step code {step} not recognized")

    def pos_from_move(self, pos, move) -> Pos:
        return pos.from_deltas([self.step(step) for step in move.steps])

    def pawn(self, **kwargs) -> Pawn:
        return Pawn(self, **kwargs)

    def knight(self, **kwargs) -> Knight:
        return Knight(self, **kwargs)


class Hex:
    """Trichess board cell"""

    def __init__(self, pos, gid):
        self.pos = pos
        self.gid = gid
        self.piece = None

    def __repr__(self) -> str:
        return f"Hex({self.pos.q:g},{self.pos.r:g})[{self.gid}]"

    @property
    def color(self) -> int:
        return int(2 * self.pos.q + self.pos.r) % 3


class Board:
    """Class to store current trichess board"""

    def __init__(self, **kwargs):
        # board dict
        self.board = {}
        self.gid = {}
        # setup players
        self.player0 = kwargs.get("player0", Player(0))
        self.player1 = kwargs.get("player1", Player(1))
        self.player2 = kwargs.get("player2", Player(2))
        # generate all cells
        gid = 0
        for q in range(-7, 8):
            for r in range(-7, 8):
                # check whether on board
                s = -q - r
                if -7 <= s <= 7:
                    pos = Pos(q, r)
                    sgid = str(gid)
                    self.board[pos] = Hex(pos, sgid)
                    self.gid[sgid] = self.board[pos]
                    gid += 1
        self.init_pieces()

    def init_pieces(self):
        # place pawns
        for i in range(-7, -3):
            self.place_piece(Pos(i, 6), self.player0.pawn)
            self.place_piece(Pos(6, i), self.player1.pawn)
            self.place_piece(Pos(i, -6 - i), self.player2.pawn)
        for i in range(-2, 2):
            self.place_piece(Pos(i, 6), self.player0.pawn)
            self.place_piece(Pos(6, i), self.player1.pawn)
            self.place_piece(Pos(i, -6 - i), self.player2.pawn)
        # place knights
        self.place_piece(Pos(-5, 7), self.player0.knight)
        self.place_piece(Pos(-2, 7), self.player0.knight)
        self.place_piece(Pos(-2, -5), self.player1.knight)
        self.place_piece(Pos(-5, -2), self.player1.knight)
        self.place_piece(Pos(7, -2), self.player2.knight)
        self.place_piece(Pos(7, -5), self.player2.knight)

    def __iter__(self) -> iter:
        return iter(self.board.values())

    def __getitem__(self, pos) -> Hex:
        return self.board[pos]

    def place_piece(self, pos, piece) -> Piece:
        self.board[pos].piece = piece(hex=self.board[pos])

    def hexs_from_piece(self, piece) -> list[Hex]:
        return [self.board[dest] for dest in piece.moves() if dest in self.board]
