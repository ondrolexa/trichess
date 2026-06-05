// Triches board state
const AppState = {
  // Board hex mappings: GID → Konva shape (populated at runtime)
  gid2hex: {},
  gid2high: {},
  gid2valid: {},
  gid2attack: {},
  gid2piece: {},

  // Coordinate → GID lookup (populated at runtime)
  pos2gid: {},

  // Player / seat mappings (populated from server response)
  seat2pid: {},
  seat2name: {},
  pid2seat: {},
  pid2name: {},

  // Game slog
  slog: "",
  server_slog: "",
  game_slog: "",
  game_moves: 0,

  // Turn & interaction flags
  on_move: false,
  view_pid: 0,
  ready: false,

  // Animation tween
  active_tween: { active: false, tween: null },

  // Eliminated-piece Konva shapes per player (populated at runtime)
  elpieces: { 0: {}, 1: {}, 2: {} },

  // Player display
  player_names: { 0: "", 1: "", 2: "" },
  player_names_font: { 0: "", 1: "", 2: "" },
  player_names_color: { 0: "#ffffff", 1: "#ffffff", 2: "#ffffff" },

  // Move label
  movelabel_text: "",

  // Move-selection
  movestage: -1,
  target: -1,
  current: -1,
  targets: new Set(),
  promotions: new Set(),
  lastmove: { gid: -1, tgid: -1 },

  // Canvas / layout dimensions
  stageWidth: 20,
  stageHeight: 17,
  visual_shift: 20,

  // Touch / pinch-zoom gesture tracking
  lastCenter: null,
  lastDist: 0,
  dragStopped: false,
};
// ─────────────────────────────────────────────────────────────────────────────

// DOM references (not state — never reassigned)
const slogtext = document.getElementById("log");
const submit = document.getElementById("submitGame");
const draw = document.getElementById("voteDraw");
const resign = document.getElementById("voteResign");
const submitText = document.getElementById("submitText");
const loader = document.getElementById("loader");
const backmove = document.getElementById("backMove");
const forwardmove = document.getElementById("forwardMove");
const modalPiece = new bootstrap.Modal(document.getElementById("selectPiece"));
const navbar = document.getElementById("header");
const voteModals = {
  draw: new bootstrap.Modal(document.getElementById("voteDrawDialog")),
  resign: new bootstrap.Modal(document.getElementById("voteResignDialog")),
};

// Constants
const LINE_DASH = [0.2, 0.1];
const LINE_WIDTH = 0.04;

const API_URL = `${window.location.protocol}//${window.location.host}`;

const HEX_RADIUS = 7;
const TOTAL_HEXES = 169;
const MAX_ELIMINATED = 23;
const HEX_SIZE = Math.sqrt(1 / 3);

function buildHeaders() {
  return new Headers({
    Accept: "application/json",
    "Content-Type": "application/json",
    Authorization: access_token,
  });
}

function apiFetch(path, body) {
  AppState.ready = false;
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });
}

function apiFetchGet(path) {
  AppState.ready = false;
  return fetch(`${API_URL}${path}`, {
    method: "GET",
    headers: buildHeaders(),
  });
}

// Konva objects and events

const stage = new Konva.Stage({
  container: "canvas",
  width: AppState.stageWidth,
  height: AppState.stageHeight,
  draggable: true,
  offset: {
    x: -AppState.stageWidth / 2,
    y: -AppState.stageHeight / 2 + 1,
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
  const oldScale = stage.scaleX();

  const mousePointTo = {
    x: stage.getPointerPosition().x / oldScale - stage.x() / oldScale,
    y: stage.getPointerPosition().y / oldScale - stage.y() / oldScale,
  };

  const newScale = e.evt.deltaY > 0 ? oldScale * 0.95 : oldScale / 0.95;
  stage.scale({ x: newScale, y: newScale });

  const newPos = {
    x: -(mousePointTo.x - stage.getPointerPosition().x / newScale) * newScale,
    y: -(mousePointTo.y - stage.getPointerPosition().y / newScale) * newScale,
  };
  stage.position(newPos);
  stage.batchDraw();
});

Konva.hitOnDragEnabled = true;
function getDistance(p1, p2) {
  return Math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2);
}

function getCenter(p1, p2) {
  return {
    x: (p1.x + p2.x) / 2,
    y: (p1.y + p2.y) / 2,
  };
}

