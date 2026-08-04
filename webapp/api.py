import logging
import os
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, Response, abort, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Resource, fields, reqparse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from engine import get_game
from webapp.botplayer import maybe_trigger_bot
from webapp.events import publish_board_move, subscribe_board_events
from webapp.main import GAME, db, post_notification
from webapp.models import Score, TriBoard, User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

blueprint = Blueprint("api", __name__)

api = Api(blueprint, version="1.0", title="TriChess API")

authorizations = {
    "jsonWebToken": {"type": "apiKey", "in": "header", "name": "Authorization"}
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


def _parse_ts(raw):
    """Parse SQLite DATETIME string to a Python datetime object."""
    if raw is None:
        return datetime.min
    if isinstance(raw, datetime):
        return raw
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Fallback: return epoch so ordering is still safe
    return datetime.min


def _seat_map(tb):
    """username -> seat index (0/1/2) for a TriBoard's three players."""
    return {
        tb.player_0.username: 0,
        tb.player_1.username: 1,
        tb.player_2.username: 2,
    }


def _board_summary(tb, username):
    """Dict shape shared by ActiveGames.get()'s "own"/"joined" lists."""
    ga = get_game(0, tb.slog)
    seats = _seat_map(tb)
    return {
        "id": tb.id,
        "player_0": tb.player_0.username,
        "player_1": tb.player_1.username,
        "player_2": tb.player_2.username,
        "my_turn": seats[username] == ga.on_move,
    }


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


def get_rating_history():
    """Replay every finished triboard game in chronological order and return
    the full rating trajectory for every player who has appeared in at least
    one finished game.
    """

    S0 = aliased(Score, name="s0")
    S1 = aliased(Score, name="s1")
    S2 = aliased(Score, name="s2")
    users = User.query.all()
    ratings = {u.id: starting_rating for u in users}

    # history stores (timestamp, rating) snapshots after each game
    history = defaultdict(list)

    # Games with a bot seat don't create Score rows (see GameBoard.post()'s
    # board_has_bot guard) — excluding them here too, not just via missing
    # Score rows, matters: an included-but-scoreless board would COALESCE to
    # "everyone scored 0", which the Elo update reads as a real (and wrong)
    # result rather than "this game doesn't count".
    bot_ids = select(User.id).where(User.is_bot)
    stmt = (
        select(
            TriBoard.modified_at,
            TriBoard.player_0_id,
            func.coalesce(S0.score, 0).label("player_0_score"),
            TriBoard.player_1_id,
            func.coalesce(S1.score, 0).label("player_1_score"),
            TriBoard.player_2_id,
            func.coalesce(S2.score, 0).label("player_2_score"),
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
        .order_by(TriBoard.modified_at)
    )
    games = db.session.execute(stmt).all()

    for row in games:
        raw_ts, p0id, p0s, p1id, p1s, p2id, p2s = row

        # Parse timestamp – SQLite stores datetimes as strings
        ts = _parse_ts(raw_ts)

        # Ensure every player appearing in a game has an initial rating
        # (handles edge cases where active=0 users still have games)
        for pid in (p0id, p1id, p2id):
            if pid not in ratings:
                ratings[pid] = starting_rating

        # --- 3-player Elo update ---
        q0 = 10 ** (ratings[p0id] / L)
        q1 = 10 ** (ratings[p1id] / L)
        q2 = 10 ** (ratings[p2id] / L)
        Q = q0 + q1 + q2

        e0 = q0 / Q  # expected score for player 0
        e1 = q1 / Q  # expected score for player 1
        e2 = q2 / Q  # expected score for player 2

        ratings[p0id] += K * (p0s - e0)
        ratings[p1id] += K * (p1s - e1)
        ratings[p2id] += K * (p2s - e2)

        # Record snapshot for each player at this moment in time
        history[p0id].append((ts, ratings[p0id]))
        history[p1id].append((ts, ratings[p1id]))
        history[p2id].append((ts, ratings[p2id]))

    return dict(history)


def get_user_rating_history(user_id):
    """Return the rating trajectory for a single user.
    Returns an empty list if the user has never played a finished game.
    """
    history = get_rating_history()
    return history.get(user_id, [])


def get_current_ratings():
    """Return the final (current) rating for every user as a flat dict.
    Users who have never played a finished game are not included.
    """
    history = get_rating_history()
    return {uid: points[-1][1] for uid, points in history.items() if points}


# rating update
def update_rating_db():
    """Update user rating in database."""
    users = User.query.all()
    current_ratings = get_current_ratings()
    for u in users:
        if u.id in current_ratings:
            u.rating = current_ratings[u.id]

    db.session.commit()


# move API

moveapi = api.namespace(
    "move", description="Move validation", authorizations=authorizations
)

ValidMovesParser = reqparse.RequestParser()
ValidMovesParser.add_argument(name="slog", type=str, required=True, nullable=False)
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
MakeMoveParser.add_argument(name="slog", type=str, required=True, nullable=False)
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
GameInfoParser.add_argument(name="slog", type=str, required=True, nullable=False)
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
        "in_chess": fields.Boolean,
        "king_pos": fields.Integer,
        "chess_by": fields.Nested(game_pieces),
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
                res["in_chess"], res["king_pos"], res["chess_by"] = ga.in_chess()
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
VoteParser.add_argument(name="slog", type=str, required=True, nullable=False)
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
UpdateBoardParser.add_argument(name="slog", type=str, required=True, nullable=False)

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
        username = get_jwt_identity()
        try:
            user = User.query.filter_by(username=username).first()
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
                res["view_pid"] = pid[username]
                try:
                    ga = get_game(pid[username], tb.slog or "")
                    res["move_number"] = ga.move_number
                    code_pid = (
                        pid[username]
                        if view_pid_override is None
                        else view_pid_override
                    )
                    gid2hex = (
                        ga.gid2hex
                        if code_pid == pid[username]
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
        username = get_jwt_identity()
        try:
            user = User.query.filter_by(username=username).first()
            user_in = TriBoard.for_player(user.id)
            tb = (
                db.session.query(TriBoard)
                .with_for_update()
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
                    ga2 = get_game(0, state.slog)
                    pid = _seat_map(tb)
                    players = {
                        0: tb.player_0,
                        1: tb.player_1,
                        2: tb.player_2,
                    }
                    # Games with a bot seat are casual: no Score rows, no
                    # rating impact, no pointless notifications to a bot's
                    # own (unmonitored) username.
                    board_has_bot = any(p.is_bot for p in players.values())
                    single_player_vs_bots = sum(p.is_bot for p in players.values()) == 2
                    notify_players = (
                        not single_player_vs_bots or SINGLE_PLAYER_NOTIFICATIONS
                    )
                    poster = ga1.on_move == pid[username]
                    voting = ga1.voting.active() or ga2.voting.active()
                    oneadded = ga2.move_number - ga1.move_number == 1
                    same = ga2.slog.startswith(ga1.slog)
                    if poster and ((oneadded and same) or voting):
                        tb.slog = ga2.slog
                        user = User.query.filter_by(
                            username=players[ga2.on_move].username
                        ).first()
                        endgame_kind = ga2.endgame()
                        if endgame_kind is not None:
                            # Game finished do all needed
                            tb.status = 2
                            if endgame_kind == "draw":
                                scores = compute_outcome_scores(ga2)
                                for uid, value in scores.items():
                                    if not board_has_bot:
                                        new_score = Score(
                                            player_id=players[uid].id,
                                            board_id=tb.id,
                                            score=value,
                                            tag="D",
                                            onmove=uid == ga2.on_move,
                                        )
                                        db.session.add(new_score)
                                    if not players[uid].is_bot and notify_players:
                                        post_notification(
                                            players[uid].username,
                                            f"Draw agreed in game {state.id}",
                                            "Game over",
                                            state.id,
                                        )
                                logger.log(
                                    GAME,
                                    "Game finished — tag D (draw)",
                                    extra={
                                        "user_id": user.id,
                                        "board_id": tb.id,
                                    },
                                )
                            elif endgame_kind == "resignation":
                                resigned = ga2.voting.results(kind="resign")
                                ruid = set([0, 1, 2]).difference(resigned).pop()
                                scores = compute_outcome_scores(ga2)
                                if not board_has_bot:
                                    for uid, value in scores.items():
                                        new_score = Score(
                                            player_id=players[uid].id,
                                            board_id=tb.id,
                                            score=value,
                                            tag="R",
                                            onmove=uid == ga2.on_move,
                                        )
                                        db.session.add(new_score)
                                # notify
                                if not players[ruid].is_bot and notify_players:
                                    post_notification(
                                        players[ruid].username,
                                        f"You win in game {state.id} by resignation",
                                        "Game over",
                                        state.id,
                                    )
                                for uid in resigned:
                                    if not players[uid].is_bot and notify_players:
                                        post_notification(
                                            players[uid].username,
                                            f"You lost in game {state.id} by resignation",
                                            "Game over",
                                            state.id,
                                        )
                                logger.log(
                                    GAME,
                                    "Game finished — tag R (resignation)",
                                    extra={
                                        "user_id": user.id,
                                        "board_id": tb.id,
                                    },
                                )
                            elif endgame_kind == "checkmate":
                                scores = compute_outcome_scores(ga2)
                                for uid, value in scores.items():
                                    if not board_has_bot:
                                        new_score = Score(
                                            player_id=players[uid].id,
                                            board_id=tb.id,
                                            score=value,
                                            tag="N",
                                            onmove=uid == ga2.on_move,
                                        )
                                        db.session.add(new_score)
                                    if players[uid].is_bot or not notify_players:
                                        continue
                                    if uid == ga2.on_move:
                                        post_notification(
                                            players[uid].username,
                                            f"You lost in game {state.id}",
                                            "Game over",
                                            state.id,
                                        )
                                    else:
                                        post_notification(
                                            players[uid].username,
                                            f"{players[ga2.on_move].username} lost in game {state.id}. Your score is {scores[uid]:g}",
                                            "Game over",
                                            state.id,
                                        )
                                logger.log(
                                    GAME,
                                    "Game finished — tag N (checkmate)",
                                    extra={
                                        "user_id": user.id,
                                        "board_id": tb.id,
                                    },
                                )
                            elif endgame_kind == "stalemate":
                                scores = compute_outcome_scores(ga2)
                                for uid, value in scores.items():
                                    if not board_has_bot:
                                        new_score = Score(
                                            player_id=players[uid].id,
                                            board_id=tb.id,
                                            score=value,
                                            tag="S",
                                            onmove=uid == ga2.on_move,
                                        )
                                        db.session.add(new_score)
                                    if not players[uid].is_bot and notify_players:
                                        post_notification(
                                            players[uid].username,
                                            f"The game {state.id} ended in a stalemate",
                                            "Game over",
                                            state.id,
                                        )
                                logger.log(
                                    GAME,
                                    "Game finished — tag S (stalemate)",
                                    extra={
                                        "user_id": user.id,
                                        "board_id": tb.id,
                                    },
                                )
                            else:  # endgame_kind == "repetition"
                                scores = compute_outcome_scores(ga2)
                                for uid, value in scores.items():
                                    if not board_has_bot:
                                        new_score = Score(
                                            player_id=players[uid].id,
                                            board_id=tb.id,
                                            score=value,
                                            tag="T",
                                            onmove=uid == ga2.on_move,
                                        )
                                        db.session.add(new_score)
                                    if not players[uid].is_bot and notify_players:
                                        post_notification(
                                            players[uid].username,
                                            f"The game {state.id} ended in a threefold repetition",
                                            "Game over",
                                            state.id,
                                        )
                                logger.log(
                                    GAME,
                                    "Game finished — tag T (repetition)",
                                    extra={
                                        "user_id": user.id,
                                        "board_id": tb.id,
                                    },
                                )
                            if not board_has_bot:
                                update_rating_db()
                        else:
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
                            "Move made",
                            extra={
                                "user_id": user.id,
                                "board_id": tb.id,
                            },
                        )
                        db.session.commit()
                        publish_board_move(tb.id, len(ga2.slog))
                        if tb.status == 1:
                            maybe_trigger_bot(tb.id)
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


@blueprint.route("/manager/board/events")
@jwt_required(locations=["query_string"])
def board_events():
    """SSE stream: one ping per move/vote persisted on this board.

    Auth via query-string JWT (locations=["query_string"], this route only
    — the global JWT_TOKEN_LOCATION config is untouched, every other
    endpoint stays header-only) because the browser's native EventSource
    API can't set custom headers; ondro.js strips the "Bearer " prefix off
    the page's normal JWT and appends it as ?jwt=<token>.

    A raw Flask route rather than a Flask-RESTX Resource, since RESTX's
    response marshaling doesn't fit a streaming generator — falls through
    to Flask's normal error handling untouched by RESTX.

    Same seat-membership authorization as GameBoard.get() — status 1
    (active) or 2 (archived/just-finished, so a client already on the page
    when the game ends still gets the final push) boards only, and only
    for a user actually seated on it.
    """
    id = request.args.get("id", type=int)
    if id is None:
        abort(400)
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if user is None:
        abort(401)
    user_in = TriBoard.for_player(user.id)
    active_or_archive = db.or_(TriBoard.status == 1, TriBoard.status == 2)
    tb = (
        TriBoard.query.filter_by(id=id)
        .filter(active_or_archive)
        .filter(user_in)
        .first()
    )
    if tb is None:
        abort(404)

    def gen():
        yield ": connected\n\n"
        yield from subscribe_board_events(id)

    response = Response(stream_with_context(gen()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # Traefik: disable proxy buffering
    return response


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
            username = get_jwt_identity()
            user = User.query.filter_by(username=username).first()
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
                res["own"] = [_board_summary(tb, username) for tb in own]
                res["joined"] = [_board_summary(tb, username) for tb in joined]
                return res
            except Exception as err:
                logger.error(
                    f"[GET /games] Unexpected error during processing triboard: {err}"
                )
                managerapi.abort(417, message="An unexpected error occurred")
