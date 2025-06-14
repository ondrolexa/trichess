import pytest

from engine import Move, Pos


class Test_Player_Steps:
    def test_player0_fl(self, player0):
        assert player0.pos_from_move(Pos(0, 0), Move("FL")) == Pos(0, -1)

    def test_player0_fr(self, player0):
        assert player0.pos_from_move(Pos(0, 0), Move("FR")) == Pos(1, -1)

    def test_player1_fl(self, player1):
        assert player1.pos_from_move(Pos(0, 0), Move("FL")) == Pos(1, 0)

    def test_player1_fr(self, player1):
        assert player1.pos_from_move(Pos(0, 0), Move("FR")) == Pos(0, 1)

    def test_player2_fl(self, player2):
        assert player2.pos_from_move(Pos(0, 0), Move("FL")) == Pos(-1, 1)

    def test_player2_fr(self, player2):
        assert player2.pos_from_move(Pos(0, 0), Move("FR")) == Pos(-1, 0)


class Test_Board:
    def test_move_piece(self, board):
        p1, p2 = Pos(-5, 6), Pos(-5, 5)
        board.move_piece(p1, p2, "")
        assert not board[p1].has_piece
        assert board[p2].has_piece


class Test_GameAPI:
    def test_game_play(self, api):
        p1, p2 = Pos(-5, 6), Pos(-5, 5)
        api.make_move(api.pos2gid[p1], api.pos2gid[p2])
        p1, p2 = Pos(-1, -5), Pos(-1, -4)
        api.make_move(api.pos2gid[p1], api.pos2gid[p2])
        assert api.move_number == 2
