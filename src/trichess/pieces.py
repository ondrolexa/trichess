from typing import Self


class Pos:
    """A class to represent axial coordinates on trichess board.

    Args:
        q (int): first coordinate
        r (int): second coordinate
        code (str): Attribute used by piece move to classify positions

    Attributes:
        value (complex): A complex number representing position
        code (str): Attribute used by piece move to classify positions
        q (float): first coordinate
        r (float): second coordinate

    """

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

    def from_deltas(self, deltas: list, code="s") -> Self:
        """Return new position calculated from current one and list of deltas."""
        res = self.value + sum(deltas)
        return Pos(res.real, res.imag, code=code)


class Move:
    """A class to represent movement on trichesboard

    Args:
        *args (str): any number of step codes.
        code (str): Type of move. One of s, a or n

    Attributes:
        steos (tuple): tuple of step codes.
        code (str): Type of move. One of s, a or n

    """

    def __init__(self, *args, code="s"):
        self.steps = args
        self.code = code


class Piece:
    """A class to represent trichess piece

    Args:
        symbol (str): A character used to show piece on matplotlib UI
        label (str): A character used to show piece in terminal and log
        player (Player): Player is owner of piece
        used (bool, optional): Whether the piece have been moved in current game
        hex (Hex, optional): Cell on which piece is placed or None

    Attributes:
        symbol (str): A character used to show piece on matplotlib UI
        label (str): A character used to show piece in terminal and log
        player (Player): Player is owner of piece
        used (bool): Whether the piece have been moved in current game
        hex (Hex): Cell on which piece is placed or None
        pos (Pos): Position of piece or None
        special_attack (bool): True when piece has special moves to attack

    """

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

    def pos_candidates(self) -> list[Pos]:
        """Returns list of new position candidates"""
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
