const canvas0 = document.getElementById('canvas');
canvas0.addEventListener('mouseclick', Click_Board);
//var scale =  (canvas0.clientWidth / 800)
//canvas0.style.width = canvas0.width*scale  + 'px';
//canvas0.style.height = canvas0.height*scale + 'px';
window.onresize = function(){var scale =  (canvas0.clientWidth / 800)
                            canvas0.style.width = canvas0.width*scale  + 'px';
                            canvas0.style.height = canvas0.height*scale + 'px';
                            window.location.reload()
                            };

const ctx0 = canvas0.getContext('2d');
const url = `${window.location.protocol}//${window.location.host}`;
const r = 17; // radius
const piece_size = 2.5;
const bpiece_lineWidth = 0.2
const epiece_lineWidth = 0.3
const pawn_size = "22px";
const mame_size = "24px";

const info_size = r.toString()+"px";
// colors
const button_color = '#919595';
const pcs_map1 = {"":"", "P":"♟", "N":"♞", "B":"♝", "R":"♜", "Q":"♛", "K":"♚"}
const pcs_map2 = {"":"", "♟":"P", "♞":"N", "♝":"B", "♜":"R", "♛":"Q", "♚":"K"}


let SemaforGreen = true
let SemaforWait = false

function draw_piece_common( i_piece, i_lineWidth = 1, i_lineColor = "#000000", i_fillColor = "#000000", i_x, i_y) {
        if (i_piece != undefined ||  i_piece != "") {
            var path = new Path2D(pieces_paths["pieces"][i_piece]);
            ctx0.save()
            ctx0.lineWidth = i_lineWidth
            ctx0.fillStyle = i_fillColor
            ctx0.strokeStyle = i_lineColor
            ctx0.transform(piece_size,0,0,piece_size, i_x, i_y);
            ctx0.fill(path)
            ctx0.stroke(path);
            ctx0.restore()
        }
    }

function setCursorByID(id,cursorStyle) {
 var elem;
 if (document.getElementById &&
    (elem=document.getElementById(id)) ) {
  if (elem.style) elem.style.cursor=cursorStyle;
 }
}
// tools
function test(i_flag) {
    var modal = document.getElementById("myModal2")
    if (i_flag != "a"  ) {
        SemaforWait = false
        setTimeout(function (){
                modal.style.display = "none";
        }, 1);
        }
    else {
        setTimeout(function (){
            if ( !(SemaforWait) ) {
                //setCursorByID(id="main","progress")
                modal.style.color = theme["canvas"]["name_inchess"]
                modal.innerHTML = "Waiting<br/>for<br/>connection..."
                modal.style.fontSize = "40px"
                SemaforWait = true
                modal.style.display = "block";
            }
        }, 1);
    }
    }

