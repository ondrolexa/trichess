from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Resource, fields, reqparse
from sqlalchemy import and_, func
from sqlalchemy.orm import aliased

from engine import GameAPI
from webapp.main import db, post_notification
from webapp.models import Score, TriBoard, User

blueprint = Blueprint("api", __name__)

api = Api(blueprint, version="1.0", title="TriChess API")

authorizations = {
    "jsonWebToken": {"type": "apiKey", "in": "header", "name": "Authorization"}
}


# rating update
def recalculate_rating():
    # parameters
    K = 9
    L = 400

    S0 = aliased(Score)
    S1 = aliased(Score)
    S2 = aliased(Score)
    users = User.query.all()
    res = (
        db.session.query(
            TriBoard.player_0_id,
            func.ifnull(S0.score, 0),
            TriBoard.player_1_id,
            func.ifnull(S1.score, 0),
            TriBoard.player_2_id,
            func.ifnull(S2.score, 0),
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
        .filter(TriBoard.status == 2)
        .order_by(TriBoard.modified_at)
        .all()
    )

    # new ratings
    ratings = {}
    for u in users:
        ratings[u.id] = 500

    for p0id, p0s, p1id, p1s, p2id, p2s in res:
        p0q = 10 ** (ratings[p0id] / L)
        p1q = 10 ** (ratings[p1id] / L)
        p2q = 10 ** (ratings[p2id] / L)
        Q = p0q + p1q + p2q
        p0ex = p0q / Q
        p1ex = p1q / Q
        p2ex = p2q / Q
        ratings[p0id] += K * (p0s - p0ex)
        ratings[p1id] += K * (p1s - p1ex)
        ratings[p2id] += K * (p2s - p2ex)

    for u in users:
        u.rating = ratings[u.id]
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
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        gid = state.get("gid")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            moveapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"targets": ga.valid_moves(gid)}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                moveapi.abort(417, message=f"Unexpected error {err}")


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
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        from_gid = state.get("gid")
        to_gid = state.get("tgid")
        new_piece = state.get("new_piece")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            moveapi.abort(406, message="slog parsing error")
        else:
            try:
                print(from_gid, to_gid, new_piece)
                ga.make_move(from_gid, to_gid, new_piece=new_piece)
                return {"slog": ga.slog}
            except KeyError:
                moveapi.abort(404, message="gid not found")
            except Exception as err:
                moveapi.abort(417, message=f"Unexpected error {err}")


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
        0: fields.String(enum=["A", "D"]),
        1: fields.String(enum=["A", "D"]),
        2: fields.String(enum=["A", "D"]),
    },
)

game_response = api.model(
    "Game response",
    {
        "move_number": fields.Integer,
        "onmove": fields.Integer,
        "last_move": fields.Nested(last_move),
        "finished": fields.Boolean,
        "in_chess": fields.Boolean,
        "king_pos": fields.Integer,
        "chess_by": fields.Nested(game_pieces),
        "resignation": fields.Boolean,
        "draw": fields.Boolean,
        "pieces": fields.Nested(game_pieces),
        "pieces_value": fields.Nested(game_pieces_value),
        "eliminated": fields.Nested(game_eliminated),
        "eliminated_value": fields.Nested(game_pieces_value),
        "vote_draw_needed": fields.Boolean,
        "vote_resign_needed": fields.Boolean,
        "vote_results": fields.Nested(votes),
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
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            gameapi.abort(406, message="slog parsing error")
        else:
            try:
                res = {}
                res["move_number"] = ga.move_number
                res["onmove"] = ga.on_move
                res["last_move"] = ga.last_move
                res["finished"] = not ga.move_possible()
                res["in_chess"], res["king_pos"], res["chess_by"] = ga.in_chess()
                res["resignation"] = ga.resignation()
                res["draw"] = ga.draw()
                res["pieces"] = ga.pieces()
                res["pieces_value"] = ga.pieces_value()
                res["eliminated"] = ga.eliminated()
                res["eliminated_value"] = ga.eliminated_value()
                res["vote_needed"] = ga.voting.needed()
                res["vote_results"] = ga.voting.votes()
                return res
            except Exception as err:
                gameapi.abort(417, message=f"Unexpected error {err}")


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
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        vote = state.get("vote")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            voteapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"slog": ga.draw_vote(vote)}
            except Exception as err:
                voteapi.abort(417, message=f"Unexpected error {err}")


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
        ga = GameAPI(state.get("view_pid"))
        slog = state.get("slog")
        vote = state.get("vote")
        try:
            if slog:
                ga.replay_from_slog(slog)
        except Exception:
            voteapi.abort(406, message="slog parsing error")
        else:
            try:
                return {"slog": ga.resignation_vote(vote)}
            except Exception as err:
                voteapi.abort(417, message=f"Unexpected error {err}")


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
        "move_number": fields.Integer,
    },
)


