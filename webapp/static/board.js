const canvas = document.getElementById('canvas');
canvas.addEventListener('mouseclick', Click_Board);
const ctx = canvas.getContext('2d');
//const url = 'https://trichess.mykuna.eu';
const url = `${window.location.protocol}//${window.location.host}`;
const r = 30; // radius
// colors
const text_color = '#000000'
const button_color = '#919595';
const hex_color_gray = '#bcbcbc';
const hex_color =   ['#cc0000', '#000000', "#737373"];
const piece_color_red = '#f8c471';
const piece_color = ['#ffd11a', '#00ffff','#ffffff'];//#d4ac6e #cc000f
const Color_Lumi = [4,212,16, -0.4]
const Color_Lumi1 = [18,13,246, -0.4]
const pcs_map = {"":"", "P":"♟", "N":"♞", "B":"♝", "R":"♜", "Q":"♛", "K":"♚"}
let SemaforGreen = true

// tools
function debug(itext) {
        window.alert("Debug:"+itext);
}
function ColorLuminance(hex, ilum) {
	// validate hex string
	hex = String(hex).replace(/[^0-9a-f]/gi, '');
	if (hex.length < 6) {
		hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
	}
	//lum = lum || 0;
	// convert to decimal and change luminosity
	var rgb = "#", c, i;
	for (i = 0; i < 3; i++) {
	    c = parseInt(hex.substr(i*2,2), 16); //rgb
	    c += ilum[i]
		c = Math.round(Math.min(Math.max(0, c + (c * ilum[3])), 255)).toString(16);
		rgb += ("00"+c).substr(c.length);
	}
	return rgb;
}
// fetchData /////////////////////////////////////////////
function fetchData() {
    this.headers=  {"accept" : "application/json","Content-Type" : "application/json", "Authorization":""};
}
fetchData.prototype.fetchPOST = function(iurl, ijson , icallback) {
    const jsonData = JSON.stringify(ijson)
    const z = this.headers
    fetch(iurl, {
    method: "POST",
    headers: this.headers,
    body: jsonData
  })
    .then(response => {
    if (!response.ok) {
        if (response.status == 401) {
            window.alert('Token expired. Reload the page');
            throw new Error(`EEEExpire: ${response.status}`);
        }
        else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    }
    return response.json();
    })
    .then(data => {
                    icallback(data);
    })
    .catch(error => { debug('Error:'+error+' url:'+iurl)
    })
};
fetchData.prototype.fetchGET = function(iurl,  icallback) {
    //const jsonData = JSON.stringify(ijson)
    fetch(iurl, {
    method: 'GET',
    headers: this.headers,
  })
    .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
    })
    .then(data => {
                    icallback(data);
})
  .catch(error => { debug('Error:'+error+' url:'+iurl);
  })
};
function rotateArray(arr, rotateBy) {
    const n = arr.length;
    rotateBy %= n;
    return arr.slice(rotateBy).concat(arr.slice(0, rotateBy));
}