function debug(itext) {
        window.alert("Debug:"+itext);
}
function rotateArray(arr, rotateBy) {
    const n = arr.length;
    rotateBy %= n;
    return arr.slice(rotateBy).concat(arr.slice(0, rotateBy));
}
// fetchData /////////////////////////////////////////////
class fetchData {
    constructor() {
        this.headers=  {"accept" : "application/json","Content-Type" : "application/json", "Authorization":""}
    }
    fetchPOST(iurl, ijson , icallback) {
        const jsonData = JSON.stringify(ijson)
        const z = this.headers
        fetch(iurl, {
            method: "POST",
            headers: this.headers,
            body: jsonData
        })
            .then(response => {
            test("a")
            if (!response.ok) {
                if (response.status == 401) {
                    window.alert('Token expired. Reload the page');
                    location.reload();
                    //throw new Error(`Token expired. Reload the page: ${response.status}`);
                }
                else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            return response.json();
            })
            .then(data => { test("d");
                            icallback(data);
            })
            .catch(error => { debug('Error:'+error+' url:'+iurl)
            })
    }
    fetchGET(iurl,  icallback) {
    //const jsonData = JSON.stringify(ijson)
        fetch(iurl, {
            method: 'GET',
            headers: this.headers,
        })
            .then(response => {
                test("a")
                if (!response.ok) {
                  throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => { test("d")
                        icallback(data) })
            .catch(error => { debug('Error:'+error+' url:'+iurl) })
    };
}
// ssel //////////////////////////////////////////////////
class ssel {
    constructor(){
        this.active = false
        this.line = []
        this.line[0] = new llines('Select piece:', 550, 350, 'center', 200, "15px "+theme["pieces"]["font-family"] , theme["canvas"]["info"] )
        this.line[1] = new llines(' ♛  ♜  ♝  ♞ ', 550, 400, 'center', 200, piece_size+" "+theme["pieces"]["font-family"] , '#ff00ff', 2, theme["pieces"]["stroke-color"])
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
        ctx0.fillStyle =  theme["canvas"]["background"];
        ctx0.rect(400,300, 307, 130);
        ctx0.fill();
        this.line[0].write()
        this.line[1].write()
        this.active = true
    }
}
// llines ////////////////////////////////////////////////
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
        ctx0.font = ifont
        var text_width = ctx0.measureText(this.text).width
        var l = this.text.length
        while (text_width > ilength) {
            l--;
            this.text = this.text.substr(0,l);
            text_width = ctx0.measureText(this.text).width
        }
        this.text_width = text_width;
        this.text_hi  = ifont.substring(0,2);
        this.text_high  = Number(this.font.substring(0,2));
    }
    clear() {
        var c = -1
        if (this.align == 'left') {
            c = 1}
        //ctx0.fillStyle = "balck"
        ctx0.clearRect(this.pos_x-5*c,this.pos_y+5, c*this.length, (this.text_high+10)*(-1));
        //ctx0.fill()
        this.text = ''
    }
    write() {
        ctx0.save();
        ctx0.beginPath();
        ctx0.font = this.font;
        ctx0.textAlign = this.align;
        ctx0.fillStyle = this.color;
        ctx0.lineWidth = this.strokeLine
        ctx0.lineJoin = 'circle';
        ctx0.strokeStyle = this.strokeColor
        if (this.strokeLine != undefined) {
            ctx0.lineWidth = undefined
            ctx0.strokeStyle = undefined
            ctx0.strokeText(this.text,this.pos_x, this.pos_y);
        }
        ctx0.fillText(this.text,this.pos_x,this.pos_y);
        ctx0.restore()
      }
    draw() {
        // text zisti pocet znakov
        if (this.text.charAt(0) != "" || this.text.charAt(0) != undefined) {
            var offset = piece_size*4
            var dist = piece_size*10
            piece_size
            for ( let i = 0; i < this.text.length; i++) {
                if (this.align == "right") {
                    draw_piece_common( this.text.charAt(0)
                                     , epiece_lineWidth
                                     , this.strokeColor
                                     , this.color
                                     , this.pos_x + (-1) * (offset + i * dist)
                                     , this.pos_y)
                    }
                else {
                    draw_piece_common( this.text.charAt(0)
                                     , epiece_lineWidth
                                     , this.strokeColor
                                     , this.color
                                     , this.pos_x + (1) * (offset + i * dist)
                                     , this.pos_y)
                    }
            }
        }
    }


}
// iinfo  ////////////////////////////////////////////////
class iinfo {
    constructor(iinfo_id, ipos_x, ipos_y, ialign, ivert) {
        var line_len = 260
        var line_high = 1.5*r
        const width = ctx0.canvas.width
        const height = ctx0.canvas.height
        this.text = []
        this.lines  = []
        line_len  = line_len - 30
        // info block
        if (iinfo_id == 3) {
            this.lines[0] =  new llines('', ipos_x, ipos_y, ialign, line_len, info_size+" "+theme["canvas"]["font-family"], theme["canvas"]["info"])
            this.lines[1] =  new llines('', ipos_x, ipos_y+line_high*ivert, ialign, line_len, info_size+" "+theme["canvas"]["font-family"], theme["canvas"]["info"])
        }
        // player info
        else {
            // player name
            this.lines[0] =  new llines('', ipos_x, ipos_y, ialign, line_len, mame_size+" "+theme["canvas"]["font-family"] , theme["canvas"]["name"] )
            this.lines[1] =  new llines('', ipos_x, ipos_y+line_high*ivert, ialign, line_len, info_size+" "+theme["canvas"]["font-family"], theme["canvas"]["info"])
        }
        // elimited
        for (let i = 2; i < 7; i++) {
            line_len  = line_len-18//10 - 60/i
            this.lines[i] =  new llines('', ipos_x, ipos_y+i*line_high*ivert, ialign, line_len, piece_size+" "+theme["canvas"]["font-family"] , theme["pieces"]["color"][iinfo_id], 2, theme["pieces"]["stroke-color"])
        }
    }
    write() {
    for (let i = 0; i < 2; i++) {
            this.lines[i].write()
        }
    for (let i = 2; i < 7; i++) {
            this.lines[i].draw()
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
    var a = theme["canvas"]["font-family"]
    this.panel = []
    this.players = []
    this.index = []
    this.panel[0] = new iinfo(0, 780   , 380   , 'right', -1)
    this.panel[1] = new iinfo(1, 20    , 1.5*r    , 'left' ,  1)
    this.panel[2] = new iinfo(2, 780   , 1.5*r    , 'right',  1)
    this.panel[3] = new iinfo(3, 20    , 380   , 'left' , -1)
    }
    set (idata) {
        this.index = rotateArray([0,1,2], B.view_player)
        for (let i = 0; i < 3; i++) {
            this.panel[i].lines[0].text = this.players[this.index[i] ] // set players names
              //set players color
            //for (let j = 2; j < 7; j++) {
                //this.panel[i].lines[j].color =  theme["pieces"]["color"][this.index[i]]
                //this.panel[i].lines[j].strokeColor = text_color
            //}
        }
        this.panel[3].lines[1].text = 'Game ID: '+ID.toString()
        this.panel[3].lines[0].text= 'Move: '+B.move_number_org.toString()+'/'+B.move_number.toString()
        for (let i = 0; i < 3; i++) {
            // highlight players
            if (this.index[i] == idata.onmove) {
                this.panel[i].lines[0].strokeLine = 4
                this.panel[i].lines[0].strokeColor = theme["canvas"]["name_onmove"]
                }
            else
                {this.panel[i].lines[0].strokeLine = undefined}
            // eliminated_value
            this.panel[i].lines[1].text= 'lost: '+idata.eliminated_value[this.index[i]].toString()
            // eliminated pieces
            var e = elim2array(idata.eliminated[this.index[i]])
            if (e != undefined)
                {
                for (let j = 0; j < e.length; j++) {
                    this.panel[i].lines[j+2].color= theme["pieces"]["color"][(this.index[i]+2)%3]
                    this.panel[i].lines[j+2].font = pawn_size+" "+theme["pieces"]["font-family"]
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
class  hex {
    constructor(a, b, id) {
        this.x =  (a +b*(0.5 ))*(r * Math.sqrt(3))+91;
        this.y =  (1 + b * 1.5) * r;
        this.id = id;
        this.piece = {"piece":"" , "player_id":-1};
        this.hex_color =  theme["board"]["hex_color"][(a+2*b)%3] ;
        this.lumi = undefined  // R,G,B, luminiscence
        this.show_flag = true; // true means to redraw the hex
        this.valid_flag = false;
        this.promo_flag = false;
    }
    set(ipiece) {
    if (ipiece.piece !=  this.piece.piece || ipiece.player_id !=  this.piece.player_id) {
        this.show_flag = true;
        }
    this.piece.piece  = ipiece.piece;
    this.piece.player_id = ipiece.player_id;
    }
    setlumi(ilumi) {
   this.lumi = ilumi
   this.show_flag = true
    }
    draw() {
        ctx0.save()
        ctx0.beginPath();
        //ctx0.lineWidth = 3;
        //ctx0.strokeStyle = "#ff9b09"//theme["board"]["valid_move"];

        for (let i = 0; i < 6; i++) { //draw hex tile
            ctx0.lineTo(this.x + r * Math.cos((i  + 0.5)*(Math.PI / 3 )),
                       this.y + r * Math.sin((i  + 0.5)*(Math.PI / 3 )));
        }
        ctx0.closePath();
        ctx0.fillStyle = this.hex_color
        if (this.lumi != undefined) {
            ctx0.fillStyle = this.hex_color
            ctx0.fill();
            ctx0.fillStyle = this.lumi
            }
        else
        {ctx0.fillStyle = this.hex_color
        }
        //ctx0.stroke()
        ctx0.fill();
        ctx0.restore()

    }
    draw_piece2(i_lineWidth = 1, i_lineColor = "#000000") {
        draw_piece_common( this.piece.piece
                         , i_lineWidth
                         , i_lineColor
                         , theme["pieces"]["color"][(this.piece.player_id+2)%3]
                         , this.x,this.y
                         )
    }

    line_intersect2(ax,bo) {
       if (ax.u2/ax.u1 == bo.z2/bo.z1) {
            return
        }
        if (ax.u2 == 0 ) {
            var s = (ax.a2 - bo.b2) / bo.z2
        }
        else {
            var s = (ax.u1 / ax.u2 * (bo.b2 - ax.a2) + ax.a1 - bo.b1)/(bo.z1 - ax.u1 / ax.u2 * bo.z2)
        }
        var t = (bo.b1+s*bo.z1-ax.a1)/ax.u1
        var x = ax.a1+t*ax.u1
        var y = ax.a2+t*ax.u2
        B.hexs[84].x, B.hexs[84].y
        var dist = Math.sqrt(Math.pow((B.hexs[84].x - x),2) + Math.pow((B.hexs[84].y - y),2))
        if (dist < r*12.3) {

            return {"x": Math.round(x), "y":Math.round(y) }
        }
        return
    }
    draw_hex(i_width, i_color) {
        ctx0.save()
        ctx0.lineWidth = i_width
        ctx0.strokeStyle = i_color
        ctx0.beginPath()
        for (let i = 0; i < 6; i++) { //draw hex
           ctx0.lineTo(this.x + r * Math.cos((i  + 0.5)*(Math.PI / 3 )),
           this.y + r * Math.sin((i  + 0.5)*(Math.PI / 3 )));
        }
        ctx0.closePath();
        ctx0.stroke();
        ctx0.restore()
    }
    draw_mark(i_kind) {
        this.show_flag = true;
        ctx0.save();
        ctx0.strokeStyle = theme["board"]["valid_move"]
        ctx0.lineWidth = 2
        if (i_kind == 'safe') {
           ctx0.beginPath();
           ctx0.arc(this.x, this.y, r/2, 0, 2 * Math.PI);
           ctx0.stroke()
        } else if (i_kind == 'rect') {
            this.draw_hex(2,theme["board"]["valid_move"]) //curso
            ctx0.lineWidth = 0.5
            var axis = []
            axis[0] =  {"a1":this.x  ,"a2":this.y   ,   "u1":B.hexs[0].x    ,"u2":0 }
            axis[1] =  {"a1":this.x  ,"a2":this.y   ,   "u1":1/2            ,"u2":Math.sqrt(3)/2 }
            axis[2] =  {"a1":this.x  ,"a2":this.y   ,   "u1":-1/2           ,"u2":Math.sqrt(3)/2 }
            var point = []
            var j = 0
            for (let k= 0; k < 3; k++) {
                for (let i= 0; i < 6; i++) {
                    var ret = this.line_intersect2(axis[k], B.border[i])
                    if (ret != undefined) {
                        //point[j] = ret
                        if  ( point[j-1] == undefined  || !(ret.x == point[j-1].x && ret.y == point[j-1].y )) {
                                point.push(ret)
                                j++
                        }
                    }
                }

                ctx0.moveTo(point[0].x, point[0].y)
                ctx0.lineTo(point[1].x, point[1].y)
                ctx0.stroke()
                j = 0
                point = []
            }
            ctx0.stroke();
        } else if (i_kind == 'attack') {
            ctx0.beginPath();
            ctx0.moveTo(this.x-r/1.6, this.y-r/1.6);
            ctx0.lineTo(this.x+r/1.6, this.y+r/1.6);
            ctx0.moveTo(this.x+r/1.6, this.y-r/1.6);
            ctx0.lineTo(this.x-r/1.6, this.y+r/1.6);
           ctx0.stroke();
        } else {
            const a = 0;
        }
        ctx0.restore();
    }
}
// board /////////////////////////////////////////////////
class board {
    constructor() {
        this.hexs    = [];
        this.gid_old = 85;
        this.gid_new = 85;
        this.slog = "";
        this.view_player =  0;
        this.view_player_org =  0;
        this.move_number =  -1;
        this.move_number_org =  -1;
        this.move_number_max =  -1;
        this.onmove =  0;
        this.finished =  false;
        this.hist_changed =  false;
        this.border = []
        this.last_move_from =  -1
        this.last_move_to =  -1
    }
    init() {
        let cnt = 0;
        for (let i = 0; i < 15; i++) {
            for (let j = 0; j < 15 ; j++) {
                if ((j + i > 6) && (j < 15)&& (i < 15)&& (j+i < 22)) {
                    this.hexs[cnt] = new hex(j, i, cnt);
                    cnt = ++ cnt;
                }
            }
        }
        this.border[0] =  {"b1":this.hexs[0].x  ,"b2":this.hexs[0].y   ,   "z1":this.hexs[0].x    ,"z2":0 }
        this.border[1] =  {"b1":this.hexs[7].x  ,"b2":this.hexs[7].y   ,   "z1":1/2               ,"z2":Math.sqrt(3)/2 }
        this.border[2] =  {"b1":this.hexs[91].x ,"b2":this.hexs[91].y  ,   "z1":-1/2              ,"z2":Math.sqrt(3)/2 }
        this.border[3] =  {"b1":this.hexs[168].x,"b2":this.hexs[168].y ,   "z1":-this.hexs[168].y ,"z2":0 }
        this.border[4] =  {"b1":this.hexs[161].x,"b2":this.hexs[161].y ,   "z1":-1/2              ,"z2":-Math.sqrt(3)/2 }
        this.border[5] =  {"b1":this.hexs[77].x ,"b2":this.hexs[77].y  ,   "z1":1/2                ,"z2":-Math.sqrt(3)/2 }
    }
    set(idata) {
        const jdata = idata;
        this.move_number =  jdata.move_number;
        this.finished = jdata.finished;
        this.onmove = jdata.onmove;
        this.last_move_from =  jdata.last_move.from
        this.last_move_to =  jdata.last_move.to
        if (this.move_number_org == -1) {
            this.move_number_org = jdata.move_number;
        }
        if (this.move_number_max == -1) {
            this.move_number_max = jdata.move_number;
        }
        for (let z= 0; z < 169; z++) {   // clear
            this.hexs[z].set({"piece":"", "player_id":-1})
            //this.hexs[z].piece.piece = undefined
            this.hexs[z].setlumi(undefined)
        }
        for (let player_id  in jdata.pieces) {// set pieses
             for (let j in jdata.pieces[player_id]) {
                 const pcs =jdata.pieces[player_id][j];
                 this.hexs[pcs.gid].set({"piece":pcs.piece, "player_id":Number(player_id)})
            }
        }
        // set chess by
        for (let player_id  in jdata.chess_by) {
             for (let j in jdata.chess_by[player_id]) {
                 const pcs =jdata.chess_by[player_id][j];
                 this.hexs[pcs.gid].setlumi(theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"])
                 this.hexs[pcs.gid].draw_piece2( bpiece_lineWidth, theme["board"]["hint_lines"])
            }
        }
        //king_pos
        if (!(jdata.chess_by[0].length == 0 && jdata.chess_by[1].length == 0 && jdata.chess_by[2].length == 0)) {
            this.hexs[jdata.king_pos].setlumi(theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"])
            this.hexs[jdata.king_pos].draw_piece2( bpiece_lineWidth ,theme["board"]["hint_lines"])
        }
       if (jdata.king_pos != 0) {
           //this.hexs[jdata.king_pos].setlumi(theme["board"]["hex_inchess"] + theme["board"]["hex_alpha"])
       }
    }
    draw_tile() {
        for (let i = 0; i < 169; i++) {
            if (this.hexs[i].show_flag) {
                this.hexs[i].draw()
                //this.hexs[i].lumi = 0
            }
        }
    }
    draw_pieces() {
        // mark last move
        if (this.last_move_from != -1 ) {
            this.hexs[this.last_move_from].draw_hex(3, theme["board"]["last_move"] )
            this.hexs[this.last_move_to].draw_hex(3, theme["board"]["last_move"])
            //ctx0.save()
            //ctx0.lineWidth = 1
            //ctx0.strokeStyle = theme["board"]["last_move"]
            //ctx0.beginPath();
            //ctx0.moveTo(this.hexs[this.last_move_from].x, this.hexs[this.last_move_from].y )
            //ctx0.lineTo(this.hexs[this.last_move_to].x, this.hexs[this.last_move_to].y )
            //ctx0.stroke();
            //ctx0.restore()
        }
        for (let i = 0; i < 169; i++) {
            if (this.hexs[i].show_flag) {
                this.hexs[i].draw_piece2(bpiece_lineWidth)
                //this.hexs[i].lumi = 0
            }
        }
    };
    getGid(ix,iy) {
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
    moveValid() {
        if (!(this.hexs[this.gid_new].piece.piece != undefined && this.hexs[this.gid_new].piece.player_id == this.onmove)) {
            return
        }
        F.fetchPOST(url+'/api/v1/move/valid', {"slog": this.slog.substring(0,this.move_number*4), "view_pid": this.view_player, "gid": this.gid_new}, Step_valid_moves);
    }
    moveMake(inew_piece = "") {
        if (this.gid_old == -1 || this.gid_old == this.gid_new)  {return}
        if (!(this.hexs[this.gid_old].piece.piece != undefined && this.hexs[this.gid_old].piece.player_id == this.onmove)) {
            return;
            }
        if (!(this.hexs[this.gid_new].valid_flag)) {
            return;
        }
        F.fetchPOST(url+'/api/v1/move/make', {"slog": this.slog.substring(0,this.move_number*4), "view_pid": this.view_player, "gid": this.gid_old, "tgid": this.gid_new, "new_piece": inew_piece}, Step_make_move);
    }
}
//----------------------------------------------------
function elim2array(idata) {
    let s = ''
    for (i in idata) {
        s = s + pcs_map1[idata[i]]
    }
    var t = Array.from(s).sort().reverse().join('').match(/(.)\1*/g)
    s = ''
    for (i in t) {
        t[i] =  t[i].replace(t[i].charAt(0),  pcs_map2[t[i].charAt(0)])
    }
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
    F.headers.Authorization = TOKEN;
    F.fetchGET(url+'/api/v1/manager/board?id='+ID.toString(), Step_2_setplayers)
}
function Step_2_setplayers(idata) {
    II.players = [idata.player_0, idata.player_1, idata.player_2]
    B.view_player = (idata.view_pid)%3
    B.view_player_org = (idata.view_pid)%3
    B.slog = idata.slog
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Step_3_setelim_board_and_draw(idata) {
    B.set(idata);
    B.draw_tile();
    B.draw_pieces();
    B.set(idata);
    II.clear()
    II.set(idata);
    II.write()
    button_control()
    if (B.finished) {
        // Get the modal
        var name = II.players[B.onmove]
        var modal = document.getElementById("myModal");
        modal.style.color = theme["pieces"]["color"][(B.onmove+2)%3]
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
        if (B.move_number_org == B.move_number-1 && B.view_player_org == (B.onmove+2)%3 && !(B.hist_changed)  ) {
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
        document.getElementById(this.id).style.backgroundColor = '#c9c9d9'//button_color;
        document.getElementById(this.id).disabled = true;
        //document.getElementById(this.id).cursor = 'not-allowed';
    }
    else {
        document.getElementById(this.id).style.backgroundColor = this.color_enable;//'#d9d9d9' //this.color_enable;
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
    if (B.move_number_org == B.move_number-1 && B.view_player_org == (B.onmove+2)%3 ) {
    //if (B.move_number_org == B.move_number-1 && 0 == (B.onmove+2)%3 ) {
        F.fetchPOST(url+'/api/v1/manager/board', {"id": ID, "slog": B.slog.substring(0,B.move_number*4)},function () {} );
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
function Click_Rotate() {
    B.view_player = (B.view_player+1)%3
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Click_Board(event) {
    function getMouesPosition(e) {
        var mouseX = e.offsetX * canvas0.width / canvas0.clientWidth | 0;
        var mouseY = e.offsetY * canvas0.height / canvas0.clientHeight | 0;
        return {x: mouseX, y: mouseY};
    }
    const pos = getMouesPosition(event)
    if (SemaforGreen) {
        SemaforGreen = false;
        const bounds = canvas0.getBoundingClientRect()
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
                B.draw_tile();
                B.draw_pieces();
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
        B.draw_tile()
        B.hexs[B.gid_new].draw_mark('rect'); // show cursor
        B.draw_pieces()
        //if new piece promotion
        if (B.hexs[B.gid_new].promo_flag) {
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
var b_ok = new butt('b_ok', theme["canvas"]["name_onmove"])
var b_rf = new butt('b_rf', button_color )
var b_fw = new butt('b_fw', button_color )
var b_bw = new butt('b_bw', button_color )
var II = new iinfos()
var SS = new ssel()

B.init();

B.draw_tile();
II.write()

Step_1_settoken()

//F.fetchPOST(url+'/token', {username: "filio", password: ''} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "ondro", password: ''} , Step_1_settoken);
//F.fetchPOST(url+'/token', {username: "livia", password: ''} , Step_1_settoken);
