from trichess.pieces import Bishop, King, Knight, Move, Pawn, Piece, Pos, Queen, Rook

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


class Player:
    """A class to represent a trichess player.

    Note:
        Player has defined position on trichessboard.
        0-bottom, 1-left, 2-right

    Args:
        pid (int): Player ID. Must be 0, 1 or 2 according to position

    Keyword Args:
        name (str, optional): Player name

    Attributes:
        pid (int): Player ID. Must be 0, 1 or 2 according to position
        name (str): Player name

    """

    def __init__(self, pid: int, **kwargs):
        self.pid = pid
        self.name = kwargs.get("name", f"Player {pid}")
        self.king_piece = None

    def __repr__(self) -> str:
        return f"[{self.name}]"

    def step(self, step) -> complex:
        """Return step code converted to complex number."""
        if step.endswith("r"):
            return -STEP[self.pid][step[:-1]]
        else:
            return STEP[self.pid][step]

    def pos_from_move(self, pos: Pos, move: Move) -> Pos:
        """Return new position calculated from current one and move."""
        return pos.from_deltas([self.step(step) for step in move.steps], kind=move.kind)

    def pawn(self, **kwargs) -> Pawn:
        """Create Player's instance of pawn piece."""
        return Pawn(self, **kwargs)

    def knight(self, **kwargs) -> Knight:
        """Create Player's instance of knight piece."""
        return Knight(self, **kwargs)

    def bishop(self, **kwargs) -> Bishop:
        """Create Player's instance of bishop piece."""
        return Bishop(self, **kwargs)

    def rook(self, **kwargs) -> Rook:
        """Create Player's instance of rook piece."""
        return Rook(self, **kwargs)

    def queen(self, **kwargs) -> Queen:
        """Create Player's instance of queen piece."""
        return Queen(self, **kwargs)

    def king(self, **kwargs) -> King:
        """Create Player's instance of king piece."""
        # keep reference for king
        self.king_piece = King(self, **kwargs)
        return self.king_piece


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
        log = kwargs.get("log", [])
        for pos_from, pos_to in log:
            self.move_piece(pos_from, pos_to)

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

    def move_piece(self, pos_from, pos_to):
        """Move piece from one position to other.

        Note:
            When there is no piece on position, error is raised

        """
        piece = self._board[pos_from].piece
        piece.used = True
        piece.hex = self._board[pos_to]
        self._board[pos_to].piece = piece
        self._board[pos_from].piece = None

    def possible_moves(self, piece: Piece) -> list[Pos]:
        """Return list of all posiible moves for given piece."""
        all = []
        for dest in piece.pos_candidates():
            if dest in self._board:
                if dest.kind == "a" and self._board[dest].has_piece:
                    if self._board[dest].piece.player is not piece.player:
                        all.append(dest)
                elif dest.kind == "s":
                    if self._board[dest].has_piece:
                        if self._board[dest].piece.player is not piece.player:
                            all.append(dest)
                    else:
                        all.append(dest)
                elif dest.kind == "n":
                    if self._board[dest].has_piece:
                        if self._board[dest].piece.player is not piece.player:
                            all.append(dest)
                    else:
                        all.append(dest)
                else:
                    pass
        return all


class GameAPI:
    """A class to represent trichess game.

    All interaction between front-end and engine must use GameAPI.

    Attributes:
        ready (bool): True when game is ready, otherwise False.
        move_number (int): Number of moves played in game.
        players (dict): A dictionary with three players. Keys are 0, 1 and 2
        board (Board): Instance of trichess board.
        log (list): List of played moves. Each move is represented by tuple
            of two positions `(pos_from, pos_to)`.
        on_move (int): ID of player on move

    """

    def __init__(self):
        self.ready = False
        self.log = []
        self.move_number = 0
        self.players = {0: None, 1: None, 2: None}

    def new_game(self, **kwargs):
        """Initialize new Game

        Keyword Args:
            player0 (Player, optional): Player on position 0-bottom
            player1 (Player, optional): Player on position 1-left
            player2 (Player, optional): Player on position 2-right
        """
        self.players[0] = kwargs.get("player0", Player(0))
        self.players[1] = kwargs.get("player1", Player(1))
        self.players[2] = kwargs.get("player2", Player(2))
        self.board = Board(players=self.players)
        self.ready = True

    @property
    def on_move(self):
        return self.move_number % 3

    def get_possible_moves(self, hex: Hex) -> list:
        """Return list of possible new positions for piece on cell."""
        if self.ready:
            if hex.has_piece:
                piece = hex.piece
                if self.players[self.on_move] is piece.player:
                    return self.board.possible_moves(piece)
        return []

    def make_move(self, hex_from, hex_to):
        """Make move from hex to other hex and record it to the log."""
        if self.ready:
            # add move to log
            self.log.append((hex_from.pos, hex_to.pos))
            # make move
            self.board.move_piece(hex_from.pos, hex_to.pos)
            self.move_number += 1

    def undo(self):
        """Undo last move."""
        if self.ready and self.move_number > 0:
            self.replay_from_log(self.log[:-1])

    def in_chess(self, player: Player) -> bool:
        """Check if players king is under attack"""
        if self.ready:
            for hex in self.board:
                if hex.has_piece:
                    piece = hex.piece
                    if piece.player is not player:
                        targets = self.board.possible_moves(piece)
                        if player.king_piece.hex.pos in targets:
                            return True
        return False

    def replay_from_log(self, log: list):
        """Initalize board and replay all moves from log."""
        self.log = log
        self.move_number = len(log)
        self.board = Board(players=self.players, log=log)

    def log2string(self):
        """Returns game log as string."""
        if self.ready and self.move_number > 0:
            return "".join([f"{p1.code}{p2.code}" for p1, p2 in self.log])

    def string2log(self, s):
        """Returns game log from string."""
        log = []
        for q1, r1, q2, r2 in zip(s[::4], s[1::4], s[2::4], s[3::4]):
            log.append(
                (Pos(ord(q1) - 72, ord(r1) - 72), Pos(ord(q2) - 72, ord(r2) - 72))
            )
        return log

    def logtail(self, n=5):
        nlog = [(ix + 1, p1, p2) for ix, (p1, p2) in enumerate(self.log)]
        return " ".join([f"{ix}:{p1.code}-{p2.code}" for ix, p1, p2 in nlog[-n:]])
