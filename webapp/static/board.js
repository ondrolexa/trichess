const Control_panel = {
  "elems": [
    {
      "id": "0_message",
      "text": "",
      "font": "35px Arial",
      "stroke_flag": false,
      "show_flag": true,
      "pos": {
        "x": 20,
        "y": 675,
        "rotate": 0,
        "align": "left"
      }
    },
    {
      "id": "0_player",
      "text": "Player_0",
      "font": "35px Verdana",
      "stroke_flag": false,
      "show_flag": true,
      "pos": {
        "x": 1050,
        "y": 675,
        "rotate": 0,
        "align": "right"
      }
    },
    {
      "id": "1_player",
      "text": "Player_1",
      "font": "35px Verdana",
      "stroke_flag": false,
      "show_flag": true,
      "pos": {
        "x": 10,
        "y": 47,
        "rotate": 0,
        "align": "left"
      }
    },
    {
      "id": "2_player",
      "text": "Player_2",
      "font": "35px Verdana",
      "stroke_flag": false,
      "show_flag": true,
      "pos": {
        "x": 1050,
        "y": 47,
        "rotate": 0,
        "align": "right"
      }
    },
    {
      "id": "0_eliminate",
      "text": "eliminate_0",
      "font": "38px Arial",
      "stroke_flag": true,
      "show_flag": true,
      "pos": {
        "x": 1100,
        "y": 550,
        "rotate": 0,
        "align": "right",
      }
    },
    {
      "id": "1_eliminate",
      "text": "eliminate_1",
      "font": "38px Arial",
      "stroke_flag": true,
      "show_flag": true,
      "pos": {
        "x": 5,
        "y": 100,
        "rotate": 0,
        "align": "left"
      }
    },
    {
      "id": "2_eliminate",
      "text": "eliminate_2",
      "font": "38px Arial",
      "stroke_flag": true,
      "show_flag": true,
      "pos": {
        "x": 1100,
        "y": 100,
        "rotate": 0,
        "align": "right"
      }
    }
  ]
}
const canvas = document.getElementById('canvas');
canvas.addEventListener('mouseclick', Click_Board);
const ctx = canvas.getContext('2d');
const url = 'https://trichess.mykuna.eu';
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
        span = document.getElementById("message").innerHTML = "Debug:"+itext;
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
    debug('connect:'+iurl);
    fetch(iurl, {
    method: "POST",
    headers: this.headers,
    body: jsonData
  })
    .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
    })
    .then(data => {
                    icallback(data);
                    debug('end:'+iurl);
    })
    .catch(error => { debug('Error:'+error+' url:'+iurl);
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

// hex ///////////////////////////////////////////////////
function hex(a, b, id) {
    this.x =  (a +b*(0.5 ))*(r * Math.sqrt(3));
    this.y =  (1 + b * 1.5) * r;
    this.id = id;
    this.piece = {"piece:":"" , "player_id":-1};
    this.hex_color = hex_color[(a+2*b)%3];
    this.lumi = [0,0,0,0]  // R,G,B, luminiscence
    this.show_flag = true; // true means to redraw the hex
    this.valid_flag = false;
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
    this.gid_old = -1;
    this.gid_new = -1;
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
board.prototype.moveMake = async function() {
    if (this.gid_old == -1 || this.gid_old == this.gid_new)  {return}
    if (!(this.hexs[this.gid_old].piece.piece != undefined && this.hexs[this.gid_old].piece.player_id == this.onmove)) {
        return;
        }
    if (!(this.hexs[this.gid_new].valid_flag)) {
        return;
    }
    F.fetchPOST(url+'/api/v1/move/make', {"slog": this.slog.substring(0,this.move_number*4), "view_pid": this.view_player, "gid": this.gid_old, "tgid": this.gid_new}, Step_make_move);
}

//element/////////////////////////////////////////
function elem(init) {

    this.e = init;
}
elem.prototype.clear  = function () {
            let high = Number(this.e.font.substring(0,2))
            let width = 6*high;
            ctx.fillStyle = "black";
            ctx.fillRect(this.e.pos.x,this.e.pos.y, 2,2);//todo
            ctx.fillStyle = "green";
            if (this.e.pos.align == "left"){
                ctx.clearRect(this.e.pos.x-3,this.e.pos.y+4, width, -high);//todo
                if (this.e.id.substring(2,6) == 'elim') {
                    ctx.clearRect(this.e.pos.x-2,this.e.pos.y-high, 255, high*3);//todo
                }
            }
            else if (this.e.pos.align = "right"){
                ctx.clearRect(this.e.pos.x+3,this.e.pos.y+4, -width, -high);//todo
                if (this.e.id.substring(2,6) == 'elim') {
                    ctx.clearRect(this.e.pos.x,this.e.pos.y-high, -255, high*3);//todo
                }
            }
}
elem.prototype.draw2  = function () {
    if (this.e.show_flag) {
        let player_id = Number(this.e.id.substring(0, 1))
        ctx.save();
        ctx.beginPath();
        this.clear();
        ctx.font = this.e.font;
        ctx.textAlign = this.e.pos.align;
        ctx.fillStyle = piece_color[player_id];
        ctx.miterLimit = 2;
        ctx.lineWidth = 2;
        //ctx.lineJoin = 'circle';
        ctx.textAlign = this.e.pos.align;
        //ctx.textAlign = "right";
        let limit = 6 // number of eliminated pieces in one row
        if (this.e.id.substring(2,6) == 'elim') {
            ctx.fillStyle = piece_color[(player_id+B.view_player+2)%3];
        }
        else {
            ctx.strokeStyle = 'lightgreen';
            ctx.lineWidth = 8
            ctx.fillStyle = text_color
        }
        if (this.e.id.substring(2,6) == 'elim' && this.e.text.length > limit) {
            let high = Number(this.e.font.substring(0,2))
            let line = []
            line[0] = this.e.text.substring(0,6)
            line[1] = this.e.text.substring(6,12)
            line[2] = this.e.text.substring(12,19)
            for (let i in line) {
                ctx.strokeText(line[i],this.e.pos.x,this.e.pos.y+i*high);
                ctx.fillText(line[i],this.e.pos.x,this.e.pos.y+i*high);
            }
        }
        else {
            if (this.e.stroke_flag) {
                ctx.strokeText(this.e.text.toUpperCase(),this.e.pos.x, this.e.pos.y);
            }
            ctx.lineWidth = 8
            ctx.fillText(this.e.text.toUpperCase(),this.e.pos.x,this.e.pos.y);
        }
        ctx.restore()
        }
}
elem.prototype.settext  = function (itext) {
    let limit = 4
    this.e.show_flag = true
    this.e.text = itext
};
//elementS/////////////////////////////////////////
function elems(control_panel) {
    this.ID = 0
    this.elems  = [];
    for (let i in control_panel.elems) {
        this.elems[i] = new elem(control_panel.elems[i]);
    }
};
elems.prototype.text= function (itext) {
    this.elems[0].e.text = itext;
    this.elems[0].e.show_flag = true;
};
elems.prototype.onmove= function (i) {
    for (let j = 1; j < 4; j++) {
        this.elems[j].e.show_flag = true;
        this.elems[j].e.stroke_flag = false;
    }
    this.elems[i+1].e.stroke_flag = true;

    for (let j = 1; j < 4; j++) {
        this.elems[j].draw2();
    }
};
elems.prototype.draw = function() {
    for (let i in this.elems) {
        this.elems[i].draw2();            }
};
//----------------------------------------------------
function elim2pieces(idata) {
    let s = ''
    for (i in idata) {
        s = s + pcs_map[idata[i]]
    }
    return s
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
    }
    const jsonData = idata;
    for (let i  in jsonData.targets) {
        const obj = jsonData.targets[i];
        B.hexs[obj.tgid].draw_mark(obj.kind); //todo
        B.hexs[obj.tgid].valid_flag = true;
        B.hexs[obj.tgid].chang_flag = true;
    }
}
function Step_1_settoken(idata) {
    //F.headers.Authorization = "Bearer "+idata.access_token;
    F.headers.Authorization = TOKEN;
    F.fetchGET(url+'/api/v1/manager/board?id='+ID.toString(), Step_2_setplayers)
}
function Step_2_setplayers(idata) {
    let player = [idata.player_0, idata.player_1, idata.player_2]
    CP.ID = idata.id
    B.view_player = idata.view_pid
    B.slog = idata.slog
    //B.slog = "BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJGOKGBGDINFMFKGCKDIHGOGIJDNEMDEIJNBLBBOCMIJKIODNFFOGLKIGIOHKLINJMGIGDOBKDEODNGBIDNEJGCNELIDOANFMECKALOAIDMEHODOCNBHBJHOMEDLEKBJALNALCCMDKAHCHMELEAODOHGLENDLEDKFJCIDINCMDCNAOFCGEKJJKDNDIAIBIKDHADIDFEDFCKLKHDFLBCHKHOFNDFMHJEGHFLEKF"

    CP.elems[1].settext(player[(B.view_player+0) % 3 ])
    CP.elems[2].settext(player[(B.view_player+1) % 3 ])
    CP.elems[3].settext(player[(B.view_player+2) % 3 ])
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Step_3_setelim_board_and_draw(idata) {
    B.set(idata);
    B.draw();
    CP.elems[4].settext(elim2pieces(idata.eliminated[(B.view_player+0) % 3]))
    CP.elems[5].settext(elim2pieces(idata.eliminated[(B.view_player+1) % 3]))
    CP.elems[6].settext(elim2pieces(idata.eliminated[(B.view_player+2) % 3]))
    CP.elems[0].e.show_flag = true;
    CP.elems[0].e.text = B.move_number_org.toString()+"/"+B.move_number.toString()//+"-"+B.onmove.toString()+"-v:"+B.view_player.toString();
    CP.draw()
    if (B.view_player ==0 ){
        CP.onmove(idata.onmove);    //todo
    }
    else {
        CP.onmove((idata.onmove+ Math.pow(-1, B.view_player+1)+B.view_player)%3);    //todo
    }
    button_control()
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
        let x = pos.x //- bounds.x
        let y = pos.y //- bounds.y
        B.getGid(x,y);
        B.draw();
        B.hexs[B.gid_new].draw_mark('rect'); // show cursor
        B.moveValid();
        B.moveMake();
        SemaforGreen = true;
    }
};
// Main ////////////////////////////////////////////////////////////////////////////////
let B = new board()
let F = new fetchData()
let CP = new elems(Control_panel)
let b_ok = new butt('b_ok', "lightgreen" )
let b_rf = new butt('b_rf', button_color )
let b_fw = new butt('b_fw', button_color )
let b_bw = new butt('b_bw', button_color )
B.init();
B.draw();
Step_1_settoken()
//F.fetchPOST(url+'/token', {username: "filio", password: 'tyblko'} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "ondro", password: 'marketa25'} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "livia", password: 'neutrino'} , Step_1_settoken);
