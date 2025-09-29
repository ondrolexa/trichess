const gid2hex = {};
const gid2high = {};
const gid2valid = {};
const gid2attack = {};
const gid2piece = {};
const pos2gid = {};
const p0el = {};
const p1el = {};
const p2el = {};
const player_names = { 0: "", 1: "", 2: "" };
const player_names_font = { 0: "", 1: "", 2: "" };
var movelabel_text = "";
const player_names_color = { 0: "#ffffff", 1: "#ffffff", 2: "#ffffff" };
const pieces_symbols = { P: "♟", N: "♞", B: "♝", R: "♜", Q: "♛", K: "♚" };
var stageWidth = 20;
var stageHeight = 18;
var movestage = -1;
var target = -1;
var current = -1;
var ready = false;
var targets = new Set();
var promotions = new Set();
var lastmove = { from: -1, to: -1 };
const slogtext = document.getElementById("log");
const submit = document.getElementById("submitGame");
const submitText = document.getElementById("submitText");
const loader = document.getElementById("loader");
const backmove = document.getElementById("backMove");
const forwardmove = document.getElementById("forwardMove");
const modalPiece = new bootstrap.Modal(document.getElementById("selectPiece"));
var seat = {};
var slog = "";
var server_slog = "";
var game_slog = "";
var on_move = false;
var view_pid = 0;

const api_url = `${window.location.protocol}//${window.location.host}`;

var stage = new Konva.Stage({
  container: "canvas",
  width: stageWidth,
  height: stageHeight,
  draggable: true,
  offset: {
    x: -stageWidth / 2,
    y: -stageHeight / 2 + 1,
  },
});

const background = new Konva.Rect({
  x: 0,
  y: 0,
  width: stage.width(),
  height: stage.height(),
  offset: {
    x: -stage.offsetX(),
    y: -stage.offsetY(),
  },
  fill: theme["canvas"]["background"],
  listening: false,
});

stage.on("wheel", function (e) {
  e.evt.preventDefault();
  var oldScale = stage.scaleX();

  var mousePointTo = {
    x: stage.getPointerPosition().x / oldScale - stage.x() / oldScale,
    y: stage.getPointerPosition().y / oldScale - stage.y() / oldScale,
  };

  var newScale = e.evt.deltaY > 0 ? oldScale * 0.95 : oldScale / 0.95;
  stage.scale({ x: newScale, y: newScale });

  var newPos = {
    x: -(mousePointTo.x - stage.getPointerPosition().x / newScale) * newScale,
    y: -(mousePointTo.y - stage.getPointerPosition().y / newScale) * newScale,
  };
  stage.position(newPos);
  stage.batchDraw();
});

var movelabel = new Konva.Shape({
  x: -7,
  y: 4,
  width: 3.5,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = theme["canvas"]["font-family"];
    context.fillStyle = theme["canvas"]["info"];
    context.textAlign = "center";
    var lines = movelabel_text.split("\n");
    for (var i = 0; i < lines.length; i++)
      context.fillText(lines[i], 0, i * 10);
  },
});

var p0name = new Konva.Shape({
  x: 0,
  y: 7.4,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = player_names_font[0];
    context.fillStyle = player_names_color[0];
    context.textAlign = "center";
    context.fillText(player_names[0], 0, 0);
  },
});

var p1name = new Konva.Shape({
  x: -9.2,
  y: -6.9,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = player_names_font[1];
    context.fillStyle = player_names_color[1];
    context.textAlign = "left";
    context.fillText(player_names[1], 0, 0);
  },
});

var p2name = new Konva.Shape({
  x: 9.2,
  y: -6.9,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = player_names_font[2];
    context.fillStyle = player_names_color[2];
    context.textAlign = "right";
    context.fillText(player_names[2], 0, 0);
  },
});

