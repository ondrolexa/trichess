import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import get_current_user, jwt_required
from flask_restx import Api, Resource, fields, reqparse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from engine import get_game
from webapp.botplayer import maybe_trigger_bot
from webapp.events import publish_board_move
from webapp.main import GAME, db, post_notification
from webapp.models import RatingHistory, Score, TriBoard, User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

blueprint = Blueprint("api", __name__)

api = Api(blueprint, version="1.0", title="TriChess API")

authorizations = {
    "jsonWebToken": {
        "type": "oauth2",
        "flow": "password",
        "tokenUrl": "/token",
        "scopes": {},
    }
}

K = 9.0
L = 400.0
starting_rating = 500.0

# A single human playing against 2 bots is solo practice — live "your
# turn"/"game over" pushes for it are suppressed by default (see
# GameBoard.post()'s notify_players). resend_notification() (webapp/main.py)
# deliberately never consults this — a solo player who walked away should
# still get the 24h-stale reminder regardless.
SINGLE_PLAYER_NOTIFICATIONS = (
    os.environ.get("SINGLE_PLAYER_NOTIFICATIONS", "false").lower() == "true"
)


def _bot_notification_flags(players):
    """Return (board_has_bot, notify_players) for a game's 3 seats.

    Games with a bot seat are casual: no Score rows, no rating impact, no
    pointless notifications to a bot's own (unmonitored) username. A solo
    human playing against 2 bots additionally has its own notifications
    suppressed by default (see SINGLE_PLAYER_NOTIFICATIONS).
    """
    board_has_bot = any(p.is_bot for p in players.values())
    single_player_vs_bots = sum(p.is_bot for p in players.values()) == 2
    notify_players = not single_player_vs_bots or SINGLE_PLAYER_NOTIFICATIONS
    return board_has_bot, notify_players


def finalize_if_finished(
    tb, ga, players, board_has_bot, notify_players, actor_user=None
):
    """If *ga* (the board's current replayed state) is over, mark *tb*
    finished and run the same scoring/notification/logging that a live
    move ending the game goes through. Returns the endgame kind classifying
    how it ended, or None if the game isn't actually over.

    *actor_user* is the User to credit the GAME log line to; None when
    called from an automated sweep rather than a live request. Caller is
    responsible for the eventual db.session.commit().
    """
    endgame_kind = ga.endgame()
    if endgame_kind is None:
        return None
    tb.status = 2
    log_user_id = actor_user.id if actor_user is not None else None
    if endgame_kind == "draw":
        scores = compute_outcome_scores(ga)
        for uid, value in scores.items():
            if not board_has_bot:
                db.session.add(
                    Score(
                        player_id=players[uid].id,
                        board_id=tb.id,
                        score=value,
                        tag="D",
                        onmove=uid == ga.on_move,
                    )
                )
            if not players[uid].is_bot and notify_players:
                post_notification(
                    players[uid].username,
                    f"Draw agreed in game {tb.id}",
                    "Game over",
                    tb.id,
                )
        logger.log(
            GAME,
            "Game finished — tag D (draw)",
            extra={"user_id": log_user_id, "board_id": tb.id},
        )
    elif endgame_kind == "resignation":
        resigned = ga.voting.results(kind="resign")
        ruid = set([0, 1, 2]).difference(resigned).pop()
        scores = compute_outcome_scores(ga)
        if not board_has_bot:
            for uid, value in scores.items():
                db.session.add(
                    Score(
                        player_id=players[uid].id,
                        board_id=tb.id,
                        score=value,
                        tag="R",
                        onmove=uid == ga.on_move,
                    )
                )
        if not players[ruid].is_bot and notify_players:
            post_notification(
                players[ruid].username,
                f"You win in game {tb.id} by resignation",
                "Game over",
                tb.id,
            )
        for uid in resigned:
            if not players[uid].is_bot and notify_players:
                post_notification(
                    players[uid].username,
                    f"You lost in game {tb.id} by resignation",
                    "Game over",
                    tb.id,
                )
        logger.log(
            GAME,
            "Game finished — tag R (resignation)",
            extra={"user_id": log_user_id, "board_id": tb.id},
        )
    elif endgame_kind == "checkmate":
        scores = compute_outcome_scores(ga)
        for uid, value in scores.items():
            if not board_has_bot:
                db.session.add(
                    Score(
                        player_id=players[uid].id,
                        board_id=tb.id,
                        score=value,
                        tag="N",
                        onmove=uid == ga.on_move,
                    )
                )
            if players[uid].is_bot or not notify_players:
                continue
            if uid == ga.on_move:
                post_notification(
                    players[uid].username,
                    f"You lost in game {tb.id}",
                    "Game over",
                    tb.id,
                )
            else:
                post_notification(
                    players[uid].username,
                    f"{players[ga.on_move].username} lost in game {tb.id}. Your score is {scores[uid]:g}",
                    "Game over",
                    tb.id,
                )
        logger.log(
            GAME,
            "Game finished — tag N (checkmate)",
            extra={"user_id": log_user_id, "board_id": tb.id},
        )
    elif endgame_kind == "stalemate":
        scores = compute_outcome_scores(ga)
        for uid, value in scores.items():
            if not board_has_bot:
                db.session.add(
                    Score(
                        player_id=players[uid].id,
                        board_id=tb.id,
                        score=value,
                        tag="S",
                        onmove=uid == ga.on_move,
                    )
                )
            if not players[uid].is_bot and notify_players:
                post_notification(
                    players[uid].username,
                    f"The game {tb.id} ended in a stalemate",
                    "Game over",
                    tb.id,
                )
        logger.log(
            GAME,
            "Game finished — tag S (stalemate)",
            extra={"user_id": log_user_id, "board_id": tb.id},
        )
    else:  # endgame_kind == "repetition"
        scores = compute_outcome_scores(ga)
        for uid, value in scores.items():
            if not board_has_bot:
                db.session.add(
                    Score(
                        player_id=players[uid].id,
                        board_id=tb.id,
                        score=value,
                        tag="T",
                        onmove=uid == ga.on_move,
                    )
                )
            if not players[uid].is_bot and notify_players:
                post_notification(
                    players[uid].username,
                    f"The game {tb.id} ended in a threefold repetition",
                    "Game over",
                    tb.id,
                )
        logger.log(
            GAME,
            "Game finished — tag T (repetition)",
            extra={"user_id": log_user_id, "board_id": tb.id},
        )
    if not board_has_bot:
        record_game_rating(tb, scores)
    return endgame_kind


