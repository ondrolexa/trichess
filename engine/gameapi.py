from collections import defaultdict
from typing import NamedTuple

from engine.board import Board
from engine.pieces import King, Pawn, Pos, Rook
from engine.player import Player

# Vote chunks in the slog, by prefix: one cast vote (later condensed) or a
# set-vote holding all 3 votes. Everything else is a move.
VOTE_PREFIXES = {"r": "resign", "s": "draw"}
SET_VOTE_PREFIXES = {"R": "resign", "S": "draw"}
_SET_VOTE_PREFIX = {kind: prefix for prefix, kind in SET_VOTE_PREFIXES.items()}
_VOTE_PREFIX = {kind: prefix for prefix, kind in VOTE_PREFIXES.items()}


def is_vote_chunk(chunk):
    """True for a vote chunk (individual or set-vote), False for a move."""
    return chunk[:1] in VOTE_PREFIXES or chunk[:1] in SET_VOTE_PREFIXES


def iter_chunks(slog):
    """The slog's 4-char chunks; a trailing partial chunk is ignored."""
    for i in range(0, len(slog) - 3, 4):
        yield slog[i : i + 4]


class Voting:
    """Tracks resignation / draw voting among the three players.

    Slog vote encoding (4 chars per record; full spec in
    Help → For developers → Slog Format (webapp/templates/help.html)):
      Individual vote: ``r<v0><v1><v2>`` or ``s<v0><v1><v2>``
        where v{i} = A (accept) / D (decline) / X (not yet voted)
      Set-vote (all 3 in one chunk): ``R<v0><v1><v2>`` or ``S<v0><v1><v2>``

    *kind* is ``"resign"`` or ``"draw"`` throughout.
    """

    def __init__(self):
        self.clean()

    def clean(self):
        """Reset vote state to no-vote-in-progress."""
        self.kind = None
        self.accepts = []
        self.n_voted = 0
        self.log = ["X", "X", "X"]

    @property
    def slog(self):
        """Condensed 4-char set-vote record for the current vote state.

        Returns empty string when no vote is active.
        """
        if self.kind is None:
            return ""
        return _SET_VOTE_PREFIX[self.kind] + "".join(self.log)

    def set_votes(self, kind, v0, v1, v2):
        """Set all 3 votes at once (used when replaying a set-vote chunk)."""
        self.n_voted = 3
        self.kind = kind
        for player, vote in enumerate([v0, v1, v2]):
            self.log[player] = vote
            if vote == "A":
                self.accepts.append(player)

    def vote(self, kind, player, code):
        """Cast a single vote.  Starts a new vote if none is active."""
        if self.kind is None:
            self.kind = kind
        if self.kind != kind:
            raise ValueError(f"{self.kind} voting is in progress")
        if code != "X":
            if code == "A":
                self.accepts.append(player)
            self.log[player] = code
            self.n_voted += 1

    def chunk(self, kind, player, vote):
        """Generate a 4-char individual vote chunk for slog."""
        votelog = ["X", "X", "X"]
        votelog[player] = "A" if vote else "D"
        return _VOTE_PREFIX[kind] + "".join(votelog)

    def needed(self):
        """True when at least 1 vote cast but fewer than 3 (vote still in progress)."""
        return 0 < self.n_voted < 3

    def results(self, kind="any"):
        """List of player IDs who accepted; optionally filtered by vote kind."""
        if kind in (self.kind, "any"):
            return self.accepts
        else:
            return []

    def votes(self):
        """Return vote state dict when a vote is active (matches ``/info`` shape).

        Returns None when no vote is in progress.
        """
        if self.active():
            res = {
                "kind": self.kind,
                "n_voted": self.n_voted,
                0: self.log[0],
                1: self.log[1],
                2: self.log[2],
            }
            return res

    def finished(self):
        """True when all 3 players have voted."""
        return self.n_voted == 3

    def active(self):
        """True when any vote is in progress (1–3 votes cast)."""
        return self.n_voted > 0


# gid traversal per view_pid: (outer axis, inner axis, inner direction).
# The third axis is -outer-inner and must be on the board as well.
_GID_TRAVERSAL = {0: ("r", "q", 1), 1: ("s", "r", 1), 2: ("q", "r", -1)}


