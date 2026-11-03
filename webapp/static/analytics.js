// Google Analytics 4 with an opt-in consent banner (Consent Mode v2, "basic"
// implementation): gtag.js is not loaded at all until the visitor accepts.
// Page config comes from window.TRICHESS_GA, set by templates/_analytics.html
// (built by webapp/analytics.py ga_config()). This file sends:
//  - the page view, user properties (player class) and the lobby/account
//    events queued server-side by analytics.track_event();
//  - prefs_snapshot: the logged-in user's display preferences, once a day
//    per browser and again whenever they change;
//  - gameplay milestones (game_started, first_move, vote_cast,
//    game_completed, archive_viewed) via window.trichessGame, which both
//    board renderers call — never moves or positions.
// The event catalogue is in webapp/analytics.py (BROWSER_EVENTS here).
(function () {
  const cfg = window.TRICHESS_GA;
  if (!cfg) return;
  const game = cfg.game; // board page context, or null

  const CONSENT_KEY = "ga_consent";
  let loaded = false;

  function getConsent() {
    return storageGet(CONSENT_KEY);
  }

  // Storage blocked: the choice applies to this page view only.
  function setConsent(value) {
    storageSet(CONSENT_KEY, value);
  }

  // Password-reset and email-verification links carry live tokens in the
  // path — never send those to Google, as page URL or as referrer.
  function scrub(url) {
    return url ? url.replace(/\/(reset|verify)\/[^/?#]+/, "/$1/:token") : url;
  }

  function load() {
    if (loaded) return;
    loaded = true;
    gtag("consent", "update", { analytics_storage: "granted" });
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(cfg.id);
    document.head.appendChild(s);
    gtag("js", new Date());
    gtag("set", "user_properties", cfg.user_properties);
    const pageConfig = {
      page_location: scrub(location.href),
      page_referrer: scrub(document.referrer),
      content_group: cfg.content_group,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
    };
    if (cfg.user_id) pageConfig.user_id = cfg.user_id;
    gtag("config", cfg.id, pageConfig);
    for (const ev of cfg.events) gtag("event", ev.name, ev.params);
    sendPrefsSnapshot();
    if (game) sendGameStarted();
  }

  function storageGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      // Storage blocked: the event may be sent again on a later page.
    }
  }

  // Event-scoped preferences, so GA can count users per board/theme/piece
  // set per day or week. Re-sent the same day only if they changed.
  function sendPrefsSnapshot() {
    if (!cfg.prefs) return;
    const p = cfg.prefs;
    const day = new Date().toISOString().slice(0, 10);
    const stamp = [day, cfg.user_id, p.board_renderer, p.ui_theme, p.piece_set].join("|");
    if (storageGet("ga_prefs_snapshot") === stamp) return;
    gtag("event", "prefs_snapshot", p);
    storageSet("ga_prefs_snapshot", stamp);
  }

  function deleteGaCookies() {
    const host = location.hostname;
    const domains = ["", host, "." + host, "." + host.split(".").slice(-2).join(".")];
    for (const c of document.cookie.split(";")) {
      const name = c.split("=")[0].trim();
      if (!name.startsWith("_ga")) continue;
      for (const d of domains) {
        document.cookie =
          name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/" + (d ? "; domain=" + d : "");
      }
    }
  }

  function hideBanner() {
    const el = document.getElementById("consentBanner");
    if (el) el.remove();
  }

  function showBanner() {
    if (document.getElementById("consentBanner")) return;
    const el = document.createElement("div");
    el.id = "consentBanner";
    el.className = "position-fixed bottom-0 start-0 end-0 p-3";
    el.style.zIndex = 1080;
    el.innerHTML = `
      <div class="container">
        <div class="card shadow">
          <div class="card-body d-flex flex-column flex-md-row align-items-md-center gap-3">
            <p class="mb-0 flex-grow-1">
              We'd like to use Google Analytics cookies to understand how visitors use Trichess,
              so we can improve it. No advertising, and nothing is set unless you accept.
              <a href="/help#privacy">Privacy details</a>
            </p>
            <div class="d-flex gap-2 flex-shrink-0">
              <button type="button" class="btn btn-outline-secondary" data-consent="denied">Reject</button>
              <button type="button" class="btn btn-primary" data-consent="granted">Accept</button>
            </div>
          </div>
        </div>
      </div>`;
    el.addEventListener("click", (e) => {
      const choice = e.target.getAttribute("data-consent");
      if (!choice) return;
      const previous = getConsent();
      setConsent(choice);
      hideBanner();
      if (choice === "granted") {
        load();
      } else if (loaded || previous === "granted") {
        // Withdrawal: drop GA cookies and reload so gtag.js is gone too.
        gtag("consent", "update", { analytics_storage: "denied" });
        deleteGaCookies();
        location.reload();
      }
    });
    document.body.appendChild(el);
  }

  const consent = getConsent();
  if (consent === "granted") {
    load();
  } else if (consent !== "denied") {
    showBanner();
  }

  // Board page hooks, called by ondro.js and filio.js alike (with optional
  // chaining: this file isn't loaded when analytics is off). Events are sent
  // only once gtag is loaded, i.e. after consent.
  function sendGame(name, params) {
    if (loaded) {
      gtag("event", name, Object.assign(
        { game_type: game.game_type, board_renderer: game.board_renderer, seat: game.seat },
        params,
      ));
    }
  }

  // game_started: once per game and browser, on each player's first view of
  // a recently started game (so every player of the game reports it).
  function sendGameStarted() {
    if (!game.started_recently) return;
    const key = "ga_started_" + game.board_id;
    if (storageGet(key) !== null) return;
    sendGame("game_started", { wait_minutes: game.wait_minutes });
    storageSet(key, "1");
  }

  if (game) {
    const pageOpened = Date.now();
    const completedKey = "ga_completed_" + game.board_id;
    let startedUnfinished = null; // finished state at the page's first /info
    let endSent = false;
    let hasMoved = game.has_moved;

    // game_completed goes out once per game and browser, whether this page
    // saw the game end or opened it shortly afterwards.
    function completionReported() {
      return storageGet(completedKey) !== null;
    }

    function markCompletionReported() {
      storageSet(completedKey, "1");
    }

    // Rank by score out of 2.0; ties share the better place (a draw is 1st
    // for everyone, a 2/0/0 checkmate 1st, 2nd, 2nd).
    function placement(scores, seat) {
      const own = Number(scores[seat]) || 0;
      const above = [0, 1, 2].filter((s) => (Number(scores[s]) || 0) > own + 1e-9).length;
      return ["1st", "2nd", "3rd"][above];
    }

    window.trichessGame = {
      // Every /api/v1/game/info response for the committed position.
      info(data) {
        if (startedUnfinished === null) {
          startedUnfinished = !data.finished;
          if (data.finished) sendGame("archive_viewed", { context: "game" });
        }
        if (!data.finished || endSent) return;
        // Seen ending here, or a recently finished game opened for the
        // first time; stepping through history or old games never count.
        if (!startedUnfinished && !game.finished_recently) return;
        endSent = true;
        if (!loaded || completionReported()) return;
        const duration = startedUnfinished
          ? game.started_minutes_ago + Math.floor((Date.now() - pageOpened) / 60000)
          : game.duration_minutes;
        const scores = data.score || {};
        sendGame("game_completed", {
          endgame: data.endgame,
          duration_minutes: duration,
          total_turns: data.move_number,
          placement: placement(scores, game.seat),
          points: Math.round((Number(scores[game.seat]) || 0) * 100) / 100,
        });
        markCompletionReported();
      },
      // After a successful board submit; the last slog chunk tells a move
      // from a draw (s/S) or resign (r/R) vote.
      submitted(slog) {
        const tag = slog.slice(-4, -3);
        if (tag === "s" || tag === "S") {
          sendGame("vote_cast", { kind: "draw" });
        } else if (tag === "r" || tag === "R") {
          sendGame("vote_cast", { kind: "resign" });
        } else if (tag && !hasMoved) {
          hasMoved = true;
          sendGame("first_move", {});
        }
      },
    };
  }

  const settings = document.getElementById("cookieSettings");
  if (settings) {
    settings.addEventListener("click", (e) => {
      e.preventDefault();
      showBanner();
    });
  }
})();
