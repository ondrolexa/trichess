from engine.pieces import Move, Pos
from engine.player import STEP, Player


class TestPlayer:
    def test_creation(self):
        p = Player(0)
        assert p.pid == 0
        assert p.name == "Player 0"

    def test_custom_name(self):
        p = Player(1, name="Alice")
        assert p.pid == 1
        assert p.name == "Alice"

    def test_step_direction_keys(self):
        for pid in range(3):
            for step_code in ["FL", "FR", "SL", "DF", "DL", "DR"]:
                dq, dr = STEP[pid][step_code]
                rdq, rdr = STEP[pid][step_code + "r"]
                assert (dq, dr) == (
                    -rdq,
                    -rdr,
                ), f"{pid} {step_code}: ({dq},{dr}) != -({rdq},{rdr})"

    def test_pos_from_move(self):
        p = Player(0)
        pos = p.pos_from_move(Pos(0, 0), Move("FL"))
        assert pos.r == -1

    def test_king_singleton(self):
        p = Player(0)
        k1 = p.king()
        k2 = p.king()
        assert k1 is k2

    def test_king_piece_property(self):
        p = Player(0)
        k = p.king()
        assert p.king_piece is k

    def test_piece_factories(self):
        p = Player(0)
        assert p.pawn().label == "P"
        assert p.knight().label == "N"
        assert p.bishop().label == "B"
        assert p.rook().label == "R"
        assert p.queen().label == "Q"
        assert p.king().label == "K"

    def test_promotion(self):
        p = Player(0)
        assert p.promotion("Q").label == "Q"
        assert p.promotion("R").label == "R"
        assert p.promotion("B").label == "B"
        assert p.promotion("N").label == "N"
