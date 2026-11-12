/* ============================================================
 * JT/T 808 编解码核心 —— 由 jt808_offline 的同一套逻辑移植而来
 *   与离线工具逐字段一致，只把「读 DOM」改成「收参数」，
 *   这样网页、命令行、模拟器三处共用一份实现，不重复造轮子。
 *
 * 规则要点（与固件 gsw_modem_validate_set_param_item() 对齐）：
 *   STRING_PARAM_LEN      = 32 → 字符串长度 1~31
 *   LONG_STRING_PARAM_LEN = 64 → 0x0013 长度 1~63
 *   0x0083 车牌 1~20；0x0011/0x0012 允许空
 *   0xF001 里程基准 0.1km，上限 42949672（×100 换米不溢出 u32）
 *   固件一次最多解析 JT808_PARAM_ITEM_MAX = 9 项
 * ============================================================ */

var FLAG = 0x7E, ESC = 0x7D, ESC_FLAG = 0x02, ESC_ESC = 0x01;

var MSG_NAME = {
  /* ---- 终端 → 平台 ---- */
  "0001":"终端通用应答","0002":"终端心跳","0003":"终端注销","0004":"终端参数查询请求",
  "0100":"终端注册","0102":"终端鉴权","0104":"查询终端参数应答","0107":"查询终端属性应答",
  "0108":"终端升级结果通知","0200":"位置信息汇报","0201":"位置信息查询应答",
  "0300":"事件报告","0301":"提问应答","0302":"信息点播/取消",
  "0400":"位置信息批量上传","0704":"定位数据批量上传","0705":"CAN总线数据上传",
  "0800":"多媒体事件信息上传","0801":"多媒体数据上传","0802":"多媒体数据上传应答",
  "0805":"摄像头立即拍摄命令应答","0900":"数据上行透传","0901":"数据压缩上报",
  "0A00":"终端RSA公钥",
  /* ---- 平台 → 终端 ---- */
  "8001":"平台通用应答","8003":"补传分包请求","8100":"终端注册应答",
  "8103":"设置终端参数","8104":"查询终端参数","8105":"终端控制",
  "8106":"查询指定终端参数","8107":"查询终端属性","8108":"下发终端升级包",
  "8201":"位置信息查询","8202":"临时位置跟踪控制","8203":"人工确认报警消息",
  "8300":"文本信息下发","8301":"事件设置","8302":"提问下发",
  "8303":"信息服务","8304":"信息点播菜单设置",
  "8400":"电话回拨","8401":"设置电话本","8500":"车辆控制",
  "8600":"设置圆形区域","8601":"删除圆形区域","8602":"设置矩形区域",
  "8603":"删除矩形区域","8604":"设置多边形区域","8605":"删除多边形区域",
  "8606":"设置路线","8607":"删除路线",
  "8700":"行驶记录参数下传","8701":"行驶记录数据上传",
  "8800":"存储多媒体数据检索","8801":"摄像头立即拍摄命令",
  "8802":"存储多媒体数据上传命令","8803":"存储多媒体数据检索应答",
  "8804":"录音开始命令","8805":"单条存储多媒体数据检索上传命令",
  "8900":"数据下行透传","8A00":"平台RSA公钥"
};

var ACK_RESULT = {0:"成功/确认",1:"失败",2:"消息有误",3:"不支持",4:"报警处理确认"};

