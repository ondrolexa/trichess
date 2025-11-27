const canvas0 = document.getElementById('canvas');
canvas0.addEventListener('mouseclick', Click_Board);
const canW = canvas0.width
const canH = canvas0.   height
const ctx0 = canvas0.getContext('2d');
ctx0.lineCap = 'round';

const url = `${window.location.protocol}//${window.location.host}`;
const r = 94 // radius
const piece_size = 15;
const bpiece_lineWidth = 0.2
const epiece_lineWidth = 0.3
const lineWidth = 12
const lineStroke = 20
const boardXoffset = 450
const boardYoffset = 8
const mame_size = "150px";
const info_size = "100px";//r.toString()+"px";
const modal_wt = new bootstrap.Modal(document.getElementById("waitingMsg"))
// todo vsetky konstanty vytiahnut sem
let SemaforGreen = true
let SemaforWait = false

// tools /////////////////////////////////////////////
function isMobile() {
  const regex = /Mobi|Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
  return regex.test(navigator.userAgent);
}
function wait_msg(yes) {
    const tx = document.getElementById("waitingText")
    if (yes  && !(SemaforWait)) {
        SemaforWait = true
        setTimeout(function (){
            if ( SemaforWait ) {
                tx.style.color = theme["canvas"]["name_inchess"]
                modal_wt.show()
            }
        }, 1000);
    }
 }