const gameover = new Konva.Group({
  visible: false,
});
const gameover_bg = new Konva.Rect({
  x: -8,
  y: -3,
  width: 16,
  height: 7,
  opacity: 0.65,
  fill: theme["canvas"]["background"],
  listening: false,
});
var gameover_text = new Konva.Text({
  x: -7,
  y: -2,
  text: "GAME OVER",
  fontFamily: theme["canvas"]["font-family"],
  fill: theme["canvas"]["game_over"],
  fontSize: 2.5,
  fontStyle: "bold",
  align: "center",
  verticalAlign: "middle",
  opacity: 0.65,
  listening: false,
});
gameover.add(gameover_bg);
gameover.add(gameover_text);

var line_dash = [0.2, 0.1];
var line_width = 0.04;

var qline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: line_width,
  dash: line_dash,
  visible: false,
  listening: false,
});

var rline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: line_width,
  dash: line_dash,
  visible: false,
  listening: false,
});

var sline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: line_width,
  dash: line_dash,
  visible: false,
  listening: false,
});

// responsive canvas
function fitStageIntoDiv() {
  const container = document.querySelector("#canvas");
  const containerWidth = container.offsetWidth;
  const containerHeight = container.offsetHeight;
  const scale = Math.min(
    containerWidth / stageWidth,
    containerHeight / stageHeight,
  );
  stage.width(containerWidth);
  if (containerWidth >= 768) {
    stage.height(containerHeight);
  } else {
    stage.height(stageHeight * scale);
  }
  stage.offsetX(
    -stageWidth / 2 - (containerWidth / scale - stageWidth) / 2 - 0.5,
  );
  stage.scale({ x: scale, y: scale });
  stage.position({ x: -20, y: 0 });
  stage.draw();
}

function createHexPatch(gid, xy, color, qr) {
  let hex = new Konva.RegularPolygon({
    id: gid,
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: Math.sqrt(1 / 3),
    fill: color,
    stroke: "black",
    strokeWidth: 0.05,
    q: qr[0],
    r: qr[1],
  });
  return hex;
}

function createHexHigh(xy) {
  let hex = new Konva.RegularPolygon({
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: Math.sqrt(1 / 3) - 0.075,
    fillEnabled: false,
    stroke: "black",
    strokeWidth: 0.08,
    visible: false,
    listening: false,
  });
  return hex;
}

function createHexValid(xy) {
  let hex = new Konva.Circle({
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: 0.25,
    fillEnabled: false,
    stroke: "black",
    strokeWidth: 0.07,
    visible: false,
    listening: false,
  });
  return hex;
}

function createHexAttack(xy) {
  let hex = new Konva.Shape({
    x: xy[0],
    y: xy[1],
    sceneFunc: function (context, shape) {
      context.beginPath();
      context.moveTo(-0.3, -0.3);
      context.lineTo(0.3, 0.3);
      context.moveTo(-0.3, 0.3);
      context.lineTo(0.3, -0.3);
      context.fillStrokeShape(shape);
    },
    fillEnabled: false,
    stroke: "black",
    strokeWidth: 0.07,
    visible: false,
    listening: false,
  });
  return hex;
}

function createHexLabel(gid, xy, color, data) {
  let label = new Konva.Path({
    id: gid,
    x: xy[0],
    y: xy[1],
    data: data,
    fill: color,
    lineCap: "round",
    lineJoin: "round",
    scale: {
      x: 0.075,
      y: 0.075,
    },
    name: "piece",
    listening: false,
  });
  return label;
}

function manageMove(gid) {
  if (ready) {
    current = gid;
    if (movestage == -1) {
      setCoordHints(gid);
      validMoves(gid);
    } else {
      if (targets.has(gid)) {
        if (promotions.has(gid)) {
          target = gid;
          modalPiece.toggle();
        } else {
          current = -1;
          makeMove(movestage, gid);
        }
      } else {
        if (gid == movestage) {
          current = -1;
          cleanMove();
          cleanHigh();
        } else {
          cleanMove();
          setCoordHints(gid);
          validMoves(gid);
        }
      }
    }
  }
}

function promotePiece(label) {
  modalPiece.toggle();
  makeMove(movestage, target, label);
}