/* 参数表 —— 与固件逐条对齐，网页参数管理直接渲染这张表 */
var PARAMS = [
  { id:0x0001, name:"终端心跳间隔", sub:"DWORD 秒 10~3600", type:"u32",
    min:10, max:3600, def:"30", on:true },
  { id:0x0010, name:"主服务器 APN", sub:"STRING 1~31", type:"str",
    minLen:1, maxLen:31, def:"CMNET", on:false },
  { id:0x0011, name:"拨号用户名", sub:"STRING 0~31", type:"str",
    minLen:0, maxLen:31, def:"", on:false },
  { id:0x0012, name:"拨号密码", sub:"STRING 0~31", type:"str",
    minLen:0, maxLen:31, def:"", on:false },
  { id:0x0013, name:"主服务器地址", sub:"STRING 1~63 不含端口", type:"host",
    minLen:1, maxLen:63, def:"xatst.richlinkcloud.com", on:true },
  { id:0x0018, name:"服务器 TCP 端口", sub:"DWORD 1~65535", type:"u32",
    min:1, max:65535, def:"1808", on:true },
  { id:0x0029, name:"缺省汇报间隔", sub:"DWORD 秒 8~1800", type:"u32",
    min:8, max:1800, def:"30", on:false },
  { id:0x0083, name:"机动车号牌", sub:"STRING 1~20", type:"str",
    minLen:1, maxLen:20, def:"", on:false },
  { id:0xF001, name:"当前仪表里程基准", sub:"DWORD 0.1km 0~42949672", type:"u32",
    min:0, max:42949672, def:"0", on:false }
];

/* ============================================================
 * 工具函数
 * ============================================================ */
function hex2(b){ return (b < 16 ? "0" : "") + b.toString(16).toUpperCase(); }
function hex4(w){ var h = w.toString(16).toUpperCase(); while (h.length < 4) h = "0" + h; return h; }
function toHex(arr, sep){ return arr.map(hex2).join(sep === undefined ? " " : sep); }
function pidHex(id){ return "0x" + id.toString(16).toUpperCase().replace(/^(.{1,3})$/, "000$1").slice(-4); }
function paramName(id){
  for (var i = 0; i < PARAMS.length; i++) if (PARAMS[i].id === id) return PARAMS[i].name;
  return "";
}

/* IMSI/手机号 → BCD[6]（国标右补 0） */
function identToBcd(s){
  var d = String(s || "").replace(/\D/g, "");
  var origLen = d.length;
  var trimmed = false;
  if (d.length === 15) { d = d.slice(-12); trimmed = true; }
  if (d.length !== 12) {
    return { ok:false, err:"需要 15 位 IMSI 或 12 位手机号，当前 " + origLen + " 位数字", d:d };
  }
  var out = [];
  for (var i = 0; i < 12; i += 2) {
    out.push(parseInt(d.charAt(i), 10) * 16 + parseInt(d.charAt(i + 1), 10));
  }
  return { ok:true, bcd:out, d:d, origLen:origLen, trimmed:trimmed };
}

/* 转义 / 反转义 */
function escapeBytes(arr){
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    if (arr[i] === FLAG)      { out.push(ESC, ESC_FLAG); }
    else if (arr[i] === ESC)  { out.push(ESC, ESC_ESC); }
    else                      { out.push(arr[i]); }
  }
  return out;
}
function unescapeBytes(arr){
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    if (arr[i] === ESC) {
      i++;
      if (i >= arr.length) throw new Error("转义不完整（报文末尾是 0x7D）");
      if (arr[i] === ESC_FLAG)     out.push(FLAG);
      else if (arr[i] === ESC_ESC) out.push(ESC);
      else throw new Error("非法转义序列 7D " + hex2(arr[i]));
    } else {
      out.push(arr[i]);
    }
  }
  return out;
}

/* 组帧：返回 { frame, raw, header, body, cs } */
function buildFrame(msgId, phoneBcd, seq, body){
  if (body.length > 0x3FF) throw new Error("消息体 " + body.length + " 字节，超出 1023 上限");
  var prop = body.length & 0x3FF;
  var header = [
    (msgId >> 8) & 0xFF, msgId & 0xFF,
    (prop >> 8) & 0xFF, prop & 0xFF
  ]
  .concat(phoneBcd)
  .concat([ (seq >> 8) & 0xFF, seq & 0xFF ]);

  var raw = header.concat(body);
  var cs = 0;
  for (var i = 0; i < raw.length; i++) cs ^= raw[i];

  var frame = [FLAG].concat(escapeBytes(raw.concat([cs]))).concat([FLAG]);
  return { frame:frame, raw:raw, header:header, body:body, cs:cs };
}

/* ============================================================
 * GBK 编码（浏览器只有 GBK 解码器，编码器靠反查表构造）
 *   中文车牌 0x0083 必须按 GBK 下发，否则设备侧是乱码
 * ============================================================ */