def sweep_finalize(board_id):
    """If board_id's current position is already game-over, finalize it
    (status/scores/notifications/log) without requiring a new move to be
    POSTed. Returns True if it just finalized, False if the game is still
    ongoing (or the board doesn't exist / isn't active).

    Used by bot_sweep_command (self-heals a board stuck at status=1 whose
    slog already replays to a terminal position — e.g. a legacy game that
    predates a since-added endgame rule) and maybe_trigger_bot (so a bot is
    never asked to search for a move on a position that's already over).
    """
    tb = db.session.get(TriBoard, board_id)
    if tb is None or tb.status != 1:
        return False
    ga = get_game(0, tb.slog)
    players = {0: tb.player_0, 1: tb.player_1, 2: tb.player_2}
    board_has_bot, notify_players = _bot_notification_flags(players)
    endgame_kind = finalize_if_finished(tb, ga, players, board_has_bot, notify_players)
    if endgame_kind is None:
        return False
    db.session.commit()
    publish_board_move(tb.id, len(tb.slog))
    return True


def _seat_map(tb):
    """user id -> seat index (0/1/2) for a TriBoard's three players."""
    return {tb.player_0_id: 0, tb.player_1_id: 1, tb.player_2_id: 2}


def _accept_posted_slog(ga1, posted, poster_pid):
    """Canonical new slog if *posted* is exactly one legal step after *ga1*
    by *poster_pid*, else None.

    Replaying a slog applies moves without any legality check, so the posted
    slog is never trusted as-is: a vote must equal what the server itself
    generates for the open vote, and a move must be a single appended chunk
    that valid_moves() allows.
    """
    if ga1.on_move != poster_pid:
        return None
    if ga1.voting.needed():
        makers = [
            ga1.resignation_vote if ga1.voting.kind == "resign" else ga1.draw_vote
        ]
    else:
        makers = [ga1.resignation_vote, ga1.draw_vote]
    for make in makers:
        for vote in (True, False):
            if posted == make(vote):
                return get_game(0, posted).slog
    if (
        ga1.voting.needed()
        or len(posted) != len(ga1.slog) + 4
        or not posted.startswith(ga1.slog)
    ):
        return None
    try:
        from_pos, to_pos, label = ga1.slog2pos(*posted[-4:])
        from_gid = ga1.pos2gid[from_pos]
        to_gid = ga1.pos2gid[to_pos]
    except KeyError, ValueError:
        return None
    move = next((m for m in ga1.valid_moves(from_gid) if m["tgid"] == to_gid), None)
    if move is None or bool(label) != bool(move["promotion"]):
        return None
    return ga1.slog + ga1.move2slog(from_pos, to_pos, label)


