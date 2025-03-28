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
        "FL": 1 + 0j,
        "FR": 0 + 1j,
        "SL": 1 - 1j,
        "DF": 1 + 1j,
        "DL": 2 - 1j,
        "DR": -1 + 2j,
    },
    2: {
        "FL": -1 + 1j,
        "FR": -1 + 0j,
        "SL": 0 + 1j,
        "DF": -2 + 1j,
        "DL": -1 + 2j,
        "DR": -1 - 1j,
    },
}


class Pos:
    def __init__(self, q, r, code="s"):
        self.value = complex(q, r)
        self.code = code

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

    def from_deltas(self, deltas, code="s") -> Self:
        res = self.value + sum(deltas)
        return Pos(res.real, res.imag, code=code)


class Move:
    def __init__(self, *args, code="s"):
        self.steps = args
        self.code = code


class Piece:
    def __init__(self, symbol, label, player, **kwargs):
        self.symbol = symbol
        self.label = label
        self.player = player
        self.used = kwargs.get("used", False)
        self.hex = kwargs.get("hex", None)
        self.special_attack = False

    def __repr__(self) -> str:
        if self.hex is None:
            return f"{self.label}{self.player} (not placed)"
        else:
            return f"{self.label}{self.player} {self.hex.pos}"

    @property
    def pos(self) -> Pos:
        if self.hex is not None:
            return self.hex.pos

    def reachable(self) -> list[Pos]:
        if self.hex is not None:
            res = []
            for move in self._moves:
                if move.code != "n":
                    res.append(self.player.pos_from_move(self.pos, move))
                else:
                    pos = self.pos
                    for i in range(1, 15):
                        pos = self.player.pos_from_move(pos, move)
                        if pos in self.hex.board:
                            if self.hex.board[pos].has_piece:
                                if self.player is not self.hex.board[pos].piece.player:
                                    res.append(pos)
                                break
                            res.append(pos)
                        else:
                            break
            return res


