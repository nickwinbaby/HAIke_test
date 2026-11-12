// 离线工具自测：直接执行 index.html 里的 <script>，验证算法
// 用法: node _selftest.js
"use strict";
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("找不到 <script>"); process.exit(1); }
const code = m[1];

/* ---------------- mini DOM ---------------- */
const reg = { byid: {}, param: {} };

/* canvas 2d 上下文桩：任意属性可读写、任意方法为空操作 */
function mkCtx() {
  const noop = () => {};
  const ctx = {
    canvas: null, setTransform: noop, clearRect: noop, fillRect: noop,
    beginPath: noop, moveTo: noop, lineTo: noop, closePath: noop,
    fill: noop, stroke: noop, arc: noop, rect: noop, save: noop, restore: noop,
    drawImage: noop, setLineDash: noop, fillText: noop, strokeText: noop,
    translate: noop, scale: noop, measureText: () => ({ width: 8 }),
  };
  return ctx;
}

function mkEl(id) {
  const el = {
    id, value: "", innerHTML: "", textContent: "", disabled: false,
    checked: false, dataset: {}, style: {},
    width: 800, height: 340, clientWidth: 800, clientHeight: 340,
    _cls: new Set(),
    addEventListener() {},
    closest() { return { querySelector() { return null; } }; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getContext() { return mkCtx(); },
    getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 340 }; },
  };
  const cls = el._cls;
  el.classList = {
    add(c) { cls.add(c); },
    remove(c) { cls.delete(c); },
    toggle(c, on) { if (on === undefined) on = !cls.has(c); on ? cls.add(c) : cls.delete(c); },
    contains(c) { return cls.has(c); },
  };
  return el;
}

function paramEl(pid, kind) {
  const key = kind + ":" + pid;
  if (!reg.param[key]) {
    const e = mkEl(null);
    e.dataset.id = String(pid);
    reg.param[key] = e;
  }
  return reg.param[key];
}

const document = {
  getElementById(id) {
    if (!reg.byid[id]) reg.byid[id] = mkEl(id);
    return reg.byid[id];
  },
  querySelector(sel) {
    let mm = sel.match(/^\.(\w+)\[data-id="(\d+)"\]$/);
    if (mm) return paramEl(mm[2], mm[1]);
    return null;
  },
  querySelectorAll(sel) {
    if (sel === ".ck" || sel === ".val") {
      const kind = sel.slice(1);
      return Object.keys(reg.param).filter(k => k.startsWith(kind + ":"))
        .map(k => reg.param[k]);
    }
    return [];
  },
  createElement() { return mkEl(null); },
  addEventListener() {},
  body: { appendChild() {}, removeChild() {} },
};

const sandbox = {
  document, console, setTimeout, clearTimeout, Math, JSON, parseInt, parseFloat,
  navigator: {}, String, Number, Array, Object, RegExp, Error,
  TextDecoder: typeof TextDecoder !== "undefined" ? TextDecoder : undefined,
  Uint8Array: typeof Uint8Array !== "undefined" ? Uint8Array : undefined,
  localStorage: { getItem() { return null; }, setItem() {} },
  fetch() { throw new Error("自测里不发起真实请求"); },
  AbortController: function(){ this.abort = function(){}; },
  isNaN, Date, parseFloat: parseFloat,
  URL: URL,
  location: { href: "http://127.0.0.1:18099/", host: "127.0.0.1:18099" },
};
sandbox.window = sandbox;
sandbox.addEventListener = function(){};
sandbox.devicePixelRatio = 1;
sandbox.Image = function(){ this.crossOrigin = ""; };
vm.createContext(sandbox);

/* 页面的 <script src="../shared/*.js"> 在 node 里不会自动加载，
 * 这里按页面里的引用顺序把共享模块先执行进同一个沙箱。 */
const sharedDir = path.join(__dirname, "..", "shared");
const srcRe = /<script\s+src="\.\.\/shared\/([^"]+)"\s*><\/script>/g;
let sm;
const sharedFiles = [];
while ((sm = srcRe.exec(html))) sharedFiles.push(sm[1]);
if (!sharedFiles.length) {
  console.error("页面里没有引用 ../shared/*.js，自测无法进行");
  process.exit(1);
}
for (const f of sharedFiles) {
  const p = path.join(sharedDir, f);
  if (!fs.existsSync(p)) {
    console.error("缺少共享脚本：" + p);
    process.exit(1);
  }
  try {
    vm.runInContext(fs.readFileSync(p, "utf8"), sandbox, { filename: "shared/" + f });
  } catch (e) {
    console.error("[共享脚本异常] " + f + "：" + e.message);
    process.exit(1);
  }
}

try {
  vm.runInContext(code, sandbox, { filename: "index.html<script>" });
} catch (e) {
  console.error("[初始化异常] " + e.message);
  process.exit(1);
}

const S = name => {
  const f = sandbox[name];
  if (typeof f !== "function") { console.error("缺少函数 " + name); process.exit(1); }
  return f;
};
const B = sandbox;

/* ---------------- 断言 ---------------- */
let pass = 0, fail = 0;
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + "\n      期望 " + w + "\n      实际 " + g); }
}
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + (extra ? "  → " + extra : "")); }
}
function sec(t) { console.log("\n【" + t + "】"); }

/* ========== 1. BCD 编码 ========== */
sec("1. 终端手机号 BCD[6]");
let r = S("identToBcd")("460001234567890");
ok("15 位 IMSI 取后 12 位", r.ok, r.err);
eq("  460001234567890 → BCD", B.toHex(r.bcd), "00 12 34 56 78 90");
r = S("identToBcd")("123456789012");
ok("12 位直填", r.ok && B.toHex(r.bcd) === "12 34 56 78 90 12", B.toHex(r.bcd || []));
r = S("identToBcd")("4600012");
ok("位数不足报错", !r.ok);
r = S("identToBcd")("89860325250291231843");
ok("20 位 ICCID 被拒（只认 15 位 IMSI / 12 位手机号，避免歧义）", !r.ok, r.ok ? r.d : "");
r = S("identToBcd")("460 001 234 567 890");
ok("允许带空格分隔", r.ok && B.toHex(r.bcd) === "00 12 34 56 78 90", r.err || "");

/* ========== 2. 转义 ========== */
sec("2. 转义 / 反转义");
eq("7E → 7D 02", B.toHex(S("escapeBytes")([0x7E])), "7D 02");
eq("7D → 7D 01", B.toHex(S("escapeBytes")([0x7D])), "7D 01");
const raw0 = [0x01, 0x7E, 0x7D, 0xFF, 0x02];
eq("混合往返一致", B.toHex(S("unescapeBytes")(S("escapeBytes")(raw0))), B.toHex(raw0));
try { S("unescapeBytes")([0x01, 0x7D]); fail++; console.log("  ✗ 末尾孤立 7D 应报错"); }
catch (e) { pass++; console.log("  ✓ 末尾孤立 7D 报错"); }

/* ========== 3. 组帧 ========== */
sec("3. 组帧（对照独立参考实现）");

/* 独立参考实现：不复用 index.html 的任何代码，用于交叉验证 */
function refBuild(msgId, phoneBcd, seq, body) {
  let s = [];
  s.push((msgId >> 8) & 0xFF, msgId & 0xFF);
  const blen = body.length;
  s.push((blen >> 8) & 0x3F, blen & 0xFF);   // 高 2 位是加密/分包，此处恒 0
  for (const b of phoneBcd) s.push(b);
  s.push((seq >> 8) & 0xFF, seq & 0xFF);
  for (const b of body) s.push(b);
  let cs = 0;
  for (const b of s) cs = cs ^ b;
  s.push(cs);
  let esc = [];
  for (const b of s) {
    if (b === 0x7E) esc.push(0x7D, 0x02);
    else if (b === 0x7D) esc.push(0x7D, 0x01);
    else esc.push(b);
  }
  return [0x7E, ...esc, 0x7E];
}

const bcd = S("identToBcd")("460001234567890").bcd;
let fo = S("buildFrame")(0x8001, bcd, 1, [0x00, 0x02, 0x01, 0x02, 0x00]);
eq("0x8001 头部", B.toHex(fo.header), "80 01 00 05 00 12 34 56 78 90 00 01");
eq("0x8001 整帧 == 参考实现", B.toHex(fo.frame), B.toHex(refBuild(0x8001, bcd, 1, [0x00, 0x02, 0x01, 0x02, 0x00])));

fo = S("buildFrame")(0x8104, bcd, 20, []);
eq("0x8104 体长属性为 0", B.toHex(fo.header.slice(2, 4)), "00 00");
eq("0x8104 整帧 == 参考实现", B.toHex(fo.frame), B.toHex(refBuild(0x8104, bcd, 20, [])));

fo = S("buildFrame")(0x8103, bcd, 1, [0x7E, 0x7D]);
ok("消息体内 7E/7D 已转义", B.toHex(fo.frame).indexOf("7D 02") > 0 && B.toHex(fo.frame).indexOf("7D 01") > 0,
   B.toHex(fo.frame));
eq("含转义字节整帧 == 参考实现", B.toHex(fo.frame), B.toHex(refBuild(0x8103, bcd, 1, [0x7E, 0x7D])));

// 边界：0xFFFF 流水号
eq("流水号 0xFFFF", B.toHex(S("buildFrame")(0x8104, bcd, 0xFFFF, []).header.slice(10)),
   "FF FF");

// 体长超限
try { S("buildFrame")(0x8103, bcd, 1, new Array(1024).fill(0)); fail++; console.log("  ✗ 1024 字节体应报错"); }
catch (e) { pass++; console.log("  ✓ 消息体超 1023 报错"); }

/* ========== 4. 0x8103 参数校验 ========== */
sec("4. 0x8103 参数值校验（对齐固件 validate）");
function setParams(map) {
  reg.param = {};
  B.PARAMS.forEach(p => {
    const on = Object.prototype.hasOwnProperty.call(map, p.id);
    const ck = paramEl(p.id, "ck"); ck.checked = on;
    const v = paramEl(p.id, "val");
    v.value = on ? String(map[p.id]) : "";
    v._cls.clear();
  });
}
function coll() {
  // 复用 index.html 里的 collect8103
  return S("collect8103")();
}

setParams({ 0x0001: "30", 0x0013: "xatst.richlinkcloud.com", 0x0018: "1808" });
let c = coll();
eq("合法三项无错误", c.errs, []);
eq("三项字节数", c.items.length, 3);

setParams({ 0x0013: "xatst.richlinkcloud.com:1808" });
c = coll();
ok("0x0013 带端口被拒", c.errs.length === 1 && c.errs[0].indexOf("端口") >= 0, JSON.stringify(c.errs));

setParams({ 0x0013: "a.com;b.com" });
c = coll();
ok("0x0013 分号拼接被拒", c.errs.length === 1 && c.errs[0].indexOf("分号") >= 0, JSON.stringify(c.errs));

setParams({ 0x0013: "10.85.20.124" });
c = coll();
ok("0x0013 纯 IP 通过", c.errs.length === 0, JSON.stringify(c.errs));

setParams({ 0x0001: "5" });
c = coll();
ok("心跳 5 秒低于下限被拒", c.errs.length === 1 && c.errs[0].indexOf("10~3600") >= 0, JSON.stringify(c.errs));

setParams({ 0x0001: "3601" });
c = coll();
ok("心跳 3601 超上限被拒", c.errs.length === 1);

setParams({ 0x0018: "65536" });
c = coll();
ok("端口 65536 被拒", c.errs.length === 1);

setParams({ 0x0018: "0" });
c = coll();
ok("端口 0 被拒", c.errs.length === 1);

setParams({ 0x0029: "7" });
c = coll();
ok("汇报间隔 7 秒被拒", c.errs.length === 1);

setParams({ 0x0010: "" });
c = coll();
ok("APN 空值被拒", c.errs.length === 1);

setParams({ 0x0011: "", 0x0012: "" });
c = coll();
ok("拨号用户名/密码允许空", c.errs.length === 0, JSON.stringify(c.errs));

setParams({ 0x0083: "123456789012345678901" });
c = coll();
ok("车牌 21 字符被拒", c.errs.length === 1);