function cleanHigh() {
  for (let gid = 0; gid < 169; gid++) {
    gid2high[gid].visible(false);
    gid2valid[gid].visible(false);
    gid2attack[gid].visible(false);
  }
  qline.visible(false);
  rline.visible(false);
  sline.visible(false);
}

function backMove() {
  if (slog.length > 0) {
    slog = slog.slice(0, -4);
    movestage = -1;
    cleanHigh();
    gameInfo(false, true);
    ready = true;
  }
}

function forwardMove() {
  if (slog.length < game_slog.length) {
    slog = game_slog.slice(0, slog.length + 4);
    movestage = -1;
    cleanHigh();
    gameInfo(false, true);
    ready = true;
  }
}

function boardReset() {
  cleanHigh();
  stage.destroyChildren();
  boardInfo();
}

function cleanMove() {
  gid2high[movestage].visible(false);
  for (let tgid of targets) {
    gid2high[tgid].visible(false);
    gid2valid[tgid].visible(false);
    gid2attack[tgid].visible(false);
  }
  if (target != -1) {
    gid2piece[target].data(gid2piece[movestage].data());
    gid2piece[target].fill(gid2piece[movestage].fill());
    gid2piece[movestage].data("");
    gid2piece[movestage].fill("#ffffff");
  }
  targets.clear();
  promotions.clear();
  target = -1;
  movestage = -1;
  gameInfo(false, true);
  ready = true;
}

function drawPieces(pieces) {
  for (let gid = 0; gid <= 168; gid++) {
    gid2piece[gid].data("");
  }
  for (let pid in pieces) {
    for (let pcs in pieces[pid]) {
      gid2piece[pieces[pid][pcs].gid].data(
        pieces_paths["pieces"][pieces[pid][pcs].piece],
      );
      gid2piece[pieces[pid][pcs].gid].fill(theme["pieces"]["color"][pid]);
    }
  }
}

function updateStats(eliminated, value, move_number) {
  player_names[0] = `${seat[0]} (${value[(0 + view_pid) % 3]})`;
  el = eliminated[(0 + view_pid) % 3];
  for (let pcs in el) {
    p0el[pcs].data(pieces_paths["pieces"][el[pcs]]);
  }
  for (let i = el.length; i < 23; i++) {
    p0el[i].data("");
  }

  player_names[1] = `${seat[1]} (${value[(1 + view_pid) % 3]})`;
  el = eliminated[(1 + view_pid) % 3];
  for (let pcs in el) {
    p1el[pcs].data(pieces_paths["pieces"][el[pcs]]);
  }
  for (let i = el.length; i < 23; i++) {
    p1el[i].data("");
  }

  player_names[2] = `${seat[2]} (${value[(2 + view_pid) % 3]})`;
  el = eliminated[(2 + view_pid) % 3];
  for (let pcs in el) {
    p2el[pcs].data(pieces_paths["pieces"][el[pcs]]);
  }
  for (let i = el.length; i < 23; i++) {
    p2el[i].data("");
  }

  slogtext.innerHTML = slog;
  movelabel_text = `Move\n${move_number}/${game_slog.length / 4}`;
}

function setCoordHints(gid) {
  let q = gid2hex[gid].getAttr("q");
  let r = gid2hex[gid].getAttr("r");
  gid_l11 = pos2gid[[Math.max(-7 - r, -7), r]];
  gid_l12 = pos2gid[[Math.min(7 - r, 7), r]];
  gid_l21 = pos2gid[[q, Math.max(-7 - q, -7)]];
  gid_l22 = pos2gid[[q, Math.min(7 - q, 7)]];
  gid_l31 = pos2gid[[q + Math.min(7 - q, r + 7), r - Math.min(7 - q, r + 7)]];
  gid_l32 = pos2gid[[q - Math.min(q + 7, 7 - r), r + Math.min(q + 7, 7 - r)]];
  qline.points([
    gid2hex[gid_l11].x(),
    gid2hex[gid_l11].y(),
    gid2hex[gid_l12].x(),
    gid2hex[gid_l12].y(),
  ]);
  rline.points([
    gid2hex[gid_l21].x(),
    gid2hex[gid_l21].y(),
    gid2hex[gid_l22].x(),
    gid2hex[gid_l22].y(),
  ]);
  sline.points([
    gid2hex[gid_l31].x(),
    gid2hex[gid_l31].y(),
    gid2hex[gid_l32].x(),
    gid2hex[gid_l32].y(),
  ]);
  qline.visible(true);
  rline.visible(true);
  sline.visible(true);
}

