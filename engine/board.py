from engine.pieces import Pawn, Piece, Pos
from engine.player import Player

base0 = [Pos(i, 7) for i in range(-7, 1)]
base1 = [Pos(i, -7 - i) for i in range(-7, 1)]
base2 = [Pos(7, i) for i in range(-7, 1)]


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

    def __init__(self, pos, board):
        self.pos = pos
        self.board = board
        self.piece = None

    def __repr__(self) -> str:
        return f"Hex({self.pos.q},{self.pos.r})"

    @property
    def has_piece(self) -> bool:
        return True if self.piece is not None else False

    @property
    def color(self) -> int:
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
        # board dict
        self._board = {}
        # setup players
        self.players = kwargs.get("players", {0: Player(0), 1: Player(1), 2: Player(2)})
        # generate all cells
        for r in range(-7, 8):
            for q in range(-7, 8):
                # check whether on board
                s = -q - r
                if -7 <= s <= 7:
                    pos = Pos(q, r)
                    self._board[pos] = Hex(pos, self)
        self.init_pieces()
        self.opposite = {
            0: base1 + base2,
            1: base0 + base2,
            2: base0 + base1,
        }
        self.eliminated = []
        log = kwargs.get("log", [])
        for pos_from, pos_to, label in log:
            self.move_piece(pos_from, pos_to, label)

    def init_pieces(self):
        """Initialize trichess board pieces to starting positions"""

        for hex in self:
            hex.piece = None
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
        return iter(self._board.values())

    def __getitem__(self, pos: Pos | int) -> Hex:
        return self._board.get(pos, None)

    def __contains__(self, pos: Pos) -> bool:
        return pos in self._board

    def place_piece(self, pos: Pos, create_piece_fn):
        """Place piece on cell with given position.

        Note:
            Piece is passed as creator function. See Player methods.

        """
        self._board[pos].piece = create_piece_fn(hex=self._board[pos])

    def move_piece(self, pos_from: Pos, pos_to: Pos, label: str):
        """Move piece from one position to other.

        Note:
            When there is no piece on position, error is raised
            When label is not empty string, piece is promoted

        """
        thex = self._board[pos_to]
        if thex.has_piece:
            self.eliminated.append(thex.piece)
        if label:
            piece = self._board[pos_from].piece.player.promotion(label)
            piece.used = True
        else:
            piece = self._board[pos_from].piece
            piece.used = True
        piece.hex = thex
        thex.piece = piece
        self._board[pos_from].piece = None

    def test_move_piece(self, pos_from, pos_to):
        piece = self._board[pos_from].piece
        piece.hex = self._board[pos_to]
        to_piece = self._board[pos_to].piece if self._board[pos_to].has_piece else None
        self._board[pos_to].piece = piece
        self._board[pos_from].piece = None
        res, _, _ = self.in_chess(piece.player)
        piece.hex = self._board[pos_from]
        self._board[pos_from].piece = piece
        self._board[pos_to].piece = to_piece
        return not res

    def promotion(self, piece: Piece, pos: Pos) -> bool:
        """Return turn when pos in opposite base"""
        return (pos in self.opposite[piece.player.pid]) and isinstance(piece, Pawn)

    def in_chess(self, player: Player) -> tuple[bool, list]:
        """Check if players king is under attack and returns list of attacking pieces"""
        pieces = []
        inchess = False
        kingpos = player.king_piece.hex.pos
        for hex in self:
            if hex.has_piece:
                piece = hex.piece
                if piece.player is not player:
                    targets = self.possible_moves(piece)
                    if kingpos in targets:
                        pieces.append(piece)
                        inchess = True
        return inchess, kingpos, pieces

    def possible_moves(self, piece: Piece) -> list[Pos]:
        """Return list of all posiible moves for given piece."""
        all = []
        for dest in piece.pos_candidates():
            if dest in self._board:
                match dest.kind:
                    case "s":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                        else:
                            all.append(dest)
                    case "a":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                    case "n":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                        else:
                            all.append(dest)
                    case _:
                        all.append(dest)
        return all
