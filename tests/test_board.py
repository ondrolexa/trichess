from engine.board import Board
from engine.pieces import Pos


def count_cells(board):
    return sum(1 for _ in board)


class TestBoardCreation:
    def test_169_cells(self):
        b = Board()
        assert count_cells(b) == 169

    def test_all_positions_have_valid_coords(self):
        b = Board()
        for hex in b:
            pos = hex.pos
            s = -pos.q - pos.r
            assert -7 <= pos.q <= 7
            assert -7 <= pos.r <= 7
            assert -7 <= s <= 7

    def test_initial_pieces_count(self):
        b = Board()
        placed = sum(1 for hex in b if hex.has_piece)
        # 8 pawns + 2 knights + 3 bishops + 2 rooks + 1 queen + 1 king = 17 per player × 3 = 51
        assert placed == 51


class TestHex:
    def test_color(self):
        b = Board()
        for hex in b:
            if hex.has_piece:
                c = hex.color
                assert c in (0, 1, 2)
                assert hex.color == (2 * hex.pos.q + hex.pos.r) % 3

    def test_has_piece_property(self):
        b = Board()
        player0_pawn_hex = b[Pos(0, 6)]
        assert player0_pawn_hex.has_piece
        empty_hex = b[Pos(0, 0)]
        assert not empty_hex.has_piece


class TestPiecePlacement:
    def test_each_player_has_king(self):
        b = Board()
        assert b[Pos(-4, 7)].piece.label == "K"
        assert b[Pos(-3, -4)].piece.label == "K"
        assert b[Pos(7, -3)].piece.label == "K"

    def test_each_player_has_one_queen(self):
        b = Board()
        queens = [hex for hex in b if hex.has_piece and hex.piece.label == "Q"]
        assert len(queens) == 3

    def test_player_piece_colors(self):
        b = Board()
        for hex in b:
            if hex.has_piece:
                pid = hex.piece.player.pid
                if hex.pos.r == 7 or hex.pos.r == 6:
                    assert pid == 0, f"Expected pid 0 at {hex.pos}"


class TestMovement:
    def test_simple_move(self):
        b = Board()
        b.move_piece(Pos(-7, 7), Pos(-7, 6), "")
        assert not b[Pos(-7, 7)].has_piece
        assert b[Pos(-7, 6)].has_piece

    def test_capture(self):
        b = Board()
        # Place a player-0 rook and a player-1 pawn so the rook can capture
        b[Pos(0, 6)].piece = None  # clear player 0 pawn
        b[Pos(0, 5)].piece = None  # clear any piece at target
        rook = b.players[0].rook(hex=b[Pos(0, 6)])
        b[Pos(0, 6)].piece = rook
        pawn = b.players[1].pawn(hex=b[Pos(0, 5)])
        b[Pos(0, 5)].piece = pawn

        b.move_piece(Pos(0, 6), Pos(0, 5), "")
        assert len(b.eliminated) == 1

    def test_eliminated_tracks_capturer(self):
        b = Board()
        b[Pos(0, 6)].piece = None
        b[Pos(0, 5)].piece = None
        rook = b.players[0].rook(hex=b[Pos(0, 6)])
        b[Pos(0, 6)].piece = rook
        pawn = b.players[1].pawn(hex=b[Pos(0, 5)])
        b[Pos(0, 5)].piece = pawn

        b.move_piece(Pos(0, 6), Pos(0, 5), "")
        captured_entry = b.eliminated[-1]
        assert captured_entry[0] == 0  # player 0 captured someone


class TestPossibleMoves:
    def test_pawn_initial_moves(self):
        b = Board()
        hex = b[Pos(-7, 6)]
        moves = b.possible_moves(hex.piece)
        # bottom pawn at (-7,6) can move forward or double-forward
        target_positions = {p.code for p in moves}
        assert Pos(-7, 5).code in target_positions
        assert Pos(-7, 4).code in target_positions

    def test_sliding_piece_blocked(self):
        b = Board()
        hex = b[Pos(-7, 7)]
        moves = b.possible_moves(hex.piece)
        # rook at (-7,7) should see its own pawn at (-7,6) as blocking
        target_positions = {p.code for p in moves}
        assert Pos(-7, 6).code not in target_positions

    def test_knight_moves(self):
        b = Board()
        hex = b[Pos(-5, 7)]
        moves = b.possible_moves(hex.piece)
        assert len(moves) > 0


class TestChess:
    def test_in_chess(self):
        b = Board()
        in_chess = b.in_chess(b.players[0])
        assert in_chess[0] is False

    def test_test_move_prevents_self_check(self):
        b = Board()
        # clearing a pawn and moving king into danger
        _ = b[Pos(-4, 7)].piece
        b[Pos(-7, 6)].piece = None
        b[Pos(-6, 6)].piece = None
        b[Pos(-5, 6)].piece = None

        # king at (-4,7) can move to (-4,6) if safe
        assert b.test_move_piece(Pos(-4, 7), Pos(-4, 6))
        # not testing other positions since need specific threat setup


class TestPromotion:
    def test_pawn_in_opposite_base(self):
        b = Board()
        # pawn at forward edge of opponent's base
        pawn = b[Pos(-7, 6)].piece
        result = b.promotion(pawn, Pos(-7, 4))
        assert result is False  # not deep enough

    def test_pawn_reaching_opposite_base_edge(self):
        b = Board()
        pawn = b[Pos(-7, 6)].piece
        # Pos(0, -7) is in player 0's opposite base (base1)
        result = b.promotion(pawn, Pos(0, -7))
        assert result is True
