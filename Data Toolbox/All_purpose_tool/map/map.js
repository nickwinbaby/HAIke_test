(function(){
"use strict";

L.Icon.Default.mergeOptions({
  iconRetinaUrl:"vendor/marker-icon-2x.png",
  iconUrl:"vendor/marker-icon.png",
  shadowUrl:"vendor/marker-shadow.png"
});

var params=new URLSearchParams(location.search),token=params.get("token")||"",pageMode=params.get("mode")||"all",requestedShape=params.get("shape")||"circle";
var markers=[],fences=[],referenceMarkers=[],tracks=[],seq=0,mode=null,downLL=null,draft=null,polyPts=[],showTrackNames=false,trackNameSize=12,hoverCoordTooltip=null;
var layerItems=L.layerGroup(),layerTracks=L.layerGroup(),layerDraft=L.layerGroup(),layerLocation=L.layerGroup();
var hint=document.getElementById("hint"),tipEl=document.getElementById("tip"),itemsEl=document.getElementById("items"),statusEl=document.getElementById("status");
var searchInput=document.getElementById("searchInput"),searchResults=document.getElementById("searchResults"),searchClear=document.getElementById("searchClear");
var searchItems=[],searchActive=-1,searchTimer=0,searchToken=0,searchCache={};

/* 默认中心以 WGS84 保存；显示到高德底图前统一转换为 GCJ-02。 */
var DEFAULT_CENTER_WGS84=[34.188178,108.878631];
var A=6378245.0,EE=0.00669342162296594323,R=6371008.8;
function outChina(lat,lon){return !(lon>73.66&&lon<135.05&&lat>3.86&&lat<53.55)}
function tLat(x,y){var r=-100+2*x+3*y+.2*y*y+.1*x*y+.2*Math.sqrt(Math.abs(x));r+=(20*Math.sin(6*x*Math.PI)+20*Math.sin(2*x*Math.PI))*2/3;r+=(20*Math.sin(y*Math.PI)+40*Math.sin(y/3*Math.PI))*2/3;r+=(160*Math.sin(y/12*Math.PI)+320*Math.sin(y*Math.PI/30))*2/3;return r}
function tLon(x,y){var r=300+x+2*y+.1*x*x+.1*x*y+.1*Math.sqrt(Math.abs(x));r+=(20*Math.sin(6*x*Math.PI)+20*Math.sin(2*x*Math.PI))*2/3;r+=(20*Math.sin(x*Math.PI)+40*Math.sin(x/3*Math.PI))*2/3;r+=(150*Math.sin(x/12*Math.PI)+300*Math.sin(x/30*Math.PI))*2/3;return r}
function wgs2gcj(lat,lon){if(outChina(lat,lon))return[lat,lon];var dl=tLat(lon-105,lat-35),dn=tLon(lon-105,lat-35),rad=lat/180*Math.PI,m=Math.sin(rad);m=1-EE*m*m;var sq=Math.sqrt(m);dl=dl*180/((A*(1-EE))/(m*sq)*Math.PI);dn=dn*180/(A/sq*Math.cos(rad)*Math.PI);return[lat+dl,lon+dn]}
function gcj2wgs(lat,lon){if(outChina(lat,lon))return[lat,lon];var la=lat,lo=lon;for(var i=0;i<5;i++){var g=wgs2gcj(la,lo);la+=lat-g[0];lo+=lon-g[1]}return[la,lo]}
function dist(a,b){var p1=a.lat*Math.PI/180,p2=b.lat*Math.PI/180,dp=p2-p1,dl=(b.lng-a.lng)*Math.PI/180;var x=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;return 2*R*Math.asin(Math.min(1,Math.sqrt(x)))}

var defaultCenterGcj=wgs2gcj(DEFAULT_CENTER_WGS84[0],DEFAULT_CENTER_WGS84[1]);
var map=L.map("map",{center:defaultCenterGcj,zoom:14,minZoom:2,maxZoom:18,zoomControl:false,worldCopyJump:true,zoomSnap:.5,zoomDelta:.5,doubleClickZoom:false});
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",{minZoom:1,maxZoom:3,attribution:"低缩放底图 © Esri"}).addTo(map);
var storedMapStyle=localStorage.getItem("gnss-map-style"),mapStyle=storedMapStyle==="7"||storedMapStyle==="satellite"?storedMapStyle:"8";
function createAmapLayer(style){if(style==="satellite")return L.tileLayer("https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",{subdomains:["1","2","3","4"],minZoom:4,maxZoom:18,attribution:"卫星影像 © 高德地图"});return L.tileLayer("https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style="+style+"&x={x}&y={y}&z={z}",{subdomains:["1","2","3","4"],minZoom:4,maxZoom:18,attribution:"底图 © 高德地图"})}
var amapLayer=createAmapLayer(mapStyle).addTo(map);
L.control.zoom({position:"bottomright"}).addTo(map);L.control.scale({position:"bottomleft",imperial:false,maxWidth:130}).addTo(map);
layerItems.addTo(map);layerTracks.addTo(map);layerDraft.addTo(map);layerLocation.addTo(map);

function f6(v){return Number(v).toFixed(6)}
function showTip(text,ms){tipEl.textContent=text||"";tipEl.classList.toggle("show",!!text);if(ms)setTimeout(function(){tipEl.classList.remove("show")},ms)}
var confirmDialog=document.getElementById("confirmDialog"),confirmOkButton=document.getElementById("confirmOkButton"),confirmResolve=null;
function askConfirm(){return new Promise(function(resolve){confirmResolve=resolve;confirmDialog.classList.add("show");confirmOkButton.focus()})}
function closeConfirm(value){if(!confirmDialog.classList.contains("show"))return;confirmDialog.classList.remove("show");var resolve=confirmResolve;confirmResolve=null;if(resolve)resolve(value)}
confirmDialog.querySelectorAll('[data-confirm-action="cancel"]').forEach(function(button){button.onclick=function(){closeConfirm(false)}});confirmOkButton.onclick=function(){closeConfirm(true)};document.addEventListener("keydown",function(event){if(event.key==="Escape"&&confirmDialog.classList.contains("show")){event.preventDefault();closeConfirm(false)}});
function clearDraft(){layerDraft.clearLayers();draft=null;downLL=null;polyPts=[]}
function pointIcon(index){return L.divIcon({className:"point-div-icon",html:'<div class="map-pin"><span>'+index+'</span></div>',iconSize:[34,42],iconAnchor:[17,39],tooltipAnchor:[0,-35]})}
function currentIcon(){return L.divIcon({className:"current-div-icon",html:'<div class="current-dot"></div>',iconSize:[28,28],iconAnchor:[14,14],tooltipAnchor:[0,-18]})}
function referenceIcon(){return L.divIcon({className:"reference-div-icon",html:'<div class="reference-pin"></div>',iconSize:[28,34],iconAnchor:[14,32],popupAnchor:[0,-29],tooltipAnchor:[0,-29]})}
var TRACK_COLORS=["#e11d48","#2563eb","#059669","#7c3aed","#ea580c","#0891b2","#ca8a04"];
function xmlChildren(node,name){return Array.from(node.getElementsByTagNameNS("*",name))}
function firstXmlText(node,name){var found=xmlChildren(node,name)[0];return found?found.textContent.trim():""}
function parseCoordinateText(text){var points=[];String(text||"").trim().split(/\s+/).forEach(function(item){var values=item.split(",");if(values.length<2)return;var lon=Number(values[0]),lat=Number(values[1]);if(Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180)points.push([lat,lon])});return points}
function plainKmlText(text){var value=String(text||"").replace(/<br\s*\/?>/gi,"\n").replace(/<\/p>/gi,"\n");var doc=new DOMParser().parseFromString(value,"text/html");return(doc.body.textContent||"").trim()}
function placemarkInfo(node){
  var name=firstXmlText(node,"name"),parts=[],description=plainKmlText(firstXmlText(node,"description"));
  if(description)parts.push(description);
  xmlChildren(node,"Data").forEach(function(data){var value=firstXmlText(data,"value"),key=data.getAttribute("name")||"属性";if(value)parts.push(key+"："+value)});
  xmlChildren(node,"SimpleData").forEach(function(data){var value=data.textContent.trim(),key=data.getAttribute("name")||"属性";if(value)parts.push(key+"："+value)});
  return {name:name,remark:parts.join("\n")};
}
function parseKml(text,fileName,state){
  var xml=new DOMParser().parseFromString(text,"application/xml");
  if(xml.getElementsByTagName("parsererror").length)throw new Error("KML 文件格式无效");
  var features=[],placemarks=xmlChildren(xml,"Placemark"),containers=placemarks.length?placemarks:[xml];
  containers.forEach(function(container){
    var info=placemarkInfo(container);
    xmlChildren(container,"LineString").forEach(function(node){var pts=parseCoordinateText(firstXmlText(node,"coordinates"));if(pts.length>=2)features.push({type:"line",points:pts,name:info.name,remark:info.remark})});
    xmlChildren(container,"Polygon").forEach(function(node){var pts=parseCoordinateText(firstXmlText(node,"coordinates"));if(pts.length>=3)features.push({type:"polygon",points:pts,name:info.name,remark:info.remark})});
    xmlChildren(container,"Point").forEach(function(node){var pts=parseCoordinateText(firstXmlText(node,"coordinates"));if(pts.length)features.push({type:"point",points:[pts[0]],name:info.name,remark:info.remark})});
    xmlChildren(container,"Track").forEach(function(node){var pts=[];xmlChildren(node,"coord").forEach(function(coord){var values=coord.textContent.trim().split(/\s+/),lon=Number(values[0]),lat=Number(values[1]);if(Number.isFinite(lat)&&Number.isFinite(lon))pts.push([lat,lon])});if(pts.length>=2)features.push({type:"line",points:pts,name:info.name,remark:info.remark})});
  });
  if(!features.length)throw new Error("未找到可显示的轨迹、点位或多边形坐标");
  var restoredId=state&&Number(state.id),trackId=Number.isFinite(restoredId)&&restoredId>0?restoredId:++seq;
  seq=Math.max(seq,trackId);
  return {id:trackId,kind:"kml",name:fileName,features:features,color:state&&state.color||TRACK_COLORS[tracks.length%TRACK_COLORS.length],visible:state?state.visible!==false:true,rawText:text};
}
function createSearchTrack(lat,lon,state){var restoredId=state&&Number(state.id),trackId=Number.isFinite(restoredId)&&restoredId>0?restoredId:++seq;seq=Math.max(seq,trackId);var name=f6(lat)+","+f6(lon);return{id:trackId,kind:"search",name:name,features:[{type:"point",points:[[Number(lat),Number(lon)]],name:name,remark:"搜索坐标（WGS84）"}],color:state&&state.color||TRACK_COLORS[tracks.length%TRACK_COLORS.length],visible:state?state.visible!==false:true,rawText:""}}
function trackPointCount(track){return track.features.reduce(function(total,feature){return total+feature.points.length},0)}
function trackPinIcon(color){var safe=/^#[0-9a-f]{6}$/i.test(color)?color:"#e11d48";return L.divIcon({className:"track-pin-icon",html:'<div class="track-color-pin"><svg viewBox="0 0 24 28" aria-hidden="true"><path d="M8 2h8l-1.4 3.2v5.1l4.1 4.2v1.8H13v8.1L12 27l-1-2.6v-8.1H5.3v-1.8l4.1-4.2V5.2z" fill="'+safe+'" stroke="rgba(20,35,45,.55)" stroke-width="1" stroke-linejoin="round"/></svg></div>',iconSize:[21,24],iconAnchor:[10,23],popupAnchor:[0,-20]})}
function popupContent(track,feature,point){
  var box=document.createElement("div");box.className="kml-popup";
  if(feature.name){var title=document.createElement("div");title.className="kml-popup-title";title.textContent=feature.name;box.appendChild(title)}
  if(feature.remark){var remark=document.createElement("div");remark.className="kml-popup-remark";remark.textContent=feature.remark;box.appendChild(remark)}
  if(point){var coord=document.createElement("div");coord.className="kml-popup-coord";coord.textContent="WGS84："+f6(point[0])+","+f6(point[1]);box.appendChild(coord)}
  return box;
}
function renderTracks(){
  layerTracks.clearLayers();
  tracks.forEach(function(track){if(track.visible===false)return;track.features.forEach(function(feature){var pts=feature.points.map(function(p){return wgs2gcj(p[0],p[1])}),opts={color:track.color,weight:3,opacity:.9,fillOpacity:.12},layer;if(feature.type==="line")layer=L.polyline(pts,opts);else if(feature.type==="polygon")layer=L.polygon(pts,opts);else layer=L.marker(pts[0],{icon:trackPinIcon(track.color)});if(feature.name){layer.bindTooltip(feature.name,showTrackNames?{permanent:true,direction:"top",className:"track-name-label"}:{direction:"top"});if(showTrackNames)layer.on("tooltipopen",function(event){var element=event.tooltip.getElement();if(element){element.style.setProperty("--track-name-color",track.color);element.style.setProperty("--track-name-size",trackNameSize+"px")}})}layer.bindPopup(popupContent(track,feature,feature.type==="point"?feature.points[0]:null));layer.addTo(layerTracks)})});
}
function focusTrack(track){var pts=[];track.features.forEach(function(feature){feature.points.forEach(function(p){pts.push(wgs2gcj(p[0],p[1]))})});if(pts.length===1)map.setView(pts[0],17);else if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.15),{maxZoom:17})}
function visibilityIcon(hidden){return hidden?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.2A10.7 10.7 0 0 1 12 4c5.5 0 9 6 9 6a15.7 15.7 0 0 1-2.1 2.8M6.2 6.2C4.2 7.6 3 10 3 10s3.5 6 9 6a9.8 9.8 0 0 0 3-.5"/></svg>':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="12" cy="12" r="2.5"/></svg>'}
function deleteIcon(){return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>'}
function storedTrackData(){return tracks.map(function(track){var record={id:track.id,kind:track.kind||"kml",name:track.name,color:track.color,visible:track.visible!==false};if(track.kind==="search"){record.lat=track.features[0].points[0][0];record.lon=track.features[0].points[0][1]}else record.text=track.rawText;return record})}
function saveTrackSession(){if(pageMode!=="track")return Promise.resolve();return fetch("/api/tracks?token="+encodeURIComponent(token),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(storedTrackData())}).catch(function(){showTip("轨迹临时保存失败，刷新后可能丢失",2600)})}
function restoreTrackSession(){
  return fetch("/api/tracks?token="+encodeURIComponent(token)).then(function(response){if(!response.ok)throw new Error();return response.json()}).then(function(records){
    tracks=[];(Array.isArray(records)?records:[]).forEach(function(record){try{tracks.push(record.kind==="search"?createSearchTrack(record.lat,record.lon,record):parseKml(record.text,record.name,record))}catch(_error){}});
    renderTracks();renderTrackSidebar();renderList();if(tracks.length)fitAll();
  }).catch(function(){showTip("未能恢复之前导入的轨迹",2200)});
}
function renderTrackSidebar(){
  var list=document.getElementById("trackFileList"),count=document.getElementById("trackFileCount");if(!list||!count)return;
  count.textContent=tracks.length+" 个";
  if(!tracks.length){list.innerHTML='<div class="track-empty">尚未导入 KML 文件</div>';return}
  list.innerHTML=tracks.map(function(track,index){var hidden=track.visible===false,meta=track.kind==="search"?"搜索坐标 · WGS84":track.features.length+' 个图形 · '+trackPointCount(track)+' 个坐标点';return '<div class="track-file '+(hidden?'hidden':'')+'" data-index="'+index+'"><div class="track-file-title"><button class="track-icon-btn" data-action="toggle" title="'+(hidden?'显示该项目':'隐藏该项目')+'" aria-label="'+(hidden?'显示':'隐藏')+'">'+visibilityIcon(hidden)+'</button><input class="track-color" type="color" value="'+track.color+'" title="更换轨迹和图钉颜色" aria-label="更换颜色"><span class="track-file-name" title="点击定位">'+escHtml(track.name)+'</span><button class="track-icon-btn delete-track" data-action="delete" title="删除该项目" aria-label="删除">'+deleteIcon()+'</button></div><div class="track-file-meta">'+meta+'</div></div>'}).join("");
  list.querySelectorAll(".track-file").forEach(function(row){var index=Number(row.dataset.index),color=row.querySelector(".track-color");row.querySelector(".track-file-name").onclick=function(){focusTrack(tracks[index])};row.querySelector('[data-action="toggle"]').onclick=function(){tracks[index].visible=tracks[index].visible===false;renderTracks();renderTrackSidebar();renderList();saveTrackSession()};color.oninput=function(){tracks[index].color=color.value;renderTracks()};color.onchange=function(){saveTrackSession()};row.querySelector('[data-action="delete"]').onclick=function(){tracks.splice(index,1);renderTracks();renderTrackSidebar();renderList();saveTrackSession()}});
}
function importKmlFiles(files){
  var list=Array.from(files||[]);if(!list.length)return;
  Promise.all(list.map(function(file){return file.text().then(function(text){return parseKml(text,file.name)}).then(function(track){tracks.push(track);return null}).catch(function(error){return file.name+"："+error.message})})).then(function(errors){renderTracks();renderTrackSidebar();renderList();fitAll();saveTrackSession();var failed=errors.filter(Boolean);if(failed.length){showTip("部分文件导入失败",2400);statusEl.textContent=failed.join("；")}else{showTip("KML 导入完成",1800)}});
}
function fenceType(shape){return shape==="polygon"?"poly":shape==="rectangle"?"rect":shape}
function saveFence(fence){
  /* 每种围栏最多保留一个；同类型重画时只替换该类型。 */
  var type=fenceType(fence.shape);
  fences=fences.filter(function(item){return fenceType(item.shape)!==type});
  fences.push(fence);
  clearDraft();
  redraw();
  showTip("围栏已完成；同类型重新绘制会替换原围栏",2200);
}

function hideHoverCoordinate(){if(hoverCoordTooltip){map.closeTooltip(hoverCoordTooltip);hoverCoordTooltip=null}}
function setMode(next){mode=mode===next?null:next;clearDraft();hideHoverCoordinate();map.dragging.enable();map.getContainer().style.cursor=mode?"crosshair":"";document.querySelectorAll("[data-mode]").forEach(function(b){b.classList.toggle("on",b.dataset.mode===mode)});
  var texts={point:"在地图上单击标注经纬度点，可连续添加。",circle:"按住并拖动：按下点是圆心，拖动距离是半径；重画只会替换原圆形围栏。",rect:"按住并从一角拖到对角，生成矩形；重画只会替换原矩形围栏。",polygon:"逐点单击添加顶点，双击或点“完成多边形”；至少 3 点，重画只会替换原多边形围栏。",reference:"移动鼠标查看 WGS84 经纬度；单击添加参考标记。参考点不参与围栏回填。"};
  hint.textContent=mode?texts[mode]:"选择一种绘制方式；所有坐标以 WGS84 回填。";
}
document.querySelectorAll("[data-mode]").forEach(function(b){b.onclick=function(){setMode(b.dataset.mode)}});

function copyReferenceCoordinate(point){
  var text=f6(point.lat)+","+f6(point.lon),done=function(){showTip("坐标已复制："+text,1800)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done).catch(function(){fallbackCopy(text,done)})}else fallbackCopy(text,done)
}
function fallbackCopy(text,done){var input=document.createElement("textarea");input.value=text;input.style.position="fixed";input.style.opacity="0";document.body.appendChild(input);input.select();try{document.execCommand("copy");done()}catch(_error){showTip("复制失败，请手动复制",2000)}document.body.removeChild(input)}
function referencePopup(point,index){
  var box=document.createElement("div");box.className="reference-popup";
  box.innerHTML='<div class="reference-popup-title">参考标记 '+(index+1)+'</div><div class="reference-popup-coord">纬度：'+f6(point.lat)+'<br>经度：'+f6(point.lon)+'<br>纬度,经度：'+f6(point.lat)+','+f6(point.lon)+'</div><div class="reference-popup-actions"><button type="button" class="copy-reference">复制坐标</button><button type="button" class="delete-reference">删除标记</button></div>';
  box.querySelector(".copy-reference").onclick=function(){copyReferenceCoordinate(point)};
  box.querySelector(".delete-reference").onclick=function(){referenceMarkers.splice(index,1);map.closePopup();redraw();showTip("参考标记已删除",1500)};
  return box;
}
function redraw(){layerItems.clearLayers();
  markers.forEach(function(p,i){var g=wgs2gcj(p.lat,p.lon);L.marker(g,{icon:pointIcon(i+1)}).bindTooltip((i+1)+" · "+f6(p.lat)+", "+f6(p.lon),{permanent:true,direction:"top",className:"coord-label"}).addTo(layerItems)});
  referenceMarkers.forEach(function(p,i){var g=wgs2gcj(p.lat,p.lon),label="纬度 "+f6(p.lat)+" · 经度 "+f6(p.lon);L.marker(g,{icon:referenceIcon()}).bindTooltip(label,{permanent:true,direction:"top",className:"reference-coord-label"}).bindPopup(referencePopup(p,i)).addTo(layerItems)});
  fences.forEach(function(f){var opts={color:f.shape==="circle"?"#2563eb":f.shape==="rect"?"#0f766e":"#7c3aed",weight:2,fillOpacity:.12};if(f.shape==="circle"){var c=wgs2gcj(f.points[0][0],f.points[0][1]);L.circle(c,Object.assign({radius:f.radius},opts)).addTo(layerItems)}else{var pts=f.points.map(function(p){return wgs2gcj(p[0],p[1])});(f.shape==="rect"?L.rectangle(L.latLngBounds(pts),opts):L.polygon(pts,opts)).addTo(layerItems)}});
  renderList();
}
function renderList(){
  if(pageMode==="track"){
    var visibleCount=tracks.filter(function(track){return track.visible!==false}).length;
    statusEl.textContent="已加载 "+tracks.length+" 个 KML · 当前显示 "+visibleCount+" 个 · 共 "+tracks.reduce(function(n,t){return n+trackPointCount(t)},0)+" 个坐标点 · KML 按 WGS84 显示";
    return;
  }
  var all=[];
  markers.forEach(function(p,i){all.push('<span class="chip">点 '+(i+1)+' · '+f6(p.lat)+', '+f6(p.lon)+' <b data-kind="point" data-index="'+i+'">×</b></span>')});
  fences.forEach(function(f,i){var n=f.shape==="circle"?"圆形":f.shape==="rect"?"矩形":"多边形";all.push('<span class="chip">围栏 '+(i+1)+' · '+n+(f.radius?' · '+f.radius+'m':'')+' <b data-kind="fence" data-index="'+i+'">×</b></span>')});
  itemsEl.innerHTML=all.join("")||'<span class="empty">还没有标注点或围栏</span>';
  itemsEl.querySelectorAll("b[data-kind]").forEach(function(x){x.onclick=function(){var a=x.dataset.kind==="point"?markers:fences;a.splice(Number(x.dataset.index),1);redraw()}});
  statusEl.textContent="标注点 "+markers.length+" 个 · 围栏 "+fences.length+" 个 · 保存为 WGS84";
}

map.on("mousedown",function(e){if(mode!=="circle"&&mode!=="rect")return;downLL=e.latlng;map.dragging.disable();layerDraft.clearLayers()});
map.on("mousemove",function(e){
  if(mode==="reference"){var w=gcj2wgs(e.latlng.lat,e.latlng.lng),text="纬度 "+f6(w[0])+" · 经度 "+f6(w[1]);if(!hoverCoordTooltip)hoverCoordTooltip=L.tooltip({permanent:true,direction:"top",offset:[0,-8],className:"cursor-coord-label",interactive:false});hoverCoordTooltip.setLatLng(e.latlng).setContent(text);if(!map.hasLayer(hoverCoordTooltip))hoverCoordTooltip.addTo(map);return}
  if(!downLL||(mode!=="circle"&&mode!=="rect"))return;layerDraft.clearLayers();if(mode==="circle"){var r=dist(downLL,e.latlng);draft=L.circle(downLL,{radius:r,color:"#f59e0b",fillOpacity:.14}).addTo(layerDraft);showTip("半径 "+Math.round(r)+" 米")}else{draft=L.rectangle(L.latLngBounds(downLL,e.latlng),{color:"#f59e0b",fillOpacity:.14}).addTo(layerDraft);showTip("拖动到对角后松开")}
});
map.on("mouseout",function(){if(mode==="reference")hideHoverCoordinate()});
map.on("mouseup",function(e){if(!downLL||(mode!=="circle"&&mode!=="rect"))return;map.dragging.enable();var start=downLL;downLL=null;if(mode==="circle"){var radius=dist(start,e.latlng);if(radius<5){showTip("半径太小，请重新拖动",1800);clearDraft();return}var c=gcj2wgs(start.lat,start.lng);saveFence({id:++seq,shape:"circle",points:[[c[0],c[1]]],radius:Math.round(radius)})}else{var sw=gcj2wgs(Math.min(start.lat,e.latlng.lat),Math.min(start.lng,e.latlng.lng)),ne=gcj2wgs(Math.max(start.lat,e.latlng.lat),Math.max(start.lng,e.latlng.lng));if(dist(start,e.latlng)<10){showTip("矩形太小，请重新拖动",1800);clearDraft();return}saveFence({id:++seq,shape:"rect",points:[[sw[0],sw[1]],[ne[0],ne[1]]],radius:0})}});
map.on("click",function(e){if(mode==="point"){var w=gcj2wgs(e.latlng.lat,e.latlng.lng);markers.push({lat:w[0],lon:w[1]});redraw();return}if(mode==="reference"){var r=gcj2wgs(e.latlng.lat,e.latlng.lng);referenceMarkers.push({lat:r[0],lon:r[1]});redraw();showTip("参考标记已添加；点击标记可复制或删除",1800);return}if(mode!=="polygon")return;polyPts.push(e.latlng);layerDraft.clearLayers();if(polyPts.length===1)L.circleMarker(e.latlng,{radius:5,color:"#f59e0b",fillOpacity:1}).addTo(layerDraft);else L.polygon(polyPts,{color:"#f59e0b",fillOpacity:.14}).addTo(layerDraft);showTip("已添加 "+polyPts.length+" 个顶点，双击或点“完成多边形”")});
map.on("dblclick",function(){if(mode==="polygon")finishPolygon()});
function finishPolygon(){if(mode!=="polygon"){setMode(null);return}if(polyPts.length<3){showTip("多边形至少需要 3 个点",1800);return}var pts=polyPts.map(function(p){return gcj2wgs(p.lat,p.lng)});saveFence({id:++seq,shape:"poly",points:pts,radius:0})}
document.getElementById("finishButton").onclick=finishPolygon;
document.getElementById("clearButton").onclick=async function(){
  if(pageMode==="track"){
    if(!tracks.length){showTip("当前没有已加载的轨迹",1600);return}
    if(!await askConfirm())return;
    tracks=[];layerTracks.clearLayers();renderTrackSidebar();renderList();saveTrackSession();showTip("已删除全部轨迹",1800);return;
  }
  markers=[];fences=[];referenceMarkers=[];tracks=[];clearDraft();layerTracks.clearLayers();redraw()
};
function fitAll(){var pts=[];markers.forEach(function(p){pts.push(wgs2gcj(p.lat,p.lon))});referenceMarkers.forEach(function(p){pts.push(wgs2gcj(p.lat,p.lon))});fences.forEach(function(f){f.points.forEach(function(p){pts.push(wgs2gcj(p[0],p[1]))})});tracks.forEach(function(t){if(t.visible===false)return;t.features.forEach(function(feature){feature.points.forEach(function(p){pts.push(wgs2gcj(p[0],p[1]))})})});if(!pts.length){showTip("还没有可显示的图形",1600);return false}if(pts.length===1)map.setView(pts[0],16);else map.fitBounds(L.latLngBounds(pts).pad(.15),{maxZoom:17});return true}
document.getElementById("fitButton").onclick=fitAll;
document.getElementById("importKmlButton").onclick=function(){document.getElementById("kmlFileInput").click()};
document.getElementById("kmlFileInput").onchange=function(){importKmlFiles(this.files);this.value=""};
document.getElementById("sidebarImportButton").onclick=function(){document.getElementById("kmlFileInput").click()};
var showTrackNamesInput=document.getElementById("showTrackNames"),trackNameSizeSelect=document.getElementById("trackNameSize");
showTrackNamesInput.onchange=function(){showTrackNames=this.checked;trackNameSizeSelect.disabled=!showTrackNames;renderTracks()};
trackNameSizeSelect.onchange=function(){trackNameSize=Number(this.value)||12;renderTracks()};
var mapStyleSelect=document.getElementById("mapStyleSelect");mapStyleSelect.value=mapStyle;mapStyleSelect.onchange=function(){mapStyle=this.value==="7"||this.value==="satellite"?this.value:"8";map.removeLayer(amapLayer);amapLayer=createAmapLayer(mapStyle).addTo(map);localStorage.setItem("gnss-map-style",mapStyle);showTip(mapStyle==="7"?"已切换为简洁底图":mapStyle==="satellite"?"已切换为卫星影像":"已切换为详细底图",1600)};

document.getElementById("locateButton").onclick=function(){
  if(!navigator.geolocation){showTip("当前浏览器不支持读取位置",2600);return}
  showTip("正在读取当前位置…");
  navigator.geolocation.getCurrentPosition(function(pos){
    var lat=pos.coords.latitude,lon=pos.coords.longitude,accuracy=pos.coords.accuracy||0,g=wgs2gcj(lat,lon);
    layerLocation.clearLayers();
    if(accuracy>0)L.circle(g,{radius:accuracy,color:"#e11d48",weight:1,fillColor:"#e11d48",fillOpacity:.08}).addTo(layerLocation);
    L.marker(g,{icon:currentIcon()}).bindTooltip("当前位置 · "+f6(lat)+", "+f6(lon)+(accuracy?" · 精度约 "+Math.round(accuracy)+"m":""),{permanent:true,direction:"top",className:"coord-label"}).addTo(layerLocation);
    map.setView(g,17);statusEl.textContent="当前位置："+f6(lat)+", "+f6(lon)+(accuracy?" · 精度约 "+Math.round(accuracy)+"m":"");showTip("已定位到当前位置",1800);
  },function(err){
    var msg=err&&err.code===1?"位置权限被拒绝，请在浏览器中允许位置访问":err&&err.code===2?"Windows 当前无法提供位置信息":err&&err.code===3?"读取位置超时":"读取当前位置失败";
    showTip(msg,4200);statusEl.textContent=msg;
  },{enableHighAccuracy:true,timeout:12000,maximumAge:30000});
};

function escHtml(value){return String(value==null?"":value).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function hideSearchResults(){searchResults.classList.remove("show");searchActive=-1}
function renderSearchResults(items,emptyText){
  searchItems=items||[];searchActive=-1;
  if(!searchItems.length){searchResults.innerHTML='<div class="search-result empty">'+escHtml(emptyText||"未找到地点，也可直接输入 纬度,经度")+'</div>';searchResults.classList.add("show");return}
  searchResults.innerHTML=searchItems.map(function(item,index){return '<div class="search-result" data-index="'+index+'"><b>'+escHtml(item.name)+'</b>'+(item.address?'<span>'+escHtml(item.address)+'</span>':"")+'</div>'}).join("");
  searchResults.classList.add("show");
  searchResults.querySelectorAll(".search-result[data-index]").forEach(function(row){row.onmousedown=function(e){e.preventDefault();pickSearchResult(searchItems[Number(row.dataset.index)])}});
}
function searchPlaces(query){
  var q=String(query||"").trim();if(!q)return Promise.resolve([]);if(searchCache[q])return Promise.resolve(searchCache[q]);
  var m=/^\s*(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(q);
  if(m){var la=Number(m[1]),lo=Number(m[2]);if(la>=-90&&la<=90&&lo>=-180&&lo<=180){var coord=[{name:"坐标 "+f6(la)+", "+f6(lo),address:"按输入的 WGS84 经纬度定位",lat:la,lon:lo,isCoordinate:true}];searchCache[q]=coord;return Promise.resolve(coord)}}
  return fetch("https://photon.komoot.io/api/?limit=8&lang=default&q="+encodeURIComponent(q)).then(function(r){if(!r.ok)throw new Error();return r.json()}).then(function(j){
    var out=[];(j.features||[]).forEach(function(feature){var coords=feature.geometry&&feature.geometry.coordinates;if(!coords||coords.length<2)return;var p=feature.properties||{},parts=[p.country,p.state,p.city,p.district,p.street].filter(function(x,i,a){return x&&a.indexOf(x)===i});var address=parts.join(" "),name=p.name||p.street||p.city||address||q;out.push({name:name,address:address,lat:Number(coords[1]),lon:Number(coords[0])})});searchCache[q]=out;return out;
  });
}
function pickSearchResult(item){if(!item)return;var display=wgs2gcj(item.lat,item.lon);map.setView(display,16);searchInput.value=item.name;searchClear.classList.add("show");hideSearchResults();if(pageMode==="track"&&item.isCoordinate){tracks.push(createSearchTrack(item.lat,item.lon));renderTracks();renderTrackSidebar();renderList();saveTrackSession();showTip("已定位并添加搜索标记",1800)}else showTip("已定位到 "+item.name,1800)}
function requestSearch(pickFirst){
  var q=searchInput.value.trim();if(!q){hideSearchResults();return}
  var token=++searchToken;renderSearchResults([],"搜索中…");
  searchPlaces(q).then(function(items){if(token!==searchToken)return;if(pickFirst&&items.length){pickSearchResult(items[0]);return}renderSearchResults(items,"未找到“"+q+"”，请尝试更短的地名")}).catch(function(){if(token!==searchToken)return;renderSearchResults([],"地点搜索暂时不可用，请检查网络；也可输入经纬度")});
}
function setSearchActive(index){var rows=searchResults.querySelectorAll(".search-result[data-index]");if(!rows.length)return;searchActive=(index+rows.length)%rows.length;rows.forEach(function(row,i){row.classList.toggle("active",i===searchActive)});rows[searchActive].scrollIntoView({block:"nearest"})}
searchInput.oninput=function(){searchClear.classList.toggle("show",!!searchInput.value);clearTimeout(searchTimer);var q=searchInput.value.trim();if(!q){++searchToken;hideSearchResults();return}searchTimer=setTimeout(function(){requestSearch(false)},320)};
searchInput.onkeydown=function(e){if(e.key==="ArrowDown"&&searchItems.length){e.preventDefault();setSearchActive(searchActive+1)}else if(e.key==="ArrowUp"&&searchItems.length){e.preventDefault();setSearchActive(searchActive-1)}else if(e.key==="Enter"){e.preventDefault();if(searchActive>=0&&searchItems[searchActive])pickSearchResult(searchItems[searchActive]);else requestSearch(true)}else if(e.key==="Escape")hideSearchResults()};
searchInput.onfocus=function(){if(searchItems.length&&searchInput.value.trim())searchResults.classList.add("show")};
searchClear.onclick=function(){searchInput.value="";searchItems=[];++searchToken;searchClear.classList.remove("show");hideSearchResults();searchInput.focus()};
document.getElementById("searchButton").onclick=function(){requestSearch(true)};
document.addEventListener("mousedown",function(e){if(!e.target.closest(".search"))hideSearchResults()});
document.getElementById("applyButton").onclick=function(){var payload={mode:pageMode,markers:pageMode==="fence"||pageMode==="fence808"?[]:markers,fences:fences};fetch("/api/apply?token="+encodeURIComponent(token),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(function(r){if(!r.ok)throw new Error();return r.json()}).then(function(){statusEl.textContent="已回填主工具，可返回主窗口继续操作";showTip("回填成功",1800)}).catch(function(){showTip("回填失败，请保持主工具正在运行",2600)})};

if(pageMode==="point"){
  document.getElementById("pageTitle").textContent="地图经纬度标记";
  document.querySelectorAll('[data-scope="fence"],[data-scope="track"]').forEach(function(el){el.style.display="none"});
  document.getElementById("applyButton").textContent="确定并回填标注点";
  setMode("point");
}else if(pageMode==="fence"){
  document.getElementById("pageTitle").textContent="电子围栏绘制";
  document.querySelectorAll('[data-scope="point"],[data-scope="track"]').forEach(function(el){el.style.display="none"});
  document.getElementById("applyButton").textContent="确定并回填围栏";
  setMode(null);
}else if(pageMode==="fence808"){
  document.getElementById("pageTitle").textContent="JT/T 808 电子围栏绘制";
  document.querySelectorAll('[data-scope="point"],[data-scope="track"]').forEach(function(el){el.style.display="none"});
  document.getElementById("applyButton").textContent="确定并回填808围栏";
  setMode(null);
  hint.textContent="选择圆形、矩形或多边形进行绘制；也可添加地图参考标记。所有坐标按 WGS84 回填到 808 组包页面。";
}else if(pageMode==="track"){
  document.getElementById("pageTitle").textContent="KML 轨迹查看";
  document.querySelectorAll('[data-scope="point"],[data-scope="fence"]').forEach(function(el){el.style.display="none"});
  document.getElementById("applyButton").style.display="none";
  document.getElementById("fitButton").textContent="显示全部轨迹";
  document.getElementById("clearButton").textContent="删除全部轨迹";
  document.getElementById("trackSidebar").classList.add("show");
  itemsEl.style.display="none";
  setMode(null);
  hint.textContent="导入本机 KML 文件，在地图上查看轨迹、点位或多边形；文件不会上传。";
}else{
  setMode("point");
}
redraw();if(pageMode==="track")restoreTrackSession();setTimeout(function(){map.invalidateSize()},100);
})();

