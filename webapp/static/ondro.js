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

  // GID → slog 2-char coordinate code (populated from server response)
  gid2code: [],
  click_code: null,

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
  move_number: 0,

  // Move-selection
  movestage: -1,
  target: -1,
  current: -1,
  targets: new Set(),
  promotions: new Set(),
  lastmove: { gid: -1, tgid: -1 },
  prelastmove: { gid: -1, tgid: -1 },

  // Canvas / layout dimensions. Defaults are the portrait-optimized values
  // (bigger/lower board) since doOnOrientationChange() never fires on many
  // mobile browsers' initial page load — only on an actual rotation — so a
  // fresh load must already start in this state. Landscape cases in
  // doOnOrientationChange() explicitly override back to the original values.
  stageWidth: 15.8,
  stageHeight: 15.5,
  visual_shift: 70,
  baseScale: 1,

  // Player-cluster anchor points (world coords) — see applyAnchors(). All
  // default to the portrait-tuned values for the same reason as stageWidth
  // above (a fresh load must start in the portrait state without waiting
  // for an orientation event); landscape cases in doOnOrientationChange()
  // explicitly override each one back to its original unshifted value.
  // Derived by symmetry from anchor2 (the canonical reference): anchor1 is
  // its exact mirror across the vertical axis (x=0). anchor0el started as
  // the same mirror across the horizontal axis (y=0), but in portrait that
  // exact mirror clipped player 0's outermost eliminated-piece row at the
  // bottom edge — the large portrait visual_shift pushes everything down
  // uniformly, and player 0's rack (already the lowest cluster) had the
  // least margin to spare, unlike player 2's (top) mirror-image position.
  // anchor0el.y is now tuned independently (not a strict mirror) to claw
  // back that margin; anchor0el.x is still the exact mirror. See
  // doOnOrientationChange().
  anchor0name: { x: 0, y: 7.4 },
  anchor0el: { x: 7.35, y: 7.6 },
  anchor1: { x: -7.35, y: -8.4 },
  anchor2: { x: 7.35, y: -8.4 },
  anchorMove: { x: -6.4, y: 5.5 },

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
const mainContainer = document.querySelector(".main-container");
const voteModals = {
  draw: new bootstrap.Modal(document.getElementById("voteDrawDialog")),
  resign: new bootstrap.Modal(document.getElementById("voteResignDialog")),
};

// Constants
const LINE_DASH = [0.2, 0.1];
const LINE_WIDTH = 0.04;

const API_URL = `${window.location.protocol}//${window.location.host}`;

const TOTAL_HEXES = 169;
const MAX_ELIMINATED = 23;
const HEX_SIZE = Math.sqrt(1 / 3);

// Zoom bounds, relative to AppState.baseScale (the natural-fit scale set by
// fitStageIntoDiv()) — can't zoom out past the natural fit or in past 4x.
const MIN_ZOOM_FACTOR = 1.0;
const MAX_ZOOM_FACTOR = 4.0;

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

// Shared by wheel-zoom and pinch-zoom: clamps newScale to
// [baseScale*MIN_ZOOM_FACTOR, baseScale*MAX_ZOOM_FACTOR], rescales the stage
// while keeping focalPoint (in stage-container pixel coordinates) visually
// stationary, and redraws.
function applyZoom(newScale, focalPoint) {
  const oldScale = stage.scaleX();
  const clampedScale = Math.min(
    Math.max(newScale, AppState.baseScale * MIN_ZOOM_FACTOR),
    AppState.baseScale * MAX_ZOOM_FACTOR,
  );
  const pointTo = {
    x: (focalPoint.x - stage.x()) / oldScale,
    y: (focalPoint.y - stage.y()) / oldScale,
  };
  stage.scale({ x: clampedScale, y: clampedScale });
  stage.position({
    x: focalPoint.x - pointTo.x * clampedScale,
    y: focalPoint.y - pointTo.y * clampedScale,
  });
  stage.batchDraw();
}

