class Pos:
    """Lightweight axial coordinate.  Stores q, r as plain ints.

    Args:
        q (int): first coordinate
        r (int): second coordinate
        kind (str): Attribute used by piece move to classify positions

    Attributes:
        kind (str): Attribute used by piece move to classify positions.
        code (str): Position encoded as two ASCII chars for slog encoding.
        q (int): first coordinate
        r (int): second coordinate

    """

    __slots__ = ("_q", "_r", "kind", "_hash")

    def __init__(self, q, r, kind="s"):
        self._q = int(q)
        self._r = int(r)
        self.kind = kind
        self._hash = hash((self._q, self._r))

    def __eq__(self, other):
        if isinstance(other, Pos):
            return self._q == other._q and self._r == other._r
        if isinstance(other, tuple):
            return self._q == other[0] and self._r == other[1]
        return NotImplemented

    def __hash__(self):
        return self._hash

    def __repr__(self) -> str:
        return f"Pos({self._q},{self._r})"

    @property
    def code(self) -> str:
        """Encode axial (q, r) as two ASCII chars offset by 72 for slog encoding."""
        return chr(72 + self._q) + chr(72 + self._r)

    @property
    def promcode(self) -> str:
        """Encode (q, r) shifted by +32 (offset 104) for promotion notation."""
        return chr(104 + self._q) + chr(104 + self._r)

    @property
    def q(self) -> int:
        return self._q

    @property
    def r(self) -> int:
        return self._r


class Move:
    """A class to represent movement on trichesboard

    Args:
        *args (str): any number of step codes.
        kind (str): Type of move: s step, f forward onto an empty cell
            only, a attack (capture) only, d pawn double step, n slide,
            c castling

    Attributes:
        steps (tuple): tuple of step codes.
        kind (str): Type of move (see Args)

    """

    def __init__(self, *args, kind="s"):
        self.steps = args
        self.kind = kind


