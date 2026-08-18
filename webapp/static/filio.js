const canvas0 = document.getElementById("canvas");
canvas0.addEventListener("mouseclick", Click_Board);
let portrait = true
let r = 82
let boardXoffset = -411;
let boardYoffset = 8;
let piece_size = 15;
let mame_size = "150px";
let info_size = "100px"; //r.toString()+"px";
let canW = 0;
let canH = 0;

const ctx0 = canvas0.getContext("2d");
ctx0.lineCap = "round";
const url = `${window.location.protocol}//${window.location.host}`;
const bpiece_lineWidth = 0.2;
const epiece_lineWidth = 0.3;
const lineWidth = 5  ;
const lineStroke = 20;
const modal_wt = new bootstrap.Modal(document.getElementById("waitingMsg"));
const modal_go = new bootstrap.Modal(document.getElementById("gameOver"));
const modalDraw = new bootstrap.Modal(document.getElementById("voteDialog"));
// todo vsetky konstanty vytiahnut sem
let SemaforGreen = true;
let SemaforWait = false;
// tools /////////////////////////////////////////////
function isMobile() {
  const regex =
    /Mobi|Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
  return regex.test(navigator.userAgent);
}
function wait_msg(yes) {
  const tx = document.getElementById("waitingText");
  if (yes && !SemaforWait) {
    SemaforWait = true;
    setTimeout(function () {
      if (SemaforWait) {
        tx.style.color = theme["canvas"]["info"];
        modal_wt.show();
      }
    }, 500);
  }
}
function debug(itext) {
  window.alert("Debug:" + itext);
}
function rotateArray(arr, rotateBy) {
  const n = arr.length;
  rotateBy %= n;
  return arr.slice(rotateBy).concat(arr.slice(0, rotateBy));
}
function draw_piece_common(
  i_piece,
  i_lineWidth = 1,
  i_lineColor = "#000000",
  i_fillColor = "#000000",
  i_x,
  i_y,
  i_rotate = 0,
  i_hp = piece_size,
  i_hs = 0,
  i_vs = 0,
  i_vp = piece_size,
) {
  if (i_piece != undefined || i_piece !== "") {
    var path = new Path2D(pieces_paths["pieces"][i_piece]);
    ctx0.save();
    ctx0.lineWidth = i_lineWidth;
    ctx0.fillStyle = i_fillColor;
    ctx0.strokeStyle = i_lineColor;
    ctx0.transform(i_hp, i_hs, i_vs, i_vp, i_x, i_y);
    ctx0.rotate((i_rotate * Math.PI) / 180);
    ctx0.fill(path);
    ctx0.stroke(path);
    ctx0.restore();
  }
}
// fetchData /////////////////////////////////////////////
class fetchData {
  constructor() {
    this.headers = {
      accept: "application/json",
      "Content-Type": "application/json",
      Authorization: "",
    };
  }
  semaforwait_green() {
    SemaforWait = false;
    modal_wt.hide();
  };
  fetchPOST(iurl, ijson, icallback) {
    const jsonData = JSON.stringify(ijson);
    const z = this.headers;
    fetch(iurl, {
      method: "POST",
      headers: this.headers,
      body: jsonData,
    })
      .then((response) => {
        wait_msg(true);
        if (!response.ok) {
          if (response.status === 401 || response.status === 422) {
            window.alert("Token expired!");
            location.reload();
          return;
          }
          else {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
        }
        return response.json();
      })
      .then((data) => {
        this.semaforwait_green();
        icallback(data);
      })
      .catch((error) => {
        this.semaforwait_green();
        if (!(response.status === 401 || response.status === 422)) {
          debug("fetchPOST:" + error + " url:" + iurl);
        }
      });
  }
  fetchGET(iurl, icallback) {
    fetch(iurl, {
      method: "GET",
      headers: this.headers,
    })
      .then((response) => {
        wait_msg(true);
        if (!response.ok) {
          if (response.status === 401 || response.status === 422) {
            window.alert("Token expired!");
            location.reload();
            return;
          } else {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
        }
        return response.json();
      })
      .then((data) => {
        this.semaforwait_green();
        icallback(data);
      })
      .catch((error) => {
        //wait_msg(false)
        this.semaforwait_green();
        if (!(response.status === 401 || response.status === 422)) {
          debug("fetchGET:" + error + " url:" + iurl);
        }
      });
  }
}
// ssel - promotion ////////////////////////////////////////////////
class ssel {
  constructor() {
    this.active = false;
    this.selx = 0;
    this.sely = 0;
    this.ps = 0
    this.line = [];
    this.line[0] = new llines();
    this.line[0].set_text("Select piece:");
    this.line[0].set(
        2160,
        1040,
        "center",
        200,
        info_size + " " + theme["pieces"]["font-family"],
        theme["canvas"]["info"],
    );
    this.line[1] = new llines();
    this.line[0].set_piece("QRBN");
    this.line[1].set(
        2463,
        1170,
        "right",
        200,
        info_size + " " + theme["pieces"]["font-family"],
        "green",
        2,
        theme["pieces"]["stroke-color"],
    );
  }
  set() {
    if (portrait) {
      this.line[0].pos_x = 1080;
      this.line[0].pos_y = 1300;
      this.line[0].length = 200
      this.line[1].pos_x = 1320;
      this.line[1].pos_y = 1420;
      this.line[1].length = 200
      this.selx = 870;
      this.sely = 1364;
      this.ps = piece_size * 9;
      ctx0.rect(650, 1170, 860, 330);
    }
    else {
      this.line[0].pos_x = 2160;
      this.line[0].pos_y = 1040;
      this.line[0].length = 200
      this.line[1].pos_x = 2463;
      this.line[1].pos_y = 1170;
      this.line[1].length = 200
      this.selx = 1900;
      this.sely = 1100;
      this.ps = piece_size * 9;
      ctx0.rect(1670, 894, 978, 375);
    }
  }
  write() {
    ctx0.save();
    ctx0.beginPath();
    ctx0.fillStyle = theme["canvas"]["background"];
    this.set();
    for (let i = 0; i < 4; i++) {
      ctx0.rect(this.selx + i * this.ps, this.sely, this.ps, this.ps);
    }
    ctx0.fill();
    ctx0.closePath();
    ctx0.stroke();
    ctx0.restore();
    this.line[0].write();
    this.line[1].draw();
    this.active = true;
    ctx0.restore();
  }
  getpromo(ix, iy) {
    const ps = piece_size * 9;
    const pcs = ["N", "B", "R", "Q"];
    for (let i = 0; i < 4; i++) {
      ctx0.fillStyle = "green";
      ctx0.rect(this.selx + i * this.ps, this.sely, this.ps, this.ps);
      ctx0.fill();
      if (
          this.selx + i * this.ps < ix &&
          ix < this.selx + (i + 1) * this.ps &&
          this.sely < iy &&
          iy < this.sely + this.ps
      ) {
        SS.active = false;
        return pcs[i];
      }
    }
    SS.active = false;
    return "";
  }
}
// llines ////////////////////////////////////////////////
class llines {
  constructor(
  ) {
    this.player_id = -1; //todo ?
    this.text = "";
    this.pos_x = 0;
    this.pos_y = 0;
    this.align = "";
    this.length = 0; //todo ?
    this.font = "";
    this.color = "";
    this.strokeLine = 0;
    this.strokeColor = "";
    this.text_width = 0;
    this.text_width_old = 0;
    this.text_height = 0;
  }
  set(
    ipos_x,
    ipos_y,
    ialign,
    ilength,
    ifont,
    icolor,
    istrokeLine,
    istrokeColor,
  ) {
    //this.player_id = -1;
    this.pos_x = ipos_x;
    this.pos_y = ipos_y;
    this.align = ialign;
    this.length = ilength;
    this.font = ifont;
    this.color = icolor;
    this.strokeLine = istrokeLine;
    this.strokeColor = istrokeColor;
  }
  set_text(itext) {
    ctx0.save();
    ctx0.font = this.font
    this.text_width_old = this.text_width
    this.text_width = ctx0.measureText(itext).width;
    this.text_height = parseInt(ctx0.font.match(/\d+/), 10);
    this.text = itext;
    ctx0.restore();
  }
  set_piece(itext) {
    ctx0.save();
    ctx0.font = this.font
    this.text_width_old = this.text_width
    this.text_width = itext.length;
    this.text_height = parseInt(ctx0.font.match(/\d+/), 10);
    this.text = itext;
    ctx0.restore();
  }

  write() {
    ctx0.save();
    ctx0.beginPath();
    ctx0.font = this.font;
    ctx0.textAlign = this.align;
    ctx0.fillStyle = this.color;
    ctx0.lineWidth = this.strokeLine;
    ctx0.lineJoin = "circle";
    ctx0.strokeStyle = this.strokeColor;
    if (this.strokeLine != undefined) {
      ctx0.lineWidth = undefined;
      ctx0.strokeStyle = undefined;
      ctx0.strokeText(this.text, this.pos_x, this.pos_y);
    }
    ctx0.fillText(this.text, this.pos_x, this.pos_y);
    ctx0.closePath();
    ctx0.restore();
  }
  draw() {
    // text zisti pocet znakov
    if (!(this.text == "" || this.text == undefined)) {
      let offset = piece_size * 6;
      var dist = piece_size * 9;
      var align = 1;
      var strokeColor = this.strokeColor;
      var c = 0;
      let center_cor = 0;
      if (this.align == "right") {
        align = -1;
      }
      if (this.align == "center") {
        center_cor = -200;
        align = -1;
        offset =  -1*(piece_size *4.5)*(this.text.length-1)
      }

      for (let i = 0; i < this.text.length; i++) {
        if (this.text[i] == "B" && this.player_id != -1) {
          strokeColor = B.bishop_elim[this.player_id][c];
          c++;
        }
        draw_piece_common(
          this.text[i], //elimineted pieces
          epiece_lineWidth,
          strokeColor,
          this.color,
          this.pos_x + align * (offset + i * dist),
          this.pos_y,
        );
      }
    }
  }
  clear_text() {
    let corr = this.text_height/3;
    //ctx0.closePath()
    //ctx0.save();
    //ctx0.fillStyle = "red"
    if (this.align === 'left') {
      ctx0.clearRect(this.pos_x,this.pos_y + corr ,this.text_width_old,-this.text_height - corr);
    }
    if (this.align === 'center') {
      ctx0.clearRect(this.pos_x-this.text_width_old/2  ,this.pos_y + corr, this.text_width_old,-this.text_height - corr);
    }
    if (this.align === 'right') {
      ctx0.clearRect(this.pos_x,this.pos_y + corr ,-this.text_width_old,-this.text_height - corr);
    }
    //ctx0.fill()
    //ctx0.closePath()
    //ctx0.restore();
  }
  clear_piece() {
    let offset = piece_size ;
    //ctx0.save();
    //ctx0.fillStyle = "blue"
    let p = piece_size * 9.6
    if (this.text_width_old !== 0) {
      if (this.align === 'left') {
        ctx0.clearRect(this.pos_x+offset,this.pos_y+p/2, p * this.text_width_old, -p)
      }
      if (this.align === 'center') {
        ctx0.clearRect(this.pos_x-(p * this.text_width_old/2),this.pos_y+p/2, p * this.text_width_old, -p)
      }
      if (this.align === 'right') {
        ctx0.clearRect(this.pos_x-offset,this.pos_y+p/2, -p * this.text_width_old, -p)
      }
    }
    //ctx0.fill()
    //ctx0.closePath()
    //ctx0.restore();
  }
}
// iinfo  ////////////////////////////////////////////////
class iinfo {
  constructor(iinfo_id, ipos_x, ipos_y, ialign, ivert) {
    this.info_id = iinfo_id;
    this.x = ipos_x;
    this.y = ipos_y;
    this.align = ialign;
    this.vert = ivert;
    this.lines = [];
    for (let i = 0; i < 8; i++) {
      this.lines[i] = new llines
    }
  }
  set(iinfo_id, ipos_x, ipos_y, ialign, ivert) {
    this.info_id = iinfo_id;
    this.x = ipos_x;
    this.y = ipos_y;
    this.align = ialign;
    this.vert = ivert;
    var line_len = 260;
    var line_high = 1.5 * r;
    //set lines
    line_len = line_len - 30;
    var inf_ofs = 0;
    const dist_top = 30; // top and bottom distance
    var nam_ofs = (Number(mame_size.substring(0, mame_size.length - 2)) + dist_top) * ivert;
    if (ivert == -1) {
      nam_ofs = dist_top * ivert;
    }
    if (ivert == 1) {
      inf_ofs =
        nam_ofs +
        dist_top +
        Number(info_size.substring(0, info_size.length - 2));
    } else {
      inf_ofs =
        (Number(mame_size.substring(0, mame_size.length - 2)) + dist_top) *
          ivert +
        dist_top * ivert;
    }
    // info panel
    if (iinfo_id == 3) {
      //todo
      let x_corr=0 //correction
      let y_corr=0 //correction
      for (let i = 0; i < 8; i++) {
        if (portrait && i>2) {
          x_corr=canW/2
          y_corr=line_high*3
        }
        this.lines[i].set(
          ipos_x+x_corr,
          ipos_y + line_high * i * ivert+y_corr,
          ialign,
          line_len,
          info_size + " " + theme["canvas"]["font-family"],
          theme["canvas"]["info"],
        );
      }
    }
    // players info
    else {
      // player name
      this.lines[0].set(
        ipos_x,
        ipos_y + nam_ofs,
        ialign,
        line_len,
        mame_size + " " + theme["canvas"]["font-family"],
        theme["canvas"]["name"],
      );
      this.lines[1].set(
        ipos_x,
        ipos_y + inf_ofs,
        ialign,
        line_len,
        info_size + " " + theme["canvas"]["font-family"],
        theme["pieces"]["color"][iinfo_id],
        10,
        theme["pieces"]["stroke-color"],
      );
      // eliminated
      var ofs =
        inf_ofs +
        (40 + Number(mame_size.substring(0, mame_size.length - 2))) * ivert;
      if (ivert == 1) {
        ofs = ofs - 70;
      } //todo
      let line_num = 0
      if (portrait) {
        line_num = 8
      }
      else {
        line_num = 7
      }
      for (let i = 2; i < line_num; i++) {
        line_len = line_len - 18;
        this.lines[i].set(
          ipos_x,
          ipos_y + ofs + (i - 2) * line_high * ivert,
          ialign,
          line_len,
          (piece_size * 15).toString() + " " + theme["canvas"]["font-family"],
          theme["pieces"]["color"][iinfo_id],
          2,
          theme["pieces"]["stroke-color"],
        );
      }
    }
  }
  write() {
    //this.clear()
    for (let i = 0; i < 2; i++) {
      if (this.lines[i].text !== "") {
        this.lines[i].clear_text()
        this.lines[i].write();
      }
    }
    let row_cnt = 7
    if (portrait) {
      row_cnt = 8
    }
    for (let i = 2; i < row_cnt; i++) {
      if (this.info_id != 3) {
        this.lines[i].clear_piece(); //elim pieces
        this.lines[i].draw(); //elim pieces
      } else { // info panel 3 power lines...
        this.lines[i].clear_text()
        this.lines[i].write();
      }
    }
    }
  }
class iinfos {
  constructor() {
    var a = theme["canvas"]["font-family"];
    var dist_rl = 150;
    this.players = [];
    this.index = [];
    this.panel = [];
    this.pieces_value = [];
    this.vote_results = null;
    this.eliminations = [];

    for (let i = 0; i < 4; i++) {
      this.panel[i] = new iinfo(0, 0, 0, "", 0);
    }
    this.set_oriantation();
  }
  set_oriantation() {
    if (portrait) {
      this.set_portrait();
    }
    else {
      this.set_landscape();
    }
  }
  set_portrait() {
      this.panel[0].set(0, canW/2 , 2270 , "center", 1);
      this.panel[1].set(1, 0, 2270, "left", 1);
      this.panel[2].set(2, canW, 2270, "right", 1);
      this.panel[3].set(3, 0, 320, "left", -1);
  }
  set_landscape() {
      var dist_rl = 80;
      this.panel[0].set(0, canW - dist_rl, canH - 50, "right", -1);
      this.panel[1].set(1, dist_rl, 0, "left", 1);
      this.panel[2].set(2, canW - dist_rl, 0, "right", 1);
      this.panel[3].set(3, dist_rl, canH - 50, "left", -1);
  }
  set(idata) {
    this.index = rotateArray([0, 1, 2], B.view_player); //todo
    this.set_oriantation();
    this.panel[3].lines[5].set_text("# " + ID.toString());
    this.vote_results = idata.vote_results;
    this.pieces_value = idata.pieces_value;
    this.eliminations = idata.eliminations;

    let last_move = B.slog.substring((B.slog_pointer-1) * 4, B.slog_pointer * 4);
    let a = last_move.substring(0,1)
    if (a == 's' || a == 'S') {
      last_move = ""
    }
    else {
      last_move = last_move.substr(0,2)+"-"+last_move.substr(2,2)
    }
    let cursor_coor = ""
    if (B.gid_new>0) {
      cursor_coor = B.hexs[B.gid_new].sc
    }
    this.panel[3].lines[4].set_text("Move: " + B.move_number_org.toString() + "/" + B.move_number.toString()+"  "+last_move)//+"-"+cursor_coor
    if (B.gid_new>0){
      this.panel[3].lines[3].set_text("Cursor: " + B.hexs[B.gid_new].code)
    }
    //vote history
    if (idata.vote_results != null) {
      let verb = " offers ";
      let j = 0;
      let vc = 0; // vote count
      for (let i = 0; i < 3; i++) {
        if (idata.vote_results[i] != "X") {
          vc++;
        }
      }
      let index2 = rotateArray([0, 1, 2], idata.onmove - vc); //todo
      for (let i = 0; i < 3; i++) {
        if (idata.vote_results[index2[i]] == "A") {
          this.panel[3].lines[2 - j].set_text(this.players[index2[i]].substr(0, 12)+verb+idata.vote_results.kind+".");
          verb = " accepts ";
          j++;
        } else if (idata.vote_results[index2[i]] == "D") {
          this.panel[3].lines[2 - j].set_text(this.players[index2[i]]+" declines "+idata.vote_results.kind+".");
          j++;
        } else {
          //this.panel[3].lines[2 - j].set_text("");
          //j++;
        }
      }
    }
    else {
      this.panel[3].lines[2].set_text("Power:");
    }
    this.elim_lines();
    for (let i = 0; i < 3; i++) {
      this.panel[i].lines[0].set_text(this.players[this.index[i]]); // set players names
      for (let z = 0; z < 7; z++) {
        this.panel[i].lines[z].player_id = this.index[i];
      }
    }
    for (let i = 0; i < 3; i++) {
      // highlight players
      if (this.index[i] == idata.onmove) {
        this.panel[i].lines[0].strokeLine = 0;
        this.panel[i].lines[0].strokeColor = theme["canvas"]["name"];
        this.panel[i].lines[0].color = theme["canvas"]["name_onmove"];
      } else {
        this.panel[i].lines[0].strokeLine = 0;
        this.panel[i].lines[0].color = theme["canvas"]["name"];
      }
      // eliminated_value / pieces_value
      this.panel[i].lines[1].color =
        theme["pieces"]["color"][(this.index[i] + 2) % 3];
      this.panel[i].lines[1].text = ""; // idata.eliminated_value[this.index[i]].toString()
      // set eliminated pieces
      var e = elim2array(idata.eliminated[this.index[i]]);
      if (e != undefined) {
        for (let j = 2; j < this.panel[i].lines.length; j++) {
          if (e[j-2] !== undefined) {
            this.panel[i].lines[j].color =  theme["pieces"]["color"][this.index[i]];
            this.panel[i].lines[j].set_piece(e[j-2]);
          }
          else { // because need to delete empty lines
            this.panel[i].lines[j].set_piece("");
          }
        }
      }
    }
  }
  daw_line(ix, iy, i_width, i_high, i_color) {
    if (i_width == 0 || undefined) {
      return;
    }
    ctx0.save();
    ctx0.lineWidth = 5; //*epiece_lineWidth
    ctx0.strokeStyle = theme["pieces"]["stroke-color"];
    ctx0.beginPath();
    ctx0.fillStyle = i_color;
    ctx0.rect(ix, iy, i_width, i_high);
    ctx0.fill();
    ctx0.stroke();
    ctx0.closePath();
    ctx0.restore();
  }
  clear_power_lines() {
    let high = r*0.7;
    this.panel[3].lines[0].text_width_old = r*13
    this.panel[3].lines[0].text_height = high*2
    this.panel[3].lines[0].clear_text()
    this.panel[3].lines[1].text_width_old = r*13
    this.panel[3].lines[1].text_height = high*2
    this.panel[3].lines[1].clear_text()
  }
  power_lines() {
    if (this.vote_results == null) {
      let high = r*0.7;
      let x = this.panel[3].lines[0].pos_x+4 // 4 due to stroke
      let y = this.panel[3].lines[0].pos_y
      let p = 0; //power
      this.clear_power_lines();
      for (let i = 0; i < 3; i++) {
        //draw hex
        y = y - high;
        p = this.pieces_value[this.index[i]];
        this.daw_line(
          x,
          y,
          (r/4) * p,
          high,
          theme["pieces"]["color"][this.index[i] % 3],
        );
      }
      //this.panel[3].lines[2].pos_y = y - 20
    }
  }
  clear_elim_lines() {
    for (let i = 0; i < 3; i++) {
      this.panel[i].lines[1].text_width_old = r * 8
      this.panel[i].lines[1].text_height = Number(info_size.substring(0, info_size.length - 2));
      this.panel[i].lines[1].clear_text()
    }
  }
  elim_lines() {
    this.clear_elim_lines()
    let high = r/4;
    let step = r/7;
    let al = -1;
    for (let i = 0; i < 3; i++) {
      if (this.panel[i].align == "left") {
        al = 1;
      } else {
        al = -1;
      }
      let ind = rotateArray([0, 1, 2], i + B.view_player); //todo
      let e1 = this.eliminations[ind[0]][ind[1]];
      let e2 = this.eliminations[ind[0]][ind[2]];
      let x = this.panel[i].lines[1].pos_x+al*4;
      let y = this.panel[i].lines[1].pos_y-10;
      let corr1 = 0;
      let corr2 = 0;
      if (this.panel[i].lines[1].align == "center" && e1!=0 && e2!=0 ) {
        corr1 = (e1 * step)/2;
        corr2 = (e2 * step)/2;
      }
      this.daw_line(
        x+corr1,
        y,
        al * e1 * step,
        high * this.panel[i].vert,
        theme["pieces"]["color"][ind[1]],
      );
      this.daw_line(
        x+corr2,
        y - high,
        al * e2 * step,
        high * this.panel[i].vert,
        theme["pieces"]["color"][ind[2]],
      );
    }
  }
  write() {
    if (this.vote_results !== null) {
      this.clear_power_lines()
    }
    for (let i = 0; i < 4; i++) {
      this.panel[i].write();
    }
    if (this.vote_results == null) {
      this.power_lines();
    }
  }
  getVoteHist() {
    const msg = this.panel[3].lines.map(({ text }) => text);
    const msg1 = msg.slice(0, 3).reverse();
    return msg1.join("<br>");
  }
}
// hex ///////////////////////////////////////////////////
function  setx(a,b) {
  return (a + b * 0.5) * (r * Math.sqrt(3)) + boardXoffset;
  }
  function sety(b) {
    return   (1 + b * 1.5) * r + boardYoffset;
  }
class hex {
  constructor(a, b, id) {
    this.a = a
    this.b = b
    this.x = setx(a,b);
    this.y = sety(b);
    this.code = "";
    this.id = id;
    this.piece = { piece: "", player_id: -1 };
    this.hex_color = theme["board"]["hex_color"][(2 * a + b) % 3];
    this.lumi = undefined; // R,G,B, luminiscence todo
    this.show_flag = true; // true means to redraw the hex todo revizia ci to pouzouzivam.
    this.valid_flag = false;
    this.promo_flag = false;
  }
  set(ipiece) {
    if (
      ipiece.piece != this.piece.piece ||
      ipiece.player_id != this.piece.player_id
    ) {
      this.show_flag = true;
    }
    this.piece.piece = ipiece.piece;
    this.piece.player_id = ipiece.player_id;
  }
  setlumi(ilumi) {
    this.lumi = ilumi;
    this.show_flag = true;
  }
  draw() {
    ctx0.save();
    ctx0.beginPath();
    let color = theme["board"]["hex_border"]
    if ( theme["board"]["hex_border"]!== null ) {
      ctx0.lineWidth = r/30;
      ctx0.strokeStyle = theme["board"]["hex_border"];
    }
    for (let i = 0; i < 6; i++) {
      //draw hex tile
      ctx0.lineTo(
        this.x + r * Math.cos((i + 0.5) * (Math.PI / 3)),
        this.y + r * Math.sin((i + 0.5) * (Math.PI / 3)),
      );
    }
    ctx0.fillStyle = this.hex_color;
    if (this.lumi != undefined) {
      ctx0.fillStyle = this.hex_color;
      ctx0.fill();
      ctx0.fillStyle = this.lumi;
    } else {
      ctx0.fillStyle = this.hex_color;
    }
    ctx0.closePath();
    ctx0.fill();
    if ( theme["board"]["hex_border"]!== null ) {
       ctx0.stroke()
    }
    ctx0.restore();
  }
  draw_piece2(i_lineWidth = 1, i_lineColor = "#000000") {
    draw_piece_common(
      this.piece.piece,
      i_lineWidth,
      i_lineColor,
      theme["pieces"]["color"][this.piece.player_id],
      this.x,
      this.y,
    );
  }
  draw_hex(i_width, i_color, i_r) {
    ctx0.save();
    ctx0.lineWidth = i_width;
    ctx0.strokeStyle = i_color;
    ctx0.beginPath();
    for (let i = 0; i < 6; i++) {
      //draw hex
      ctx0.lineTo(
        this.x + r * i_r * Math.cos((i + 0.5) * (Math.PI / 3)),
        this.y + r * i_r * Math.sin((i + 0.5) * (Math.PI / 3)),
      );
    }
    ctx0.closePath();
    ctx0.stroke();
    ctx0.restore();
  }
  line_intersect2(ax, bo) {
    if (ax.u2 / ax.u1 == bo.z2 / bo.z1) {
      return;
    }
    if (ax.u2 == 0) {
      var s = (ax.a2 - bo.b2) / bo.z2;
    } else {
      var s =
        ((ax.u1 / ax.u2) * (bo.b2 - ax.a2) + ax.a1 - bo.b1) /
        (bo.z1 - (ax.u1 / ax.u2) * bo.z2);
    }
    var t = (bo.b1 + s * bo.z1 - ax.a1) / ax.u1;
    var x = ax.a1 + t * ax.u1;
    var y = ax.a2 + t * ax.u2;
    (B.hexs[84].x, B.hexs[84].y);
    var dist = Math.sqrt(
      Math.pow(B.hexs[84].x - x, 2) + Math.pow(B.hexs[84].y - y, 2),
    );
    if (dist < r * 12.3) {
      return { x: Math.round(x), y: Math.round(y) };
    }
    return;
  }
  draw_mark(i_kind) {
    this.show_flag = true;
    ctx0.save();
    ctx0.strokeStyle = theme["board"]["valid_move"];
    ctx0.lineWidth = lineWidth;
    ctx0.beginPath();
    if (i_kind == "safe") {
      ctx0.arc(this.x, this.y, r / 2, 0, 2 * Math.PI);
    } else if (i_kind == "rect") {
      this.draw_hex(lineWidth, theme["board"]["valid_move"], 0.85); //curso
      ctx0.lineWidth = lineWidth/2 ;
      var axis = [];
      axis[0] = { a1: this.x, a2: this.y, u1: B.hexs[0].x, u2: 0 };
      axis[1] = { a1: this.x, a2: this.y, u1: 1 / 2, u2: Math.sqrt(3) / 2 };
      axis[2] = { a1: this.x, a2: this.y, u1: -1 / 2, u2: Math.sqrt(3) / 2 };
      var point = [];
      var j = 0;
      for (let k = 0; k < 3; k++) {
        for (let i = 0; i < 6; i++) {
          var ret = this.line_intersect2(axis[k], B.border[i]);
          if (ret != undefined) {
            //point[j] = ret
            if (
              point[j - 1] == undefined ||
              !(ret.x == point[j - 1].x && ret.y == point[j - 1].y)
            ) {
              point.push(ret);
              j++;
            }
          }
        }
        ctx0.moveTo(point[0].x, point[0].y);
        ctx0.lineTo(point[1].x, point[1].y);
        j = 0;
        point = [];
      }
    } else if (i_kind == "attack") {
      ctx0.moveTo(this.x - r / 1.6, this.y - r / 1.6);
      ctx0.lineTo(this.x + r / 1.6, this.y + r / 1.6);
      ctx0.moveTo(this.x + r / 1.6, this.y - r / 1.6);
      ctx0.lineTo(this.x - r / 1.6, this.y + r / 1.6);
    } else {
      const a = 0;
    }
    ctx0.stroke();
    ctx0.closePath();
    ctx0.restore();
  }
}
// board /////////////////////////////////////////////////
class board {
  constructor() {
    this.hexs = [];
    this.gid_old = 85;
    this.gid_new = -1;
    this.slog = "";
    this.view_player = 0;
    this.view_player_org = 0;
    this.move_number = -1;
    this.move_number_org = -1;
    this.move_number_max = -1;
    this.last_move_from = -1;
    this.last_move_to = -1;
    this.pre_last_move_from = -1;
    this.pre_last_move_to = -1;
    this.onmove = 0;
    this.finished = false;
    this.endgame = "";
    this.hist_changed = false;
    this.border = [];
    this.bishop_elim = [];
    this.slog_pointer = -1; // todo slog_pointer vs this.move_number*
    this.vote_needed = false;
    this.vote_results_kind = "x";
  }
  set_border(){ //todo review
     this.border[0] = {
      b1: this.hexs[0].x,
      b2: this.hexs[0].y,
      z1: this.hexs[0].x,
      z2: 0,
    };
    this.border[1] = {
      b1: this.hexs[7].x,
      b2: this.hexs[7].y,
      z1: 1 / 2,
      z2: Math.sqrt(3) / 2,
    };
    this.border[2] = {
      b1: this.hexs[91].x,
      b2: this.hexs[91].y,
      z1: -1 / 2,
      z2: Math.sqrt(3) / 2,
    };
    this.border[3] = {
      b1: this.hexs[168].x,
      b2: this.hexs[168].y,
      z1: -this.hexs[168].y,
      z2: 0,
    };
    this.border[4] = {
      b1: this.hexs[161].x,
      b2: this.hexs[161].y,
      z1: -1 / 2,
      z2: -Math.sqrt(3) / 2,
    };
    this.border[5] = {
      b1: this.hexs[77].x,
      b2: this.hexs[77].y,
      z1: 1 / 2,
      z2: -Math.sqrt(3) / 2,
    };
  }
  init() {
    let cnt = 0;
    for (let i = 0; i < 15; i++) {
      for (let j = 0; j < 15; j++) {
        if (j + i > 6 && j < 15 && i < 15 && j + i < 22) {
          this.hexs[cnt] = new hex(j, i, cnt);
          cnt = ++cnt;
        }
      }
    }
    this.set_border();
  }
  init_xy() { //todo zjednotit s init
    let cnt = 0;
    for (let i = 0; i < 15; i++) {
      for (let j = 0; j < 15; j++) {
        if (j + i > 6 && j < 15 && i < 15 && j + i < 22) {
          this.hexs[cnt].x = setx(j, i);
          this.hexs[cnt].y = sety(i);
          cnt = ++cnt;
        }
      }
    }
   this.set_border();
  }
  bishop_elim_color() {
    var c = [];
    for (let j = 0; j < 3; j++) {
      c[j] = theme["board"]["hex_color"];
    }
    for (let z = 0; z < 169; z++) {
      if (this.hexs[z].piece.piece == "B") {
        var p = c[this.hexs[z].piece.player_id].slice();
        var t = p.indexOf(this.hexs[z].hex_color);
        if (t > -1) {
          // only splice array when item is found
          p.splice(t, 1); // 2nd parameter means remove one item only
          c[this.hexs[z].piece.player_id] = p;
        }
        //https://stackoverflow.com/questions/5767325/how-can-i-remove-a-specific-item-from-an-array-in-javascript
      }
    }
    this.bishop_elim = c;
  }
  set(idata) {
    const jdata = idata;
    this.move_number = jdata.move_number; //this.slog.length/4//jdata.move_number;
    this.finished = jdata.finished;
    this.endgame = jdata.endgame;
    this.onmove = jdata.onmove;
    this.vote_needed = jdata.vote_needed;
    if (jdata.vote_results != null) {
      this.vote_results_kind = jdata.vote_results.kind;
    }
    if (jdata.pre_last_move != null) {
      this.pre_last_move_from = jdata.pre_last_move.gid;
      this.pre_last_move_to = jdata.pre_last_move.tgid;
    }
    if (jdata.last_move != null) {
      this.last_move_from = jdata.last_move.gid;
      this.last_move_to = jdata.last_move.tgid;
    }
    if (this.move_number_org == -1){
      this.move_number_org = jdata.move_number; //this.slog.length/4//jdata.move_number;
    }
    if (this.move_number_max == -1) {
      this.move_number_max = jdata.move_number; //this.slog.length/4 //jdata.move_number;
    }
    for (let z = 0; z < 169; z++) {
      // clear
      this.hexs[z].set({ piece: "", player_id: -1 });
      //this.hexs[z].piece.piece = undefined
      this.hexs[z].setlumi(undefined);
    }
    for (let player_id in jdata.pieces) {
      // set pieses
      for (let j in jdata.pieces[player_id]) {
        const pcs = jdata.pieces[player_id][j];
        this.hexs[pcs.gid].set({
          piece: pcs.piece,
          player_id: Number(player_id),
        });
      }
    }
    // set chess by
    for (let player_id in jdata.chess_by) {
      for (let j in jdata.chess_by[player_id]) {
        const pcs = jdata.chess_by[player_id][j];
        this.hexs[pcs.gid].setlumi(
          theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"],
        );
        this.hexs[pcs.gid].draw_piece2(
          bpiece_lineWidth,
          theme["board"]["hint_lines"],
        );
      }
    }
    //king_pos
    if (
      !(
        jdata.chess_by[0].length == 0 &&
        jdata.chess_by[1].length == 0 &&
        jdata.chess_by[2].length == 0
      )
    ) {
      this.hexs[jdata.king_pos].setlumi(
        theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"],
      );
      this.hexs[jdata.king_pos].draw_piece2(
        bpiece_lineWidth,
        theme["board"]["hint_lines"],
      );
    }
    if (jdata.king_pos != 0) {
      //this.hexs[jdata.king_pos].setlumi(theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"])
    }
    this.bishop_elim_color();
  }
  set_code(idata) {
    for (let i = 0; i < 169; i++) {
      this.hexs[i].code = idata.gid2code[i]
    }
  }
  draw_tile() {
    for (let i = 0; i < 169; i++) {
      if (this.hexs[i].show_flag) {
        this.hexs[i].draw();
      }
    }
  }
  draw_pieces() {
    // mark last & prelast move
    let hex_size = 0.93;
    let hex_lineWidth = lineWidth*1.7;
    let hex_color =  "";
    if (this.last_move_from != null && this.last_move_from != -1) {
      hex_color =  theme["pieces"]["color"][this.hexs[this.last_move_to].piece.player_id]
      this.hexs[this.last_move_from].draw_hex(hex_lineWidth, hex_color, hex_size);
      this.hexs[this.last_move_to].draw_hex(hex_lineWidth, hex_color, hex_size);
    }
    if (this.pre_last_move_from != null && this.pre_last_move_from != -1) {
      hex_color =  theme["pieces"]["color"][this.hexs[this.pre_last_move_to].piece.player_id]
      this.hexs[this.pre_last_move_from].draw_hex(hex_lineWidth, hex_color, hex_size);
      this.hexs[this.pre_last_move_to].draw_hex(hex_lineWidth, hex_color, hex_size);
    }
    // draw piece
    for (let i = 0; i < 169; i++) {
      if (this.hexs[i].show_flag) {
        this.hexs[i].draw_piece2(bpiece_lineWidth);
      }
    }
  }
  getGid(ix, iy) {
    let d = 0;
    let d_min = 99999999;
    let r_x = 0;
    let r_y = 0;
    let r_i = 0;
    for (let i = 0; i < 169; i++) {
      d = Math.pow(ix - this.hexs[i].x, 2) + Math.pow(iy - this.hexs[i].y, 2);
      if (d < d_min) {
        d_min = d;
        r_x = this.hexs[i].x;
        r_y = this.hexs[i].y;
        r_i = this.hexs[i].id;
      }
    }
    if (d_min < 44000) {
      this.gid_old = this.gid_new;
      this.gid_new = r_i;
      return this.gid_new;
    }
    else {
      B.gid_new = -1;
    }
  }
  getSlog() {
    let slog = this.slog.substr(0, this.slog_pointer * 4);
    return slog;
  }
  get_gid_rotate() {
    let xc = this.hexs[84].x
    let yc = this.hexs[84].y
    let xp = this.hexs[this.gid_new].x
    let yp = this.hexs[this.gid_new].y
    let c = Math.sqrt( Math.pow(xc - xp, 2) +Math.pow(yc - yp, 2)); //radius
    if (c==0) {
      return 84
    }
    let a = (yp-yc)
    let b = (xp-xc)
    let angle = Math.asin(a/c)
    let a120 = 2*(Math.PI / 3)
    if (b<0) {
      angle = Math.PI - Math.asin(a/c)
    }
    angle = angle -  a120 // otocit o 120 stupnu
    let x = c*Math.cos(angle)+xc
    let y = c*Math.sin(angle)+yc
    for (let z = 0; z < 169; z++) {
      if (Math.round(this.hexs[z].x) == Math.round(x) &&  Math.round(this.hexs[z].y)  == Math.round(y)) {
      return z
      }
    }
    return -1
  }
  // move ---------------------------------------------
  moveValid() {
    if (B.gid_new>0){
      II.panel[3].lines[3].set_text("Cursor: " + B.hexs[B.gid_new].code)
      II.panel[3].lines[3].clear_text()
      II.panel[3].lines[3].write()
    if (
      !(
        this.hexs[this.gid_new].piece.piece != undefined &&
        this.hexs[this.gid_new].piece.player_id == this.onmove
      )
    ) {
      return;
    }
    F.fetchPOST(
      url + "/api/v1/move/valid",
      { slog: this.getSlog(), view_pid: this.view_player, gid: this.gid_new },
      Step_valid_moves,
    );
    }
  }
  moveMake(inew_piece = "") {
    if (this.gid_old == -1 || this.gid_old == this.gid_new || this.gid_new === -1) {
      return;
    }
    if (
      !(
        this.hexs[this.gid_old].piece.piece != undefined &&
        this.hexs[this.gid_old].piece.player_id == this.onmove
      )
    ) {
      return;
    }
    if (!this.hexs[this.gid_new].valid_flag) {
      return;
    }
    F.fetchPOST(
      url + "/api/v1/move/make",
      {
        slog: this.getSlog(),
        view_pid: this.view_player,
        gid: this.gid_old,
        tgid: this.gid_new,
        new_piece: inew_piece,
      },
      Step_make_move,
    );
  }
}
// Button ////////////////////////////////////////////////////////////////////////////////
class butt {
  constructor(iid, icolor) {
    this.id = iid;
    this.disabled = true;
    this.color_enable = icolor;
  }
}
//----------------------------------------------------
function elim2array(idata) {
  if (idata.length ==0) {
    return
  }
  const pcs_map1 = { "": "", P: "♟", N: "♞", B: "♝", R: "♜", Q: "♛", K: "♚" };
  const pcs_map2 = {
    "": "",
    "♟": "P",
    "♞": "N",
    "♝": "B",
    "♜": "R",
    "♛": "Q",
    "♚": "K",
  };
  let s = "";
  for (i in idata) {
    s = s + pcs_map1[idata[i]];
  }
  var t = Array.from(s)
    .sort()
    .reverse()
    .join("")
    .match(/(.)\1*/g);
  if (portrait && t[0].length > 4) {  //max 4 pawns one in line -> insert line
    t.unshift(t[0].substring(0,4))
    t[1] = t[1].substring(4)
  }

  //s = "";
  for (i in t) {
    t[i] = t[i].replaceAll(t[i].charAt(0), pcs_map2[t[i].charAt(0)]);
  }
  return t;
}
function Step_make_move(idata) {
  B.slog = idata.slog;
  B.slog_pointer = idata.slog.length / 4;
  B.hexs[B.gid_old].piece.piece = "";
  B.hexs[B.gid_old].piece.player_id = -1;
  if (B.move_number_org > B.move_number) {
    B.hist_changed = true;
  }
  B.move_number_max = B.move_number + 1;
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog, view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Step_valid_moves(idata) {
  for (let j = 0; j < 169; j++) {
    B.hexs[j].valid_flag = false;
    //B.hexs[j].promo_flag = false;
  }
  const jsonData = idata;
  for (let i in jsonData.targets) {
    const obj = jsonData.targets[i];
    B.hexs[obj.tgid].draw_mark(obj.kind); //todo
    B.hexs[obj.tgid].valid_flag = true;
    B.hexs[obj.tgid].chang_flag = true;
    B.hexs[obj.tgid].promo_flag = obj.promotion;
  }
  F.semaforwait_green();
}
function Step_1_settoken() {
  F.headers.Authorization = TOKEN;
  F.fetchGET(
    url + "/api/v1/manager/board?id=" + ID.toString(),
    Step_2_setplayers,
  );
}
function Step_2_setplayers(idata) {
  II.players = [idata.player_0, idata.player_1, idata.player_2];
  B.view_player = idata.view_pid;
  B.view_player_org = idata.view_pid;
  B.slog = idata.slog;
  B.slog_pointer = idata.slog.length / 4;
  B.set_code(idata)
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog, view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Step_5_game_info() {
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog, view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Step_4_set_votedraw(idata) {
  B.slog = idata.slog;
  B.slog_pointer = idata.slog.length / 4;
  F.fetchPOST(
    url + "/api/v1/manager/board",
    { id: ID, slog: B.slog },
    Step_5_game_info,
  );
}
function Step_3_setelim_board_and_draw(idata) {
  B.set(idata);
  B.draw_tile();
  B.draw_pieces();
  II.set(idata);
  II.write();
  II.elim_lines();
  if (SS.active) {
    SS.set()
    SS.write()
  }
  if (B.gid_new >= 0) {
    B.hexs[B.gid_new].draw_mark("rect") //show cursor
    B.moveValid();
    }
  button_control();
  if (
    idata.vote_needed &&
    B.view_player_org == B.onmove &&
    B.slog_pointer == B.slog.length / 4
  ) {
    window_vote(B.vote_results_kind, II.getVoteHist());
  }
  if (B.finished) {
    let name = II.players[B.onmove];
    let vp = document.getElementById("goVotePlayers");
    let ot = document.getElementById("gameOverText");
    ot.innerHTML = "GAME OVER !!!<br>" + B.endgame.toUpperCase();
    if (idata.vote_results == null) {
      vp.innerHTML = "<br>" + name + " lost :-(";
    } else if (
      B.vote_results_kind == "draw" ||
      B.vote_results_kind == "resign"
    ) {
      vp.innerHTML = II.getVoteHist();
    } else {

    }
    //score
    const rp0 = document.getElementById("goRatingPlayer0");
    const rp1 = document.getElementById("goRatingPlayer1");
    const rp2 = document.getElementById("goRatingPlayer2");
    rp0.innerHTML = "<td>" + II.players[0] + "</td> <td>" + idata.score[0] + "</td>";
    rp1.innerHTML = "<td>" + II.players[1] + "</td> <td>" + idata.score[1] + "</td>";
    rp2.innerHTML = "<td>" + II.players[2] + "</td> <td>" + idata.score[2] + "</td>";
    modal_go.show();
    F.semaforwait_green();
  }
}
function button_control() {
  if (B.move_number_org == B.move_number && B.slog_pointer == B.slog.length/4) {
    //&& SemaforVoteDraw
    document.getElementById("b_dr").disabled = false;
    document.getElementById("b_rs").disabled = false;
  } else {
    document.getElementById("b_dr").disabled = true;
    document.getElementById("b_rs").disabled = true;
  }
  if (B.finished) {
    document.getElementById("b_dr").disabled = true;
    document.getElementById("b_rs").disabled = true;
    document.getElementById("b_rt").disabled = true;
  }
  else {
    document.getElementById("b_rt").disabled = false;
  }
  if (
    B.move_number_org == B.move_number - 1 &&
    B.view_player_org == (B.onmove + 2) % 3 &&
    !B.hist_changed
  ) {
    document.getElementById("b_ok").disabled = false;
    document.getElementById("b_ok").style.backgroundColor = theme["canvas"]["name_onmove"];
  } else {
    document.getElementById("b_ok").style.backgroundColor = "#6c757d";
    document.getElementById("b_ok").disabled = true;
  }
  if (B.move_number == 0) {
    document.getElementById("b_bw").disabled = true;
  } else {
    document.getElementById("b_bw").disabled = false;
  }
  if (B.slog_pointer == B.slog.length / 4) {
    document.getElementById("b_fw").disabled = true;
  } else {
    document.getElementById("b_fw").disabled = false;
  }
}
function window_vote(ikind, itext) {
  //var modal = document.getElementById("voteDrawDialog");
  const vp = document.getElementById("votePlayers");
  const vk1 = document.getElementById("voteKind1");
  const vk2 = document.getElementById("voteKind2");
  const av = document.getElementById("acceptVote");
  vp.innerHTML = itext;
  vk1.innerHTML = ikind;
  vk2.innerHTML = ikind;
  if (ikind == "draw") {
    av.innerHTML = "accept";
  } else {
    av.innerHTML = "vote";
  }
  modalDraw.show();
}
// Click ////////////////////////////////////////////////////////////////////////////////
function Click_Vote(ivalue) {
  if (!B.vote_needed && !ivalue) {
    return; //chncel decline
  }
  SS.active = false;
  F.fetchPOST(
    url + "/api/v1/vote/" + B.vote_results_kind,
    { slog: B.slog, view_pid: B.view_player, vote: ivalue },
    Step_4_set_votedraw,
  );
}
function Click_Draw() {
  let b_decline = document.getElementById("b_decline");
  b_decline.style.display = "none";
  B.vote_results_kind = "draw";
  window_vote("draw", ["Do you want to offer the draw?"]);
}
function Click_Resign() {
  let b_decline = document.getElementById("b_decline");
  b_decline.style.display = "none";
  B.vote_results_kind = "resign";
  window_vote("resign", ["Do you want to offer the resignation?"]);
}
function Click_Demo() {
  function code2gid(code) {
    for (let z = 0; z < 169; z++) {
      if (code === B.hexs[z].code) {
        return z;
      }
    }
    return -1;
  }
  function fff_valid() {
      B.moveValid();
  }
  const slog = B.slog;
  B.slog = "";
  let point = 0;
  //B.slog_pointer = 0;
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function runLoopWithDelay() {
  B.slog_pointer = 0;
  II.clear_elim_lines()
  let row_cnt = 7
    if (portrait) {  row_cnt = 8   };
    for (let j = 0; j < 3; j++) {
      for (let i = 2; i < row_cnt; i++) {
        II.panel[j].lines[i].set_text("")
      }
    }
  //////////////////////////////////////////////////////////////////////
  for (let i = 1; i <= 100; i++) {
    F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog, view_pid: B.view_player },
      Step_3_setelim_board_and_draw,
    );
    await delay(500);
    B.draw_tile(); // remove cursor
    B.draw_pieces();
    await delay(2000);
    let code1 = slog.substring((B.slog_pointer*4),(B.slog_pointer*4)+2)
    B.gid_new = code2gid(code1)
    B.hexs[B.gid_new].draw_mark("rect")  //cursor start move
    await delay(500);
    fff_valid(); // show valid moves
    await delay(1000);
    B.draw_tile(); // remove cursor
    B.draw_pieces();
    B.moveValid();; // show valid moves
    //await delay(1500);
    let code2 = slog.substring((B.slog_pointer*4)+2,(B.slog_pointer*4)+4)
    B.gid_old = B.gid_new;
    B.gid_new = code2gid(code2)
    B.hexs[B.gid_new].draw_mark("rect")
    await delay(500);
    B.draw_tile(); // remove cursor
    B.draw_pieces();
    B.moveMake();
    B.slog = B.slog + B.hexs[B.gid_old].code + B.hexs[B.gid_new].code
    B.slog_pointer = B.slog_pointer +1
  }
}
runLoopWithDelay();
}
function Click_Backward() {
  SS.active = false;
  B.slog_pointer = B.slog_pointer - 1;
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog.substr(0, B.slog_pointer * 4), view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Click_Forward() {
  SS.active = false;
  B.slog_pointer = B.slog_pointer + 1;
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: B.slog.substr(0, B.slog_pointer * 4), view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Click_OK() {
  SS.active = false;
  if (
    B.move_number_org == B.move_number - 1 &&
    B.view_player_org == (B.onmove + 2) % 3
  ) {
    F.fetchPOST(
      url + "/api/v1/manager/board",
      { id: ID, slog: B.getSlog() },
      function () {
        F.semaforwait_green()
      },
    );
  }
  B.move_number_org = -1;
  B.move_number_max = -1;
  document.getElementById("b_ok").disabled = false;
  document.getElementById("b_ok").style.backgroundColor = "#9fa5aa";
  B.hist_changed = false;
}
function Click_Refresh() {
  B.move_number_max = -1;
  B.move_number_org = -1;
  B.hist_changed = false;
  II.panel[3].lines[3].set_text("")      // remove cursor
  B.gid_new = -1;
  F.fetchGET(
    url + "/api/v1/manager/board?id=" + ID.toString()+"&view_pid="+B.view_player.toString(),
    Step_2_setplayers,
  );
}
function Click_Rotate() {
  SS.active = false;
  let slog = B.getSlog();
  if (B.gid_new != -1) {
    B.gid_new = B.get_gid_rotate();
  }
  B.view_player = (B.view_player + 1) % 3;
 F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: slog, view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
}
function Click_Board(event) {
function getMouesPosition(e) {
    var mouseX = ((e.offsetX * canvas0.width) / canvas0.clientWidth) | 0;
    var mouseY = ((e.offsetY * canvas0.height) / canvas0.clientHeight) | 0;
    return { x: mouseX, y: mouseY };
  }
  const pos = getMouesPosition(event);
  if (SemaforGreen) {
    SemaforGreen = false;
    const bounds = canvas0.getBoundingClientRect();
    let x = pos.x;
    let y = pos.y;
    if (B.gid_new == -1) {
      B.gid_new = 84
    }
    //if pieces window is open
    if (B.hexs[B.gid_new].promo_flag && SS.active) {
      //CP.elems[7].e.show_flag = false
      //CP.elems[8].e.show_flag = false
      a = SS.getpromo(x, y);
      if (a == "") {
        // ked klikne do prdele
        SemaforGreen = true;
        B.draw_tile();
        B.draw_pieces();
        return;
      }
      B.moveMake(a);
      B.hexs[B.gid_new].promo_flag = false;
      SemaforGreen = true;
      return;
    }
    // gid_new gid_old change
    else {
      B.getGid(x, y);
    }
    B.draw_tile();
    if (B.gid_new !== -1) {
      B.hexs[B.gid_new].draw_mark("rect"); // show cursor
    } else {
      II.panel[3].lines[3].set_text("")      // remove cursor
      II.panel[3].lines[3].clear_text();
    }
    B.draw_pieces();
    //if new piece promotion
    if (B.gid_new  !== -1) {
      if (B.hexs[B.gid_new].promo_flag ) {
        SS.line[1].color = theme["pieces"]["color"][B.onmove % 3];
        SS.write();
        SemaforGreen = true;
        return;
      }
    }
    B.moveValid();
    B.moveMake();
    SemaforGreen = true;
  }
}
function resizee_init () {
if (window.innerWidth > window.innerHeight) {
  canvas0.width = 4320
  canvas0.height = 2180
  portrait = false
  r = 94
  boardXoffset = 450
  boardYoffset = 8;
  piece_size = 15;
  mame_size = "150px";
  info_size = "100px"; //r.toString()+"px";

  }
else {
  canvas0.width = 2160
  canvas0.height = 3330
  portrait = true
  r = 83
  boardXoffset = -429;
  boardYoffset = 380;
  piece_size = 12;
  mame_size = "130px";
  info_size = "100px"; //r.toString()+"px";
  }
canW = canvas0.width;
canH = canvas0.height;
if (isMobile()) {
    document.getElementById("baseFooter").classList.remove("footer");
    window.scrollTo({  top: 50,  behavior: "smooth",});
  }
}
function resizee_refresh () {
  resizee_init ()
  B.init_xy();
  let slog = B.slog.substr(0, B.slog_pointer * 4);
  F.fetchPOST(
    url + "/api/v1/game/info",
    { slog: slog, view_pid: B.view_player },
    Step_3_setelim_board_and_draw,
  );
   // show cursor
}

// Main ////////////////////////////////////////////////////////////////////////////////
resizee_init ()
var B = new board();
var F = new fetchData();
var II = new iinfos();
var SS = new ssel();
B.init();
B.draw_tile();
Step_1_settoken();

window.addEventListener('orientationchange', function() {
    // After orientationchange, add a one-time resize event
    var afterOrientationChange = function() {
        resizee_refresh()
        window.removeEventListener('resize', afterOrientationChange); //todo review
    };
    window.addEventListener('resize', afterOrientationChange);
});

//const boardEvents = new EventSource(
//  `${url}/api/v1/manager/board/events?id=${ID}&jwt=${encodeURIComponent(TOKEN.replace(/^Bearer\s+/, ""))}`,
//);
//boardEvents.onmessage = (event) => {
//  const payload = JSON.parse(event.data);
//  if (payload.slog_length <= B.slog.length) {
//    return;
//  }
//  else {
//    Click_Refresh();
//  }
//  };
//