def _board_summary(tb, user_id):
    """Dict shape shared by ActiveGames.get()'s "own"/"joined" lists."""
    ga = get_game(0, tb.slog)
    seats = _seat_map(tb)
    return {
        "id": tb.id,
        "player_0": tb.player_0.username,
        "player_1": tb.player_1.username,
        "player_2": tb.player_2.username,
        "my_turn": seats[user_id] == ga.on_move,
    }


def _chess_status(inchess, king_pos, chess_by):
    """Shape an engine in_chess()/in_chess_next() tuple into the JSON API's
    nullable-object form: None when not in chess, else {king_pos, chess_by}."""
    return {"king_pos": king_pos, "chess_by": chess_by} if inchess else None


def compute_outcome_scores(ga):
    """Score (out of 2.0) awarded to each player once a finished game's result
    is known — shared by the API's finished-game preview (GameInfo) and its
    persist path (GameBoard), which previously reimplemented this separately."""
    match ga.endgame():
        case "resignation":
            resigned = ga.voting.results(kind="resign")
            uid = set([0, 1, 2]).difference(resigned).pop()
            scores = {0: 0.0, 1: 0.0, 2: 0.0}
            scores[uid] = 2.0
            return scores
        case "checkmate":
            in_chess, _, who = ga.in_chess()
            scores = {0: 0.0, 1: 0.0, 2: 0.0}
            tot = [len(p) for p in who.values()]
            for uid, v in enumerate(tot):
                score = v * 2 / sum(tot)
                if score > 0:
                    scores[uid] = score
            return scores
        case _:
            # draw, stalemate, repetition all split points equally
            return {0: 2.0 / 3, 1: 2.0 / 3, 2: 2.0 / 3}


def elo_update(ratings, scores):
    """3-player Elo: the three players' new ratings after one game, from their
    ratings before it and their scores in it (out of 2.0)."""
    q = [10 ** (r / L) for r in ratings]
    total = sum(q)
    return [r + K * (s - qi / total) for r, s, qi in zip(ratings, scores, q)]


def _rated_games():
    """Every rated (bot-free) finished game in rating order:
    (board_id, finished_at, (p0, p1, p2), (s0, s1, s2))."""
    S0 = aliased(Score, name="s0")
    S1 = aliased(Score, name="s1")
    S2 = aliased(Score, name="s2")
    # Games with a bot seat don't create Score rows (see GameBoard.post()'s
    # board_has_bot guard) — excluding them here too, not just via missing
    # Score rows, matters: an included-but-scoreless board would COALESCE to
    # "everyone scored 0", which the Elo update reads as a real (and wrong)
    # result rather than "this game doesn't count".
    bot_ids = select(User.id).where(User.is_bot)
    stmt = (
        select(
            TriBoard.id,
            TriBoard.modified_at,
            TriBoard.player_0_id,
            TriBoard.player_1_id,
            TriBoard.player_2_id,
            func.coalesce(S0.score, 0),
            func.coalesce(S1.score, 0),
            func.coalesce(S2.score, 0),
        )
        .outerjoin(
            S0, and_(TriBoard.id == S0.board_id, TriBoard.player_0_id == S0.player_id)
        )
        .outerjoin(
            S1, and_(TriBoard.id == S1.board_id, TriBoard.player_1_id == S1.player_id)
        )
        .outerjoin(
            S2, and_(TriBoard.id == S2.board_id, TriBoard.player_2_id == S2.player_id)
        )
        .where(
            TriBoard.status == 2,
            TriBoard.player_0_id.notin_(bot_ids),
            TriBoard.player_1_id.notin_(bot_ids),
            TriBoard.player_2_id.notin_(bot_ids),
        )
        .order_by(TriBoard.modified_at, TriBoard.id)
    )
    for board_id, ts, p0, p1, p2, s0, s1, s2 in db.session.execute(stmt):
        yield board_id, ts or datetime.min, (p0, p1, p2), (s0, s1, s2)


def get_rating_history():
    """Replay every rated game from scratch: {user_id: [(timestamp, rating),
    ...]} for every player of at least one. The source of truth that the
    incremental updates (record_game_rating) must agree with."""
    ratings = {}
    history = defaultdict(list)
    for _, ts, ids, scores in _rated_games():
        before = [ratings.get(i, starting_rating) for i in ids]
        for i, rating in zip(ids, elo_update(before, scores)):
            ratings[i] = rating
            history[i].append((ts, rating))
    return dict(history)