class Piece:
    """A class to represent trichess piece

    Args:
        symbol (str): Unicode chess symbol of the piece (♟, ♞, …)
        label (str): A character used to show piece in terminal and log
        player (Player): Player is owner of piece
        used (bool, optional): Whether the piece have been moved in current game
        hex (Hex, optional): Cell on which piece is placed or None

    Attributes:
        symbol (str): Unicode chess symbol of the piece (♟, ♞, …)
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
        self.value = 0
        self.special_attack = False
        self.used = kwargs.get("used", False)
        self.hex = kwargs.get("hex", None)

    def __repr__(self) -> str:
        if self.hex is None:
            return f"{self.label}{self.player} (not placed)"
        else:
            return f"{self.label}{self.player} {self.hex.pos}"

    @property
    def _moves(self) -> list[Move]:
        raise NotImplementedError

    @property
    def pos(self) -> Pos | None:
        if self.hex is not None:
            return self.hex.pos

    def pos_candidates(self, castling: bool) -> list[Pos] | None:
        """Raw candidate positions after applying each move, before legality filtering.

        Arg:
            castling: when True, include castling moves (king two-step with rook).
        """
        if self.hex is None:
            return None
        res = []
        for move in self._moves:
            if move.kind == "c":
                if castling:
                    dest = self._castling_target(move)
                    if dest is not None:
                        res.append(dest)
            else:
                _CANDIDATES[move.kind](self, move, res)
        return res

    # One method per move kind; each appends its candidates to *res*.

    def _step(self, move, res):
        """s: a plain step, whatever stands there (Board.possible_moves filters)."""
        res.append(self.player.pos_from_move(self.pos, move))

    def _forward(self, move, res):
        """f: a step onto an empty cell only (pawn advance)."""
        dest = self.player.pos_from_move(self.pos, move)
        dk = (dest._q, dest._r)
        board = self.hex.board
        if dk in board._board and not board._has_piece(dk):
            res.append(dest)

    def _attack(self, move, res):
        """a: a step onto an occupied cell only (pawn capture)."""
        dest = self.player.pos_from_move(self.pos, move)
        dk = (dest._q, dest._r)
        board = self.hex.board
        if dk in board._board and board._has_piece(dk):
            res.append(dest)

    def _slide(self, move, res):
        """n: repeat the step until the edge or the first occupied cell (included)."""
        board = self.hex.board
        cur = self.pos
        for _ in range(14):
            dest = self.player.pos_from_move(cur, move)
            dk = (dest._q, dest._r)
            if dk not in board._board:
                break
            res.append(dest)
            if board._has_piece(dk):
                break
            cur = dest

    def _double(self, move, res):
        """d: a two-step advance with both cells empty (pawn's first move)."""
        player, pos = self.player, self.pos
        board = self.hex.board
        pos1 = player.pos_from_move(pos, Move(move.steps[0]))
        dk1 = (pos1._q, pos1._r)
        if dk1 not in board._board or board._has_piece(dk1):
            return
        pos2 = player.pos_from_move(pos, move)
        dk2 = (pos2._q, pos2._r)
        if dk2 in board._board and not board._has_piece(dk2):
            res.append(pos2)

    def _castling_target(self, move):
        """c: the king's castling destination, or None when castling that way
        is not allowed: the king is in check or has moved, the cell it
        passes or lands on is occupied or attacked (the landing cell only
        later, by the legality filter), a cell between the king's landing
        cell and the rook is occupied (long side), or the rook is missing
        or has moved."""
        player, pos = self.player, self.pos
        board = self.hex.board
        _board, _has = board._board, board._has_piece
        if board.pos_in_chess(player, pos)[0]:
            return None
        dest = player.pos_from_move(pos, move)
        dk = (dest._q, dest._r)
        overmove = Move(move.steps[0])
        overpos = player.pos_from_move(pos, overmove)
        if dk not in _board or self.hex.piece.used:
            return None
        if _has((overpos._q, overpos._r)) or _has(dk):
            return None
        if board.pos_in_chess(player, overpos)[0]:
            return None
        if move.steps[0] == "SL":
            rpos = player.pos_from_move(dest, overmove)
        else:
            # Long side: one more cell between the king's landing cell and the rook.
            fpos = player.pos_from_move(dest, overmove)
            fk = (fpos._q, fpos._r)
            if fk not in _board or _has(fk):
                return None
            rpos = player.pos_from_move(fpos, overmove)
        rk = (rpos._q, rpos._r)
        if rk not in _board or not _has(rk):
            return None
        rp = _board[rk].piece
        if isinstance(rp, Rook) and not rp.used:
            return dest
        return None


# Move kind -> Piece method generating its candidates (castling, "c", is
# handled separately: it needs the castling flag).
_CANDIDATES = {
    "s": Piece._step,
    "f": Piece._forward,
    "a": Piece._attack,
    "n": Piece._slide,
    "d": Piece._double,
}


class Pawn(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♟", "P", player, **kwargs)
        self.value = 1
        self.special_attack = True

    @property
    def _moves(self) -> list[Move]:
        moves = [
            Move("FL", kind="f"),
            Move("FR", kind="f"),
            Move("DL", kind="a"),
            Move("DF", kind="a"),
            Move("DR", kind="a"),
        ]
        if not self.used:
            moves.extend(
                [
                    Move("FL", "FL", kind="d"),
                    Move("FR", "FR", kind="d"),
                ]
            )
        return moves


class Knight(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♞", "N", player, **kwargs)
        self.value = 3

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
        self.value = 3

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("DL", kind="n"),
            Move("DF", kind="n"),
            Move("DR", kind="n"),
            Move("DLr", kind="n"),
            Move("DFr", kind="n"),
            Move("DRr", kind="n"),
        ]


class Rook(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♜", "R", player, **kwargs)
        self.value = 5

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("SL", kind="n"),
            Move("FL", kind="n"),
            Move("FR", kind="n"),
            Move("SLr", kind="n"),
            Move("FLr", kind="n"),
            Move("FRr", kind="n"),
        ]


class Queen(Piece):
    def __init__(self, player, **kwargs):
        super().__init__("♛", "Q", player, **kwargs)
        self.value = 9

    @property
    def _moves(self) -> list[Move]:
        return [
            Move("SL", kind="n"),
            Move("FL", kind="n"),
            Move("FR", kind="n"),
            Move("SLr", kind="n"),
            Move("FLr", kind="n"),
            Move("FRr", kind="n"),
            Move("DL", kind="n"),
            Move("DF", kind="n"),
            Move("DR", kind="n"),
            Move("DLr", kind="n"),
            Move("DFr", kind="n"),
            Move("DRr", kind="n"),
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
            Move("SL", "SL", kind="c"),
            Move("SLr", "SLr", kind="c"),
        ]