function validMoves(gid) {
  const url = `${api_url}/api/v1/move/valid`;
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;

  fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({ slog: slog, view_pid: view_pid, gid: gid }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      gid2high[gid].visible(true);
      gid2high[gid].stroke(theme["board"]["selection"]);
      for (let i in data.targets) {
        let tgid = data.targets[i].tgid;
        targets.add(tgid);
        if (data.targets[i].kind == "attack") {
          gid2attack[tgid].stroke(theme["board"]["attack_move"]);
          gid2attack[tgid].visible(true);
        } else {
          gid2valid[tgid].stroke(theme["board"]["valid_move"]);
          gid2valid[tgid].visible(true);
        }
        if (data.targets[i].promotion) {
          promotions.add(tgid);
        }
      }
      movestage = gid;
      ready = true;
    })
    .catch((error) => {
      alert("validMoves Error:", error);
    });
}

function makeMove(gid, tgid, new_piece = "") {
  const url = `${api_url}/api/v1/move/make`;
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;

  fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({
      slog: slog,
      view_pid: view_pid,
      gid: gid,
      tgid: tgid,
      new_piece: new_piece,
    }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      if (new_piece != "") {
        gid2piece[gid].data(pieces_paths["pieces"][new_piece]);
      }
      slog = data.slog;
      if (slog.slice(0, -4) == game_slog.slice(0, slog.length - 4)) {
        game_slog = slog;
      }
      target = tgid;
      cleanHigh();
      cleanMove();
    })
    .catch((error) => {
      alert("makeMove Error:", error);
    });
}