class Pawn(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♟", "P", player, **kwargs)
        self.special_attack = True

    @property
    def _moves(self) -> list[Move]:
        moves = [
            Move("FL"),
            Move("FR"),
            Move("DL", code="a"),
            Move("DF", code="a"),
            Move("DR", code="a"),
        ]
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
        super().__init__("♞", "N", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        return [
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


class Bishop(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♝", "B", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("DL", code="n"),
            Move("DF", code="n"),
            Move("DR", code="n"),
            Move("DLr", code="n"),
            Move("DFr", code="n"),
            Move("DRr", code="n"),
        ]


class Rook(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♜", "R", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("SL", code="n"),
            Move("FL", code="n"),
            Move("FR", code="n"),
            Move("SLr", code="n"),
            Move("FLr", code="n"),
            Move("FRr", code="n"),
        ]


class Queen(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♛", "Q", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("SL", code="n"),
            Move("FL", code="n"),
            Move("FR", code="n"),
            Move("SLr", code="n"),
            Move("FLr", code="n"),
            Move("FRr", code="n"),
            Move("DL", code="n"),
            Move("DF", code="n"),
            Move("DR", code="n"),
            Move("DLr", code="n"),
            Move("DFr", code="n"),
            Move("DRr", code="n"),
        ]


class King(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♚", "K", player, **kwargs)

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("SL"),
            Move("FL"),
            Move("FR"),
            Move("SLr"),
            Move("FLr"),
            Move("FRr"),
            Move("DL"),
            Move("DF"),
            Move("DR"),
            Move("DLr"),
            Move("DFr"),
            Move("DRr"),
        ]


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
        return pos.from_deltas([self.step(step) for step in move.steps], code=move.code)

    def pawn(self, **kwargs) -> Pawn:
        return Pawn(self, **kwargs)

    def knight(self, **kwargs) -> Knight:
        return Knight(self, **kwargs)

    def bishop(self, **kwargs) -> Bishop:
        return Bishop(self, **kwargs)

    def rook(self, **kwargs) -> Rook:
        return Rook(self, **kwargs)

    def queen(self, **kwargs) -> Queen:
        return Queen(self, **kwargs)

    def king(self, **kwargs) -> King:
        return King(self, **kwargs)


class Hex:
    """Trichess board cell"""

    def __init__(self, pos, board):
        self.pos = pos
        self.board = board
        self.piece = None

    def __repr__(self) -> str:
        return f"Hex({self.pos.q:g},{self.pos.r:g})"

    @property
    def has_piece(self) -> bool:
        return True if self.piece is not None else False

    @property
    def color(self) -> int:
        return int(2 * self.pos.q + self.pos.r) % 3


class Board:
    """Class to store current trichess board"""

    def __init__(self, **kwargs):
        # board dict
        self.board = {}
        # setup players
        self.players = kwargs.get("players", [Player(0), Player(1), Player(2)])
        # generate all cells
        for q in range(-7, 8):
            for r in range(-7, 8):
                # check whether on board
                s = -q - r
                if -7 <= s <= 7:
                    pos = Pos(q, r)
                    self.board[pos] = Hex(pos, self.board)
        self.init_pieces()
        log = kwargs.get("log", [])
        for pos_from, pos_to in log:
            self.move_piece(pos_from, pos_to)

    def init_pieces(self):
        # place pawns
        for i in range(-7, -3):
            self.place_piece(Pos(i, 6), self.players[0].pawn)
            self.place_piece(Pos(i, -6 - i), self.players[1].pawn)
            self.place_piece(Pos(6, i), self.players[2].pawn)
        for i in range(-2, 2):
            self.place_piece(Pos(i, 6), self.players[0].pawn)
            self.place_piece(Pos(i, -6 - i), self.players[1].pawn)
            self.place_piece(Pos(6, i), self.players[2].pawn)
        # place knights
        self.place_piece(Pos(-5, 7), self.players[0].knight)
        self.place_piece(Pos(-2, 7), self.players[0].knight)
        self.place_piece(Pos(-2, -5), self.players[1].knight)
        self.place_piece(Pos(-5, -2), self.players[1].knight)
        self.place_piece(Pos(7, -2), self.players[2].knight)
        self.place_piece(Pos(7, -5), self.players[2].knight)
        # place bishops
        self.place_piece(Pos(-6, 7), self.players[0].bishop)
        self.place_piece(Pos(-1, 7), self.players[0].bishop)
        self.place_piece(Pos(-3, 6), self.players[0].bishop)
        self.place_piece(Pos(-1, -6), self.players[1].bishop)
        self.place_piece(Pos(-6, -1), self.players[1].bishop)
        self.place_piece(Pos(-3, -3), self.players[1].bishop)
        self.place_piece(Pos(7, -1), self.players[2].bishop)
        self.place_piece(Pos(7, -6), self.players[2].bishop)
        self.place_piece(Pos(6, -3), self.players[2].bishop)
        # place rooks
        self.place_piece(Pos(-7, 7), self.players[0].rook)
        self.place_piece(Pos(0, 7), self.players[0].rook)
        self.place_piece(Pos(0, -7), self.players[1].rook)
        self.place_piece(Pos(-7, 0), self.players[1].rook)
        self.place_piece(Pos(7, 0), self.players[2].rook)
        self.place_piece(Pos(7, -7), self.players[2].rook)
        # place queens
        self.place_piece(Pos(-3, 7), self.players[0].queen)
        self.place_piece(Pos(-4, -3), self.players[1].queen)
        self.place_piece(Pos(7, -4), self.players[2].queen)
        # place kings
        self.place_piece(Pos(-4, 7), self.players[0].king)
        self.place_piece(Pos(-3, -4), self.players[1].king)
        self.place_piece(Pos(7, -3), self.players[2].king)

    def __iter__(self) -> iter:
        return iter(self.board.values())

    def __getitem__(self, pos: Pos | int) -> Hex:
        return self.board.get(pos, None)

    def __contains__(self, pos: Pos) -> bool:
        return pos in self.board

    def place_piece(self, pos: Pos, create_piece_fn) -> Piece:
        self.board[pos].piece = create_piece_fn(hex=self.board[pos])

    def move_piece(self, pos_from, pos_to):
        piece = self.board[pos_from].piece
        piece.used = True
        piece.hex = self.board[pos_to]
        self.board[pos_to].piece = piece
        self.board[pos_from].piece = None

    def all_moves(self, piece) -> list[Pos]:
        all = []
        for dest in piece.reachable():
            if dest in self.board:
                if dest.code == "a" and self.board[dest].has_piece:
                    if self.board[dest].piece.player is not piece.player:
                        all.append(dest)
                elif dest.code == "s":
                    if self.board[dest].has_piece:
                        if self.board[dest].piece.player is not piece.player:
                            all.append(dest)
                    else:
                        all.append(dest)
                elif dest.code == "n":
                    if self.board[dest].has_piece:
                        if self.board[dest].piece.player is not piece.player:
                            all.append(dest)
                    else:
                        all.append(dest)
                else:
                    pass
        return all


class GameAPI:
    def __init__(self):
        self.ready = False
        self.log = []
        self.move_number = 0

    def new_game(self, **kwargs):
        self.players = [
            kwargs.get("player0", Player(0)),
            kwargs.get("player1", Player(1)),
            kwargs.get("player2", Player(2)),
        ]
        self.board = Board(players=self.players)
        self.ready = True

    @property
    def on_move(self):
        return self.move_number % 3

    def get_moves(self, hex):
        if self.ready:
            ok = False
            moves = []
            if self.ready:
                if hex.has_piece:
                    piece = hex.piece
                    if self.players[self.on_move] is piece.player:
                        moves = self.board.all_moves(piece)
                        ok = True
            return ok, moves

    def make_move(self, hex_from, hex_to):
        if self.ready:
            # add move to log
            self.log.append((hex_from.pos, hex_to.pos))
            # make move
            self.board.move_piece(hex_from.pos, hex_to.pos)
            self.move_number += 1

    def undo(self):
        if self.ready and self.move_number > 0:
            self.replay_from_log(self.log[:-1])

    def replay_from_log(self, log):
        self.log = log
        self.move_number = len(log)
        self.board = Board(players=self.players, log=log)