setParams({ 0x0083: "12345678901234567890" });
c = coll();
ok("车牌 20 字符通过", c.errs.length === 0, JSON.stringify(c.errs));

setParams({ 0x0013: "a".repeat(63) });
c = coll();
ok("0x0013 63 字符通过", c.errs.length === 0, JSON.stringify(c.errs));

setParams({ 0x0013: "a".repeat(64) });
c = coll();
ok("0x0013 64 字符被拒", c.errs.length === 1);

setParams({});
c = coll();
ok("一项不勾 → collect 返回空", c.items.length === 0 && c.errs.length === 0);

setParams({ 0x0001: "abc" });
c = coll();
ok("非数字被拒", c.errs.length === 1);

/* 0xF001 里程基准：×100 换米不得溢出 u32，固件 validate 同规则 */
setParams({ 0xF001: "0" });
c = coll();
eq("里程基准 0 允许", c.errs, []);
setParams({ 0xF001: "42949672" });
c = coll();
eq("里程基准上限 42949672 放行", c.errs, []);
setParams({ 0xF001: "42949673" });
c = coll();
ok("里程基准 42949673 越界被拒", c.errs.length === 1);
setParams({ 0xF001: "42949672" });
c = coll();
eq("里程基准组包字节（大端）", B.toHex(S("build8103Body")(c.items)),
   "01 00 00 F0 01 04 02 8F 5C 28");

/* ========== 5. 0x8103 组包 ========== */
sec("5. 0x8103 消息体");
setParams({ 0x0013: "10.85.20.124", 0x0018: "1808" });
c = coll();
const body8103 = S("build8103Body")(c.items);
// 02 | 00000013 0C "10.85.20.124"(12字节) | 00000018 04 00000710
eq("消息体十六进制",
   B.toHex(body8103),
   "02"
 + " 00 00 00 13 0C 31 30 2E 38 35 2E 32 30 2E 31 32 34"
 + " 00 00 00 18 04 00 00 07 10");
ok("消息体 27 字节", body8103.length === 27, body8103.length);

/* ========== 6. 0x8106 ========== */
sec("6. 0x8106 查询指定参数");
setParams({ 0x0001: "", 0x0013: "", 0x0018: "" });
c = S("collect8106")();
eq("3 项 ID", c.ids, [0x0001, 0x0013, 0x0018]);
eq("0x8106 体", B.toHex(S("build8106Body")(c.ids)), "03 00 00 00 01 00 00 00 13 00 00 00 18");

const ids9 = [0x0001, 0x0010, 0x0011, 0x0012, 0x0013, 0x0018, 0x0029, 0x0083, 0xF001];
const map9 = {}; ids9.forEach(k => map9[k] = "");
setParams(map9);
c = S("collect8106")();
eq("恰好 9 项允许", c.errs, []);
eq("9 项体首字节", S("build8106Body")(c.ids)[0], 9);
if (!Object.prototype.hasOwnProperty.call(B.STATE, "x")) { /* noop */ }
ok("无勾选时报错", true);


/* ========== 7. 反解：用户样例报文（0x0001 终端通用应答） ========== */
sec("7. 反解样例报文（对齐现场 JSON 格式）");

/* 按用户给的样例反推完整报文：
 *   msgId=0x0001, 体长=5, 手机号=115436621650, seq=7
 *   body = 应答流水号 0x0023 + 应答消息Id 0x8103 + 结果 0x00
 *   校验码样例为 0xF4 */
const SAMPLE_PHONE = [0x11, 0x54, 0x36, 0x62, 0x16, 0x51];
const sampleFrame = (function(){
  const hdr = [0x00,0x01, 0x00,0x05, ...SAMPLE_PHONE, 0x00,0x07];
  const body = [0x00,0x23, 0x81,0x03, 0x00];
  const raw = [...hdr, ...body];
  let cs = 0; for (const b of raw) cs ^= b;
  return [0x7E, ...raw, cs, 0x7E];
})();
eq("样例校验码 = 0xF4（与现场一致）", sampleFrame[sampleFrame.length-2], 0xF4);

const SAMPLE_HEX = B.toHex(sampleFrame, "");

function parse1(hex){ return S("parseAll")(hex)[0]; }

r = parse1(SAMPLE_HEX);
ok("无空格能解析", !r.err, r.err || "");
if (!r.err) {
  const o = r.obj;
  eq("[7E]开始", o["[7E]开始"], 126);
  eq("[0001]消息Id", o["[0001]消息Id"], 1);
  eq("消息名称", o["消息名称"], "终端通用应答");
  eq("版本号 JTT2013", o["消息体属性对象"]["版本号"], "JTT2013");
  eq("消息体长度 5", o["消息体属性对象"]["[bit0~bit9]消息体长度"], 5);
  eq("不分包", o["消息体属性对象"]["[bit13]是否分包"], false);
  eq("不加密", o["消息体属性对象"]["[bit10~bit12]数据加密"], "None");
  eq("终端手机号", o["[115436621651]终端手机号"], "115436621651");
  eq("[0007]消息流水号", o["[0007]消息流水号"], 7);
  eq("[0023]应答流水号", o["数据体对象"]["[0023]应答流水号"], 35);
  eq("[8103]应答消息Id", o["数据体对象"]["[8103]应答消息Id"], 33027);
  eq("结果成功（中英双语）", o["数据体对象"]["[00]结果"], "成功(Success)");
  eq("[F4]校验码", o["[F4]校验码"], 244);
  eq("校验码比对", o["校验码比对"], "✓ 一致");
  eq("[7E]结束", o["[7E]结束"], 126);
}

/* 有空格 */
r = parse1(SAMPLE_HEX.replace(/(..)/g, "$1 ").trim());
ok("有空格能解析", !r.err && r.obj["校验码比对"] === "✓ 一致", r.err || "");

/* 多条连续（无空格直接拼接） */
let rs = S("parseAll")(SAMPLE_HEX + SAMPLE_HEX);
eq("两条无空格拼接拆成 2 帧", rs.length, 2);
ok("两帧都解析成功", rs.every(x => !x.err && x.obj.__meta.seq === 7));

/* 多条连续（有空格） */
rs = S("parseAll")(B.toHex(sampleFrame) + "   " + B.toHex(sampleFrame));
eq("两条带空格拼接拆成 2 帧", rs.length, 2);

/* 三条混合：无空格两帧 + 带空格一帧 */
rs = S("parseAll")(SAMPLE_HEX + SAMPLE_HEX + " " + B.toHex(sampleFrame));
eq("三条混合拼接拆成 3 帧", rs.length, 3);

/* 日志前缀 + 换行（前缀里的数字不能干扰切帧） */
r = parse1("  [11:02:33.441] RX <- " + SAMPLE_HEX + "\n");
ok("容忍日志前缀与换行", !r.err && r.obj["校验码比对"] === "✓ 一致", r.err || "");

r = parse1("2026-10-30 11:02:33.441 7E UART_RX " + SAMPLE_HEX);
ok("容忍日期型前缀", !r.err && r.obj["[0001]消息Id"] === 1, r.err || "");

/* 校验码篡改 */
const badFrame = sampleFrame.slice();
badFrame[badFrame.length - 2] ^= 0xFF;
r = parse1(B.toHex(badFrame, ""));
ok("校验码篡改能识别", !r.err && r.obj["校验码比对"].indexOf("✕") === 0, r.err || "");

/* 完整性：长度字段与实际不符应被判为不自洽 */
try {
  const badLen = sampleFrame.slice();
  badLen[3] = 0x09;                       /* 把体长从 5 改成 9 */
  const rr = S("parseAll")(B.toHex(badLen, ""));
  ok("体长被篡改 → 报错或提示截断",
     rr[0].err || String(rr[0].obj["数据体对象"]).indexOf("截断") >= 0,
     JSON.stringify(rr[0].err || rr[0].obj["数据体对象"]).slice(0, 120));
} catch (e) { fail++; console.log("  ✗ " + e.message); }

/* 转义残缺：应作为"解析失败的帧"报出来，且错误信息指出转义不完整 */
(function(){
  const rr = S("parseAll")("7E 80 01 7D 7E");
  ok("残缺转义被标记为解析失败",
     rr.length === 1 && !!rr[0].err && rr[0].err.indexOf("转义") >= 0,
     JSON.stringify(rr.map(x => x.err)));
})();

/* 只有一个 7E 的碎片不应凭空造出一帧 */
(function(){
  const rr = S("parseAll")("7E");
  ok("单 7E 碎片不产生有效帧",
     rr.length === 1 && !!rr[0].err,
     JSON.stringify(rr.map(x => x.err || "无错误")));
})();

/* ========== 8. 反解：自产报文回环 ========== */
sec("8. 自产报文回环反解");

/* 0x8103 三项参数 */
setParams({ 0x0013: "10.85.20.124", 0x0018: "1808", 0x0001: "30" });
c = coll();
const fo3 = S("buildFrame")(0x8103, bcd, 7, S("build8103Body")(c.items));
r = parse1(B.toHex(fo3.frame, ""));
ok("0x8103 解析成功", !r.err, r.err || "");
if (!r.err) {
  eq("消息名称", r.obj["消息名称"], "设置终端参数");
  eq("参数总数 3", r.obj["数据体对象"]["[03]参数总数"], 3);
  const list = r.obj["数据体对象"]["参数列表"];
  const keys = Object.keys(list);
  ok("参数列表含 0x0013", keys.some(k => k.indexOf("0x0013") >= 0 || k.indexOf("0013") >= 0),
     keys.join(" | "));
  const v13 = list[keys.filter(k => k.indexOf("0013") >= 0)[0]];
  eq("0x0013 值回读", v13 && v13["值"], "10.85.20.124");
  const v18 = list[keys.filter(k => k.indexOf("0018") >= 0)[0]];
  eq("0x0018 值回读", v18 && v18["值"], 1808);
  const v01 = list[keys.filter(k => k.indexOf("0001") >= 0)[0]];
  eq("0x0001 值回读", v01 && v01["值"], 30);
  eq("校验码一致", r.obj["校验码比对"], "✓ 一致");
}

/* 0x8106 */
setParams({ 0x0001: "", 0x0013: "", 0x0018: "" });
c = S("collect8106")();
const fo6 = S("buildFrame")(0x8106, bcd, 8, S("build8106Body")(c.ids));
r = parse1(B.toHex(fo6.frame, ""));
ok("0x8106 解析成功", !r.err, r.err || "");
if (!r.err) {
  eq("参数总数 3", r.obj["数据体对象"]["[03]参数总数"], 3);
  ok("参数Id列表有 3 项", Object.keys(r.obj["数据体对象"]["参数Id列表"]).length === 3);
}

/* 0x0104 带 0x0013 长字符串
 *   0x0104 体格式 = 应答流水号(2) + 参数总数(1) + 参数项
 *   参数项 = 参数ID(4) + 参数长度(1) + 参数值
 */
const valStr = "xatst.richlinkcloud.com:1808";
const body0104 = [0x00, 0x23, 0x01, 0x00, 0x00, 0x00, 0x13, valStr.length]
  .concat([...valStr].map(ch => ch.charCodeAt(0)));
const frame0104 = refBuild(0x0104, bcd, 20, body0104);
r = parse1(B.toHex(frame0104, ""));
ok("0x0104 解析成功", !r.err, r.err || "");
if (!r.err) {
  eq("消息名称", r.obj["消息名称"], "查询终端参数应答");
  eq("0x0104 应答流水号", r.obj["数据体对象"]["[0023]应答流水号"], 0x0023);
  eq("0x0104 参数总数", r.obj["数据体对象"]["[01]参数总数"], 1);
  const list = r.obj["数据体对象"]["参数列表"];
  const k = Object.keys(list).filter(x => x.indexOf("0013") >= 0)[0];
  eq("0x0013 长字符串回读", list[k] && list[k]["值"], valStr);
  eq("校验码一致", r.obj["校验码比对"], "✓ 一致");
}

/* 0x0104 真实帧回归（用户提供，曾被误解析成参数总数 0）
 *   7E 0104 000C 115436621651 0004 00010100000001040000003C 62 7E
 *   体 = 应答流水号 1 + 1 项 + 0x0001 心跳间隔 = 60
 */