@managerapi.route("/board")
class GameBoard(Resource):
    @managerapi.doc(
        description="Get trichess board",
        params={"id": "Board ID"},
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
            managerapi.abort(417, message=f"Unexpected error {err}")
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
                ga = GameAPI(pid[username])
                try:
                    if tb.slog:
                        ga.replay_from_slog(tb.slog)
                        res["move_number"] = ga.move_number
                    else:
                        res["move_number"] = 0
                except Exception:
                    gameapi.abort(406, message="slog parsing error")
                return res
            except Exception:
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
            user_in = db.or_(
                TriBoard.player_0_id == user.id,
                TriBoard.player_1_id == user.id,
                TriBoard.player_2_id == user.id,
            )
            tb = TriBoard.query.filter_by(status=1, id=state.id).filter(user_in).first()
        except Exception as err:
            managerapi.abort(417, message=f"Unexpected error {err}")
        else:
            if tb:
                try:
                    ga1 = GameAPI(0)
                    ga1.replay_from_slog(tb.slog)
                    ga2 = GameAPI(0)
                    ga2.replay_from_slog(state.slog)
                    pid = {
                        tb.player_0.username: 0,
                        tb.player_1.username: 1,
                        tb.player_2.username: 2,
                    }
                    players = {
                        0: tb.player_0,
                        1: tb.player_1,
                        2: tb.player_2,
                    }
                    poster = ga1.on_move == pid[username]
                    voting = ga1.voting.active() | ga2.voting.active()
                    oneadded = ga2.move_number - ga1.move_number == 1
                    same = ga2.slog.startswith(ga1.slog)
                    if poster & ((oneadded & same) | voting):
                        tb.slog = ga2.slog
                        user = User.query.filter_by(
                            username=players[ga2.on_move].username
                        ).first()
                        if not ga2.move_possible():
                            # Game finshed do all needed
                            tb.status = 2
                            in_chess, gid, who = ga2.in_chess()
                            if ga2.draw():
                                for uid in players:
                                    new_score = Score(
                                        board_id=tb.id,
                                        player_id=players[uid].id,
                                        score=2.0 / 3,
                                    )
                                    db.session.add(new_score)
                                    # notify
                                    post_notification(
                                        players[uid].username,
                                        f"Draw agreed in game {state.id}",
                                        "Game over",
                                        state.id,
                                        user.board,
                                    )
                            elif ga2.resignation():
                                resigned = ga2.voting.results(kind="resign")
                                uid = set([0, 1, 2]).difference(resigned).pop()
                                new_score = Score(
                                    board_id=tb.id,
                                    player_id=players[uid].id,
                                    score=2.0,
                                )
                                db.session.add(new_score)
                                # notify
                                post_notification(
                                    players[uid].username,
                                    f"You win in game {state.id} by resignation",
                                    "Game over",
                                    state.id,
                                    user.board,
                                )
                                for uid in resigned:
                                    post_notification(
                                        players[uid].username,
                                        f"You lost in game {state.id} by resignation",
                                        "Game over",
                                        state.id,
                                        user.board,
                                    )
                            elif in_chess:
                                tot = [len(p) for p in who.values()]
                                for uid, v in enumerate(tot):
                                    score = v * 2 / sum(tot)
                                    if score > 0:
                                        new_score = Score(
                                            board_id=tb.id,
                                            player_id=players[uid].id,
                                            score=score,
                                        )
                                        db.session.add(new_score)
                                        post_notification(
                                            players[uid].username,
                                            f"{players[ga2.on_move].username} lost in game {state.id}. Your score is {score:g}",
                                            "Game over",
                                            state.id,
                                            user.board,
                                        )
                                # notify
                                post_notification(
                                    players[ga2.on_move].username,
                                    f"You lost in game {state.id}",
                                    "Game over",
                                    state.id,
                                    user.board,
                                )
                            else:
                                for uid in players:
                                    new_score = Score(
                                        board_id=tb.id,
                                        player_id=players[uid].id,
                                        score=2.0 / 3,
                                    )
                                    db.session.add(new_score)
                                    post_notification(
                                        players[uid].username,
                                        f"The game {state.id} ended in a stalemate",
                                        "Game over",
                                        state.id,
                                        user.board,
                                    )
                        else:
                            # notify next player
                            post_notification(
                                players[ga2.on_move].username,
                                f"It's your turn in game {state.id}",
                                "Your turn",
                                state.id,
                                user.board,
                            )
                        db.session.commit()
                        recalculate_rating()
                    else:
                        managerapi.abort(
                            409, message="Posted slog is in conflict with server one"
                        )
                except Exception as err:
                    if hasattr(err, "message"):
                        print(err.message)
                    else:
                        print(err)
                    managerapi.abort(417, message=f"Unexpected error {err}")
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
                    ga = GameAPI(0)
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
                    ga = GameAPI(0)
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