def record_game_rating(tb, scores):
    """Apply one just-finished rated game to its players' ratings and rating
    history, in the caller's transaction (it commits).

    The three users' rows are locked first, in id order, so two games ending
    at once can't both start from the same old rating. FOR NO KEY UPDATE, so
    log rows naming these users (DBHandler, own connection) aren't blocked.
    """
    ids = [tb.player_0_id, tb.player_1_id, tb.player_2_id]
    users = {
        u.id: u
        for u in db.session.query(User)
        .filter(User.id.in_(ids))
        .order_by(User.id)
        .with_for_update(key_share=True)
    }
    before = [
        users[i].rating if users[i].rating is not None else starting_rating for i in ids
    ]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i, rating in zip(ids, elo_update(before, [scores[s] for s in range(3)])):
        users[i].rating = rating
        db.session.add(
            RatingHistory(user_id=i, board_id=tb.id, rating=rating, created_at=now)
        )


def rebuild_ratings():
    """Recompute every rating and the whole rating history from all rated
    games (after a rated game is deleted, or to repair). Caller commits."""
    ratings = {}
    db.session.query(RatingHistory).delete()
    for board_id, ts, ids, scores in _rated_games():
        before = [ratings.get(i, starting_rating) for i in ids]
        for i, rating in zip(ids, elo_update(before, scores)):
            ratings[i] = rating
            db.session.add(
                RatingHistory(
                    user_id=i, board_id=board_id, rating=rating, created_at=ts
                )
            )
    for user in User.query.filter_by(is_bot=False):
        user.rating = ratings.get(user.id, starting_rating)
    return len(ratings)


def get_user_rating_history(user_id):
    """[(timestamp, rating), ...] after each of the user's rated games;
    empty if they have none."""
    return [
        (h.created_at, h.rating)
        for h in RatingHistory.query.filter_by(user_id=user_id).order_by(
            RatingHistory.created_at, RatingHistory.id
        )
    ]


# Client-supplied slogs are replayed in full (~20 µs per entry), so their
# size is capped: real games stay under ~300 entries.
MAX_SLOG_ENTRIES = 4000


def slog_arg(value):
    """reqparse type for a slog: a string of 4-char entries, bounded."""
    if not isinstance(value, str) or len(value) % 4:
        raise ValueError("slog must be a string of 4-character entries")
    if len(value) > 4 * MAX_SLOG_ENTRIES:
        raise ValueError(f"slog longer than {MAX_SLOG_ENTRIES} entries")
    return value


# move API

moveapi = api.namespace(
    "move", description="Move validation", authorizations=authorizations
)

ValidMovesParser = reqparse.RequestParser()
ValidMovesParser.add_argument(name="slog", type=slog_arg, required=True, nullable=False)
ValidMovesParser.add_argument(name="view_pid", type=int, required=True, nullable=False)
ValidMovesParser.add_argument(name="gid", type=int, required=True, nullable=False)
valid_payload = api.model(
    "Valid payload",
    {
        "slog": fields.String(example="BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJ"),
        "view_pid": fields.Integer(example=0),
        "gid": fields.Integer(example=167),
    },
)

valid_target = api.model(
    "Target",
    {
        "tgid": fields.Integer(example=167),
        "kind": fields.String(example="safe"),
        "promotion": fields.Boolean,
    },
)

valid_response = api.model(
    "Valid response",
    {
        "targets": fields.List(fields.Nested(valid_target)),
    },
)


@moveapi.route("/valid")
class ValidMoves(Resource):
    @moveapi.expect(valid_payload, validate=True)
    @moveapi.doc(
        description="Returns all valid moves from given position",
        security="jsonWebToken",
        responses={
            404: "gid not found",
            406: "slog parsing error",
            417: "Unexpected error",
        },
    )
    @jwt_required()
    @moveapi.response(200, "Success", valid_response)
    def post(self):
        state = ValidMovesParser.parse_args()
        slog = state.get("slog")
        gid = state.get("gid")
        try:
            ga = get_game(state.get("view_pid"), slog)
        except Exception as err:
            logger.error(f"[POST /valid] slog parsing error: {err}")
            moveapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"targets": ga.valid_moves(gid)}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                logger.error(f"[POST /valid] Unexpected error: {err}")
                moveapi.abort(417, message="An unexpected error occurred")