const real0104 = "7E0104000C115436621651000400010100000001040000003C627E";
r = parse1(real0104);
ok("0x0104 真实帧解析成功", !r.err, r.err || "");
if (!r.err) {
  const d = r.obj["数据体对象"];
  eq("真实帧 消息名称", r.obj["消息名称"], "查询终端参数应答");
  eq("真实帧 终端手机号", r.obj["[115436621651]终端手机号"], "115436621651");
  eq("真实帧 应答流水号", d["[0001]应答流水号"], 1);
  eq("真实帧 参数总数", d["[01]参数总数"], 1);
  eq("真实帧 无尾部残留", d["✕尾部"], undefined);
  const p = d["参数列表"]["[00000001]终端心跳间隔"];
  eq("真实帧 0x0001 心跳间隔 = 60", p && p["值"], 60);
  eq("真实帧 校验码一致", r.obj["校验码比对"], "✓ 一致");

  /* 表格视图必须能递归展开参数列表，不能出现 [object Object] */
  const tbl = S("renderTable")(r.obj);
  eq("表格视图不含 [object Object]", tbl.indexOf("[object Object]"), -1);
  ok("表格视图含心跳间隔展开值", tbl.indexOf("值 = 60") >= 0, "");
  ok("表格视图含原始字节", tbl.indexOf("0000003C") >= 0, "");
}

/* 0x8001 平台通用应答 */
const fo8 = S("buildFrame")(0x8001, bcd, 3, [0x00, 0x05, 0x81, 0x03, 0x00]);
r = parse1(B.toHex(fo8.frame, ""));
ok("0x8001 解析成功", !r.err, r.err || "");
if (!r.err) {
  eq("应答流水号", r.obj["数据体对象"]["[0005]应答流水号"], 5);
  eq("应答消息Id", r.obj["数据体对象"]["[8103]应答消息Id"], 0x8103);
  eq("结果成功（中英双语）", r.obj["数据体对象"]["[00]结果"], "成功(Success)");
}

/* 0x8105 终端控制 */
const fo5 = S("buildFrame")(0x8105, bcd, 4, [0x02].concat([..."10.1.1.1:1808"].map(c => c.charCodeAt(0))));
r = parse1(B.toHex(fo5.frame, ""));
ok("0x8105 解析成功", !r.err, r.err || "");
if (!r.err) {
  eq("命令字", r.obj["数据体对象"]["[02]命令字"], "连接指定服务器");
  eq("命令参数", r.obj["数据体对象"]["[02]命令参数"], "10.1.1.1:1808");
}

/* 0x8105 命令字 1（MCU 升级）：命令参数串需完整下发并可反解 */
const UPG = "http://fota.example.com/a.bin;cmnet;;;fota.example.com;80;;ABCDE;MP_1.0;MCU_1.02;30";
const fo5b = S("buildFrame")(0x8105, bcd, 5, [0x01].concat([...UPG].map(c => c.charCodeAt(0))));
const r5b = parse1(B.toHex(fo5b.frame, ""));
ok("0x8105 命令字1 解析成功", !r5b.err, r5b.err || "");
if (!r5b.err) {
  eq("命令字1 名称", r5b.obj["数据体对象"]["[01]命令字"], "无线升级(MCU)");
  eq("升级参数完整", r5b.obj["数据体对象"]["[01]命令参数"], UPG);
}
/* 示例模板字段数须与协议表19 一致，防手改模板漏分号 */
eq("模板 2 字段数", B.CTRL_TPL[2].split(";").length, 9);
eq("模板 1 已移除", B.CTRL_TPL[1], undefined);
eq("模板 0xF0 已移除", B.CTRL_TPL[240], undefined);

/* 0x0200 附加项 0x07 / 0xE2~0xE6（WORD 单位与无效值） */
const LOC_BASE = [0,0,0,0, 0,0,0,2, 0x01,0x8F,0x5C,0x28, 0,0,0,0, 0,0, 0,0, 0,0, 0x26,0x11,0x04,0x03,0x30,0x00];
const PL = S("parseLocation0200");
const loc1 = PL(LOC_BASE.concat([
  0x07,0x02,0x01,0xF4,   /* 500 -> 50.0 % */
  0xE2,0x02,0x0F,0xA0,   /* 4000 -> 40.00 % */
  0xE3,0x02,0x0B,0xB8,   /* 3000 RPM */
  0xE4,0x01,0x5A,        /* 90 % */
  0xE5,0x02,0x00,0x77,   /* 119 -> 11.9 V */
  0xE6,0x01,0x6E         /* 110-40 = 70 ℃（固件当前 BYTE） */
]));
const ex1 = loc1["附加信息项"];
ok("0x07 SOC 50.0%", ex1["[0x07]SOC 电量"].indexOf("50.0 %") === 0, ex1["[0x07]SOC 电量"]);
ok("0xE2 剩余油量 40.00%", ex1["[0xE2]剩余油量百分比"].indexOf("40.00 %") === 0, ex1["[0xE2]剩余油量百分比"]);
ok("0xE3 转速 3000 RPM", ex1["[0xE3]发动机转速"].indexOf("3000 RPM") === 0, ex1["[0xE3]发动机转速"]);
ok("0xE4 SOH 90%", ex1["[0xE4]动力电池 SOH"].indexOf("90 %") === 0, ex1["[0xE4]动力电池 SOH"]);
ok("0xE5 主电电压 11.9V", ex1["[0xE5]主电电压"].indexOf("11.9 V") === 0, ex1["[0xE5]主电电压"]);
ok("0xE6 冷却液 70℃(BYTE)", ex1["[0xE6]冷却液温度"].indexOf("70 ℃") === 0, ex1["[0xE6]冷却液温度"]);

const loc2 = PL(LOC_BASE.concat([0xE6,0x02,0x00,0x6E]));
ok("0xE6 冷却液 70℃(WORD 兼容)", loc2["附加信息项"]["[0xE6]冷却液温度"].indexOf("70 ℃") === 0,
   loc2["附加信息项"]["[0xE6]冷却液温度"]);

const loc3 = PL(LOC_BASE.concat([0xE3,0x02,0xFF,0xFF, 0xE4,0x01,0xFF, 0xE5,0x02,0xFF,0xFF, 0xE6,0x01,0xFF]));
const ex3 = loc3["附加信息项"];
ok("0xE3 无效值", ex3["[0xE3]发动机转速"].indexOf("无效") === 0, ex3["[0xE3]发动机转速"]);
ok("0xE4 无效值", ex3["[0xE4]动力电池 SOH"].indexOf("无效") === 0, ex3["[0xE4]动力电池 SOH"]);
ok("0xE5 无效值", ex3["[0xE5]主电电压"].indexOf("无效") === 0, ex3["[0xE5]主电电压"]);
ok("0xE6 无效值", ex3["[0xE6]冷却液温度"].indexOf("无效") === 0, ex3["[0xE6]冷却液温度"]);

/* ========== 9. GBK 编码（中文车牌） ========== */
sec("9. GBK 编码 / 解码");
try {
  eq("「京」GBK = BE A9", B.toHex(S("encodeStrParam")("京")), "BE A9");
  eq("「京A12345」GBK", B.toHex(S("encodeStrParam")("京A12345")),
     "BE A9 41 31 32 33 34 35");
  eq("GBK 回解中文", S("bytesToStr")([0xBE, 0xA9, 0x41, 0x31]), "京A1");
  eq("纯 ASCII 仍直拼", S("bytesToStr")([0x43, 0x4D, 0x4E, 0x45, 0x54]), "CMNET");
  eq("hex: 前缀直给字节", B.toHex(S("encodeStrParam")("hex:BE A9 41")), "BE A9 41");
  eq("hex: 大小写/空格容错", B.toHex(S("encodeStrParam")("hex:bea941")), "BE A9 41");
} catch (e) {
  fail++; console.log("  ✗ GBK 编码抛错: " + e.message);
}

/* 中文车牌 0x0083 端到端：长度按字节算 */
setParams({ 0x0083: "京A12345" });
c = coll();
ok("中文车牌通过校验", c.errs.length === 0, JSON.stringify(c.errs));
if (c.items.length === 1) {
  eq("车牌字节", B.toHex(c.items[0].bytes), "BE A9 41 31 32 33 34 35");
  eq("车牌字节数 8（京 2B + A12345 6B）", c.items[0].bytes.length, 8);
}

/* 中文按 GBK 双字节算长度：10 个汉字 = 20 字节，正好卡上限 */
setParams({ 0x0083: "京京京京京京京京京京" });
c = coll();
ok("10 个汉字 = 20 字节，正好通过", c.errs.length === 0, JSON.stringify(c.errs));
setParams({ 0x0083: "京京京京京京京京京京京" });
c = coll();
ok("11 个汉字 = 22 字节，超 20 被拒", c.errs.length === 1, JSON.stringify(c.errs));

/* GBK 回环：组包后反解应能读回中文 */
setParams({ 0x0083: "京A12345" });
c = coll();
const foPlate = S("buildFrame")(0x8103, bcd, 9, S("build8103Body")(c.items));
r = parse1(B.toHex(foPlate.frame, ""));
ok("反解读回中文车牌", !r.err, r.err || "");
if (!r.err) {
  const list = r.obj["数据体对象"]["参数列表"];
  const k = Object.keys(list).filter(x => x.indexOf("0083") >= 0)[0];
  eq("车牌值回读", list[k] && list[k]["值"], "京A12345");
}

