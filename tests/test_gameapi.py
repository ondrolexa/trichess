from engine import GameAPI, get_game
from engine.pieces import Pos


class TestCastling:
    def test_castling_offered_after_path_clears_via_replay(self):
        # Regression test: get_game() builds two Board() instances sharing
        # the same Player objects (GameAPI.__init__, then
        # replay_from_slog). Player.king() used to cache its King instance
        # and silently drop the `hex=` kwarg on the second placement, so an
        # unmoved king's `.hex` stayed pointed at the first, throwaway
        # board — permanently frozen at the pristine starting layout. Any
        # castling occupancy check (Piece.pos_candidates reads board state
        # via `self.hex.board`) then saw turn-0 occupancy instead of the
        # real, replayed position. Here pid 2's queen starts on Pos(7,-4),
        # directly between the king (Pos(7,-3), never moved) and its SLr
        # castling destination (Pos(7,-5)) toward the rook on Pos(7,-7);
        # once the queen has moved away for real, castling must be offered.
        slog = (
            "BNDLHBIBOCLEDNEMFDHDNFMFINIMCFFEOFMEANBMBHBIMEJGBOJKDFEF"
            "OGKCFNFMIBJBNHLHGNGLJBKCOBKDGOIKFEICOHNHEOGNHAHBNEJAAOAJ"
            "HBJBJALCENFLDEDKODNEFLNHICFE"
        )
        ga = get_game(2, slog)
        assert ga.on_move == 2

        king_gid = ga.pos2gid[Pos(7, -3)]
        assert ga.gid2hex[king_gid].piece.label == "K"
        castle_gid = ga.pos2gid[Pos(7, -5)]

        moves = ga.valid_moves(king_gid)
        assert any(m["tgid"] == castle_gid for m in moves)


class TestGidMapping:
    def test_169_gids_view_0(self):
        ga = GameAPI(view_pid=0)
        assert len(ga.gid2hex) == 169
        assert len(ga.pos2gid) == 169

    def test_169_gids_view_1(self):
        ga = GameAPI(view_pid=1)
        assert len(ga.gid2hex) == 169

    def test_169_gids_view_2(self):
        ga = GameAPI(view_pid=2)
        assert len(ga.gid2hex) == 169

    def test_mapping_is_bidirectional(self):
        ga = GameAPI(view_pid=0)
        for gid, hex in ga.gid2hex.items():
            assert ga.pos2gid[hex.pos] == gid

    def test_different_views_map_differently(self):
        ga0 = GameAPI(view_pid=0)
        ga1 = GameAPI(view_pid=1)
        # same gid should refer to different positions under different views
        h0 = ga0.gid2hex[0]
        h1 = ga1.gid2hex[0]
        assert h0.pos != h1.pos


class TestSlogEncoding:
    def test_slog2pos_roundtrip(self):
        ga = GameAPI(view_pid=0)
        from_pos = Pos(-7, 7)
        to_pos = Pos(-7, 6)
        slog = ga.move2slog(from_pos, to_pos, "")
        decoded_from, decoded_to, label = ga.slog2pos(*slog)
        assert decoded_from == from_pos
        assert decoded_to == to_pos
        assert label == ""

    def test_slog_promotion_encoding_q(self):
        ga = GameAPI(view_pid=0)
        # Promotion to Queen: encode with uppercase on q1
        slog = ga.move2slog(Pos(-7, 6), Pos(-7, 7), "Q")
        _, _, label = ga.slog2pos(*slog)
        assert label == "Q"

    def test_slog_promotion_encoding_r(self):
        ga = GameAPI(view_pid=0)
        slog = ga.move2slog(Pos(-7, 6), Pos(-7, 7), "R")
        _, _, label = ga.slog2pos(*slog)
        assert label == "R"

    def test_slog_promotion_encoding_b(self):
        ga = GameAPI(view_pid=0)
        slog = ga.move2slog(Pos(-7, 6), Pos(-7, 7), "B")
        _, _, label = ga.slog2pos(*slog)
        assert label == "B"

    def test_slog_promotion_encoding_n(self):
        ga = GameAPI(view_pid=0)
        slog = ga.move2slog(Pos(-7, 6), Pos(-7, 7), "N")
        _, _, label = ga.slog2pos(*slog)
        assert label == "N"


