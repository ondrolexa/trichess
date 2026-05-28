from engine.pieces import Bishop, King, Knight, Move, Pawn, Piece, Pos, Queen, Rook


class TestPos:
    def test_creation(self):
        p = Pos(3, -5)
        assert p.q == 3
        assert p.r == -5

    def test_equality(self):
        assert Pos(1, 2) == Pos(1, 2)
        assert Pos(1, 2) != Pos(2, 1)

    def test_hash(self):
        assert hash(Pos(1, 2)) == hash(Pos(1, 2))
        assert hash(Pos(1, 2)) != hash(Pos(2, 1))

    def test_code(self):
        assert Pos(0, 0).code == "HH"
        assert Pos(-7, 7).code == "AO"
        assert Pos(7, -7).code == "OA"

    def test_code_roundtrip(self):
        for q in range(-7, 8):
            for r in range(-7, 8):
                if -7 <= -q - r <= 7:
                    p = Pos(q, r)
                    decoded_q = ord(p.code[0]) - 72
                    decoded_r = ord(p.code[1]) - 72
                    assert (decoded_q, decoded_r) == (q, r)

    def test_from_deltas(self):
        p = Pos(3, -5)
        result = p.from_deltas([1 + 0j, 0 - 1j])
        assert result == Pos(4, -6)
        assert result.kind == "s"

    def test_from_deltas_custom_kind(self):
        p = Pos(0, 0)
        result = p.from_deltas([1j], kind="a")
        assert result.kind == "a"


class TestMove:
    def test_single_step(self):
        m = Move("FL")
        assert m.steps == ("FL",)
        assert m.kind == "s"

    def test_multi_step(self):
        m = Move("FL", "FR", kind="n")
        assert m.steps == ("FL", "FR")
        assert m.kind == "n"


class TestPieceTypes:
    def test_pawn(self, game):
        p = Pawn(game.players[0])
        assert p.label == "P"
        assert p.value == 1
        assert p.special_attack is True
        assert p.used is False

    def test_knight(self, game):
        p = Knight(game.players[0])
        assert p.label == "N"
        assert p.value == 3
        assert p.special_attack is False

    def test_bishop(self, game):
        p = Bishop(game.players[0])
        assert p.label == "B"
        assert p.value == 3

    def test_rook(self, game):
        p = Rook(game.players[0])
        assert p.label == "R"
        assert p.value == 5

    def test_queen(self, game):
        p = Queen(game.players[0])
        assert p.label == "Q"
        assert p.value == 9

    def test_king(self, game):
        p = King(game.players[0])
        assert p.label == "K"
        assert p.value == 0
        assert p.used is False

    def test_piece_repr_placed(self, game):
        p = Pawn(game.players[0], hex=game.board[Pos(0, 6)])
        assert "P" in repr(p)
        assert "0" in repr(p)

    def test_piece_repr_not_placed(self, game):
        p = Pawn(game.players[0])
        assert "not placed" in repr(p)

    def test_piece_pos_property(self, game):
        hex = game.board[Pos(0, 6)]
        assert hex.has_piece
        assert hex.piece.pos == Pos(0, 6)

    def test_pawn_double_move_added_only_when_unused(self, game):
        p = Pawn(game.players[0])
        assert not p.used
        moves = p._moves
        kinds = [m.kind for m in moves]
        assert "d" in kinds

        p.used = True
        moves = p._moves
        kinds = [m.kind for m in moves]
        assert "d" not in kinds