var _gbkMap = null;

function buildGbkMap(){
  if (_gbkMap) return _gbkMap;
  _gbkMap = Object.create(null);
  if (typeof TextDecoder === "undefined") return _gbkMap;
  var dec;
  try { dec = new TextDecoder("gbk", { fatal:false }); }
  catch (e) { return _gbkMap; }   /* 环境不支持 GBK，只能走 hex: */

  for (var b = 0x80; b <= 0xFF; b++) {
    var s1 = dec.decode(new Uint8Array([b]));
    if (s1 && s1.length === 1 && s1 !== "\uFFFD" && _gbkMap[s1] === undefined) {
      _gbkMap[s1] = [b];
    }
  }
  for (var lead = 0x81; lead <= 0xFE; lead++) {
    for (var trail = 0x40; trail <= 0xFE; trail++) {
      if (trail === 0x7F) continue;
      var s2 = dec.decode(new Uint8Array([lead, trail]));
      if (s2 && s2.length === 1 && s2 !== "\uFFFD" && _gbkMap[s2] === undefined) {
        _gbkMap[s2] = [lead, trail];
      }
    }
  }
  return _gbkMap;
}

/* 字符串 → 字节：ASCII 直通，非 ASCII 走 GBK */
function gbkEncode(str){
  var out = [], map = null;
  for (var i = 0; i < str.length; i++) {
    var ch = str.charAt(i);
    var code = str.charCodeAt(i);
    if (code < 0x80) { out.push(code); continue; }
    if (!map) map = buildGbkMap();
    var bs = map[ch];
    if (!bs) {
      throw new Error("字符「" + ch + "」无法用 GBK 编码，请改用 hex: 前缀直接给字节");
    }
    for (var k = 0; k < bs.length; k++) out.push(bs[k]);
  }
  return out;
}

/* 字节 → 显示字符串：优先 GBK 解码，避免中文车牌显示成点 */
function bytesToStr(arr){
  if (!arr || arr.length === 0) return "";
  var allAscii = true;
  for (var i = 0; i < arr.length; i++) {
    if (arr[i] < 0x20 || arr[i] >= 0x7F) { allAscii = false; break; }
  }
  if (allAscii) {
    var s = "";
    for (var j = 0; j < arr.length; j++) s += String.fromCharCode(arr[j]);
    return s;
  }
  if (typeof TextDecoder !== "undefined") {
    try {
      var t = new TextDecoder("gbk", { fatal:false }).decode(new Uint8Array(arr));
      if (t.indexOf("\uFFFD") < 0) return t;
    } catch (e) { /* 落到下面 */ }
  }
  var r = "";
  for (var k = 0; k < arr.length; k++) {
    r += (arr[k] >= 32 && arr[k] < 127) ? String.fromCharCode(arr[k]) : ".";
  }
  return r;
}

/* 字符串参数编码：支持 hex: 前缀直接给字节（跳过 GBK） */
function encodeStrParam(s){
  s = String(s === undefined || s === null ? "" : s);
  if (/^hex:/i.test(s)) {
    var h = s.slice(4).replace(/[^0-9a-fA-F]/g, "");
    if (h.length % 2) throw new Error("hex: 后面的十六进制位数必须为偶数");
    var out = [];
    for (var i = 0; i < h.length; i += 2) out.push(parseInt(h.substr(i, 2), 16));
    return out;
  }
  return gbkEncode(s);
}

/* ============================================================
 * 0x8103 / 0x8106 组包
 * ============================================================ */

