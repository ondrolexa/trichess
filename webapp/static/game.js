const HEX_COLORS = ["#a8baf0", "#f0b6a8", "#d1f0a8"];
const PIECES_COLOR = ["#000599", "#B33900", "#1D6600"];
const PIECES = { P: "♟", N: "♞", B: "♝", R: "♜", Q: "♛", K: "♚" };
const gid2xy = {};
const gid2color = {};
const gid2hex = {};
const gid2high = {};
const gid2piece = {};

var stageWidth = 20;
var stageHeight = 15;
var movestage = -1;
var target = -1;
var ready = false;
var targets = new Set();
var promotions = new Set();
var lastmove = { from: -1, to: -1 };
var slogtext = document.getElementById("log");
var submit = document.getElementById("submitGame");
var modalPiece = new bootstrap.Modal(document.getElementById("selectPiece"));
const hostname = "trichess.mykuna.eu"; //new URL(window.location.href).hostname;
const protocol = "https:"; //window.location.protocol;

var seat_0 = "";
var seat_1 = "";
var seat_2 = "";
var slog = "";
var server_slog = "";
var game_slog = "";
var on_move = false;
var view_pid = 0;

var stage = new Konva.Stage({
  container: "canvas",
  width: stageWidth,
  height: stageHeight,
  draggable: true,
  offset: {
    x: -stageWidth / 2 + 1,
    y: -7,
  },
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

var movelabel = new Konva.Text({
  x: -12,
  y: 5.75,
  text: "",
  fontSize: 0.6,
  align: "right",
  width: 6,
  listening: false,
});
var p0name = new Konva.Text({
  x: 4.5,
  y: 5.75,
  text: "",
  fontSize: 0.6,
  align: "left",
  width: 6,
  listening: false,
});
var p0el = new Konva.Text({
  x: 6.5,
  y: 1.5,
  text: "",
  fontSize: 0.7,
  width: 2.5,
  align: "center",
  listening: false,
});
var p1name = new Konva.Text({
  x: -10.3,
  y: -6.5,
  text: "",
  fontSize: 0.6,
  align: "right",
  width: 6,
  listening: false,
});
var p1el = new Konva.Text({
  x: -9,
  y: -6.5,
  text: "",
  fontSize: 0.7,
  width: 2.5,
  align: "center",
  listening: false,
});
var p2name = new Konva.Text({
  x: 4.5,
  y: -6.5,
  text: "",
  fontSize: 0.6,
  align: "left",
  width: 6,
  listening: false,
});
var p2el = new Konva.Text({
  x: 6.5,
  y: -6.5,
  text: "",
  fontSize: 0.7,
  width: 2.5,
  align: "center",
  listening: false,
});

// responsive canvas
function fitStageIntoDiv() {
  const container = document.querySelector("#canvas");
  const containerWidth = container.offsetWidth;
  const scale = containerWidth / stageWidth;
  stage.width(stageWidth * scale);
  stage.height((3 * stageWidth * scale) / 4);
  stage.scale({ x: scale, y: scale });
  stage.position({ x: 0, y: 0 });
  stage.draw();
}

function createHexPatch(gid, xy, color) {
  let hex = new Konva.RegularPolygon({
    id: gid,
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: Math.sqrt(1 / 3),
    fill: color,
    stroke: "black",
    strokeWidth: 0.05,
  });
  return hex;
}

function createHexHigh(xy) {
  let hex = new Konva.RegularPolygon({
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: 0.45,
    fillEnabled: false,
    stroke: "black",
    strokeWidth: 0.07,
    visible: false,
    listening: false,
  });
  return hex;
}

function createHexLabel(gid, xy, color, text) {
  let label = new Konva.Text({
    id: gid,
    x: xy[0] - 0.36,
    y: xy[1] - 0.4,
    //fontFamily: "Calibri",
    fontSize: 0.8,
    text: text,
    fill: color,
    align: "center",
    verticalAlign: "middle",
    name: "piece",
  });
  return label;
}

function manageMove(gid) {
  if (ready) {
    if (movestage == -1) {
      validMoves(gid);
    } else {
      if (targets.has(gid)) {
        if (promotions.has(gid)) {
          target = gid;
          modalPiece.toggle();
        } else {
          makeMove(movestage, gid);
        }
      } else {
        if (gid == movestage) {
          cleanMove();
        } else {
          cleanMove();
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
  }
}

function backMove() {
  if (slog.length > 0) {
    slog = slog.slice(0, -4);
    movestage = -1;
    cleanHigh();
    gameInfo(true);
    ready = true;
  }
}

function forwardMove() {
  if (slog.length < game_slog.length) {
    slog = game_slog.slice(0, slog.length + 4);
    movestage = -1;
    cleanHigh();
    gameInfo(true);
    ready = true;
  }
}

function boardReset() {
  stage.destroyChildren();
  boardInfo();
}

function cleanMove() {
  gid2high[movestage].visible(false);
  for (let tgid of targets) {
    gid2high[tgid].visible(false);
  }
  if (target != -1) {
    gid2piece[target].text(gid2piece[movestage].text());
    gid2piece[target].fill(gid2piece[movestage].fill());
    gid2piece[movestage].text("");
    gid2piece[movestage].fill("#ffffff");
  }
  targets.clear();
  promotions.clear();
  target = -1;
  movestage = -1;
  gameInfo();
  ready = true;
}

function drawPieces(pieces) {
  for (let gid = 0; gid <= 168; gid++) {
    gid2piece[gid].text("");
    gid2piece[gid].fill("#ffffff");
  }
  for (let pid in pieces) {
    for (let pcs in pieces[pid]) {
      gid2piece[pieces[pid][pcs].gid].text(PIECES[pieces[pid][pcs].piece]);
      gid2piece[pieces[pid][pcs].gid].fill(PIECES_COLOR[pid]);
    }
  }
}

function updateStats(eliminated, move_number) {
  let pp0 = [];
  el = eliminated[((0 + view_pid) % 3).toString()];
  for (let pcs in el) {
    pp0.push(PIECES[el[pcs]]);
  }
  p0el.text(pp0.join(" "));
  let pp1 = [];
  el = eliminated[((1 + view_pid) % 3).toString()];
  for (let pcs in el) {
    pp1.push(PIECES[el[pcs]]);
  }
  p1el.text(pp1.join(" "));
  let pp2 = [];
  el = eliminated[((2 + view_pid) % 3).toString()];
  for (let pcs in el) {
    pp2.push(PIECES[el[pcs]]);
  }
  p2el.text(pp2.join(""));
  slogtext.innerHTML = slog;
  movelabel.text(`${move_number}/${game_slog.length / 4}`);
}

function validMoves(gid) {
  const url = `${protocol}//${hostname}/api/v1/move/valid`;
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
      gid2hex[gid].stroke("black");
      for (let i in data.targets) {
        let tgid = data.targets[i].tgid;
        targets.add(tgid);
        gid2high[tgid].visible(true);
        if (data.targets[i].kind == "attack") {
          gid2high[tgid].stroke("red");
        } else {
          gid2high[tgid].stroke("green");
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
  const url = `${protocol}//${hostname}/api/v1/move/make`;
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
        gid2piece[gid].text(PIECES[new_piece]);
      }
      slog = data.slog;
      if (slog.slice(0, -4) == game_slog.slice(0, slog.length - 4)) {
        game_slog = slog;
      }
      target = tgid;
      cleanHigh();
      cleanMove();
      if (slog.slice(0, -4) == server_slog && on_move) {
        submit.disabled = false;
        submit.className = "btn btn-danger mb-2 col-12";
      } else {
        submit.disabled = true;
        submit.className = "btn btn-secondary mb-2 col-12";
      }
    })
    .catch((error) => {
      alert("makeMove Error:", error);
    });
}

function gameInfo(init = false) {
  const url = `${protocol}//${hostname}/api/v1/game/info`;
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
        drawPieces(data.pieces);
        on_move = data.onmove == view_pid;
      }
      p0name.fontStyle("normal");
      p0name.fill("black");
      p1name.fontStyle("normal");
      p1name.fill("black");
      p2name.fontStyle("normal");
      p2name.fill("black");
      if ((data.onmove + 3 - view_pid) % 3 == 0) {
        p0name.fontStyle("bold");
        if (data.in_chess) {
          p0name.fill("red");
          gid2high[data.king_pos].visible(true);
          gid2high[data.king_pos].stroke("red");
          for (let xby in data.chess_by[1]) {
            gid2high[data.chess_by[1][xby].gid].visible(true);
            gid2high[data.chess_by[1][xby].gid].stroke("green");
          }
          for (let xby in data.chess_by[2]) {
            gid2high[data.chess_by[2][xby].gid].visible(true);
            gid2high[data.chess_by[2][xby].gid].stroke("green");
          }
        }
      } else if ((data.onmove + 3 - view_pid) % 3 == 1) {
        p1name.fontStyle("bold");
        if (data.in_chess) {
          p1name.fill("red");
          gid2high[data.king_pos].visible(true);
          gid2high[data.king_pos].stroke("red");
          for (let xby in data.chess_by[0]) {
            gid2high[data.chess_by[0][xby].gid].visible(true);
            gid2high[data.chess_by[0][xby].gid].stroke("green");
          }
          for (let xby in data.chess_by[2]) {
            gid2high[data.chess_by[2][xby].gid].visible(true);
            gid2high[data.chess_by[2][xby].gid].stroke("green");
          }
        }
      } else {
        p2name.fontStyle("bold");
        if (data.in_chess) {
          p2name.fill("red");
          gid2high[data.king_pos].visible(true);
          gid2high[data.king_pos].stroke("red");
          for (let xby in data.chess_by[0]) {
            gid2high[data.chess_by[0][xby].gid].visible(true);
            gid2high[data.chess_by[0][xby].gid].stroke("green");
          }
          for (let xby in data.chess_by[1]) {
            gid2high[data.chess_by[1][xby].gid].visible(true);
            gid2high[data.chess_by[1][xby].gid].stroke("green");
          }
        }
      }
      updateStats(data.eliminated, data.move_number);

      if (data.last_move != null) {
        if (lastmove["from"] != -1) {
          gid2hex[lastmove["from"]].opacity(1);
        }
        lastmove["from"] = data.last_move["from"];
        gid2hex[lastmove["from"]].opacity(0.35);
        if (lastmove["to"] != -1) {
          gid2hex[lastmove["to"]].opacity(1);
        }
        lastmove["to"] = data.last_move["to"];
        gid2hex[lastmove["to"]].opacity(0.35);
      }
    })
    .catch((error) => {
      alert("gameInfo Error:", error);
    });
}

function boardInfo() {
  const url =
    `${protocol}//${hostname}/api/v1/manager/board?id=` + id.toString();
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
      seat_0 = seats[(0 + view_pid) % 3];
      seat_1 = seats[(1 + view_pid) % 3];
      seat_2 = seats[(2 + view_pid) % 3];
      slog = data.slog;
      server_slog = data.slog;
      game_slog = data.slog;
      gameInfo(true);
      var layer = new Konva.Layer();
      stage.add(layer);

      // Create mappings
      let gid = 0;
      for (let r = -7; r <= 7; r++) {
        for (let q = -7; q <= 7; q++) {
          const s = -q - r;
          if (s >= -7 && s <= 7) {
            const x = q + 0.5 * r;
            const y = (r * Math.sqrt(3)) / 2;
            gid2xy[gid] = [x, y];
            const colorid = (((2 * q + r) % 3) + 3) % 3;
            gid2hex[gid] = createHexPatch(gid, [x, y], HEX_COLORS[colorid]);
            gid2high[gid] = createHexHigh([x, y]);
            gid2piece[gid] = createHexLabel(gid, [x, y], "#ffffff", "");
            gid++;
          }
        }
      }

      // Add board hexes
      for (let gid = 0; gid <= 168; gid++) {
        layer.add(gid2hex[gid]);
        layer.add(gid2piece[gid]);
        layer.add(gid2high[gid]);
      }
      // set colors eliminated
      p0el.fill(PIECES_COLOR[(0 + view_pid) % 3]);
      p1el.fill(PIECES_COLOR[(1 + view_pid) % 3]);
      p2el.fill(PIECES_COLOR[(2 + view_pid) % 3]);
      // set names
      p0name.text(seat_0);
      p1name.text(seat_1);
      p2name.text(seat_2);
      layer.add(movelabel);
      layer.add(p0name);
      layer.add(p0el);
      layer.add(p1name);
      layer.add(p1el);
      layer.add(p2name);
      layer.add(p2el);

      layer.on("click touchenter", function (evt) {
        const shape = evt.target;
        manageMove(shape.id());
      });

      layer.draw();

      fitStageIntoDiv();
      submit.disabled = true;
      ready = true;
    })
    .catch((error) => {
      alert("Error:", error);
    });
}

function boardSubmit() {
  const url = `${protocol}//${hostname}/api/v1/manager/board`;
  const headers = new Headers();
  headers.append("Accept", "application/json");
  headers.append("Content-Type", "application/json");
  headers.append("Authorization", access_token);
  ready = false;

  fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({ id: id, slog: slog }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      server_slog = slog;
      submit.disabled = true;
      on_move = false;
      ready = true;
    })
    .catch((error) => {
      alert("Error:", error);
    });
}

window.addEventListener("resize", fitStageIntoDiv);

boardInfo();
