from engine.pieces import Bishop, King, Knight, Pawn, Piece, Pos, Queen, Rook
from engine.player import Player

# Promotion zone edges per player.
# Each player has three contiguous board edges that make up the opposite
# territory — when a pawn reaches any of these positions it can promote.
# Naming: base{A}{B} = edge shared by players A and B, belonging to neither.
base0 = [Pos(i, 7) for i in range(-7, 1)]
base01 = [Pos(-7, i) for i in range(1, 7)]
base1 = [Pos(i, -7 - i) for i in range(-7, 1)]
base12 = [Pos(i, -7) for i in range(1, 7)]
base2 = [Pos(7, i) for i in range(-7, 1)]
base20 = [Pos(7 - i, i) for i in range(1, 7)]

# Starting layout per player: (Player factory, cells), placed in this order.
# Pawn rows: player 0 on r=6, player 1 on s=6 (r=-6-q), player 2 on q=6;
# the gap in the middle of each row holds the third bishop.
_PAWN_COLS = (*range(-7, -3), *range(-2, 2))
STARTING_LAYOUT = (
    (
        ("pawn", [(i, 6) for i in _PAWN_COLS]),
        ("knight", [(-5, 7), (-2, 7)]),
        ("bishop", [(-6, 7), (-1, 7), (-3, 6)]),
        ("rook", [(-7, 7), (0, 7)]),
        ("queen", [(-3, 7)]),
        ("king", [(-4, 7)]),
    ),
    (
        ("pawn", [(i, -6 - i) for i in _PAWN_COLS]),
        ("knight", [(-2, -5), (-5, -2)]),
        ("bishop", [(-1, -6), (-6, -1), (-3, -3)]),
        ("rook", [(0, -7), (-7, 0)]),
        ("queen", [(-4, -3)]),
        ("king", [(-3, -4)]),
    ),
    (
        ("pawn", [(6, i) for i in _PAWN_COLS]),
        ("knight", [(7, -2), (7, -5)]),
        ("bishop", [(7, -1), (7, -6), (6, -3)]),
        ("rook", [(7, 0), (7, -7)]),
        ("queen", [(7, -4)]),
        ("king", [(7, -3)]),
    ),
)

# Castling (Help → For developers → Hex Geometry (webapp/templates/help.html)): (king_from, king_to) -> (rook_from, rook_to), as (q, r) tuples.
CASTLING_ROOK_MOVES = {
    ((-4, 7), (-6, 7)): ((-7, 7), (-5, 7)),
    ((-4, 7), (-2, 7)): ((0, 7), (-3, 7)),
    ((-3, -4), (-1, -6)): ((0, -7), (-2, -5)),
    ((-3, -4), (-5, -2)): ((-7, 0), (-4, -3)),
    ((7, -3), (7, -1)): ((7, 0), (7, -2)),
    ((7, -3), (7, -5)): ((7, -7), (7, -4)),
}

# Precomputed attack tables for fast is_attacked().
# Straight directions (Rook slides): the 6 edge-adjacent hex directions.
_STRAIGHT = ((-1, 0), (0, -1), (1, -1), (1, 0), (0, 1), (-1, 1))
# Diagonal directions (Bishop slides): the 6 directions through a cell's
# corners, to the cell beyond.
_DIAGONAL = ((-1, -1), (1, -2), (2, -1), (1, 1), (-1, 2), (-2, 1))
# King step offsets: union of straight + diagonal (12 total).
_KING_STEPS = _STRAIGHT + _DIAGONAL
# Knight attack offsets (same for all players).
_KNIGHT_OFFSETS = (
    (-3, 1),
    (-3, 2),
    (-2, -1),
    (-2, 3),
    (-1, -2),
    (-1, 3),
    (1, -3),
    (1, 2),
    (2, -3),
    (2, 1),
    (3, -2),
    (3, -1),
)
# Pawn attack offsets per player: a pawn at pos+offset attacks pos.
# (Help → For developers → Hex Geometry (webapp/templates/help.html).)
_PAWN_ATTACK = (
    ((-2, 1), (-1, 2), (1, 1)),
    ((-2, 1), (-1, -1), (1, -2)),
    ((1, -2), (1, 1), (2, -1)),
)


class Hex:
    """A class to represent a trichess board cell.

    Args:
        pos (Pos): Position of cell
        board (Board): Board instance containing the cell

    Attributes:
        piece (Piece, None): Piece instance on this cell or None
        has_piece (bool): True when contains piece, otherwise False
        color (int): Color of the cell. Returns 0, 1 or 2

    """

    __slots__ = ("pos", "board", "piece")

    def __init__(self, pos, board):
        self.pos = pos
        self.board = board
        self.piece = None

    def __repr__(self) -> str:
        return f"Hex({self.pos.q},{self.pos.r})"

    @property
    def has_piece(self) -> bool:
        return self.piece is not None

    @property
    def color(self) -> int:
        """Cell territory color (0, 1, 2) via the formula (2q + r) % 3."""
        return (2 * self.pos.q + self.pos.r) % 3


