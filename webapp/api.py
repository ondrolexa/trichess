import logging

from flask import Blueprint, request
from flask_jwt_extended import get_current_user, jwt_required
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_restx import Api, Resource, fields, reqparse
from jwt import PyJWTError
from werkzeug.exceptions import HTTPException

from engine import get_game
from webapp.botplayer import maybe_trigger_bot
from webapp.events import publish_board_move
from webapp.game_end import bot_notification_flags, finalize_if_finished
from webapp.log import GAME
from webapp.main import db, post_notification
from webapp.models import GameStatus, TriBoard

logger = logging.getLogger(__name__)

blueprint = Blueprint("api", __name__)

api = Api(blueprint, version="1.0", title="TriChess API")


@api.errorhandler(Exception)
def _api_error(err):
    """Every error raised in a resource. abort()'s HTTPExceptions keep their
    code (flask-restx sends their message itself); auth errors go on to
    flask-jwt-extended's 401/422 handlers; anything else is a 500, which
    flask-restx logs with its traceback (and so into the Log table)."""
    if isinstance(err, HTTPException):
        return {}, err.code
    if isinstance(err, (JWTExtendedException, PyJWTError)):
        raise err
    # Leave nothing half-written (e.g. Score rows of a failed game finish).
    db.session.rollback()
    return {"message": "An unexpected error occurred"}, 500


def _load_game_or_abort(ns, view_pid, slog):
    """Replay *slog* for *view_pid*, or abort with 406 if it doesn't parse."""
    try:
        return get_game(view_pid, slog)
    except Exception as err:
        logger.error(f"[{request.method} {request.path}] slog parsing error: {err}")
        ns.abort(406, message="slog parsing error")


authorizations = {
    "jsonWebToken": {
        "type": "oauth2",
        "flow": "password",
        "tokenUrl": "/token",
        "scopes": {},
    }
}


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
    return {
        "id": tb.id,
        "player_0": tb.player_0.username,
        "player_1": tb.player_1.username,
        "player_2": tb.player_2.username,
        "my_turn": tb.seat_of(user_id) == ga.on_move,
    }


def _chess_status(inchess, king_pos, chess_by):
    """Shape an engine in_chess()/in_chess_next() tuple into the JSON API's
    nullable-object form: None when not in chess, else {king_pos, chess_by}."""
    return {"king_pos": king_pos, "chess_by": chess_by} if inchess else None


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
            500: "Unexpected error",
        },
    )
    @jwt_required()
    @moveapi.response(200, "Success", valid_response)
    def post(self):
        state = ValidMovesParser.parse_args()
        ga = _load_game_or_abort(moveapi, state.get("view_pid"), state.get("slog"))
        try:
            return {"targets": ga.valid_moves(state.get("gid"))}
        except KeyError:
            moveapi.abort(404, message="gid not found")


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
            500: "Unexpected error",
        },
    )
    @jwt_required()
    @moveapi.response(200, "Success", move_response)
    def post(self):
        state = MakeMoveParser.parse_args()
        ga = _load_game_or_abort(moveapi, state.get("view_pid"), state.get("slog"))
        try:
            ga.make_move(
                state.get("gid"), state.get("tgid"), new_piece=state.get("new_piece")
            )
        except KeyError:
            moveapi.abort(404, message="gid not found")
        return {"slog": ga.slog}


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

game_player_eliminations = api.model(
    "Game players eliminations of opponent pieces",
    {
        # Per seat: how many pieces it took from each opponent, in turn order.
        pid: fields.Nested(
            api.model(
                f"Game player {pid} eliminations of opponent pieces",
                {(pid + 1) % 3: fields.Integer, (pid + 2) % 3: fields.Integer},
            )
        )
        for pid in range(3)
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
        responses={406: "slog parsing error", 500: "Unexpected error"},
    )
    @jwt_required()
    @gameapi.response(200, "Success", game_response)
    def post(self):
        state = GameInfoParser.parse_args()
        ga = _load_game_or_abort(gameapi, state.get("view_pid"), state.get("slog"))
        endgame = ga.endgame()
        return {
            "move_number": ga.move_number,
            "onmove": ga.on_move,
            "last_move": ga.last_move,
            "pre_last_move": ga.pre_last_move,
            "endgame": endgame,
            "finished": endgame is not None,
            "in_chess": _chess_status(*ga.in_chess()),
            "in_chess_next": _chess_status(*ga.in_chess_next()),
            "pieces": ga.pieces(),
            "pieces_value": ga.pieces_value(),
            "eliminated": ga.eliminated(),
            "eliminated_value": ga.eliminated_value(),
            "eliminations": ga.player_eliminations(),
            "vote_needed": ga.voting.needed(),
            "vote_results": ga.voting.votes(),
            "score": (
                ga.outcome_scores(endgame)
                if endgame is not None
                else {0: 0.0, 1: 0.0, 2: 0.0}
            ),
        }


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
        responses={406: "slog parsing error", 500: "Unexpected error"},
    )
    @jwt_required()
    @voteapi.response(200, "Success", vote_response)
    def post(self):
        state = VoteParser.parse_args()
        ga = _load_game_or_abort(voteapi, state.get("view_pid"), state.get("slog"))
        return {"slog": ga.draw_vote(state.get("vote"))}