class TestGameFlow:
    def test_valid_moves_returns_list(self, game):
        targets = game.valid_moves(167)
        assert isinstance(targets, list)

    def test_valid_moves_empty_for_opponent_piece(self, game):
        # gid 0 should be opponent's territory (player 0's base)
        targets = game.valid_moves(0)
        assert len(targets) == 0

    def test_make_move_updates_slog(self, game):
        assert game.slog == ""
        game.make_move(167, 152)
        assert len(game.slog) == 4

    def test_make_move_increments_move_number(self, game):
        assert game.move_number == 0
        game.make_move(167, 152)
        assert game.move_number == 1

    def test_on_move_cycles(self, game):
        assert game.on_move == 0
        game.make_move(167, 152)
        assert game.on_move == 1

    def test_replay_from_empty_slog(self, game):
        # should not raise
        game.replay_from_slog("")
        assert game.move_number == 0

    def test_replay_full_game_roundtrip(self, game):
        moves = []
        for _ in range(3):
            # find any valid move for the player on move
            moved = False
            for gid in range(169):
                targets = game.valid_moves(gid)
                if targets:
                    game.make_move(gid, targets[0]["tgid"])
                    moves.append((gid, targets[0]["tgid"]))
                    moved = True
                    break
            assert moved, f"no valid moves found for player {game.on_move}"
        slog = game.slog
        assert len(slog) == 12

        ga2 = GameAPI(view_pid=0)
        ga2.replay_from_slog(slog)
        assert ga2.move_number == len(moves)
        assert ga2.on_move == len(moves) % 3

    def test_last_move_after_moves(self, game_with_one_move):
        lm = game_with_one_move.last_move
        assert lm is not None
        assert "gid" in lm
        assert "tgid" in lm

    def test_last_move_none_on_empty_slog(self, game):
        assert game.last_move is None

    def test_last_move_none_after_vote_only_slog(self):
        ga = GameAPI(view_pid=0)
        ga.replay_from_slog("RAAA")  # set-resign, all accept
        assert ga.last_move is None

    def test_last_move_none_after_full_vote_record(self):
        """When slog ends with a set-vote (R/S prefix), last_move returns None."""
        ga = GameAPI(view_pid=0)
        ga.make_move(152, 142)
        ga.replay_from_slog(ga.slog + "RAAD")
        assert ga.last_move is None

    def test_pre_last_move_none_on_empty_slog(self, game):
        assert game.pre_last_move is None

    def test_pre_last_move_none_after_one_move(self, game_with_one_move):
        assert game_with_one_move.pre_last_move is None

    def test_pre_last_move_after_two_moves(self, game):
        first_targets = game.valid_moves(152)
        game.make_move(152, first_targets[0]["tgid"])
        second_from = next(gid for gid in range(169) if game.valid_moves(gid))
        second_targets = game.valid_moves(second_from)
        game.make_move(second_from, second_targets[0]["tgid"])

        plm = game.pre_last_move
        assert plm is not None
        assert plm["gid"] == 152
        assert plm["tgid"] == first_targets[0]["tgid"]

    def test_pre_last_move_none_after_full_vote_record(self):
        """When slog ends with a set-vote (R/S prefix), pre_last_move returns None."""
        ga = GameAPI(view_pid=0)
        ga.make_move(152, 142)
        ga.replay_from_slog(ga.slog + "RAAD")
        assert ga.pre_last_move is None

    def test_undo_reverts_state(self, game):
        game.make_move(167, 152)
        assert game.move_number == 1
        game.undo()
        assert game.move_number == 0


class TestEliminated:
    def test_eliminated_starts_empty(self, game):
        el = game.eliminated()
        assert all(len(v) == 0 for v in el.values())

    def test_eliminated_value_starts_zero(self, game):
        ev = game.eliminated_value()
        assert all(v == 0 for v in ev.values())


class TestVoting:
    def test_voting_inactive_initially(self, game):
        assert not game.voting.active()
        assert not game.voting.finished()

    def test_resign_vote_progression(self, game):
        assert not game.voting.needed()
        game.voting.resign_vote(0, "A")
        assert game.voting.needed()
        game.voting.resign_vote(1, "A")
        game.voting.resign_vote(2, "D")
        assert game.voting.finished()
        assert len(game.voting.accepts) == 2

    def test_draw_vote_progression(self, game):
        game.voting.draw_vote(0, "A")
        game.voting.draw_vote(1, "A")
        game.voting.draw_vote(2, "A")
        assert game.voting.finished()
        assert len(game.voting.accepts) == 3

    def test_set_resign_voting(self, game):
        game.voting.set_resign_voting("A", "A", "D")
        assert game.voting.finished()
        assert len(game.voting.accepts) == 2

    def test_set_draw_voting(self, game):
        game.voting.set_draw_voting("A", "D", "A")
        assert game.voting.finished()
        assert len(game.voting.accepts) == 2

    def test_resignation_detected(self, game):
        game.voting.set_resign_voting("A", "A", "D")
        assert game.resignation()
        assert game.endgame() == "resignation"

    def test_draw_detected(self, game):
        game.voting.set_draw_voting("A", "A", "A")
        assert game.draw()
        assert game.endgame() == "draw"

    def test_draw_not_resign(self, game):
        game.voting.set_draw_voting("A", "A", "A")
        assert not game.resignation()

    def test_votes_returns_info_when_active(self, game):
        game.voting.resign_vote(0, "A")
        info = game.voting.votes()
        assert info is not None
        assert info["kind"] == "resign"
        assert info[0] == "A"

    def test_clean_resets_voting(self, game):
        game.voting.set_resign_voting("A", "A", "D")
        assert game.voting.finished()
        game.voting.clean()
        assert not game.voting.active()

    def test_on_move_during_voting(self, game):
        game.make_move(167, 152)
        assert game.on_move == 1
        game.voting.resign_vote(1, "A")
        assert game.on_move == 2
        game.voting.resign_vote(2, "D")
        assert game.on_move == 0