/* 单条参数按类型转字节；非法抛错，消息直接可用作提示 */
function paramValueBytes(info, rawVal){
  if (info.type === "u32") {
    var t = String(rawVal == null ? "" : rawVal).trim();
    if (!/^\d+$/.test(t)) throw new Error("必须是十进制整数");
    var n = parseInt(t, 10);
    if (n < info.min || n > info.max) {
      throw new Error("范围 " + info.min + "~" + info.max + "，当前 " + n);
    }
    return { bytes:[(n >>> 24) & 0xFF, (n >>> 16) & 0xFF, (n >>> 8) & 0xFF, n & 0xFF], text:String(n) };
  }
  var b = encodeStrParam(rawVal);
  if (info.type === "host") {
    var s = String(rawVal);
    if (s.indexOf(":") >= 0) throw new Error("不能带端口，端口请单独用 0x0018 下发");
    if (s.indexOf(";") >= 0) throw new Error("不能用分号拼接多个地址");
  }
  if (b.length < info.minLen) throw new Error("不能为空（至少 " + info.minLen + " 字节）");
  if (b.length > info.maxLen) throw new Error("长度 " + b.length + " 超过上限 " + info.maxLen);
  return { bytes:b, text:String(rawVal) };
}

/* items: [{id, bytes}] → 0x8103 消息体 */
function build8103Body(items){
  var body = [items.length & 0xFF];
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    body.push((it.id >>> 24) & 0xFF, (it.id >>> 16) & 0xFF, (it.id >>> 8) & 0xFF, it.id & 0xFF);
    body.push(it.bytes.length & 0xFF);
    body = body.concat(it.bytes);
  }
  return body;
}

/* ids: [0x0001, ...] → 0x8106 消息体 */
function build8106Body(ids){
  var body = [ids.length & 0xFF];
  for (var i = 0; i < ids.length; i++) {
    var id = ids[i];
    body.push((id >>> 24) & 0xFF, (id >>> 16) & 0xFF, (id >>> 8) & 0xFF, id & 0xFF);
  }
  return body;
}

/* ============================================================
 * 电子围栏 0x8600 ~ 0x8605
 *   与固件 srv_geo_fence_808.c 逐字段对齐：
 *   设置类 0x8600 圆形 / 0x8602 矩形：
 *     [操作1][区域总数1][项 × n]
 *     圆形项 = ID4 + 属性2 + 纬度4 + 经度4 + 半径4 [+起止时间12][+限速3]
 *     矩形项 = ID4 + 属性2 + 左上纬4 + 左上经4 + 右下纬4 + 右下经4 [+12][+3]
 *   设置类 0x8604 多边形（无操作/数量前缀，单条）：
 *     ID4 + 属性2 [+12][+3] + 顶点数2 + 顶点(纬度4 + 经度4) × n
 *   删除类 0x8601 / 0x8603 / 0x8605：
 *     [区域总数1][ID4 × n]，n = 0 表示删除全部同类区域
 *   固件上限：单条设置最多 10 项（JT808_GEO_FENCE_MAX_NUM）、
 *             删除最多 40 个 ID、多边形 3~10 个顶点
 * ============================================================ */
var FENCE_INFO = {
  "8600": { shape:"circle", set:true,  name:"设置圆形区域" },
  "8601": { shape:"circle", set:false, name:"删除圆形区域" },
  "8602": { shape:"rect",   set:true,  name:"设置矩形区域" },
  "8603": { shape:"rect",   set:false, name:"删除矩形区域" },
  "8604": { shape:"poly",   set:true,  name:"设置多边形区域" },
  "8605": { shape:"poly",   set:false, name:"删除多边形区域" }
};

var FENCE_DOC = {
  "8600": "消息体：操作1 + 区域总数1 + [ID4 + 属性2 + 纬度4 + 经度4 + 半径4（+ 起止时间12）（+ 限速3）]",
  "8601": "消息体：区域总数1 + 区域ID4 × n（数量 0 = 删除全部圆形区域）",
  "8602": "消息体：操作1 + 区域总数1 + [ID4 + 属性2 + 左上纬4 + 左上经4 + 右下纬4 + 右下经4（+ 起止时间12）（+ 限速3）]",
  "8603": "消息体：区域总数1 + 区域ID4 × n（数量 0 = 删除全部矩形区域）",
  "8604": "消息体：ID4 + 属性2（+ 起止时间12）（+ 限速3）+ 顶点数2 + 顶点(纬度4 + 经度4) × n，无操作/数量前缀",
  "8605": "消息体：区域总数1 + 区域ID4 × n（数量 0 = 删除全部多边形区域）"
};

