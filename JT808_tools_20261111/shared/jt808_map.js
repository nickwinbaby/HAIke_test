/* ============================================================
 * JT808 平台 / 离线工具共用：地图、围栏绘制、地点搜索
 *
 *  依赖 Leaflet（页面自行引入 leaflet.css / leaflet.js）。
 *  本文件只定义函数，不在加载时碰 DOM / L，node 自测可直接 require。
 *
 *  两层用法：
 *    1) 纯函数：GCJ、haversine、fmtDist、searchPlace、srchBind
 *    2) 地图实例：JT808Map.create({ el, tipEl, hintEl, buttons, onAdd })
 *       —— 绘制完成通过 onAdd({ shape, points(WGS84), radius }) 交给调用方，
 *          平台侧存后端，离线侧存本地数组，模块本身不落库。
 *
 *  坐标约定：存储/报文一律 WGS84，贴到高德底图前转 GCJ-02。
 * ============================================================ */
(function (root) {
"use strict";

/* ---------- 一、WGS84 <-> GCJ-02 ---------- */
var GCJ = (function () {
  var A = 6378245.0, EE = 0.00669342162296594323;

  function outOfChina(lat, lon) {
    return !(lon > 73.66 && lon < 135.05 && lat > 3.86 && lat < 53.55);
  }
  function tLat(x, y) {
    var r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    r += (20 * Math.sin(y * Math.PI) + 40 * Math.sin(y / 3 * Math.PI)) * 2 / 3;
    r += (160 * Math.sin(y / 12 * Math.PI) + 320 * Math.sin(y * Math.PI / 30)) * 2 / 3;
    return r;
  }
  function tLon(x, y) {
    var r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    r += (20 * Math.sin(x * Math.PI) + 40 * Math.sin(x / 3 * Math.PI)) * 2 / 3;
    r += (150 * Math.sin(x / 12 * Math.PI) + 300 * Math.sin(x / 30 * Math.PI)) * 2 / 3;
    return r;
  }
  function wgs2gcj(lat, lon) {
    if (outOfChina(lat, lon)) return [lat, lon];
    var dLat = tLat(lon - 105.0, lat - 35.0);
    var dLon = tLon(lon - 105.0, lat - 35.0);
    var radLat = lat / 180.0 * Math.PI;
    var magic = Math.sin(radLat);
    magic = 1 - EE * magic * magic;
    var sq = Math.sqrt(magic);
    dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sq) * Math.PI);
    dLon = (dLon * 180.0) / (A / sq * Math.cos(radLat) * Math.PI);
    return [lat + dLat, lon + dLon];
  }
  /* 反解：迭代逼近，5 次足够到亚米级 */
  function gcj2wgs(lat, lon) {
    if (outOfChina(lat, lon)) return [lat, lon];
    var wLat = lat, wLon = lon;
    for (var i = 0; i < 5; i++) {
      var g = wgs2gcj(wLat, wLon);
      wLat += lat - g[0];
      wLon += lon - g[1];
    }
    return [wLat, wLon];
  }
  return { wgs2gcj: wgs2gcj, gcj2wgs: gcj2wgs };
})();

