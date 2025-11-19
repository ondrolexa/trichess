from engine import GameAPI, Move, Pos


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
    def test_game_init(self, api):
        api.make_move(154, 144)
        api.make_move(18, 29)
        assert api.move_number == 2

    def test_slog(self, slog1):
        api = GameAPI(0)
        api.replay_from_slog(slog1)
        assert api.move_number == 74
        assert api.on_move == 2
        assert not api.draw()
        assert not api.resignation()
        assert api.move_possible()

    def test_declined_voting_parse(self, slog2):
        api = GameAPI(0)
        api.replay_from_slog(slog2)
        assert api.move_number == 28
        assert api.voting.votes() == {
            "kind": "draw",
            "n_voted": 3,
            0: "D",
            1: "A",
            2: "A",
        }
        assert api.on_move == 1
        assert api.slog[-4:] == "SDAA"

    def test_voting_vote(self, slog3):
        api = GameAPI(0)
        api.replay_from_slog(slog3)
        onmove = api.on_move
        api.replay_from_slog(api.draw_vote(True))
        api.replay_from_slog(api.draw_vote(True))
        api.replay_from_slog(api.draw_vote(False))
        assert api.on_move == onmove
        assert api.voting.votes() == {
            "kind": "draw",
            "n_voted": 3,
            0: "A",
            1: "D",
            2: "A",
        }

    def test_chess(self, slog4):
        api = GameAPI(0)
        api.replay_from_slog(slog4)
        inchess, kingpos, pieces = api.in_chess()
        assert inchess
        assert pieces[2][0]["piece"] == "Q"