class GameAPI:
    """Game logic layer exposed to the HTTP API.

    All interaction between front-end and the engine goes through this class.
    The API is stateless — every request reconstructs state by calling
    ``replay_from_slog(slog)`` on a fresh instance.

    Keyword Args:
        name0 (str, optional): Name of player on position 0-bottom
        name1 (str, optional): Name of player on position 1-left
        name2 (str, optional): Name of player on position 2-right
        view_pid (int): Player perspective for gid numbering (0=bottom, 1=left, 2=right)

    Attributes:
        move_number (int): Number of moves played.
        players (dict): Three Player instances, keys 0, 1, 2.
        view_pid (int): Perspective for gid→hex mapping.
        board (Board): Current board state.
        voting (Voting): Resign / draw vote tracker.
        slog (str): Serialized game log.
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
        self.position_counts = defaultdict(int)
        self.position_counts[self._position_signature()] += 1

    # gid<->Pos ordering is a pure function of view_pid — same 169 cells,
    # same traversal order, every single time. Caching it (keyed by
    # view_pid, shared across all GameAPI instances process-wide) skips
    # rebuilding that nested-loop/bounds-check/Pos-construction traversal on
    # every replay and GameAPI.copy(). Only gid2hex actually needs rebuilding per instance, since it holds
    # this specific board's Hex objects.
    _GID_ORDER_CACHE: dict = {}

    def update_ui_mappings(self):
        """Build gid↔hex lookups for the current *view_pid*.

        Traversal order differs per view_pid:
          view 0 — row-major by r then q
          view 1 — by s then r
          view 2 — by q then r (reversed)
        Each maps the same 169 hex cells to a different gid ordering.
        """
        order = GameAPI._GID_ORDER_CACHE.get(self.view_pid)
        if order is None:
            outer, inner, step = _GID_TRAVERSAL[self.view_pid]
            order = []
            for a in range(-7, 8):
                for b in range(-7 * step, 8 * step, step):
                    third = -a - b
                    if -7 <= third <= 7:
                        axes = {outer: a, inner: b}
                        pos = Pos(axes.get("q", third), axes.get("r", third))
                        order.append((len(order), pos))
            GameAPI._GID_ORDER_CACHE[self.view_pid] = order

        board = self.board
        self.gid2hex = {}
        self.pos2gid = {}
        for gid, pos in order:
            self.gid2hex[gid] = board[pos]
            self.pos2gid[pos] = gid

    def copy(self):
        """Fast shallow copy — snapshots board state instead of replaying slog."""
        ga = GameAPI.__new__(GameAPI)
        ga.slog = self.slog
        ga.move_number = self.move_number
        ga.voting = self.voting
        ga.players = {}
        for pid, p in self.players.items():
            new_p = Player.__new__(Player)
            new_p.__dict__.update(p.__dict__)
            ga.players[pid] = new_p
        ga.view_pid = self.view_pid
        ga.board = self.board.copy(players=ga.players)
        ga.update_ui_mappings()
        # position_counts intentionally omitted — copy() is for exploring
        # hypothetical moves (the bot search used to call it once per node),
        # never for repetition()/endgame() on a real game.
        return ga

    @property
    def on_move(self):
        """Player ID whose turn it is.

        Skewed by ``voting.n_voted`` because the player casting a vote is
        also considered "on move".
        """
        return (self.move_number + self.voting.n_voted) % 3

    @property
    def on_move_previous(self):
        """Player ID who had the previous turn."""
        return (self.move_number + self.voting.n_voted - 1) % 3

    @property
    def last_move(self):
        """Last move as ``{gid, tgid}``, or None if no moves or last entry is a vote."""
        if self.slog:
            if not is_vote_chunk(self.slog[-4:]):
                from_pos, to_pos, new_piece = self.slog2pos(*self.slog[-4:])
                return {
                    "gid": self.pos2gid[from_pos],
                    "tgid": self.pos2gid[to_pos],
                }
        return None

    @property
    def pre_last_move(self):
        """Second-to-last move as ``{gid, tgid}``, or None if there isn't one."""
        if self.last_move is None:
            return None
        move_chunks = [c for c in iter_chunks(self.slog) if not is_vote_chunk(c)]
        if len(move_chunks) < 2:
            return None
        from_pos, to_pos, new_piece = self.slog2pos(*move_chunks[-2])
        return {
            "gid": self.pos2gid[from_pos],
            "tgid": self.pos2gid[to_pos],
        }

    def _chess_report(self, pid):
        """(in check, king gid, attackers by pid) for player *pid*."""
        res = {0: [], 1: [], 2: []}
        inchess, kingpos, pieces = self.board.in_chess(self.players[pid])
        for p in pieces:
            res[p.player.pid].append({"gid": self.pos2gid[p.pos], "piece": p.label})
        return inchess, self.pos2gid[kingpos], res

    def in_chess(self):
        """Check if player on move has chess"""
        return self._chess_report(self.on_move)

    def in_chess_next(self):
        """Check if the player after the one on move has chess"""
        return self._chess_report((self.on_move + 1) % 3)

    def eliminated(self):
        """Return eliminated pieces for players"""
        res = {0: [], 1: [], 2: []}
        for _, p in self.board.eliminated:
            res[p.player.pid].append(p.label)
        return res

    def eliminated_value(self):
        """Return total values of eliminated pieces for players"""
        res = {0: 0, 1: 0, 2: 0}
        for _, p in self.board.eliminated:
            res[p.player.pid] += p.value
        return res

    def player_eliminations(self):
        """Return values of opponent eliminated pieces for players"""
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
        """Decode a 4-char slog segment into (Pos, Pos, promotion_label).

        Promotion is signalled by a lowercase (offset +32) character
        in a specific position:
          q1 → Queen, r1 → Rook, q2 → Bishop, r2 → Knight.
        Coordinate characters never exceed "O", so "> O" is the flag.
        Spec: Help → For developers → Slog Format (webapp/templates/help.html).
        """
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
        """Encode a move into a 4-char slog segment.

        Promotion is encoded by adding 32 to the ASCII offset of a
        specific character (Q→q1, R→r1, B→q2, N→r2).
        """
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
        """Reset and replay a full game from a slog string.

        Handles three kinds of 4-char chunks:
          - Regular moves (decoded via ``slog2pos``)
          - Individual votes (``r``/``s`` prefix → accumulated)
          - Set-votes (``R``/``S`` prefix → set all 3 at once)
        Completed voting sequences are condensed into the slog automatically.
        """
        self.slog = ""
        self.move_number = 0
        self.board = Board(players=self.players)
        self.voting.clean()
        self.update_ui_mappings()
        self.position_counts = defaultdict(int)
        self.position_counts[self._position_signature()] += 1
        # replay
        for chunk in iter_chunks(s):
            if not apply_chunk(self.voting, chunk):
                from_pos, to_pos, new_piece = self.slog2pos(*chunk)
                # make move
                self.board.move_piece(from_pos, to_pos, new_piece)
                self.move_number += 1
                self.position_counts[self._position_signature()] += 1

            # fix slog when just finished voting
            if self.voting.finished() and chunk[0] in VOTE_PREFIXES:
                self.slog = self.slog[:-8] + self.voting.slog
            else:
                self.slog += chunk

    def logtail(self, n=5):
        return self.slog[-4 * n :]

    def valid_moves(self, gid):
        """Return all legal moves from *gid* for the player on move.

        Filters candidate moves to those that do not leave the moving
        player in check.

        Returns a list of ``{tgid, kind, promotion}`` dicts.
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
                        targets.append(
                            {
                                "tgid": tgid,
                                "kind": "attack"
                                if self.board[pos].has_piece
                                else "safe",
                                "promotion": self.board.promotion(piece, pos),
                            }
                        )
        return targets

    def make_move(self, from_gid, to_gid, new_piece=""):
        """Execute a move and record it in the slog.

        Does nothing when a vote is in progress (voting.needed()).
        """
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
        return self.slog + self.voting.chunk("resign", self.on_move, vote)

    def draw_vote(self, vote: bool):
        """Get slog with draw voting"""
        return self.slog + self.voting.chunk("draw", self.on_move, vote)

    def resignation(self):
        """True when 2 of 3 players accepted a resign vote."""
        return (
            self.voting.kind == "resign"
            and self.voting.finished()
            and len(self.voting.accepts) == 2
        )

    def draw(self):
        """True when all 3 players accepted a draw vote."""
        return (
            self.voting.kind == "draw"
            and self.voting.finished()
            and len(self.voting.accepts) == 3
        )

    def move_possible(self):
        """True when the player on move has at least one legal move.

        Returns False when the game has ended by resignation or draw.
        """
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

    def _position_signature(self):
        """Hashable snapshot of everything that affects future legal moves.

        Made of the on-move player, every occupied hex's (pos, label,
        owning pid), and the ``used`` flag of Pawn/King/Rook pieces — the
        only pieces whose move generation depends on it (a pawn's
        double-step and a king/rook's castling eligibility). Board
        iteration order is fixed, so two equal positions always produce an
        identical signature without needing to sort.
        """
        pieces = []
        for hex in self.board:
            if hex.has_piece:
                piece = hex.piece
                entry = (hex.pos.q, hex.pos.r, piece.label, piece.player.pid)
                if isinstance(piece, (Pawn, King, Rook)):
                    entry += (piece.used,)
                pieces.append(entry)
        return (self.on_move, tuple(pieces))

    def repetition(self):
        """True when the current position has now occurred 3 or more times."""
        return self.position_counts[self._position_signature()] >= 3

    def endgame(self):
        """Classify how the game ended, or None while it's still ongoing.

        Checked in this order: an explicit draw vote, an explicit
        resignation vote, threefold repetition (checked independently of
        move availability — a position can recur while the on-move player
        still has legal moves), then — only once the on-move player has no
        legal move at all — checkmate vs stalemate depending on whether
        their king is currently attacked.
        """
        if self.draw():
            return "draw"
        if self.resignation():
            return "resignation"
        if self.repetition():
            return "repetition"
        if not self.move_possible():
            in_chess, _, _ = self.in_chess()
            return "checkmate" if in_chess else "stalemate"
        return None

    def outcome_scores(self, kind=None):
        """Points (out of 2.0) per player of a finished game: {pid: score}.

        Resignation gives the player who declined 2.0; checkmate splits 2.0
        by how many pieces each player attacks the mated king with; draw,
        stalemate and repetition give everyone 2/3. *kind* is the endgame()
        result, computed here when not given (bot search passes it in, since
        endgame()'s legal-move scan is the expensive part).
        """
        kind = kind or self.endgame()
        scores = {0: 0.0, 1: 0.0, 2: 0.0}
        if kind == "resignation":
            resigned = self.voting.results(kind="resign")
            scores[({0, 1, 2} - set(resigned)).pop()] = 2.0
            return scores
        if kind == "checkmate":
            _, _, who = self.in_chess()
            attackers = [len(pieces) for pieces in who.values()]
            total = sum(attackers)
            if total:
                for pid, count in enumerate(attackers):
                    scores[pid] = count * 2 / total
            return scores
        return {0: 2.0 / 3, 1: 2.0 / 3, 2: 2.0 / 3}


def get_game(view_pid, slog):
    ga = GameAPI(view_pid)
    ga.replay_from_slog(slog)
    return ga


class SlogSummary(NamedTuple):
    move_number: int
    on_move: int
    voting_active: bool


def apply_chunk(voting, chunk):
    """Apply one slog chunk's votes to *voting*; False for a move chunk,
    which the caller applies. A vote that finished on an earlier chunk is
    cleared first. Shared by GameAPI.replay_from_slog and slog_summary."""
    if voting.finished():
        voting.clean()
    prefix = chunk[0]
    if prefix in VOTE_PREFIXES:
        kind = VOTE_PREFIXES[prefix]
        for player, code in enumerate(chunk[1:]):
            voting.vote(kind, player, code)
    elif prefix in SET_VOTE_PREFIXES:
        voting.set_votes(SET_VOTE_PREFIXES[prefix], *chunk[1:])
    else:
        return False
    return True


def slog_summary(slog):
    """``move_number``, ``on_move`` and whether a vote is in progress, read
    from the slog string alone — no board replay, so microseconds instead of
    milliseconds. Meant for pages listing many games.

    Vote handling is GameAPI.replay_from_slog's own (apply_chunk).
    """
    voting = Voting()
    move_number = 0
    for chunk in iter_chunks(slog):
        if not apply_chunk(voting, chunk):
            move_number += 1
    return SlogSummary(move_number, (move_number + voting.n_voted) % 3, voting.active())
