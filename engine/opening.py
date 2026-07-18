import json
from pathlib import Path

from engine.gameapi import GameAPI

# A ply's top move is only ever used once at least this many independent
# finished games agree on it — keeps the book from repeating a single
# game's idiosyncratic choice.
MIN_SUPPORT = 3
# How many plies (half-moves) deep to record. Beyond this, per-game move
# prefixes diverge too fast for a small game corpus to give any real signal.
MAX_BOOK_PLIES = 9

# Lives in instance/ (not engine/) so it survives image rebuilds: the
# Dockerfile only COPYs engine/, but instance/ is bind-mounted from the
# host in docker-compose.yml, same as trichess.db.
BOOK_PATH = Path(__file__).resolve().parent.parent / "instance" / "opening_book.json"

_VOTE_PREFIXES = ("r", "s", "R", "S")


def _moves_only(slog: str) -> list[str]:
    """Split a slog into its 4-char chunks, dropping vote chunks."""
    chunks = [slog[i : i + 4] for i in range(0, len(slog), 4)]
    return [c for c in chunks if c[:1] not in _VOTE_PREFIXES]


def build_book(slogs: list[str]) -> dict[int, dict[str, int]]:
    """Count, per ply index, how often each move chunk was played.

    Pooled across games regardless of what preceded a given ply (rather
    than keyed by the exact move prefix) — with only a modest number of
    finished games, pooling is what actually gives each ply real support;
    exact-prefix matching collapses to ~1 observation per prefix after the
    very first move.
    """
    book: dict[int, dict[str, int]] = {}
    for slog in slogs:
        moves = _moves_only(slog)
        for ply in range(min(len(moves), MAX_BOOK_PLIES)):
            counts = book.setdefault(ply, {})
            move = moves[ply]
            counts[move] = counts.get(move, 0) + 1
    return book


def save_book(book: dict[int, dict[str, int]], path: Path = BOOK_PATH) -> None:
    with open(path, "w") as f:
        json.dump(book, f, indent=2, sort_keys=True)


def load_book(path: Path = BOOK_PATH) -> dict[int, dict[str, int]]:
    if not path.exists():
        return {}
    with open(path) as f:
        raw = json.load(f)
    return {int(ply): counts for ply, counts in raw.items()}


_BOOK = load_book()


def book_move(ga: GameAPI) -> tuple[int, dict, str] | None:
    """Suggest an opening move for the player on move, from historical games.

    Returns (from_gid, move_dict, promo_label) matching choose_move()'s
    return shape, or None when the book has nothing usable for this ply
    (no recorded entry, insufficient support, or the top candidate(s)
    don't happen to be legal in this specific game's actual position).
    """
    if ga.voting.needed():
        return None

    ply = len(_moves_only(ga.slog))
    candidates = _BOOK.get(ply)
    if not candidates:
        return None

    for move, count in sorted(candidates.items(), key=lambda kv: -kv[1]):
        if count < MIN_SUPPORT:
            break
        from_pos, to_pos, _ = ga.slog2pos(*move)
        if from_pos not in ga.pos2gid or to_pos not in ga.pos2gid:
            continue
        from_gid = ga.pos2gid[from_pos]
        hex = ga.gid2hex[from_gid]
        if not hex.has_piece or hex.piece.player.pid != ga.on_move:
            continue
        for m in ga.valid_moves(from_gid):
            if ga.gid2hex[m["tgid"]].pos == to_pos:
                return (from_gid, m, "")

    return None
