import time

from engine import GameAPI, choose_move, choose_vote, evaluate, get_game
from engine.bot import MIN_SOUND_DEPTH, _has_piece_under_attack, _terminal_score
from engine.eval import evaluate_for_pid

# A real reported position (8 plies in, still within the opening book's
# depth) where pid 2's Rook on OH is hanging to a Bishop. Regression case:
# the book used to fire regardless and suggest an unrelated pawn push,
# abandoning the rook — see _has_piece_under_attack.
HANGING_ROOK_SLOG = "HNIMBHBINFLHINKLHBHDOCMFGOIKDFEF"

# HANGING_ROOK_SLOG continued 3 more plies (the bot walked its Bishop to a
# square only pid 1 attacks — "OBIE" — then pid 0 moved, then pid 1 actually
# captured it — "HDIE"). At this new position, choose_move at depth 1 or 2
# repeats the exact same class of mistake with the Queen. See
# TestSearchDepth for why: depth<3 never simulates the *second* opponent's
# turn at all, so a move that's safe against the immediate next mover but
# hangs to the mover after that looks completely safe.
HANGING_QUEEN_SLOG = HANGING_ROOK_SLOG + "OBIEFOEMHDIE"

# A real, late-game position (67 moves in) where pid 2 has a decisive
# material lead and pid 1 has already cast an "Accept" vote on a draw,
# leaving pid 2 (the "bot" in this scenario) to respond next.
DRAW_VOTE_SLOG = (
    "FOEMHBIBNFMFFNFMCFFENHLHHNHLBGDIOGMEINIMFCEFNAMBBNBMDIFHOCNFGOHM"
    "BHBJNIMICOFNCGCHOBKDENMJFEHFNBMCANALDECGMEIGCNCLFHDIIGHFMJOFHAH"
    "FOHOFDNDLDIBMKDLBDOENBMAOMCLCBODKAHBGOAIGEOAOCGAKIGBGDKBIEFBGOD"
    "IGBIAKHFLBIGBGAOFEEDFEBGGBCLCKBJALGBIAHMGLLBLCNELCFMFLALAMIALDD"
    "LDKDFEFLDKEHLHKsXAX"
)
# Same position with the trailing draw-vote chunk stripped off — a clean
# board with no active vote, used as a base to construct other vote
# scenarios via the real slog round-trip (GameAPI.resignation_vote()/
# draw_vote() + get_game()), the same mechanism choose_vote() itself uses.
NO_VOTE_SLOG = DRAW_VOTE_SLOG[:-4]


class TestEvaluate:
    def test_evaluate_returns_float(self, game):
        assert isinstance(evaluate(game), float)

    def test_evaluate_for_pid_returns_float(self, game):
        for pid in range(3):
            assert isinstance(evaluate_for_pid(game, pid), float)

    def test_fresh_position_is_symmetric(self, game):
        # Nothing has happened yet, so every seat should score identically.
        scores = [evaluate_for_pid(game, pid) for pid in range(3)]
        assert scores[0] == scores[1] == scores[2]


class TestHasPieceUnderAttack:
    def test_fresh_board_is_false(self, game):
        # A long-range slider can legally "attack" an untouched edge pawn on
        # the starting position (nothing blocks the diagonal yet) — that's
        # routine, not a reason to abandon the opening book, so pawns are
        # deliberately excluded from this check.
        assert not _has_piece_under_attack(game)

    def test_true_when_a_non_pawn_piece_is_hanging(self):
        ga = get_game(0, HANGING_ROOK_SLOG)
        assert _has_piece_under_attack(ga)