// llines ///////////////////////////////////////////////////
class llines {
  constructor( itext, ipos_x, ipos_y, ialign, ilength, ifont, icolor, istrokeLine, istrokeColor ) {
    this.text        = itext;
    this.pos_x       = ipos_x;
    this.pos_y       = ipos_y;
    this.align       = ialign;
    this.length      = ilength
    this.font        = ifont;
    this.color       = icolor;
    this.strokeLine = istrokeLine
    this.strokeColor = istrokeColor
    ctx.font = ifont
    var text_width = ctx.measureText(this.text).width
    var l = this.text.length
    while (text_width > ilength) {
        l--;
        this.text = this.text.substr(0,l);
        text_width = ctx.measureText(this.text).width
    }
    this.text_width = text_width;
    this.text_hi  = ifont.substring(0,2);
    this.text_high  = Number(this.font.substring(0,2));
  }
  clear() {
        var c = -1
        if (this.align == 'left') {
            c = 1}
        ctx.save();
        //ctx.strokeStyle = "red";
        //ctx.rect(this.pos_x,this.pos_y+10, c*this.length, (this.text_high+10)*(-1));
        //ctx.stroke()
        //ctx.restore()
        ctx.clearRect(this.pos_x,this.pos_y+12, c*this.length+12, (this.text_high+10)*(-1));
        this.text = ''
  }
  write() {
        ctx.save();
        ctx.beginPath();
        ctx.font = this.font;
        ctx.textAlign = this.align;
        ctx.fillStyle = this.color;
        ctx.lineWidth = this.strokeLine
        ctx.lineJoin = 'circle';
        ctx.strokeStyle = this.strokeColor
        if (this.strokeLine != undefined) {
            ctx.lineWidth = undefined
            ctx.strokeStyle = undefined
            ctx.strokeText(this.text,this.pos_x, this.pos_y);
        }
        ctx.fillText(this.text,this.pos_x,this.pos_y);
        ctx.restore()
    }
}
// ssel ////////////////////////////////////////////////////////
class ssel {
    constructor(){
        this.active = false
        this.line = []
        this.line[0] = new llines('Select piece:', 550, 350, 'center', 200, "35px "+theme["pieces"]["font-family"] , text_color, 0, "#000000")
        this.line[1] = new llines(' ♛  ♜  ♝  ♞ ', 550, 400, 'center', 200, "35px "+theme["pieces"]["font-family"] , '#ffffff', 2, "#000000")
    }
    getpromo(ix,iy) {
    const possx = [475, 525, 575, 625]
    const possy = [391, 391, 391, 391]
    const piece = ["Q", "R", "B", "N"]
    let d = 0;
    let d_min = 35;
    for (let i = 0; i < 4; i++) {
        d = Math.sqrt(Math.pow((ix-possx[i]),2) + Math.pow((iy-possy[i]),2))
        if (d<d_min) {
            return piece[i]
            }
        }
    return ""
    }
    write() {
        ctx.fillStyle = '#ffffff';
        ctx.rect(400,300, 307, 130);
        ctx.fill();
        this.line[0].write()
        this.line[1].write()
        this.active = true
    }
}
// iinfo  ///////////////////////////////////////////////////
class iinfo {
    constructor(iinfo_id, ipos_x, ipos_y, ialign, ivert) {
        var line_len = 310
        var line_high = 45
        const width = ctx.canvas.width
        const height = ctx.canvas.height
        this.text = []
        this.lines  = []
        this.lines[0] =  new llines('', ipos_x, ipos_y, ialign, line_len, "35px "+theme["board"]["font-family"] , text_color, undefined ,theme["board"]["name_color_onmove"])
        line_len  = line_len - 30
        if (iinfo_id == 3)
            {this.lines[1] =  new llines('', ipos_x, ipos_y+line_high*ivert, ialign, line_len, "35px "+theme["board"]["font-family"], text_color)}
        else
            {this.lines[1] =  new llines('', ipos_x, ipos_y+line_high*ivert, ialign, line_len, "25px "+theme["board"]["font-family"], text_color)}
        for (let i = 2; i < 7; i++) {
            line_len  = line_len-25//10 - 60/i
            this.lines[i] =  new llines('', ipos_x, ipos_y+i*line_high*ivert, ialign, line_len, "35px "+theme["pieces"]["font-family"] , text_color, 0, "#000000")
        }
    }
    write() {
    for (let i = 0; i < 7; i++) {
            this.lines[i].write()
        }
    }
    clear() {
    for (let i = 0; i < 7; i++) {
            this.lines[i].clear()
        }
    }
  }
