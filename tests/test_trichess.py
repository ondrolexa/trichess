import pytest

from trichess import Move, Pos


class Test_Board:
    def test_pos_gid(self, board):
        assert board[Pos(-4, 2)] is board.gid["32"]


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
