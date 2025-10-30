from engine.board import Board
from engine.pieces import Pos
from engine.player import Player


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
        self.log = []
        self.move_number = 0
        self.vote_resign = {"log": "", "results": []}
        self.vote_draw = {"log": "", "results": []}
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

        ga.replay_from_log(log=self.log.copy())
        return ga

    @property
    def on_move(self):
        return (
            self.move_number
            + len(self.vote_draw["log"]) // 4
            + len(self.vote_resign["log"]) // 4
        ) % 3

    @property
    def on_move_previous(self):
        return (
            self.move_number
            + len(self.vote_draw["log"]) // 4
            + len(self.vote_resign["log"]) // 4
            - 1
        ) % 3

    @property
    def last_move(self):
        if self.log:
            return {
                "from": self.pos2gid[self.log[-1][0]],
                "to": self.pos2gid[self.log[-1][1]],
            }

    @property
    def in_chess(self):
        """Check if player on move has chess"""
        res = {0: [], 1: [], 2: []}
        inchess, kingpos, pieces = self.board.in_chess(self.players[self.on_move])
        for p in pieces:
            res[p.player.pid].append({"gid": self.pos2gid[p.pos], "piece": p.label})
        return inchess, self.pos2gid[kingpos], res

    @property
    def eliminated(self):
        """Return eliminated pieces for player pid"""
        res = {0: [], 1: [], 2: []}
        for p in self.board.eliminated:
            res[p.player.pid].append(p.label)
        return res

    @property
    def eliminated_value(self):
        """Return total values of eliminated pieces for player pid"""
        res = {0: 0, 1: 0, 2: 0}
        for p in self.board.eliminated:
            res[p.player.pid] += p.value
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

    @property
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
        nlog = []
        for p1, p2, label in self.log:
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
            nlog.append(chr(72 + q1) + chr(72 + r1) + chr(72 + q2) + chr(72 + r2))
        return "".join(nlog) + self.vote_resign["log"] + self.vote_draw["log"]

    def replay_from_slog(self, s: str):
        """Initalize board and replay all moves from string log."""
        log = []
        # clean votings
        self.vote_resign = {"log": "", "results": []}
        self.vote_draw = {"log": "", "results": []}
        for q1, r1, q2, r2 in zip(s[::4], s[1::4], s[2::4], s[3::4]):
            # clean previous finished votings
            if (len(self.vote_resign["log"]) // 4) == 3:
                self.vote_resign = {"log": "", "results": []}
            if (len(self.vote_draw["log"]) // 4) == 3:
                self.vote_draw = {"log": "", "results": []}
            if q1 == "R":
                # check resignation, suggesting player got 1
                if r1 == "A":
                    self.vote_resign["results"].append(0)
                if q2 == "A":
                    self.vote_resign["results"].append(1)
                if r2 == "A":
                    self.vote_resign["results"].append(2)
                self.vote_resign["log"] += f"{q1}{r1}{q2}{r2}"
            elif q1 == "S":
                # draw voting. game ends with ends with SAAA
                if r1 == "A":
                    self.vote_draw["results"].append(0)
                if q2 == "A":
                    self.vote_draw["results"].append(1)
                if r2 == "A":
                    self.vote_draw["results"].append(2)
                self.vote_draw["log"] += f"{q1}{r1}{q2}{r2}"
            else:
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
                log.append(
                    (
                        Pos(ord(q1) - 72, ord(r1) - 72),
                        Pos(ord(q2) - 72, ord(r2) - 72),
                        new_label,
                    )
                )
        self.replay_from_log(log)

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
        # add move to log
        from_pos, to_pos = self.gid2hex[from_gid].pos, self.gid2hex[to_gid].pos
        self.log.append((from_pos, to_pos, new_piece))
        # make move
        self.board.move_piece(from_pos, to_pos, new_piece)
        self.move_number += 1

    def resignation_vote(self, vote: bool):
        """Get slog with resignation voting"""
        slog = self.slog
        votelog = ["X", "X", "X"]
        if vote:
            votelog[self.on_move] = "A"
        else:
            votelog[self.on_move] = "D"
        return slog + "R" + "".join(votelog)

    def resignation_vote_needed(self):
        """Return True if resignation vote is needed"""
        if len(self.vote_resign["log"]) > 0 and len(self.vote_resign["log"]) < 12:
            return True
        return False

    def resignation(self):
        """Return True if there is agreement on resignation"""
        if (len(self.vote_resign["log"]) // 4) == 3:
            if len(self.vote_resign["results"]) == 2:
                return True
        return False

    def draw_vote(self, vote: bool):
        """Get slog with draw voting"""
        slog = self.slog
        votelog = ["X", "X", "X"]
        if vote:
            votelog[self.on_move] = "A"
        else:
            votelog[self.on_move] = "D"
        return slog + "S" + "".join(votelog)

    def draw_vote_needed(self):
        """Return True if draw vote is needed"""
        if len(self.vote_draw["log"]) > 0 and len(self.vote_draw["log"]) < 12:
            return True
        return False

    def draw(self):
        """Return True if there is agreement on draw"""
        if (len(self.vote_draw["log"]) // 4) == 3:
            if len(self.vote_draw["results"]) == 3:
                return True
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
