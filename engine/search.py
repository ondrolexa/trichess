"""Compact position + alpha-beta search used only by the bot.

The object engine (Board/Hex/Piece/Pos) stays the source of truth for the web
app. It is too slow for a search tree: a node used to cost a whole
GameAPI.copy(), and every move generated thousands of Pos objects. This module
holds the same rules as flat lists over the 169 cells, makes and unmakes moves
in place, and precomputes every move/attack target at import time. All tables
are derived from the engine's own definitions (Player.STEP, the pieces'
_moves, Board.opposite, CASTLING_ROOK_MOVES), and tests/test_search.py checks
move generation, evaluation and the search result against the object engine.

The layout (ints in flat arrays, no objects per node) is kept Rust-shaped on
purpose, so a native port can follow it line by line if Python is not enough.

Semantics deliberately mirror the object engine, quirks included:
- legality ("does this leave my king attacked?") follows Board._is_attacked and
  Board.test_move_piece: a plain displacement, no promotion or castling rook hop;
- castling's "king not in check / not passing through check" follows
  Board.pos_in_chess, i.e. the squares an enemy piece could *move* to — on an
  empty square that counts pawn pushes but not pawn captures;
- a captured king keeps its last square in ``kings`` (Player._king_piece keeps
  pointing at its old Hex there).
"""

import random
import time

from engine.board import CASTLING_ROOK_MOVES, Board
from engine.eval import (
    _CENTER_BONUS,
    _PROMO_BONUS,
    ACTIVITY_WEIGHT,
    DEFENDER_CAP,
    KING_SAFETY_WEIGHT,
    MATERIAL_WEIGHT,
    MOBILITY_CAP,
    MOBILITY_WEIGHT,
)
from engine.pieces import Bishop, King, Knight, Pawn, Queen, Rook
from engine.player import STEP, Player

PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
_CLASSES = {PAWN: Pawn, KNIGHT: Knight, BISHOP: Bishop, ROOK: Rook, QUEEN: Queen}
_CLASSES[KING] = King
TYPE_OF_LABEL = {"P": PAWN, "N": KNIGHT, "B": BISHOP, "R": ROOK, "Q": QUEEN, "K": KING}
VALUE = [0] * 7
for _t, _cls in _CLASSES.items():
    VALUE[_t] = _cls(Player(0)).value

# A piece is the int pid * 8 + type (types 1..6), 0 is an empty cell.
# code >> 3 is the owner, code & 7 the type.

# Cells in view-0 gid order — the same order Board iterates its hexes in, so
# move lists (and thus move ordering ties) come out exactly as before.
CELLS = [(q, r) for r in range(-7, 8) for q in range(-7, 8) if -7 <= -q - r <= 7]
INDEX = {c: i for i, c in enumerate(CELLS)}
N = len(CELLS)
ENEMIES = ((1, 2), (0, 2), (0, 1))


def _target(i: int, steps, pid: int) -> int:
    """Cell reached from cell *i* by summing *steps* (-1 when off the board)."""
    q, r = CELLS[i]
    for s in steps:
        dq, dr = STEP[pid][s]
        q += dq
        r += dr
    return INDEX.get((q, r), -1)


def _ok(c: int) -> bool:
    return c >= 0


def _moves_of(t: int):
    piece = _CLASSES[t](Player(0))  # unused piece: pawns list their double steps
    return piece._moves


# Forward move tables, per pid and cell, grouped by move kind. Every piece's
# _moves list keeps one kind together and in this order, so the generated
# move order matches Piece.pos_candidates.
PAWN_FWD = [[None] * N for _ in range(3)]  # kind "f"
PAWN_ATK = [[None] * N for _ in range(3)]  # kind "a"
PAWN_DBL = [[None] * N for _ in range(3)]  # kind "d": (middle, target)
KNIGHT_STEPS = [[None] * N for _ in range(3)]
KING_STEPS = [[None] * N for _ in range(3)]
CASTLE = [[None] * N for _ in range(3)]  # kind "c": (dest, over, extra, rook)
RAYS = [[[None] * N for _ in range(7)] for _ in range(3)]  # kind "n"

