const gid2xy = {};
const gid2color = {};
const gid2hex = {};
const gid2high = {};
const gid2piece = {};
const pieces_symbols = { P: "♟", N: "♞", B: "♝", R: "♜", Q: "♛", K: "♚" };
var stageWidth = 20;
var stageHeight = 18;
var movestage = -1;
var target = -1;
var ready = false;
var targets = new Set();
var promotions = new Set();
var lastmove = { from: -1, to: -1 };
var slogtext = document.getElementById("log");
var submit = document.getElementById("submitGame");
var backmove = document.getElementById("backMove");
var forwardmove = document.getElementById("forwardMove");
var modalPiece = new bootstrap.Modal(document.getElementById("selectPiece"));
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
  fill: theme["board"]["background"],
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

var movelabel = new Konva.Text({
  x: -11.5,
  y: 6,
  text: "",
  fontFamily: theme["board"]["font-family"],
  fontSize: 0.6,
  align: "right",
  width: 6,
  listening: false,
});
var p0name = new Konva.Text({
  x: -3,
  y: 6.75,
  text: "",
  fontFamily: theme["board"]["font-family"],
  fontSize: 0.6,
  align: "center",
  width: 6,
  listening: false,
});
var p0el = new Konva.Text({
  x: 6.5,
  y: 2,
  text: "",
  fontFamily: theme["pieces"]["font-family"],
  fontSize: 0.7,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.15,
  fillAfterStrokeEnabled: true,
  width: 2.5,
  align: "center",
  listening: false,
});
var p1name = new Konva.Text({
  x: -10.5,
  y: -7.25,
  text: "",
  fontFamily: theme["board"]["font-family"],
  fontSize: 0.6,
  align: "right",
  width: 6,
  listening: false,
});
var p1el = new Konva.Text({
  x: -9,
  y: -6.5,
  text: "",
  fontFamily: theme["pieces"]["font-family"],
  fontSize: 0.7,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.15,
  fillAfterStrokeEnabled: true,
  width: 2.5,
  align: "center",
  listening: false,
});
var p2name = new Konva.Text({
  x: 4.5,
  y: -7.25,
  text: "",
  fontFamily: theme["board"]["font-family"],
  fontSize: 0.6,
  align: "left",
  width: 6,
  listening: false,
});
var p2el = new Konva.Text({
  x: 6.5,
  y: -6.5,
  text: "",
  fontFamily: theme["pieces"]["font-family"],
  fontSize: 0.7,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.15,
  fillAfterStrokeEnabled: true,
  width: 2.5,
  align: "center",
  listening: false,
});