function gameInfo(init = false, redraw = false) {
  const url = `${api_url}/api/v1/game/info`;
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;

  fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({ slog: slog, view_pid: view_pid }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      if (init) {
        on_move = data.onmove == view_pid;
      }
      if (redraw) {
        drawPieces(data.pieces);
      }

      player_names_font[0] =
        "400 10px " + theme["canvas"]["font-family"] + ", sans-serif";
      player_names_color[0] = theme["canvas"]["name"];
      player_names_font[1] =
        "400 10px " + theme["canvas"]["font-family"] + ", sans-serif";
      player_names_color[1] = theme["canvas"]["name"];
      player_names_font[2] =
        "400 10px " + theme["canvas"]["font-family"] + ", sans-serif";
      player_names_color[2] = theme["canvas"]["name"];
      if ((data.onmove + 3 - view_pid) % 3 == 0) {
        player_names_font[0] =
          "900 10px " + theme["canvas"]["font-family"] + ", sans-serif";
        if (data.in_chess) {
          player_names_color[0] = theme["canvas"]["name_inchess"];
        } else {
          player_names_color[0] = theme["canvas"]["name_onmove"];
        }
      } else if ((data.onmove + 3 - view_pid) % 3 == 1) {
        player_names_font[1] =
          "900 10px " + theme["canvas"]["font-family"] + ", sans-serif";
        if (data.in_chess) {
          player_names_color[1] = theme["canvas"]["name_inchess"];
        } else {
          player_names_color[1] = theme["canvas"]["name_onmove"];
        }
      } else {
        player_names_font[2] =
          "900 10px " + theme["canvas"]["font-family"] + ", sans-serif";
        if (data.in_chess) {
          player_names_color[2] = theme["canvas"]["name_inchess"];
        } else {
          player_names_color[2] = theme["canvas"]["name_onmove"];
        }
      }
      if (data.in_chess) {
        gid2high[data.king_pos].visible(true);
        gid2high[data.king_pos].stroke("red");
        for (var player in data.chess_by) {
          for (var pcs in data.chess_by[player]) {
            gid2high[data.chess_by[player][pcs].gid].visible(true);
            gid2high[data.chess_by[player][pcs].gid].stroke("green");
          }
        }
      }
      updateStats(data.eliminated, data.eliminated_value, data.move_number);
      if (slog.slice(0, -4) == server_slog && on_move) {
        submit.disabled = false;
        submit.className = "btn btn-danger mb-2 col-12";
      } else {
        submit.disabled = true;
        submit.className = "btn btn-secondary mb-2 col-12";
      }
      if (slog.length < game_slog.length) {
        forwardmove.disabled = false;
        forwardmove.className = "btn btn-primary mb-2 col-12";
      } else {
        forwardmove.disabled = true;
        forwardmove.className = "btn btn-secondary mb-2 col-12";
      }
      if (slog.length > 0) {
        backmove.disabled = false;
        backmove.className = "btn btn-primary mb-2 col-12";
      } else {
        backmove.disabled = true;
        backmove.className = "btn btn-secondary mb-2 col-12";
      }
      if (data.finished) {
        gameover_text.text(
          "GAME OVER\n" + seat[(data.onmove + 3 - view_pid) % 3] + " lost",
        );
        gameover.visible(true);
      } else {
        gameover.visible(false);
      }

      if (data.last_move != null) {
        if (lastmove["from"] != -1) {
          gid2high[lastmove["from"]].visible(false);
        }
        lastmove["from"] = data.last_move["from"];
        gid2high[lastmove["from"]].visible(true);
        if (current == lastmove["from"]) {
          gid2high[lastmove["from"]].stroke(theme["board"]["selection"]);
        } else {
          gid2high[lastmove["from"]].stroke(theme["board"]["last_move"]);
        }
        if (lastmove["to"] != -1) {
          gid2high[lastmove["to"]].visible(false);
        }
        lastmove["to"] = data.last_move["to"];
        gid2high[lastmove["to"]].visible(true);
        if (current == lastmove["to"]) {
          gid2high[lastmove["to"]].stroke(theme["board"]["selection"]);
        } else {
          gid2high[lastmove["to"]].stroke(theme["board"]["last_move"]);
        }
      }
    })
    .catch((error) => {
      window.location.reload(true);
      // alert("gameInfo Error:", error);
    });
}