var R_EARTH = 6371008.8;
function haversine(a1, o1, a2, o2) {
  var p1 = a1 * Math.PI / 180, p2 = a2 * Math.PI / 180;
  var dp = p2 - p1, dl = (o2 - o1) * Math.PI / 180;
  var x = Math.sin(dp / 2) * Math.sin(dp / 2) +
          Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
  return 2 * R_EARTH * Math.asin(Math.min(1, Math.sqrt(x)));
}
function fmtDist(m) {
  if (m == null) return "—";
  return m >= 1000 ? (m / 1000).toFixed(2) + " km" : Math.round(m) + " m";
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

/* ---------- 二、地点搜索（Photon，OSM 数据，免 key） ----------
 * 返回值是 WGS84，贴到高德底图前统一转 GCJ-02。
 */
var _srchToken = 0;
var _srchCache = {};

function searchPlace(kw) {
  kw = String(kw || "").trim();
  if (!kw) return Promise.resolve([]);
  if (_srchCache[kw]) return Promise.resolve(_srchCache[kw]);

  /* 纯经纬度直接当坐标用，不走网络：用户填的通常是 WGS84 */
  var m = /^\s*(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(kw);
  if (m) {
    var la = parseFloat(m[1]), lo = parseFloat(m[2]);
    if (la >= -90 && la <= 90 && lo >= -180 && lo <= 180) {
      var g = GCJ.wgs2gcj(la, lo);
      return Promise.resolve([{ name: "坐标 " + m[1] + ", " + m[2],
                                addr: "按输入的经纬度（WGS84）定位",
                                lat: g[0], lon: g[1] }]);
    }
  }

  var url = "https://photon.komoot.io/api/?limit=8&lang=default&q=" + encodeURIComponent(kw);
  return fetch(url).then(function (r) { return r.json(); }).then(function (j) {
    var out = [];
    (j && j.features || []).forEach(function (ft) {
      var g = ft.geometry && ft.geometry.coordinates;
      if (!g || g.length < 2) return;
      var p = ft.properties || {};
      var addr = [p.country, p.state, p.city, p.district, p.street]
        .filter(function (x, i, a) { return x && a.indexOf(x) === i; }).join(" ");
      var nm = p.name || p.street || addr || kw;
      if (nm === addr && addr) addr = p.county || "";
      var c = GCJ.wgs2gcj(g[1], g[0]);
      out.push({ name: nm, addr: addr, lat: c[0], lon: c[1] });
    });
    _srchCache[kw] = out;
    return out;
  }).catch(function () { return []; });
}

function srchRender(boxSel, items, onPick, emptyTxt) {
  var box = document.querySelector(boxSel);
  if (!box) return;
  if (!items.length) {
    box.innerHTML = '<div class="it"><span class="no">'
      + (emptyTxt || "没搜到，换个说法试试（也可直接输「纬度,经度」）") + "</span></div>";
    box.classList.add("show");
    return;
  }
  box.innerHTML = items.map(function (it, i) {
    return '<div class="it" data-i="' + i + '"><b>' + esc(it.name) + "</b>"
      + (it.addr ? '<span class="ad">' + esc(it.addr) + "</span>" : "") + "</div>";
  }).join("");
  box.classList.add("show");
  box.querySelectorAll(".it").forEach(function (el) {
    el.addEventListener("click", function () {
      var it = items[Number(el.getAttribute("data-i"))];
      box.classList.remove("show");
      onPick(it);
    });
  });
}

/* 输入防抖：避免每敲一个字就发一次请求 */
function srchBind(inputSel, boxSel, onPick, labelTxt) {
  var inp = document.querySelector(inputSel), box = document.querySelector(boxSel);
  if (!inp || !box) return;
  var t = 0;
  inp.addEventListener("input", function () {
    clearTimeout(t);
    var kw = inp.value.trim();
    if (!kw) { box.classList.remove("show"); return; }
    t = setTimeout(function () {
      box.innerHTML = '<div class="it"><span class="no">搜索中…</span></div>';
      box.classList.add("show");
      var tk = ++_srchToken;
      searchPlace(kw).then(function (items) {
        if (tk !== _srchToken) return;      /* 只认最后一次请求 */
        srchRender(boxSel, items, onPick, "没找到「" + kw + "」，试试更短的地名");
      });
    }, 320);
  });
  inp.addEventListener("keydown", function (e) {
    if (e.key === "Escape") box.classList.remove("show");
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest && !e.target.closest(".srch")) box.classList.remove("show");
  });
}

/* ---------- 三、围栏配色 / 形状 ---------- */
function fenceColor(f, sel) {
  if (sel) return "#f59e0b";
  if (f.shape === "circle") return "#2563eb";
  if (f.shape === "rect") return "#0f766e";
  return "#7c3aed";
}
function isPoly(s) { return s === "polygon" || s === "poly"; }

function toShape(f, sel) {
  var col = fenceColor(f, sel);
  var opts = { color: col, weight: sel ? 3 : 2, fillColor: col, fillOpacity: sel ? .18 : .1 };
  var pts = f.points || [];
  if (f.shape === "circle" && pts.length) {
    var c = GCJ.wgs2gcj(pts[0][0], pts[0][1]);
    return L.circle([c[0], c[1]], Object.assign({ radius: f.radius || 0 }, opts));
  }
  if (f.shape === "rect" && pts.length >= 2) {
    var a = GCJ.wgs2gcj(pts[0][0], pts[0][1]);
    var b = GCJ.wgs2gcj(pts[1][0], pts[1][1]);
    return L.rectangle(L.latLngBounds([a[0], a[1]], [b[0], b[1]]), opts);
  }
  if (isPoly(f.shape) && pts.length >= 3) {
    var ll = pts.map(function (p) {
      var g = GCJ.wgs2gcj(p[0], p[1]);
      return [g[0], g[1]];
    });
    return L.polygon(ll, opts);
  }
  return null;
}

function fencePoints(f) {
  var pts = f.points || [];
  return pts.map(function (p) {
    var g = GCJ.wgs2gcj(p[0], p[1]);
    return [g[0], g[1]];
  });
}

/* ---------- 四、地图实例 ----------
 * opts = {
 *   el:        地图容器 id
 *   tipEl:     提示条 id（可选）
 *   hintEl:    提示文字容器 id（可选）
 *   buttons:   { circle, rect, poly, stop } 按钮 id（可选）
 *   search:    { input, result, clear } 搜索控件 id（可选）
 *   onAdd:     绘制完成回调，收到 { shape, points, radius }（WGS84）
 *   toast:     搜索定位后的提示回调（可选）
 * }
 */
function create(opts) {
  opts = opts || {};
  var map = L.map(opts.el || "map", {
    center: [31.230416, 121.473701],
    zoom: 14,
    minZoom: 2,
    maxZoom: 18,
    zoomControl: false,
    scrollWheelZoom: true,
    /* 别加 maxBounds：缩到世界级别时会在平移与回弹之间无限抖动 */
    worldCopyJump: true,
    zoomSnap: 0.5,
    zoomDelta: 0.5,
    attributionControl: true
  });

  /* z1~z3 Esri 全球图，z4~z18 高德路网 */
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    { minZoom: 1, maxZoom: 3, className: "amap-tile", attribution: "低缩放底图 © Esri" }).addTo(map);

  var amap = L.tileLayer(
    "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
    { subdomains: ["1", "2", "3", "4"], minZoom: 4, maxZoom: 18, noWrap: false,
      className: "amap-tile", attribution: "底图 © 高德地图" });
  amap.addTo(map);
  amap.on("tileerror", function () {
    tip("底图瓦片加载失败——检查这台机器能不能访问外网（webrd0x.is.autonavi.com）", 6000);
  });

  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.scale({ position: "bottomleft", imperial: false, maxWidth: 130 }).addTo(map);

  var layerFence = L.layerGroup().addTo(map);
  var layerTrack = L.layerGroup().addTo(map);
  var layerDev   = L.layerGroup().addTo(map);
  var layerDraft = L.layerGroup().addTo(map);

  var tipEl  = opts.tipEl  ? document.getElementById(opts.tipEl)  : null;
  var hintEl = opts.hintEl ? document.getElementById(opts.hintEl) : null;
  var btns   = opts.buttons || {};
  var onAdd  = opts.onAdd || function () {};
  var toast  = opts.toast || function () {};

  var DRAW = null, POLY_PTS = [], draftShape = null, PICK_CB = null;

  function tip(msg, ms) {
    if (!tipEl) return;
    if (!msg) { tipEl.classList.remove("show"); return; }
    tipEl.textContent = msg;
    tipEl.classList.add("show");
    if (ms) setTimeout(function () { tipEl.classList.remove("show"); }, ms);
  }
  function hint(html) { if (hintEl) hintEl.innerHTML = html; }
  function btn(id) { return id ? document.getElementById(id) : null; }

  function setDrawMode(mode) {
    DRAW = mode;
    POLY_PTS = [];
    if (draftShape) { layerDraft.removeLayer(draftShape); draftShape = null; }
    ["circle", "rect", "poly"].forEach(function (k) {
      var b = btn(btns[k]);
      if (b) b.classList.remove("on");
    });
    var stop = btn(btns.stop);
    if (stop) stop.disabled = !mode;

    if (!mode) {
      map.dragging.enable();
      map.getContainer().style.cursor = "";
      tip("");
      hint('点上方「圆形 / 矩形 / 多边形」后在地图上绘制；可连续画多个。');
      return;
    }
    map.getContainer().style.cursor = "crosshair";
    var on = btn(btns[mode === "polygon" ? "poly" : mode]);
    if (on) on.classList.add("on");
    if (mode === "polygon") {
      hint('在地图上<b>逐点单击</b>加顶点，<b>双击</b>或点「停止」结束。至少 3 个点。');
    } else {
      hint('在地图上<b>按住拖拽</b>绘制' +
        (mode === "circle" ? "圆形：按下点是圆心，拖出的距离是半径" : "矩形：从一角拖到对角") +
        '。可连续画多个。');
    }
    tip(mode === "polygon" ? "单击加点，双击结束" : "按住并拖动", 3000);
  }

  var downLL = null;
  map.on("mousedown", function (e) {
    if (!DRAW || DRAW === "polygon") return;
    downLL = e.latlng;
    map.dragging.disable();
    if (draftShape) { layerDraft.removeLayer(draftShape); draftShape = null; }
  });
  map.on("mousemove", function (e) {
    if (!DRAW || DRAW === "polygon" || !downLL) return;
    if (draftShape) layerDraft.removeLayer(draftShape);
    if (DRAW === "circle") {
      var r = haversine(downLL.lat, downLL.lng, e.latlng.lat, e.latlng.lng);
      draftShape = L.circle(downLL, { radius: r, color: "#f59e0b", weight: 2,
        fillColor: "#f59e0b", fillOpacity: .13, className: "draw-preview" }).addTo(layerDraft);
      tip("半径 " + Math.round(r) + " 米", 0);
    } else {
      var b = L.latLngBounds(downLL, e.latlng);
      draftShape = L.rectangle(b, { color: "#f59e0b", weight: 2,
        fillColor: "#f59e0b", fillOpacity: .13, className: "draw-preview" }).addTo(layerDraft);
      tip("对角 " + fmtDist(haversine(downLL.lat, downLL.lng, e.latlng.lat, e.latlng.lng)), 0);
    }
  });
  map.on("mouseup", function (e) {
    if (!DRAW || DRAW === "polygon" || !downLL) return;
    map.dragging.enable();
    var start = downLL;
    downLL = null;
    if (DRAW === "circle") {
      var r = haversine(start.lat, start.lng, e.latlng.lat, e.latlng.lng);
      if (r < 5) { tip("半径太小，重新拖一次", 2000); return; }
      var w = GCJ.gcj2wgs(start.lat, start.lng);
      onAdd({ shape: "circle", points: [[w[0], w[1]]], radius: Math.round(r) });
    } else {
      var sw = GCJ.gcj2wgs(Math.min(start.lat, e.latlng.lat), Math.min(start.lng, e.latlng.lng));
      var ne = GCJ.gcj2wgs(Math.max(start.lat, e.latlng.lat), Math.max(start.lng, e.latlng.lng));
      if (haversine(sw[0], sw[1], ne[0], ne[1]) < 10) {
        tip("面积太小，重新拖一次", 2000); return;
      }
      onAdd({ shape: "rect", points: [[sw[0], sw[1]], [ne[0], ne[1]]] });
    }
    if (draftShape) { layerDraft.removeLayer(draftShape); draftShape = null; }
    tip("");
  });
  map.on("click", function (e) {
    if (PICK_CB) {
      var cb = PICK_CB;
      PICK_CB = null;
      map.getContainer().style.cursor = "";
      tip("");
      cb(e.latlng);
      return;
    }
    if (DRAW !== "polygon") return;
    POLY_PTS.push(e.latlng);
    if (draftShape) layerDraft.removeLayer(draftShape);
    if (POLY_PTS.length === 1) {
      draftShape = L.circleMarker(e.latlng, { radius: 5, color: "#f59e0b",
        fillColor: "#f59e0b", fillOpacity: 1 }).addTo(layerDraft);
    } else {
      draftShape = L.polygon(POLY_PTS, { color: "#f59e0b", weight: 2,
        fillColor: "#f59e0b", fillOpacity: .13, className: "draw-preview" }).addTo(layerDraft);
    }
    tip("已加 " + POLY_PTS.length + " 个点，双击结束（至少 3 个）", 0);
  });
  map.on("dblclick", function () {
    if (DRAW !== "polygon" || POLY_PTS.length < 3) return;
    finishPolygon();
  });

  function finishPolygon() {
    if (POLY_PTS.length < 3) { tip("至少 3 个点", 2000); return; }
    var wgs = POLY_PTS.map(function (p) {
      var w = GCJ.gcj2wgs(p.lat, p.lng);
      return [w[0], w[1]];
    });
    onAdd({ shape: "polygon", points: wgs });
    POLY_PTS = [];
    if (draftShape) { layerDraft.removeLayer(draftShape); draftShape = null; }
    tip("");
  }

  function pick(cb) {
    PICK_CB = cb;
    map.getContainer().style.cursor = "crosshair";
    tip("在地图上单击取点（Esc 取消）", 0);
  }
  function cancelPick() {
    PICK_CB = null;
    map.getContainer().style.cursor = "";
    tip("");
  }

  /* 在指定容器上画一批围栏，返回图层数组（WGS84 → GCJ-02） */
  function renderShapes(fences) {
    layerFence.clearLayers();
    var shapes = [];
    (fences || []).forEach(function (f, i) {
      var s = toShape(f, !!f.selected);
      if (!s) return;
      s.bindTooltip((i + 1) + " · " + (f.name || ("围栏 " + (f.id || (i + 1))))
        + (f.radius ? " · 半径 " + fmtDist(f.radius) : ""),
        { permanent: false, direction: "center", className: "ftip" });
      s.addTo(layerFence);
      shapes.push(s);
    });
    return shapes;
  }

  function fitFences(fences) {
    var pts = [];
    (fences || []).forEach(function (f) {
      pts = pts.concat(fencePoints(f));
    });
    if (!pts.length) return false;
    if (pts.length === 1) { map.setView(pts[0], 16); return true; }
    map.fitBounds(L.latLngBounds(pts).pad(0.25), { maxZoom: 17 });
    return true;
  }

  function bindSearch(cfg) {
    cfg = cfg || opts.search;
    if (!cfg || !cfg.input || !cfg.result) return;
    srchBind(cfg.input, cfg.result, function (it) {
      map.setView([it.lat, it.lon], 16);
      var inp = document.querySelector(cfg.input);
      if (inp) inp.value = it.name;
      toast("已定位到 " + it.name);
    });
    if (cfg.clear) {
      var clr = document.querySelector(cfg.clear);
      if (clr) clr.addEventListener("click", function () {
        var inp = document.querySelector(cfg.input);
        var box = document.querySelector(cfg.result);
        if (inp) inp.value = "";
        if (box) box.classList.remove("show");
      });
    }
  }
  if (opts.search) bindSearch(opts.search);

  return {
    map: map,
    layerFence: layerFence, layerTrack: layerTrack,
    layerDev: layerDev, layerDraft: layerDraft,
    setDrawMode: setDrawMode,
    finishPolygon: finishPolygon,
    getDrawMode: function () { return DRAW; },
    getPolyPts: function () { return POLY_PTS; },
    tip: tip, hint: hint,
    pick: pick, cancelPick: cancelPick,
    pickPending: function () { return !!PICK_CB; },
    invalidate: function () { map.invalidateSize(); },
    renderShapes: renderShapes,
    fitFences: fitFences,
    setView: function (ll, z) { map.setView(ll, z == null ? 16 : z); }
  };
}

root.JT808Map = {
  GCJ: GCJ,
  haversine: haversine,
  fmtDist: fmtDist,
  searchPlace: searchPlace,
  srchBind: srchBind,
  fenceColor: fenceColor,
  create: create
};

})(typeof window !== "undefined" ? window : this);
