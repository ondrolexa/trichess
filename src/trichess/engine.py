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
        self.eliminated = []
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
        thex = self._board[pos_to]
        if thex.has_piece:
            self.eliminated.append(thex.piece)
        piece.hex = thex
        thex.piece = piece
        self._board[pos_from].piece = None

    def test_move_piece(self, pos_from, pos_to):
        piece = self._board[pos_from].piece
        piece.hex = self._board[pos_to]
        to_piece = self._board[pos_to].piece if self._board[pos_to].has_piece else None
        self._board[pos_to].piece = piece
        self._board[pos_from].piece = None
        res = not self.in_chess(piece.player)
        piece.hex = self._board[pos_from]
        self._board[pos_from].piece = piece
        self._board[pos_to].piece = to_piece
        return res

    def in_chess(self, player: Player) -> bool:
        """Check if players king is under attack"""
        for hex in self:
            if hex.has_piece:
                piece = hex.piece
                if piece.player is not player:
                    targets = self.possible_moves(piece)
                    if player.king_piece.hex.pos in targets:
                        return True
        return False

    def possible_moves(self, piece: Piece) -> list[Pos]:
        """Return list of all posiible moves for given piece."""
        all = []
        for dest in piece.pos_candidates():
            if dest in self._board:
                match dest.kind:
                    case "a":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                    case "s":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                        else:
                            all.append(dest)
                    case "d":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                        else:
                            all.append(dest)
                    case "n":
                        if self._board[dest].has_piece:
                            if self._board[dest].piece.player is not piece.player:
                                all.append(dest)
                        else:
                            all.append(dest)
        return all


class GameAPI:
    """A trichess game API.

    All interaction between front-end and engine must use GameAPI.

    Keyword Args:
        name0 (str, optional): Name of player on position 0-bottom
        name1 (str, optional): Name of player on position 1-left
        name2 (str, optional): Name of player on position 2-right
        view_player (int, optional): Which player is on bottom of the board
            Default 0

    Attributes:
        ready (bool): True when game is ready, otherwise False.
        move_number (int): Number of moves played in game.
        players (dict): A dictionary with three players. Keys are 0, 1 and 2
        view_player (int): Which player is on bottom of the board
        board (Board): Instance of trichess board.
        log (list): List of played moves. Each move is represented by tuple
            of two positions `(pos_from, pos_to)`.
        on_move (int): ID of player on move
        on_move_previous(int): ID of player from last move

    """

    def __init__(self, **kwargs):
        self.log = []
        self.move_number = 0
        self.players = {
            0: Player(0, name=kwargs.get("name0", "Player 0")),
            1: Player(1, name=kwargs.get("name1", "Player 1")),
            2: Player(2, name=kwargs.get("name2", "Player 2")),
        }
        self.view_player = kwargs.get("view_player", 0)
        self.board = Board(players=self.players)
        self.update_ui_mappings()

    def update_ui_mappings(self):
        # UI gid mappings to engine hex and pos
        self.gid2hex = {}
        self.pos2gid = {}

        match self.view_player:
            case 0:
                gid = 0
                for r in range(-7, 8):
                    for q in range(-7, 8):
                        # check whether on board
                        s = -q - r
                        if -7 <= s <= 7:
                            pos = Pos(q, r)
                            self.gid2hex[gid] = self.board[pos]
                            self.pos2gid[pos] = gid
                            gid += 1
            case 1:
                gid = 0
                for s in range(-7, 8):
                    for r in range(-7, 8):
                        # check whether on board
                        q = -r - s
                        if -7 <= q <= 7:
                            pos = Pos(q, r)
                            self.gid2hex[gid] = self.board[pos]
                            self.pos2gid[pos] = gid
                            gid += 1
            case 2:
                gid = 0
                for q in range(-7, 8):
                    for r in range(7, -8, -1):
                        # check whether on board
                        s = -q - r
                        if -7 <= s <= 7:
                            pos = Pos(q, r)
                            self.gid2hex[gid] = self.board[pos]
                            self.pos2gid[pos] = gid
                            gid += 1

    def copy(self):
        ga = GameAPI(
            player0=self.players[0], player1=self.players[1], player2=self.players[2]
        )

        ga.replay_from_log(log=self.log.copy())
        return ga

    @property
    def on_move(self):
        return self.move_number % 3

    @property
    def on_move_previous(self):
        return (self.move_number - 1) % 3

    @property
    def eliminated(self):
        """Return eliminated pieces for player pid"""
        res = {0: [], 1: [], 2: []}
        for p in self.board.eliminated:
            res[p.player.pid].append(p.label)
        return res

    @property
    def pieces(self):
        res = {0: [], 1: [], 2: []}
        for hex in self.board:
            if hex.has_piece:
                p = hex.piece
                res[p.player.pid].append(
                    {"gid": self.pos2gid[hex.pos], "piece": p.label}
                )
        return res

    def seat(self, seat: int):
        """Return player on seat 0, 1 or 2"""
        return self.players[(self.view_player + seat) % 3]

    def undo(self):
        """Undo last move."""
        if self.move_number > 0:
            self.replay_from_log(self.log[:-1])

    def replay_from_log(self, log: list):
        """Initalize board and replay all moves from log."""
        self.log = log
        self.move_number = len(log)
        self.board = Board(players=self.players, log=log)
        self.update_ui_mappings()

    @property
    def slog(self):
        """Returns game log as string."""
        return "".join([f"{p1.code}{p2.code}" for p1, p2 in self.log])

    def replay_from_string(self, s: str):
        """Initalize board and replay all moves from string log."""
        log = []
        for q1, r1, q2, r2 in zip(s[::4], s[1::4], s[2::4], s[3::4]):
            log.append(
                (Pos(ord(q1) - 72, ord(r1) - 72), Pos(ord(q2) - 72, ord(r2) - 72))
            )
        self.replay_from_log(log)

    def logtail(self, n=5):
        nlog = [(ix + 1, p1, p2) for ix, (p1, p2) in enumerate(self.log)]
        return " ".join([f"{ix}:{p1.code}-{p2.code}" for ix, p1, p2 in nlog[-n:]])

    def valid_moves(self, gid):
        """Return all valid moves from gid for player on move

        Returns list of dictionaries.

        """
        hex = self.gid2hex[gid]
        moves = []
        targets = []
        if hex.has_piece:
            piece = hex.piece
            if self.players[self.on_move] is piece.player:
                moves = self.board.possible_moves(piece)
        if moves:
            for pos in moves:
                tgid = self.pos2gid[pos]
                testok = self.board.test_move_piece(hex.pos, self.gid2hex[tgid].pos)
                if testok:
                    if not self.board[pos].has_piece:
                        targets.append({"tgid": tgid, "kind": "safe"})
                    else:
                        targets.append({"tgid": tgid, "kind": "attack"})
        return targets

    def make_move(self, from_gid, to_gid):
        """Make move from from_gid to to_gid and record it to the log."""
        # add move to log
        from_pos, to_pos = self.gid2hex[from_gid].pos, self.gid2hex[to_gid].pos
        self.log.append((from_pos, to_pos))
        # make move
        self.board.move_piece(from_pos, to_pos)
        self.move_number += 1

    def move_possible(self):
        """Return True if there is any move possible"""
        for hex in self.board:
            if hex.has_piece:
                piece = hex.piece
                if self.players[self.on_move] is piece.player:
                    moves = self.board.possible_moves(piece)
                    tested = [
                        self.board.test_move_piece(piece.pos, pos) for pos in moves
                    ]
                    if any(tested):
                        return True
        return False