stage.on("touchmove", function (e) {
  e.evt.preventDefault();
  let touch1 = e.evt.touches[0];
  let touch2 = e.evt.touches[1];

  // we need to restore dragging, if it was cancelled by multi-touch
  if (touch1 && !touch2 && !stage.isDragging() && AppState.dragStopped) {
    stage.startDrag();
    AppState.dragStopped = false;
  }

  if (touch1 && touch2) {
    // we need to stop Konva's drag&drop and implement our own pan logic with two pointers
    if (stage.isDragging()) {
      AppState.dragStopped = true;
      stage.stopDrag();
    }

    let rect = stage.container().getBoundingClientRect();

    let p1 = {
      x: touch1.clientX - rect.left,
      y: touch1.clientY - rect.top,
    };
    let p2 = {
      x: touch2.clientX - rect.left,
      y: touch2.clientY - rect.top,
    };

    if (!AppState.lastCenter) {
      AppState.lastCenter = getCenter(p1, p2);
      return;
    }
    let newCenter = getCenter(p1, p2);

    let dist = getDistance(p1, p2);

    if (!AppState.lastDist) {
      AppState.lastDist = dist;
    }

    // local coordinates of center point
    let pointTo = {
      x: (newCenter.x - stage.x()) / stage.scaleX(),
      y: (newCenter.y - stage.y()) / stage.scaleX(),
    };

    let scale = stage.scaleX() * (dist / AppState.lastDist);

    stage.scaleX(scale);
    stage.scaleY(scale);

    // calculate new position of the stage
    let newPos = {
      x: newCenter.x - pointTo.x * scale,
      y: newCenter.y - pointTo.y * scale,
    };

    stage.position(newPos);

    AppState.lastDist = dist;
    AppState.lastCenter = newCenter;
  }
});

stage.on("touchend", function () {
  AppState.lastDist = 0;
  AppState.lastCenter = null;
});

const movelabel = new Konva.Shape({
  x: -7.7,
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
    const lines = AppState.movelabel_text.split("\n");
    for (let i = 0; i < lines.length; i++)
      context.fillText(lines[i], 0, i * 10);
  },
});

const p0name = new Konva.Shape({
  x: 0,
  y: 7.4,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = AppState.player_names_font[0];
    context.fillStyle = AppState.player_names_color[0];
    context.textAlign = "center";
    context.fillText(AppState.player_names[0], 0, 0);
  },
});

const p0el1 = new Konva.Rect({
  x: 0,
  y: 7.7,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][1],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const p0el2 = new Konva.Rect({
  x: 0,
  y: 7.7,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][2],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const p1name = new Konva.Shape({
  x: -9.2,
  y: -6.9,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = AppState.player_names_font[1];
    context.fillStyle = AppState.player_names_color[1];
    context.textAlign = "left";
    context.fillText(AppState.player_names[1], 0, 0);
  },
});

const p1el2 = new Konva.Rect({
  x: -9.2,
  y: -7.8,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][2],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const p1el0 = new Konva.Rect({
  x: -9.2,
  y: -7.8,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][0],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const p2name = new Konva.Shape({
  x: 9.2,
  y: -6.9,
  width: 8,
  height: 1,
  scale: {
    x: 0.07,
    y: 0.07,
  },
  sceneFunc: function (context, shape) {
    context.font = AppState.player_names_font[2];
    context.fillStyle = AppState.player_names_color[2];
    context.textAlign = "right";
    context.fillText(AppState.player_names[2], 0, 0);
  },
});

const p2el0 = new Konva.Rect({
  x: 9.2,
  y: -7.8,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][0],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const p2el1 = new Konva.Rect({
  x: 9.2,
  y: -7.8,
  width: 0,
  height: 2.5,
  fill: theme["pieces"]["color"][1],
  offsetX: 0,
  stroke: theme["pieces"]["stroke-color"],
  strokeWidth: 0.5,
  scale: {
    x: 0.07,
    y: 0.07,
  },
});

const gameover = new Konva.Group({
  visible: false,
});

const gameover_bg = new Konva.Rect({
  x: -8,
  y: -3,
  width: 16,
  height: 6.5,
  opacity: 0.65,
  fill: theme["canvas"]["background"],
  listening: true,
});

const gameover_text = new Konva.Text({
  x: -7,
  y: -2,
  text: "GAME OVER",
  fontFamily: theme["canvas"]["font-family"],
  fill: theme["canvas"]["game_over"],
  fontSize: 2.4,
  fontStyle: "bold",
  align: "center",
  verticalAlign: "middle",
  opacity: 0.65,
  listening: false,
});

gameover.add(gameover_bg);
gameover.add(gameover_text);
gameover.on("click tap", function (evt) {
  gameover.visible(false);
});

const qline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: LINE_WIDTH,
  dash: LINE_DASH,
  visible: false,
  listening: false,
});

const rline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: LINE_WIDTH,
  dash: LINE_DASH,
  visible: false,
  listening: false,
});