/* 区域属性位 → 属性值 */
function fencePropVal(o){
  var v = 0;
  if (o.time)  v |= 0x0001;
  if (o.speed) v |= 0x0002;
  if (o.in)    v |= 0x0008;
  if (o.out)   v |= 0x0020;
  return v;
}

/* 校验 12 位 BCD 时间字段，规则与固件 jt808_geo_fence_valid_bcd_time 一致：
   全 0 也合法；月 01~12、日 01~31、时 00~23、分秒 00~59。
   返回 null 表示合法，否则返回原因。 */
function bcdTimeErr(s){
  var d = String(s == null ? "" : s).replace(/\s/g, "");
  if (!/^\d{12}$/.test(d)) return "需为 12 位数字，当前 " + d.length + " 位";
  if (d === "000000000000") return null;
  var mo = parseInt(d.substr(2, 2), 10);
  var dy = parseInt(d.substr(4, 2), 10);
  var hh = parseInt(d.substr(6, 2), 10);
  var mi = parseInt(d.substr(8, 2), 10);
  var ss = parseInt(d.substr(10, 2), 10);
  if (mo < 1 || mo > 12) {
    return "月份 " + d.substr(2, 2) + " 非法（01~12），前两位应为年份，如 261030073000";
  }
  if (dy < 1 || dy > 31) return "日 " + d.substr(4, 2) + " 非法（01~31）";
  if (hh > 23) return "时 " + d.substr(6, 2) + " 非法（00~23）";
  if (mi > 59) return "分 " + d.substr(8, 2) + " 非法（00~59）";
  if (ss > 59) return "秒 " + d.substr(10, 2) + " 非法（00~59）";
  return null;
}

function bcdTimeBytes(s){
  if (bcdTimeErr(s)) return null;
  var d = String(s == null ? "" : s).replace(/\s/g, "");
  var out = [];
  for (var i = 0; i < 12; i += 2) {
    out.push(parseInt(d.charAt(i), 10) * 16 + parseInt(d.charAt(i + 1), 10));
  }
  return out;
}

/* datetime-local 的 "2026-10-30T07:30:00" → 12 位 YYMMDDhhmmss；格式不对返回 "" */
function dtToBcd(v){
  var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(String(v == null ? "" : v).trim());
  if (!m) return "";
  return m[1].slice(2) + m[2] + m[3] + m[4] + m[5] + (m[6] || "00");
}

/* 12 位 BCD → datetime-local 的值；全 0 或非法返回 "" */
function bcdToDt(s){
  var d = String(s == null ? "" : s).replace(/\s/g, "");
  if (bcdTimeErr(d) || d === "000000000000") return "";
  return "20" + d.substr(0, 2) + "-" + d.substr(2, 2) + "-" + d.substr(4, 2)
       + "T" + d.substr(6, 2) + ":" + d.substr(8, 2) + ":" + d.substr(10, 2);
}

/* 时间框原始值 → 12 位 BCD：空 = 全 0；非法原样返回，交给 bcdTimeErr 报原因 */
function fenceTimeBcd(raw){
  raw = String(raw == null ? "" : raw).trim();
  if (raw === "") return "000000000000";
  if (/^\d{12}$/.test(raw)) return raw;
  return dtToBcd(raw) || raw;
}

/* 十进制度 → 1e-6 度整数，大端 4 字节；非法时压入 errs 并返回 null */
function degToU32(s, isLat, errs, label){
  var t = String(s == null ? "" : s).trim();
  if (!/^-?\d+(\.\d+)?$/.test(t)) {
    errs.push(label + "需为十进制度，如 " + (isLat ? "31.230416" : "121.473701"));
    return null;
  }
  var deg = parseFloat(t);
  var lim = isLat ? 90 : 180;
  if (deg < -lim || deg > lim) {
    errs.push(label + "需在 -" + lim + " ~ " + lim + " 度，当前 " + deg);
    return null;
  }
  var v = Math.round(deg * 1000000);
  return [ (v >>> 24) & 0xFF, (v >>> 16) & 0xFF, (v >>> 8) & 0xFF, v & 0xFF ];
}

