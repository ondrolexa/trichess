"""engine.search must agree with the object engine it was ported from.

Positions come from seeded random games (biased towards captures, castling
and promotion so the rare rules get exercised). In view 0 a gid *is* the
search's cell index, so move lists compare element by element, order
included — order decides ties in the bot's move ordering.
"""

import random

import pytest

from engine import bot
from engine.eval import evaluate_for_pid
from engine.gameapi import get_game
from engine.pieces import Pos
from engine.search import CASTLING_ROOK, CELLS, INDEX, N, Position, Search


def _old_moves(ga):
    return [
        (g, m["tgid"], m["promotion"], m["kind"] == "attack")
        for g, m in bot._all_moves(ga)
    ]


def _new_moves(pos):
    return [(i, to, promo, bool(victim)) for i, to, promo, victim in pos.legal_moves()]


def _random_games(seeds=(11, 12, 13, 14, 15), plies=220):
    """(game, legal moves, move played) along seeded random games, in view 0."""
    out = []
    for seed in seeds:
        rng = random.Random(seed)
        ga = get_game(0, "")
        for _ in range(plies):
            moves = bot._all_moves(ga)
            if not moves:
                out.append((get_game(0, ga.slog), moves, None))
                break
            special = [
                (g, m)
                for g, m in moves
                if m["promotion"] or (g, m["tgid"]) in CASTLING_ROOK
            ]
            captures = [(g, m) for g, m in moves if m["kind"] == "attack"]
            if special and rng.random() < 0.7:
                g, m = rng.choice(special)
            elif captures and rng.random() < 0.5:
                g, m = rng.choice(captures)
            else:
                g, m = rng.choice(moves)
            label = rng.choice("QRBN") if m["promotion"] else ""
            out.append((get_game(0, ga.slog), moves, (g, m["tgid"], label)))
            ga.make_move(g, m["tgid"], label)
    return out


@pytest.fixture(scope="module")
def games():
    return _random_games()


@pytest.fixture(scope="module")
def positions(games):
    return [(ga, moves) for ga, moves, _ in games]


@pytest.fixture(scope="module")
def played(games):
    return [move for _, _, move in games if move]


def _snapshot(pos):
    return (list(pos.board), list(pos.used), list(pos.kings), pos.stm)


class TestParity:
    def test_positions_cover_castling_and_promotion(self, positions, played):
        assert len(positions) > 500
        assert any(label for _, _, label in played)
        assert any((g, t) in CASTLING_ROOK for g, t, _ in played)

    def test_legal_moves_match(self, positions):
        for ga, _ in positions:
            assert _new_moves(Position.from_game(ga)) == _old_moves(ga), ga.slog

    def test_has_legal_move_matches_move_possible(self, positions):
        for ga, _ in positions:
            assert Position.from_game(ga).has_legal_move() == ga.move_possible()

    def test_evaluation_matches(self, positions):
        for ga, _ in positions[::3]:
            pos = Position.from_game(ga)
            for pid in range(3):
                assert pos.evaluate(pid) == evaluate_for_pid(ga, pid), ga.slog

    def test_attack_queries_match(self, positions):
        for ga, _ in positions[::7]:
            pos = Position.from_game(ga)
            for pid in range(3):
                player = ga.players[pid]
                king = player.king_piece.hex.pos
                assert pos.attacked(
                    INDEX[(king.q, king.r)], pid
                ) == ga.board._is_attacked(king, player)
                for i in range(N):
                    expected = ga.board.pos_in_chess(player, Pos(*CELLS[i]))[0]
                    assert pos.reached(i, pid) == expected, (ga.slog, pid, CELLS[i])

    def test_make_matches_engine_and_unmake_restores(self, positions):
        for ga, _ in positions[::2]:
            pos = Position.from_game(ga)
            before = _snapshot(pos)
            for i, to, promo, _ in pos.legal_moves():
                for label in ("Q", "N") if promo else ("",):
                    undo = pos.make(i, to, label)
                    after = ga.copy()
                    after.make_move(i, to, label)
                    expected = Position.from_game(after)
                    assert _snapshot(pos) == _snapshot(expected), (ga.slog, i, to)
                    pos.unmake(undo)
                    assert _snapshot(pos) == before

    def test_terminal_score_matches(self, positions):
        ended = [ga for ga, moves in positions if not moves]
        assert ended, "seeds should include at least one finished game"
        for ga in ended:
            pos = Position.from_game(ga)
            for pid in range(3):
                assert pos.terminal_score(pid) == bot._terminal_score(ga, pid)