class Board:
    """A class to represent a trichess board.

    Keyword Args:
        players (dict): A dictionary with three players. Keys must be 0, 1 and 2
        log (list, optional): Chess game log

    Attributes:
        players (dict): A dictionary with three players. Keys are 0, 1 and 2

    """

    def __init__(self, **kwargs):
        # board dict — keyed by (q, r) tuples for fast lookups
        self._board: dict[tuple[int, int], Hex] = {}
        # setup players
        self.players = kwargs.get("players", {0: Player(0), 1: Player(1), 2: Player(2)})
        # precompute enemy pids for each player
        self._enemy_pids = {}
        pids = list(self.players.keys())
        for pid in pids:
            self._enemy_pids[pid] = tuple(p for p in pids if p != pid)
        # generate all cells
        for r in range(-7, 8):
            for q in range(-7, 8):
                s = -q - r
                if -7 <= s <= 7:
                    pos = Pos(q, r)
                    self._board[(q, r)] = Hex(pos, self)
        self.init_pieces()
        self.opposite = {
            0: base1 + base12 + base2,
            1: base2 + base20 + base0,
            2: base0 + base01 + base1,
        }
        self.eliminated = []
        log = kwargs.get("log", [])
        for pos_from, pos_to, label in log:
            self.move_piece(pos_from, pos_to, label)

    def __iter__(self):
        return iter(self._board.values())

    def __getitem__(self, pos) -> Hex:
        """Look up hex by axial coordinate.  Accepts Pos or (q, r) tuple."""
        if isinstance(pos, tuple):
            return self._board[pos]
        return self._board[(pos._q, pos._r)]

    def get(self, q, r) -> Hex | None:
        """Fast single-call hex lookup by raw coordinates."""
        return self._board.get((q, r))

    def __contains__(self, pos) -> bool:
        """True when the axial coordinate is on the board.  Accepts Pos or tuple."""
        if isinstance(pos, tuple):
            return pos in self._board
        return (pos._q, pos._r) in self._board

    def _has_piece(self, key) -> bool:
        """Check if a board cell at key (q,r tuple) has a piece."""
        h = self._board.get(key)
        return h is not None and h.piece is not None

    def copy(self, players=None) -> "Board":
        """Create a deep copy of the board state without replaying slog.

        *players* lets the caller supply independent Player instances (e.g.
        GameAPI.copy() makes fresh ones) — pieces are re-pointed to them so
        identity checks like ``piece.player is players[pid]`` keep working
        on the copy.  Defaults to sharing the source board's players dict.
        """
        b = Board.__new__(Board)
        b.players = players if players is not None else self.players
        b._enemy_pids = self._enemy_pids
        # copy board cells
        new_board = {}
        for k, old_hex in self._board.items():
            new_hex = Hex(old_hex.pos, b)
            if old_hex.piece is not None:
                # share immutable piece metadata; copy mutable state
                p = old_hex.piece
                new_piece = p.__class__.__new__(p.__class__)
                new_piece.__dict__.update(p.__dict__)
                new_piece.player = b.players[p.player.pid]
                new_piece.hex = new_hex
                new_hex.piece = new_piece
                # update king reference for the owning player
                if isinstance(p, King):
                    b.players[p.player.pid]._king_piece = new_piece
            new_board[k] = new_hex
        b._board = new_board
        b.opposite = self.opposite
        b.eliminated = list(self.eliminated)
        return b

    def init_pieces(self):
        """Clear the board and place all 51 pieces (17 per player) at starting positions."""
        for hex in self:
            hex.piece = None
        for pid, layout in enumerate(STARTING_LAYOUT):
            player = self.players[pid]
            for kind, cells in layout:
                for q, r in cells:
                    self.place_piece(Pos(q, r), getattr(player, kind))

    def place_piece(self, pos: Pos, create_piece_fn):
        """Place piece on cell at *pos*.

        *create_piece_fn* is a Player factory method that receives
        the target Hex as ``hex=`` keyword arg.
        """
        self._board[(pos._q, pos._r)].piece = create_piece_fn(
            hex=self._board[(pos._q, pos._r)]
        )

    def move_piece(self, pos_from: Pos, pos_to: Pos, label: str):
        """Move piece, handling capture, promotion, and castling side effects.

        When *label* is non-empty and the piece is a Pawn entering the
        opponent's base, the piece is promoted.  King moves that cross
        two steps trigger castling (the matching rook is also moved).
        """
        fk = (pos_from._q, pos_from._r)
        tk = (pos_to._q, pos_to._r)
        thex = self._board[tk]
        if thex.has_piece:
            self.eliminated.append((self._board[fk].piece.player.pid, thex.piece))
        if label and self.promotion(self._board[fk].piece, pos_to):
            piece = self._board[fk].piece.player.promotion(label)
        else:
            piece = self._board[fk].piece
        piece.used = True
        piece.hex = thex
        thex.piece = piece
        self._board[fk].piece = None
        # Check castling
        if isinstance(piece, King):
            rook = CASTLING_ROOK_MOVES.get((fk, tk))
            if rook is not None:
                self.move_piece(Pos(*rook[0]), Pos(*rook[1]), "")

    def test_move_piece(self, pos_from, pos_to):
        """Temporarily apply move and test whether own king is still safe.

        Restores original board state before returning.  Used for
        legality filtering — a move is legal only when it does not
        leave the moving player in check.
        """
        fk = (pos_from._q, pos_from._r)
        tk = (pos_to._q, pos_to._r)
        piece = self._board[fk].piece
        to_hex = self._board[tk]
        to_piece = to_hex.piece if to_hex.has_piece else None
        to_hex.piece = piece
        self._board[fk].piece = None
        if isinstance(piece, King):
            king_pos = pos_to
        else:
            king_pos = piece.player.king_piece.hex.pos
        res = self._is_attacked(king_pos, piece.player)
        self._board[fk].piece = piece
        to_hex.piece = to_piece
        return not res

    def promotion(self, piece: Piece, pos: Pos) -> bool:
        """True when a Pawn reaches an opponent-base cell."""
        return (pos in self.opposite[piece.player.pid]) and isinstance(piece, Pawn)

    def in_chess(self, player: Player) -> tuple[bool, list, list]:
        """Check if player's king is under attack, return (bool, king_pos, attackers)."""
        return self.pos_in_chess(player, player.king_piece.hex.pos)

    def pos_in_chess(self, player: Player, pos) -> tuple[bool, list, list]:
        """Check if *pos* is attacked by any enemy piece."""
        pieces = []
        inchess = False
        for hex in self:
            if hex.has_piece:
                piece = hex.piece
                if piece.player is not player:
                    targets = self.possible_moves(piece, castling=False)
                    if pos in targets:
                        pieces.append(piece)
                        inchess = True
        return inchess, pos, pieces

    def _is_attacked(self, pos: Pos, by_player: Player) -> bool:
        """Fast check if *pos* is attacked by any piece of *by_player*'s opponents.

        Uses reverse-direction scanning: from *pos*, scan outward along each
        attack direction and check for threatening pieces.

        Only proven correct for *by_player*'s own king square (see
        TestAttackDetectionConsistency in tests/test_board.py): on other
        squares it disagrees with pos_in_chess() (e.g. flags untouched pawns
        on a fresh board), so don't reuse it for arbitrary pieces.
        """
        q, r = pos._q, pos._r
        enemy_pids = self._enemy_pids[by_player.pid]
        if self._ray_hits(q, r, _STRAIGHT, enemy_pids, (Rook, Queen)):
            return True
        if self._ray_hits(q, r, _DIAGONAL, enemy_pids, (Bishop, Queen)):
            return True
        if self._step_hits(q, r, _KING_STEPS, enemy_pids, King):
            return True
        if self._step_hits(q, r, _KNIGHT_OFFSETS, enemy_pids, Knight):
            return True
        # Pawn attacks depend on the pawn owner's orientation.
        board = self._board
        for pid in enemy_pids:
            for dq, dr in _PAWN_ATTACK[pid]:
                h = board.get((q + dq, r + dr))
                if h is not None and h.piece is not None:
                    if h.piece.player.pid == pid and isinstance(h.piece, Pawn):
                        return True
        return False

    def _ray_hits(self, q, r, directions, enemy_pids, kinds) -> bool:
        """True when, along any of *directions* from (q, r), the first piece
        met is an enemy one of *kinds*."""
        board = self._board
        for dq, dr in directions:
            sq, sr = q + dq, r + dr
            while -7 <= sq <= 7 and -7 <= sr <= 7 and -7 <= -sq - sr <= 7:
                h = board.get((sq, sr))
                if h is not None and h.piece is not None:
                    if h.piece.player.pid in enemy_pids and isinstance(h.piece, kinds):
                        return True
                    break
                sq += dq
                sr += dr
        return False

    def _step_hits(self, q, r, offsets, enemy_pids, kind) -> bool:
        """True when an enemy *kind* stands one of *offsets* away from (q, r)."""
        board = self._board
        for dq, dr in offsets:
            h = board.get((q + dq, r + dr))
            if h is not None and h.piece is not None:
                if h.piece.player.pid in enemy_pids and isinstance(h.piece, kind):
                    return True
        return False

    def possible_moves(self, piece: Piece, castling: bool = True) -> list[Pos]:
        """Filter candidate positions by board occupancy and piece ownership."""
        all = []
        candidates = piece.pos_candidates(castling)
        if candidates is not None:
            _board = self._board
            for dest in candidates:
                dk = (dest._q, dest._r)
                h = _board.get(dk)
                if h is None:
                    continue
                match dest.kind:
                    case "s":
                        if not h.has_piece or h.piece.player is not piece.player:
                            all.append(dest)
                    case "a":
                        if h.has_piece and h.piece.player is not piece.player:
                            all.append(dest)
                    case "n":
                        if not h.has_piece or h.piece.player is not piece.player:
                            all.append(dest)
                    case _:
                        all.append(dest)
        return all
