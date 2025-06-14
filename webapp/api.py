from typing import Optional

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Resource, fields, reqparse

from engine import GameAPI
from webapp import db
from webapp.models import TriBoard, User

blueprint = Blueprint("api", __name__)

api = Api(blueprint, version="1.0", title="TriChess API")

authorizations = {
    "jsonWebToken": {"type": "apiKey", "in": "header", "name": "Authorization"}
}

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
        responses={400: "slog parsing error", 404: "gid not found"},
    )
    @jwt_required()
    @moveapi.response(200, "Success", valid_response)
    def post(self):
        state = ValidMovesParser.parse_args()
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        gid = state.get("gid")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            moveapi.abort(400, message="slog parsing error")
        else:
            try:
                return {"targets": ga.valid_moves(gid)}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                moveapi.abort(404, message=f"Unexpected error {err}")


MakeMoveParser = reqparse.RequestParser()
MakeMoveParser.add_argument(name="slog", type=str, required=True, nullable=False)
MakeMoveParser.add_argument(name="view_pid", type=int, required=True, nullable=False)
MakeMoveParser.add_argument(name="gid", type=int, required=True, nullable=False)
MakeMoveParser.add_argument(name="tgid", type=int, required=True, nullable=False)
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
        responses={400: "slog parsing error", 404: "gid not found"},
    )
    @jwt_required()
    @moveapi.response(200, "Success", move_response)
    def post(self):
        state = MakeMoveParser.parse_args()
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        from_gid = state.get("gid")
        to_gid = state.get("tgid")
        new_piece = state.get("new_piece")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            moveapi.abort(400, message="slog parsing error")
        else:
            try:
                ga.make_move(from_gid, to_gid, new_piece=new_piece)
                return {"slog": ga.slog}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                moveapi.abort(404, message=f"Unexpected error {err}")


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
        "0": fields.List(fields.Nested(game_piece)),
        "1": fields.List(fields.Nested(game_piece)),
        "2": fields.List(fields.Nested(game_piece)),
    },
)

game_elimenated = api.model(
    "Game players pieces",
    {
        "0": fields.List(fields.String),
        "1": fields.List(fields.String),
        "2": fields.List(fields.String),
    },
)

game_response = api.model(
    "Game response",
    {
        "move_number": fields.Integer,
        "onmove": fields.Integer,
        "last_move": fields.Nested(last_move),
        "finished": fields.Boolean,
        "in_chess": fields.Integer,
        "king_pos": fields.Integer,
        "chess_by": fields.Nested(game_pieces),
        "pieces": fields.Nested(game_pieces),
        "eliminated": fields.Nested(game_elimenated),
    },
)


@gameapi.route("/info")
class GameInfo(Resource):
    @gameapi.expect(game_payload, validate=True)
    @gameapi.doc(
        description="Get information about game",
        security="jsonWebToken",
        responses={400: "slog parsing error", 404: "Unexpected error"},
    )
    @jwt_required()
    @gameapi.response(200, "Success", game_response)
    def post(self):
        state = GameInfoParser.parse_args()
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            gameapi.abort(400, message="slog parsing error")
        else:
            try:
                res = {}
                res["move_number"] = ga.move_number
                res["onmove"] = ga.on_move
                res["last_move"] = ga.last_move
                res["finished"] = not ga.move_possible()
                res["in_chess"], res["king_pos"], res["chess_by"] = ga.in_chess
                res["pieces"] = ga.pieces
                res["eliminated"] = ga.eliminated
                return res
            except Exception as err:
                gameapi.abort(404, message=f"Unexpected error {err}")


# manager API

managerapi = api.namespace(
    "manager", description="Games manager", authorizations=authorizations
)

BoardParser = reqparse.RequestParser()
BoardParser.add_argument(name="id", type=int, required=True, nullable=False)

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
    },
)