var gameover = new Konva.Text({
  x: -7.75,
  y: -2,
  text: "GAME OVER",
  fontFamily: theme["board"]["font-family"],
  fill: theme["board"]["game_over"],
  fontSize: 2.5,
  fontStyle: "bold",
  opacity: 0.95,
  align: "center",
  verticalAlign: "middle",
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
    y: xy[1] - 0.45,
    fontFamily: theme["pieces"]["font-family"],
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
  gameInfo(false, true);
  ready = true;
}

function drawPieces(pieces) {
  for (let gid = 0; gid <= 168; gid++) {
    gid2piece[gid].text("");
    gid2piece[gid].fill("#ffffff");
  }
  for (let pid in pieces) {
    for (let pcs in pieces[pid]) {
      gid2piece[pieces[pid][pcs].gid].text(
        pieces_symbols[pieces[pid][pcs].piece],
      );
      gid2piece[pieces[pid][pcs].gid].fill(theme["pieces"]["color"][pid]);
    }
  }
}

function updateStats(eliminated, value, move_number) {
  p0name.text(`${seat[0]} (${value[(0 + view_pid) % 3]})`);
  let pp0 = [];
  el = eliminated[(0 + view_pid) % 3];
  for (let pcs in el) {
    pp0.push(pieces_symbols[el[pcs]]);
  }
  p0el.text(pp0.join(" "));

  p1name.text(`${seat[1]} (${value[(1 + view_pid) % 3]})`);
  let pp1 = [];
  el = eliminated[(1 + view_pid) % 3];
  for (let pcs in el) {
    pp1.push(pieces_symbols[el[pcs]]);
  }
  p1el.text(pp1.join(" "));

  p2name.text(`${seat[2]} (${value[(2 + view_pid) % 3]})`);
  let pp2 = [];
  el = eliminated[(2 + view_pid) % 3];
  for (let pcs in el) {
    pp2.push(pieces_symbols[el[pcs]]);
  }
  p2el.text(pp2.join(""));
  slogtext.innerHTML = slog;
  movelabel.text(`#${id}:${move_number}/${game_slog.length / 4}`);
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
      gid2high[gid].stroke("black");
      for (let i in data.targets) {
        let tgid = data.targets[i].tgid;
        targets.add(tgid);
        gid2high[tgid].visible(true);
        if (data.targets[i].kind == "attack") {
          gid2high[tgid].stroke(theme["board"]["attack_move"]);
        } else {
          gid2high[tgid].stroke(theme["board"]["valid_move"]);
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
        gid2piece[gid].text(pieces_symbols[new_piece]);
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

      p0name.fontStyle("normal");
      p0name.fill(theme["board"]["name_color"]);
      p1name.fontStyle("normal");
      p1name.fill(theme["board"]["name_color"]);
      p2name.fontStyle("normal");
      p2name.fill(theme["board"]["name_color"]);
      if ((data.onmove + 3 - view_pid) % 3 == 0) {
        p0name.fontStyle("bold");
        if (data.in_chess) {
          p0name.fill(theme["board"]["name_color_inchess"]);
        } else {
          p0name.fill(theme["board"]["name_color_onmove"]);
        }
      } else if ((data.onmove + 3 - view_pid) % 3 == 1) {
        p1name.fontStyle("bold");
        if (data.in_chess) {
          p1name.fill(theme["board"]["name_color_inchess"]);
        } else {
          p1name.fill(theme["board"]["name_color_onmove"]);
        }
      } else {
        p2name.fontStyle("bold");
        if (data.in_chess) {
          p2name.fill(theme["board"]["name_color_inchess"]);
        } else {
          p2name.fill(theme["board"]["name_color_onmove"]);
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
        gameover.text(
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
        gid2high[lastmove["from"]].stroke(theme["board"]["last_move"]);
        if (lastmove["to"] != -1) {
          gid2high[lastmove["to"]].visible(false);
        }
        lastmove["to"] = data.last_move["to"];
        gid2high[lastmove["to"]].visible(true);
        gid2high[lastmove["to"]].stroke(theme["board"]["last_move"]);
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
      var layer = new Konva.Layer();
      stage.add(layer);
      layer.add(background);

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
            gid2hex[gid] = createHexPatch(
              gid,
              [x, y],
              theme["hex"]["color"][colorid],
            );
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
      p0el.fill(theme["pieces"]["color"][(0 + view_pid) % 3]);
      p1el.fill(theme["pieces"]["color"][(1 + view_pid) % 3]);
      p2el.fill(theme["pieces"]["color"][(2 + view_pid) % 3]);

      layer.add(movelabel);
      layer.add(p0name);
      layer.add(p0el);
      layer.add(p1name);
      layer.add(p1el);
      layer.add(p2name);
      layer.add(p2el);
      // game over
      layer.add(gameover);

      layer.on("click touchenter", function (evt) {
        const shape = evt.target;
        manageMove(shape.id());
      });

      layer.draw();

      fitStageIntoDiv();
      submit.disabled = true;
      submit.className = "btn btn-secondary mb-2 col-12";
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
      submit.className = "btn btn-secondary mb-2 col-12";
      on_move = false;
      ready = true;
    })
    .catch((error) => {
      alert("Error:", error);
    });
}

window.addEventListener("resize", fitStageIntoDiv);

boardInfo();