# (view_pid, slog, move chosen by the pre-rewrite GameAPI search at depth 3)
REFERENCE = [
    (1, "BOIAFCIANGLGENGMGBLGOEMF", "GOJI"),
    (
        1,
        "BOIAFCIANGLGENGMGBLGOEMFGMBHDFDGODIGBNCMIAJCOGCMEOEKBGINMFNGFNFLCFBIIGINEKDJEECF",
        "INFK",
    ),
    (
        1,
        "BOIAFCIANGLGENGMGBLGOEMFGMBHDFDGODIGBNCMIAJCOGCMEOEKBGINMFNGFNFLCFBIIGINEKDJEECFCMGEDJGGCFBHINHOFOEMLGJKNGMFAOHHBHFLNHMIHHNBHANAHOJKGGAMDEEEJKHKCOFMFLHKOBAIAMMG",
        "EEEJ",
    ),
    (
        1,
        "BOIAFCIANGLGENGMGBLGOEMFGMBHDFDGODIGBNCMIAJCOGCMEOEKBGINMFNGFNFLCFBIIGINEKDJEECFCMGEDJGGCFBHINHOFOEMLGJKNGMFAOHHBHFLNHMIHHNBHANAHOJKGGAMDEEEJKHKCOFMFLHKOBAIAMMGNAOAMFMGGNHMJCIFNCMCANCLAHBHAIEMGOEMFDGEOHFHNBMBBHFHNEDJMBHBEEEMNFLFDOCOEMLFMGLFHNIMFHMADJCLCODOOAMCNDMCHBHIMAMCOCNAHIGJ",
        "MCHH",
    ),
    (2, "BNDLBGINNEJGFOINGCGDOGEL", "GOKG"),
    (
        2,
        "BNDLBGINNEJGFOINGCGDOGELCOELDEHINBMCFNGMHINIJGGDINKKEEGDODENDOENNINHOHLKGOMCNHIH",
        "OCMF",
    ),
    (
        2,
        "BNDLBGINNEJGFOINGCGDOGELCOELDEHINBMCFNGMHINIJGGDINKKEEGDODENDOENNINHOHLKGOMCNHIHOEODCNDMIHELNDMCENDOGDKHLKKKHOOHKHHNNGLIEOELDFEFKKHNOHHOBHBIHNGNHOHBAHDHGNHMELFJ",
        "DHIH",
    ),
    (
        2,
        "BNDLBGINNEJGFOINGCGDOGELCOELDEHINBMCFNGMHINIJGGDINKKEEGDODENDOENNINHOHLKGOMCNHIHOEODCNDMIHELNDMCENDOGDKHLKKKHOOHKHHNNGLIEOELDFEFKKHNOHHOBHBIHNGNHOHBAHDHGNHMELFJHAHBHMHBFJFECFFELIKIDOCNFEHBOCLDBOEIHBIDOFMEEIIAGBIANALACNDOIAGEOANAAOBNGEKINAKDBNBICGBIKDKIANAMDHJBKIIIDOCOJBOBLDOBDLDK",
        "IDHG",
    ),
    (0, "BOIABGINOBAIEOFMFCIAAIFN", "GOFN"),
    (
        0,
        "BOIABGINOBAIEOFMFCIAAIFNGOFNINNDODNDHONICFAIOGCMNIHOGBHCNDDNFODNHCCMOHOGFNAIAHAI",
        "NGMH",
    ),
    (
        0,
        "BOIABGINOBAIEOFMFCIAAIFNGOFNINNDODNDHONICFAIOGCMNIHOGBHCNDDNFODNHCCMOHOGFNAIAHAINBLBFMGLCMANOABNGLIKANOGBNOAENKKOGNFNAMAGNILFDHDNCMCAOAMAIALNHMHAMFMEEMAOCNFIKIA",
        "DENE",
    ),
    (1, "BOIABGHMOBAIGOHMGBMHAIFN", "EOFN"),
    (
        1,
        "BOIABGHMOBAIGOHMGBMHAIFNCOFNEEHHNFMHBNBMDEHEOGIAGNGLAHANNBLDEOGNHHNEODNEAOFJHAIA",
        "NEHE",
    ),
    (
        1,
        "BOIABGHMOBAIGOHMGBMHAIFNCOFNEEHHNFMHBNBMDEHEOGIAGNGLAHANNBLDEOGNHHNEODNEAOFJHAIAMHLHHMLEHEHDNELEENILHDHNLECNDOENHNNHCNDNENGMGCHCDNANFNELNHOHANFDFJFLCFFDNALAILFI",
        "IAIG",
    ),
]


@pytest.mark.parametrize("view_pid, slog, expected", REFERENCE)
def test_choose_move_picks_the_reference_move(view_pid, slog, expected, monkeypatch):
    # Book off: the reference moves were recorded from search alone.
    monkeypatch.setattr(bot, "book_move", lambda ga: None)
    ga = get_game(view_pid, slog)
    from_gid, m, label = bot.choose_move(ga, depth=3)
    from_pos, to_pos = ga.gid2hex[from_gid].pos, ga.gid2hex[m["tgid"]].pos
    assert ga.move2slog(from_pos, to_pos, label) == expected
    assert m in ga.valid_moves(from_gid)


def test_search_root_puts_first_move_first():
    pos = Position.from_game(get_game(0, REFERENCE[1][1]))
    search = Search(pos)
    best = search.search_root(3)
    assert Search(pos).search_root(3, first=best[:4])[:5] == best[:5]