@managerapi.route("/board")
class GameBoard(Resource):
    @managerapi.doc(
        description="Get trichess board",
        params={"id": "Board ID"},
        security="jsonWebToken",
        responses={400: "Board not found", 404: "Unexpected error"},
    )
    @jwt_required()
    @managerapi.response(200, "Success", board_response)
    @managerapi.expect(BoardParser)
    def get(self):
        id = BoardParser.parse_args()["id"]
        res = {}
        username = get_jwt_identity()
        try:
            user = User.query.filter_by(username=username).first()
            user_in = db.or_(
                TriBoard.player_0_id == user.id,
                TriBoard.player_1_id == user.id,
                TriBoard.player_2_id == user.id,
            )
            tb = TriBoard.query.filter_by(status=1, id=id).filter(user_in).first()
        except Exception as err:
            managerapi.abort(404, message=f"Unexpected error {err}")
        else:
            try:
                pid = {
                    tb.player_0.username: 0,
                    tb.player_1.username: 1,
                    tb.player_2.username: 2,
                }
                res["id"] = tb.id
                res["player_0"] = tb.player_0.username
                res["player_1"] = tb.player_1.username
                res["player_2"] = tb.player_2.username
                res["slog"] = tb.slog
                res["view_pid"] = pid[username]
                return res
            except Exception:
                managerapi.abort(400, message="Board not found")

    @managerapi.doc(
        description="Update trichess board slog",
        security="jsonWebToken",
        responses={
            400: "Board not found",
            404: "Unexpected error",
            409: "Posted slog is in conflict with server one",
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
            user_in = db.or_(
                TriBoard.player_0_id == user.id,
                TriBoard.player_1_id == user.id,
                TriBoard.player_2_id == user.id,
            )
            tb = TriBoard.query.filter_by(status=1, id=state.id).filter(user_in).first()
        except Exception as err:
            managerapi.abort(404, message=f"Unexpected error {err}")
        else:
            if tb:
                try:
                    ga1 = GameAPI()
                    ga1.replay_from_slog(tb.slog)
                    ga2 = GameAPI()
                    ga2.replay_from_slog(state.slog)
                    pid = {
                        tb.player_0.username: 0,
                        tb.player_1.username: 1,
                        tb.player_2.username: 2,
                    }
                    poster = ga1.on_move == pid[username]
                    oneadded = ga2.move_number - ga1.move_number == 1
                    same = ga2.slog.startswith(ga1.slog)
                    if poster & oneadded & same:
                        tb.slog = state.slog
                        db.session.commit()
                    else:
                        managerapi.abort(
                            409, message="Posted slog is in conflict with server one"
                        )
                except Exception as err:
                    managerapi.abort(404, message=f"Unexpected error {err}")
            else:
                managerapi.abort(400, message="Board not found")


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
            user_in = db.or_(
                TriBoard.player_0_id == user.id,
                TriBoard.player_1_id == user.id,
                TriBoard.player_2_id == user.id,
            )
            own = TriBoard.query.filter_by(status=1, owner_id=user.id).all()
            joined = (
                TriBoard.query.filter_by(status=1)
                .filter(TriBoard.owner_id != user.id)
                .filter(user_in)
                .all()
            )
        except Exception as err:
            managerapi.abort(404, message=f"Unexpected error {err}")
        else:
            try:
                dt = []
                for tb in own:
                    ga = GameAPI()
                    ga.replay_from_slog(tb.slog)
                    seats = {
                        tb.player_0.username: 0,
                        tb.player_1.username: 1,
                        tb.player_2.username: 2,
                    }
                    dt.append(
                        {
                            "id": tb.id,
                            "player_0": tb.player_0.username,
                            "player_1": tb.player_1.username,
                            "player_2": tb.player_2.username,
                            "my_turn": seats[username] == ga.on_move,
                        }
                    )
                res["own"] = dt
                dt = []
                for tb in joined:
                    ga = GameAPI()
                    ga.replay_from_slog(tb.slog)
                    seats = {
                        tb.player_0.username: 0,
                        tb.player_1.username: 1,
                        tb.player_2.username: 2,
                    }
                    dt.append(
                        {
                            "id": tb.id,
                            "player_0": tb.player_0.username,
                            "player_1": tb.player_1.username,
                            "player_2": tb.player_2.username,
                            "my_turn": seats[username] == ga.on_move,
                        }
                    )
                res["joined"] = dt
                return res
            except Exception as err:
                managerapi.abort(404, message=f"Unexpected error {err}")