class TestSlogReplayVoting:
    def test_replay_individual_resign_votes(self):
        ga = GameAPI(view_pid=0)
        ga.replay_from_slog("rAXXX")
        assert ga.voting.active()
        assert not ga.voting.finished()

    def test_replay_complete_resign_votes(self):
        ga = GameAPI(view_pid=0)
        ga.replay_from_slog("rAADDD")
        assert ga.voting.finished()

    def test_replay_set_resign_voting(self):
        ga = GameAPI(view_pid=0)
        ga.replay_from_slog("RAAA")  # 3 acceptances in one chunk
        assert ga.voting.finished()
        assert len(ga.voting.accepts) == 3


class TestMovePossible:
    def test_move_possible_at_start(self, game):
        assert game.move_possible()

    def test_move_possible_empty_after_resignation(self, game):
        game.voting.set_resign_voting("A", "A", "D")
        assert not game.move_possible()

    def test_move_possible_empty_after_draw(self, game):
        game.voting.set_draw_voting("A", "A", "A")
        assert not game.move_possible()


class TestEndgame:
    def test_endgame_none_at_start(self, game):
        assert game.endgame() is None
        assert not game.repetition()

    def test_repetition_via_move_sequence(self):
        # Each player shuffles a knight out and back to the same square,
        # twice around — the starting position (already counted once at
        # construction) then recurs after each full 3-player round trip,
        # reaching 3 occurrences (threefold) after the second cycle.
        ga = GameAPI(view_pid=0)
        knights = {0: 166, 1: 17, 2: 26}
        current = dict(knights)
        for _ in range(2):
            for pid in range(3):
                frm = current[pid]
                to = next(m["tgid"] for m in ga.valid_moves(frm) if m["kind"] == "safe")
                ga.make_move(frm, to)
                current[pid] = to
            for pid in range(3):
                frm = current[pid]
                to = knights[pid]
                ga.make_move(frm, to)
                current[pid] = to

        # position_counts is only maintained while replaying a slog — the
        # real API always reconstructs state this way (get_game() ->
        # replay_from_slog()), so replay the accumulated slog to see it.
        replayed = GameAPI(view_pid=0)
        replayed.replay_from_slog(ga.slog)
        assert replayed.repetition()
        assert replayed.endgame() == "repetition"

    def test_repetition_counting_threshold(self, game):
        sig = game._position_signature()
        assert not game.repetition()
        game.position_counts[sig] = 2
        assert not game.repetition()
        game.position_counts[sig] = 3
        assert game.repetition()

    def test_stalemate_detected(self):
        # Clear the board down to a lone king plus two enemy queens
        # positioned to cover every one of the king's 5 on-board escape
        # squares (from a board corner) without attacking the king's own
        # square — a genuine stalemate: no legal move, not in check.
        #
        # Player.king() caches its King instance and ignores `hex=` on
        # repeat calls, so repositioning it must go through
        # king.hex/new_hex directly rather than board.place_piece(...).
        ga = GameAPI(view_pid=0)
        board = ga.board
        for hex in board:
            hex.piece = None

        king = ga.players[0].king_piece
        king.hex.piece = None
        king_hex = board[Pos(0, 7)]
        king_hex.piece = king
        king.hex = king_hex

        q1 = ga.players[1].queen()
        q1_hex = board[Pos(1, -7)]
        q1_hex.piece = q1
        q1.hex = q1_hex

        q2 = ga.players[2].queen()
        q2_hex = board[Pos(-1, 5)]
        q2_hex.piece = q2
        q2.hex = q2_hex

        assert not ga.move_possible()
        assert not ga.in_chess()[0]
        assert ga.endgame() == "stalemate"
