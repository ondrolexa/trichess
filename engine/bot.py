from engine.eval import evaluate_for_pid
from engine.gameapi import GameAPI, get_game
from engine.opening import book_move
from engine.pieces import Pawn

# _minimax alternates strictly between "the root pid" (maximizing) and
# "whoever's actually on move" (minimizing) for each remaining depth unit —
# it does NOT treat "one ply" as "one opponent's turn" the way 2-player
# minimax implicitly does. In this 3-player game, 2 different opponents move
# between the root pid's own turns, so depth needs at least 3 to simulate a
# full round (root move -> opponent A's reply -> opponent B's reply) before
# scoring. Below that, the search is structurally blind to whatever the
# *second* opponent in the rotation can do — not weaker play, a real blind
# spot: at depth 1 or 2, a move that hangs a piece to that second opponent
# looks completely safe, since that opponent's turn is never simulated at all.
MIN_SOUND_DEPTH = 3


def _terminal_score(ga: GameAPI, pid: int) -> float:
    """Return game-over score for *pid*, matching server-side compute_outcome_scores.

    Draw: every player gets 2/3. Resignation: the non-accepting player gets
    2.0, the two who accepted get 0.0. Checkmate: score = (player's checker
    count) * 2 / total checkers. Stalemate / other: each player gets 2/3.
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


def _all_moves(ga: GameAPI):
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


def _capture_score(ga: GameAPI, from_gid: int, tgid: int) -> float:
    """MVV-LVA: prefer capturing the most valuable victim with the least
    valuable attacker (a Pawn taking a Queen sorts far ahead of a Queen
    taking a Pawn) — both piece values are read directly off the board, no
    move simulation needed."""
    attacker = ga.gid2hex[from_gid].piece
    victim = ga.gid2hex[tgid].piece
    return victim.value * 10 - attacker.value


def _order_moves(ga: GameAPI, moves, history: dict | None = None):
    """Order moves to maximize alpha-beta cutoffs: promotions, then captures
    (MVV-LVA), then quiet moves ranked by the history heuristic.

    Only ~5% of moves are captures in a typical developed position here (the
    other ~95% are quiet moves the board's high branching factor makes
    numerous) — MVV-LVA alone barely dents the search, since it only
    reorders that small slice. The history heuristic (which quiet
    (from,to) pairs have caused beta cutoffs elsewhere in *this* search,
    scored via _minimax's cutoff bookkeeping below) is what actually orders
    the bulk of the tree.
    """
    history = history or {}

    def key(item):
        from_gid, m = item
        if m["promotion"]:
            return (2, 0.0)
        if m["kind"] == "attack":
            return (1, _capture_score(ga, from_gid, m["tgid"]))
        return (0, history.get((from_gid, m["tgid"]), 0))

    return sorted(moves, key=key, reverse=True)


def _minimax(
    ga: GameAPI, depth: int, alpha: float, beta: float, pid: int, history: dict
) -> float:
    if not ga.move_possible():
        return _terminal_score(ga, pid)
    if depth == 0:
        return evaluate_for_pid(ga, pid)

    moves = _order_moves(ga, _all_moves(ga), history)

    def record_cutoff(from_gid, tgid, m):
        # Only quiet moves feed the history table — captures/promotions are
        # already ordered by MVV-LVA/priority and don't need this signal.
        if m["kind"] != "attack" and not m["promotion"]:
            key = (from_gid, tgid)
            history[key] = history.get(key, 0) + depth * depth

    if ga.on_move == pid:
        value = -1e18
        for from_gid, m in moves:
            if m["promotion"]:
                for label in ["Q", "R", "B", "N"]:
                    ga_copy = ga.copy()
                    ga_copy.make_move(from_gid, m["tgid"], label)
                    score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
                    if score > value:
                        value = score
                    alpha = max(alpha, value)
                    if alpha >= beta:
                        break
            else:
                ga_copy = ga.copy()
                ga_copy.make_move(from_gid, m["tgid"])
                score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
                if score > value:
                    value = score
                alpha = max(alpha, value)
            if alpha >= beta:
                record_cutoff(from_gid, m["tgid"], m)
                break
        return value
    else:
        value = 1e18
        for from_gid, m in moves:
            if m["promotion"]:
                for label in ["Q", "R", "B", "N"]:
                    ga_copy = ga.copy()
                    ga_copy.make_move(from_gid, m["tgid"], label)
                    score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
                    if score < value:
                        value = score
                    beta = min(beta, value)
                    if alpha >= beta:
                        break
            else:
                ga_copy = ga.copy()
                ga_copy.make_move(from_gid, m["tgid"])
                score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
                if score < value:
                    value = score
                beta = min(beta, value)
            if alpha >= beta:
                record_cutoff(from_gid, m["tgid"], m)
                break
        return value


def choose_move(ga: GameAPI, depth: int = MIN_SOUND_DEPTH) -> tuple[int, dict]:
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

    best_score = -1e18
    best_move = None
    pid = ga.on_move
    alpha = -1e18
    beta = 1e18

    history: dict = {}
    moves = _order_moves(ga, _all_moves(ga), history)

    for from_gid, m in moves:
        if m["promotion"]:
            best_promo = ""
            best_promo_score = -1e18
            for label in ["Q", "R", "B", "N"]:
                ga_copy = ga.copy()
                ga_copy.make_move(from_gid, m["tgid"], label)
                score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
                if score > best_promo_score:
                    best_promo_score = score
                    best_promo = label
            if best_promo_score > best_score:
                best_score = best_promo_score
                best_move = (from_gid, m, best_promo)
            alpha = max(alpha, best_score)
        else:
            ga_copy = ga.copy()
            ga_copy.make_move(from_gid, m["tgid"])
            score = _minimax(ga_copy, depth - 1, alpha, beta, pid, history)
            if score > best_score:
                best_score = score
                best_move = (from_gid, m, "")
            alpha = max(alpha, best_score)

    return best_move


def _vote_slog(ga: GameAPI, vote: bool) -> str:
    """Cast *vote* for whichever kind of vote is currently active."""
    if ga.voting.kind == "resign":
        return ga.resignation_vote(vote)
    return ga.draw_vote(vote)


def _resolve_vote(ga: GameAPI, pid: int, depth: int) -> float:
    """Value of a state reached right after someone just cast a vote.

    Note: evaluate_for_pid()'s raw score is not on the same scale as
    _terminal_score()'s 0.0-2.0 range (it's roughly material-scale, e.g.
    tens of points), so this "mixed outcome" branch tends to bias toward
    declining any vote unless the position is clearly bad. This mirrors an
    existing characteristic of _minimax()/choose_move(), which already
    mixes evaluate_for_pid()-scored and _terminal_score()-scored branches
    at the same tree level — not a new problem introduced here.
    """
    if ga.voting.finished():
        if ga.resignation() or ga.draw():
            return _terminal_score(ga, pid)
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