for _pid in range(3):
    for _i in range(N):
        _fwd, _atk, _dbl = [], [], []
        for _m in _moves_of(PAWN):
            _to = _target(_i, _m.steps, _pid)
            if _m.kind == "f" and _ok(_to):
                _fwd.append(_to)
            elif _m.kind == "a" and _ok(_to):
                _atk.append(_to)
            elif _m.kind == "d":
                _mid = _target(_i, _m.steps[:1], _pid)
                if _ok(_mid) and _ok(_to):
                    _dbl.append((_mid, _to))
        PAWN_FWD[_pid][_i] = tuple(_fwd)
        PAWN_ATK[_pid][_i] = tuple(_atk)
        PAWN_DBL[_pid][_i] = tuple(_dbl)
        KNIGHT_STEPS[_pid][_i] = tuple(
            c for c in (_target(_i, m.steps, _pid) for m in _moves_of(KNIGHT)) if _ok(c)
        )
        _king, _castle = [], []
        for _m in _moves_of(KING):
            if _m.kind == "s":
                _to = _target(_i, _m.steps, _pid)
                if _ok(_to):
                    _king.append(_to)
            elif _m.kind == "c":
                _dest = _target(_i, _m.steps, _pid)
                _step = _m.steps[:1]
                _over = _target(_i, _step, _pid)
                if _m.steps[0] == "SL":
                    _extra = -1
                    _rook = _target(_dest, _step, _pid) if _ok(_dest) else -1
                else:
                    _extra = _target(_dest, _step, _pid) if _ok(_dest) else -1
                    _rook = _target(_extra, _step, _pid) if _ok(_extra) else -1
                if _ok(_dest) and _ok(_rook):
                    _castle.append((_dest, _over, _extra, _rook))
        KING_STEPS[_pid][_i] = tuple(_king)
        CASTLE[_pid][_i] = tuple(_castle)
        for _t in (BISHOP, ROOK, QUEEN):
            _rays = []
            for _m in _moves_of(_t):
                _ray, _cur = [], _i
                for _ in range(14):
                    _cur = _target(_cur, _m.steps, _pid)
                    if not _ok(_cur):
                        break
                    _ray.append(_cur)
                _rays.append(tuple(_ray))
            RAYS[_pid][_t][_i] = tuple(_rays)


def _reverse(table):
    rev = [[[] for _ in range(N)] for _ in range(3)]
    for pid in range(3):
        for i in range(N):
            for c in table[pid][i]:
                rev[pid][c].append(i)
    return [[tuple(cells) for cells in per_pid] for per_pid in rev]


# Reverse tables: which cells a piece of pid must stand on to reach a cell.
REV_PAWN_FWD = _reverse(PAWN_FWD)
REV_PAWN_ATK = _reverse(PAWN_ATK)
REV_KNIGHT = _reverse(KNIGHT_STEPS)
REV_KING = _reverse(KING_STEPS)
REV_PAWN_DBL = [[[] for _ in range(N)] for _ in range(3)]
for _pid in range(3):
    for _i in range(N):
        for _mid, _to in PAWN_DBL[_pid][_i]:
            REV_PAWN_DBL[_pid][_to].append((_i, _mid))
REV_PAWN_DBL = [[tuple(x) for x in per_pid] for per_pid in REV_PAWN_DBL]

# Slider rays seen from the target cell, each with a bitmask of the piece
# types that attack along it. Rays are symmetric, so this needs every pid to
# slide in the same 6 + 6 directions — asserted rather than assumed.
_ROOK_MASK = (1 << ROOK) | (1 << QUEEN)
_BISHOP_MASK = (1 << BISHOP) | (1 << QUEEN)
for _pid in range(3):
    for _i in range(N):
        _r = set(RAYS[_pid][ROOK][_i])
        _b = set(RAYS[_pid][BISHOP][_i])
        assert _r == set(RAYS[0][ROOK][_i]) and _b == set(RAYS[0][BISHOP][_i])
        assert set(RAYS[_pid][QUEEN][_i]) == _r | _b
SLIDER_RAYS = [
    tuple((ray, _ROOK_MASK) for ray in RAYS[0][ROOK][i] if ray)
    + tuple((ray, _BISHOP_MASK) for ray in RAYS[0][BISHOP][i] if ray)
    for i in range(N)
]

_OPPOSITE = Board().opposite
PROMO = [[False] * N for _ in range(3)]
PROMO_BONUS_AT = [[0] * N for _ in range(3)]
for _pid in range(3):
    for _p in _OPPOSITE[_pid]:
        PROMO[_pid][INDEX[(_p.q, _p.r)]] = True


def _distance(a: int, b: int) -> int:
    (q1, r1), (q2, r2) = CELLS[a], CELLS[b]
    return max(abs(q1 - q2), abs(r1 - r2), abs(q1 + r1 - q2 - r2))


CASTLING_ROOK = {
    (INDEX[kf], INDEX[kt]): (INDEX[rf], INDEX[rt])
    for (kf, kt), (rf, rt) in CASTLING_ROOK_MOVES.items()
}

# The outcome share of a finished game (0.0-2.0) and evaluate() (material
# scale, typically tens of points) can't be mixed at one tree level: a
# checkmate (2.0) would look worse than any ordinary move (~50). Finished
# nodes are fed to the search as terminal_value() instead, which rescales the
# share far beyond any reachable evaluation.
WIN_VALUE = 10_000.0