stage.on("wheel", function (e) {
  e.evt.preventDefault();
  const oldScale = stage.scaleX();
  const newScale = e.evt.deltaY > 0 ? oldScale * 0.95 : oldScale / 0.95;
  applyZoom(newScale, stage.getPointerPosition());
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

    let scale = stage.scaleX() * (dist / AppState.lastDist);
    applyZoom(scale, newCenter);

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
    context.textAlign = "left";
    const lines = AppState.movelabel_text.split("\n");
    for (let i = 0; i < lines.length; i++)
      context.fillText(lines[i], 0, i * 10);
  },
});

const p0name = new Konva.Shape({
  x: 0,
  y: 0,
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
  y: 0.3,
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
  y: 0.3,
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
  x: 1.5,
  y: 1,
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
  x: 1.5,
  y: 0.1,
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
  x: 1.5,
  y: 0.1,
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
  x: -1.5,
  y: 1,
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
  x: -1.5,
  y: 0.1,
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
  x: -1.5,
  y: 0.1,
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

// Anchor groups: each player's UI cluster is children of a Group positioned
// at a single tunable "anchor" point, so per-orientation repositioning (see
// AppState.anchor*/applyAnchors()) moves the whole cluster as a rigid unit
// instead of requiring every shape's own hardcoded coordinate to be
// rescaled individually. Player 1 and 2's name/rack/eliminated-pieces share
// ONE anchor each (they're already co-located in one board corner). Player
// 0's name+rack is NOT co-located with player 0's eliminated pieces (name
// is bottom-center for readability, pieces are in a board corner like
// players 1/2), so player 0 keeps two separate anchors. Every anchor is
// derived from symmetry: anchor1 mirrors anchor2 across the vertical axis
// (x=0), anchor0el mirrors anchor2 across the horizontal axis (y=0) — see
// doOnOrientationChange()/applyInitialLayout() for the derivation.
const group0name = new Konva.Group({ x: 0, y: 7.4 });
group0name.add(p0name, p0el1, p0el2);
const group0el = new Konva.Group({ x: 9.2, y: 6.9 });
const group1 = new Konva.Group({ x: -9.2, y: -6.9 });
group1.add(p1name, p1el2, p1el0);
const group2 = new Konva.Group({ x: 9.2, y: -6.9 });
group2.add(p2name, p2el0, p2el1);

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

function applyAnchors() {
  group0name.position(AppState.anchor0name);
  group0el.position(AppState.anchor0el);
  group1.position(AppState.anchor1);
  group2.position(AppState.anchor2);
  movelabel.position(AppState.anchorMove);
  pieces_layer.batchDraw();
}

function fitStageIntoDiv() {
  let container = document.querySelector("#canvas");
  let containerWidth = container.offsetWidth;
  let containerHeight = container.offsetHeight;
  let scale = Math.min(
    containerWidth / AppState.stageWidth,
    containerHeight / AppState.stageHeight,
  );
  // Always match the container div's own measured size — sizing from
  // stageHeight*scale instead (as a previous version did below a 768px
  // breakpoint) only equals containerHeight when scale happens to be
  // height-bound. On portrait phones the virtual world (stageWidth=20,
  // stageHeight=17, wider than tall) is reliably width-bound against a
  // container that's taller than wide, so that formula systematically
  // undersized the canvas — leaving a gap below the board, and clipping
  // zoomed content at the canvas's own (too-small) pixel boundary.
  stage.width(containerWidth);
  stage.height(containerHeight);
  stage.offsetX(
    -AppState.stageWidth / 2 -
      (containerWidth / scale - AppState.stageWidth) / 2,
  );
  // offsetY was previously only ever set once, at stage construction, from
  // AppState.stageHeight's literal default (15.5, the portrait value) — it
  // never got recomputed per orientation/mode the way offsetX does above.
  // That's harmless whenever the live stageHeight happens to match that
  // default (true for portrait), but for any mode using a different
  // stageHeight (e.g. desktop's 16.7) it silently rendered with a stale,
  // wrong vertical center — most likely the real cause of desktop's
  // "everything needs to shift down, player 1/2 not visible" (a stale,
  // too-small-magnitude offsetY shifts content up on screen). The "+1" is
  // an intentional fixed downward-from-center bias (unrelated to scale),
  // preserved here exactly as it was at construction.
  stage.offsetY(-AppState.stageHeight / 2 + 1);
  stage.scale({ x: scale, y: scale });
  // x: -10 is an intentional empirical correction, not dead pixel-offset
  // cruft — removing it (tried once) made the board visibly off-center to
  // the user, even though the offsetX math above centers world-x=0 on the
  // container's own midpoint. Something outside this formula (likely
  // asymmetric visual weight from the player racks, or container
  // box-model quirks) shifts the true visual center left of world-x=0.
  //
  // Vertical position: width-bound fits (portrait/desktop) have leftover
  // vertical room, where AppState.visual_shift's per-orientation constant
  // (hand-tuned against real devices) controls how that slack is used.
  // Height-bound fits (mobile landscape, where the container is much wider
  // than the world box) have *zero* leftover vertical space by
  // definition — offsetY/scale already map the world box to exactly
  // containerHeight pixels top-to-bottom, so any additional fixed-pixel
  // shift on top of that either leaves a gap above the board or clips it
  // below, and the right amount to cancel that out (`scale`) depends on
  // the live container size, not a per-device constant. Using `scale`
  // itself as the y-shift exactly cancels offsetY's "-1 world unit" term,
  // landing the content flush against the container's top and bottom.
  const heightBound =
    containerHeight / AppState.stageHeight <=
    containerWidth / AppState.stageWidth;
  stage.position({
    x: -10,
    y: heightBound ? scale : AppState.visual_shift,
  });
  // Natural-fit scale, used as the zoom-out floor by applyZoom().
  AppState.baseScale = scale;
  stage.batchDraw();
}

function doOnOrientationChange() {
  if (!window.screen || !window.screen.orientation) {
    return;
  }
  // requestAnimationFrame: navbar.style.display changes just below, and
  // fitStageIntoDiv()/applyAnchors() read the container's layout size right
  // after — deferring to the next paint avoids measuring a stale size from
  // before the browser has reflowed the navbar toggle.
  // Mobile-landscape (both cases below) stays at its original baseline
  // size (stageHeight 20, the binding dimension in landscape) — a ~10%
  // scale-up was tried here but made the board too big on real devices, so
  // only mobile-portrait and desktop (applyInitialLayout() below) got a
  // permanent size increase; mobile-landscape did not.
  switch (window.screen.orientation.type) {
    case "landscape-primary":
      navbar.style.display = "none";
      // Reclaim the navbar's reserved height now that it's hidden — see
      // the .no-navbar rule in ondro.css.
      mainContainer.classList.add("no-navbar");
      AppState.stageWidth = 15.8;
      AppState.stageHeight = 22.5;
      AppState.visual_shift = 20;
      AppState.anchor0name = { x: 0, y: 7.4 };
      AppState.anchor0el = { x: 11.2, y: 6.9 };
      AppState.anchor1 = { x: -11.2, y: -6.9 };
      AppState.anchor2 = { x: 11.2, y: -6.9 };
      AppState.anchorMove = { x: -9.7, y: 4 };
      requestAnimationFrame(() => {
        fitStageIntoDiv();
        applyAnchors();
        window.scrollTo(0, 0);
      });
      break;
    case "portrait-secondary":
      navbar.style.display = "";
      mainContainer.classList.remove("no-navbar");
      AppState.stageWidth = 15.8;
      AppState.stageHeight = 15.5;
      AppState.visual_shift = 70;
      AppState.anchor0name = { x: 0, y: 7.4 };
      AppState.anchor0el = { x: 8.8, y: 9.5 };
      AppState.anchor1 = { x: -8.8, y: -9.5 };
      AppState.anchor2 = { x: 8.8, y: -9.5 };
      AppState.anchorMove = { x: -7.3, y: 5.5 };
      requestAnimationFrame(() => {
        fitStageIntoDiv();
        applyAnchors();
        window.scrollTo(0, 0);
      });
      break;
    case "landscape-secondary":
      navbar.style.display = "none";
      mainContainer.classList.add("no-navbar");
      AppState.stageWidth = 15.8;
      AppState.stageHeight = 22.5;
      AppState.visual_shift = 20;
      AppState.anchor0name = { x: 0, y: 7.4 };
      AppState.anchor0el = { x: 11.2, y: 6.9 };
      AppState.anchor1 = { x: -11.2, y: -6.9 };
      AppState.anchor2 = { x: 11.2, y: -6.9 };
      AppState.anchorMove = { x: -9.7, y: 4 };
      requestAnimationFrame(() => {
        fitStageIntoDiv();
        applyAnchors();
        window.scrollTo(0, 0);
      });
      break;
    default:
      navbar.style.display = "";
      mainContainer.classList.remove("no-navbar");
      AppState.stageWidth = 15.8;
      AppState.stageHeight = 15.5;
      AppState.visual_shift = 70;
      AppState.anchor0name = { x: 0, y: 7.4 };
      AppState.anchor0el = { x: 8.8, y: 9.5 };
      AppState.anchor1 = { x: -8.8, y: -9.5 };
      AppState.anchor2 = { x: 8.8, y: -9.5 };
      AppState.anchorMove = { x: -7.3, y: 7 };
      requestAnimationFrame(() => {
        fitStageIntoDiv();
        applyAnchors();
        window.scrollTo(0, 0);
      });
  }
}

function applyInitialLayout() {
  // window.screen.orientation existing is NOT a reliable mobile signal —
  // desktop Chrome/Edge/Firefox all expose it too (reporting
  // "landscape-primary" for an ordinary monitor), which used to route
  // desktop into doOnOrientationChange()'s mobile-landscape case: navbar
  // force-hidden, smaller mobile scale instead of desktop's own, and a
  // mobile-only window.scrollBy(0, 200) — the exact "navbar disappeared,
  // board too high" desktop regression. Gate on touch capability instead,
  // which real mobile/tablet devices have and desktop browsers don't.
  const isTouchDevice =
    "ontouchstart" in window || navigator.maxTouchPoints > 0;
  if (isTouchDevice && window.screen && window.screen.orientation) {
    doOnOrientationChange(); // covers all mobile cases correctly, portrait or landscape, from a cold load
    return;
  }
  // Desktop (or any non-touch browser) — classify by actual measured
  // dimensions instead, so first load isn't stuck with mobile-portrait
  // values. Desktop's non-portrait branch is scaled ~20% bigger than the
  // original baseline (bigger than mobile-landscape's ~10%, since desktop
  // has more room to spare) — stageHeight 20 -> 16.7 is what drives that,
  // being the binding dimension whenever the window is wider than tall.
  navbar.style.display = "";
  mainContainer.classList.remove("no-navbar");
  const isPortrait = window.innerHeight > window.innerWidth;
  AppState.stageWidth = isPortrait ? 15.8 : 14.2;
  AppState.stageHeight = isPortrait ? 15.5 : 16.7;
  AppState.visual_shift = isPortrait ? 70 : 40;
  AppState.anchor0name = { x: 0, y: 7.4 };
  AppState.anchor0el = isPortrait ? { x: 7.35, y: 7.6 } : { x: 11.2, y: 7.6 };
  AppState.anchor1 = isPortrait ? { x: -7.35, y: -8.4 } : { x: -11.2, y: -7.6 };
  AppState.anchor2 = isPortrait ? { x: 7.35, y: -8.4 } : { x: 11.2, y: -7.6 };
  AppState.anchorMove = isPortrait
    ? { x: -5.85, y: 5.5 }
    : { x: -9.7, y: 4 };
  fitStageIntoDiv();
  applyAnchors();
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
    // NOTE: no hitStrokeWidth here. This hex grid tiles edge-to-edge with
    // zero gap between adjacent cells (center-to-center spacing == HEX_SIZE
    // * sqrt(3), a standard zero-gap hex tiling identity), so any positive
    // hitStrokeWidth pads every hex's hit region into its neighbors' — a
    // touch-target enlargement that works for isolated buttons breaks a
    // tightly tessellated grid like this one (a click can register on the
    // wrong neighboring hex instead). Hit region intentionally matches the
    // visual fill exactly.
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

function hideMoveHighlight(state) {
  if (state["gid"] != -1) {
    AppState.gid2high[state["gid"]].visible(false);
  }
  if (state["tgid"] != -1) {
    AppState.gid2high[state["tgid"]].visible(false);
  }
  state["gid"] = -1;
  state["tgid"] = -1;
}

function setMoveHighlight(state, moveData, color) {
  state["gid"] = moveData["gid"];
  AppState.gid2high[state["gid"]].visible(true);
  AppState.gid2high[state["gid"]].stroke(
    AppState.current == state["gid"] ? theme["board"]["selection"] : color,
  );
  state["tgid"] = moveData["tgid"];
  AppState.gid2high[state["tgid"]].visible(true);
  AppState.gid2high[state["tgid"]].stroke(
    AppState.current == state["tgid"] ? theme["board"]["selection"] : color,
  );
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
    AppState.click_code = AppState.gid2code[gid];
    updateMoveLabel();
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

function handleBoardClick(evt) {
  let shape = evt.target;
  manageMove(shape.id());
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
  // Destroy only the per-gid shapes boardInfo() recreates on every reset —
  // removeChildren() alone leaks their listeners. Layer "chrome" (background,
  // qline/rline/sline, player-name labels, gameover) is a set of singletons
  // that boardInfo() re-adds by reference each time and must NOT be destroyed
  // here (gameover in particular has a click handler attached once at module
  // scope — destroying it would break the tap-to-dismiss game-over banner).
  for (let gid = 0; gid < TOTAL_HEXES; gid++) {
    AppState.gid2hex[gid].destroy();
    AppState.gid2high[gid].destroy();
    AppState.gid2valid[gid].destroy();
    AppState.gid2attack[gid].destroy();
    AppState.gid2piece[gid].destroy();
  }
  for (let p = 0; p < 3; p++) {
    for (let i = 0; i < MAX_ELIMINATED; i++) {
      AppState.elpieces[p][i].destroy();
    }
  }
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
    for (let i = el.length; i < MAX_ELIMINATED; i++) {
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
  AppState.move_number = move_number;
  updateMoveLabel();
}

function updateMoveLabel() {
  const coord = AppState.click_code ?? "--";
  AppState.movelabel_text = `C: ${coord}\nM: ${AppState.move_number}/${AppState.game_moves}`;
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
      AppState.ready = true;
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
      AppState.ready = true;
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
      AppState.ready = true;
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
      AppState.ready = true;
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

      if (
        AppState.slog == AppState.server_slog &&
        AppState.on_move &&
        !data.finished
      ) {
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
      // Show last two moves: hide both trackers' old squares first
      // (unconditionally, so a null response resets the tracker instead of
      // leaving stale gid/tgid behind), then draw both new ones (pre-last
      // first, last move second so an overlapping last-move highlight
      // visually wins) — hiding must not be interleaved with drawing, or
      // one tracker's stale-hide step can erase a square the other tracker
      // just drew.
      const preLastMoverPid = ((((data.move_number - 2) % 3) + 3) % 3);
      const lastMoverPid = ((((data.move_number - 1) % 3) + 3) % 3);
      hideMoveHighlight(AppState.prelastmove);
      hideMoveHighlight(AppState.lastmove);
      if (data.pre_last_move != null) {
        setMoveHighlight(
          AppState.prelastmove,
          data.pre_last_move,
          theme["pieces"]["color"][preLastMoverPid],
        );
      }
      if (data.last_move != null) {
        setMoveHighlight(
          AppState.lastmove,
          data.last_move,
          theme["pieces"]["color"][lastMoverPid],
        );
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
      board_layer.off("click tap", handleBoardClick);
      if (data.vote_needed && !data.finished) {
        if (data.onmove == AppState.view_pid) {
          showVoteModal(data.vote_results["kind"], data.vote_results);
        } else {
          AppState.movelabel_text = `${data.vote_results["kind"]} voting\nin progress`;
        }
      } else if (data.finished) {
        if (data.endgame === "draw") {
          gameover_text.text("GAME OVER\nDraw agreed");
        } else if (data.endgame === "resignation") {
          let wid;
          if (data.vote_results[0] == "D") {
            wid = 0;
          } else if (data.vote_results[1] == "D") {
            wid = 1;
          } else {
            wid = 2;
          }
          gameover_text.text("GAME OVER\n" + AppState.pid2name[wid] + " win");
        } else if (data.endgame === "stalemate") {
          gameover_text.text("GAME OVER\nStalemate");
        } else if (data.endgame === "repetition") {
          gameover_text.text("GAME OVER\nThreefold repetition");
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
        board_layer.on("click tap", handleBoardClick);
      }
    })
    .catch((response) => {
      console.error(
        `GameInfo error ${response.status}: ${response.statusText}`,
      );
      AppState.ready = true;
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
      AppState.gid2code = data.gid2code;
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
        // Vertical mirror of player 2's array (q0 = q2 + r2), so player 0's
        // rack is the vertical mirror image of player 2's — fills bottom-up
        // the same way player 2's fills toward the board.
        0: [
          6, 5, 4, 3, 2, 6, 5, 4, 3, 7, 6, 5, 4, 7, 6, 5, 8, 7, 6, 8, 7, 9, 8,
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
        // Vertical mirror of player 2's array (r0 = -r2).
        0: [
          7, 7, 7, 7, 7, 6, 6, 6, 6, 5, 5, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 1, 1,
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
      const elpiecesGroup = [group0el, group1, group2];
      for (let i = 0; i < MAX_ELIMINATED; i++) {
        for (let p = 0; p < 3; p++) {
          let x = q[p][i] / 1.2 + 0.5 * r[p][i] / 1.2 - 0.5;
          let y = (r[p][i] * Math.sqrt(3)) / 2 / 1.2;
          // Convert to group-local coordinates using each group's fixed
          // landscape/desktop construction anchor as the reference offset
          // (not the live, mutable AppState.anchor1/anchor2/anchor0el —
          // those change per orientation via applyAnchors(), and using them
          // here would double-apply the shift on top of the group's own
          // .position()). Player 0's reference (9.2, 6.9) mirrors player 2's
          // (9.2, -6.9) across y=0, matching the q0/r0 mirror above.
          if (p === 1) {
            x += 9.2;
            y += 6.9;
          } else if (p === 2) {
            x -= 9.2;
            y += 6.9;
          } else if (p === 0) {
            x -= 9.2;
            y -= 6.9;
          }
          AppState.elpieces[p][i] = createHexLabel(
            0,
            [x, y],
            theme["pieces"]["color"][AppState.seat2pid[p]],
            theme["pieces"]["stroke-color"] != theme["canvas"]["background"]
              ? 0.25
              : 0,
            "",
          );
          elpiecesGroup[p].add(AppState.elpieces[p][i]);
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
      pieces_layer.add(group0name, group0el, group1, group2);

      // game over
      top_layer.add(gameover);
      // lines
      interactive_layer.add(qline);
      interactive_layer.add(rline);
      interactive_layer.add(sline);
      board_layer.batchDraw();
      interactive_layer.batchDraw();
      pieces_layer.batchDraw();
      top_layer.batchDraw();

      applyInitialLayout();
      submit.disabled = true;
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      AppState.ready = true;
    })
    .catch((response) => {
      console.log(`BoardInfo error ${response.status}: ${response.statusText}`);
      AppState.ready = true;
      // window.location.reload();
    });
}

function boardSubmit() {
  submit.disabled = true;
  submit.className = "btn btn-secondary p-0 mb-0 col-12";
  submitText.textContent = "";
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
      submitText.textContent = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
    })
    .catch((response) => {
      submitText.textContent = "Submit";
      submit.className = "btn btn-secondary mb-2 col-12";
      loader.style.display = "none";
      alert(`BoardSubmit error ${response.status}: ${response.statusText}`);
      // window.location.reload();
    });
}

function debounce(fn, delayMs) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delayMs);
  };
}

window.addEventListener("resize", debounce(fitStageIntoDiv, 150));
window.addEventListener("orientationchange", doOnOrientationChange);
// Mobile browsers can silently invalidate a backgrounded tab's Konva hit
// canvases (the off-screen graphs used for click/tap hit-testing) even
// though the visible canvas repaints fine on return, leaving the board
// unclickable until reload. Force a hit-graph rebuild whenever the page
// regains visibility.
document.addEventListener("visibilitychange", function () {
  if (document.visibilityState === "visible") {
    board_layer.drawHit();
    interactive_layer.drawHit();
    pieces_layer.drawHit();
    top_layer.drawHit();
  }
});

// ready to go

boardInfo();

// Live updates: an SSE ping means a move/vote was persisted on this board
// (by another player or the bot) — never trust the pushed payload, always
// refetch full state through the existing authenticated GET. Use
// boardReset(), not boardInfo() directly: boardInfo() only creates and
// adds new per-gid Konva shapes, it never destroys the previous ones, so
// calling it a 2nd time on an already-drawn board leaves the old piece
// shapes on the layer alongside the new ones (the moved piece then
// visibly appears on both its old and new hex). boardReset() destroys the
// stale shapes first, exactly like every other post-initial-load refresh
// (boardSubmit(), forwardMove(), etc.) already does.
const rawToken = access_token.replace(/^Bearer\s+/, "");
const boardEvents = new EventSource(
  `${API_URL}/api/v1/manager/board/events?id=${id}&jwt=${encodeURIComponent(rawToken)}`,
);
boardEvents.onmessage = (event) => {
  // slog_length (chars, 4 per persisted move/vote) is a monotonically
  // increasing counter — if it's no bigger than what boardInfo() already
  // confirmed synced, this ping is just the echo of this same tab's own
  // just-submitted move/vote (boardSubmit()/voteDraw()/voteResign() already
  // refreshed locally on success), or a stale duplicate. Skip the redundant
  // reset. Never trust the payload beyond this length comparison — actual
  // rendering always comes from a fresh authenticated refetch below.
  const payload = JSON.parse(event.data);
  if (payload.slog_length <= AppState.server_slog.length) {
    return;
  }
  // If the local player currently has an uncommitted candidate move/vote
  // staged (click-to-select, or backMove/forwardMove local navigation),
  // drop this ping rather than wiping their in-progress UI state out from
  // under them — self-corrects on the next event, or whenever they
  // themselves submit/reset (which refreshes the board anyway).
  if (AppState.slog === AppState.server_slog) {
    boardReset();
  }
};
boardEvents.onerror = () => {
  // EventSource retries automatically on transient network blips, but
  // browsers never expose the failed request's HTTP status on an 'error'
  // event, so an expired JWT looks identical to a blip from here — it
  // would otherwise retry forever. Confirm with a real header-authenticated
  // request (the same GET boardInfo() already uses) before acting: only a
  // genuine 401/422 means the token is dead, not a network hiccup.
  apiFetchGet("/api/v1/manager/board?id=" + id.toString()).then((response) => {
    if (response.status === 401 || response.status === 422) {
      boardEvents.close();
      window.location.href = "/login";
    }
  });
};