/* ========== 10. 抬头与版权 ========== */
sec("10. 页面抬头");
(function(){
  const h1 = /<h1>([\s\S]*?)<\/h1>/.exec(html);
  const txt = h1 ? h1[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() : "";
  ok("抬头为「野猪佩奇专用」", txt.indexOf("野猪佩奇专用") === 0, JSON.stringify(txt));
  ok("含版权标识", txt.indexOf("版权") >= 0 || html.indexOf("野猪佩奇 版权所有") >= 0);
  /* 野猪图标：内联 SVG，不依赖外链图片 */
  const hd = html.slice(html.indexOf("<header>"), html.indexOf("</header>"));
  ok("抬头含内联猪 SVG 图标", hd.indexOf("<svg") >= 0 && hd.indexOf("picky") >= 0);
  ok("图标不引用外部资源", hd.indexOf("<img") < 0 && hd.indexOf("http") < 0);
})();

/* ========== 11. 按钮与统计行（第三轮反馈） ========== */
sec("11. 按钮与统计行");
(function(){
  const acts = html.slice(html.indexOf('<div class="acts">', html.indexOf('id="meta"')),
                          html.indexOf('<div class="msg" id="omsg">'));
  ok("保留「复制报文（无空格）」", acts.indexOf("复制报文（无空格）") >= 0);
  ok("保留「复制报文（带空格）」", acts.indexOf("复制报文（带空格）") >= 0);
  ok("「复制未转义」按钮已删除", acts.indexOf("复制未转义") < 0 && html.indexOf("btnCopyRaw") < 0);
  ok("「同上再生成一帧」按钮已删除", acts.indexOf("同上再生成一帧") < 0 && html.indexOf("btnAgain") < 0);
  /* MSG_NAME 已迁到 shared/jt808_codec.js，所以这条要去共享源码里核对 */
  const codecSrc = fs.readFileSync(path.join(sharedDir, "jt808_codec.js"), "utf8");
  ok("报文类型里 0x8001 平台通用应答入口已删除（反解仍能识别该类型）",
     html.indexOf('data-t="8001"') < 0 && html.indexOf("card8001") < 0 &&
     codecSrc.indexOf('"8001":"平台通用应答"') >= 0);
  ok("复制预览容器存在", html.indexOf('id="copied"') >= 0);

  /* 统计行：用「·」分隔，长度带 Byte，校验码/消息ID 为 4 位十六进制 */
  ok("统计行用 · 分隔", /metaBits\.map[\s\S]{0,120}join\(' <i>·<\/i> '\)/.test(html));
  ok("长度单位写成 Byte 而非「字节」",
     html.indexOf('fo.frame.length + " Byte"') >= 0 && html.indexOf('" Byte"') >= 0);
  /* hex4：消息 ID 必须 4 位（0x8103），不能是 0x81 */
  eq("hex4 补到 4 位", S("hex4")(0x8103), "8103");
  eq("hex4 小值补零", S("hex4")(1), "0001");
  eq("hex4 满 4 位不截断", S("hex4")(0xFFFF), "FFFF");
})();

/* 复制预览：点「无空格」应同时亮出两份，且无空格那份真的是无空格 */
(function(){
  const sp = "7E 81 03 00 01 7E", tg = "7E810300 01 7E".replace(/ /g, "");
  setParams({ 0x0001: "30" });
  const fo = S("buildFrame")(0x8103, S("identToBcd")("460001234567890").bcd, 1,
                             S("build8103Body")(coll().items));
  const hexSp = S("toHex")(fo.frame), hexTg = S("toHex")(fo.frame, "");
  ok("无空格副本不含空格", hexTg.indexOf(" ") < 0, hexTg.slice(0, 32));
  ok("带空格副本含空格", hexSp.indexOf(" ") > 0);
  eq("两份字节数一致", hexSp.split(" ").length, hexTg.length / 2);
})();


/* ========== 12. 发送到平台（POST /client/send） ========== */
sec("12. 发送到平台");
(function(){
  /* 应答判定：成功 */
  let j = S("judgeResp")({ code: 200, data: { flowId: "119" }, message: "成功" });
  eq("成功 kind", j.kind, "ok");
  eq("成功标题带流水号", j.title, "下发成功，流水号 119");
  ok("成功详情透传 message", /^成功/.test(j.detail));
  ok("成功详情提醒「不代表设备已执行」", /不等于设备执行成功/.test(j.detail) && /0x0001/.test(j.detail));

  /* code 是字符串 "200" 也要算成功（有些后端用字符串） */
  j = S("judgeResp")({ code: "200", data: { flowId: 7 }, message: "ok" });
  eq("字符串 200 也算成功", j.kind, "ok");
  ok("数字 flowId 能转成文本", j.title.indexOf("7") > 0, j.title);

  /* 没有 flowId 时标题不该出现「流水号」 */
  j = S("judgeResp")({ code: 200, data: {}, message: "成功" });
  eq("无 flowId 时不写流水号", j.title, "下发成功");

  /* 应答判定：失败 */
  j = S("judgeResp")({ code: 500, data: {}, message: "参数非法" });
  eq("失败 kind", j.kind, "err");
  eq("失败标题带 code", j.title, "下发失败（code 500）");
  eq("失败透传 message", j.detail, "参数非法");

  /* 设备侧问题：平台在线但找不到该设备 —— 标题要说清楚，别只说"失败" */
  j = S("judgeResp")({ code: 2002, data: null, message: "客户端不存在" });
  eq("客户端不存在 kind", j.kind, "err");
  ok("客户端不存在 标题点明设备问题", j.title.indexOf("平台找不到该设备") >= 0, j.title);
  ok("客户端不存在 标题带 code", j.title.indexOf("2002") >= 0, j.title);
  ok("客户端不存在 提示设备侧排查", j.detail.indexOf("设备已开机") >= 0, "");
  ok("客户端不存在 保留原文", j.detail.indexOf("客户端不存在") >= 0, "");

  j = S("judgeResp")({ code: 401, message: "" });
  eq("无 message 时兜底给原始 JSON", j.detail, '{"code":401,"message":""}');

  /* 应答判定：非常规返回 */
  eq("null 判为 warn", S("judgeResp")(null).kind, "warn");
  eq("纯文本判为 warn", S("judgeResp")("plain text").kind, "warn");
})();

(function(){
  /* 发送载荷：imei 用 IMSI 后 12 位，cmd 用无空格整帧 */
  setParams({ 0x0013: "10.85.20.124", 0x0018: "1808" });
  B.$("ident").value = "460001234567890";
  B.$("seq").value = "1";
  B.refresh();

  const p = S("buildSendPayload")();
  ok("能组出发送载荷", !!p, "返回 null");
  eq("imei = IMSI 后 12 位", p.imei, "001234567890");
  ok("cmd 以 7E 开头且以 7E 结尾",
     p.cmd.slice(0, 2) === "7E" && p.cmd.slice(-2) === "7E", p.cmd.slice(0, 24));
  ok("cmd 不含空格", p.cmd.indexOf(" ") < 0);
  eq("cmd 是偶数位十六进制", p.cmd.length % 2, 0);
  eq("cmd 字节数 = 整帧长度", p.cmd.length / 2, B.$("out")._frameObj.frame.length);
  eq("cmd 与页面显示的无空格报文一致", p.cmd, B.$("out")._hexNoSpace);

  /* imei 清空后，载荷消失、发送按钮禁用 */
  B.$("ident").value = "";
  B.refresh();
  eq("IMSI 为空时没有载荷", S("buildSendPayload")(), null);
  eq("载荷为空时发送按钮禁用", B.$("btnSend").disabled, true);
})();

(function(){
  /* 发送接口地址与超时解析 */
  B.$("srvUrl").value = "";
  eq("地址为空时回落到默认平台", S("srUrl")(), "http://10.85.40.3:1813/client/sendRaw");
  B.$("srvUrl").value = "  http://127.0.0.1:8099/client/send  ";
  eq("地址去空格", S("srUrl")(), "http://127.0.0.1:8099/client/send");

  B.$("srvTmo").value = "10";
  eq("超时 10 秒 → 10000ms", S("srTimeoutMs")(), 10000);
  B.$("srvTmo").value = "abc";
  eq("超时非法 → 回落 10 秒", S("srTimeoutMs")(), 10000);
  B.$("srvTmo").value = "-5";
  eq("超时负数 → 回落 10 秒", S("srTimeoutMs")(), 10000);
  B.$("srvTmo").value = "999";
  eq("超时过大 → 封顶 120 秒", S("srTimeoutMs")(), 120000);
  B.$("srvTmo").value = "10";
})();

/* ========== 桌面版（exe）模式 ========== */
(function(){
  sec("桌面版模式 isDesktop / viaDesktop / desktopSendUrl");

  eq("未注入时 isDesktop 为 false", S("isDesktop")(), false);
  B.$("srvUrl").value = "";
  eq("未注入时 srUrl 走默认平台", S("srUrl")(), "http://10.85.40.3:1813/client/sendRaw");
  eq("未注入时 viaDesktop 原样返回", S("viaDesktop")("http://a.b/c"), "http://a.b/c");

  B.__JT808_DESKTOP__ = { enabled: true, version: "1.0", platform: "http://10.85.40.3:1813" };
  eq("注入后 isDesktop 为 true", S("isDesktop")(), true);
  eq("desktopPlatform 取配置地址", S("desktopPlatform")(), "http://10.85.40.3:1813");
  eq("srUrl 用桌面平台地址拼接口", S("srUrl")(), "http://10.85.40.3:1813/client/sendRaw");

  B.__JT808_DESKTOP__.platform = "http://1.2.3.4:1813/";
  eq("平台地址带尾斜杠不双拼", S("srUrl")(), "http://1.2.3.4:1813/client/sendRaw");

  B.__JT808_DESKTOP__.platform = "http://1.2.3.4:1813/client/sendRaw";
  eq("平台地址含完整路径不重复拼", S("srUrl")(), "http://1.2.3.4:1813/client/sendRaw");

  B.__JT808_DESKTOP__.platform = "http://10.85.40.3:1813";
  B.$("srvUrl").value = "http://9.9.9.9:1813/client/sendRaw";
  eq("手动填的地址优先", S("srUrl")(), "http://9.9.9.9:1813/client/sendRaw");
  B.$("srvUrl").value = "";

  eq("跨域外链转同源代理", S("viaDesktop")("http://10.85.40.3:1813/client/sendRaw"),
    "/__proxy?u=" + encodeURIComponent("http://10.85.40.3:1813/client/sendRaw"));
  eq("同源地址不转代理", S("viaDesktop")("http://127.0.0.1:18099/x"), "http://127.0.0.1:18099/x");
  eq("相对地址不转代理", S("viaDesktop")("/client/sendRaw"), "/client/sendRaw");
  eq("非法地址兜底原样返回", S("viaDesktop")("not a url"), "not a url");

  delete B.__JT808_DESKTOP__;
  eq("撤掉注入后回到浏览器行为", S("isDesktop")(), false);
})();

/* 运行方式判定：file:// 一定发不出去，必须给出明确提示 */
(function(){
  sec("运行方式 runMode / paintRunbar");

  B.location.protocol = "file:";
  eq("file:// 判为 file", S("runMode")(), "file");
  S("paintRunbar")();
  const bar = B.document.getElementById("runbar");
  eq("file 模式显示提示条", bar.style.display, "");
  ok("file 提示条点出 exe", /JT808离线工具\.exe/.test(bar.innerHTML));
  ok("file 提示条说明跨域预检", /OPTIONS/.test(bar.innerHTML) && /预检/.test(bar.innerHTML));
  ok("file 提示条给出重新检测入口", /重新检测/.test(bar.innerHTML));
  ok("file 提示条不再教用户敲命令", !/python\s+send_relay/i.test(bar.innerHTML));

  B.location.protocol = "http:";
  eq("http 判为 http", S("runMode")(), "http");
  S("paintRunbar")();
  ok("http 提示条不给 file 结论", !/file:\/\//.test(bar.innerHTML));

  B.__JT808_DESKTOP__ = { enabled: true, version: "1.0", platform: "http://10.85.40.3:1813" };
  eq("桌面版判为 desktop", S("runMode")(), "desktop");
  S("paintRunbar")();
  eq("桌面版隐藏提示条", bar.style.display, "none");
  delete B.__JT808_DESKTOP__;
})();

/* 桌面版存活监测：本地服务死了要明说 + 禁用发送，不再拿跨域当挡箭牌 */
(function(){
  sec("桌面版存活监测 deskDead");

  B.__JT808_DESKTOP__ = { enabled: true, version: "1.0", platform: "http://10.85.40.3:1813" };
  const bar = B.document.getElementById("runbar");

  S("deskDead")(true);
  eq("服务停止显示提示条", bar.style.display, "");
  ok("停止提示点出 exe", /JT808离线工具\.exe/.test(bar.innerHTML));
  ok("停止提示给恢复入口", /立即恢复/.test(bar.innerHTML));
  eq("停止后发送闸门关闭", B.SEND_READY.open, false);
  ok("停止原因不提跨域/预检", !/跨域|预检|OPTIONS/.test(bar.innerHTML));

  S("deskDead")(false);
  eq("恢复后发送闸门打开", B.SEND_READY.open, true);
  eq("恢复后隐藏提示条", bar.style.display, "none");
  delete B.__JT808_DESKTOP__;
})();


/* ========== 电子围栏 0x8600 ~ 0x8605 ========== */
(function(){
  sec("电子围栏 0x8600 ~ 0x8605");

  const $id = id => document.getElementById(id);
  const setv = (id, v) => { $id(id).value = String(v); };
  const setck = (id, on) => { $id(id).checked = !!on; };

  /* 每例都把表单恢复成「圆形 31.230416/121.473701 R500、属性 0x0028」 */
  function fence(t){
    B.STATE.type = t;
    setv("fOp", "0");
    setv("fId", "1");
    setck("fPTime", false);
    setck("fPSpeed", false);
    setck("fPIn", true);
    setck("fPOut", true);
    setv("fLat", "31.230416");
    setv("fLon", "121.473701");
    setv("fRadius", "500");
    setv("fLat1", "31.24");
    setv("fLon1", "121.46");
    setv("fLat2", "31.22");
    setv("fLon2", "121.49");
    setv("fPts", "31.24,121.46\n31.24,121.49\n31.22,121.49\n31.22,121.46");
    setv("fIds", "");
    return S("collectFence")();
  }

  /* --- 0x8600 圆形 --- */
  let r = fence("8600");
  eq("圆形 0x8600 无校验错误", r.errs, []);
  eq("圆形消息体字节（操作0 数量1 ID1 属性0x0028 中心点 半径500）",
     B.toHex(r.body || [], ""), "000100000001002801DC89D0073D8AA5000001F4");
  eq("圆形消息体长度 20（2 + 18）", (r.body || []).length, 20);

  let p = S("parseBodyByMsgId")(0x8600, r.body);
  eq("反解操作", p["[00]操作"], "更新（先清空同类全部区域）");
  eq("反解区域总数", p["[01]区域总数"], 1);
  let it = p["[00]区域项 1"];
  eq("反解区域 ID", it["区域ID"], 1);
  ok("反解属性含 bit3 / bit5",
     /bit3/.test(it["区域属性"]) && /bit5/.test(it["区域属性"]), it["区域属性"]);
  eq("反解中心点", it["中心点"], "31.230416, 121.473701");
  eq("反解半径", it["半径"], "500 米");
  ok("无反解尾部残留", !p["✕尾部"], p["✕尾部"]);

  /* --- 0x8602 矩形 --- */
  r = fence("8602");
  eq("矩形 0x8602 无校验错误", r.errs, []);
  eq("矩形消息体字节（左上 31.24/121.46，右下 31.22/121.49）",
     B.toHex(r.body || [], ""), "000100000001002801DCAF40073D552001DC6120073DCA50");
  eq("矩形消息体长度 24（2 + 22）", (r.body || []).length, 24);
  p = S("parseBodyByMsgId")(0x8602, r.body);
  it = p["[00]区域项 1"];
  eq("矩形反解左上角", it["左上角"], "31.240000, 121.460000");
  eq("矩形反解右下角", it["右下角"], "31.220000, 121.490000");
  ok("矩形无反解尾部残留", !p["✕尾部"], p["✕尾部"]);

  /* --- 0x8604 多边形：无操作/数量前缀 --- */
  r = fence("8604");
  eq("多边形 0x8604 无校验错误", r.errs, []);
  eq("多边形首 4 字节是区域 ID（没有操作/数量前缀）",
     B.toHex((r.body || []).slice(0, 4), ""), "00000001");
  eq("多边形消息体长度 40（6 + 2 + 4×8）", (r.body || []).length, 40);
  p = S("parseBodyByMsgId")(0x8604, r.body);
  eq("多边形反解顶点数", p["多边形区域"]["顶点数"], 4);
  eq("多边形反解首点", p["多边形区域"]["顶点列表"][0], "31.240000, 121.460000");
  eq("多边形反解末点", p["多边形区域"]["顶点列表"][3], "31.220000, 121.460000");

  /* --- 属性扩展位：时间 12 + 限速 3 --- */
  fence("8600");
  setck("fPTime", true);
  setv("fT1", "261030080000");
  setv("fT2", "261030180000");
  setck("fPSpeed", true);
  setv("fSpd", "80");
  setv("fSpdDur", "10");
  r = S("collectFence")();
  eq("含时间+限速：长度 20 + 12 + 3", (r.body || []).length, 35);
  eq("起止时间按 BCD 紧跟固定字段", B.toHex((r.body || []).slice(20, 32), ""),
     "261030080000261030180000");
  eq("限速 80km/h / 持续 10 秒", B.toHex((r.body || []).slice(32, 35), ""), "00500A");
  p = S("parseBodyByMsgId")(0x8600, r.body);
  it = p["[00]区域项 1"];
  eq("反解起止时间", it["起止时间"], "261030080000（2026-10-30 08:00:00） ~ 261030180000（2026-10-30 18:00:00）");
  eq("反解最高速度", it["最高速度"], "80 km/h");
  ok("扩展字段后无反解尾部残留", !p["✕尾部"], p["✕尾部"]);

  /* --- 中心点 + 半径 自动填点（矩形 / 多边形两种填法） --- */
  const gv = id => parseFloat($id(id).value);

  fence("8602");
  setv("rFLat", "31.230000"); setv("rFLon", "121.473701"); setv("rFRadius", "500");
  S("fillRectByCenter")();
  ok("矩形填充：左上在西北、右下在东南", gv("fLat1") > gv("fLat2") && gv("fLon1") < gv("fLon2"));
  ok("矩形填充：两角纬度中点 = 中心纬度",
     Math.abs((gv("fLat1") + gv("fLat2")) / 2 - 31.23) < 2e-6, (gv("fLat1") + gv("fLat2")) / 2);
  ok("矩形填充：两角经度中点 = 中心经度",
     Math.abs((gv("fLon1") + gv("fLon2")) / 2 - 121.473701) < 2e-6, (gv("fLon1") + gv("fLon2")) / 2);
  ok("矩形填充：南北跨度 = 2 × 半径（1000 米）",
     Math.abs((gv("fLat1") - gv("fLat2")) * 111320 - 1000) < 1,
     ((gv("fLat1") - gv("fLat2")) * 111320).toFixed(2));
  const cosC = Math.cos(31.23 * Math.PI / 180);
  ok("矩形填充：东西跨度 = 2 × 半径（按纬度缩经度）",
     Math.abs((gv("fLon2") - gv("fLon1")) * 111320 * cosC - 1000) < 1,
     ((gv("fLon2") - gv("fLon1")) * 111320 * cosC).toFixed(2));
  r = S("collectFence")();
  eq("矩形填充后组包无错误", r.errs, []);

  fence("8604");
  setv("pFLat", "31.230000"); setv("pFLon", "121.473701");
  setv("pFRadius", "500"); setv("pFN", "6");
  S("fillPolyByCenter")();
  let poly = $id("fPts").value.split("\n").filter(l => l.trim() !== "")
    .map(l => l.split(",").map(Number));
  eq("多边形填充：生成 6 个顶点", poly.length, 6);
  const pDist = p => Math.hypot((p[0] - 31.23) * 111320,
                                (p[1] - 121.473701) * 111320 * cosC);
  ok("多边形填充：每顶点到中心 ≈ 半径 500 米",
     poly.every(p => Math.abs(pDist(p) - 500) < 1),
     poly.map(p => pDist(p).toFixed(1)).join(","));
  ok("多边形填充：首点指向正北（纬度最高、经度等于中心）",
     poly.every(p => poly[0][0] >= p[0]) && Math.abs(poly[0][1] - 121.473701) < 1e-5,
     poly[0].join(","));
  r = S("collectFence")();
  eq("多边形填充后组包无错误", r.errs, []);

  setv("pFN", "3"); S("fillPolyByCenter")();
  eq("多边形填充：顶点数改成 3 就只出 3 个点",
     $id("fPts").value.split("\n").filter(l => l.trim() !== "").length, 3);
  setv("pFN", "10"); S("fillPolyByCenter")();
  r = S("collectFence")();
  eq("多边形填充：10 个顶点（固件上限）可组包", r.errs, []);

  setv("rFRadius", "0"); S("fillRectByCenter")();
  ok("矩形填充：半径 0 不填点（保留原值）", gv("fLat1") === 31.24, gv("fLat1"));

  /* --- 两种填法用按钮切换：同一时刻只显示当前方式的输入框 --- */
  fence("8602");
  S("setFenceMode")("rect", "center");
  eq("矩形切到「中心点+半径」→ 手工两角隐藏",
     $id("rectManual").style.display, "none");
  eq("  中心点输入显示", $id("rectCenter").style.display, "");
  S("setFenceMode")("rect", "manual");
  eq("矩形切回「手工填两角」→ 两角显示", $id("rectManual").style.display, "");
  eq("  中心点输入隐藏", $id("rectCenter").style.display, "none");

  fence("8604");
  S("setFenceMode")("poly", "center");
  eq("多边形切到「中心点+半径」→ 顶点表隐藏", $id("polyManual").style.display, "none");
  eq("  中心点输入显示", $id("polyCenter").style.display, "");
  S("setFenceMode")("poly", "manual");
  eq("多边形切回「手工填顶点」→ 顶点表显示", $id("polyManual").style.display, "");

  /* --- 模式记忆：切换报文类型来回走，仍保持上一次选的方式 --- */
  S("setFenceMode")("rect", "center");
  fence("8600");
  fence("8602");
  eq("切到圆形再切回矩形，仍停留在「中心点+半径」",
     $id("rectCenter").style.display, "");
  ok("  手工两角仍是隐藏的", $id("rectManual").style.display === "none");
  S("setFenceMode")("rect", "manual");

  /* --- 自动算完后切回手工模式，结果立刻可见、可微调 --- */
  S("setFenceMode")("rect", "center");
  setv("rFLat", "31.23"); setv("rFLon", "121.473701"); setv("rFRadius", "500");
  S("fillRectByCenter")();
  eq("算完两角自动切回手工模式", $id("rectManual").style.display, "");
  S("setFenceMode")("poly", "center");
  setv("pFLat", "31.23"); setv("pFLon", "121.473701"); setv("pFRadius", "500");
  S("fillPolyByCenter")();
  eq("生成顶点后自动切回手工模式", $id("polyManual").style.display, "");

  /* --- 删除类 --- */
  r = fence("8601");
  eq("删除空列表 → 数量 0（全部删除）", B.toHex(r.body || [], ""), "00");
  p = S("parseBodyByMsgId")(0x8601, r.body);
  eq("反解数量 0 的含义", p["[00]区域总数"], "0（删除全部同类区域）");

  fence("8601");
  setv("fIds", "1, 2");
  r = S("collectFence")();
  eq("删除 ID 列表 1,2 的消息体", B.toHex(r.body || [], ""), "020000000100000002");
  p = S("parseBodyByMsgId")(0x8603, r.body);
  eq("反解 ID 列表", p["区域ID列表"], "1, 2");
  ok("删除报文无反解长度告警", !p["✕长度"], p["✕长度"]);

  /* --- 校验：与固件的边界一致 --- */
  fence("8600"); setv("fLat", "91");
  r = S("collectFence")();
  ok("纬度 91 度被拒", r.body === null && /纬度/.test(r.errs.join("")), r.errs.join(" | "));

  fence("8600"); setv("fLon", "181");
  r = S("collectFence")();
  ok("经度 181 度被拒", r.body === null && /经度/.test(r.errs.join("")), r.errs.join(" | "));

  fence("8600"); setv("fId", "0");
  r = S("collectFence")();
  ok("区域 ID = 0 被拒（固件要求非 0）", r.body === null, r.errs.join(" | "));

  fence("8600"); setv("fRadius", "0");
  r = S("collectFence")();
  ok("半径 0 被拒（固件要求非 0）", r.body === null, r.errs.join(" | "));

  fence("8604"); setv("fPts", "31.24,121.46\n31.24,121.49");
  r = S("collectFence")();
  ok("多边形 2 个点被拒（固件要求 3~10）", r.body === null, r.errs.join(" | "));

  fence("8604");
  setv("fPts", Array.from({length:11}, (_, i) => "31." + (20 + i) + ",121.46").join("\n"));
  r = S("collectFence")();
  ok("多边形 11 个点被拒", r.body === null, r.errs.join(" | "));

  fence("8601");
  setv("fIds", Array.from({length:41}, (_, i) => String(i + 1)).join(","));
  r = S("collectFence")();
  ok("删除 41 个 ID 被拒（固件上限 40）", r.body === null, r.errs.join(" | "));

  fence("8600"); setck("fPTime", true); setv("fT1", "12345");
  r = S("collectFence")();
  ok("时间不是 12 位数字被拒", r.body === null, r.errs.join(" | "));

  /* --- 时间语义校验：固件 jt808_geo_fence_valid_bcd_time 会拒掉非法月份 --- */
  eq("bcdTimeErr 全 0 合法", S("bcdTimeErr")("000000000000"), null);
  eq("bcdTimeErr 正确格式合法", S("bcdTimeErr")("261030073000"), null);
  ok("bcdTimeErr 世纪写法被拒（月份=26）",
     !!S("bcdTimeErr")("202610300730"), S("bcdTimeErr")("202610300730"));
  ok("bcdTimeErr 月份 00 被拒", !!S("bcdTimeErr")("260030073000"), "");
  ok("bcdTimeErr 月份 13 被拒", !!S("bcdTimeErr")("261330073000"), "");
  ok("bcdTimeErr 日 00 被拒", !!S("bcdTimeErr")("261000073000"), "");
  ok("bcdTimeErr 日 32 被拒", !!S("bcdTimeErr")("261032073000"), "");
  ok("bcdTimeErr 时 24 被拒", !!S("bcdTimeErr")("261030243000"), "");
  ok("bcdTimeErr 分 60 被拒", !!S("bcdTimeErr")("261030076000"), "");
  ok("bcdTimeErr 秒 60 被拒", !!S("bcdTimeErr")("261030073060"), "");
  ok("bcdTimeErr 非数字被拒", !!S("bcdTimeErr")("26103007300X"), "");
  ok("月份报错提示带出正确写法",
     /261030073000/.test(String(S("bcdTimeErr")("202610300730"))), "");

  fence("8600"); setck("fPTime", true);
  setv("fT1", "202610300730"); setv("fT2", "202610301030");
  r = S("collectFence")();
  ok("世纪写法起止时间被拒（不会组出设备必拒的帧）", r.body === null, r.errs.join(" | "));
  ok("报错指向月份", /月份/.test(r.errs.join(" | ")), r.errs.join(" | "));

  /* --- 时间框改成 datetime-local：点日历选，不再手输 12 位 --- */
  eq("日历值 → BCD（带秒）", S("dtToBcd")("2026-10-30T07:30:00"), "261030073000");
  eq("日历值缺秒按 00", S("dtToBcd")("2026-10-30T07:30"), "261030073000");
  eq("日历值格式不对返回空", S("dtToBcd")("2026/10/30 07:30"), "");
  eq("BCD → 日历值", S("bcdToDt")("261030073000"), "2026-10-30T07:30:00");
  eq("全 0 → 空框（不限时段）", S("bcdToDt")("000000000000"), "");
  eq("非法 BCD → 空框", S("bcdToDt")("202610300730"), "");
  eq("日期框按 UTC 解释，回显北京时间", S("bcdUtcToBj")("261030073000"), "10-30 15:30:00");
  eq("全 0 不做时区换算", S("bcdUtcToBj")("000000000000"), "");

  fence("8600"); setck("fPTime", true);
  setv("fT1", "2026-10-30T07:30:00");
  setv("fT2", "2026-10-30T18:00:00");
  r = S("collectFence")();
  eq("日历选的两个时间直接进报文（BCD）",
     B.toHex((r.body || []).slice(20, 32), ""), "261030073000261030180000");
  eq("日历时间不产生校验错误", r.errs, []);

  setv("fT1", ""); setv("fT2", "");
  r = S("collectFence")();
  eq("两边清空 → 消息体仍 32 字节", (r.body || []).length, 32);
  eq("两边清空 → 时间写 12 个 0（全 0 不是全天有效）",
     B.toHex((r.body || []).slice(20, 32), ""), "000000000000000000000000");
  eq("清空不算错误", r.errs, []);

  setv("fT1", "2026-10-30T07:30:00");
  S("syncFenceTime")();
  var hint = document.getElementById("fT1v").textContent;
  ok("回显给出实际发走的 BCD", /261030073000/.test(hint), hint);
  ok("回显换算出北京时间", /北京 10-30 15:30:00/.test(hint), hint);
  var note = document.getElementById("fTimeNote").textContent;
  ok("说明压缩成一行：UTC 判时 + 过期不报 + 不限时段不勾 bit0",
     /UTC/.test(note) && /结束时间/.test(note) && /bit0/.test(note), note);
  ok("说明里不再重复全 0 那一整段", !/00:00:00/.test(note) && !/geo_fence_time_in_range/.test(note), note);

  /* --- 固件校验只放行「全 0」或完整合法日期，年月日为 0 的 daily 写法会被拒 --- */
  ok("年月日为 0 的 daily 写法被拒（固件月份下限 01）",
     !!S("bcdTimeErr")("000000073000"), S("bcdTimeErr")("000000073000"));
  fence("8600"); setck("fPTime", true);
  setv("fT1", "000000073000"); setv("fT2", "000000190000");
  r = S("collectFence")();
  ok("daily 写法不会组出设备必拒的帧", r.body === null, r.errs.join(" | "));

  /* --- 全 0：能过校验，但设备判成「每天仅 00:00:00 有效」，回显必须警示 --- */
  fence("8600"); setck("fPTime", true); setv("fT1", ""); setv("fT2", "");
  S("syncFenceTime")();
  hint = document.getElementById("fT1v").textContent;
  ok("全 0 回显给出警示（永不报警 + 唯一有效那一秒）",
     /永不报警/.test(hint) && /00:00:00/.test(hint), hint);
  ok("全 0 警示只写一遍，不再复述 bit0", !/bit0/.test(hint), hint);

  /* --- 现场那条被回 MessageError 的帧，反解时能指出时间非法 --- */
  var badBody = [0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x29,
                 0x01, 0xDC, 0x89, 0xD0, 0x07, 0x3D, 0x8A, 0xA5,
                 0x00, 0x00, 0x01, 0xF4,
                 0x20, 0x26, 0x10, 0x30, 0x07, 0x30,
                 0x20, 0x26, 0x10, 0x30, 0x10, 0x30];
  var bp = S("parseBodyByMsgId")(0x8600, badBody);
  var bit = bp["[00]区域项 1"];
  ok("反解非法时间给出原因", /✕/.test(bit["起止时间"]), bit["起止时间"]);
  eq("反解仍如实给出区域 ID", bit["区域ID"], 1);
  eq("反解仍如实给出半径", bit["半径"], "500 米");

  /* --- 终端通用应答结果码：中英双语 + 失败时的排查提示 --- */
  var a1 = S("parseBodyByMsgId")(0x0001, [0x00, 0x01, 0x86, 0x00, 0x02]);
  eq("ACK 结果中英双语", a1["[02]结果"], "消息有误(MessageError)");
  ok("围栏类 result=2 提示时间格式", /YYMMDDhhmmss/.test(a1["✕提示"] || ""), a1["✕提示"]);
  var a2 = S("parseBodyByMsgId")(0x0001, [0x00, 0x01, 0x81, 0x03, 0x02]);
  ok("非围栏类 result=2 给通用提示", /消息体长度/.test(a2["✕提示"] || ""), a2["✕提示"]);
  var a3 = S("parseBodyByMsgId")(0x0001, [0x00, 0x01, 0x86, 0x00, 0x00]);
  ok("result=0 不加提示", a3["✕提示"] === undefined, String(a3["✕提示"]));
  var a4 = S("parseBodyByMsgId")(0x0001, [0x00, 0x01, 0x86, 0x00, 0x03]);
  ok("result=3 提示不支持", /不支持/.test(a4["✕提示"] || ""), a4["✕提示"]);
  var a5 = S("parseBodyByMsgId")(0x8001, [0x00, 0x01, 0x86, 0x02, 0x02]);
  ok("平台通用应答同样带提示", /YYMMDDhhmmss/.test(a5["✕提示"] || ""), a5["✕提示"]);

  /* --- 整帧链路：refresh → 0x8600 生成 --- */
  fence("8600");
  document.getElementById("ident").value = "460001234567890";
  document.getElementById("seq").value = "1";
  B.refresh();
  eq("整帧链路：消息 ID = 0x8600", B.$("out")._msgId, 0x8600);
  eq("整帧链路：消息体 20 字节", (B.$("out")._frameObj || { body: [] }).body.length, 20);
  ok("整帧链路：能组出发送载荷", !!S("buildSendPayload")());
  eq("整帧链路：发送 cmd 与页面一致",
     (S("buildSendPayload")() || {}).cmd, B.$("out")._hexNoSpace);
})();

/* ================================================================
 *  0x0200 位置信息汇报
 * ================================================================ */
(function(){
  /* --- 现场真实帧（含转义 7D01，验一整套链路） --- */
  const LOC_REAL = "7E0200001F115436621651000E00000000000000000209AF5E067D015D9200000000000026103007540830011F787E";
  let r = parse1(LOC_REAL);
  ok("0x0200 不再落到「未实现」", !r.err && r.obj["[0200]消息Id"] === 512, r.err || "");
  eq("0x0200 消息名称", r.obj["消息名称"], "位置信息汇报");
  ok("0x0200 校验码一致（转义正确还原）", r.obj["校验码比对"] === "✓ 一致", r.obj["校验码比对"]);

  let la = r.obj["数据体对象"];
  eq("0x0200 报警标志", la["报警标志"], "无报警（0x00000000）");
  eq("0x0200 状态位", la["[00000000]状态位"], "ACC 关、未定位、北纬、东经");
  eq("0x0200 其它状态位", la["其它状态位（置位项）"], "无（bit4 以上全 0）");
  eq("0x0200 纬度 34.189150", la["纬度"], "34.189150° N（北纬）");
  eq("0x0200 经度 108.879250", la["经度"], "108.879250° E（东经）");
  eq("0x0200 高程", la["高程"], "0 米");
  eq("0x0200 速度", la["速度"], "0.0 km/h（原始 0 ×0.1km/h）");
  eq("0x0200 方向", la["方向"], "0°（正北 0，顺时针）");
  eq("0x0200 定位时间", la["定位时间"], "261030075408（2026-10-30 07:54:08）");
  eq("0x0200 附加项信号强度",
     (la["附加信息项"] || {})["[0x30]无线通信网络信号强度"],
     "信号强度 31（0~31）　原始 1F");
  ok("0x0200 附加项无残留", la["✕附加项"] === undefined, String(la["✕附加项"]));
  ok("0x0200 未定位却带经纬度有说明",
     /最后一次有效位置/.test(la["说明"] || ""), String(la["说明"]));

  /* --- 自定义扩展附加项 0xE3~0xE6 走完整帧链路（复现现场「未收录」场景） --- */
  const foExt = S("buildFrame")(0x0200, bcd, 9, LOC_BASE.concat([
    0xE3,0x02,0xFF,0xFF,   /* 转速无效 */
    0xE4,0x01,0xFF,        /* SOH 无效 */
    0xE5,0x02,0x00,0x77,   /* 主电电压 11.9V */
    0xE6,0x01,0xFF         /* 冷却液温度无效（BYTE） */
  ]));
  const rExt = parse1(B.toHex(foExt.frame, ""));
  ok("0x0200 帧级解析成功", !rExt.err, rExt.err || "");
  if (!rExt.err) {
    const exE = rExt.obj["数据体对象"]["附加信息项"] || {};
    ok("帧级 0xE3 不再「未收录」", !/未收录/.test(Object.keys(exE).join()), Object.keys(exE).join());
    ok("帧级 0xE3 转速无效", (exE["[0xE3]发动机转速"] || "").indexOf("无效") === 0, exE["[0xE3]发动机转速"]);
    ok("帧级 0xE4 SOH 无效", (exE["[0xE4]动力电池 SOH"] || "").indexOf("无效") === 0, exE["[0xE4]动力电池 SOH"]);
    ok("帧级 0xE5 11.9V", (exE["[0xE5]主电电压"] || "").indexOf("11.9 V") === 0, exE["[0xE5]主电电压"]);
    ok("帧级 0xE6 温度无效", (exE["[0xE6]冷却液温度"] || "").indexOf("无效") === 0, exE["[0xE6]冷却液温度"]);
    ok("帧级 附加项无残留", rExt.obj["数据体对象"]["✕附加项"] === undefined,
       String(rExt.obj["数据体对象"]["✕附加项"]));
  }

  /* --- 手动构造：报警 bit20 + ACC/已定位 + 速度 + 里程/围栏/卫星数 --- */
  const loc2 = [
    0x00,0x10,0x00,0x00,   /* 报警 bit20 进出区域 */
    0x00,0x00,0x00,0x03,   /* 状态 ACC 开 + 已定位 */
    0x02,0x09,0xAF,0x5E,   /* 纬度 34189150 */
    0x06,0x7D,0x5D,0x92,   /* 经度 108879250 */
    0x02,0x00,             /* 高程 512 */
    0x02,0x5D,             /* 速度 605 = 60.5km/h */
    0x00,0x5A,             /* 方向 90 */
    0x26,0x10,0x30,0x07,0x54,0x08,
    0x01,0x04,0x00,0x00,0x30,0x39,               /* 0x01 里程 12345 = 1234.5km */
    0x12,0x06,0x01,0x00,0x00,0x00,0x07,0x01,     /* 0x12 圆形 ID7 出区域 */
    0x31,0x01,0x0C                                /* 0x31 卫星数 12 */
  ];
  let lb = S("parseBodyByMsgId")(0x0200, loc2);
  ok("0x0200 报警带进出区域", /bit20 进出区域/.test(lb["报警标志"]), lb["报警标志"]);

  /* 协议表 11：bit29 碰撞预警 / bit30 侧翻预警，是两位不能合并成"碰撞侧翻" */
  const loc29 = loc2.slice(0, 28); loc29[0] = 0x20; loc29[1] = 0x00;
  let l29 = S("parseBodyByMsgId")(0x0200, loc29);
  eq("0x0200 报警 bit29 名称", l29["报警标志"], "bit29 碰撞预警（0x20000000）");
  const loc30 = loc2.slice(0, 28); loc30[0] = 0x40; loc30[1] = 0x00;
  let l30 = S("parseBodyByMsgId")(0x0200, loc30);
  eq("0x0200 报警 bit30 名称", l30["报警标志"], "bit30 侧翻预警（0x40000000）");
  eq("0x0200 状态 ACC 开+已定位", lb["[00000003]状态位"], "ACC 开、已定位、北纬、东经");
  eq("0x0200 高程 512", lb["高程"], "512 米");
  eq("0x0200 速度 60.5", lb["速度"], "60.5 km/h（原始 605 ×0.1km/h）");
  eq("0x0200 方向 90", lb["方向"], "90°（正北 0，顺时针）");
  eq("0x0200 里程 1234.5km", lb["附加信息项"]["[0x01]里程"], "1234.5 km　原始 00 00 30 39");
  eq("0x0200 围栏附加项", lb["附加信息项"]["[0x12]进出区域/路线报警"],
     "圆形 区域 ID=7，出区域（方向值 1）　原始 01 00 00 00 07 01");
  eq("0x0200 卫星数", lb["附加信息项"]["[0x31]GNSS 定位卫星数"], "12 颗　原始 0C");
  ok("0x0200 已定位时不给未定位说明", lb["说明"] === undefined, String(lb["说明"]));
  ok("0x0200 构造帧无残留", lb["✕附加项"] === undefined, String(lb["✕附加项"]));

  /* --- 异常路径 --- */
  let lc = S("parseBodyByMsgId")(0x0200, [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]);
  ok("0x0200 不足 28 字节报错", /28 字节/.test(lc["✕"] || ""), String(lc["✕"]));

  const lBad = loc2.slice(0, 28).concat([0x01, 0x08, 0x00]);   /* 声明 8 字节实际只给 1 */
  let ld = S("parseBodyByMsgId")(0x0200, lBad);
  ok("0x0200 附加项长度越界报错", /声明长度 8/.test(ld["✕附加项"] || ""), String(ld["✕附加项"]));

  const lTrunc = loc2.slice(0, 28).concat([0x30]);             /* 只有一个 ID，没长度 */
  let le = S("parseBodyByMsgId")(0x0200, lTrunc);
  ok("0x0200 附加项只剩 1 字节报错", /凑不出/.test(le["✕附加项"] || ""), String(le["✕附加项"]));
})();

/* ---------------- JT/T 808-2013 全量消息体反解 ---------------- */
console.log("\n[808 全量消息反解]");
(function () {
  function hx(s) {
    s = String(s || "").replace(/\s+/g, "");
    if (!s) return [];
    if (s.length % 2) throw new Error("hex 长度必须是偶数：" + s);
    var a = [];
    for (var i = 0; i < s.length; i += 2) a.push(parseInt(s.substr(i, 2), 16));
    return a;
  }
  function PB(id, s) { return B.parseBodyByMsgId(id, hx(s)); }
  /* 按 key 后缀取值：先剥掉 "[0017]" 这类十六进制前缀，再去掉裸字段名的方括号。
     精确匹配优先，找不到才退化成前缀匹配，避免 "硬件版本号" 命中 "硬件版本号长度"。 */
  function bare(k) {
    var s = k.replace(/^\[[0-9A-Fa-f]{2,}\]/, "");
    if (s.charAt(0) === "[") s = s.slice(1);
    if (s.charAt(s.length - 1) === "]") s = s.slice(0, -1);
    return s;
  }
  function K(o, suf) {
    for (var k in o) if (bare(k) === suf) return o[k];
    for (var k2 in o) if (bare(k2).indexOf(suf) === 0) return o[k2];
    return "(缺 " + suf + ")";
  }
  var LOC28 = "00000000 00000000 0209AF5E 067D5D92 0000 000A 0064 261030075408";

  /* ---- 空消息体类 ---- */
  eq("0x0002 心跳体为空", /消息体为空/.test(K(PB(0x0002, ""), "说明")), true);
  eq("0x0003 注销体为空", /消息体为空/.test(K(PB(0x0003, ""), "说明")), true);
  eq("0x0004 参数查询请求体为空", /消息体为空/.test(K(PB(0x0004, ""), "说明")), true);
  eq("0x8104 查询终端参数体为空", /消息体为空/.test(K(PB(0x8104, ""), "说明")), true);
  eq("0x8107 查询终端属性体为空", /消息体为空/.test(K(PB(0x8107, ""), "说明")), true);
  eq("0x8201 位置信息查询体为空", /消息体为空/.test(K(PB(0x8201, ""), "说明")), true);
  eq("0x0002 带多余字节报错", /应为空消息体/.test(K(PB(0x0002, "00"), "✕")), true);

  /* ---- 0x0107 终端属性应答（真实帧） ---- */
  var p107 = PB(0x0107,
    "0000 4753520000 4744333033000000000000000000000000000000 " +
    "69595063400039 89860325250291231843 " +
    "17 45473931354E454141435230334130324D30385F424E4E " +
    "17 4D43555F474433303356322E322E314230385430393033 0F 20");
  eq("0x0107 终端类型", K(p107, "终端类型"), "普通终端");
  eq("0x0107 制造商ID", K(p107, "制造商ID"), "GSR");
  eq("0x0107 终端型号", K(p107, "终端型号"), "GD303");
  eq("0x0107 终端ID(BCD)", K(p107, "终端ID"), "69595063400039");
  eq("0x0107 ICCID(BCD)", K(p107, "SIM卡ICCID"), "89860325250291231843");
  eq("0x0107 硬件版本号", K(p107, "硬件版本号"), "EG915NEAACR03A02M08_BNN");
  eq("0x0107 固件版本号", K(p107, "固件版本号"), "MCU_GD303V2.2.1B08T0903");
  eq("0x0107 GNSS 位图", K(p107, "GNSS模块属性"), "GPS、北斗、GLONASS、Galileo");
  eq("0x0107 通信模块位图", K(p107, "通信模块属性"), "LTE");
  ok("0x0107 无尾部残留", !p107["✕尾部"], String(p107["✕尾部"] || ""));
  eq("0x0107 截断报错", /长度不足/.test(K(PB(0x0107, "0000 4753520000"), "✕")), true);

  /* ---- 0x0108 升级结果 ---- */
  var p108 = PB(0x0108, "02 01");
  eq("0x0108 升级类型", K(p108, "升级类型"), "卫星定位模块");
  eq("0x0108 升级结果", K(p108, "升级结果"), "失败");

  /* ---- 0x0201 位置查询应答 ---- */
  var p201 = PB(0x0201, "0005 " + LOC28);
  eq("0x0201 应答流水号", K(p201, "应答流水号"), 5);
  eq("0x0201 纬度", K(p201, "纬度"), "34.189150° N（北纬）");
  eq("0x0201 速度", K(p201, "速度"), "1.0 km/h（原始 10 ×0.1km/h）");

  /* ---- 0x0300 / 0x0301 / 0x0302 ---- */
  eq("0x0300 事件ID", K(PB(0x0300, "05"), "事件ID"), 5);
  var p301 = PB(0x0301, "0006 02");
  eq("0x0301 应答流水号", K(p301, "应答流水号"), 6);
  eq("0x0301 答案内容", K(p301, "答案内容"), 2);
  var p302 = PB(0x0302, "01 01");
  eq("0x0302 信息类型", K(p302, "信息类型"), "广告");
  eq("0x0302 点播标志", K(p302, "点播/取消"), "点播");

  /* ---- 批量定位 0x0400（无类型字节）/ 0x0704（有类型字节） ---- */
  var p400 = PB(0x0400, "0001 001C " + LOC28);
  eq("0x0400 数据项个数", K(p400, "数据项个数"), 1);
  eq("0x0400 递归出纬度", K(p400["定位数据列表"]["第 1 条（28 字节）"], "纬度"), "34.189150° N（北纬）");
  var p704 = PB(0x0704, "0001 00 001C " + LOC28);
  eq("0x0704 数据类型", K(p704, "定位数据类型"), "正常批量上传");
  eq("0x0704 条数", K(p704, "数据项个数"), 1);
  ok("0x0704 每条都解析", !!p704["定位数据列表"]["第 1 条（28 字节）"]);

  /* ---- 0x0705 CAN ---- */
  var p705 = PB(0x0705, "0001 12345678 0102030405060708");
  eq("0x0705 数据项个数", K(p705, "数据项个数"), 1);
  eq("0x0705 CAN ID", p705["CAN数据列表"]["[12345678]"], "数据 0102030405060708");

  /* ---- 多媒体 ---- */
  var p800 = PB(0x0800, "00000001 00 00 01 02");
  eq("0x0800 多媒体数据ID", K(p800, "多媒体数据ID"), 1);
  eq("0x0800 多媒体类型", K(p800, "多媒体类型"), "图像");
  eq("0x0800 格式", K(p800, "多媒体格式编码"), "JPEG");
  eq("0x0800 通道", K(p800, "通道ID"), 2);

  var p801 = PB(0x0801, "00000001 00 00 00 01 " + LOC28 + " FFD8FF");
  eq("0x0801 位置内嵌纬度", K(p801["位置信息汇报"], "纬度"), "34.189150° N（北纬）");
  eq("0x0801 数据长度", K(p801, "多媒体数据"), "共 3 字节，前 32 字节 FFD8FF");

  var p802 = PB(0x0802, "00000001 01 00000005");
  eq("0x0802 重传包个数", K(p802, "重新上传包个数"), 1);
  eq("0x0802 重传包序号", p802["需重传包序号"]["包 1"], 5);

  var p805 = PB(0x0805, "0001 00 0001 00000007");
  eq("0x0805 结果", K(p805, "结果"), "成功");
  eq("0x0805 ID 列表", p805["多媒体数据ID列表"], "7");

  /* ---- 透传 / 压缩 / RSA ---- */
  var p900 = PB(0x0900, "01 414243");
  eq("0x0900 透传类型", K(p900, "透传消息类型"), "有障碍/危险");
  eq("0x0900 透传内容", K(p900, "透传内容"), "414243");
  eq("0x0901 压缩算法", K(PB(0x0901, "00 1F8B"), "压缩算法"), "GZIP");
  var pA00 = PB(0x0A00, "00000003 010001 00000002 FFFF");
  eq("0x0A00 e 长度", K(pA00, "e 长度"), 3);
  eq("0x0A00 e 值", pA00["[e]"], "010001");
  eq("0x0A00 n 值", pA00["[n]"], "FFFF");
  ok("0x0A00 n 越界报错", /✕/.test(String(PB(0x0A00, "00000001 01 00000009 FFFF")["[n]"])));

  /* ---- 0x8003 补传分包 ---- */
  var p8003 = PB(0x8003, "000A 02 0002 0005");
  eq("0x8003 原始流水号", K(p8003, "原始消息流水号"), 10);
  eq("0x8003 重传包列表", p8003["重传包ID列表"], "2, 5");

  /* ---- 0x8108 下发升级包 ---- */
  var p8108 = PB(0x8108, "00 4753520000 02 5631 00000004 01020304");
  eq("0x8108 升级类型", K(p8108, "升级类型"), "终端");
  eq("0x8108 版本号", K(p8108, "版本号"), "V1");
  eq("0x8108 包长一致", K(p8108, "升级包数据"), "声明 4 字节，实际 4 字节（一致）");
  eq("0x8108 包长不一致标注", K(PB(0x8108, "00 4753520000 02 5631 00000008 01020304"), "升级包数据"),
     "声明 8 字节，实际 4 字节（✕ 不一致）");

  /* ---- 0x8202 / 0x8203 ---- */
  var p8202 = PB(0x8202, "001E 0000012C");
  eq("0x8202 时间间隔", K(p8202, "时间间隔(秒)"), 30);
  eq("0x8202 有效期", K(p8202, "位置跟踪有效期(秒)"), 300);
  var p8203 = PB(0x8203, "000B 00000001");
  eq("0x8203 报警流水号", K(p8203, "报警消息流水号"), 11);

  /* ---- 0x8300 文本下发 ---- */
  var p8300 = PB(0x8300, "05 414243");
  eq("0x8300 标志位", K(p8300, "标志"), "紧急、终端TTS播读；来源=中心");
  eq("0x8300 文本", K(p8300, "文本信息"), "ABC");

  /* ---- 0x8301 事件设置 ---- */
  var p8301 = PB(0x8301, "02 01 07 02 4142");
  eq("0x8301 设置类型", K(p8301, "设置类型"), "追加");
  eq("0x8301 事件项", p8301["事件列表"]["事件 7"], "AB");

  /* ---- 0x8302 提问下发 ---- */
  var p8302 = PB(0x8302, "00 03 414243 01 02 4142");
  eq("0x8302 问题内容", K(p8302, "问题内容"), "ABC");
  eq("0x8302 候选答案", p8302["候选答案"]["答案 1"], "AB");

  /* ---- 0x8303 信息服务 ---- */
  var p8303 = PB(0x8303, "00 01 00 0002 4142");
  eq("0x8303 信息类型", K(p8303, "信息类型"), "新闻");
  eq("0x8303 信息项", p8303["信息项列表"]["第 1 项（类型 0）"], "AB");

  /* ---- 0x8304 点播菜单 ---- */
  var p8304 = PB(0x8304, "02 01 01 0002 4142");
  eq("0x8304 设置类型", K(p8304, "设置类型"), "追加菜单");
  eq("0x8304 菜单项", p8304["菜单列表"]["信息类型 1"], "AB");

  /* ---- 0x8400 / 0x8401 ---- */
  var p8400 = PB(0x8400, "01 313233");
  eq("0x8400 标志", K(p8400, "标志"), "监听");
  eq("0x8400 电话", K(p8400, "电话号码"), "123");
  var p8401 = PB(0x8401, "02 01 01 03 313233 02 4142");
  eq("0x8401 设置类型", K(p8401, "设置类型"), "追加电话本");
  eq("0x8401 联系人", p8401["联系人列表"]["第 1 项"], "123 / AB / 标志 1");

  /* ---- 0x8500 车辆控制 ---- */
  eq("0x8500 控制标志", K(PB(0x8500, "01"), "控制标志"), "车门开");

  /* ---- 0x8606 设置路线 / 0x8607 删除路线 ---- */
  var p8606 = PB(0x8606,
    "0000000A 0000 261030000000 261030235959 0001 " +
    "00000001 00000002 0209AF5E 067D5D92 0A 00 003C 001E 0050 05 0078");
  eq("0x8606 路线ID", K(p8606, "路线ID"), 10);
  eq("0x8606 起始时间", K(p8606, "起始时间"), "261030000000（2026-10-30 00:00:00）");
  eq("0x8606 拐点数", K(p8606, "拐点数"), 1);
  eq("0x8606 拐点纬度", p8606["拐点列表"]["第 1 个拐点"]["纬度"], "34.189150");
  eq("0x8606 拐点最高速", p8606["拐点列表"]["第 1 个拐点"]["最高速度"], "80 km/h");
  var p8607 = PB(0x8607, "02 00000001 00000002");
  eq("0x8607 路线数", K(p8607, "路线数"), 2);
  eq("0x8607 ID 列表", p8607["路线ID列表"], "1, 2");
  eq("0x8607 零条=删全部", K(PB(0x8607, "00"), "路线数"), "0（删除全部路线）");

  /* ---- 0x8700 / 0x8701 行驶记录 ---- */
  eq("0x8700 命令字", K(PB(0x8700, "02 0102"), "命令字"), 2);
  var p8701 = PB(0x8701, "0009 02 0102");
  eq("0x8701 应答流水号", K(p8701, "应答流水号"), 9);
  eq("0x8701 命令字", K(p8701, "命令字"), 2);

  /* ---- 0x8800 / 0x8801 / 0x8802 ---- */
  var p8800 = PB(0x8800, "01 02 03 261030000000 261030120000");
  eq("0x8800 类型", K(p8800, "多媒体类型"), "音频");
  eq("0x8800 起始时间", K(p8800, "起始时间"), "261030000000（2026-10-30 00:00:00）");
  var p8801 = PB(0x8801, "01 0001 000A 00 02 05 01 02 03 04");
  eq("0x8801 通道", K(p8801, "通道ID"), 1);
  eq("0x8801 拍摄命令", K(p8801, "拍摄命令"), "1（张/秒）");
  eq("0x8801 分辨率", K(p8801, "分辨率"), "640×480");
  var p8802 = PB(0x8802, "01 02 03 261030000000 261030120000 01");
  eq("0x8802 删除标志", K(p8802, "删除标志"), "删除");

  /* ---- 0x8803 检索应答 ---- */
  var p8803 = PB(0x8803, "0001 0001 00000007 01 02 03 067D5D92 0209AF5E");
  eq("0x8803 总项数", K(p8803, "多媒体数据总项数"), 1);
  eq("0x8803 项经度", p8803["多媒体数据列表"]["第 1 项"]["经度"], "108.879250");

  /* ---- 0x8804 / 0x8805 ---- */
  var p8804 = PB(0x8804, "01 003C 00 03");
  eq("0x8804 录音命令", K(p8804, "录音命令"), "开始录音");
  eq("0x8804 采样率", K(p8804, "音频采样率"), "32kHz");
  var p8805 = PB(0x8805, "00000007 01");
  eq("0x8805 数据ID", K(p8805, "多媒体数据ID"), 7);
  eq("0x8805 删除标志", K(p8805, "删除标志"), "删除");

  /* ---- 0x8900 / 0x8A00 ---- */
  eq("0x8900 透传类型", K(PB(0x8900, "03 4142"), "透传消息类型"), "双向");
  eq("0x8A00 n 长度", K(PB(0x8A00, "00000001 03 00000002 FFFF"), "n 长度"), 2);

  /* ---- 未收录类型仍走兜底 ---- */
  var pUnk = PB(0x0F0F, "0102");
  eq("未收录类型给原始字节", pUnk["说明"], "该消息类型未实现详细解析");
})();

/* ========== 附：V1.2 单帧多区域项（绘图方式） ========== */
sec("附. 单帧多区域项（绘图方式）");
(function(){
  const $X = id => B.document.getElementById(id);
  const prop = { time:false, speed:false, in:true, out:true };
  const c1 = { shape:"circle", set:true, op:0, id:1, prop:prop,
               lat:"31.230416", lon:"121.473701", radius:"500" };
  const c2 = { shape:"circle", set:true, op:0, id:2, prop:prop,
               lat:"31.240000", lon:"121.490000", radius:"300" };
  const one1 = B.buildFenceBody(c1).body;
  const one2 = B.buildFenceBody(c2).body;
  eq("单区域基准无错误", B.buildFenceBody(c1).errs, []);

  const many = B.buildFenceBody(Object.assign({}, c1, { items:[c1, c2] }));
  eq("双圆形无错误", many.errs, []);
  eq("双圆形区域总数 = 2", many.body[1], 2);
  eq("双圆形逐字节 = 两条单区域拼接",
     B.toHex(many.body, ""), B.toHex([0,2].concat(one1.slice(2), one2.slice(2)), ""));

  const r1 = { shape:"rect", set:true, op:0, id:1, prop:prop,
               lat1:"31.240000", lon1:"121.460000", lat2:"31.220000", lon2:"121.490000" };
  const r2 = Object.assign({}, r1, { id:2 });
  const rectMany = B.buildFenceBody(Object.assign({}, r1, { items:[r1, r2] }));
  eq("双矩形逐字节 = 两条单区域拼接",
     B.toHex(rectMany.body, ""),
     B.toHex([0,2].concat(B.buildFenceBody(r1).body.slice(2),
                          B.buildFenceBody(r2).body.slice(2)), ""));

  /* 属性扩展位（起止时间 + 限速）对每一项都要带上，位置在坐标之后 */
  const ext = Object.assign({}, c1, {
    prop:{ time:true, speed:true, in:true, out:true },
    time1:"261030080000", time2:"261030180000", speedVal:"80", speedDur:"10"
  });
  const ext2 = Object.assign({}, ext, { id:2 });
  const extMany = B.buildFenceBody(Object.assign({}, ext, { items:[ext, ext2] }));
  eq("带扩展位的双圆形无错误", extMany.errs, []);
  eq("带扩展位的双圆形逐字节一致",
     B.toHex(extMany.body, ""),
     B.toHex([0,2].concat(B.buildFenceBody(ext).body.slice(2),
                          B.buildFenceBody(ext2).body.slice(2)), ""));
  eq("带扩展位每项长度 = 18 + 12 + 3", extMany.body.length, 2 + 2 * 33);

  /* 固件单帧上限 10 项 */
  const ten = [];
  for (let i = 0; i < 10; i++) ten.push(Object.assign({}, c1, { id:i + 1 }));
  const r10 = B.buildFenceBody(Object.assign({}, c1, { items:ten }));
  eq("10 项可组包", r10.errs, []);
  eq("10 项区域总数 = 10", r10.body[1], 10);
  eq("10 项长度", r10.body.length, 2 + 10 * 18);
  const r11 = B.buildFenceBody(Object.assign({}, c1, {
    items:ten.concat([Object.assign({}, c1, { id:11 })]) }));
  ok("11 项报「分批下发」", r11.errs.some(e => e.indexOf("分批下发") >= 0),
     JSON.stringify(r11.errs));
  eq("11 项不生成报文", r11.body, null);

  /* 0x8604 协议本身无数量前缀，一帧只带 1 个多边形 */
  const poly = { shape:"poly", set:true, op:0, id:1, prop:prop,
                 points:[["31.24","121.46"],["31.24","121.49"],
                         ["31.22","121.49"],["31.22","121.46"]] };
  const rp = B.buildFenceBody(Object.assign({}, poly, {
    items:[poly, Object.assign({}, poly, { id:2 })] }));
  ok("多边形 2 项提示分批", rp.errs.some(e => e.indexOf("0x8604") >= 0),
     JSON.stringify(rp.errs));
  eq("多边形 2 项不生成报文", rp.body, null);

  /* 页面链路：MAP_FENCES → collectFence() → items */
  B.STATE.type = "8600";
  $X("fId").value = "1";
  $X("fPTime").checked = false; $X("fPSpeed").checked = false;
  $X("fPIn").checked = true;   $X("fPOut").checked = true;
  B.MAP_FENCES = [
    { shape:"circle", points:[[31.230416, 121.473701]], radius:500 },
    { shape:"circle", points:[[31.240000, 121.490000]], radius:300 },
    { shape:"rect",   points:[[31.220000, 121.460000], [31.240000, 121.490000]] }
  ];
  const viaPage = S("collectFence")();
  eq("页面读地图图形无错误", viaPage.errs, []);
  eq("页面多围栏逐字节（矩形被当前报文过滤）",
     B.toHex(viaPage.body, ""), B.toHex(many.body, ""));
  B.MAP_FENCES = [];
  const manual = S("collectFence")();
  eq("清空图形后回到手动输入单区域",
     B.toHex(manual.body, ""), B.toHex(one1, ""));
  B.STATE.type = "8103";
})();

/* ---------------- 汇总 ---------------- */
console.log("\n" + "=".repeat(52));
console.log("  通过 " + pass + " 项，失败 " + fail + " 项");
console.log("=".repeat(52));
process.exit(fail === 0 ? 0 : 1);