MakeMoveParser = reqparse.RequestParser()
MakeMoveParser.add_argument(name="slog", type=slog_arg, required=True, nullable=False)
MakeMoveParser.add_argument(name="view_pid", type=int, required=True, nullable=False)
MakeMoveParser.add_argument(name="gid", type=int, required=True, nullable=False)
MakeMoveParser.add_argument(name="tgid", type=int, required=True, nullable=False)
MakeMoveParser.add_argument(name="new_piece", type=str, required=True, nullable=False)
move_payload = api.model(
    "Move payload",
    {
        "slog": fields.String(example="BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJ"),
        "view_pid": fields.Integer(example=0),
        "gid": fields.Integer(example=167),
        "tgid": fields.Integer(example=72),
        "new_piece": fields.String(example=""),
    },
)

move_response = api.model(
    "Move response",
    {
        "slog": fields.String(),
    },
)


@moveapi.route("/make")
class MakeMove(Resource):
    @moveapi.expect(move_payload, validate=True)
    @moveapi.doc(
        description="Make move and return updated slog",
        security="jsonWebToken",
        responses={
            404: "gid not found",
            406: "slog parsing error",
            417: "Unexpected error",
        },
    )
    @jwt_required()
    @moveapi.response(200, "Success", move_response)
    def post(self):
        state = MakeMoveParser.parse_args()
        slog = state.get("slog")
        from_gid = state.get("gid")
        to_gid = state.get("tgid")
        new_piece = state.get("new_piece")
        try:
            ga = get_game(state.get("view_pid"), slog)
        except Exception as err:
            logger.error(f"[POST /make] slog parsing error: {err}")
            moveapi.abort(406, message="slog parsing error")
        else:
            try:
                ga.make_move(from_gid, to_gid, new_piece=new_piece)
                return {"slog": ga.slog}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                logger.error(f"[POST /make] Unexpected error: {err}")
                moveapi.abort(417, message="An unexpected error occurred")


# game API

gameapi = api.namespace(
    "game", description="Game information", authorizations=authorizations
)

GameInfoParser = reqparse.RequestParser()
GameInfoParser.add_argument(name="slog", type=slog_arg, required=True, nullable=False)
GameInfoParser.add_argument(name="view_pid", type=int, required=True, nullable=False)

game_payload = api.model(
    "Game payload",
    {
        "slog": fields.String(
            example="BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJGOKGBGDINFMFKGCKDIHGOGIJDNEMDEIJNBLBBOCMIJKIODNFFOGLKIGIOHKLINJMGIGDOBKDEODNGBIDNEJGCNELIDOANFMECKALOAIDMEHODOCNBHBJHOMEDLEKBJALNALCCMDKAHCHMELEAODOHGLENDLEDKFJCIDINCMDCNAOFCGEKJJKDNDIAIBIKDHADIDFEDFCKLKHDFLBCHKH"
        ),
        "view_pid": fields.Integer(example=0),
    },
)

last_move = api.model(
    "Last move",
    {
        "from": fields.Integer,
        "to": fields.Integer,
    },
)

game_piece = api.model(
    "Game piece",
    {
        "gid": fields.Integer,
        "piece": fields.String,
    },
)

game_pieces = api.model(
    "Game players pieces",
    {
        0: fields.List(fields.Nested(game_piece)),
        1: fields.List(fields.Nested(game_piece)),
        2: fields.List(fields.Nested(game_piece)),
    },
)

game_eliminated = api.model(
    "Game players eliminated pieces",
    {
        0: fields.List(fields.String),
        1: fields.List(fields.String),
        2: fields.List(fields.String),
    },
)

player_0_eliminations = api.model(
    "Game player 0 eliminations of opponent pieces",
    {1: fields.Integer, 2: fields.Integer},
)

player_1_eliminations = api.model(
    "Game player 1 eliminations of opponent pieces",
    {2: fields.Integer, 0: fields.Integer},
)

player_2_eliminations = api.model(
    "Game player 2 eliminations of opponent pieces",
    {0: fields.Integer, 1: fields.Integer},
)

game_player_eliminations = api.model(
    "Game players eliminations of opponent pieces",
    {
        0: fields.Nested(player_0_eliminations),
        1: fields.Nested(player_1_eliminations),
        2: fields.Nested(player_2_eliminations),
    },
)

game_pieces_value = api.model(
    "Game players pieces total value",
    {
        0: fields.Integer,
        1: fields.Integer,
        2: fields.Integer,
    },
)

votes = api.model(
    "Voting results",
    {
        "kind": fields.String(enum=["resign", "draw"]),
        "n_voted": fields.Integer,
        0: fields.String(enum=["A", "D"]),
        1: fields.String(enum=["A", "D"]),
        2: fields.String(enum=["A", "D"]),
    },
)