class TestChooseMove:
    def _assert_legal(self, ga, move):
        assert move is not None
        from_gid, move_dict, promo_label = move
        hex = ga.gid2hex[from_gid]
        assert hex.has_piece
        assert hex.piece.player.pid == ga.on_move
        targets = {m["tgid"]: m for m in ga.valid_moves(from_gid)}
        assert move_dict["tgid"] in targets
        if move_dict["promotion"]:
            assert promo_label in ("Q", "R", "B", "N")
        else:
            assert promo_label == ""

    def test_returns_legal_move_depth_1(self, game):
        move = choose_move(game, depth=1)
        self._assert_legal(game, move)

    def test_opening_move_uses_the_book(self, game):
        # A fresh game's first move should come from the opening book (a
        # Pawn/Knight development move, near-instant since it skips the
        # minimax search entirely), not a search-driven Queen sortie.
        start = time.perf_counter()
        move = choose_move(game)
        elapsed = time.perf_counter() - start
        self._assert_legal(game, move)
        from_gid, _, _ = move
        assert game.gid2hex[from_gid].piece.label in ("P", "N")
        assert elapsed < 1, f"expected a fast book hit, took {elapsed:.2f}s"

    def test_returns_legal_move_after_a_move(self, game_with_one_move):
        move = choose_move(game_with_one_move, depth=1)
        self._assert_legal(game_with_one_move, move)

    def test_skips_the_book_when_a_piece_is_hanging(self):
        # Regression test: the opening book used to fire regardless of
        # tactics and suggest NB->MB (an unrelated pawn push) here, leaving
        # pid 2's Rook on OH hanging to a Bishop. depth=1 is enough to prove
        # the book was bypassed (its top candidate is no longer returned)
        # without paying for a deep search in the test suite — separately
        # verified during development that depth=3 actually finds a move
        # that defends the Rook (87 legal replies at the root here makes a
        # full 3-ply search too slow, ~70s, for a unit test).
        ga = get_game(0, HANGING_ROOK_SLOG)
        assert ga.on_move == 2
        assert _has_piece_under_attack(ga)

        book_from_pos, book_to_pos, _ = ga.slog2pos("N", "B", "M", "B")
        book_choice = (ga.pos2gid[book_from_pos], ga.pos2gid[book_to_pos])

        move = choose_move(ga, depth=1)
        self._assert_legal(ga, move)
        from_gid, m, _ = move
        assert (from_gid, m["tgid"]) != book_choice

    def test_depth_2_completes_quickly(self, game):
        start = time.perf_counter()
        move = choose_move(game, depth=2)
        elapsed = time.perf_counter() - start
        self._assert_legal(game, move)
        assert elapsed < 10, f"choose_move(depth=2) took {elapsed:.2f}s"

    def test_does_not_mutate_input_game(self, game):
        slog_before = game.slog
        choose_move(game, depth=1)
        assert game.slog == slog_before

    def test_returns_none_while_a_vote_is_pending(self, game):
        game.voting.resign_vote(0, "A")
        assert game.voting.needed()
        assert choose_move(game) is None


class TestSearchDepth:
    """_minimax alternates strictly between "root pid" and "whoever's
    actually on move" per remaining depth unit — it doesn't treat one ply as
    one opponent's turn the way 2-player minimax implicitly does. In this
    3-player game 2 different opponents move between the root pid's turns,
    so depth < MIN_SOUND_DEPTH never simulates the *second* opponent at all,
    making the search structurally blind to whatever that opponent can do —
    not just weaker play, a real blind spot. Confirmed against 2 real
    reported blunders below.
    """

    def test_min_sound_depth_is_three(self):
        # One root move + one reply from each of the 2 other players before
        # anything gets scored — the minimum needed to simulate a full round.
        assert MIN_SOUND_DEPTH == 3

    def test_default_depth_is_sound(self):
        import inspect

        assert (
            inspect.signature(choose_move).parameters["depth"].default
            == MIN_SOUND_DEPTH
        )

    def test_shallow_depth_hangs_a_piece_to_the_second_opponent(self):
        # Depth 1 and depth 2 each blunder a different piece here (Queen,
        # then Bishop) — both hang to pid 1, but pid 0 is who actually moves
        # next, so neither depth ever simulates the piece that's really
        # threatening.
        expected = {1: ("OD", "GH"), 2: ("OB", "IE")}
        for depth, (from_code, to_code) in expected.items():
            ga = get_game(0, HANGING_ROOK_SLOG)
            from_gid, m, _ = choose_move(ga, depth=depth)
            assert ga.gid2hex[from_gid].pos.code == from_code
            assert ga.gid2hex[m["tgid"]].pos.code == to_code

    def test_shallow_depth_hangs_a_queen_to_the_second_opponent(self):
        ga = get_game(0, HANGING_QUEEN_SLOG)
        for depth in (1, 2):
            from_gid, m, _ = choose_move(ga, depth=depth)
            assert ga.gid2hex[from_gid].pos.code == "OD"
            assert ga.gid2hex[m["tgid"]].pos.code == "GH"