class iinfos {
    constructor() {
    var a = theme["board"]["font-family"]
    this.panel = []
    this.players = []
    this.index = []
    this.panel[0] = new iinfo(0, 1100   , 675   , 'right', -1)
    this.panel[1] = new iinfo(1, 0      , 45    , 'left' ,  1)
    this.panel[2] = new iinfo(2, 1100   , 45    , 'right',  1)
    this.panel[3] = new iinfo(3, 0      , 675   , 'left' , -1)
    }
    set (idata) {
        this.index = rotateArray([0,1,2], B.view_player)
        for (let i = 0; i < 3; i++) {
            this.panel[i].lines[0].text = this.players[this.index[i] ] // set players names
              //set players color
            for (let j = 2; j < 7; j++) {
                this.panel[i].lines[j].color =  theme["pieces"]["color"][this.index[i]]
                this.panel[i].lines[j].strokeColor = text_color
            }
        }
        this.panel[3].lines[1].text = 'Game ID: '+ID.toString()
        this.panel[3].lines[0].text= 'Move: '+B.move_number_org.toString()+'/'+B.move_number.toString()
        for (let i = 0; i < 3; i++) {
            // highlight players
            if (this.index[i] == idata.onmove)
                {this.panel[i].lines[0].strokeLine = 8}
            else
                {this.panel[i].lines[0].strokeLine = undefined}
            // eliminated_value
            this.panel[i].lines[1].text= 'lost: '+idata.eliminated_value[this.index[i]].toString()
            // eliminated pieces
            var e = elim2array(idata.eliminated[this.index[i]])
            if (e != undefined)
                {
                for (let j = 0; j < e.length; j++) {
                    this.panel[i].lines[j+2].text= e[j]
                    }
                }
        }
    }
    write() {
    for (let i = 0; i < 4; i++) {
        this.panel[i].write()
        }
    }
    clear() {
        for (let i = 0; i < 4; i++) { //draw hex tile
            this.panel[i].clear()
        }
    }
}
// hex ///////////////////////////////////////////////////
function hex(a, b, id) {
    this.x =  (a +b*(0.5 ))*(r * Math.sqrt(3))+8;
    this.y =  (1 + b * 1.5) * r;
    this.id = id;
    this.piece = {"piece":"" , "player_id":-1};
    this.hex_color = hex_color[(a+2*b)%3];
    this.lumi = [0,0,0,0]  // R,G,B, luminiscence
    this.show_flag = true; // true means to redraw the hex
    this.valid_flag = false;
    this.promo_flag = false;
}
hex.prototype.set = function (ipiece) {
    if (ipiece.piece !=  this.piece.piece || ipiece.player_id !=  this.piece.player_id) {
        this.show_flag = true;
        }
    this.piece.piece  = ipiece.piece;
    this.piece.player_id = ipiece.player_id;
    }
hex.prototype.setlumi = function (ilumi) {
   this.lumi = ilumi
   this.show_flag = true
    }
