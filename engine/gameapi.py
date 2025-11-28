from engine.board import Board
from engine.pieces import Pos
from engine.player import Player


class Voting:
    """Game voting tracking"""

    def __init__(self):
        self.clean()

    def clean(self):
        self.kind = None
        self.accepts = []
        self.n_voted = 0
        self.log = ["X", "X", "X"]

    @property
    def slog(self):
        if self.kind == "resign":
            return "R" + "".join(self.log)
        if self.kind == "draw":
            return "S" + "".join(self.log)
        return ""

    def set_resign_voting(self, v0, v1, v2):
        self.n_voted = 3
        self.kind = "resign"
        for player, vote in enumerate([v0, v1, v2]):
            self.log[player] = vote
            if vote == "A":
                self.accepts.append(player)

    def set_draw_voting(self, v0, v1, v2):
        self.n_voted = 3
        self.kind = "draw"
        for player, vote in enumerate([v0, v1, v2]):
            self.log[player] = vote
            if vote == "A":
                self.accepts.append(player)

    def resign_vote(self, player, code):
        if self.kind is None:
            self.kind = "resign"
        if self.kind == "resign":
            if code != "X":
                if code == "A":
                    self.accepts.append(player)
                self.log[player] = code
                self.n_voted += 1
        else:
            raise ValueError(f"{self.kind} voting is in progress")

    def draw_vote(self, player, code):
        if self.kind is None:
            self.kind = "draw"
        if self.kind == "draw":
            if code != "X":
                if code == "A":
                    self.accepts.append(player)
                self.log[player] = code
                self.n_voted += 1
        else:
            raise ValueError(f"{self.kind} voting is in progress")

    def resign_slog(self, player, vote):
        votelog = ["X", "X", "X"]
        if vote:
            votelog[player] = "A"
        else:
            votelog[player] = "D"
        return "r" + "".join(votelog)

    def draw_slog(self, player, vote):
        votelog = ["X", "X", "X"]
        if vote:
            votelog[player] = "A"
        else:
            votelog[player] = "D"
        return "s" + "".join(votelog)

    def needed(self):
        return 0 < self.n_voted < 3

    def results(self, kind="any"):
        if kind in (self.kind, "any"):
            return self.accepts
        else:
            return []

    def votes(self):
        if self.active():
            res = {"kind": self.kind, "n_voted": self.n_voted}
            res[0] = self.log[0]
            res[1] = self.log[1]
            res[2] = self.log[2]
            return res

    def finished(self):
        return self.n_voted == 3

    def active(self):
        return self.n_voted > 0


