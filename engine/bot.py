import time

from engine.eval import evaluate_for_pid
from engine.gameapi import GameAPI, get_game
from engine.opening import book_move
from engine.pieces import Pawn, Pos
from engine.search import CELLS, WIN_VALUE, Position, Search, Timeout, terminal_value

# The search (engine.search.Search) alternates strictly between "the root
# pid" (maximizing) and "whoever's actually on move" (minimizing) for each
# remaining depth unit —
# it does NOT treat "one ply" as "one opponent's turn" the way 2-player
# minimax implicitly does. In this 3-player game, 2 different opponents move
# between the root pid's own turns, so depth needs at least 3 to simulate a
# full round (root move -> opponent A's reply -> opponent B's reply) before
# scoring. Below that, the search is structurally blind to whatever the
# *second* opponent in the rotation can do — not weaker play, a real blind
# spot: at depth 1 or 2, a move that hangs a piece to that second opponent
# looks completely safe, since that opponent's turn is never simulated at all.
MIN_SOUND_DEPTH = 3

# Iterative deepening never goes past this, whatever the time budget.
MAX_DEPTH = 12


def _terminal_score(ga: GameAPI, pid: int) -> float:
    """Return game-over score for *pid*, matching server-side compute_outcome_scores.

    Draw: every player gets 2/3. Resignation: the non-accepting player gets
    2.0, the two who accepted get 0.0. Checkmate: score = (player's checker
    count) * 2 / total checkers. Stalemate / other: each player gets 2/3.

    Used for vote decisions; the move search has its own port of the
    checkmate/stalemate part (search.Position.terminal_score). Deliberately
    does not check GameAPI.repetition()/endgame(): votes are resolved a few
    plies at most, nowhere near enough to observe a real threefold
    repetition. Stalemate is already covered by the final `return 2.0 / 3`.
    """
    if ga.draw():
        return 2.0 / 3
    if ga.resignation():
        resigned = ga.voting.results(kind="resign")
        winner = ({0, 1, 2} - set(resigned)).pop()
        return 2.0 if pid == winner else 0.0
    in_chess, _, who = ga.in_chess()
    if in_chess:
        tot = [len(p) for p in who.values()]
        total = sum(tot)
        if total > 0:
            return tot[pid] * 2.0 / total
        return 0.0
    return 2.0 / 3


def _terminal_value(ga: GameAPI, pid: int, depth_left: int) -> float:
    """Search-scale value of a finished node for *pid* (see search.WIN_VALUE)."""
    return terminal_value(_terminal_score(ga, pid), depth_left)


def _all_moves(ga: GameAPI):
    """Legal moves of the player on move as (from_gid, valid_moves entry).

    The search has its own move generator; this object-engine version is
    the reference tests/test_search.py checks it against."""
    moves = []
    pid = ga.on_move
    for hex in ga.board:
        if not hex.has_piece or hex.piece.player.pid != pid:
            continue
        gid = ga.pos2gid[hex.pos]
        for m in ga.valid_moves(gid):
            moves.append((gid, m))
    return moves


def _has_piece_under_attack(ga: GameAPI) -> bool:
    """True if any of the on-move player's own pieces is currently attacked.

    The opening book (see below) is a context-blind historical-frequency
    lookup — it only checks that its top candidate is legal, never whether
    it's tactically sound. That's fine in a quiet opening, but once a piece
    is hanging the book has to be skipped in favor of real search, or the
    bot will happily push a book pawn move while leaving a rook to be
    captured.

    Deliberately uses pos_in_chess() (full piece-iteration), not the faster
    _is_attacked() ray-scanner — _is_attacked is only proven correct for a
    player's own king square (see TestAttackDetectionConsistency in
    tests/test_board.py); using it here for arbitrary own pieces produced
    false positives on a fresh board (flagging untouched pawns as attacked).

    Pawns are excluded: a long-range slider "attacking" an undeveloped edge
    pawn is routine even on the starting position (nothing blocks the
    diagonal yet) and isn't worth abandoning the book over. Restricting this
    to Knight/Bishop/Rook/Queen/King catches real hanging-piece situations
    (the reported bug: an undefended Rook) without defeating the book on
    essentially every opening move.
    """
    player = ga.board.players[ga.on_move]
    for hex in ga.board:
        if (
            hex.has_piece
            and hex.piece.player.pid == ga.on_move
            and not isinstance(hex.piece, Pawn)
        ):
            if ga.board.pos_in_chess(player, hex.pos)[0]:
                return True
    return False