hex.prototype.draw = function () {
    ctx.beginPath();
    ctx.lineWidth = 0;
    for (let i = 0; i < 6; i++) { //draw hex tile
        ctx.lineTo(this.x + r * Math.cos((i  + 0.5)*(Math.PI / 3 )),
                   this.y + r * Math.sin((i  + 0.5)*(Math.PI / 3 )));
    }
    ctx.closePath();
    ctx.fillStyle = ColorLuminance(this.hex_color, this.lumi);
    ctx.fill();
    if (this.piece.piece != undefined) {
        this.draw_piece()
        }
    //ctx.stroke();
}
hex.prototype.draw_piece = function () {
        ctx.font = "38px Verdana";
        ctx.textAlign = "left";
        ctx.fillStyle = piece_color[(this.piece.player_id+2)%3];      //todo
        ctx.miterLimit = 2;
        ctx.lineJoin = 'circle';
        ctx.lineWidth = 2;
        //if (this.hex_color == '#cc0000' &&  ctx.fillStyle == piece_color_red)  {
        //    ctx.strokeStyle = "white";
        //}
        ctx.strokeText(pcs_map[this.piece.piece],this.x-17, this.y+13); // todo
        ctx.fillText(pcs_map[this.piece.piece],this.x-17,this.y+13); // todo
        ctx.strokeStyle = "black"
        //draw_piece(this.piece.piece, this.piece.player_id, this.x, this.y)
        //ctx.lineWidth = 1
        

}
hex.prototype.draw_mark = function (i_kind) {
    this.show_flag = true;
    ctx.save();
    if (this.hex_color == '#ffffff' )  {
        ctx.strokeStyle = '#000000';
    }
    else {
        ctx.strokeStyle = '#ffffff';
    }
    ctx.lineWidth = 3
    if (i_kind == 'safe') {
       ctx.beginPath();
       ctx.arc(this.x, this.y, r/2, 0, 2 * Math.PI);
       ctx.stroke();
    } else if (i_kind == 'rect') {
       ctx.beginPath();
       ctx.rect(this.x-r/2, this.y-r/2, r, r);
       ctx.stroke();
    } else if (i_kind == 'attack') {
        ctx.beginPath();
        ctx.moveTo(this.x-r/1.6, this.y-r/1.6);
        ctx.lineTo(this.x+r/1.6, this.y+r/1.6);
        ctx.moveTo(this.x+r/1.6, this.y-r/1.6);
        ctx.lineTo(this.x-r/1.6, this.y+r/1.6);
       ctx.stroke();
    } else {
        const a = 0;
    }
    ctx.restore();
}
// board /////////////////////////////////////////////////
function board() {
    this.hexs    = [];
    this.gid_old = 85;
    this.gid_new = 85;
    this.slog = "";
    this.view_player =  0;
    this.move_number =  -1;
    this.move_number_org =  -1;
    this.move_number_max =  -1;
    this.onmove =  0;
    this.finished =  false;
    this.hist_changed =  false;
}
board.prototype.set = function(idata) {
    const jdata = idata;
    this.move_number =  jdata.move_number;
    this.finished = jdata.finished;
    this.onmove = jdata.onmove;
    if (this.move_number_org == -1) {
        this.move_number_org = jdata.move_number;
    }
    if (this.move_number_max == -1) {
        this.move_number_max = jdata.move_number;
    }
    for (let z= 0; z < 169; z++) {   // clear
        this.hexs[z].set({"piece":"", "player_id":-1})
        this.hexs[z].setlumi([0,0,0,0])
    }
    for (let player_id  in jdata.pieces) {// set pieses
         for (let j in jdata.pieces[player_id]) {
             const pcs =jdata.pieces[player_id][j];
             this.hexs[pcs.gid].set({"piece":pcs.piece, "player_id":Number(player_id)})
        }
    }
    // mark last move
    if (jdata.last_move != undefined ) {
        this.hexs[jdata.last_move.from].setlumi(Color_Lumi)
        this.hexs[jdata.last_move.to].setlumi(Color_Lumi)
    }
    // set chess by
    for (let player_id  in jdata.chess_by) {
         for (let j in jdata.chess_by[player_id]) {
             const pcs =jdata.chess_by[player_id][j];
             this.hexs[pcs.gid].setlumi(Color_Lumi1)
        }
    }
    //king_pos
    if (!(jdata.chess_by[0].length == 0 && jdata.chess_by[1].length == 0 && jdata.chess_by[2].length == 0)) {
        this.hexs[jdata.king_pos].setlumi(Color_Lumi1)
    }
   if (jdata.king_pos != 0) {
       //this.hexs[jdata.king_pos].setlumi(Color_Lumi1)
   }
}
board.prototype.init  = function () {
  let cnt = 0;
  for (let i = 0; i < 15; i++) {
    for (let j = 0; j < 15 ; j++) {
      if ((j + i > 6) && (j < 15)&& (i < 15)&& (j+i < 22)) {
        this.hexs[cnt] = new hex(j, i, cnt);
        cnt = ++ cnt;
      }
    }
  }
};
board.prototype.draw  = function () {
    for (let i = 0; i < 169; i++) {
        if (this.hexs[i].show_flag) {
            this.hexs[i].draw()
            //this.hexs[i].lumi = 0
        }
    }
};
board.prototype.getGid  = function (ix,iy) {
    let d = 0;
    let d_min = 99999999;
    let r_x = 0;
    let r_y = 0;
    let r_i = 0;
    for (let i = 0; i < 169; i++) {
        d = Math.pow((ix-this.hexs[i].x),2) + Math.pow((iy-this.hexs[i].y),2)
        if (d<d_min) {
            d_min = d;
            r_x = this.hexs[i].x;
            r_y = this.hexs[i].y;
            r_i = this.hexs[i].id;
            }
        }
    this.gid_old = this.gid_new;
    this.gid_new = r_i;
    return r_i;
};
// move ---------------------------------------------
board.prototype.moveValid = async function() {
    if (!(this.hexs[this.gid_new].piece.piece != undefined && this.hexs[this.gid_new].piece.player_id == this.onmove)) {
        return
    }
    F.fetchPOST(url+'/api/v1/move/valid', {"slog": this.slog.substring(0,this.move_number*4), "view_pid": this.view_player, "gid": this.gid_new}, Step_valid_moves);
}
board.prototype.moveMake = async function(inew_piece = "") {
    if (this.gid_old == -1 || this.gid_old == this.gid_new)  {return}
    if (!(this.hexs[this.gid_old].piece.piece != undefined && this.hexs[this.gid_old].piece.player_id == this.onmove)) {
        return;
        }
    if (!(this.hexs[this.gid_new].valid_flag)) {
        return;
    }
    F.fetchPOST(url+'/api/v1/move/make', {"slog": this.slog.substring(0,this.move_number*4), "view_pid": this.view_player, "gid": this.gid_old, "tgid": this.gid_new, "new_piece": inew_piece}, Step_make_move);
}
//----------------------------------------------------
function elim2array(idata) {
    let s = ''
    for (i in idata) {
        s = s + pcs_map[idata[i]]
    }
    var t = Array.from(s).sort().reverse().join('').match(/(.)\1*/g)
    return t;
}
function Step_make_move(idata) {
         B.slog = idata.slog;
         B.hexs[B.gid_old].piece.piece = "";
         B.hexs[B.gid_old].piece.player_id = -1;
         if (B.move_number_org > B.move_number) {
             B.hist_changed =  true;
         }
         B.move_number_max = B.move_number+1;
         F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player}, Step_3_setelim_board_and_draw);
}
function Step_valid_moves(idata) {
    for (let j=0; j < 169; j++ ) {
        B.hexs[j].valid_flag = false;
        B.hexs[j].promo_flag = false;
    }
    const jsonData = idata;
    for (let i  in jsonData.targets) {
        const obj = jsonData.targets[i];
        B.hexs[obj.tgid].draw_mark(obj.kind); //todo
        B.hexs[obj.tgid].valid_flag = true;
        B.hexs[obj.tgid].chang_flag = true;
        B.hexs[obj.tgid].promo_flag = obj.promotion
    }
}
function Step_1_settoken(idata) {
    //F.headers.Authorization = "Bearer "+idata.access_token;
    F.headers.Authorization = TOKEN;
    F.fetchGET(url+'/api/v1/manager/board?id='+ID.toString(), Step_2_setplayers)
}
function Step_2_setplayers(idata) {
    II.players = [idata.player_0, idata.player_1, idata.player_2]
    B.view_player = (idata.view_pid)%3
    B.slog = idata.slog
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Step_3_setelim_board_and_draw(idata) {
    B.set(idata);
    B.draw();
    B.set(idata);
    II.clear()
    II.set(idata);
    II.write()
    button_control()
    if (B.finished) {
        // Get the modal
        var name = II.players[B.onmove]
        var modal = document.getElementById("myModal");
        modal.style.color = theme["pieces"]["color"][B.onmove]
        modal.innerHTML = "GAME OVER <br>"+name+" lost :-("
        modal.style.display = "block";
        window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = "none";
            }
        }
    }
}