/* 无符号数 → 大端 4 字节 */
function u32Bytes(s, errs, label, min){
  var t = String(s == null ? "" : s).trim();
  if (!/^\d+$/.test(t)) { errs.push(label + "需为十进制整数"); return null; }
  var n = parseInt(t, 10);
  if (n < min || n > 4294967295) { errs.push(label + "需在 " + min + " ~ 4294967295，当前 " + n); return null; }
  return [ (n >>> 24) & 0xFF, (n >>> 16) & 0xFF, (n >>> 8) & 0xFF, n & 0xFF ];
}

/* 属性扩展位对应的时间/限速字节，顺序：时间 12 → 限速 3 */
function fenceCondBytes(prop, o, errs){
  var out = [];
  if (prop & 0x0001) {
    var t1s = fenceTimeBcd(o.time1), t2s = fenceTimeBcd(o.time2);
    var t1 = bcdTimeBytes(t1s);
    var t2 = bcdTimeBytes(t2s);
    if (!t1) errs.push("起始时间" + bcdTimeErr(t1s));
    if (!t2) errs.push("结束时间" + bcdTimeErr(t2s));
    if (t1 && t2) out = out.concat(t1, t2);
  }
  if (prop & 0x0002) {
    var sp = String(o.speedVal == null ? "" : o.speedVal).trim();
    var du = String(o.speedDur == null ? "" : o.speedDur).trim();
    var spOk = /^\d+$/.test(sp) && parseInt(sp, 10) <= 65535;
    var duOk = /^\d+$/.test(du) && parseInt(du, 10) <= 255;
    if (!spOk) errs.push("最高速度需为 0 ~ 65535 的整数");
    if (!duOk) errs.push("超速持续需为 0 ~ 255 的整数");
    if (spOk && duOk) {
      var n = parseInt(sp, 10);
      out = out.concat([ (n >>> 8) & 0xFF, n & 0xFF, parseInt(du, 10) & 0xFF ]);
    }
  }
  return out;
}

/**
 * 组电子围栏消息体。
 * o = {
 *   shape:"circle"|"rect"|"poly", set:true|false,
 *   op:0|1|2,                     // 仅设置类、圆/矩形用
 *   ids:[1,2],                    // 删除类
 *   id:1, prop:{time,speed,in,out},
 *   time1,time2,speedVal,speedDur,
 *   lat,lon,radius,               // 圆形
 *   lat1,lon1,lat2,lon2,          // 矩形
 *   points:[[lat,lon], ...]       // 多边形
 * }
 * 返回 { body, errs, prop }
 */
/**
 * 组电子围栏消息体。
 * o = {
 *   shape:"circle"|"rect"|"poly", set:true|false,
 *   op:0|1|2,                     // 仅设置类、圆/矩形用
 *   ids:[1,2],                    // 删除类
 *   id:1, prop:{time,speed,in,out},
 *   time1,time2,speedVal,speedDur,
 *   lat,lon,radius,               // 圆形
 *   lat1,lon1,lat2,lon2,          // 矩形
 *   points:[[lat,lon], ...],      // 多边形
 *   items:[{ id, shape, lat, lon, radius / lat1.. / points }, ...]
 *         // 可选：一帧多个区域项。不传时按上面单区域字段组包，行为与旧版一致。
 *         // 圆/矩形：[操作1][区域总数1][项×n]，n≤10；
 *         // 多边形 0x8604 协议本身无数量前缀，一帧只能 1 项。
 *         // 属性位/起止时间/限速对所有项共用，取 o 上的值。
 * }
 * 返回 { body, errs, prop }
 */