# Zobrist keys for the transposition table. One key per (cell, piece code,
# used flag) plus one per side to move, drawn from a fixed seed so Python and
# the Rust port (which receives these lists from engine/native.py) hash
# identically. A cell's contribution is 0 when empty.
_rng = random.Random(0x7C1E55)
ZOB = [_rng.getrandbits(64) for _ in range(N * 24 * 2)]
ZOB_STM = [_rng.getrandbits(64) for _ in range(3)]
TT_BITS = 20
MAX_KILLER_DEPTH = 64
# Futility pruning one ply above the leaves. A quiet move (no capture, no
# promotion) leaves material unchanged, so its leaf score stays within
# FUTILITY_MARGIN of the node's own evaluation (measured over ~12k quiet moves
# of the reference games with the current eval weights: max 1.92, 99.9th
# percentile 1.32, 99th 0.66 -- re-measure after any eval change). When even that margin
# cannot move the node's value past the window, the remaining quiet moves are
# skipped -- except moves that give check or leave no reply, which may be a
# mate or stalemate and are searched normally. Negative disables it.
#
# Most quiet moves are ruled out as checks without making them
# (Position.may_give_check: a direct attack from the destination, a discovered
# slider attack through the origin, or any king move); only the few candidates
# are made and tested with attacked(). Stalemate is ruled out by requiring the next player
# to have at least FUTILITY_MIN_MOVERS pieces with a pseudo-legal move.
FUTILITY_MARGIN = 2.5


FUTILITY_MIN_MOVERS = 4


def _init_check_tables():
    # att_mask[x][c]: slider types (1 << kind) that, standing on c, could
    # attack cell x along one of x's rays if nothing were in between.
    att_mask = [[0] * N for _ in range(N)]
    for x in range(N):
        for ray, mask in SLIDER_RAYS[x]:
            for c in ray:
                att_mask[x][c] |= mask
    return att_mask


ATT_MASK = _init_check_tables()


class Timeout(Exception):
    """Raised inside the search when its deadline has passed."""


def _init_eval_tables():
    center = [_CENTER_BONUS.get(_distance(i, INDEX[(0, 0)]), 0) for i in range(N)]
    for pid in range(3):
        targets = [INDEX[(p.q, p.r)] for p in _OPPOSITE[pid]]
        for i in range(N):
            d = min(_distance(i, t) for t in targets)
            PROMO_BONUS_AT[pid][i] = _PROMO_BONUS[d] if d < len(_PROMO_BONUS) else 0
    near = [frozenset(j for j in range(N) if _distance(i, j) <= 2) for i in range(N)]
    return center, near


CENTER_BONUS_AT, NEAR2 = _init_eval_tables()