@voteapi.route("/resign")
class ResignVote(Resource):
    @voteapi.expect(vote_payload, validate=True)
    @voteapi.doc(
        description="Vote for resign and return updated slog",
        security="jsonWebToken",
        responses={406: "slog parsing error", 500: "Unexpected error"},
    )
    @jwt_required()
    @voteapi.response(200, "Success", vote_response)
    def post(self):
        state = VoteParser.parse_args()
        ga = _load_game_or_abort(voteapi, state.get("view_pid"), state.get("slog"))
        return {"slog": ga.resignation_vote(state.get("vote"))}


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
            500: "Unexpected error",
        },
    )
    @jwt_required()
    @managerapi.response(200, "Success", board_response)
    @managerapi.expect(BoardParser)
    def get(self):
        args = BoardParser.parse_args()
        user = get_current_user()
        tb = (
            TriBoard.query.filter_by(id=args["id"])
            .filter(TriBoard.status.in_((GameStatus.ACTIVE, GameStatus.FINISHED)))
            .filter(TriBoard.for_player(user.id))
            .first()
        )
        if tb is None:
            managerapi.abort(404, message="Board not found")
        pid = tb.seat_of(user.id)
        slog = tb.slog or ""
        ga = _load_game_or_abort(managerapi, pid, slog)
        code_pid = args.get("view_pid")
        if code_pid is None or code_pid == pid:
            gid2hex = ga.gid2hex
        else:
            gid2hex = _load_game_or_abort(managerapi, code_pid, slog).gid2hex
        return {
            "id": tb.id,
            "player_0": tb.player_0.username,
            "player_1": tb.player_1.username,
            "player_2": tb.player_2.username,
            "slog": tb.slog,
            "view_pid": pid,
            "move_number": ga.move_number,
            "gid2code": [gid2hex[gid].pos.code for gid in range(len(gid2hex))],
        }

    @managerapi.doc(
        description="Update trichess board slog",
        security="jsonWebToken",
        responses={
            404: "Board not found",
            409: "Posted slog is in conflict with server one",
            500: "Unexpected error",
        },
    )
    @jwt_required()
    @managerapi.response(200, "Success")
    @managerapi.expect(board_payload, validate=True)
    def post(self):
        state = UpdateBoardParser.parse_args()
        user = get_current_user()
        tb = (
            db.session.query(TriBoard)
            # FOR NO KEY UPDATE: serialises moves on this board but
            # doesn't block the FK check of a Log row written about it
            # meanwhile (DBHandler uses its own connection).
            .with_for_update(key_share=True)
            .filter_by(status=GameStatus.ACTIVE, id=state.id)
            .filter(TriBoard.for_player(user.id))
            .first()
        )
        if tb is None:
            managerapi.abort(404, message="Board not found")
        ga, move_id = _apply_posted_slog(tb, user, state.slog)
        players = tb.players
        board_has_bot, notify_players = bot_notification_flags(players)
        endgame_kind = finalize_if_finished(
            tb,
            ga,
            players,
            board_has_bot,
            notify_players,
            actor_user=players[ga.on_move],
        )
        if endgame_kind is None and notify_players:
            _notify_next_player(tb, players[ga.on_move])
        logger.log(
            GAME,
            "Move end " + move_id,
            extra={"user_id": user.id, "board_id": tb.id},
        )
        _commit_move(tb, len(ga.slog))


def _apply_posted_slog(tb, user, posted):
    """Set *tb*'s slog to *posted* if it's one legal step by *user*, else
    abort with 409. Returns the new position and the move's log id."""
    ga = get_game(0, tb.slog)
    move_id = f"{ga.move_number:03d}"
    logger.log(
        GAME,
        "Move.str " + move_id,
        extra={"user_id": user.id, "board_id": tb.id},
    )
    new_slog = _accept_posted_slog(ga, posted, tb.seat_of(user.id))
    if new_slog is None:
        managerapi.abort(409, message="Posted slog is in conflict with server one")
    ga = get_game(0, new_slog)
    tb.slog = ga.slog
    return ga, move_id


def _notify_next_player(tb, player):
    if not player.is_bot:
        post_notification(
            player.username, f"It's your turn in game {tb.id}", "Your turn", tb.id
        )


def _commit_move(tb, slog_length):
    """Commit the move, ping the board's live viewers, and queue the next
    bot move if the game goes on."""
    db.session.commit()
    publish_board_move(tb.id, slog_length)
    if tb.status == GameStatus.ACTIVE:
        # finalize_if_finished just ran on this position
        maybe_trigger_bot(tb.id, finalize=False)


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
        responses={500: "Unexpected error"},
    )
    @jwt_required()
    @managerapi.response(200, "Success", games_fields)
    def get(self):
        user = get_current_user()
        own = TriBoard.query.filter_by(status=GameStatus.ACTIVE, owner_id=user.id).all()
        joined = (
            TriBoard.query.filter_by(status=GameStatus.ACTIVE)
            .filter(TriBoard.owner_id != user.id)
            .filter(TriBoard.for_player(user.id))
            .all()
        )
        return {
            "own": [_board_summary(tb, user.id) for tb in own],
            "joined": [_board_summary(tb, user.id) for tb in joined],
        }
