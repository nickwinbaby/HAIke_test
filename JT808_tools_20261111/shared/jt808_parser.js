/* ============================================================
 * JT/T 808-2013 报文反解 —— 由 jt808_offline 的同一套实现移植而来
 *   50 种消息体解析器，一条消息一个函数，返回 JSON 友好对象。
 *   依赖 jt808_codec.js（hex2/hex4/toHex/unescapeBytes/bytesToStr/paramName）。
 * ============================================================ */

/* 全局剪贴板与转义：网页里 toast / 复制由调用方注入 */
function escapeHtml(s){
  return String(s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}

/* ============================================================
 * 反解
 *   1) 支持有空格 / 无空格 / 多条连续 / 带日志前缀
 *   2) 多帧自动拆分，逐帧独立解析
 *   3) 输出结构对齐现场用的 JSON 视图 + 中文表格两种
 * ============================================================ */

/* ---------- 1. 从任意文本里切出所有 7E…7E 帧 ---------- */
/**
 * 难点：日志前缀（"[11:02:33.441] RX <- "）里也含十六进制数字，
 * 直接 strip 非 hex 字符会让 "7E" 落在奇数字节边界的错位位置上。
 * 所以改成：找到所有 7E 出现位置，逐个尝试 + 用消息体属性里的长度字段自校验，
 * 自洽才算一帧。这样有无空格、有无前缀、多条拼接都能正确切。
 */
function splitFrames(text){
  var s = String(text || "").toUpperCase();

  /* 把文本切成若干"十六进制片段"：
   * 连续 hex 字符（中间允许空白）算一段，遇到别的字符就断开。
   * 这样日志前缀里的 "2026-10-30" / "[11:02:33.441]" 会被切成独立小段，
   * 不会和真正的报文粘在一起造成字节错位。 */
  var runs = extractHexRuns(s);

  var frames = [];

  /* 逐片段找帧；只在片段内部找 7E...7E，绝不跨片段拼接 */
  for (var ri = 0; ri < runs.length; ri++) {
    var run = runs[ri];

    /* 一个片段里可能有多帧（无分隔直接拼），逐个切 */
    var pos = 0;
    while (pos < run.length) {
      var start = run.indexOf("7E", pos);
      if (start < 0) break;

      var accepted = false;
      var scan = start + 2;
      while (scan <= run.length - 2) {
        var end = run.indexOf("7E", scan);
        if (end < 0) break;

        var candidate = run.slice(start, end + 2);
        if (isFrameSelfConsistent(candidate)) {
          frames.push({ hex:candidate, complete:true });
          pos = end + 2;
          accepted = true;
          break;
        }
        scan = end + 2;
      }
      if (accepted) continue;

      /* 片段内找不到自洽帧尾：把剩余部分当残缺帧，交给解析阶段报错。
       * 但要排除 "7E" 这种只有帧头没有内容的碎片（日志里常出现），
       * 否则会凭空多出一帧空帧。 */
      var rest = run.slice(start);
      if (rest.length > 2) {
        frames.push({ hex:rest, complete:false });
      }
      pos = run.length;
    }
  }

  if (frames.length === 0) {
    /* 没有任何 7E：把像报文的最长偶数片段按裸数据尝试 */
    var best = "";
    for (var k = 0; k < runs.length; k++) {
      var x = runs[k];
      if (x.length % 2 === 0 && x.length > best.length) best = x;
    }
    if (!best) throw new Error("没有找到可解析的十六进制内容");
    frames.push({ hex:best, complete:false, bare:true });
  }
  return frames;
}

/**
 * 把文本切成连续的十六进制片段。
 * 空白不中断片段（"7E 81 03" 要算一段），其它任何字符都断开。
 */
function extractHexRuns(s){
  var runs = [], cur = "";
  for (var i = 0; i < s.length; i++) {
    var ch = s.charAt(i);
    if ((ch >= "0" && ch <= "9") || (ch >= "A" && ch <= "F")) {
      cur += ch;
    } else if (ch === " " || ch === "\t" || ch === "\n" || ch === "\r" || ch === "\f" || ch === "\v") {
      continue;                      /* 空白：不中断也不计入 */
    } else {
      if (cur) { runs.push(cur); cur = ""; }
    }
  }
  if (cur) runs.push(cur);
  return runs;
}

function isFrameSelfConsistent(hexWithFlags){
  if (hexWithFlags.length % 2 !== 0) return false;
  if (hexWithFlags.substr(0, 2) !== "7E" || hexWithFlags.substr(-2) !== "7E") return false;

  var inner = hexWithFlags.slice(2, -2);
  if (inner.length % 2 !== 0) return false;
  if (inner.length < 24) return false;          /* 12 字节头 = 24 字符 */

  var bytes;
  try { bytes = unescapeBytes(hexStrToBytes(inner)); } catch (e) { return false; }
  if (bytes.length < 12) return false;

  var prop = (bytes[2] << 8) | bytes[3];
  var bodyLen = prop & 0x03FF;
  var subpkg  = (prop >> 13) & 0x01;
  var need = 12 + (subpkg ? 4 : 0) + bodyLen + 1;   /* 头 + 分包 + 体 + 校验 */

  if (need !== bytes.length) return false;
  /* 消息 ID 不能是 0x0000 / 0x7E7E 这类明显错位的值 */
  var msgId = (bytes[0] << 8) | bytes[1];
  if (msgId === 0x0000 || msgId === 0x7E7E) return false;
  return true;
}

/* ---------- 2. 单帧：hex → 字节 → 结构 ---------- */
function hexStrToBytes(h){
  if (h.length % 2) throw new Error("十六进制位数为奇数（" + h.length + "），可能粘贴不完整");
  var out = [];
  for (var i = 0; i < h.length; i += 2) out.push(parseInt(h.substr(i, 2), 16));
  return out;
}

/**
 * 解析一帧，返回结构化对象（JSON 友好）
 * 字段命名对齐现场调试习惯：[值]名称 的形式保留在 key 里
 */
function parseOneFrame(hex){
  var hasFlag = (hex.substr(0, 2) === "7E" && hex.substr(-2) === "7E");
  var bodyHex = hasFlag ? hex.slice(2, -2) : hex;

  var escBytes = hexStrToBytes(bodyHex);
  var bytes;
  try {
    bytes = hasFlag ? unescapeBytes(escBytes) : escBytes;
  } catch (e) {
    throw new Error("转义还原失败：" + e.message);
  }

  if (bytes.length < 12) {
    throw new Error("消息头不足 12 字节（实际 " + bytes.length + " 字节）");
  }

  var msgId  = (bytes[0] << 8) | bytes[1];
  var prop   = (bytes[2] << 8) | bytes[3];
  var bodyLen = prop & 0x03FF;
  var encrypt = (prop >> 10) & 0x07;
  var subpkg  = (prop >> 13) & 0x01;
  var version = (prop >> 14) & 0x01;   /* JTT2019 才有此位，2013 恒 0 */

  var phone = bytes.slice(4, 10);
  var seq   = (bytes[10] << 8) | bytes[11];

  var bodyStart = 12;
  var bodyEnd   = bodyStart + bodyLen;
  var csIdx     = bodyEnd;

  var obj = {};
  obj["[7E]开始"] = hasFlag ? 126 : null;

  obj["[" + normHex16(msgId) + "]消息Id"] = msgId;
  obj["消息名称"] = MSG_NAME[normHex16(msgId)] || "未收录";

  /* 消息体属性拆位 */
  var propObj = {};
  propObj["[" + pad16(prop) + "]消息体属性"] = prop;
  propObj["版本号"] = version ? "JTT2019" : "JTT2013";
  propObj["[bit15]保留"] = (prop >> 15) & 0x01;
  propObj["[bit14]保留"] = version;
  propObj["[bit13]是否分包"] = !!subpkg;
  var ENC = {0:"None", 1:"RSA", 2:"SM2"};
  propObj["[bit10~bit12]数据加密"] = ENC[encrypt] !== undefined ? ENC[encrypt] : ("未知(" + encrypt + ")");
  propObj["[bit0~bit9]消息体长度"] = bodyLen;
  obj["消息体属性对象"] = propObj;

  obj["[" + bcdDigits(phone) + "]终端手机号"] = bcdDigits(phone);
  obj["[" + normHex16(seq) + "]消息流水号"] = seq;

  /* 分包信息 */
  if (subpkg) {
    if (bytes.length >= bodyStart + 4) {
      var total = (bytes[bodyStart] << 8) | bytes[bodyStart + 1];
      var index = (bytes[bodyStart + 2] << 8) | bytes[bodyStart + 3];
      obj["分包"] = { "[总包数]": total, "[包序号]": index };
      bodyStart += 4;
      bodyEnd   = bodyStart + bodyLen - 4;
    } else {
      obj["分包"] = "声明分包但缺少封装项";
    }
  }

  /* 消息体 */
  var bodyBytes = null;
  if (bodyLen === 0) {
    obj["数据体对象"] = {};
  } else if (bodyEnd > bytes.length) {
    obj["数据体对象"] = "✕ 声明 " + bodyLen + " 字节，实际只剩 "
                     + Math.max(0, bytes.length - bodyStart) + " 字节，报文被截断";
  } else {
    bodyBytes = bytes.slice(bodyStart, bodyEnd);
    obj["数据体对象"] = parseBodyByMsgId(msgId, bodyBytes);
  }

  /* 校验码 */
  if (hasFlag) {
    var csCalc = 0;
    for (var i = 0; i < csIdx && i < bytes.length; i++) csCalc ^= bytes[i];
    if (csIdx < bytes.length) {
      var csReal = bytes[csIdx];
      obj["[" + normHex(csReal) + "]校验码"] = csReal;
      obj["校验码比对"] = (csCalc === csReal)
        ? "✓ 一致"
        : ("✕ 不一致（本地计算 " + normHex(csCalc) + "）");
    } else {
      obj["[" + "??" + "]校验码"] = "缺失";
      obj["校验码比对"] = "✕ 缺失";
    }
    obj["[7E]结束"] = 126;
  } else {
    obj["[7E]结束"] = null;
    obj["校验码比对"] = "未带帧头帧尾，跳过校验";
  }

  /* 附带元信息，供表格视图用 */
  obj.__meta = {
    hasFlag: hasFlag,
    msgId: msgId,
    bodyLen: bodyLen,
    seq: seq,
    bodyBytes: bodyBytes,
    extraBytes: (hasFlag && csIdx + 1 < bytes.length) ? bytes.length - csIdx - 1 : 0,
    csOk: (hasFlag && csIdx < bytes.length) ? (bytes[csIdx] === (function(){
      var c = 0; for (var k = 0; k < csIdx && k < bytes.length; k++) c ^= bytes[k]; return c;
    })()) : null
  };
  return obj;
}

/* 数字 → 大写十六进制，按位宽补零
 *   normHex  : 2 位（1 字节字段，如结果码）
 *   normHex16: 4 位（2 字节字段，如消息 ID、流水号）
 *   normHex32: 8 位（4 字节字段，如参数 ID）
 */
function normHex(v){ return padHex(v, 2); }
function normHex16(v){ return padHex(v, 4); }
function normHex32(v){ return padHex(v, 8); }
function padHex(v, width){
  var h = (v >>> 0).toString(16).toUpperCase();
  while (h.length < width) h = "0" + h;
  return h;
}
function pad16(v){ return ("0000000000000000" + v.toString(2)).slice(-16); }
function bcdDigits(arr){
  var s = "";
  for (var i = 0; i < arr.length; i++) {
    s += ((arr[i] >> 4) & 0xF).toString() + (arr[i] & 0xF).toString();
  }
  return s;
}

/* ============================================================
 * JT/T 808-2013 全量消息体反解
 *   每条消息一个函数，前缀 parse + 消息名，返回 JSON 友好对象。
 *   字段顺序一律按标准 8.x 节，注释里标出对应表号。
 * ============================================================ */
function u16At(a, o){ return (a[o] << 8) | a[o + 1]; }
function u8At(a, o){ return a[o]; }

/* 去掉尾部 0x00 后按 GBK/ASCII 转文本（定长字段专用） */
function trimNul(a){
  var n = a.length;
  while (n > 0 && a[n - 1] === 0) n--;
  return bytesToStr(a.slice(0, n));
}
/* BCD 字节 → 数字串（ICCID / 终端ID / 手机号） */
function bcdNum(a){
  var s = "";
  for (var i = 0; i < a.length; i++) {
    s += ((a[i] >> 4) & 0xF).toString() + (a[i] & 0xF).toString();
  }
  return s;
}
/* 位图 → 中文名称串，table[i] 对应 bit i */
function bitNames(v, table){
  var t = [];
  for (var i = 0; i < table.length; i++) {
    if (v & (1 << i)) t.push(table[i]);
  }
  return t.length ? t.join("、") : "无";
}
/* 长度不足时统一报错，调用方 return out 即可 */
function need(out, body, n, name){
  if (body.length < n) {
    out["✕"] = (name || "该消息") + "长度不足 " + n + " 字节（实际 " + body.length + "）";
    return false;
  }
  return true;
}

/* ---------- 0x0002 终端心跳 / 0x0003 终端注销（空消息体） ---------- */
function parseEmptyBody(body, name){
  var out = {};
  if (body.length === 0) out["说明"] = name + "：消息体为空，符合标准";
  else out["✕"] = name + "应为空消息体，实际带 " + body.length + " 字节：" + toHex(body, "");
  return out;
}

/* ---------- 0x0107 查询终端属性应答（表 22） ---------- */
function parseTerminalProperty(body){
  var out = {}, o = 0;
  if (!need(out, body, 45, "终端属性")) return out;

  var TT = { 0:"普通终端", 1:"车载终端", 2:"手持终端", 3:"专用终端" };
  var tt = u16At(body, o); o += 2;
  out["[" + normHex16(tt) + "]终端类型"] = TT[tt] || ("其他(" + tt + ")");

  out["[" + toHex(body.slice(o, o + 5), "") + "]制造商ID"] = trimNul(body.slice(o, o + 5)); o += 5;
  out["[" + toHex(body.slice(o, o + 20), "") + "]终端型号"] = trimNul(body.slice(o, o + 20)); o += 20;
  out["[" + toHex(body.slice(o, o + 7), "") + "]终端ID"] = bcdNum(body.slice(o, o + 7)); o += 7;
  out["[" + toHex(body.slice(o, o + 10), "") + "]SIM卡ICCID"] = bcdNum(body.slice(o, o + 10)); o += 10;

  if (o >= body.length) { out["✕尾部"] = "硬件版本号长度缺失"; return out; }
  var hwLen = body[o++];
  if (!need(out, body.slice(o), hwLen, "硬件版本号")) return out;
  out["[" + normHex(hwLen) + "]硬件版本号长度"] = hwLen;
  out["[硬件版本号]"] = trimNul(body.slice(o, o + hwLen)); o += hwLen;

  if (o >= body.length) { out["✕尾部"] = "固件版本号长度缺失"; return out; }
  var fwLen = body[o++];
  if (!need(out, body.slice(o), fwLen, "固件版本号")) return out;
  out["[" + normHex(fwLen) + "]固件版本号长度"] = fwLen;
  out["[固件版本号]"] = trimNul(body.slice(o, o + fwLen)); o += fwLen;

  if (o + 2 > body.length) { out["✕尾部"] = "GNSS/通信模块属性缺失"; return out; }
  var gnss = body[o++], comm = body[o++];
  out["[" + normHex(gnss) + "]GNSS模块属性"] =
    bitNames(gnss, ["GPS", "北斗", "GLONASS", "Galileo"]);
  out["[" + normHex(comm) + "]通信模块属性"] =
    bitNames(comm, ["GPRS", "CDMA", "TD-SCDMA", "WCDMA", "HSDPA", "LTE", "其他"]);

  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x0108 终端升级结果通知（表 25） ---------- */
function parseUpgradeResult(body){
  var out = {};
  if (!need(out, body, 2, "升级结果")) return out;
  var TY = { 0:"终端", 1:"道路运输证IC卡读卡器", 2:"卫星定位模块", 0x0C:"其他" };
  var RE = { 0:"成功", 1:"失败", 2:"取消" };
  out["[" + normHex(body[0]) + "]升级类型"] = TY[body[0]] || ("未收录(" + body[0] + ")");
  out["[" + normHex(body[1]) + "]升级结果"] = RE[body[1]] || ("未收录(" + body[1] + ")");
  if (body.length > 2) out["[附加字节]"] = toHex(body.slice(2), "");
  return out;
}

/* ---------- 0x0201 位置信息查询应答（表 26）：流水号 + 完整 0x0200 体 ---------- */
function parseLocAnswer(body){
  var out = {};
  if (!need(out, body, 3, "位置查询应答")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]应答流水号"] = u16At(body, 0);
  var loc = parseLocation0200(body.slice(2));
  for (var k in loc) out[k] = loc[k];
  return out;
}

/* ---------- 0x0300 事件报告（表 27）：事件 ID ---------- */
function parseEventReport(body){
  var out = {};
  if (!need(out, body, 1, "事件报告")) return out;
  out["[" + normHex(body[0]) + "]事件ID"] = body[0];
  if (body.length > 1) out["✕尾部"] = "还有 " + (body.length - 1) + " 字节未解析";
  return out;
}

/* ---------- 0x0301 提问应答（表 28） ---------- */
function parseQuestionAnswer(body){
  var out = {};
  if (!need(out, body, 3, "提问应答")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]应答流水号"] = u16At(body, 0);
  out["[" + normHex(body[2]) + "]答案内容"] = body[2];
  if (body.length > 3) out["✕尾部"] = "还有 " + (body.length - 3) + " 字节未解析";
  return out;
}

/* ---------- 0x0302 信息点播/取消（表 29） ---------- */
function parseInfoDemand(body){
  var out = {};
  if (!need(out, body, 2, "信息点播")) return out;
  var TY = { 1:"广告", 2:"天气", 3:"新闻" };
  out["[" + normHex(body[0]) + "]信息类型"] = TY[body[0]] || ("未收录(" + body[0] + ")");
  out["[" + normHex(body[1]) + "]点播/取消"] = body[1] === 1 ? "点播" : body[1] === 0 ? "取消" : ("未定义(" + body[1] + ")");
  return out;
}

/* ---------- 0x0704 定位数据批量上传（表 32）/ 0x0400 位置信息批量上传（2019）
 *   0704 = 个数(2) + 类型(1) + N×[长度(2) + 0x0200 体]
 *   0400 = 个数(2) +            N×[长度(2) + 0x0200 体]（无类型字节）
 *   每条递归走 parseLocation0200 ---------- */
function parseBatchLocation(body, hasType){
  var out = {};
  var head = hasType ? 3 : 2;
  if (!need(out, body, head, "批量定位")) return out;
  var cnt = u16At(body, 0), o = 2;
  out["[" + normHex16(cnt) + "]数据项个数"] = cnt;
  if (hasType) {
    var typ = body[o++];
    var TY = { 0:"正常批量上传", 1:"盲区补报" };
    out["[" + normHex(typ) + "]定位数据类型"] = TY[typ] || ("未定义(" + typ + ")");
  }

  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 2 > body.length) { out["✕第" + (i + 1) + "项"] = "长度字段越界"; break; }
    var len = u16At(body, o); o += 2;
    if (o + len > body.length) { out["✕第" + (i + 1) + "项"] = "数据长度 " + len + " 超出剩余字节"; break; }
    var item = parseLocation0200(body.slice(o, o + len));
    var flat = {};
    for (var k in item) flat[k] = item[k];
    list["第 " + (i + 1) + " 条（" + len + " 字节）"] = flat;
    o += len;
  }
  out["定位数据列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x0705 CAN 总线数据上传（表 33）：每项 12 字节 ---------- */
function parseCanData(body){
  var out = {};
  if (!need(out, body, 2, "CAN 数据")) return out;
  var cnt = u16At(body, 0), o = 2;
  out["[" + normHex16(cnt) + "]数据项个数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 12 > body.length) { out["✕第" + (i + 1) + "项"] = "剩余 " + (body.length - o) + " 字节不足 12"; break; }
    var id = u32At(body, o);
    var dat = body.slice(o + 4, o + 12);
    list["[" + normHex32(id) + "]"] = "数据 " + toHex(dat, "");
    o += 12;
  }
  out["CAN数据列表"] = list;
  if (o < body.length) out["[尾部]"] = toHex(body.slice(o), "");
  return out;
}

/* ---------- 0x0800 多媒体事件信息上传（表 34）：固定 8 字节 ---------- */
function parseMediaEvent(body){
  var out = {};
  if (!need(out, body, 8, "多媒体事件")) return out;
  out["[" + normHex32(u32At(body, 0)) + "]多媒体数据ID"] = u32At(body, 0);
  out["[" + normHex(body[4]) + "]多媒体类型"] = ({0:"图像",1:"音频",2:"视频"})[body[4]] || ("未收录(" + body[4] + ")");
  out["[" + normHex(body[5]) + "]多媒体格式编码"] =
    ({0:"JPEG",1:"TIF",2:"MP3",3:"WAV",4:"WMV"})[body[5]] || ("未收录(" + body[5] + ")");
  out["[" + normHex(body[6]) + "]事件项编码"] = body[6] === 0 ? "平台下发指令" : body[6] === 1 ? "定时动作" : ("未收录(" + body[6] + ")");
  out["[" + normHex(body[7]) + "]通道ID"] = body[7];
  if (body.length > 8) out["✕尾部"] = "还有 " + (body.length - 8) + " 字节未解析";
  return out;
}

/* ---------- 0x0801 多媒体数据上传（表 35）：头 8 + 位置 28 + 数据 ---------- */
function parseMediaData(body){
  var out = {};
  if (!need(out, body, 36, "多媒体上传")) return out;
  out["[" + normHex32(u32At(body, 0)) + "]多媒体数据ID"] = u32At(body, 0);
  out["[" + normHex(body[4]) + "]多媒体类型"] = ({0:"图像",1:"音频",2:"视频"})[body[4]] || ("未收录(" + body[4] + ")");
  out["[" + normHex(body[5]) + "]多媒体格式编码"] =
    ({0:"JPEG",1:"TIF",2:"MP3",3:"WAV",4:"WMV"})[body[5]] || ("未收录(" + body[5] + ")");
  out["[" + normHex(body[6]) + "]事件项编码"] = body[6];
  out["[" + normHex(body[7]) + "]通道ID"] = body[7];
  var loc = parseLocation0200(body.slice(8, 36));
  var locFlat = {};
  for (var k in loc) locFlat[k] = loc[k];
  out["位置信息汇报"] = locFlat;
  var data = body.slice(36);
  out["[多媒体数据]"] = data.length ? ("共 " + data.length + " 字节，前 32 字节 " + toHex(data.slice(0, 32), "")) : "无数据";
  return out;
}

/* ---------- 0x0802 多媒体数据上传应答（表 36） ---------- */
function parseMediaDataAck(body){
  var out = {};
  if (!need(out, body, 5, "多媒体上传应答")) return out;
  out["[" + normHex32(u32At(body, 0)) + "]多媒体数据ID"] = u32At(body, 0);
  var n = body[4], o = 5;
  out["[" + normHex(n) + "]重新上传包个数"] = n;
  var list = {};
  for (var i = 0; i < n; i++) {
    if (o + 4 > body.length) { out["✕第" + (i + 1) + "包"] = "越界"; break; }
    list["包 " + (i + 1)] = u32At(body, o);
    o += 4;
  }
  if (n) out["需重传包序号"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x0805 摄像头立即拍摄命令应答（表 39） ---------- */
function parseMediaShotAck(body){
  var out = {};
  if (!need(out, body, 5, "拍摄命令应答")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]应答流水号"] = u16At(body, 0);
  out["[" + normHex(body[2]) + "]结果"] = body[2] === 0 ? "成功" : "失败";
  var n = u16At(body, 3), o = 5;
  out["[" + normHex16(n) + "]多媒体数据ID个数"] = n;
  var list = [];
  for (var i = 0; i < n; i++) {
    if (o + 4 > body.length) { out["✕第" + (i + 1) + "个ID"] = "越界"; break; }
    list.push(u32At(body, o));
    o += 4;
  }
  if (n) out["多媒体数据ID列表"] = list.join(", ");
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x0900 数据上行透传 / 0x8900 数据下行透传（表 40 / 表 51） ---------- */
function parsePassThrough(body, up){
  var out = {};
  if (!need(out, body, 1, "透传")) return out;
  var TY = { 0:"无障碍", 1:"有障碍/危险", 2:"有故障", 3:"双向", 4:"紧急", 0xF0:"自定义" };
  out["[" + normHex(body[0]) + "]透传消息类型"] = TY[body[0]] || ("未收录(" + body[0] + ")");
  var d = body.slice(1);
  out["[透传内容 " + d.length + " 字节]"] =
    d.length ? (toHex(d.slice(0, 64), "") + (d.length > 64 ? " …" : "")) : "无";
  return out;
}

/* ---------- 0x0901 数据压缩上报（表 41） ---------- */
function parseCompressed(body){
  var out = {};
  if (!need(out, body, 1, "压缩上报")) return out;
  out["[" + normHex(body[0]) + "]压缩算法"] = body[0] === 0 ? "GZIP" : ("未收录(" + body[0] + ")");
  out["[压缩数据]"] = "共 " + (body.length - 1) + " 字节，" + toHex(body.slice(1, 33), "") + (body.length - 1 > 32 ? " …" : "");
  return out;
}

/* ---------- 0x0A00 / 0x8A00 RSA 公钥（表 42 / 表 52）：e长 + e + n长 + n ---------- */
function parseRsaKey(body, who){
  var out = {}, o = 0;
  if (!need(out, body, 4, who + " RSA 公钥")) return out;
  var eLen = u32At(body, o); o += 4;
  if (o + eLen > body.length) { out["✕"] = "e 长度 " + eLen + " 超出剩余字节"; return out; }
  out["[" + normHex32(eLen) + "]e 长度"] = eLen;
  out["[e]"] = toHex(body.slice(o, o + eLen), ""); o += eLen;
  if (o + 4 > body.length) { out["✕尾部"] = "n 长度字段缺失"; return out; }
  var nLen = u32At(body, o); o += 4;
  out["[" + normHex32(nLen) + "]n 长度"] = nLen;
  out["[n]"] = (o + nLen <= body.length)
    ? toHex(body.slice(o, o + nLen), "")
    : ("✕ 声明 " + nLen + " 字节，实际只剩 " + (body.length - o));
  return out;
}

/* ---------- 0x8003 补传分包请求（表 44） ---------- */
function parseRetransmit(body){
  var out = {};
  if (!need(out, body, 3, "补传分包请求")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]原始消息流水号"] = u16At(body, 0);
  var n = body[2], o = 3;
  out["[" + normHex(n) + "]重传包总数"] = n;
  var list = [];
  for (var i = 0; i < n; i++) {
    if (o + 2 > body.length) { out["✕第" + (i + 1) + "包"] = "越界"; break; }
    list.push(u16At(body, o));
    o += 2;
  }
  if (n) out["重传包ID列表"] = list.join(", ");
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8104 查询终端参数 / 0x8107 查询终端属性 / 0x8201 位置信息查询（空体） ---------- */
function parseEmptyCmd(body, name){
  var out = {};
  if (body.length === 0) out["说明"] = name + "：消息体为空，符合标准（仅一帧指令）";
  else out["✕"] = name + "应为空消息体，实际带 " + body.length + " 字节：" + toHex(body, "");
  return out;
}

/* ---------- 0x8108 下发终端升级包（表 47） ---------- */
function parseUpgradePackage(body){
  var out = {}, o = 0;
  if (!need(out, body, 7, "升级包")) return out;
  var TY = { 0:"终端", 1:"道路运输证IC卡读卡器", 2:"卫星定位模块", 0x0C:"其他" };
  out["[" + normHex(body[o]) + "]升级类型"] = TY[body[o]] || ("未收录(" + body[o] + ")"); o++;
  out["[" + toHex(body.slice(o, o + 5), "") + "]制造商ID"] = trimNul(body.slice(o, o + 5)); o += 5;
  var vLen = body[o++];
  if (!need(out, body.slice(o), vLen, "版本号")) return out;
  out["[" + normHex(vLen) + "]版本号长度"] = vLen;
  out["[版本号]"] = trimNul(body.slice(o, o + vLen)); o += vLen;
  if (!need(out, body.slice(o), 4, "升级包长度")) return out;
  var pLen = u32At(body, o); o += 4;
  out["[" + normHex32(pLen) + "]升级包长度"] = pLen;
  var rest = body.length - o;
  out["[升级包数据]"] = "声明 " + pLen + " 字节，实际 " + rest + " 字节"
    + (pLen === rest ? "（一致）" : "（✕ 不一致）");
  return out;
}

/* ---------- 0x8202 临时位置跟踪控制（表 49） ---------- */
function parseTrackCtrl(body){
  var out = {};
  if (!need(out, body, 6, "临时位置跟踪")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]时间间隔(秒)"] = u16At(body, 0);
  out["[" + normHex32(u32At(body, 2)) + "]位置跟踪有效期(秒)"] = u32At(body, 2);
  if (body.length > 6) out["✕尾部"] = "还有 " + (body.length - 6) + " 字节未解析";
  return out;
}

/* ---------- 0x8203 人工确认报警消息（表 50） ---------- */
function parseManualAlarmAck(body){
  var out = {};
  if (!need(out, body, 6, "人工确认报警")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]报警消息流水号"] = u16At(body, 0);
  out["[" + normHex32(u32At(body, 2)) + "]人工确认报警类型"] = u32At(body, 2);
  return out;
}

/* ---------- 0x8300 文本信息下发（表 53） ---------- */
function parseTextDown(body){
  var out = {};
  if (!need(out, body, 1, "文本信息")) return out;
  var f = body[0];
  out["[" + normHex(f) + "]标志"] = bitNames(f,
    ["紧急", "终端显示器显示", "终端TTS播读", "广告屏显示"])
    + "；来源=" + ((f & 0x30) === 0 ? "中心" : "服务");
  out["[文本信息]"] = bytesToStr(body.slice(1));
  return out;
}

/* ---------- 0x8301 事件设置（表 54） ---------- */
function parseEventSet(body){
  var out = {};
  if (!need(out, body, 2, "事件设置")) return out;
  var ST = { 0:"删除所有事件", 1:"更新", 2:"追加", 3:"修改" };
  out["[" + normHex(body[0]) + "]设置类型"] = ST[body[0]] || ("未收录(" + body[0] + ")");
  var cnt = body[1], o = 2;
  out["[" + normHex(cnt) + "]事件总数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 2 > body.length) { out["✕第" + (i + 1) + "项"] = "越界"; break; }
    var eid = body[o], len = body[o + 1];
    o += 2;
    if (o + len > body.length) { out["✕第" + (i + 1) + "项"] = "内容长度越界"; break; }
    list["事件 " + eid] = bytesToStr(body.slice(o, o + len));
    o += len;
  }
  out["事件列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8302 提问下发（表 55） ---------- */
function parseQuestionDown(body){
  var out = {}, o = 0;
  if (!need(out, body, 2, "提问下发")) return out;
  var f = body[o++];
  out["[" + normHex(f) + "]标志"] = bitNames(f, ["紧急", "", "终端TTS播读"]);
  var qLen = body[o++];
  if (!need(out, body.slice(o), qLen, "问题内容")) return out;
  out["[" + normHex(qLen) + "]问题内容长度"] = qLen;
  out["[问题内容]"] = bytesToStr(body.slice(o, o + qLen)); o += qLen;

  var list = {};
  while (o + 2 <= body.length) {
    var aid = body[o], cLen = body[o + 1];
    o += 2;
    if (o + cLen > body.length) { out["✕答案"] = "内容长度越界"; break; }
    list["答案 " + aid] = bytesToStr(body.slice(o, o + cLen));
    o += cLen;
  }
  out["候选答案"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8303 信息服务（表 56） ---------- */
function parseInfoService(body){
  var out = {};
  if (!need(out, body, 2, "信息服务")) return out;
  out["[" + normHex(body[0]) + "]信息类型"] = body[0] === 0 ? "新闻" : body[0] === 1 ? "天气" : body[0] === 2 ? "节目单" : ("未收录(" + body[0] + ")");
  var cnt = body[1], o = 2;
  out["[" + normHex(cnt) + "]信息项总数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 3 > body.length) { out["✕第" + (i + 1) + "项"] = "越界"; break; }
    var ty = body[o], len = u16At(body, o + 1);
    o += 3;
    if (o + len > body.length) { out["✕第" + (i + 1) + "项"] = "内容长度越界"; break; }
    list["第 " + (i + 1) + " 项（类型 " + ty + "）"] = bytesToStr(body.slice(o, o + len));
    o += len;
  }
  out["信息项列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8304 信息点播菜单设置（表 57） ---------- */
function parseInfoMenu(body){
  var out = {};
  if (!need(out, body, 2, "点播菜单")) return out;
  var ST = { 0:"删除所有菜项", 1:"更新菜单", 2:"追加菜单", 3:"修改菜单" };
  out["[" + normHex(body[0]) + "]设置类型"] = ST[body[0]] || ("未收录(" + body[0] + ")");
  var cnt = body[1], o = 2;
  out["[" + normHex(cnt) + "]信息项总数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 3 > body.length) { out["✕第" + (i + 1) + "项"] = "越界"; break; }
    var ty = body[o], len = u16At(body, o + 1);
    o += 3;
    if (o + len > body.length) { out["✕第" + (i + 1) + "项"] = "名称长度越界"; break; }
    list["信息类型 " + ty] = bytesToStr(body.slice(o, o + len));
    o += len;
  }
  out["菜单列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8400 电话回拨（表 58） ---------- */
function parsePhoneCall(body){
  var out = {};
  if (!need(out, body, 1, "电话回拨")) return out;
  out["[" + normHex(body[0]) + "]标志"] = body[0] === 0 ? "普通通话" : body[0] === 1 ? "监听" : ("未收录(" + body[0] + ")");
  out["[电话号码]"] = bytesToStr(body.slice(1));
  return out;
}

/* ---------- 0x8401 设置电话本（表 59） ---------- */
function parsePhoneBook(body){
  var out = {};
  if (!need(out, body, 2, "设置电话本")) return out;
  var ST = { 0:"删除所有联系人", 1:"更新电话本", 2:"追加电话本", 3:"修改电话本" };
  out["[" + normHex(body[0]) + "]设置类型"] = ST[body[0]] || ("未收录(" + body[0] + ")");
  var cnt = body[1], o = 2;
  out["[" + normHex(cnt) + "]联系人总数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 2 > body.length) { out["✕第" + (i + 1) + "项"] = "越界"; break; }
    var flag = body[o], nLen = body[o + 1];
    o += 2;
    if (o + nLen > body.length) { out["✕第" + (i + 1) + "项"] = "号码长度越界"; break; }
    var phone = bytesToStr(body.slice(o, o + nLen));
    o += nLen;
    if (o >= body.length) { list["第 " + (i + 1) + " 项"] = phone + "（缺联系人名）"; break; }
    var cLen = body[o++];
    if (o + cLen > body.length) { out["✕第" + (i + 1) + "项"] = "联系人长度越界"; break; }
    var name = bytesToStr(body.slice(o, o + cLen));
    o += cLen;
    list["第 " + (i + 1) + " 项"] = phone + " / " + name + " / 标志 " + flag;
  }
  out["联系人列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8500 车辆控制（表 60） ---------- */
function parseVehicleCtrl(body){
  var out = {};
  if (!need(out, body, 1, "车辆控制")) return out;
  out["[" + normHex(body[0]) + "]控制标志"] = bitNames(body[0],
    ["车门开", "鸣笛", "降窗", "升窗", "开空调", "关空调", "断油断电"]);
  if (body.length > 1) out["[附加字节]"] = toHex(body.slice(1), "");
  return out;
}

/* ---------- 0x8606 设置路线（表 63） ---------- */
function parseRouteSet(body){
  var out = {}, o = 0;
  if (!need(out, body, 20, "设置路线")) return out;
  out["[" + normHex32(u32At(body, o)) + "]路线ID"] = u32At(body, o); o += 4;
  var prop = u16At(body, o); o += 2;
  out["[" + normHex16(prop) + "]路线属性"] =
    bitNames(prop, ["", "", "", "", "", ""]) === "无"
      ? "无扩展位（0x" + normHex16(prop) + "）"
      : bitNames(prop, ["", "", "", "", "", ""]);
  out["[起始时间]"] = bcdTimeStr(body.slice(o, o + 6)); o += 6;
  out["[结束时间]"] = bcdTimeStr(body.slice(o, o + 6)); o += 6;
  var cnt = u16At(body, o); o += 2;
  out["[" + normHex16(cnt) + "]拐点数"] = cnt;

  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 25 > body.length) { out["✕第" + (i + 1) + "个拐点"] = "剩余 " + (body.length - o) + " 字节不足 25"; break; }
    var it = {};
    it["拐点ID"] = u32At(body, o);
    it["路段ID"] = u32At(body, o + 4);
    it["纬度"] = degStr(u32At(body, o + 8));
    it["经度"] = degStr(u32At(body, o + 12));
    it["路段宽度"] = body[o + 16] + " 米";
    it["路段属性"] = "0x" + normHex(body[o + 17]);
    it["行驶过长阈值"] = u16At(body, o + 18) + " 秒";
    it["行驶不足阈值"] = u16At(body, o + 20) + " 秒";
    it["最高速度"] = u16At(body, o + 22) + " km/h";
    it["超速持续时间"] = body[o + 24] + " 秒";
    o += 25;
    if (o + 2 <= body.length) { it["路段行驶时间"] = u16At(body, o) + " 秒"; o += 2; }
    list["第 " + (i + 1) + " 个拐点"] = it;
  }
  out["拐点列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8607 删除路线（表 64） ---------- */
function parseRouteDel(body){
  var out = {};
  if (!need(out, body, 1, "删除路线")) return out;
  var n = body[0], o = 1;
  out["[" + normHex(n) + "]路线数"] = n === 0 ? "0（删除全部路线）" : n;
  var list = [];
  for (var i = 0; i < n; i++) {
    if (o + 4 > body.length) { out["✕第" + (i + 1) + "条"] = "越界"; break; }
    list.push(u32At(body, o));
    o += 4;
  }
  if (n) out["路线ID列表"] = list.join(", ");
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8700 行驶记录参数下传 / 0x8701 行驶记录数据上传（表 65 / 表 66） ---------- */
function parseDriveParam(body, isUp){
  var out = {}, o = 0;
  if (isUp) {
    if (!need(out, body, 3, "行驶记录数据")) return out;
    out["[" + normHex16(u16At(body, 0)) + "]应答流水号"] = u16At(body, 0); o = 2;
  }
  if (o >= body.length) { out["✕"] = "命令字缺失"; return out; }
  out["[" + normHex(body[o]) + "]命令字"] = body[o];
  var d = body.slice(o + 1);
  out["[数据块]"] = d.length ? ("共 " + d.length + " 字节：" + toHex(d.slice(0, 48), "") + (d.length > 48 ? " …" : "")) : "无";
  return out;
}

/* ---------- 0x8800 存储多媒体数据检索（表 67） ---------- */
function parseMediaSearch(body){
  var out = {};
  if (!need(out, body, 15, "多媒体检索")) return out;
  out["[" + normHex(body[0]) + "]多媒体类型"] = ({0:"图像",1:"音频",2:"视频"})[body[0]] || ("未收录(" + body[0] + ")");
  out["[" + normHex(body[1]) + "]通道ID"] = body[1];
  out["[" + normHex(body[2]) + "]事件项编码"] = body[2];
  out["[起始时间]"] = bcdTimeStr(body.slice(3, 9));
  out["[结束时间]"] = bcdTimeStr(body.slice(9, 15));
  return out;
}

/* ---------- 0x8801 摄像头立即拍摄命令（表 68） ---------- */
function parseMediaShot(body){
  var out = {};
  if (!need(out, body, 12, "立即拍摄命令")) return out;
  out["[" + normHex(body[0]) + "]通道ID"] = body[0];
  var cmd = u16At(body, 1);
  out["[" + normHex16(cmd) + "]拍摄命令"] = cmd === 0xFFFF ? "停止录像" : (cmd + "（张/秒）");
  out["[" + normHex16(u16At(body, 3)) + "]拍照间隔/录像时间"] = u16At(body, 3) + " 秒";
  out["[" + normHex(body[5]) + "]保存标志"] = body[5] === 0 ? "实时上传" : "保存";
  out["[" + normHex(body[6]) + "]分辨率"] = ({1:"320×240",2:"640×480",3:"800×600",4:"1024×768",8:"176×144",0x1C:"1280×960",0x20:"1600×1200",0x22:"2048×1536"})[body[6]] || ("未收录(" + body[6] + ")");
  out["[" + normHex(body[7]) + "]图像/视频质量"] = "1~10 档，当前 " + body[7];
  out["[" + normHex(body[8]) + "]亮度"] = body[8];
  out["[" + normHex(body[9]) + "]对比度"] = body[9];
  out["[" + normHex(body[10]) + "]饱和度"] = body[10];
  out["[" + normHex(body[11]) + "]色度"] = body[11];
  return out;
}

/* ---------- 0x8802 存储多媒体数据上传命令（表 69） ---------- */
function parseMediaUploadCmd(body){
  var out = {};
  if (!need(out, body, 16, "多媒体上传命令")) return out;
  out["[" + normHex(body[0]) + "]多媒体类型"] = ({0:"图像",1:"音频",2:"视频"})[body[0]] || ("未收录(" + body[0] + ")");
  out["[" + normHex(body[1]) + "]通道ID"] = body[1];
  out["[" + normHex(body[2]) + "]事件项编码"] = body[2];
  out["[起始时间]"] = bcdTimeStr(body.slice(3, 9));
  out["[结束时间]"] = bcdTimeStr(body.slice(9, 15));
  out["[" + normHex(body[15]) + "]删除标志"] = body[15] === 0 ? "保留" : "删除";
  return out;
}

/* ---------- 0x8803 存储多媒体数据检索应答（表 70）：每项 15 字节 ---------- */
function parseMediaSearchAck(body){
  var out = {};
  if (!need(out, body, 4, "检索应答")) return out;
  out["[" + normHex16(u16At(body, 0)) + "]应答流水号"] = u16At(body, 0);
  var cnt = u16At(body, 2), o = 4;
  out["[" + normHex16(cnt) + "]多媒体数据总项数"] = cnt;
  var list = {};
  for (var i = 0; i < cnt; i++) {
    if (o + 15 > body.length) { out["✕第" + (i + 1) + "项"] = "剩余 " + (body.length - o) + " 字节不足 15"; break; }
    var it = {};
    it["多媒体数据ID"] = u32At(body, o);
    it["多媒体类型"] = ({0:"图像",1:"音频",2:"视频"})[body[o + 4]] || ("未收录(" + body[o + 4] + ")");
    it["通道ID"] = body[o + 5];
    it["事件项编码"] = body[o + 6];
    it["经度"] = degStr(u32At(body, o + 7));
    it["纬度"] = degStr(u32At(body, o + 11));
    list["第 " + (i + 1) + " 项"] = it;
    o += 15;
  }
  out["多媒体数据列表"] = list;
  if (o < body.length) out["✕尾部"] = "还有 " + (body.length - o) + " 字节未解析";
  return out;
}

/* ---------- 0x8804 录音开始命令（表 71） ---------- */
function parseRecordStart(body){
  var out = {};
  if (!need(out, body, 5, "录音命令")) return out;
  out["[" + normHex(body[0]) + "]录音命令"] = body[0] === 0 ? "停止录音" : "开始录音";
  out["[" + normHex16(u16At(body, 1)) + "]录音时间(秒)"] = u16At(body, 1);
  out["[" + normHex(body[3]) + "]保存标志"] = body[3] === 0 ? "实时上传" : "保存";
  out["[" + normHex(body[4]) + "]音频采样率"] =
    body[4] === 0 ? "8kHz" : body[4] === 1 ? "11kHz" : body[4] === 2 ? "23kHz" : body[4] === 3 ? "32kHz" : ("未收录(" + body[4] + ")");
  return out;
}

/* ---------- 0x8805 单条存储多媒体数据检索上传命令（表 72） ---------- */
function parseMediaSingleUpload(body){
  var out = {};
  if (!need(out, body, 5, "单条上传命令")) return out;
  out["[" + normHex32(u32At(body, 0)) + "]多媒体数据ID"] = u32At(body, 0);
  out["[" + normHex(body[4]) + "]删除标志"] = body[4] === 0 ? "保留" : "删除";
  return out;
}

/* ---------- 3. 按消息 ID 解析消息体，返回 JSON 友好对象 ---------- */
function parseBodyByMsgId(msgId, body){
  var out = {};

  if (msgId === 0x0200) {                   /* 位置信息汇报 */
    return parseLocation0200(body);
  }

  if (msgId === 0x0001) {                   /* 终端通用应答 */
    if (body.length < 5) { out["✕"] = "长度不足 5 字节（实际 " + body.length + "）"; return out; }
    out["终端通用应答"] = toHex(body, "");
    out["[" + normHex16((body[0] << 8) | body[1]) + "]应答流水号"] = (body[0] << 8) | body[1];
    var ackId = (body[2] << 8) | body[3];
    out["[" + normHex16(ackId) + "]应答消息Id"] = ackId;
    out["应答消息名称"] = MSG_NAME[normHex16(ackId)] || "未收录";
    out["[" + normHex(body[4]) + "]结果"] = ACK_RESULT_EN[body[4]] || ("未定义(" + body[4] + ")");
    var h1 = ackFailHint(ackId, body[4]);
    if (h1) out["✕提示"] = h1;
    return out;
  }

  if (msgId === 0x8001) {                   /* 平台通用应答 */
    if (body.length < 5) { out["✕"] = "长度不足 5 字节"; return out; }
    out["[" + normHex16((body[0] << 8) | body[1]) + "]应答流水号"] = (body[0] << 8) | body[1];
    var aid = (body[2] << 8) | body[3];
    out["[" + normHex16(aid) + "]应答消息Id"] = aid;
    out["应答消息名称"] = MSG_NAME[normHex16(aid)] || "未收录";
    out["[" + normHex(body[4]) + "]结果"] = ACK_RESULT_EN[body[4]] || ("未定义(" + body[4] + ")");
    var h2 = ackFailHint(aid, body[4]);
    if (h2) out["✕提示"] = h2;
    return out;
  }

  if (msgId === 0x8103) {                   /* 设置终端参数：无应答流水号 */
    return parseParamBodyObj(body, true, 0);
  }

  if (msgId === 0x0104) {                   /* 查询终端参数应答：先 2 字节应答流水号 */
    if (body.length < 3) { out["✕"] = "长度不足 3 字节（实际 " + body.length + "）"; return out; }
    var ackSeq = (body[0] << 8) | body[1];
    out["[" + normHex16(ackSeq) + "]应答流水号"] = ackSeq;
    var rest = parseParamBodyObj(body, false, 2);
    for (var k in rest) out[k] = rest[k];
    return out;
  }

  if (msgId === 0x8106) {                   /* 查询指定参数 */
    if (body.length < 1) { out["✕"] = "参数总数缺失"; return out; }
    var cnt = body[0];
    out["[" + normHex(cnt) + "]参数总数"] = cnt;
    var off = 1, list = {};
    for (var i = 0; i < cnt && off + 4 <= body.length; i++, off += 4) {
      var pid = ((body[off] << 24) | (body[off + 1] << 16) | (body[off + 2] << 8) | body[off + 3]) >>> 0;
      list["[" + normHex32(pid) + "]"] = paramName(pid) || "未收录";
    }
    out["参数Id列表"] = list;
    if (off < body.length) out["✕尾部"] = "还有 " + (body.length - off) + " 字节未解析";
    return out;
  }

  if (msgId === 0x8100) {                   /* 终端注册应答 */
    if (body.length < 3) { out["✕"] = "长度不足 3 字节"; return out; }
    out["[" + normHex16((body[0] << 8) | body[1]) + "]应答流水号"] = (body[0] << 8) | body[1];
    var REG = ["成功","车辆已被注册","数据库中无该车辆","终端已被注册","数据库中无该终端"];
    out["[" + normHex(body[2]) + "]结果"] = REG[body[2]] || ("未定义(" + body[2] + ")");
    if (body.length > 3) out["鉴权码"] = bytesToStr(body.slice(3));
    return out;
  }

  if (msgId === 0x8105) {                   /* 终端控制 */
    if (body.length < 1) { out["✕"] = "命令字缺失"; return out; }
    var CN = {1:"无线升级(MCU)",2:"连接指定服务器",3:"终端关机",4:"终端复位",
              5:"恢复出厂设置",6:"关闭数据通信",7:"关闭所有无线通信",0xF0:"Modem 无线升级"};
    out["[" + normHex(body[0]) + "]命令字"] = (CN[body[0]] || "未收录") ;
    if (body.length > 1) out["[" + normHex(body[0]) + "]命令参数"] = bytesToStr(body.slice(1));
    return out;
  }

  if (msgId === 0x8600) {                   /* 设置圆形区域 */
    return parseFenceSetObj(body, true);
  }

  if (msgId === 0x8602) {                   /* 设置矩形区域 */
    return parseFenceSetObj(body, false);
  }

  if (msgId === 0x8604) {                   /* 设置多边形区域：无操作/数量前缀 */
    return parseFencePolyObj(body);
  }

  if (msgId === 0x8601 || msgId === 0x8603 || msgId === 0x8605) {   /* 删除区域 */
    return parseFenceDelObj(body);
  }

  if (msgId === 0x0100) {                   /* 终端注册 */
    if (body.length < 37) { out["✕"] = "长度不足 37 字节"; return out; }
    var o = 0;
    out["[" + normHex((body[o] << 8) | body[o+1]) + "]省域ID"] = (body[o] << 8) | body[o+1]; o += 2;
    out["[" + normHex((body[o] << 8) | body[o+1]) + "]市县ID"] = (body[o] << 8) | body[o+1]; o += 2;
    out["[" + toHex(body.slice(o, o+5), "") + "]制造商ID"] = bytesToStr(body.slice(o, o+5)); o += 5;
    out["[" + toHex(body.slice(o, o+20), "") + "]终端型号"] = bytesToStr(body.slice(o, o+20)); o += 20;
    out["[" + toHex(body.slice(o, o+7), "") + "]终端ID"] = bytesToStr(body.slice(o, o+7)); o += 7;
    out["[" + normHex(body[o]) + "]车牌颜色"] = body[o]; o += 1;
    out["[车牌]"] = bytesToStr(body.slice(o));
    return out;
  }

  if (msgId === 0x0102) {                   /* 终端鉴权 */
    out["[鉴权码]"] = bytesToStr(body);
    out["[IMEI]"] = body.length > 15 ? bytesToStr(body.slice(-15)) : "";
    return out;
  }

  /* ======== 以下为 JT/T 808-2013 消息表全量分支 ======== */
  if (msgId === 0x0002) return parseEmptyBody(body, "终端心跳");
  if (msgId === 0x0003) return parseEmptyBody(body, "终端注销");
  if (msgId === 0x0004) return parseEmptyCmd(body, "终端参数查询请求");

  if (msgId === 0x0107) return parseTerminalProperty(body);
  if (msgId === 0x0108) return parseUpgradeResult(body);

  if (msgId === 0x0201) return parseLocAnswer(body);

  if (msgId === 0x0300) return parseEventReport(body);
  if (msgId === 0x0301) return parseQuestionAnswer(body);
  if (msgId === 0x0302) return parseInfoDemand(body);

  if (msgId === 0x0400) return parseBatchLocation(body, false);
  if (msgId === 0x0704) return parseBatchLocation(body, true);
  if (msgId === 0x0705) return parseCanData(body);

  if (msgId === 0x0800) return parseMediaEvent(body);
  if (msgId === 0x0801) return parseMediaData(body);
  if (msgId === 0x0802) return parseMediaDataAck(body);
  if (msgId === 0x0805) return parseMediaShotAck(body);

  if (msgId === 0x0900) return parsePassThrough(body, true);
  if (msgId === 0x0901) return parseCompressed(body);
  if (msgId === 0x0A00) return parseRsaKey(body, "终端");

  if (msgId === 0x8003) return parseRetransmit(body);

  if (msgId === 0x8104) return parseEmptyCmd(body, "查询终端参数");
  if (msgId === 0x8107) return parseEmptyCmd(body, "查询终端属性");
  if (msgId === 0x8108) return parseUpgradePackage(body);

  if (msgId === 0x8201) return parseEmptyCmd(body, "位置信息查询");
  if (msgId === 0x8202) return parseTrackCtrl(body);
  if (msgId === 0x8203) return parseManualAlarmAck(body);

  if (msgId === 0x8300) return parseTextDown(body);
  if (msgId === 0x8301) return parseEventSet(body);
  if (msgId === 0x8302) return parseQuestionDown(body);
  if (msgId === 0x8303) return parseInfoService(body);
  if (msgId === 0x8304) return parseInfoMenu(body);

  if (msgId === 0x8400) return parsePhoneCall(body);
  if (msgId === 0x8401) return parsePhoneBook(body);
  if (msgId === 0x8500) return parseVehicleCtrl(body);

  if (msgId === 0x8606) return parseRouteSet(body);
  if (msgId === 0x8607) return parseRouteDel(body);

  if (msgId === 0x8700) return parseDriveParam(body, false);
  if (msgId === 0x8701) return parseDriveParam(body, true);

  if (msgId === 0x8800) return parseMediaSearch(body);
  if (msgId === 0x8801) return parseMediaShot(body);
  if (msgId === 0x8802) return parseMediaUploadCmd(body);
  if (msgId === 0x8803) return parseMediaSearchAck(body);
  if (msgId === 0x8804) return parseRecordStart(body);
  if (msgId === 0x8805) return parseMediaSingleUpload(body);

  if (msgId === 0x8900) return parsePassThrough(body, false);
  if (msgId === 0x8A00) return parseRsaKey(body, "平台");

  out["[原始字节]"] = toHex(body, "");
  out["说明"] = "该消息类型未实现详细解析";
  return out;
}

/* ============================================================
 * 电子围栏反解辅助
 * ============================================================ */
function u32At(a, o){
  return ((a[o] << 24) | (a[o + 1] << 16) | (a[o + 2] << 8) | a[o + 3]) >>> 0;
}
function s32At(a, o){
  return (a[o] << 24) | (a[o + 1] << 16) | (a[o + 2] << 8) | a[o + 3];
}
function degStr(v){ return (v / 1000000).toFixed(6); }
/* ============================================================
 * 0x0200 位置信息汇报反解
 *   基础 28 字节：报警标志4 + 状态4 + 纬度4 + 经度4 + 高程2 + 速度2 + 方向2 + 时间6
 *   其后为 TLV 附加项：ID1 + 长度1 + 内容
 *   字段与单位对齐固件 gsw_gps.c：
 *     gps_808_fill_location_base()  / gps_808_fake_get_status()
 *     gps_808_fake_fill_extra()     / gps_808_fill_geo_fence_alarm_extra()
 * ============================================================ */
var LOC_ALARM_NAMES = [
  [0, "紧急报警"], [1, "超速报警"], [2, "疲劳驾驶"], [3, "危险预警"],
  [4, "GNSS 模块故障"], [5, "GNSS 天线未接或被剪断"], [6, "GNSS 天线短路"],
  [7, "终端主电源欠压"], [8, "终端主电源掉电"], [9, "终端 LCD 或显示器故障"],
  [10, "TTS 模块故障"], [11, "摄像头故障"], [12, "道路运输证 IC 卡模块故障"],
  [13, "超速预警"], [14, "疲劳驾驶预警"],
  [18, "当天累计驾驶超时"], [19, "超时停车"],
  [20, "进出区域"], [21, "进出路线"], [22, "路段行驶时间不足/过长"],
  [23, "路线偏离"], [24, "车辆 VSS 故障"], [25, "车辆油量异常"],
  [26, "车辆被盗"], [27, "车辆非法点火"], [28, "车辆非法位移"],
  [29, "碰撞预警"], [30, "侧翻预警"]
];

/* 只列「置位 = 该含义」的位；bit0~bit3 单独成行，不在此表 */
var LOC_STATUS_SET = [
  [4, "运营状态"], [5, "经纬度加密"], [8, "处于驾驶"],
  [9, "油路正常"], [10, "电路正常"], [11, "车门加锁"],
  [12, "前门开"], [13, "中门开"], [14, "后门开"], [15, "驾驶席门开"],
  [17, "北斗定位"], [18, "有视频信号"]
];

var LOC_EXTRA_NAMES = {
  0x01: "里程", 0x02: "油量", 0x03: "车速", 0x07: "SOC 电量",
  0x12: "进出区域/路线报警", 0x30: "无线通信网络信号强度",
  0x31: "GNSS 定位卫星数", 0xE1: "设备累计里程", 0xE2: "剩余油量百分比",
  0xE3: "发动机转速", 0xE4: "动力电池 SOH", 0xE5: "主电电压", 0xE6: "冷却液温度"
};

function locHex8(v){ var h = (v >>> 0).toString(16).toUpperCase(); while (h.length < 8) h = "0" + h; return h; }
function bitSet(v, b){ return ((v >>> b) & 1) === 1; }

function locAlarmText(v){
  if (v === 0) return "无报警（0x00000000）";
  var t = [];
  for (var i = 0; i < LOC_ALARM_NAMES.length; i++) {
    if (bitSet(v, LOC_ALARM_NAMES[i][0])) t.push("bit" + LOC_ALARM_NAMES[i][0] + " " + LOC_ALARM_NAMES[i][1]);
  }
  return (t.length ? t.join("、") : "只有未收录位") + "（0x" + locHex8(v) + "）";
}

function locStatusText(v){
  var t = [];
  for (var i = 0; i < LOC_STATUS_SET.length; i++) {
    if (bitSet(v, LOC_STATUS_SET[i][0])) t.push("bit" + LOC_STATUS_SET[i][0] + " " + LOC_STATUS_SET[i][1]);
  }
  return t.length ? t.join("、") : "无（bit4 以上全 0）";
}

/* 附加项取值：只给语义。原始字节由调用方统一追加，格式对齐
   「语义值　原始 xx xx」。单位标在值里，避免 0.1km / 0.1L 看错 */
function locExtraText(id, d){
  var v;
  if (id === 0x01 && d.length >= 4) {              /* 里程 DWORD 1/10km */
    v = ((d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]) >>> 0;
    return (v / 10).toFixed(1) + " km";
  }
  if (id === 0x02 && d.length >= 2) {              /* 油量 WORD 1/10L */
    v = (d[0] << 8) | d[1];
    return (v / 10).toFixed(1) + " L";
  }
  if (id === 0x03 && d.length >= 2) {              /* 车速 WORD 1/10km/h */
    v = (d[0] << 8) | d[1];
    return (v / 10).toFixed(1) + " km/h";
  }
  if (id === 0x07 && d.length >= 2) {              /* 动力电池 SOC WORD 0.1% */
    v = (d[0] << 8) | d[1];
    if (v === 0xFFFF) return "无效（0xFFFF，非新能源车型或读不到）";
    return (v / 10).toFixed(1) + " %";
  }
  if (id === 0x07 && d.length === 1) return d[0] + " %";   /* 单字节旧格式兜底 */
  if (id === 0x12 && d.length >= 6) {              /* 类型1 + 区域ID4 + 方向1 */
    var tn = d[0] === 1 ? "圆形" : d[0] === 2 ? "矩形" : d[0] === 3 ? "多边形"
           : d[0] === 4 ? "路线" : "未知(" + d[0] + ")";
    var rid = ((d[1] << 24) | (d[2] << 16) | (d[3] << 8) | d[4]) >>> 0;
    return tn + " 区域 ID=" + rid + "，" + (d[5] === 0 ? "进区域" : "出区域") + "（方向值 " + d[5] + "）";
  }
  if (id === 0x30 && d.length >= 1) return "信号强度 " + d[0] + "（0~31）";
  if (id === 0x31 && d.length >= 1) return d[0] + " 颗";
  if (id === 0xE1 && d.length >= 4) {              /* 设备累计里程 DWORD 0.1km */
    v = ((d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]) >>> 0;
    return (v / 10).toFixed(1) + " km";
  }
  if (id === 0xE2 && d.length >= 2) {              /* 剩余油量百分比 WORD 0.01%，无效 0xFFFF */
    v = (d[0] << 8) | d[1];
    if (v === 0xFFFF) return "无效（0xFFFF，车辆不支持）";
    return (v / 100).toFixed(2) + " %";
  }
  if (id === 0xE2 && d.length === 1) return d[0] + " %";   /* 单字节旧格式兜底 */
  if (id === 0xE3 && d.length >= 2) {              /* 发动机转速 WORD 1RPM，无效 0xFFFF */
    v = (d[0] << 8) | d[1];
    if (v === 0xFFFF) return "无效（0xFFFF，车辆不支持）";
    return v + " RPM";
  }
  if (id === 0xE4 && d.length >= 1) {              /* 动力电池 SOH BYTE 1%，无效 0xFF */
    if (d[0] === 0xFF) return "无效（0xFF，非 EV/PHEV 或读不到）";
    return d[0] + " %";
  }
  if (id === 0xE5 && d.length >= 2) {              /* 主电电压 WORD 0.1V，无效 0xFFFF */
    v = (d[0] << 8) | d[1];
    if (v === 0xFFFF) return "无效（0xFFFF，未采集）";
    return (v / 10).toFixed(1) + " V";
  }
  /* 冷却液温度 1℃，偏移 -40：协议表 27 为 WORD，固件当前按 BYTE 上报，两种长度都认 */
  if (id === 0xE6 && d.length >= 2) {
    v = (d[0] << 8) | d[1];
    if (v === 0xFFFF) return "无效（0xFFFF，车辆不支持）";
    return (v - 40) + " ℃";
  }
  if (id === 0xE6 && d.length === 1) {
    if (d[0] === 0xFF) return "无效（0xFF，车辆不支持）";
    return (d[0] - 40) + " ℃";
  }
  return "长度 " + d.length + " 字节";
}

function parseLocation0200(body){
  var out = {};
  if (body.length < 28) {
    out["✕"] = "位置基本信息固定 28 字节（实际 " + body.length + "）";
    return out;
  }
  var alarm  = u32At(body, 0);
  var status = u32At(body, 4);
  var lat    = u32At(body, 8);
  var lon    = u32At(body, 12);
  var alt    = (body[16] << 8) | body[17];
  var spd    = (body[18] << 8) | body[19];
  var dir    = (body[20] << 8) | body[21];
  var located = bitSet(status, 1);

  out["报警标志"] = locAlarmText(alarm);
  out["[" + locHex8(status) + "]状态位"] = "ACC " + (bitSet(status, 0) ? "开" : "关")
                                        + "、" + (located ? "已定位" : "未定位")
                                        + "、" + (bitSet(status, 2) ? "南纬" : "北纬")
                                        + "、" + (bitSet(status, 3) ? "西经" : "东经");
  out["其它状态位（置位项）"] = locStatusText(status);
  out["纬度"] = degStr(lat) + "° " + (bitSet(status, 2) ? "S（南纬）" : "N（北纬）");
  out["经度"] = degStr(lon) + "° " + (bitSet(status, 3) ? "W（西经）" : "E（东经）");
  out["高程"] = alt + " 米";
  out["速度"] = (spd / 10).toFixed(1) + " km/h（原始 " + spd + " ×0.1km/h）";
  out["方向"] = dir + "°（正北 0，顺时针）";
  out["定位时间"] = bcdTimeStr(body.slice(22, 28));

  /* ---- 附加项 TLV ---- */
  var off = 28, extras = {}, cnt = 0;
  while (off < body.length) {
    if (body.length - off < 2) {
      out["✕附加项"] = "偏移 " + off + " 处只剩 " + (body.length - off) + " 字节，凑不出 ID + 长度";
      break;
    }
    var id = body[off], len = body[off + 1];
    if (body.length - off - 2 < len) {
      out["✕附加项"] = "0x" + hex2(id) + " 声明长度 " + len
                     + "，实际只剩 " + (body.length - off - 2) + " 字节";
      break;
    }
    var data = body.slice(off + 2, off + 2 + len);
    extras["[0x" + hex2(id) + "]" + (LOC_EXTRA_NAMES[id] || "未收录")] =
      locExtraText(id, data) + "　原始 " + toHex(data);
    off += 2 + len;
    cnt++;
  }
  if (cnt) out["附加信息项"] = extras;
  if (off === body.length && body.length > 28 && !cnt) {
    out["✕附加项"] = "消息体还有 " + (body.length - 28) + " 字节但读不出任何附加项";
  }

  if (!located && (lat !== 0 || lon !== 0)) {
    out["说明"] = "状态 bit1=0 表示当前未定位，经纬度非 0 属固件约定："
                + "未定位时上报最后一次有效位置（读 AGPS_INFO_FILE），高程/速度/方向填 0。";
  }
  return out;
}

/* 反解用：合法时原样回 hex（不啰嗦），非法时把原因直接写在值里，
   这样粘一条回包进来就能看出是哪一位不对。 */
function bcdTimeStr(a){
  var s = "";
  for (var i = 0; i < a.length; i++) s += hex2(a[i]);
  if (s === "000000000000") return "未设置（全 0）";
  var e = bcdTimeErr(s);
  if (e) return s + " ✕ " + e;
  return s + "（20" + s.substr(0, 2) + "-" + s.substr(2, 2) + "-" + s.substr(4, 2)
       + " " + s.substr(6, 2) + ":" + s.substr(8, 2) + ":" + s.substr(10, 2) + "）";
}

var FENCE_PROP_BITS = [
  [0x0001, "bit0 起止时间"], [0x0002, "bit1 限速"],
  [0x0004, "bit2 进区域报警给驾驶员"], [0x0008, "bit3 进区域报警给平台"],
  [0x0010, "bit4 出区域报警给驾驶员"], [0x0020, "bit5 出区域报警给平台"]
];
function fencePropText(p){
  var t = [];
  for (var i = 0; i < FENCE_PROP_BITS.length; i++) {
    if (p & FENCE_PROP_BITS[i][0]) t.push(FENCE_PROP_BITS[i][1]);
  }
  return t.length ? t.join("、") : "未置位（不会触发进出区域报警）";
}

/* 读取属性扩展字段（时间 12 → 限速 3），返回新偏移；越界返回 -1 */
function fenceCondRead(body, it, prop, off){
  if (prop & 0x0001) {
    if (body.length - off < 12) return -1;
    it["起止时间"] = bcdTimeStr(body.slice(off, off + 6))
                   + " ~ " + bcdTimeStr(body.slice(off + 6, off + 12));
    off += 12;
  }
  if (prop & 0x0002) {
    if (body.length - off < 3) return -1;
    it["最高速度"] = ((body[off] << 8) | body[off + 1]) + " km/h";
    it["超速持续"] = body[off + 2] + " 秒";
    off += 3;
  }
  return off;
}

/* 0x8600 圆形 / 0x8602 矩形：[操作1][区域总数1][项...] */
function parseFenceSetObj(body, isCircle){
  var out = {};
  if (body.length < 2) { out["✕"] = "消息体不足 2 字节（实际 " + body.length + "）"; return out; }
  var OP = {0:"更新（先清空同类全部区域）",1:"追加",2:"修改"};
  out["[" + normHex(body[0]) + "]操作"] = OP[body[0]] || ("未定义(" + body[0] + ")");
  var cnt = body[1];
  out["[" + normHex(cnt) + "]区域总数"] = cnt;

  var fixed = isCircle ? 18 : 22;
  var off = 2;
  for (var i = 0; i < cnt; i++) {
    var it = {};
    if (body.length - off < fixed) {
      out["✕第 " + (i + 1) + " 项"] = "长度不足 " + fixed + " 字节";
      return out;
    }
    it["区域ID"] = u32At(body, off); off += 4;
    var prop = (body[off] << 8) | body[off + 1]; off += 2;
    it["区域属性"] = "0x" + hex4(prop) + "（" + fencePropText(prop) + "）";
    if (isCircle) {
      var lat = s32At(body, off); off += 4;
      var lon = s32At(body, off); off += 4;
      it["中心点"] = degStr(lat) + ", " + degStr(lon);
      it["半径"] = u32At(body, off) + " 米"; off += 4;
    } else {
      var la1 = s32At(body, off); off += 4;
      var lo1 = s32At(body, off); off += 4;
      var la2 = s32At(body, off); off += 4;
      var lo2 = s32At(body, off); off += 4;
      it["左上角"] = degStr(la1) + ", " + degStr(lo1);
      it["右下角"] = degStr(la2) + ", " + degStr(lo2);
    }
    off = fenceCondRead(body, it, prop, off);
    if (off < 0) { out["✕第 " + (i + 1) + " 项"] = "属性扩展字段越界"; return out; }
    out["[" + normHex(i) + "]区域项 " + (i + 1)] = it;
  }
  if (off !== body.length) out["✕尾部"] = "还有 " + (body.length - off) + " 字节未解析";
  return out;
}

/* 0x8604 多边形：ID4 + 属性2 (+时间12) (+限速3) + 顶点数2 + 顶点(纬4+经4)×n */
function parseFencePolyObj(body){
  var out = {}, it = {};
  if (body.length < 8) { out["✕"] = "消息体不足 8 字节（实际 " + body.length + "）"; return out; }
  it["区域ID"] = u32At(body, 0);
  var prop = (body[4] << 8) | body[5];
  it["区域属性"] = "0x" + hex4(prop) + "（" + fencePropText(prop) + "）";
  var off = fenceCondRead(body, it, prop, 6);
  if (off < 0) { out["✕"] = "属性扩展字段越界"; return out; }
  if (body.length - off < 2) { out["✕"] = "顶点数缺失"; return out; }
  var n = (body[off] << 8) | body[off + 1]; off += 2;
  it["顶点数"] = n;
  var pts = [];
  for (var i = 0; i < n; i++) {
    if (body.length - off < 8) { it["✕"] = "第 " + (i + 1) + " 个顶点越界"; break; }
    pts.push(degStr(s32At(body, off)) + ", " + degStr(s32At(body, off + 4)));
    off += 8;
  }
  it["顶点列表"] = pts;
  out["多边形区域"] = it;
  if (off !== body.length) out["✕尾部"] = "还有 " + (body.length - off) + " 字节未解析";
  return out;
}

/* 0x8601 / 0x8603 / 0x8605：[区域总数1][区域ID4 × n]，n=0 表示删除全部同类 */
function parseFenceDelObj(body){
  var out = {};
  if (body.length < 1) { out["✕"] = "区域总数缺失"; return out; }
  var n = body[0];
  out["[" + normHex(n) + "]区域总数"] = n === 0 ? "0（删除全部同类区域）" : n;
  var ids = [];
  for (var i = 0; i < n; i++) {
    if (body.length - 1 - i * 4 < 4) { out["✕"] = "第 " + (i + 1) + " 个区域ID越界"; break; }
    ids.push(u32At(body, 1 + i * 4));
  }
  if (ids.length) out["区域ID列表"] = ids.join(", ");
  if (body.length !== 1 + n * 4) {
    out["✕长度"] = "应为 " + (1 + n * 4) + " 字节，实际 " + body.length;
  }
  return out;
}

/* 0x8103 / 0x0104 消息体 → 对象
 *   0x8103 设置终端参数：     [参数总数1][参数项...]
 *   0x0104 查询终端参数应答： [应答流水号2][参数总数1][参数项...]
 *   start 为参数总数所在偏移（0x8103 传 0，0x0104 传 2）
 */
function parseParamBodyObj(body, isSet, start){
  var out = {};
  var base = start || 0;
  if (body.length < base + 1) { out["✕"] = "参数总数缺失"; return out; }
  var count = body[base];
  out["[" + normHex(count) + "]参数总数"] = count;
  if (count > 9) out["⚠提示"] = "超固件上限 9 项（JT808_PARAM_ITEM_MAX）";

  var params = {};
  var off = base + 1, idx = 0;
  while (off < body.length && idx < count) {
    if (off + 5 > body.length) {
      params["✕第" + (idx + 1) + "项"] = "头部被截断";
      break;
    }
    var pid = ((body[off] << 24) | (body[off + 1] << 16) | (body[off + 2] << 8) | body[off + 3]) >>> 0;
    var len = body[off + 4];
    off += 5;
    if (off + len > body.length) {
      params["[" + normHex32(pid) + "]"] = "✕ 声明长度 " + len + " 超出剩余字节";
      break;
    }
    var val = body.slice(off, off + len);
    off += len;
    idx++;

    var key = "[" + normHex32(pid) + "]";
    var nm = paramName(pid);
    var shown;
    if (len === 4) {
      var u = ((val[0] << 24) | (val[1] << 16) | (val[2] << 8) | val[3]) >>> 0;
      shown = { "值": u, "原始字节": toHex(val, "") };
    } else if (len === 0) {
      shown = "（空值）";
    } else {
      shown = { "值": bytesToStr(val), "原始字节": toHex(val, "") };
    }
    params[key + (nm || "未收录")] = shown;
  }
  out["参数列表"] = params;

  if (idx === count && off < body.length) {
    out["✕尾部"] = "还有 " + (body.length - off) + " 字节未解析";
  }
  return out;
}

var ACK_RESULT_EN = {
  0:"成功(Success)", 1:"失败(Failure)", 2:"消息有误(MessageError)",
  3:"不支持(NotSupported)", 4:"报警处理确认(AlarmConfirm)"
};

/* 应答结果为失败时补充排查方向。围栏类 result=2 几乎都是时间字段或字节数不对。 */
function ackFailHint(ackId, result){
  if (result === 0) return "";
  if (result === 2 && ackId >= 0x8600 && ackId <= 0x8605) {
    return "设备解析阶段就拒绝了。围栏类最常见：起止时间不是合法 BCD，"
         + "格式是 YYMMDDhhmmss（2026-10-30 07:30:00 写 261030073000，"
         + "写成 202610300730 会让月份变成 26）；其次是属性位 bit0/bit1 "
         + "与实际附带的字节数不符、经纬度越界、区域 ID 或半径为 0。";
  }
  if (result === 2) {
    return "设备认为消息格式有误：核对消息体长度是否与属性 bit0~bit9 一致、必填字段是否齐全。";
  }
  if (result === 3) return "设备不支持该消息类型。";
  return "";
}

function paramName(id){
  for (var i = 0; i < PARAMS.length; i++) if (PARAMS[i].id === id) return PARAMS[i].name;
  return "";
}

/* ---------- 4. 渲染：JSON 视图 ---------- */
function jsonHighlight(obj, indent){
  indent = indent === undefined ? 0 : indent;
  var pad = new Array(indent + 1).join("  ");
  var padIn = new Array(indent + 2).join("  ");

  /* 隐藏内部字段 */
  if (obj && typeof obj === "object" && obj.__meta) {
    var copy = {};
    for (var k in obj) if (k !== "__meta") copy[k] = obj[k];
    obj = copy;
  }

  if (obj === null) return '<span class="jn">null</span>';
  if (typeof obj === "number") return '<span class="jn">' + obj + '</span>';
  if (typeof obj === "boolean") return '<span class="jb">' + (obj ? "true" : "false") + '</span>';
  if (typeof obj === "string") {
    var esc = escapeHtml(obj).replace(/"/g, '\\"');
    var cls = /^[✓✕]/.test(obj) ? (obj.charAt(0) === "✓" ? "js" : "jn") : "js";
    return '<span class="' + cls + '">"' + esc + '"</span>';
  }

  if (Array.isArray(obj)) {
    if (obj.length === 0) return "[]";
    var parts = [];
    for (var i = 0; i < obj.length; i++) parts.push(padIn + jsonHighlight(obj[i], indent + 1));
    return "[\n" + parts.join(",\n") + "\n" + pad + "]";
  }

  var keys = Object.keys(obj);
  if (keys.length === 0) return "{}";
  var lines = [];
  for (var j = 0; j < keys.length; j++) {
    var v = obj[keys[j]];
    lines.push(padIn + '<span class="jk">"' + escapeHtml(keys[j]).replace(/"/g, '\\"') + '"</span>'
             + ": " + jsonHighlight(v, indent + 1));
  }
  return "{\n" + lines.join(",\n") + "\n" + pad + "}";
}

/* ---------- 5. 渲染：表格视图 ---------- */

/* 把任意深度的对象/数组压成可读文本，避免出现 [object Object] */
function flatVal(v){
  if (v === null || v === undefined) return "（空）";
  if (Array.isArray(v)) {
    if (!v.length) return "[]";
    return v.map(flatVal).join(" / ");
  }
  if (typeof v === "object") {
    var ks = Object.keys(v);
    if (!ks.length) return "{}";
    return ks.map(function(k){ return k + " = " + flatVal(v[k]); }).join("；");
  }
  return String(v);
}

function renderTable(obj){
  var rows = [];
  /* 定长字段的 key 前缀可能是 40 个十六进制字符（终端型号 20 字节），
     直接铺进第一列会把列宽挤成竖排，这里折叠成前 8 位 + 省略号，
     完整字节仍保留在 title 里，悬停可看。 */
  function dispKey(k){
    return String(k).replace(/^\[([0-9A-Fa-f]{9,})\]/,
      function(_, h){ return "[" + h.slice(0, 8) + "…]"; });
  }
  function sec(t){ rows.push('<tr class="sec"><td colspan="2">' + t + '</td></tr>'); }
  function add(k, v){
    rows.push('<tr><td title="' + escapeHtml(k) + '">' + escapeHtml(dispKey(k)) + '</td><td>' + v + '</td></tr>');
  }

  sec("帧");
  add("开始", obj["[7E]开始"] === null ? "（无帧头）" : "0x7E");

  sec("消息头");
  var idKey = Object.keys(obj).filter(function(k){ return /\]消息Id$/.test(k); })[0];
  if (idKey) {
    add("消息 ID", "0x" + normHex(obj[idKey]).replace(/^0+/, "").padStart(4, "0")
      + "　" + (obj["消息名称"] || ""));
  }
  var p = obj["消息体属性对象"] || {};
  add("版本号", p["版本号"] || "");
  add("消息体长度", p["[bit0~bit9]消息体长度"] + " 字节");
  add("是否分包", p["[bit13]是否分包"] ? "<span class='errv'>是</span>" : "否");
  add("数据加密", p["[bit10~bit12]数据加密"]);
  var phKey = Object.keys(obj).filter(function(k){ return /\]终端手机号$/.test(k); })[0];
  if (phKey) add("终端手机号", obj[phKey]);
  var sqKey = Object.keys(obj).filter(function(k){ return /\]消息流水号$/.test(k); })[0];
  if (sqKey) add("消息流水号", obj[sqKey]);

  sec("消息体");
  var body = obj["数据体对象"];
  if (body && typeof body === "object" && !Array.isArray(body)) {
    var bkeys = Object.keys(body);
    if (bkeys.length === 0) {
      add("内容", "<span style='color:#828b98'>（空）</span>");
    } else {
      for (var i = 0; i < bkeys.length; i++) {
        var k = bkeys[i], v = body[k];
        if (v && typeof v === "object") {
          var sub = Object.keys(v).map(function(sk){
            return "<span class='subk'>" + escapeHtml(sk) + "</span> = "
                 + escapeHtml(flatVal(v[sk]));
          }).join("<br>");
          add(k, sub);
        } else {
          var cls = /^[✓✕]/.test(String(v)) ? (String(v).charAt(0) === "✓" ? "okv" : "errv") : "";
          add(k, cls ? '<span class="' + cls + '">' + escapeHtml(String(v)) + '</span>' : escapeHtml(String(v)));
        }
      }
    }
  } else {
    add("内容", '<span class="errv">' + escapeHtml(String(body)) + '</span>');
  }

  sec("校验");
  var csKey = Object.keys(obj).filter(function(k){ return /\]校验码$/.test(k); })[0];
  add("报文校验码", csKey ? ("0x" + normHex(obj[csKey])) : "（无）");
  var cmp = obj["校验码比对"] || "";
  add("比对结果", cmp.charAt(0) === "✓"
      ? '<span class="okv">' + escapeHtml(cmp) + '</span>'
      : '<span class="errv">' + escapeHtml(cmp) + '</span>');

  return '<table>' + rows.join("") + '</table>';
}

/* ---------- 6. 对外：解析整段文本（可多帧） ---------- */
function parseAll(text){
  var frames = splitFrames(text);
  var results = [];
  for (var i = 0; i < frames.length; i++) {
    var fr = frames[i];
    var item = { idx: i + 1, hex: fr.hex, obj: null, err: null, complete: fr.complete };
    try {
      item.obj = parseOneFrame(fr.hex);
    } catch (e) {
      item.err = e.message;
    }
    results.push(item);
  }
  return results;
}