scores = api.model(
    "Game score if ended",
    {
        0: fields.Float,
        1: fields.Float,
        2: fields.Float,
    },
)

in_chess_status = api.model(
    "Chess status (king position + attacking pieces)",
    {
        "king_pos": fields.Integer,
        "chess_by": fields.Nested(game_pieces),
    },
)

game_response = api.model(
    "Game response",
    {
        "move_number": fields.Integer,
        "onmove": fields.Integer,
        "last_move": fields.Nested(last_move),
        "pre_last_move": fields.Nested(last_move),
        "finished": fields.Boolean,
        "endgame": fields.String(
            enum=["checkmate", "draw", "resignation", "stalemate", "repetition"]
        ),
        "in_chess": fields.Nested(in_chess_status, allow_null=True),
        "in_chess_next": fields.Nested(in_chess_status, allow_null=True),
        "pieces": fields.Nested(game_pieces),
        "pieces_value": fields.Nested(game_pieces_value),
        "eliminated": fields.Nested(game_eliminated),
        "eliminated_value": fields.Nested(game_pieces_value),
        "eliminations": fields.Nested(game_player_eliminations),
        "vote_draw_needed": fields.Boolean,
        "vote_resign_needed": fields.Boolean,
        "vote_results": fields.Nested(votes),
        "score": fields.Nested(scores),
    },
)


@gameapi.route("/info")
class GameInfo(Resource):
    @gameapi.expect(game_payload, validate=True)
    @gameapi.doc(
        description="Get information about game",
        security="jsonWebToken",
        responses={406: "slog parsing error", 417: "Unexpected error"},
    )
    @jwt_required()
    @gameapi.response(200, "Success", game_response)
    def post(self):
        state = GameInfoParser.parse_args()
        slog = state.get("slog")
        try:
            ga = get_game(state.get("view_pid"), slog)
        except Exception as err:
            logger.error(f"[POST /info] slog parsing error: {err}")
            gameapi.abort(406, message="slog parsing error")
        else:
            try:
                res = {}
                res["move_number"] = ga.move_number
                res["onmove"] = ga.on_move
                res["last_move"] = ga.last_move
                res["pre_last_move"] = ga.pre_last_move
                res["endgame"] = ga.endgame()
                res["finished"] = res["endgame"] is not None
                res["in_chess"] = _chess_status(*ga.in_chess())
                res["in_chess_next"] = _chess_status(*ga.in_chess_next())
                res["pieces"] = ga.pieces()
                res["pieces_value"] = ga.pieces_value()
                res["eliminated"] = ga.eliminated()
                res["eliminated_value"] = ga.eliminated_value()
                res["eliminations"] = ga.player_eliminations()
                res["vote_needed"] = ga.voting.needed()
                res["vote_results"] = ga.voting.votes()
                res["score"] = {0: 0.0, 1: 0.0, 2: 0.0}
                if res["finished"]:
                    res["score"] = compute_outcome_scores(ga)
                return res
            except Exception as err:
                logger.error(f"[POST /info] Unexpected error: {err}")
                gameapi.abort(417, message="An unexpected error occurred")


# vote API

voteapi = api.namespace(
    "vote", description="Game voting", authorizations=authorizations
)

VoteParser = reqparse.RequestParser()
VoteParser.add_argument(name="slog", type=slog_arg, required=True, nullable=False)
VoteParser.add_argument(name="view_pid", type=int, required=True, nullable=False)
VoteParser.add_argument(name="vote", type=bool, required=True, nullable=False)
vote_payload = api.model(
    "Vote payload",
    {
        "slog": fields.String(example="BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJ"),
        "view_pid": fields.Integer(example=0),
        "vote": fields.Boolean(example=True),
    },
)

vote_response = api.model(
    "Vote response",
    {
        "slog": fields.String(),
    },
)


@voteapi.route("/draw")
class DrawVote(Resource):
    @voteapi.expect(vote_payload, validate=True)
    @voteapi.doc(
        description="Vote for draw and return updated slog",
        security="jsonWebToken",
        responses={406: "slog parsing error", 417: "Unexpected error"},
    )
    @jwt_required()
    @voteapi.response(200, "Success", vote_response)
    def post(self):
        state = VoteParser.parse_args()
        slog = state.get("slog")
        vote = state.get("vote")
        try:
            ga = get_game(state.get("view_pid"), slog)
        except Exception as err:
            logger.error(f"[POST /draw] slog parsing error: {err}")
            voteapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"slog": ga.draw_vote(vote)}
            except Exception as err:
                logger.error(f"[POST /draw] Unexpected error: {err}")
                voteapi.abort(417, message="An unexpected error occurred")