class GameAPI:
    """A trichess game API.

    All interaction between front-end and engine must use GameAPI.

    Keyword Args:
        name0 (str, optional): Name of player on position 0-bottom
        name1 (str, optional): Name of player on position 1-left
        name2 (str, optional): Name of player on position 2-right
        view_pid (int, optional): ID of player on bottom of the board

    Attributes:
        ready (bool): True when game is ready, otherwise False.
        move_number (int): Number of moves played in game.
        players (dict): A dictionary with three players. Keys are 0, 1 and 2
        view_pid (int): ID of player on bottom of the board
        board (Board): Instance of trichess board.
        log (list): List of played moves. Each move is represented by tuple
            of two positions `(pos_from, pos_to)`.
        on_move (int): ID of player on move
        on_move_previous(int): ID of player from last move

    """

    def __init__(self, view_pid, **kwargs):
        self.slog = ""
        self.move_number = 0
        self.voting = Voting()
        self.players = {
            0: Player(0, name=kwargs.get("name0", "Player 0")),
            1: Player(1, name=kwargs.get("name1", "Player 1")),
            2: Player(2, name=kwargs.get("name2", "Player 2")),
        }
        self.view_pid = view_pid % 3
        self.board = Board(players=self.players)
        self.update_ui_mappings()

    def update_ui_mappings(self):
        # UI gid mappings to engine hex and pos
        self.gid2hex = {}
        self.pos2gid = {}

        match self.view_pid:
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

        ga.replay_from_slog(self.slog)
        return ga

    @property
    def on_move(self):
        return (self.move_number + self.voting.n_voted) % 3

    @property
    def on_move_previous(self):
        return (self.move_number + self.voting.n_voted - 1) % 3

    @property
    def last_move(self):
        if self.slog:
            if self.slog[-4] not in ["R", "S", "r", "s"]:
                from_pos, to_pos, new_piece = self.slog2pos(*self.slog[-4:])
                return {
                    "from": self.pos2gid[from_pos],
                    "to": self.pos2gid[to_pos],
                }

    def in_chess(self):
        """Check if player on move has chess"""
        res = {0: [], 1: [], 2: []}
        inchess, kingpos, pieces = self.board.in_chess(self.players[self.on_move])
        for p in pieces:
            res[p.player.pid].append({"gid": self.pos2gid[p.pos], "piece": p.label})
        return inchess, self.pos2gid[kingpos], res

    def eliminated(self):
        """Return eliminated pieces for player pid"""
        res = {0: [], 1: [], 2: []}
        for _, p in self.board.eliminated:
            res[p.player.pid].append(p.label)
        return res

    def eliminated_value(self):
        """Return total values of eliminated pieces for player pid"""
        res = {0: 0, 1: 0, 2: 0}
        for _, p in self.board.eliminated:
            res[p.player.pid] += p.value
        return res

    def player_eliminations(self):
        """Return values of opponent eliminated pieces by player"""
        res = {0: {1: 0, 2: 0}, 1: {0: 0, 2: 0}, 2: {0: 0, 1: 0}}
        for pid, p in self.board.eliminated:
            res[pid][p.player.pid] += p.value
        return res

    def pieces(self):
        res = {0: [], 1: [], 2: []}
        for hex in self.board:
            if hex.has_piece:
                p = hex.piece
                res[p.player.pid].append(
                    {"gid": self.pos2gid[hex.pos], "piece": p.label}
                )
        return res

    def pieces_value(self):
        """Return total values of pieces for player pid"""
        res = {0: 0, 1: 0, 2: 0}
        for hex in self.board:
            if hex.has_piece:
                p = hex.piece
                res[p.player.pid] += p.value
        return res

    def seat(self, seat: int):
        """Return player on seat 0, 1 or 2"""
        return self.players[(self.view_pid + seat) % 3]

    def undo(self):
        """Undo last move."""
        if self.move_number > 0:
            self.replay_from_slog(self.slog[:-4])

    def slog2pos(self, q1, r1, q2, r2):
        # check promotion
        if q1 > "O":
            q1 = chr(ord(q1) - 32)
            new_label = "Q"
        elif r1 > "O":
            r1 = chr(ord(r1) - 32)
            new_label = "R"
        elif q2 > "O":
            q2 = chr(ord(q2) - 32)
            new_label = "B"
        elif r2 > "O":
            r2 = chr(ord(r2) - 32)
            new_label = "N"
        else:
            new_label = ""
        return (
            Pos(ord(q1) - 72, ord(r1) - 72),
            Pos(ord(q2) - 72, ord(r2) - 72),
            new_label,
        )

    def move2slog(self, p1, p2, label):
        """Returns game move as slog string."""
        q1, r1 = p1.q, p1.r
        q2, r2 = p2.q, p2.r
        match label:
            case "Q":
                q1 += 32
            case "R":
                r1 += 32
            case "B":
                q2 += 32
            case "N":
                r2 += 32
        return chr(72 + q1) + chr(72 + r1) + chr(72 + q2) + chr(72 + r2)

    def replay_from_slog(self, s: str):
        """Initalize board and replay all moves from string log."""
        self.slog = ""
        self.move_number = 0
        self.board = Board(players=self.players)
        self.voting.clean()
        self.update_ui_mappings()
        # replay
        for q1, r1, q2, r2 in zip(s[::4], s[1::4], s[2::4], s[3::4]):
            # clean previously finished voting
            if self.voting.finished():
                self.voting.clean()
            if q1 == "r":
                self.voting.resign_vote(0, r1)
                self.voting.resign_vote(1, q2)
                self.voting.resign_vote(2, r2)
            elif q1 == "s":
                self.voting.draw_vote(0, r1)
                self.voting.draw_vote(1, q2)
                self.voting.draw_vote(2, r2)
            elif q1 == "R":
                self.voting.set_resign_voting(r1, q2, r2)
            elif q1 == "S":
                self.voting.set_draw_voting(r1, q2, r2)
            else:
                from_pos, to_pos, new_piece = self.slog2pos(q1, r1, q2, r2)
                # make move
                self.board.move_piece(from_pos, to_pos, new_piece)
                self.move_number += 1

            # fix slog when just finished voting
            if self.voting.finished() and q1 in ["r", "s"]:
                self.slog = self.slog[:-8] + self.voting.slog
            else:
                self.slog += q1 + r1 + q2 + r2

    def logtail(self, n=5):
        return self.slog[-4 * n :]

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
                            targets.append(
                                {
                                    "tgid": tgid,
                                    "kind": "safe",
                                    "promotion": self.board.promotion(piece, pos),
                                }
                            )
                        else:
                            targets.append(
                                {
                                    "tgid": tgid,
                                    "kind": "attack",
                                    "promotion": self.board.promotion(piece, pos),
                                }
                            )
        return targets

    def make_move(self, from_gid, to_gid, new_piece=""):
        """Make move from from_gid to to_gid and record it to the log."""
        if not self.voting.needed():
            # add move to log
            from_pos, to_pos = self.gid2hex[from_gid].pos, self.gid2hex[to_gid].pos
            # make move
            self.board.move_piece(from_pos, to_pos, new_piece)
            self.slog += self.move2slog(from_pos, to_pos, new_piece)
            self.move_number += 1
            # clean previously finished voting
            if self.voting.finished():
                self.voting.clean()

    def resignation_vote(self, vote: bool):
        """Get slog with resignation voting"""
        return self.slog + self.voting.resign_slog(self.on_move, vote)

    def draw_vote(self, vote: bool):
        """Get slog with draw voting"""
        return self.slog + self.voting.draw_slog(self.on_move, vote)

    def resignation(self):
        if (
            self.voting.kind == "resign"
            and self.voting.finished()
            and len(self.voting.accepts) == 2
        ):
            return True
        else:
            return False

    def draw(self):
        if (
            self.voting.kind == "draw"
            and self.voting.finished()
            and len(self.voting.accepts) == 3
        ):
            return True
        else:
            return False

    def move_possible(self):
        """Return True if there is any move possible"""
        if self.resignation() or self.draw():
            return False
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
