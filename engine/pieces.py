class Pos:
    """Lightweight axial coordinate.  Stores q, r as plain ints.

    Args:
        q (int): first coordinate
        r (int): second coordinate
        kind (str): Attribute used by piece move to classify positions

    Attributes:
        value (complex): Complex number representation (computed on demand).
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
        kind (str): Type of move. One of s, a or n

    Attributes:
        steps (tuple): tuple of step codes.
        kind (str): Type of move. One of s, a or n

    """

    def __init__(self, *args, kind="s"):
        self.steps = args
        self.kind = kind


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
        if self.hex is not None:
            res = []
            player = self.player
            pos = self.pos
            board = self.hex.board
            _board = board._board
            _has = board._has_piece
            for move in self._moves:
                match move.kind:
                    case "s":
                        res.append(player.pos_from_move(pos, move))
                    case "f":
                        dest = player.pos_from_move(pos, move)
                        dk = (dest._q, dest._r)
                        if dk in _board and not _has(dk):
                            res.append(dest)
                    case "a":
                        dest = player.pos_from_move(pos, move)
                        dk = (dest._q, dest._r)
                        if dk in _board and _has(dk):
                            res.append(dest)
                    case "n":
                        cur = pos
                        for _ in range(14):
                            dest = player.pos_from_move(cur, move)
                            dk = (dest._q, dest._r)
                            if dk not in _board:
                                break
                            res.append(dest)
                            if _has(dk):
                                break
                            cur = dest
                    case "d":
                        partial_move = Move(move.steps[0])
                        pos1 = player.pos_from_move(pos, partial_move)
                        dk1 = (pos1._q, pos1._r)
                        if dk1 in _board and not _has(dk1):
                            pos2 = player.pos_from_move(pos, move)
                            dk2 = (pos2._q, pos2._r)
                            if dk2 in _board and not _has(dk2):
                                res.append(pos2)
                if castling and move.kind == "c":
                    inchess, _, _ = board.pos_in_chess(player, pos)
                    if not inchess:
                        dest = player.pos_from_move(pos, move)
                        dk = (dest._q, dest._r)
                        overmove = Move(move.steps[0])
                        overpos = player.pos_from_move(pos, overmove)
                        ok = (overpos._q, overpos._r)
                        if dk in _board and not self.hex.piece.used:
                            if not _has(ok) and not _has(dk):
                                inchess2, _, _ = board.pos_in_chess(player, overpos)
                                if not inchess2:
                                    if move.steps[0] == "SL":
                                        rpos = player.pos_from_move(dest, overmove)
                                        rk = (rpos._q, rpos._r)
                                        if rk in _board and _has(rk):
                                            rp = _board[rk].piece
                                            if isinstance(rp, Rook) and not rp.used:
                                                res.append(dest)
                                    else:
                                        fpos = player.pos_from_move(dest, overmove)
                                        fk = (fpos._q, fpos._r)
                                        if fk in _board and not _has(fk):
                                            rpos = player.pos_from_move(fpos, overmove)
                                            rk = (rpos._q, rpos._r)
                                            if rk in _board and _has(rk):
                                                rp = _board[rk].piece
                                                if isinstance(rp, Rook) and not rp.used:
                                                    res.append(dest)
            return res


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