function debug(itext) {
        window.alert("Debug:"+itext)
}
function rotateArray(arr, rotateBy) {
    const n = arr.length;
    rotateBy %= n;
    return arr.slice(rotateBy).concat(arr.slice(0, rotateBy));
}
function draw_piece_common( i_piece, i_lineWidth = 1, i_lineColor = "#000000", i_fillColor = "#000000", i_x, i_y , i_rotate = 0 , i_hp = piece_size, i_hs = 0, i_vs = 0, i_vp = piece_size) {
        if (i_piece != undefined ||  i_piece != "") {
            var path = new Path2D(pieces_paths["pieces"][i_piece]);
            ctx0.save()
            ctx0.lineWidth = i_lineWidth
            ctx0.fillStyle = i_fillColor
            ctx0.strokeStyle = i_lineColor
            ctx0.transform(i_hp,i_hs,i_vs,i_vp , i_x, i_y);
            ctx0.rotate(i_rotate * Math.PI / 180);
            ctx0.fill(path)
            ctx0.stroke(path);
            ctx0.restore()
        }
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
            wait_msg(true)
            if (!response.ok) {
                if (response.status == 401) {
                    window.alert('Token expired. Reload the page.');
                    location.reload();
                    return
                }
                else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            return response.json();
            })
            .then(data => {
                             SemaforWait = false //todo
                             modal_wt.hide()
                            icallback(data)
            })
            .catch(error => {//wait_msg(false )
                             SemaforWait = false //todo
                             modal_wt.hide()
                             debug('Error:'+error+' url:'+iurl)
            })
    }
    fetchGET(iurl,  icallback) {
        fetch(iurl, {
            method: 'GET',
            headers: this.headers,
        })
            .then(response => {
            wait_msg(true)
            if (!response.ok) {
                if (response.status == 401) {
                    window.alert('Token expired. Reload the page');
                    location.reload();
                    return
                }
                else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            return response.json();
            })
            .then(data => {
                            icallback(data)
                            })
            .catch(error => {//wait_msg(false)
                             SemaforWait = false //todo
                             modal_wt.hide()
                             debug('Error:'+error+' url:'+iurl)
                             })
    };
}
// ssel - promotion ////////////////////////////////////////////////
class ssel {
    constructor(){
        this.active = false
        this.line = []
        this.line[0] = new llines('Select piece:', 2160, 1040, 'center', 200, mame_size+" "+theme["pieces"]["font-family"] , theme["canvas"]["info"] )
        this.line[1] = new llines('QRBN'         , 1880, 1170, 'center', 200, info_size+" "+theme["pieces"]["font-family"] , 'green', 2, theme["pieces"]["stroke-color"])
    }
    getpromo(ix,iy) {
        const possx = 1865
        const possy = 1090
        const ps =  piece_size*10
        const pcs = ["Q","R","B","N"]
        for (let i = 0; i < 4; i++) {
            if ( possx+i*ps < ix && ix < possx+(i+1)* ps  && possy < iy && iy < possy+ps ) {
                return pcs[i]
            }
        }
        return ""
    }
    write() {
        ctx0.save()
        ctx0.beginPath()
        ctx0.fillStyle =  theme["canvas"]["background"];
        ctx0.rect(1670,894, 978, 375);
        ctx0.fill()
        const possx = 1900
        const possy = 1100
        const ps =  piece_size*9 //todo
        ctx0.strokeLine = 40
        for (let i = 0; i < 4; i++) {
            ctx0.rect(possx,possy, ps+i*ps, ps);
         }
        ctx0.closePath()
        ctx0.stroke()
        ctx0.restore()
        this.line[0].write()
        this.line[1].draw()
        this.active = true
        ctx0.restore()
    }
}
// llines ////////////////////////////////////////////////
class llines {
    constructor(itext, ipos_x, ipos_y, ialign, ilength, ifont, icolor, istrokeLine, istrokeColor ) {
        this.player_id   = -1
        this.text        = itext;
        this.pos_x       = ipos_x;
        this.pos_y       = ipos_y;
        this.align       = ialign;
        this.length      = ilength
        this.font        = ifont;
        this.color       = icolor;
        this.strokeLine  = istrokeLine
        this.strokeColor = istrokeColor
        ctx0.font = ifont
        this.text_width = ctx0.measureText(this.text).width // todo orezavat prilis dlhy text
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
        ctx0.closePath();
        ctx0.restore()
    }
    draw() {
        // text zisti pocet znakov
        if (!(this.text == "" || this.text == undefined)) {
            var offset = piece_size*6
            var dist = piece_size*9
            var align = 1
            var strokeColor = this.strokeColor
            var c = 0
            if (this.align == "right") { align = -1}
            for ( let i = 0; i < this.text.length; i++) {
                if (this.text[i] == "B" && this.player_id != -1) {
                    strokeColor = B.bishop_elim[this.player_id][c]
                    c++
                }
                draw_piece_common( this.text[i] //elimineted pieces
                                 , epiece_lineWidth
                                 , strokeColor
                                 , this.color
                                 , this.pos_x + align * (offset + i * dist)
                                 , this.pos_y)
            }
        }
    }
}
// iinfo  ////////////////////////////////////////////////
class iinfo {
    constructor(iinfo_id, ipos_x, ipos_y, ialign, ivert) { // todo revizia attr. a upratat
        this.info_id = iinfo_id
        this.x     = ipos_x
        this.y     = ipos_y
        this.align = ialign
        this.vert  = ivert
        var line_len = 260
        var line_high = 1.5*r
        this.text = []
        this.lines  = []
        line_len  = line_len - 30
        var inf_ofs = 0
        const dist_top=  30 // top and bottom distance
        var nam_ofs = (Number(mame_size.substring(0, mame_size.length - 2))+dist_top) * ivert
        if (ivert == -1) {
            nam_ofs = dist_top*ivert
        }
        if (ivert == 1) {
            inf_ofs = nam_ofs+dist_top+Number(info_size.substring(0, info_size.length - 2))
        }
        else {
            inf_ofs = (Number(mame_size.substring(0, mame_size.length - 2))+dist_top)*ivert + dist_top*ivert
        }
        // info block
        if (iinfo_id == 3) { //todo
            for (let i = 0; i < 7; i++) {
            this.lines[i] =  new llines('00', ipos_x, ipos_y+line_high*i*ivert, ialign, line_len, info_size+" "+theme["canvas"]["font-family"], theme["canvas"]["info"])
            }
        }
        // player info
        else {
            // player name
            this.lines[0] =  new llines('', ipos_x, ipos_y + nam_ofs, ialign, line_len, mame_size+" "+theme["canvas"]["font-family"] , theme["canvas"]["name"] )
            this.lines[1] =  new llines('', ipos_x, ipos_y + inf_ofs, ialign, line_len, info_size+" "+theme["canvas"]["font-family"], theme["pieces"]["color"][iinfo_id], 10, theme["pieces"]["stroke-color"])
            // elimited
            var ofs  = inf_ofs + (40+Number(mame_size.substring(0, mame_size.length - 2)))*ivert
            if (ivert == 1) { ofs  = ofs -70 } //todo
            for (let i = 2; i < 7; i++) {
                line_len  = line_len-18
                this.lines[i] =  new llines('', ipos_x, ipos_y+ofs+(i-2)*line_high*ivert, ialign, line_len, (piece_size*15).toString()+" "+theme["canvas"]["font-family"] , theme["pieces"]["color"][iinfo_id], 2, theme["pieces"]["stroke-color"])
            }
        }
    }
    clear() {
        var a = -1
        var h = canH/14
        var w = canW/3
        var d = canW/45 //sklon
        if (this.align == "left") { a = 1}
         //ctx0.save ()
         //ctx0.beginPath()
         //ctx0.fillStyle = "balck"
        for (let i = 0; i < 7; i++) {
            this.lines[i].text = ""
            if (a==1 && this.vert ==1) {
                ctx0.clearRect(0, 0 + this.vert*i*h  , a*(w-(i*d)), this.vert*h)
            }
            else if (a==1 && this.vert == -1) {
                ctx0.clearRect(0, canH + this.vert*i*h  , a*(w-(i*d)), this.vert*h)
            }
            if (a== -1 && this.vert ==1) {
                ctx0.clearRect(canW, 0 + this.vert*i*h  , a*(w-(i*d)), this.vert*h)
            }
            else if (a== -1 && this.vert == -1) {
                ctx0.clearRect(canW, canH + this.vert*i*h  , a*(w-(i*d)), this.vert*h)
            }
        }
        //ctx0.closePath();
        //ctx0.fill()
        ctx0.restore()
    }
    write() {
    //this.clear()
    for (let i = 0; i < 2; i++) {
            this.lines[i].write()
        }
    for (let i = 2; i < 7; i++) {
        if (this.info_id != 3 ) {
            this.lines[i].draw()
        }
        else {
            this.lines[i].write()
        }
        }
    }
  }