function buildFenceBody(o){
  var errs = [], body = null;
  var prop = fencePropVal(o.prop || {});

  /* ---- 删除类 ---- */
  if (!o.set) {
    var ids = o.ids || [];
    if (ids.length > 40) {
      errs.push("固件最多删除 40 个 ID（GEO_FENCE_MAX_NUM），当前 " + ids.length);
    }
    body = [ ids.length & 0xFF ];
    for (var i = 0; i < ids.length; i++) {
      var b = u32Bytes(ids[i], errs, "第 " + (i + 1) + " 个区域 ID", 1);
      if (b) body = body.concat(b);
    }
    return { errs:errs, body:errs.length ? null : body, prop:prop };
  }

  /* ---- 设置类：单区域走 o 本身，多区域走 o.items ---- */
  var items = (o.items && o.items.length) ? o.items : [o];
  if (items.length > 10) {
    errs.push("单条最多设置 10 个区域（固件上限），当前 " + items.length + " 个，请分批下发");
  }
  if (o.shape === "poly" && items.length > 1) {
    errs.push("0x8604 一帧只能带 1 个多边形区域，当前 " + items.length + " 个，请分批下发");
  }
  /* 单区域时错误文案保持原样，多项时才带序号 */
  function lab(prefix, n){
    return items.length === 1 ? prefix : "第 " + (n + 1) + " 个区域·" + prefix;
  }

  var cond = null;
  var all = [];
  for (var n = 0; n < items.length; n++) {
    var it = items[n];
    var shape = it.shape || o.shape;
    var head = [];
    var idb = u32Bytes(it.id, errs, lab("区域 ID", n), 1);
    if (idb) head = head.concat(idb);
    head = head.concat([ (prop >> 8) & 0xFF, prop & 0xFF ]);
    /* 属性扩展位对所有项相同，只算一次，但仍在 ID 之后算（报错次序与旧版一致） */
    if (n === 0) cond = fenceCondBytes(prop, o, errs);

    if (shape === "circle") {
      var lat = degToU32(it.lat, true, errs, lab("中心纬度", n));
      var lon = degToU32(it.lon, false, errs, lab("中心经度", n));
      var rad = u32Bytes(it.radius, errs, lab("半径", n), 1);
      if (lat) head = head.concat(lat);
      if (lon) head = head.concat(lon);
      if (rad) head = head.concat(rad);
      all.push(head.concat(cond));

    } else if (shape === "rect") {
      var la1 = degToU32(it.lat1, true,  errs, lab("左上纬度", n));
      var lo1 = degToU32(it.lon1, false, errs, lab("左上经度", n));
      var la2 = degToU32(it.lat2, true,  errs, lab("右下纬度", n));
      var lo2 = degToU32(it.lon2, false, errs, lab("右下经度", n));
      if (la1) head = head.concat(la1);
      if (lo1) head = head.concat(lo1);
      if (la2) head = head.concat(la2);
      if (lo2) head = head.concat(lo2);
      all.push(head.concat(cond));

    } else {                                  /* 多边形：单条、无操作/数量前缀 */
      var lines = it.points || [];
      if (lines.length < 3 || lines.length > 10) {
        errs.push("多边形顶点需 3 ~ 10 个，当前 " + lines.length);
      }
      var pts = [];
      for (var k = 0; k < lines.length; k++) {
        var pla = degToU32(lines[k][0], true,  errs, "第 " + (k + 1) + " 个顶点纬度");
        var plo = degToU32(lines[k][1], false, errs, "第 " + (k + 1) + " 个顶点经度");
        if (pla && plo) pts.push(pla.concat(plo));
      }
      var one = head.concat(cond, [ (pts.length >> 8) & 0xFF, pts.length & 0xFF ]);
      for (var m = 0; m < pts.length; m++) one = one.concat(pts[m]);
      all.push(one);
    }
  }

  if (o.shape === "poly") {
    body = all[0];
  } else {
    body = [ (parseInt(o.op, 10) || 0) & 0xFF, items.length & 0xFF ];
    for (var q = 0; q < all.length; q++) body = body.concat(all[q]);
  }

  return { errs:errs, body:errs.length ? null : body, prop:prop };
}

/* 0x8105 终端控制：命令字 2 带 9 字段参数串，其余无参数 */
function build8105Body(cmdWord, cmdParam){
  var body = [ cmdWord & 0xFF ];
  if (cmdParam && cmdWord === 2) body = body.concat(encodeStrParam(cmdParam));
  return body;
}