const sline = new Konva.Line({
  points: [],
  stroke: theme["board"]["hint_lines"],
  strokeWidth: LINE_WIDTH,
  dash: LINE_DASH,
  visible: false,
  listening: false,
});

const board_layer = new Konva.Layer();
const interactive_layer = new Konva.Layer();
const pieces_layer = new Konva.Layer();
const top_layer = new Konva.Layer();
stage.add(board_layer);
stage.add(interactive_layer);
stage.add(pieces_layer);
stage.add(top_layer);

// helpers

function fitStageIntoDiv() {
  let container = document.querySelector("#canvas");
  let containerWidth = container.offsetWidth;
  let containerHeight = container.offsetHeight;
  let scale = Math.min(
    containerWidth / AppState.stageWidth,
    containerHeight / AppState.stageHeight,
  );
  stage.width(containerWidth);
  if (containerWidth >= 768) {
    stage.height(containerHeight);
  } else {
    stage.height(AppState.stageHeight * scale);
  }
  stage.offsetX(
    -AppState.stageWidth / 2 -
      (containerWidth / scale - AppState.stageWidth) / 2,
  );
  stage.scale({ x: scale, y: scale });
  stage.position({ x: -10, y: AppState.visual_shift });
  stage.draw();
}

function doOnOrientationChange() {
  switch (window.screen.orientation.type) {
    case "landscape-primary":
      navbar.style.display = "none";
      AppState.stageWidth = 17;
      AppState.stageHeight = 20;
      AppState.visual_shift = 0;
      fitStageIntoDiv();
      window.scrollBy(0, 200);
      break;
    case "portrait-secondary":
      navbar.style.display = "";
      AppState.stageWidth = 20;
      AppState.stageHeight = 17;
      AppState.visual_shift = 20;
      fitStageIntoDiv();
      break;
    case "landscape-secondary":
      navbar.style.display = "none";
      AppState.stageWidth = 17;
      AppState.stageHeight = 20;
      AppState.visual_shift = 0;
      fitStageIntoDiv();
      break;
    default:
      navbar.style.display = "";
      AppState.stageWidth = 20;
      AppState.stageHeight = 17;
      AppState.visual_shift = 20;
      fitStageIntoDiv();
  }
}