function boardInfo() {
  const url = `${api_url}/api/v1/manager/board?id=` + id.toString();
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;

  fetch(url, {
    method: "GET",
    headers: headers,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      const seats = [data.player_0, data.player_1, data.player_2];
      view_pid = data.view_pid;
      seat[0] = seats[(0 + view_pid) % 3];
      seat[1] = seats[(1 + view_pid) % 3];
      seat[2] = seats[(2 + view_pid) % 3];
      slog = data.slog;
      server_slog = data.slog;
      game_slog = data.slog;
      gameInfo(true, true);
      var board_layer = new Konva.Layer();
      var interactive_layer = new Konva.Layer();
      var pieces_layer = new Konva.Layer();
      var top_layer = new Konva.Layer();
      stage.add(board_layer);
      stage.add(interactive_layer);
      stage.add(pieces_layer);
      stage.add(top_layer);

      // Create mappings
      let gid = 0;
      for (let r = -7; r <= 7; r++) {
        for (let q = -7; q <= 7; q++) {
          const s = -q - r;
          if (s >= -7 && s <= 7) {
            const x = q + 0.5 * r;
            const y = (r * Math.sqrt(3)) / 2;
            const colorid = (((2 * q + r) % 3) + 3) % 3;
            pos2gid[[q, r]] = gid;
            gid2hex[gid] = createHexPatch(
              gid,
              [x, y],
              theme["board"]["hex_color"][colorid],
              [q, r],
            );
            gid2high[gid] = createHexHigh([x, y]);
            gid2valid[gid] = createHexValid([x, y]);
            gid2attack[gid] = createHexAttack([x, y]);
            gid2piece[gid] = createHexLabel(gid, [x, y], "#ffffff", "");
            gid++;
          }
        }
      }

      // Create mappings for eliminated
      let q0 = [
        9, 8, 8, 7, 8, 7, 6, 7, 6, 5, 7, 6, 5, 4, 6, 5, 4, 3, 6, 5, 4, 3, 2,
      ];
      let r0 = [
        1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7, 7,
      ];
      let q1 = [
        -6, -5, -4, -3, -2, -6, -5, -4, -3, -7, -6, -5, -4, -7, -6, -5, -8, -7,
        -6, -8, -7, -9, -8,
      ];
      let r1 = [
        -7, -7, -7, -7, -7, -6, -6, -6, -6, -5, -5, -5, -5, -4, -4, -4, -3, -3,
        -3, -2, -2, -1, -1,
      ];
      let q2 = [
        13, 12, 11, 10, 9, 12, 11, 10, 9, 12, 11, 10, 9, 11, 10, 9, 11, 10, 9,
        10, 9, 10, 9,
      ];
      let r2 = [
        -7, -7, -7, -7, -7, -6, -6, -6, -6, -5, -5, -5, -5, -4, -4, -4, -3, -3,
        -3, -2, -2, -1, -1,
      ];
      for (let i = 0; i < 23; i++) {
        p0el[i] = createHexLabel(
          0,
          [q0[i] + 0.5 * r0[i] - 0.5, (r0[i] * Math.sqrt(3)) / 2],
          theme["pieces"]["color"][(0 + view_pid) % 3],
          "",
        );
        pieces_layer.add(p0el[i]);
        p1el[i] = createHexLabel(
          0,
          [q1[i] + 0.5 * r1[i] + 0.5, (r1[i] * Math.sqrt(3)) / 2],
          theme["pieces"]["color"][(1 + view_pid) % 3],
          "",
        );
        pieces_layer.add(p1el[i]);
        p2el[i] = createHexLabel(
          0,
          [q2[i] + 0.5 * r2[i] - 0.5, (r2[i] * Math.sqrt(3)) / 2],
          theme["pieces"]["color"][(2 + view_pid) % 3],
          "",
        );
        pieces_layer.add(p2el[i]);
      }

      board_layer.add(background);
      // Add board hexes
      for (let gid = 0; gid <= 168; gid++) {
        board_layer.add(gid2hex[gid]);
        pieces_layer.add(gid2piece[gid]);
        interactive_layer.add(gid2high[gid]);
        interactive_layer.add(gid2valid[gid]);
        pieces_layer.add(gid2attack[gid]);
      }

      pieces_layer.add(movelabel);
      pieces_layer.add(p0name);
      pieces_layer.add(p1name);
      pieces_layer.add(p2name);

      // game over
      top_layer.add(gameover);
      // lines
      interactive_layer.add(qline);
      interactive_layer.add(rline);
      interactive_layer.add(sline);

      board_layer.on("click tap", function (evt) {
        const shape = evt.target;
        manageMove(shape.id());
      });

      board_layer.draw();
      interactive_layer.draw();
      pieces_layer.draw();
      top_layer.draw();

      fitStageIntoDiv();
      submit.disabled = true;
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      ready = true;
    })
    .catch((error) => {
      alert("Error:", error);
    });
}

function boardSubmit() {
  const url = `${api_url}/api/v1/manager/board`;
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;
  submit.disabled = true;
  submit.className = "btn btn-secondary p-0 mb-0 col-12";
  submitText.innerHTML = "";
  loader.style.display = "inline-block";

  fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({ id: id, slog: slog }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
        submitText.innerHTML = "Submit";
        submit.className = "btn btn-secondary mb-2 col-12";
        loader.style.display = "none";
      }
      return response.json();
    })
    .then((data) => {
      server_slog = slog;
      on_move = false;
      ready = true;
      submitText.innerHTML = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
    })
    .catch((error) => {
      submitText.innerHTML = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      alert("Error:", error);
    });
}

window.addEventListener("resize", fitStageIntoDiv);

boardInfo();