@voteapi.route("/resign")
class ResignVote(Resource):
    @voteapi.expect(vote_payload, validate=True)
    @voteapi.doc(
        description="Vote for resign and return updated slog",
        security="jsonWebToken",
        responses={406: "slog parsing error", 417: "Unexpected error"},
    )
    @jwt_required()
    @voteapi.response(200, "Success", vote_response)
    def post(self):
        state = VoteParser.parse_args()
        slog = state.get("slog")
        vote = state.get("vote")
        try:
            ga = get_game(state.get("view_pid"), slog)
        except Exception as err:
            logger.error(f"[POST /resign] slog parsing error: {err}")
            voteapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"slog": ga.resignation_vote(vote)}
            except Exception as err:
                logger.error(f"[POST /resign] Unexpected error: {err}")
                voteapi.abort(417, message="An unexpected error occurred")


# manager API

managerapi = api.namespace(
    "manager", description="Games manager", authorizations=authorizations
)

BoardParser = reqparse.RequestParser()
BoardParser.add_argument(name="id", type=int, required=True, nullable=False)
BoardParser.add_argument(
    name="view_pid", type=int, required=False, nullable=True, choices=(0, 1, 2)
)

UpdateBoardParser = reqparse.RequestParser()
UpdateBoardParser.add_argument(name="id", type=int, required=True, nullable=False)
UpdateBoardParser.add_argument(
    name="slog", type=slog_arg, required=True, nullable=False
)

board_payload = api.model(
    "Board payload",
    {
        "id": fields.Integer,
        "slog": fields.String,
    },
)

board_response = api.model(
    "Board response",
    {
        "id": fields.Integer,
        "player_0": fields.String,
        "player_1": fields.String,
        "player_2": fields.String,
        "slog": fields.String,
        "view_pid": fields.Integer,
        "move_number": fields.Integer,
        "gid2code": fields.List(fields.String),
    },
)