class iinfos {
    constructor() {
    var a = theme["canvas"]["font-family"]
    var dist_rl = 150
    this.panel = []
    this.players = []
    this.index = []
    this.panel[0] = new iinfo(0, canW-dist_rl   , canH-50   , 'right', -1)
    this.panel[1] = new iinfo(1, dist_rl        , 0      , 'left' ,  1)
    this.panel[2] = new iinfo(2, canW-dist_rl   , 0    , 'right', 1)
    this.panel[3] = new iinfo(3, dist_rl        , canH-50   , 'left' , -1)
    }
    set (idata) {
        this.index = rotateArray([0,1,2], B.view_player) //todo
        this.panel[3].lines[5].text = 'Game ID: '+ID.toString()
        this.panel[3].lines[4].text= 'Move: '+B.move_number_org.toString()+'/'+B.move_number.toString()
        if ( idata.vote_results != null ) {
            let verb = ' offers '
            let j = 0
            let vc = 0  // vote count
            for (let i = 0; i < 3 ; i++) {
                if (idata.vote_results[i] != "X") {
                    vc++
                }
            }
            let index2 = rotateArray([0,1,2], idata.onmove-vc ) //todo
            for (let i = 0; i < 3 ; i++) {
                if (idata.vote_results[index2[i]] == 'A') {
                    this.panel[3].lines[2-j].text =  this.players[index2[i]].substr(0,12)+ verb + idata.vote_results.kind+'.'
                    verb = ' accepts '
                    j++
                }
                else if (idata.vote_results[index2[i]] == 'D') {
                    this.panel[3].lines[2-j].text = this.players[index2[i]] + ' declines ' +idata.vote_results.kind+'.'
                    j++
                }
                else {
                    //this.panel[3].lines[4-i].text = this .players[index2[i]]+' XXXX'
                }
            }
        }
        else {
            // power lines
            this.power_lines(idata)
        }
        for (let i = 0; i < 3; i++) {
            this.panel[i].lines[0].text = this.players[this.index[i]] // set players names
            for (let z= 0; z < 7; z++) {
                this.panel[i].lines[z].player_id = this.index[i]
            }
        }
        for (let i = 0; i < 3; i++) {
            // highlight players
            if (this.index[i] == idata.onmove) {
                this.panel[i].lines[0].strokeLine = 5
                this.panel[i].lines[0].strokeColor = theme["canvas"]["name"]
                this.panel[i].lines[0].color = theme["canvas"]["name_onmove"]
                }
            else {
                this.panel[i].lines[0].strokeLine = 0
                this.panel[i].lines[0].color = theme["canvas"]["name"]
                }
            // eliminated_value / pieces_value
            this.panel[i].lines[1].color= theme["pieces"]["color"][(this.index[i]+2)%3]
            this.panel[i].lines[1].text= ""// idata.eliminated_value[this.index[i]].toString()
            // eliminated pieces
            var e = elim2array(idata.eliminated[this.index[i]])
            if (e != undefined)
                {
                for (let j = 0; j < e.length; j++) {
                    this.panel[i].lines[j+2].color= theme["pieces"]["color"][(this.index[i]+2)%3]
                    this.panel[i].lines[j+2].text= e[j]
                    }
                }
        }
    }
    power_lines(idata){//i_width, i_color, i_r) {
        let high = 100
        let x = II.panel[3].x+5
        let y = II.panel[3].y-5
        let p = 0 //power
        ctx0.save()
        ctx0.lineWidth = 5//*epiece_lineWidth
        ctx0.strokeStyle = theme["pieces"]["stroke-color"]
        for (let i = 0; i < 3; i++) { //draw hex
            ctx0.beginPath()
            ctx0.fillStyle = theme["pieces"]["color"][(this.index[i]+2)%3]
            y = y - high
            p = idata.pieces_value[this.index[i]]
            ctx0.rect(x,y, 1200/50*p, high)
            ctx0.fill()
            ctx0.stroke()
            ctx0.closePath()
        }
        ctx0.restore()
        this.panel[3].lines[3].pos_y = y - 20
        this.panel[3].lines[3].text = 'Power:'
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
    getVoteHist() {
        const msg = this.panel[3].lines.map(({ text }) => text)
        const msg1 = msg.reverse().slice(3,7)
        return msg1.join("<br>")
    }
}
// hex ///////////////////////////////////////////////////
class  hex {
    constructor(a, b, id) {
        this.x =  (a +b*(0.5 ))*(r * Math.sqrt(3))+ boardXoffset
        this.y =  ((1 + b * 1.5) * r) + boardYoffset
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
        ctx0.closePath()
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
    draw_hex(i_width, i_color, i_r) {
        ctx0.save()
        ctx0.lineWidth = i_width
        ctx0.strokeStyle = i_color
        ctx0.beginPath()
        for (let i = 0; i < 6; i++) { //draw hex
           ctx0.lineTo(this.x + r*(i_r) * Math.cos((i  + 0.5)*(Math.PI / 3 )),
           this.y + r*(i_r) * Math.sin((i  + 0.5)*(Math.PI / 3 )));
        }
        ctx0.closePath();
        ctx0.stroke();
        ctx0.restore()
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
    draw_mark(i_kind) {
        this.show_flag = true;
        ctx0.save();
        ctx0.strokeStyle = theme["board"]["valid_move"]
        ctx0.lineWidth = lineWidth
        ctx0.beginPath();
        if (i_kind == 'safe') {
           ctx0.arc(this.x, this.y, r/2, 0, 2 * Math.PI);
        } else if (i_kind == 'rect') {
            this.draw_hex(lineWidth, theme["board"]["valid_move"],0.85) //curso
            ctx0.lineWidth = lineWidth/5
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
                j = 0
                point = []
            }
        } else if (i_kind == 'attack') {
            ctx0.moveTo(this.x-r/1.6, this.y-r/1.6);
            ctx0.lineTo(this.x+r/1.6, this.y+r/1.6);
            ctx0.moveTo(this.x+r/1.6, this.y-r/1.6);
            ctx0.lineTo(this.x-r/1.6, this.y+r/1.6);
        } else {
            const a = 0;
        }
        ctx0.closePath();
        ctx0.stroke()
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
        this.last_move_from =  -1
        this.last_move_to =  -1
        this.onmove =  0;
        this.finished =  false;
        this.hist_changed =  false;
        this.border = []
        this.bishop_elim = []
        this.slog_pointer = -1
        this.vote_needed = false
        this.vote_results_kind = 'x'
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
    bishop_elim_color() {
        var c = []
        for (let j= 0; j < 3; j++) {
            c[j] = theme["board"]["hex_color"]
        }
        for (let z= 0; z < 169; z++) {
            if (this.hexs[z].piece.piece == "B") {
                var p = c[this.hexs[z].piece.player_id].slice()
                var t = p.indexOf(this.hexs[z].hex_color)
                if (t > -1) { // only splice array when item is found
                    p.splice(t, 1); // 2nd parameter means remove one item only
                    c[this.hexs[z].piece.player_id] = p
                }
                //https://stackoverflow.com/questions/5767325/how-can-i-remove-a-specific-item-from-an-array-in-javascript
            }
        }
        this.bishop_elim = c
    }
    set(idata) {
        const jdata = idata;
        this.move_number =  jdata.move_number //this.slog.length/4//jdata.move_number;
        this.finished = jdata.finished;
        this.onmove = jdata.onmove;
        this.vote_needed = jdata.vote_needed
        if (jdata.vote_results != null) {
            this.vote_results_kind= jdata.vote_results.kind
        }
        if (jdata.last_move != null) {
            this.last_move_from =  jdata.last_move.from
            this.last_move_to =  jdata.last_move.to
        }
        if (this.move_number_org == -1) {
            this.move_number_org = jdata.move_number //this.slog.length/4//jdata.move_number;
        }
        if (this.move_number_max == -1) {
            this.move_number_max = jdata.move_number //this.slog.length/4 //jdata.move_number;
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
       this.bishop_elim_color()
    }
    draw_border () {
        ctx0.save()
        ctx0.beginPath();

        ctx0.lineWidth = 10;
        ctx0.strokeStyle = theme["board"]["border"];
        ctx0.transform(1.004,0,0,1.004, -9 , -5);

        var rb = r*1.0
        var x1 = this.hexs[0].x + rb * Math.cos( 7/6*Math.PI )
        var y1 = this.hexs[0].y + rb * Math.sin( 7/6*Math.PI )
        var x2 = this.hexs[0].x + rb * Math.cos( 3/2*Math.PI )
        var y2 = this.hexs[0].y + rb * Math.sin( 3/2*Math.PI )
        var dist = Math.sqrt( Math.pow((x1-x2), 2) + Math.pow((y1-y2), 2) )
        ctx0.moveTo(x1, y1)
        ctx0.lineTo(x2, y2)
        var d = 1
        var a1 = 0
        var a2 =  -1/6
        var m = 1
        var l = 15
        for (let j = 0; j < 90; j++) {
            if ( j%15 == 0 ) {
                    a1 = a2         //-1/6
                    a2 = a1+1/3     // 1/6
                if ( j%30 == 0 ) {m = 1} else {m = 0}
            }
             if (j%2 == m )
                 { d=a1}
             else {d=a2}
             x1 = x2
             y1 = y2
             x2 = x1 + dist * Math.cos(d*Math.PI )
             y2 = y1 + dist * Math.sin(d*Math.PI )
             ctx0.moveTo(x1, y1)
             ctx0.lineTo(x2, y2)

            }
        ctx0.closePath()
        ctx0.stroke()
        ctx0.restore()
    }
    draw_tile() {
        for (let i = 0; i < 169; i++) {
            if (this.hexs[i].show_flag) {
                this.hexs[i].draw()
                //this.hexs[i].lumi = 0
            }
        }
        this.draw_border ()
    }

    draw_pieces() {
        // mark last move
        if (this.last_move_from != -1 ) {
            this.hexs[this.last_move_from].draw_hex(lineWidth, theme["board"]["last_move"],1 )
            this.hexs[this.last_move_to].draw_hex(lineWidth, theme["board"]["last_move"], 1)
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
    return this.gid_new;
};
    getSlog() {
        let slog = this.slog.substr(0,this.slog_pointer*4)
        return slog
    }
    // move ---------------------------------------------
    moveValid() {
        if (!(this.hexs[this.gid_new].piece.piece != undefined && this.hexs[this.gid_new].piece.player_id == this.onmove)) {
            return
        }
        F.fetchPOST(url+'/api/v1/move/valid', {"slog":  this.getSlog(), "view_pid": this.view_player, "gid": this.gid_new}, Step_valid_moves);
    }
    moveMake(inew_piece = "") {
        if (this.gid_old == -1 || this.gid_old == this.gid_new)  {return}
        if (!(this.hexs[this.gid_old].piece.piece != undefined && this.hexs[this.gid_old].piece.player_id == this.onmove)) {
            return;
            }
        if (!(this.hexs[this.gid_new].valid_flag)) {
            return;
        }
        F.fetchPOST(url+'/api/v1/move/make', {"slog": this.getSlog(), "view_pid": this.view_player, "gid": this.gid_old, "tgid": this.gid_new, "new_piece": inew_piece}, Step_make_move);
    }
}
// Button ////////////////////////////////////////////////////////////////////////////////
class butt {
    constructor (iid, icolor) {
        this.id = iid;
        this.disabled = true;
        this.color_enable = icolor;
}
};
//----------------------------------------------------
function elim2array(idata) {
    const pcs_map1 = {"":"", "P":"♟", "N":"♞", "B":"♝", "R":"♜", "Q":"♛", "K":"♚"}
    const pcs_map2 = {"":"", "♟":"P", "♞":"N", "♝":"B", "♜":"R", "♛":"Q", "♚":"K"}
    let s = ''
    for (i in idata) {
        s = s + pcs_map1[idata[i]]
    }
    var t = Array.from(s).sort().reverse().join('').match(/(.)\1*/g)
    s = ''
    for (i in t) {
        t[i] =  t[i].replaceAll(t[i].charAt(0),  pcs_map2[t[i].charAt(0)])
    }
    return t;
}
function Step_make_move(idata) {
         B.slog = idata.slog;
         B.slog_pointer = idata.slog.length/4
         B.hexs[B.gid_old].piece.piece = "";
         B.hexs[B.gid_old].piece.player_id = -1;
         if (B.move_number_org > B.move_number) {
             B.hist_changed =  true;
         }
         B.move_number_max = B.move_number+1;
         B.slog_pointer = B.slog_pointer+1;
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
    SemaforWait = false //todo
    modal_wt.hide()
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
    B.slog_pointer = idata.slog.length/4
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Step_5_game_info() {
    F.fetchPOST(url+'/api/v1/game/info', {"slog": B.slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)

}
function Step_4_set_votedraw(idata) {
    B.slog = idata.slog
    B.slog_pointer = idata.slog.length/4
    F.fetchPOST(url+'/api/v1/manager/board', {"id": ID, "slog": B.slog}, Step_5_game_info )
}
function Step_3_setelim_board_and_draw(idata) {
    B.set(idata);
    B.draw_tile();
    B.draw_pieces();
    II.clear()
    II.set(idata);
    II.write()
    button_control()
    //setTimeout(function (){
    if ( idata.vote_needed && B.view_player_org == B.onmove && B.slog_pointer == B.slog.length/4) {
        window_vote(B.vote_results_kind , II.getVoteHist())
        }
    //}, 0)
        if (B.finished ) {
            var name = II.players[B.onmove]
            const modal_go = new bootstrap.Modal(document.getElementById("gameOver"))
            const vp = document.getElementById("goVotePlayers")
            //const a =  document.querySelectorAll('.modalwait')[0].style
            //const b =  document.getElementById("gameOverText").style.cssText
        if (idata.vote_results == null) {
            vp.innerHTML = "<br>"+name+" lost :-("
            //vp.style.color = theme["pieces"]["color"][(B.onmove+2)%3]
            //vp.style.backgroundColor = "#000000"
            }
        else if (B.vote_results_kind == 'draw' || B.vote_results_kind == 'resign') {
            const modal_go = new bootstrap.Modal(document.getElementById("gameOver"))
            vp.innerHTML = II.getVoteHist()
            modal_go.show()
            }
        else {
            }
        SemaforWait = false //todo
        modal_wt.hide()
        modal_go.show()
    }
    //setTimeout(function (){
    SemaforWait = false
    modal_wt.hide()
    //}, 0);

}
function button_control() {
        if (B.move_number_org == B.move_number && B.view_player_org == B.onmove ) {  //&& SemaforVoteDraw
            document.getElementById("b_dr").disabled = false;
            document.getElementById("b_rs").disabled = false;
        }
        else {
            document.getElementById("b_dr").disabled = true;
            document.getElementById("b_rs").disabled = true;
        }
        if (B.move_number_org == B.move_number-1 && B.view_player_org == (B.onmove+2)%3 && !(B.hist_changed)) {
            document.getElementById("b_ok").disabled = false;
            document.getElementById("b_ok").style.backgroundColor = theme["canvas"]["name_onmove"]
        }
        else {
            document.getElementById("b_ok").style.backgroundColor = "#6c757d"
            document.getElementById("b_ok").disabled = true;
        }
        if (B.move_number == 0) {
            document.getElementById("b_bw").disabled = true;
        }
        else {
            document.getElementById("b_bw").disabled = false;
        }
        if (B.slog_pointer == B.slog.length/4) {
            document.getElementById("b_fw").disabled = true
        }
        else {
            document.getElementById("b_fw").disabled = false
        }
}
function window_vote(ikind,itext) {
    //var modal = document.getElementById("voteDrawDialog");
    const modalDraw = new bootstrap.Modal(document.getElementById("voteDialog"))
    const vp = document.getElementById("votePlayers")
    const vk1 = document.getElementById("voteKind1")
    const vk2 = document.getElementById("voteKind2")
    const av = document.getElementById("acceptVote")
    vp.innerHTML = itext
    vk1.innerHTML = ikind
    vk2.innerHTML = ikind
    if (ikind == 'draw') {
        av.innerHTML = 'accept'
    }
    else {
        av.innerHTML = 'vote'
    }
    modalDraw.show()
}

// Click ////////////////////////////////////////////////////////////////////////////////
function Click_Vote(ivalue)   {
    if ( !B.vote_needed &&  !ivalue) {
        return //chncel decline
    }
    F.fetchPOST(url+'/api/v1/vote/'+B.vote_results_kind, {"slog": B.slog, "view_pid": B.view_player, "vote":ivalue }, Step_4_set_votedraw )
}
function Click_Draw() {
    let b_decline = document.getElementById('b_decline');
    b_decline.style.display = 'none'
    B.vote_results_kind = 'draw'
    window_vote('draw', ["Do you want to offer the draw?"])
}
function Click_Resign() {
    let b_decline = document.getElementById('b_decline');
    b_decline.style.display = 'none'
    B.vote_results_kind = 'resign'
    window_vote('resign', ["Do you want to offer the resignation?"])
}
function Click_Backward() { //todo
    B.slog_pointer = B.slog_pointer-1
    let slog = B.slog.substr(0,B.slog_pointer*4)
    //let slog = SlogBack(B.slog)
    F.fetchPOST(url+'/api/v1/game/info', {"slog": slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Click_Forward() { //todo
    B.slog_pointer = B.slog_pointer+1
    let slog = B.slog.substr(0,B.slog_pointer*4)
    F.fetchPOST(url+'/api/v1/game/info', {"slog": slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
}
function Click_OK() {
    if (B.move_number_org == B.move_number-1 && B.view_player_org == (B.onmove+2)%3 ) {
        B.slog_pointer = B.move_number+1;
        F.fetchPOST(url+'/api/v1/manager/board', {"id": ID, "slog": B.getSlog()},function () {SemaforWait = false;modal_wt.hide()} );
    }
    B.move_number_org = -1
    B.move_number_max = -1
    document.getElementById("b_ok").disabled = false;
    document.getElementById("b_ok").style.backgroundColor = "#9fa5aa"
    B.hist_changed = false
}
function Click_Refresh()    {
    B.move_number_max = -1;
    B.move_number_org = -1;
    B.hist_changed = false
    F.fetchGET(url+'/api/v1/manager/board?id='+ID.toString(), Step_2_setplayers)
};
function Click_Rotate() {
    let slog = B.getSlog()
    B.view_player = (B.view_player+1)%3
    F.fetchPOST(url+'/api/v1/game/info', {"slog": slog, "view_pid": B.view_player }, Step_3_setelim_board_and_draw)
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
        let x = pos.x
        let y = pos.y
        //if pieces window is open
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
            SS.line[1].color = theme["pieces"]["color"][(B.onmove+2)%3]
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
if (isMobile()) {
    document.getElementById("baseFooter").classList.remove("footer");
}
var B = new board()
var F = new fetchData()
var II = new iinfos()
var SS = new ssel()
B.init();
B.draw_tile();
Step_1_settoken()

