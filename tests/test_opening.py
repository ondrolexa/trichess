from engine.opening import book_move, build_book, load_book, save_book


class TestBuildBook:
    def test_counts_first_ply_across_games(self):
        slogs = [
            "DNEMFOEM",  # DNEM, FOEM
            "DNEMFOEM",  # DNEM, FOEM
            "DNEMBHBI",  # DNEM, BHBI
            "FOEMBHBI",  # FOEM, BHBI
        ]
        book = build_book(slogs)
        assert book[0] == {"DNEM": 3, "FOEM": 1}
        assert book[1] == {"FOEM": 2, "BHBI": 2}

    def test_drops_vote_chunks(self):
        book = build_book(["DNEMrAXX"])
        assert book[0] == {"DNEM": 1}
        assert 1 not in book

    def test_empty_slog_contributes_nothing(self):
        assert build_book([""]) == {}

    def test_caps_at_max_book_plies(self):
        long_slog = "DNEM" * 20
        book = build_book([long_slog])
        from engine.opening import MAX_BOOK_PLIES

        assert set(book.keys()) == set(range(MAX_BOOK_PLIES))


class TestSaveLoadBook:
    def test_round_trip(self, tmp_path):
        book = {0: {"DNEM": 3, "FOEM": 1}, 1: {"BHBI": 2}}
        path = tmp_path / "book.json"
        save_book(book, path)
        loaded = load_book(path)
        assert loaded == book

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_book(tmp_path / "does_not_exist.json") == {}


class TestBookMove:
    def _assert_legal(self, ga, move):
        assert move is not None
        from_gid, move_dict, promo_label = move
        hex = ga.gid2hex[from_gid]
        assert hex.has_piece
        assert hex.piece.player.pid == ga.on_move
        targets = {m["tgid"]: m for m in ga.valid_moves(from_gid)}
        assert move_dict["tgid"] in targets
        assert promo_label == ""

    def test_fresh_game_returns_pawn_or_knight_move(self, game):
        move = book_move(game)
        self._assert_legal(game, move)
        from_gid, _, _ = move
        assert game.gid2hex[from_gid].piece.label in ("P", "N")

    def test_none_while_a_vote_is_pending(self, game):
        game.voting.resign_vote(0, "A")
        assert book_move(game) is None

    def test_none_with_an_empty_book(self, game, monkeypatch):
        monkeypatch.setattr("engine.opening._BOOK", {})
        assert book_move(game) is None

    def test_none_when_no_candidate_meets_min_support(self, game, monkeypatch):
        monkeypatch.setattr("engine.opening._BOOK", {0: {"DNEM": 1}})
        assert book_move(game) is None

    def test_skips_illegal_top_candidate(self, game, monkeypatch):
        # "AAAA" decodes to an off-board/nonsensical position and should
        # simply be skipped in favor of the next, still-well-supported
        # candidate rather than raising or returning a bad move.
        monkeypatch.setattr("engine.opening._BOOK", {0: {"AAAA": 10, "DNEM": 5}})
        move = book_move(game)
        self._assert_legal(game, move)
        from_gid, _, _ = move
        from_pos = game.gid2hex[from_gid].pos
        assert from_pos.code == "DN"

    def test_beyond_book_depth_returns_none(self, game):
        # book_move() only needs the slog's ply *count* to decide there's no
        # entry this deep — it never touches board state when the lookup
        # comes back empty, so overwriting .slog directly (without a real,
        # legal replay) is enough to exercise this path in isolation.
        game.slog = "AAAA" * 10  # 10 plies, past MAX_BOOK_PLIES (9)
        assert book_move(game) is None
