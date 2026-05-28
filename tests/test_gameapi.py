import pytest

from engine import GameAPI
from engine.pieces import Pos


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

    def test_draw_detected(self, game):
        game.voting.set_draw_voting("A", "A", "A")
        assert game.draw()

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