@managerapi.route("/board")
class GameBoard(Resource):
    @managerapi.doc(
        description="Get trichess board",
        params={
            "id": "Board ID",
            "view_pid": "Optional 0/1/2 perspective override for gid2code only",
        },
        security="jsonWebToken",
        responses={
            404: "Board not found",
            406: "slog parsing error",
            417: "Unexpected error",
        },
    )
    @jwt_required()
    @managerapi.response(200, "Success", board_response)
    @managerapi.expect(BoardParser)
    def get(self):
        args = BoardParser.parse_args()
        id = args["id"]
        view_pid_override = args.get("view_pid")
        res = {}
        user = get_current_user()
        try:
            user_in = TriBoard.for_player(user.id)
            active_or_archive = db.or_(
                TriBoard.status == 1,
                TriBoard.status == 2,
            )
            tb = (
                TriBoard.query.filter_by(id=id)
                .filter(active_or_archive)
                .filter(user_in)
                .first()
            )
        except Exception as err:
            logger.error(f"[GET /board] Unexpected error: {err}")
            managerapi.abort(417, message="An unexpected error occurred")
        else:
            try:
                pid = _seat_map(tb)
                res["id"] = tb.id
                res["player_0"] = tb.player_0.username
                res["player_1"] = tb.player_1.username
                res["player_2"] = tb.player_2.username
                res["slog"] = tb.slog
                res["view_pid"] = pid[user.id]
                try:
                    ga = get_game(pid[user.id], tb.slog or "")
                    res["move_number"] = ga.move_number
                    code_pid = (
                        pid[user.id] if view_pid_override is None else view_pid_override
                    )
                    gid2hex = (
                        ga.gid2hex
                        if code_pid == pid[user.id]
                        else get_game(code_pid, tb.slog or "").gid2hex
                    )
                    res["gid2code"] = [
                        gid2hex[gid].pos.code for gid in range(len(gid2hex))
                    ]
                except Exception as err:
                    logger.error(f"[GET /board] slog parsing error: {err}")
                    managerapi.abort(406, message="slog parsing error")
                return res
            except Exception as err:
                logger.error(f"[GET /board] Board not found: {err}")
                managerapi.abort(404, message="Board not found")

    @managerapi.doc(
        description="Update trichess board slog",
        security="jsonWebToken",
        responses={
            404: "Board not found",
            409: "Posted slog is in conflict with server one",
            417: "Unexpected error",
        },
    )
    @jwt_required()
    @managerapi.response(200, "Success")
    @managerapi.expect(board_payload, validate=True)
    def post(self):
        state = UpdateBoardParser.parse_args()
        user1 = get_current_user()
        try:
            user_in = TriBoard.for_player(user1.id)
            tb = (
                db.session.query(TriBoard)
                # FOR NO KEY UPDATE: serialises moves on this board but
                # doesn't block the FK check of a Log row written about it
                # meanwhile (DBHandler uses its own connection).
                .with_for_update(key_share=True)
                .filter_by(status=1, id=state.id)
                .filter(user_in)
                .first()
            )
        except Exception as err:
            logger.error(
                f"[POST /board] Unexpected error during accessing triboard: {err}"
            )
            managerapi.abort(417, message="An unexpected error occurred")
        else:
            if tb:
                try:
                    ga1 = get_game(0, tb.slog)
                    move_id = f"{ga1.move_number:03d}"
                    logger.log(
                        GAME,
                        "Move.str " + move_id,
                        extra={
                            "user_id": user1.id,
                            "board_id": tb.id,
                        },
                    )
                    pid = _seat_map(tb)
                    new_slog = _accept_posted_slog(ga1, state.slog, pid[user1.id])
                    players = {
                        0: tb.player_0,
                        1: tb.player_1,
                        2: tb.player_2,
                    }
                    board_has_bot, notify_players = _bot_notification_flags(players)
                    if new_slog is not None:
                        ga2 = get_game(0, new_slog)
                        tb.slog = ga2.slog
                        user = players[ga2.on_move]
                        endgame_kind = finalize_if_finished(
                            tb,
                            ga2,
                            players,
                            board_has_bot,
                            notify_players,
                            actor_user=user,
                        )
                        if endgame_kind is None:
                            # notify next player
                            if not players[ga2.on_move].is_bot and notify_players:
                                post_notification(
                                    players[ga2.on_move].username,
                                    f"It's your turn in game {state.id}",
                                    "Your turn",
                                    state.id,
                                )
                        logger.log(
                            GAME,
                            "Move end " + move_id,
                            extra={
                                "user_id": user1.id,
                                "board_id": tb.id,
                            },
                        )
                        db.session.commit()
                        publish_board_move(tb.id, len(ga2.slog))
                        if tb.status == 1:
                            # finalize_if_finished just ran on this position
                            maybe_trigger_bot(tb.id, finalize=False)
                    else:
                        managerapi.abort(
                            409, message="Posted slog is in conflict with server one"
                        )
                except Exception as err:
                    logger.error(
                        f"[POST /board] Unexpected error during processing triboard: {err}"
                    )
                    # Undo any Score rows already added but not yet committed above.
                    db.session.rollback()
                    managerapi.abort(417, message="An unexpected error occurred")
            else:
                managerapi.abort(404, message="Board not found")


board_view_fields = api.model(
    "Board overview",
    {
        "id": fields.Integer,
        "player_0": fields.String,
        "player_1": fields.String,
        "player_2": fields.String,
        "my_turn": fields.Boolean,
    },
)

games_fields = api.model(
    "Games",
    {
        "own": fields.List(fields.Nested(board_view_fields)),
        "joined": fields.List(fields.Nested(board_view_fields)),
    },
)


@managerapi.route("/games")
class ActiveGames(Resource):
    @managerapi.doc(
        description="List all own and joined games for logged in user",
        security="jsonWebToken",
        responses={404: "Unexpected error"},
    )
    @jwt_required()
    @managerapi.response(200, "Success", games_fields)
    def get(self):
        res = {}
        try:
            user = get_current_user()
            user_in = TriBoard.for_player(user.id)
            own = TriBoard.query.filter_by(status=1, owner_id=user.id).all()
            joined = (
                TriBoard.query.filter_by(status=1)
                .filter(TriBoard.owner_id != user.id)
                .filter(user_in)
                .all()
            )
        except Exception as err:
            logger.error(
                f"[GET /games] Unexpected error during accessing triboard: {err}"
            )
            managerapi.abort(417, message="An unexpected error occurred")
        else:
            try:
                res["own"] = [_board_summary(tb, user.id) for tb in own]
                res["joined"] = [_board_summary(tb, user.id) for tb in joined]
                return res
            except Exception as err:
                logger.error(
                    f"[GET /games] Unexpected error during processing triboard: {err}"
                )
                managerapi.abort(417, message="An unexpected error occurred")