class Position:
    """Board state as flat lists, mutated in place by make()/unmake()."""

    __slots__ = ("board", "used", "kings", "stm", "hash")

    def __init__(self, board, used, kings, stm):
        self.board = board
        self.used = used
        self.kings = kings
        self.stm = stm
        h = ZOB_STM[stm]
        for i, code in enumerate(board):
            if code:
                h ^= ZOB[(i * 24 + code) * 2 + used[i]]
        self.hash = h

    @classmethod
    def from_game(cls, ga) -> "Position":
        board = [0] * N
        used = [False] * N
        for hex in ga.board:
            piece = hex.piece
            if piece is not None:
                i = INDEX[(hex.pos.q, hex.pos.r)]
                board[i] = piece.player.pid * 8 + TYPE_OF_LABEL[piece.label]
                used[i] = piece.used
        kings = [
            INDEX[(p.king_piece.hex.pos.q, p.king_piece.hex.pos.r)]
            for p in (ga.players[0], ga.players[1], ga.players[2])
        ]
        return cls(board, used, kings, ga.on_move)

    # ── attack queries ────────────────────────────────────────────────────

    def attacked(self, x: int, pid: int) -> bool:
        """Is cell *x* attacked by an enemy of *pid*? (Board._is_attacked)"""
        board = self.board
        for ray, mask in SLIDER_RAYS[x]:
            for c in ray:
                code = board[c]
                if code:
                    if code >> 3 != pid and (1 << (code & 7)) & mask:
                        return True
                    break
        for e in ENEMIES[pid]:
            knight = e * 8 + KNIGHT
            for c in REV_KNIGHT[e][x]:
                if board[c] == knight:
                    return True
            king = e * 8 + KING
            for c in REV_KING[e][x]:
                if board[c] == king:
                    return True
            pawn = e * 8 + PAWN
            for c in REV_PAWN_ATK[e][x]:
                if board[c] == pawn:
                    return True
        return False

    def reached(self, x: int, pid: int) -> bool:
        """Can an enemy of *pid* move to cell *x*? (Board.pos_in_chess)

        Unlike attacked(), this depends on what stands on *x*: an empty cell
        is reached by pawn pushes rather than pawn captures, and no piece
        "reaches" a cell held by its own side.
        """
        board = self.board
        xcode = board[x]
        xowner = xcode >> 3 if xcode else -1
        for ray, mask in SLIDER_RAYS[x]:
            for c in ray:
                code = board[c]
                if code:
                    owner = code >> 3
                    if owner != pid and owner != xowner and (1 << (code & 7)) & mask:
                        return True
                    break
        for e in ENEMIES[pid]:
            if e == xowner:
                continue
            knight = e * 8 + KNIGHT
            for c in REV_KNIGHT[e][x]:
                if board[c] == knight:
                    return True
            king = e * 8 + KING
            for c in REV_KING[e][x]:
                if board[c] == king:
                    return True
            pawn = e * 8 + PAWN
            if xcode:
                for c in REV_PAWN_ATK[e][x]:
                    if board[c] == pawn:
                        return True
            else:
                for c in REV_PAWN_FWD[e][x]:
                    if board[c] == pawn:
                        return True
                for c, mid in REV_PAWN_DBL[e][x]:
                    if board[c] == pawn and not self.used[c] and not board[mid]:
                        return True
        return False

    # ── move generation ───────────────────────────────────────────────────

    def targets(self, i: int, castling: bool) -> list:
        """Pseudo-legal destinations of the piece on *i*
        (Board.possible_moves, same order)."""
        board = self.board
        code = board[i]
        pid = code >> 3
        t = code & 7
        out = []
        if t == PAWN:
            for c in PAWN_FWD[pid][i]:
                if not board[c]:
                    out.append(c)
            for c in PAWN_ATK[pid][i]:
                x = board[c]
                if x and x >> 3 != pid:
                    out.append(c)
            if not self.used[i]:
                for mid, c in PAWN_DBL[pid][i]:
                    if not board[mid] and not board[c]:
                        out.append(c)
        elif t == KNIGHT or t == KING:
            for c in (KNIGHT_STEPS if t == KNIGHT else KING_STEPS)[pid][i]:
                x = board[c]
                if not x or x >> 3 != pid:
                    out.append(c)
            if t == KING and castling:
                out.extend(self._castling(i, pid))
        else:
            for ray in RAYS[pid][t][i]:
                for c in ray:
                    x = board[c]
                    if not x:
                        out.append(c)
                    else:
                        if x >> 3 != pid:
                            out.append(c)
                        break
        return out

    def _castling(self, i: int, pid: int) -> list:
        # Same conditions as Piece.pos_candidates, cheapest first (all of
        # them must hold, so the order doesn't change the result).
        out = []
        if self.used[i]:
            return out
        board = self.board
        for dest, over, extra, rook in CASTLE[pid][i]:
            if board[over] or board[dest]:
                continue
            if extra >= 0 and board[extra]:
                continue
            rc = board[rook]
            if not rc or rc & 7 != ROOK or self.used[rook]:
                continue
            if self.reached(i, pid) or self.reached(over, pid):
                continue
            out.append(dest)
        return out

    def mobility(self, i: int) -> int:
        """len(targets(i, castling=False)) without building the list.

        Deliberately a copy of targets()'s logic (it runs for every piece at
        every leaf, so no list is built): any change to targets() must be
        made here too."""
        board = self.board
        code = board[i]
        pid = code >> 3
        t = code & 7
        n = 0
        if t == PAWN:
            for c in PAWN_FWD[pid][i]:
                if not board[c]:
                    n += 1
            for c in PAWN_ATK[pid][i]:
                x = board[c]
                if x and x >> 3 != pid:
                    n += 1
            if not self.used[i]:
                for mid, c in PAWN_DBL[pid][i]:
                    if not board[mid] and not board[c]:
                        n += 1
        elif t == KNIGHT or t == KING:
            for c in (KNIGHT_STEPS if t == KNIGHT else KING_STEPS)[pid][i]:
                x = board[c]
                if not x or x >> 3 != pid:
                    n += 1
        else:
            for ray in RAYS[pid][t][i]:
                for c in ray:
                    x = board[c]
                    if not x:
                        n += 1
                    else:
                        if x >> 3 != pid:
                            n += 1
                        break
        return n

    def is_legal(self, i: int, to: int) -> bool:
        """Board.test_move_piece: displace, test own king, restore."""
        board = self.board
        code = board[i]
        pid = code >> 3
        captured = board[to]
        board[to] = code
        board[i] = 0
        king = to if code & 7 == KING else self.kings[pid]
        res = self.attacked(king, pid)
        board[i] = code
        board[to] = captured
        return not res

    def legal_moves(self) -> list:
        """All legal moves of the side to move as (from, to, promotion, victim)."""
        board = self.board
        pid = self.stm
        promo = PROMO[pid]
        moves = []
        for i in range(N):
            code = board[i]
            if code and code >> 3 == pid:
                is_pawn = code & 7 == PAWN
                for to in self.targets(i, True):
                    if self.is_legal(i, to):
                        moves.append((i, to, is_pawn and promo[to], board[to]))
        return moves

    def has_legal_move(self) -> bool:
        board = self.board
        pid = self.stm
        for i in range(N):
            code = board[i]
            if code and code >> 3 == pid:
                for to in self.targets(i, False):
                    if self.is_legal(i, to):
                        return True
        # Castling only matters once nothing else is legal.
        k = self.kings[pid]
        if board[k] == pid * 8 + KING:
            for to in self._castling(k, pid):
                if self.is_legal(k, to):
                    return True
        return False

    def may_give_check(self, i: int, to: int, nxt: int, king: int) -> bool:
        """Conservative: False only if the quiet move i -> to cannot leave
        player *nxt*'s king (on cell *king*) attacked, given it is not attacked
        now. A superset of the real checks; attacked() decides the rest."""
        code = self.board[i]
        k = code & 7
        e = code >> 3
        if k == KING:
            return True
        if k == KNIGHT:
            if to in REV_KNIGHT[e][king]:
                return True
        elif k == PAWN:
            if to in REV_PAWN_ATK[e][king]:
                return True
        elif ATT_MASK[king][to] & (1 << k):
            return True
        # Discovered: i is the first piece on one of the king's rays and the
        # next piece beyond it is an enemy slider that moves along that ray.
        board = self.board
        for ray, mask in SLIDER_RAYS[king]:
            if i not in ray:
                continue
            seen = False
            for c in ray:
                if c == i:
                    seen = True
                    continue
                x = board[c]
                if x:
                    if not seen:
                        break
                    if x >> 3 != nxt and (1 << (x & 7)) & mask:
                        return True
                    break
        return False

    def futility_safe(self) -> bool:
        """True when quiet-move futility pruning is allowed here: the player
        after the side to move is not in check and has several pieces that can
        move (so no single quiet move can stalemate it)."""
        nxt = (self.stm + 1) % 3
        if self.attacked(self.kings[nxt], nxt):
            return False
        movers = 0
        saved = self.stm
        self.stm = nxt
        try:
            for i in range(N):
                code = self.board[i]
                if code and code >> 3 == nxt and self.targets(i, False):
                    movers += 1
                    if movers >= FUTILITY_MIN_MOVERS:
                        return True
        finally:
            self.stm = saved
        return False

    def has_pseudo_move(self) -> bool:
        """Cheap existence check used at quiet leaves.

        A pseudo-legal move can still be illegal because it exposes the king,
        so this is not a full stalemate test — but it rules out the common
        "no legal move at all" case without running is_legal() per candidate.
        """
        board = self.board
        pid = self.stm
        for i in range(N):
            code = board[i]
            if code and code >> 3 == pid and self.targets(i, False):
                return True
        k = self.kings[pid]
        if board[k] == pid * 8 + KING and self._castling(k, pid):
            return True
        return False

    # ── make / unmake ─────────────────────────────────────────────────────

    def make(self, i: int, to: int, label: str = "") -> tuple:
        """Board.move_piece in place; returns what unmake() needs."""
        board = self.board
        used = self.used
        code = board[i]
        pid = code >> 3
        h = h_old = self.hash
        undo = (i, to, code, used[i], board[to], used[to], self.kings[pid], None, h)
        h ^= ZOB[(i * 24 + code) * 2 + used[i]]
        if board[to]:
            h ^= ZOB[(to * 24 + board[to]) * 2 + used[to]]
        if label and code & 7 == PAWN and PROMO[pid][to]:
            code = pid * 8 + TYPE_OF_LABEL[label]
        board[to] = code
        used[to] = True
        board[i] = 0
        used[i] = False
        h ^= ZOB[(to * 24 + code) * 2 + 1]
        if code & 7 == KING:
            self.kings[pid] = to
            rook = CASTLING_ROOK.get((i, to))
            if rook is not None:
                rf, rt = rook
                undo = undo[:7] + (
                    (rf, rt, board[rf], used[rf], board[rt], used[rt]),
                    h_old,
                )
                rcode = board[rf]
                h ^= ZOB[(rf * 24 + rcode) * 2 + used[rf]]
                if board[rt]:
                    h ^= ZOB[(rt * 24 + board[rt]) * 2 + used[rt]]
                board[rt] = rcode
                used[rt] = True
                board[rf] = 0
                used[rf] = False
                h ^= ZOB[(rt * 24 + rcode) * 2 + 1]
        old = self.stm
        self.stm = new = (old + 1) % 3
        self.hash = h ^ ZOB_STM[old] ^ ZOB_STM[new]
        return undo

    def unmake(self, undo: tuple) -> None:
        i, to, code, used_i, captured, used_to, king, rook, self.hash = undo
        board = self.board
        used = self.used
        if rook is not None:
            rf, rt, rcode, rused, tcode, tused = rook
            board[rf], used[rf], board[rt], used[rt] = rcode, rused, tcode, tused
        board[i] = code
        used[i] = used_i
        board[to] = captured
        used[to] = used_to
        self.kings[code >> 3] = king
        self.stm = (self.stm + 2) % 3

    # ── evaluation ────────────────────────────────────────────────────────

    def evaluate(self, pid: int) -> float:
        """Exact port of engine.eval.evaluate_for_pid."""
        board = self.board
        king = self.kings[pid]
        near = NEAR2[king]
        promo_bonus = PROMO_BONUS_AT[pid]
        my_mat = 0.0
        opp_mat = 0.0
        my_mob = 0
        activity = 0.0
        defenders = 0
        for i in range(N):
            code = board[i]
            if not code:
                continue
            if code >> 3 == pid:
                my_mat += VALUE[code & 7]
                my_mob += min(self.mobility(i), MOBILITY_CAP)
                activity += CENTER_BONUS_AT[i]
                if code & 7 == PAWN:
                    activity += promo_bonus[i]
                if i in near:
                    defenders += 1
            else:
                opp_mat += VALUE[code & 7]

        material = my_mat - opp_mat / 2.0
        king_safety = (
            min(defenders, DEFENDER_CAP) - (1 if self.attacked(king, pid) else 0)
        ) * 2.0
        return (
            material * MATERIAL_WEIGHT
            + my_mob * MOBILITY_WEIGHT
            + king_safety * KING_SAFETY_WEIGHT
            + activity * ACTIVITY_WEIGHT
        )

    def _capture_loss(self, pid: int, gain: int, only_to: int = -1) -> int:
        """Worst material swing for *pid* from the side-to-move's captures.

        ``self.stm`` is the opponent about to move; ``gain`` is the value of
        the piece our move just captured. Returns <= 0: negative means the
        opponent has a capture that leaves us behind by that many material
        points (SEE-lite, no third-player recapture modelling). With *only_to*
        only captures landing on that cell count.
        """
        worst = 0
        for f2, t2, promo, victim in self.legal_moves():
            if not victim or victim >> 3 != pid or only_to >= 0 and t2 != only_to:
                continue
            v = VALUE[victim & 7]
            # A promoting capture lands a queen, not a pawn.
            a = VALUE[QUEEN] if promo else VALUE[self.board[f2] & 7]
            undo = self.make(f2, t2, "Q" if promo else "")
            saved = self.stm
            self.stm = pid
            try:
                recapture = any(m[1] == t2 and m[3] for m in self.legal_moves())
            finally:
                self.stm = saved
                self.unmake(undo)
            net = gain - v + (a if recapture else 0)
            if net < worst:
                worst = net
        return worst

    def see_loss_after(self, i: int, to: int, label: str) -> int:
        """Material loss for the player on move if (i, to, label) is played
        and the next opponent replies immediately. 0 or positive = safe.

        The moved piece is also tested against the *other* opponent, as if it
        were to move right after (its captures landing on *to* only): a piece
        that either opponent can take for less than it is worth is a loss."""
        pid = self.stm
        gain = VALUE[self.board[to] & 7] if self.board[to] else 0
        undo = self.make(i, to, label)
        try:
            loss = self._capture_loss(pid, gain)
            next_opp = self.stm
            self.stm = (pid + 2) % 3
            try:
                loss = min(loss, self._capture_loss(pid, gain, to))
            finally:
                self.stm = next_opp
        finally:
            self.unmake(undo)
        return loss

    def terminal_score(self, pid: int) -> float:
        """Outcome share for *pid* once the side to move has no legal move
        (bot._terminal_score: checkmate split by attacker count, else 2/3)."""
        board = self.board
        stm = self.stm
        king = self.kings[stm]
        tot = [0, 0, 0]
        for i in range(N):
            code = board[i]
            if code and code >> 3 != stm and king in self.targets(i, False):
                tot[code >> 3] += 1
        total = sum(tot)
        if total > 0:
            return tot[pid] * 2.0 / total
        return 2.0 / 3