class TestTerminalScore:
    def test_finished_resignation_score(self):
        base = get_game(0, NO_VOTE_SLOG)
        # pid 1 accepts, pid 2 declines, pid 0 accepts -> 2 accepts (1, 0),
        # so pid 2 (the sole non-accepting player) wins outright.
        s1 = base.resignation_vote(True)
        s2 = get_game(0, s1).resignation_vote(False)
        s3 = get_game(0, s2).resignation_vote(True)
        ga = get_game(0, s3)
        assert ga.resignation()
        assert _terminal_score(ga, 2) == 2.0
        assert _terminal_score(ga, 0) == 0.0
        assert _terminal_score(ga, 1) == 0.0

    def test_finished_draw_score(self):
        base = get_game(0, NO_VOTE_SLOG)
        s1 = base.draw_vote(True)
        s2 = get_game(0, s1).draw_vote(True)
        s3 = get_game(0, s2).draw_vote(True)
        ga = get_game(0, s3)
        assert ga.draw()
        for pid in range(3):
            assert _terminal_score(ga, pid) == 2.0 / 3


class TestChooseVote:
    def test_returns_none_when_no_vote_is_active(self, game):
        assert not game.voting.needed()
        assert choose_vote(game) is None

    def test_declines_a_bad_draw_offer(self):
        # pid 2 (bot) is decisively ahead materially at this point in the
        # game; pid 1 already accepted a draw. Accepting would lock in a
        # guaranteed 2/3 for everyone, worse than pid 2's actual prospects
        # if the game continues, so the bot should decline.
        ga = get_game(0, DRAW_VOTE_SLOG)
        assert ga.on_move == 2
        assert ga.voting.kind == "draw"
        assert ga.voting.needed()
        assert choose_vote(ga) is False

    def test_declines_resignation_when_continuing_is_better(self):
        # Build up to a state where pid 0 must cast the deciding 3rd vote
        # on a resignation, via the same real slog round-trip choose_vote()
        # itself uses. pid 0 is comfortably ahead in this position, so
        # accepting (which would guarantee it 0.0, handing pid 2 the win)
        # should lose to declining (leaves the vote short of the 2-accept
        # threshold, so play resumes from a position pid 0 is winning).
        base = get_game(0, NO_VOTE_SLOG)
        s1 = base.resignation_vote(True)  # pid 1 accepts
        ga1 = get_game(0, s1)
        s2 = ga1.resignation_vote(False)  # pid 2 declines
        ga2 = get_game(0, s2)
        assert ga2.on_move == 0
        assert ga2.voting.needed()
        assert evaluate_for_pid(ga2, 0) > 0
        assert choose_vote(ga2) is False

    def test_does_not_mutate_input_game(self):
        ga = get_game(0, DRAW_VOTE_SLOG)
        slog_before = ga.slog
        choose_vote(ga)
        assert ga.slog == slog_before

    def test_completes_quickly(self):
        ga = get_game(0, DRAW_VOTE_SLOG)
        start = time.perf_counter()
        choose_vote(ga)
        elapsed = time.perf_counter() - start
        assert elapsed < 5, f"choose_vote() took {elapsed:.2f}s"