// Button ////////////////////////////////////////////////////////////////////////////////
function button_control() {
        if (B.move_number_org == B.move_number-1 && B.view_player == (B.onmove+2)%3 && !(B.hist_changed)  ) {
            b_ok.disabled = false;
        }
        else {
            b_ok.disabled = true;
        }
        b_ok.update()
        if (B.move_number == 0) {
            b_bw.disabled = true;
        }
        else {
            b_bw.disabled = false;
        }
        b_bw.update()
        if (B.move_number_max == B.move_number) {
            b_fw.disabled = true;
        }
        else {
            b_fw.disabled = false;
        }
        b_fw.update()
}
function butt(iid, icolor) {
    this.id = iid;
    this.disabled = true;
    this.color_enable = icolor;
}
butt.prototype.update = function() {
    if (this.disabled) {
        document.getElementById(this.id).style.backgroundColor = hex_color_gray;
        document.getElementById(this.id).disabled = true;
    }
    else {
        document.getElementById(this.id).style.backgroundColor = this.color_enable;
        document.getElementById(this.id).disabled = false;
    }
};

// Click ////////////////////////////////////////////////////////////////////////////////
function Click_Backward() {
    B.move_number = B.move_number -1
    let slog = B.slog.substring(0,B.move_number*4)
    F.fetchPOST(url+'/api/v1/game/info', {"slog": slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Click_Forward() {
    B.move_number = B.move_number +1
    let slog = B.slog.substring(0,B.move_number*4)
    F.fetchPOST(url+'/api/v1/game/info', {"slog": slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Click_OK() {
    if (B.move_number_org == B.move_number-1 && B.view_player == (B.onmove+2)%3 ) {
        F.fetchPOST(url+'/api/v1/manager/board', {"id": ID, "slog": B.slog.substring(0,B.move_number*4)} , debug);
    }
    B.move_number_org = -1
    B.move_number_max = -1
    b_ok.disabled = true
    b_ok.update()
    B.hist_changed = false
}
function Click_Refresh()    {
    B.move_number_max = -1;
    B.move_number_org = -1;
    B.hist_changed = false
    F.fetchGET(url+'/api/v1/manager/board?id='+ID.toString(), Step_2_setplayers)
};
function Click_Board(event) {
    function getMouesPosition(e) {
        var mouseX = e.offsetX * canvas.width / canvas.clientWidth | 0;
        var mouseY = e.offsetY * canvas.height / canvas.clientHeight | 0;
        return {x: mouseX, y: mouseY};
    }
    const pos = getMouesPosition(event)
    if (SemaforGreen) {
        SemaforGreen = false;
        const bounds = canvas.getBoundingClientRect()
        document.getElementById("myModal").style.display = "none";
        let x = pos.x
        let y = pos.y
        //if select pieces window is open
        if (B.hexs[B.gid_new].promo_flag && SS.active) {
            B.hexs[B.gid_new].promo_flag = false
            //CP.elems[7].e.show_flag = false
            //CP.elems[8].e.show_flag = false
            a = SS.getpromo(x,y)
            if (a == "") { // ked klikne do prdele
                SemaforGreen = true
                B.draw();
                return
            }
            B.moveMake(a)
            SemaforGreen = true
            return
        }
        // gid_new gid_old change
        else        {
            B.getGid(x,y)

        }
        B.draw();
        B.hexs[B.gid_new].draw_mark('rect'); // show cursor
        //if new piece promotion
        if (B.hexs[B.gid_new].promo_flag) {
            //CP.elems[7].e.show_flag = true
            //CP.elems[8].e.show_flag = true
            //CP.elems[7].draw2()
            //CP.elems[8].draw2()
            SS.line[1].color = theme["pieces"]["color"][B.onmove]
            SS.write()
            SemaforGreen = true
            return
        }
        B.moveValid()
        B.moveMake()
        SemaforGreen = true;
    }
};
// Main ////////////////////////////////////////////////////////////////////////////////
var B = new board()
var F = new fetchData()
var b_ok = new butt('b_ok', "lightgreen" )
var b_rf = new butt('b_rf', button_color )
var b_fw = new butt('b_fw', button_color )
var b_bw = new butt('b_bw', button_color )
var II = new iinfos()
var SS = new ssel()

B.init();
B.draw();
II.write()

Step_1_settoken()

//F.fetchPOST(url+'/token', {username: "filio", password: ''} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "ondro", password: ''} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "livia", password: ''} , Step_1_settoken);
