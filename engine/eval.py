from engine.board import Board
from engine.gameapi import GameAPI
from engine.pieces import Pawn, Pos

# Piece-square bonus: distance from center (closer = higher bonus).
_CENTER_BONUS = {0: 3, 1: 2, 2: 1, 3: 1}

# Promotion proximity bonus for pawns: distance to own promotion zone.
_PROMO_BONUS = [0, 0, 0, 1, 2, 3, 5, 8]

MATERIAL_WEIGHT = 1.0
MOBILITY_WEIGHT = 0.1
KING_SAFETY_WEIGHT = 0.3
ACTIVITY_WEIGHT = 0.05


_CENTER = Pos(0, 0)


def axial_distance(p1: Pos, p2: Pos) -> int:
    """Hex distance: the number of single steps between two cells."""
    dq = p1._q - p2._q
    dr = p1._r - p2._r
    ds = (-p1._q - p1._r) - (-p2._q - p2._r)
    return max(abs(dq), abs(dr), abs(ds))


def _promotion_distance(board: Board, pid: int, pos: Pos) -> int:
    min_d = 99
    for p in board.opposite[pid]:
        d = axial_distance(pos, p)
        if d < min_d:
            min_d = d
    return min_d


def evaluate_for_pid(ga: GameAPI, pid: int) -> float:
    """Single-pass evaluation: material + mobility + king safety + activity."""
    board = ga.board
    players = ga.players
    king_pos = players[pid].king_piece.hex.pos

    my_mat = 0.0
    opp_mat = 0.0
    my_mob = 0
    activity = 0.0
    defenders = 0

    for hex in board:
        if not hex.has_piece:
            continue
        piece = hex.piece
        pos = hex.pos
        if piece.player.pid == pid:
            my_mat += piece.value
            # castling=False: mobility only needs a candidate-square count,
            # not actual castling legality — the default (True) makes the
            # King's candidate generation run 2 full board-wide
            # pos_in_chess() scans (check the king isn't in check, then that
            # it doesn't pass through check) on every single call, which
            # dominated profiled search time (~63% of a depth-3 search) for
            # no benefit to the evaluation.
            my_mob += len(board.possible_moves(piece, castling=False))
            # center bonus
            cb = _CENTER_BONUS.get(axial_distance(pos, _CENTER))
            if cb is not None:
                activity += cb
            # promotion proximity for pawns
            if isinstance(piece, Pawn):
                promo_dist = _promotion_distance(board, pid, pos)
                if promo_dist < len(_PROMO_BONUS):
                    activity += _PROMO_BONUS[promo_dist]
            # king defenders (within 2 squares)
            if axial_distance(pos, king_pos) <= 2:
                defenders += 1
        else:
            opp_mat += piece.value

    material = my_mat - opp_mat / 2.0
    king_safety = (
        defenders - (1 if board._is_attacked(king_pos, players[pid]) else 0)
    ) * 2.0

    return (
        material * MATERIAL_WEIGHT
        + my_mob * MOBILITY_WEIGHT
        + king_safety * KING_SAFETY_WEIGHT
        + activity * ACTIVITY_WEIGHT
    )


def evaluate(ga: GameAPI) -> float:
    return evaluate_for_pid(ga, 0)