def choose_move(
    ga: GameAPI,
    depth: int = MIN_SOUND_DEPTH,
    time_limit: float | None = None,
    max_depth: int = MAX_DEPTH,
) -> tuple[int, dict, str] | None:
    """Pick a move for the player on move: ``(from_gid, move, promotion)``.

    *move* has the shape of GameAPI.valid_moves() entries; gids are in
    *ga*'s view. Without *time_limit* this is a single *depth* search.
    With it, iterative deepening: depths up to *depth* always complete (so
    MIN_SOUND_DEPTH's soundness holds however slow the machine), deeper
    ones up to *max_depth* only while *time_limit* seconds last, and an
    iteration cut off by the deadline is thrown away.
    """
    if ga.voting.needed():
        # Piece moves are no-ops while a vote is pending (see
        # GameAPI.make_move), so searching them here would just churn over
        # an unchanging position. Callers should resolve the vote via
        # choose_vote() first.
        return None

    if not _has_piece_under_attack(ga):
        opening = book_move(ga)
        if opening is not None:
            return opening

    search = Search(Position.from_game(ga))
    if time_limit is None:
        best = search.search_root(depth)
    else:
        best = _iterative_deepening(search, depth, time_limit, max_depth)
    if best is None:
        return None
    i, to, promo, victim, label, _ = best
    tgid = ga.pos2gid[Pos(*CELLS[to])]
    move = {"tgid": tgid, "kind": "attack" if victim else "safe", "promotion": promo}
    return ga.pos2gid[Pos(*CELLS[i])], move, label


def _iterative_deepening(search: Search, depth: int, time_limit: float, max_depth):
    """Search depth 1, 2, ... reusing the history table and putting the
    previous iteration's best move first, which is what makes the deeper
    iterations affordable."""
    start = time.monotonic()
    deadline = start + time_limit
    best = None
    durations = []
    for d in range(1, max(depth, max_depth) + 1):
        search.deadline = deadline if d > depth else None
        t0 = time.monotonic()
        try:
            result = search.search_root(d, first=best[:4] if best else None)
        except Timeout:
            break
        durations.append(time.monotonic() - t0)
        best = result
        if best is None or abs(best[5]) >= WIN_VALUE / 2:
            break  # no legal move, or a forced result: deeper can't change it
        if d >= depth:
            # Don't start an iteration that can't finish: an aborted one is
            # discarded, so its CPU time would be pure loss for the worker.
            growth = max(durations[-1] / durations[-2], 2.0) if d > 1 else 2.0
            if time.monotonic() + durations[-1] * growth > deadline:
                break
    return best


def _vote_slog(ga: GameAPI, vote: bool) -> str:
    """Cast *vote* for whichever kind of vote is currently active."""
    if ga.voting.kind == "resign":
        return ga.resignation_vote(vote)
    return ga.draw_vote(vote)


def _resolve_vote(ga: GameAPI, pid: int, depth: int) -> float:
    """Value of a state reached right after someone just cast a vote.

    Uses _terminal_value() for an ended game, so a vote outcome compares on
    the same scale as evaluate_for_pid() for play that resumes: a draw (0)
    is accepted only when the position evaluates as worse than that.
    """
    if ga.voting.finished():
        if ga.resignation() or ga.draw():
            return _terminal_value(ga, pid, 0)
        # All 3 voted but the vote didn't end the game — play resumes.
        return evaluate_for_pid(ga, pid)

    voter = ga.on_move
    values = []
    for vote in (True, False):
        ga_next = get_game(ga.view_pid, _vote_slog(ga, vote))
        values.append(_resolve_vote(ga_next, pid, depth))
    return max(values) if voter == pid else min(values)


def choose_vote(ga: GameAPI, depth: int = 2) -> bool | None:
    """Decide how the player on move should respond to an active vote.

    Returns True to accept, False to decline, or None when no vote is
    currently awaiting a response from anyone.
    """
    if not ga.voting.needed():
        return None

    pid = ga.on_move
    best_vote = None
    best_score = -1e18
    for vote in (True, False):
        ga_next = get_game(ga.view_pid, _vote_slog(ga, vote))
        score = _resolve_vote(ga_next, pid, depth)
        if score > best_score:
            best_score = score
            best_vote = vote
    return best_vote