def terminal_value(score: float, depth_left: int) -> float:
    """Search-scale value of an outcome share (see WIN_VALUE).

    The share is centred on the draw share (2/3 -> 0) and scaled by
    WIN_VALUE, so a win dominates and a loss is worse than any evaluation.
    *depth_left* breaks ties: quicker wins and slower losses score higher.
    """
    value = (score - 2.0 / 3) * WIN_VALUE
    if value > 0:
        return value + depth_left
    if value < 0:
        return value - depth_left
    return value


_LABELS = ("Q", "R", "B", "N")


class Search:
    """Paranoid alpha-beta search: the root pid maximises its score and every
    opponent move is assumed to minimise it (both opponents pooled into one
    minimising side).

    Same algorithm as the GameAPI-based search it replaced (same node count): promotions first,
    then captures by MVV-LVA, then quiet moves by the history heuristic; all
    four promotion pieces are tried. *deadline* (time.monotonic() value)
    makes search_root() raise Timeout once passed.
    """

    def __init__(self, pos: Position, history: dict | None = None):
        self.pos = pos
        # Transposition table: fixed size, always-replace, indexed by the low
        # hash bits; entries are (key, depth, flag, score, from, to). The Rust
        # port uses the same layout so results match entry for entry.
        self.tt = [None] * (1 << TT_BITS)
        # Two killer moves (from, to) per remaining depth: quiet moves that
        # recently caused a cutoff at the same depth are tried before the
        # other quiet moves.
        self.killers = [[None, None] for _ in range(MAX_KILLER_DEPTH)]
        self.pid = pos.stm
        self.history = {} if history is None else history
        self.deadline = None
        self.nodes = 0
        # Filled at the end of a completed search_root() (see safe_root()).
        # A deeper iteration cut off by the deadline leaves the previous
        # iteration's list intact, which is exactly what the filter needs.
        self.root_scores = []
        self.last_depth = 0

    def order(self, moves: list, depth: int = 0) -> list:
        history = self.history
        board = self.pos.board
        k0, k1 = self.killers[depth]

        def key(m):
            i, to, promo, victim = m
            if promo:
                return (3, 0.0)
            if victim:
                return (2, VALUE[victim & 7] * 10 - VALUE[board[i] & 7])
            mv = (i, to)
            if mv == k0 or mv == k1:
                return (1, 0)
            return (0, history.get(mv, 0))

        return sorted(moves, key=key, reverse=True)

    def _tick(self):
        self.nodes += 1
        if (
            self.deadline is not None
            and not self.nodes & 1023
            and time.monotonic() > self.deadline
        ):
            raise Timeout

    def minimax(self, depth: int, alpha: float, beta: float) -> float:
        self._tick()
        pos = self.pos
        pid = self.pid
        if depth == 0:
            # Checkmate always requires the side to move's king to be under
            # attack, so only pay for has_legal_move() there. Quiet leaves
            # (the vast majority) just need to rule out the trivial
            # "no pseudo-legal move at all" stalemate case.
            stm = pos.stm
            if pos.attacked(pos.kings[stm], stm):
                if not pos.has_legal_move():
                    return terminal_value(pos.terminal_score(pid), depth)
            elif not pos.has_pseudo_move():
                return terminal_value(pos.terminal_score(pid), depth)
            return pos.evaluate(pid)
        key = pos.hash
        slot = key & ((1 << TT_BITS) - 1)
        entry = self.tt[slot]
        hint = None
        if entry is not None and entry[0] == key:
            hint = (entry[4], entry[5])
            # Only a result of exactly this remaining depth is reused: mate
            # scores carry the remaining depth, so deeper results would
            # change which mate looks quickest.
            if entry[1] == depth:
                flag, score = entry[2], entry[3]
                if flag == 0:
                    return score
                if flag == 1:
                    alpha = max(alpha, score)
                else:
                    beta = min(beta, score)
                if alpha >= beta:
                    return score
        moves = pos.legal_moves()
        if not moves:
            return terminal_value(pos.terminal_score(pid), depth)
        moves = self.order(moves, depth)
        if hint is not None:
            for k, m in enumerate(moves):
                if m[0] == hint[0] and m[1] == hint[1]:
                    if k:
                        del moves[k]
                        moves.insert(0, m)
                    break
        maximizing = pos.stm == pid
        value = -1e18 if maximizing else 1e18
        alpha0, beta0 = alpha, beta
        best_i = best_to = -1
        standpat = None
        fut_ok = None
        for m in moves:
            i, to, promo, victim = m
            if depth == 1 and FUTILITY_MARGIN >= 0 and not victim and not promo:
                if standpat is None:
                    standpat = pos.evaluate(pid)
                bound = (
                    standpat + FUTILITY_MARGIN
                    if maximizing
                    else standpat - FUTILITY_MARGIN
                )
                if bound <= alpha if maximizing else bound >= beta:
                    if fut_ok is None:
                        fut_ok = pos.futility_safe()
                    if fut_ok:
                        nxt = (pos.stm + 1) % 3
                        king = pos.kings[nxt]
                        gives_check = False
                        if pos.may_give_check(i, to, nxt, king):
                            undo = pos.make(i, to, "")
                            gives_check = pos.attacked(king, nxt)
                            pos.unmake(undo)
                        if not gives_check:
                            if bound > value if maximizing else bound < value:
                                value = bound
                            continue
            for label in _LABELS if promo else ("",):
                undo = pos.make(i, to, label)
                try:
                    score = self.minimax(depth - 1, alpha, beta)
                finally:
                    pos.unmake(undo)
                if maximizing:
                    if score > value:
                        value = score
                        best_i, best_to = i, to
                    alpha = max(alpha, value)
                else:
                    if score < value:
                        value = score
                        best_i, best_to = i, to
                    beta = min(beta, value)
                if alpha >= beta:
                    break
            if alpha >= beta:
                # Only quiet moves feed the history table — captures and
                # promotions are already ordered by MVV-LVA/priority.
                if not victim and not promo:
                    self.history[(i, to)] = self.history.get((i, to), 0) + depth * depth
                    killers = self.killers[depth]
                    if killers[0] != (i, to):
                        killers[1] = killers[0]
                        killers[0] = (i, to)
                break
        # flag 0 exact, 1 lower bound (cut off high), 2 upper bound (failed low)
        if value <= alpha0:
            flag = 2
        elif value >= beta0:
            flag = 1
        else:
            flag = 0
        self.tt[slot] = (key, depth, flag, value, best_i, best_to)
        return value

    def search_root(self, depth: int, first=None):
        """Best (from, to, promotion, victim, label, score) at *depth*, or None
        without legal moves. *first* (a move tuple) is searched first."""
        pos = self.pos
        moves = self.order(pos.legal_moves())
        if first is not None and first in moves:
            moves.remove(first)
            moves.insert(0, first)
        best = None
        best_score = -1e18
        alpha, beta = -1e18, 1e18
        scores = []
        for m in moves:
            i, to, promo, victim = m
            move_best, move_label = -1e18, ""
            for label in _LABELS if promo else ("",):
                undo = pos.make(i, to, label)
                try:
                    score = self.minimax(depth - 1, alpha, beta)
                finally:
                    pos.unmake(undo)
                if score > move_best:
                    move_best, move_label = score, label
            scores.append((i, to, promo, victim, move_label, move_best))
            if move_best > best_score:
                best_score = move_best
                best = (i, to, promo, victim, move_label, best_score)
            alpha = max(alpha, best_score)
        # Kept only for a completed iteration (a Timeout skips this), so
        # safe_root() always sees one consistent depth.
        self.root_scores = scores
        self.last_depth = depth
        return best

    # ── post-search tactical safety ───────────────────────────────────────

    def _probe(self, move, depth: int, threshold: float):
        """Null-window test: can this root move reach *threshold*?

        Returns the promotion label that does, or None. Much cheaper than a
        full-window re-search: the veto only needs "safe score + material
        saved >= best", not the safe move's exact score.
        """
        i, to, promo, victim, label0, _ = move
        pos = self.pos
        labels = _LABELS if promo else (label0,)
        for label in labels:
            undo = pos.make(i, to, label)
            try:
                score = self.minimax(depth - 1, threshold - 1e-9, threshold + 1e-9)
            finally:
                pos.unmake(undo)
            if score >= threshold:
                return label
        return None

    def safe_root(self):
        """Best root move of the last completed iteration with the
        material-safety veto applied.

        If the best move loses material to the next opponent's immediate
        reply, prefer a safe move when its score plus the material saved is
        at least the best score: ``safe_score + material_saved >= best``.
        A genuine sacrifice, a forced win/loss, or a position where every
        move loses material keeps the original choice. A Timeout while
        probing (only possible when a deadline is set) also keeps it.
        """
        if not self.root_scores:
            return None
        ordered = sorted(self.root_scores, key=lambda m: m[5], reverse=True)
        best = ordered[0]
        if abs(best[5]) >= WIN_VALUE / 2:
            return best
        pos = self.pos
        best_loss = pos.see_loss_after(best[0], best[1], best[4])
        if best_loss >= 0:
            return best
        safe = [m for m in ordered if pos.see_loss_after(m[0], m[1], m[4]) >= 0]
        if not safe:
            return best
        # best_loss is negative; subtracting it adds the material saved.
        threshold = best[5] + best_loss
        try:
            for m in safe[:12]:
                label = self._probe(m, self.last_depth, threshold)
                if label is not None:
                    return (m[0], m[1], m[2], m[3], label, m[5])
        except Timeout:
            return best
        return best