function createHexPatch(gid, xy, color, stroke, qr) {
  let hex = new Konva.RegularPolygon({
    id: gid,
    x: xy[0],
    y: xy[1],
    sides: 6,
    radius: HEX_SIZE,
    fill: color,
    stroke: stroke,
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
    radius: HEX_SIZE - 0.075,
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

function createHexLabel(gid, xy, color, strokewidth, data) {
  let label = new Konva.Path({
    id: gid,
    x: xy[0],
    y: xy[1],
    data: data,
    fill: color,
    lineCap: "round",
    lineJoin: "round",
    stroke: theme["pieces"]["stroke-color"],
    strokeWidth: strokewidth,
    scale: {
      x: 0.075,
      y: 0.075,
    },
    name: "piece",
    listening: false,
  });
  return label;
}

// Move cycle manager

function manageMove(gid) {
  if (AppState.ready) {
    AppState.current = gid;
    if (AppState.movestage == -1) {
      setCoordHints(gid);
      validMoves(gid);
    } else {
      if (AppState.targets.has(gid)) {
        if (AppState.promotions.has(gid)) {
          AppState.target = gid;
          modalPiece.toggle();
        } else {
          AppState.current = -1;
          makeMove(AppState.movestage, gid);
        }
      } else {
        if (gid == AppState.movestage) {
          AppState.current = -1;
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
  makeMove(AppState.movestage, AppState.target, label);
}

function cleanHigh() {
  for (let gid = 0; gid < TOTAL_HEXES; gid++) {
    AppState.gid2high[gid].visible(false);
    AppState.gid2valid[gid].visible(false);
    AppState.gid2attack[gid].visible(false);
  }
  qline.visible(false);
  rline.visible(false);
  sline.visible(false);
}

function backMove() {
  if (AppState.slog.length > 0) {
    AppState.slog = AppState.slog.slice(0, -4);
    AppState.movestage = -1;
    cleanHigh();
    gameInfo(false, true);
    AppState.ready = true;
  }
}

function forwardMove() {
  if (AppState.slog.length < AppState.game_slog.length) {
    AppState.slog = AppState.game_slog.slice(0, AppState.slog.length + 4);
    AppState.movestage = -1;
    cleanHigh();
    gameInfo(false, true);
    AppState.ready = true;
  }
}

function boardReset() {
  cleanHigh();
  board_layer.removeChildren();
  interactive_layer.removeChildren();
  pieces_layer.removeChildren();
  top_layer.removeChildren();
  boardInfo();
}

function cleanMove() {
  AppState.gid2high[AppState.movestage].visible(false);
  for (let tgid of AppState.targets) {
    AppState.gid2high[tgid].visible(false);
    AppState.gid2valid[tgid].visible(false);
    AppState.gid2attack[tgid].visible(false);
  }
  AppState.targets.clear();
  AppState.promotions.clear();
  AppState.target = -1;
  AppState.movestage = -1;
  gameInfo(false, true);
  AppState.ready = true;
}

function drawPieces(pieces) {
  for (let gid = 0; gid < TOTAL_HEXES; gid++) {
    AppState.gid2piece[gid].data("");
  }
  for (let [pid, piecesForPid] of Object.entries(pieces)) {
    for (let pcs of piecesForPid) {
      AppState.gid2piece[pcs.gid].data(pieces_paths["pieces"][pcs.piece]);
      AppState.gid2piece[pcs.gid].fill(theme["pieces"]["color"][pid]);
    }
  }
}

function updateStats(
  eliminated,
  eliminated_value,
  eliminations,
  pieces_value,
  move_number,
) {
  for (let p = 0; p < 3; p++) {
    AppState.player_names[p] =
      `${AppState.seat2name[p]} (${pieces_value[AppState.seat2pid[p]]}/${eliminated_value[AppState.seat2pid[p]]})`;
    let el = eliminated[AppState.seat2pid[p]];
    for (let pcs in el) {
      AppState.elpieces[p][pcs].data(pieces_paths["pieces"][el[pcs]]);
    }
    for (let i = el.length; i < 23; i++) {
      AppState.elpieces[p][i].data("");
    }
  }

  p0el1.width(eliminations[AppState.seat2pid[0]][AppState.seat2pid[1]]);
  p0el1.offsetX(eliminations[AppState.seat2pid[0]][AppState.seat2pid[1]]);
  p0el1.fill(theme["pieces"]["color"][AppState.seat2pid[1]]);
  p0el2.width(eliminations[AppState.seat2pid[0]][AppState.seat2pid[2]]);
  p0el2.fill(theme["pieces"]["color"][AppState.seat2pid[2]]);

  p1el2.width(eliminations[AppState.seat2pid[1]][AppState.seat2pid[2]]);
  p1el2.fill(theme["pieces"]["color"][AppState.seat2pid[2]]);
  p1el0.width(eliminations[AppState.seat2pid[1]][AppState.seat2pid[0]]);
  p1el0.offsetX(-eliminations[AppState.seat2pid[1]][AppState.seat2pid[2]]);
  p1el0.fill(theme["pieces"]["color"][AppState.seat2pid[0]]);

  p2el0.width(eliminations[AppState.seat2pid[2]][AppState.seat2pid[0]]);
  p2el0.offsetX(
    eliminations[AppState.seat2pid[2]][AppState.seat2pid[0]] +
      eliminations[AppState.seat2pid[2]][AppState.seat2pid[1]],
  );
  p2el0.fill(theme["pieces"]["color"][AppState.seat2pid[0]]);
  p2el1.width(eliminations[AppState.seat2pid[2]][AppState.seat2pid[1]]);
  p2el1.offsetX(eliminations[AppState.seat2pid[2]][AppState.seat2pid[1]]);
  p2el1.fill(theme["pieces"]["color"][AppState.seat2pid[1]]);

  slogtext.textContent = AppState.slog;
  AppState.movelabel_text = `Move\n${move_number}/${AppState.game_moves}`;
}

function setCoordHints(gid) {
  let q = AppState.gid2hex[gid].getAttr("q");
  let r = AppState.gid2hex[gid].getAttr("r");
  let gid_l11 = AppState.pos2gid[[Math.max(-7 - r, -7), r]];
  let gid_l12 = AppState.pos2gid[[Math.min(7 - r, 7), r]];
  let gid_l21 = AppState.pos2gid[[q, Math.max(-7 - q, -7)]];
  let gid_l22 = AppState.pos2gid[[q, Math.min(7 - q, 7)]];
  let gid_l31 =
    AppState.pos2gid[[q + Math.min(7 - q, r + 7), r - Math.min(7 - q, r + 7)]];
  let gid_l32 =
    AppState.pos2gid[[q - Math.min(q + 7, 7 - r), r + Math.min(q + 7, 7 - r)]];
  qline.points([
    AppState.gid2hex[gid_l11].x(),
    AppState.gid2hex[gid_l11].y(),
    AppState.gid2hex[gid_l12].x(),
    AppState.gid2hex[gid_l12].y(),
  ]);
  rline.points([
    AppState.gid2hex[gid_l21].x(),
    AppState.gid2hex[gid_l21].y(),
    AppState.gid2hex[gid_l22].x(),
    AppState.gid2hex[gid_l22].y(),
  ]);
  sline.points([
    AppState.gid2hex[gid_l31].x(),
    AppState.gid2hex[gid_l31].y(),
    AppState.gid2hex[gid_l32].x(),
    AppState.gid2hex[gid_l32].y(),
  ]);
  qline.visible(true);
  rline.visible(true);
  sline.visible(true);
}

// API calls

function validMoves(gid) {
  apiFetch("/api/v1/move/valid", {
    slog: AppState.slog,
    view_pid: AppState.view_pid,
    gid: gid,
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      AppState.gid2high[gid].visible(true);
      AppState.gid2high[gid].stroke(theme["board"]["selection"]);
      for (let target of data.targets) {
        let tgid = target.tgid;
        AppState.targets.add(tgid);
        if (target.kind == "attack") {
          AppState.gid2attack[tgid].stroke(theme["board"]["attack_move"]);
          AppState.gid2attack[tgid].visible(true);
        } else {
          AppState.gid2valid[tgid].stroke(theme["board"]["valid_move"]);
          AppState.gid2valid[tgid].visible(true);
        }
        if (target.promotion) {
          AppState.promotions.add(tgid);
        }
      }
      AppState.movestage = gid;
      AppState.ready = true;
    })
    .catch((response) => {
      console.error(
        `ValidMoves error ${response.status}: ${response.statusText}`,
      );
      // window.location.reload();
    });
}

function makeMove(gid, tgid, new_piece = "") {
  apiFetch("/api/v1/move/make", {
    slog: AppState.slog,
    view_pid: AppState.view_pid,
    gid: gid,
    tgid: tgid,
    new_piece: new_piece,
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      if (new_piece != "") {
        AppState.gid2piece[gid].data(pieces_paths["pieces"][new_piece]);
      }
      AppState.slog = data.slog;
      if (AppState.slog.length >= AppState.game_slog.length) {
        AppState.game_slog = AppState.slog;
      }
      AppState.target = tgid;
      cleanHigh();
      cleanMove();
    })
    .catch((response) => {
      console.error(
        `MakeMove error ${response.status}: ${response.statusText}`,
      );
      // window.location.reload();
    });
}

function voteDraw(vote) {
  apiFetch("/api/v1/vote/draw", {
    slog: AppState.slog,
    view_pid: AppState.view_pid,
    vote: vote,
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      AppState.slog = data.slog;
      if (AppState.slog.length >= AppState.game_slog.length) {
        AppState.game_slog = AppState.slog;
      }
      AppState.movestage = -1;
      cleanHigh();
      gameInfo(false, true);
      AppState.ready = true;
    })
    .catch((response) => {
      console.error(
        `VoteDraw error ${response.status}: ${response.statusText}`,
      );
      // window.location.reload();
    });
}

function voteResign(vote) {
  apiFetch("/api/v1/vote/resign", {
    slog: AppState.slog,
    view_pid: AppState.view_pid,
    vote: vote,
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      AppState.slog = data.slog;
      if (AppState.slog.length >= AppState.game_slog.length) {
        AppState.game_slog = AppState.slog;
      }
      AppState.movestage = -1;
      cleanHigh();
      gameInfo(false, true);
      AppState.ready = true;
    })
    .catch((response) => {
      console.error(
        `VoteResign error ${response.status}: ${response.statusText}`,
      );
      // window.location.reload();
    });
}

function showVoteModal(kind, vote_results) {
  let modalId = kind === "draw" ? "voteDrawDialog" : "voteResignDialog";
  let prefix = kind === "draw" ? "voteDraw" : "voteResign";
  let initiated = document.getElementById(prefix + "Initiated");
  let acceptPlayers = document.getElementById(prefix + "AcceptPlayers");
  let declinePlayers = document.getElementById(prefix + "DeclinePlayers");
  let accepting = [];
  let declining = [];
  for (let p = 0; p < 3; p++) {
    if (vote_results[AppState.seat2pid[p]] === "A")
      accepting.push(AppState.seat2name[p]);
    else if (vote_results[AppState.seat2pid[p]] === "D")
      declining.push(AppState.seat2name[p]);
  }
  initiated.textContent =
    AppState.seat2name[3 - vote_results["n_voted"]] ?? "Unknown";
  acceptPlayers.textContent = accepting.join(" ");
  declinePlayers.textContent = declining.join(" ");
  voteModals[kind].show();
}

function gameInfo(init = false, redraw = false) {
  apiFetch("/api/v1/game/info", {
    slog: AppState.slog,
    view_pid: AppState.view_pid,
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      if (init) {
        AppState.on_move = data.onmove == AppState.view_pid;
      }
      if (redraw) {
        drawPieces(data.pieces);
      }

      const fontBase = `${theme["canvas"]["font-family"]}, sans-serif`;
      for (let s = 0; s < 3; s++) {
        const isOnMove = AppState.pid2seat[data.onmove] === s;
        AppState.player_names_font[s] =
          `${isOnMove ? 900 : 400} 10px ${fontBase}`;
        AppState.player_names_color[s] = isOnMove
          ? data.in_chess
            ? theme["canvas"]["name_inchess"]
            : theme["canvas"]["name_onmove"]
          : theme["canvas"]["name"];
      }

      if (AppState.active_tween["active"] == true) {
        AppState.active_tween["tween"].reset();
        AppState.active_tween["tween"].destroy();
        AppState.active_tween["active"] = false;
      }

      updateStats(
        data.eliminated,
        data.eliminated_value,
        data.eliminations,
        data.pieces_value,
        data.move_number,
      );

      if (AppState.slog == AppState.server_slog && AppState.on_move) {
        draw.disabled = false;
        resign.disabled = false;
      } else {
        draw.disabled = true;
        resign.disabled = true;
      }
      // Setup buttons
      if (
        AppState.slog.slice(0, -4) == AppState.server_slog &&
        AppState.on_move
      ) {
        submit.disabled = false;
        submit.className = "btn btn-danger mb-2 col-12";
      } else {
        submit.disabled = true;
        submit.className = "btn btn-secondary mb-2 col-12";
      }
      if (AppState.slog.length < AppState.game_slog.length) {
        forwardmove.disabled = false;
        forwardmove.className = "btn btn-primary mb-2 col-12";
      } else {
        forwardmove.disabled = true;
        forwardmove.className = "btn btn-secondary mb-2 col-12";
      }
      if (AppState.slog.length > 0) {
        backmove.disabled = false;
        backmove.className = "btn btn-primary mb-2 col-12";
      } else {
        backmove.disabled = true;
        backmove.className = "btn btn-secondary mb-2 col-12";
      }
      // Show last move
      if (data.last_move != null) {
        if (AppState.lastmove["gid"] != -1) {
          AppState.gid2high[AppState.lastmove["gid"]].visible(false);
        }
        AppState.lastmove["gid"] = data.last_move["gid"];
        AppState.gid2high[AppState.lastmove["gid"]].visible(true);
        if (AppState.current == AppState.lastmove["gid"]) {
          AppState.gid2high[AppState.lastmove["gid"]].stroke(
            theme["board"]["selection"],
          );
        } else {
          AppState.gid2high[AppState.lastmove["gid"]].stroke(
            theme["board"]["last_move"],
          );
        }
        if (AppState.lastmove["tgid"] != -1) {
          AppState.gid2high[AppState.lastmove["tgid"]].visible(false);
        }
        AppState.lastmove["tgid"] = data.last_move["tgid"];
        AppState.gid2high[AppState.lastmove["tgid"]].visible(true);
        if (AppState.current == AppState.lastmove["tgid"]) {
          AppState.gid2high[AppState.lastmove["tgid"]].stroke(
            theme["board"]["selection"],
          );
        } else {
          AppState.gid2high[AppState.lastmove["tgid"]].stroke(
            theme["board"]["last_move"],
          );
        }
      }
      // show piece in chess
      if (data.in_chess) {
        AppState.active_tween["tween"] = new Konva.Tween({
          node: AppState.gid2piece[data.king_pos],
          easing: Konva.Easings.EaseInOut,
          duration: 0.5,
          scaleX: 0.1,
          scaleY: 0.1,
          yoyo: true,
        });
        AppState.active_tween["tween"].play();
        AppState.active_tween["active"] = true;
        AppState.gid2high[data.king_pos].visible(true);
        AppState.gid2high[data.king_pos].stroke(theme["board"]["hex_inchess"]);
        for (let player in data.chess_by) {
          for (let pcs in data.chess_by[player]) {
            AppState.gid2high[data.chess_by[player][pcs].gid].visible(true);
            AppState.gid2high[data.chess_by[player][pcs].gid].stroke(
              theme["board"]["hex_inchess"],
            );
          }
        }
      }
      // Show voting results
      if (data.vote_results != null) {
        AppState.movelabel_text = `Move ${data.move_number}\n${data.vote_results["kind"]} voting`;
        for (let p = 0; p < 3; p++) {
          AppState.player_names[p] =
            `${AppState.seat2name[p]} (${data.vote_results[AppState.seat2pid[p]]})`;
        }
      }
      // Open voting if needed
      board_layer.off("click tap");
      if (data.vote_needed && !data.finished) {
        if (data.onmove == AppState.view_pid) {
          showVoteModal(data.vote_results["kind"], data.vote_results);
        } else {
          AppState.movelabel_text = `${data.vote_results["kind"]} voting\nin progress`;
        }
      } else if (data.finished) {
        if (data.draw) {
          gameover_text.text("GAME OVER\nDraw agreed");
        } else if (data.resignation) {
          let wid;
          if (data.vote_results[0] == "D") {
            wid = 0;
          } else if (data.vote_results[1] == "D") {
            wid = 1;
          } else {
            wid = 2;
          }
          gameover_text.text("GAME OVER\n" + AppState.pid2name[wid] + " win");
        } else {
          gameover_text.text(
            "GAME OVER\n" + AppState.pid2name[data.onmove] + " lost",
          );
        }
        for (let p = 0; p < 3; p++) {
          AppState.player_names[p] =
            `${AppState.seat2name[p]} (${data.score[AppState.seat2pid[p]]})`;
        }
        gameover.visible(true);
      } else {
        gameover.visible(false);
        board_layer.on("click tap", function (evt) {
          let shape = evt.target;
          manageMove(shape.id());
        });
      }
    })
    .catch((response) => {
      console.error(
        `GameInfo error ${response.status}: ${response.statusText}`,
      );
      // window.location.reload();
    });
}

function boardInfo() {
  apiFetchGet("/api/v1/manager/board?id=" + id.toString())
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      // Create seats mappings
      let seats = [data.player_0, data.player_1, data.player_2];
      AppState.view_pid = data.view_pid;
      for (let p = 0; p < 3; p++) {
        AppState.seat2pid[p] = (p + AppState.view_pid) % 3;
        AppState.seat2name[p] = seats[AppState.seat2pid[p]];
        AppState.pid2seat[p] = (p + 3 - AppState.view_pid) % 3;
        AppState.pid2name[p] = seats[p];
      }
      AppState.slog = data.slog;
      AppState.server_slog = data.slog;
      AppState.game_slog = data.slog;
      AppState.game_moves = data.move_number;
      gameInfo(true, true);
      // Create board mappings
      let gid = 0;
      for (let r = -7; r <= 7; r++) {
        for (let q = -7; q <= 7; q++) {
          let s = -q - r;
          if (s >= -7 && s <= 7) {
            let x = q + 0.5 * r;
            let y = (r * Math.sqrt(3)) / 2;
            let colorid = (((2 * q + r) % 3) + 3) % 3;
            AppState.pos2gid[[q, r]] = gid;
            AppState.gid2hex[gid] = createHexPatch(
              gid,
              [x, y],
              theme["board"]["hex_color"][colorid],
              theme["board"]["hex_border"],
              [q, r],
            );
            AppState.gid2high[gid] = createHexHigh([x, y]);
            AppState.gid2valid[gid] = createHexValid([x, y]);
            AppState.gid2attack[gid] = createHexAttack([x, y]);
            AppState.gid2piece[gid] = createHexLabel(
              gid,
              [x, y],
              "#ffffff",
              0,
              "",
            );
            gid++;
          }
        }
      }
      // Create mappings for eliminated
      let q = {
        0: [
          9, 8, 8, 7, 8, 7, 6, 7, 6, 5, 7, 6, 5, 4, 6, 5, 4, 3, 6, 5, 4, 3, 2,
        ],
        1: [
          -5, -4, -3, -2, -1, -5, -4, -3, -2, -6, -5, -4, -3, -6, -5, -4, -7,
          -6, -5, -7, -6, -8, -7,
        ],
        2: [
          13, 12, 11, 10, 9, 12, 11, 10, 9, 12, 11, 10, 9, 11, 10, 9, 11, 10, 9,
          10, 9, 10, 9,
        ],
      };
      let r = {
        0: [
          1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7, 7,
        ],
        1: [
          -7, -7, -7, -7, -7, -6, -6, -6, -6, -5, -5, -5, -5, -4, -4, -4, -3,
          -3, -3, -2, -2, -1, -1,
        ],
        2: [
          -7, -7, -7, -7, -7, -6, -6, -6, -6, -5, -5, -5, -5, -4, -4, -4, -3,
          -3, -3, -2, -2, -1, -1,
        ],
      };
      for (let i = 0; i < 23; i++) {
        for (let p = 0; p < 3; p++) {
          AppState.elpieces[p][i] = createHexLabel(
            0,
            [q[p][i] + 0.5 * r[p][i] - 0.5, (r[p][i] * Math.sqrt(3)) / 2],
            theme["pieces"]["color"][AppState.seat2pid[p]],
            theme["pieces"]["stroke-color"] != theme["canvas"]["background"]
              ? 0.25
              : 0,
            "",
          );
          pieces_layer.add(AppState.elpieces[p][i]);
        }
      }

      board_layer.add(background);
      // Add board hexes
      for (let gid = 0; gid < TOTAL_HEXES; gid++) {
        board_layer.add(AppState.gid2hex[gid]);
        pieces_layer.add(AppState.gid2piece[gid]);
        interactive_layer.add(AppState.gid2high[gid]);
        interactive_layer.add(AppState.gid2valid[gid]);
        pieces_layer.add(AppState.gid2attack[gid]);
      }

      pieces_layer.add(movelabel);
      pieces_layer.add(p0name);
      pieces_layer.add(p0el1);
      pieces_layer.add(p0el2);
      pieces_layer.add(p1name);
      pieces_layer.add(p1el2);
      pieces_layer.add(p1el0);
      pieces_layer.add(p2name);
      pieces_layer.add(p2el0);
      pieces_layer.add(p2el1);

      // game over
      top_layer.add(gameover);
      // lines
      interactive_layer.add(qline);
      interactive_layer.add(rline);
      interactive_layer.add(sline);
      board_layer.draw();
      interactive_layer.draw();
      pieces_layer.draw();
      top_layer.draw();

      fitStageIntoDiv();
      submit.disabled = true;
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      AppState.ready = true;
    })
    .catch((response) => {
      console.log(`BoardInfo error ${response.status}: ${response.statusText}`);
      // window.location.reload();
    });
}

function boardSubmit() {
  submit.disabled = true;
  submit.className = "btn btn-secondary p-0 mb-0 col-12";
  submitText.innerHTML = "";
  loader.style.display = "inline-block";

  apiFetch("/api/v1/manager/board", { id: id, slog: AppState.slog })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      return Promise.reject(response);
    })
    .then((data) => {
      boardReset();
      AppState.on_move = false;
      AppState.ready = true;
      submitText.innerHTML = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
    })
    .catch((response) => {
      submitText.innerHTML = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      alert(`BoardSubmit error ${response.status}: ${response.statusText}`);
      // window.location.reload();
    });
}

window.addEventListener("resize", fitStageIntoDiv);
window.addEventListener("orientationchange", doOnOrientationChange);

// ready to go

boardInfo();
