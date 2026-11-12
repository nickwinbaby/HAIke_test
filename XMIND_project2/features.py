"""Document features shared by validation, collaboration and XMind interchange."""
import base64
import copy
import io
import json
import re
import uuid
import zipfile
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from limits import MAX_DOCUMENT
from tree_json import dumps as tree_json_dumps

LAYOUTS = {"balanced", "right", "left", "down", "up"}
THEMES = {"original", "ocean", "forest", "ink", "pastel", "sunset"}
DOC_FIELDS = ("layout", "background", "theme", "lineType", "lineWidth", "spacing", "relationships", "annotations")
STYLE_FIELDS = {"fill", "text", "line", "border", "fontSize", "bold", "italic", "shape"}
SHAPES = {"rectangle", "roundedRect", "ellipse", "underline", "diamond"}


def new_id():
    return uuid.uuid4().hex


def valid_link(value):
    return isinstance(value, str) and len(value) <= 2048 and (not value or urlsplit(value).scheme in {"http", "https", "mailto"})


def validate_features(doc):
    if doc.get("layout", "balanced") not in LAYOUTS or doc.get("theme", "original") not in THEMES:
        raise ValueError("布局或主题无效。")
    if doc.get("lineType", "curve") not in {"curve", "straight", "elbow"}:
        raise ValueError("连线样式无效。")
    if doc.get("lineWidth", 2) not in {1, 2, 3, 4} or doc.get("spacing", "normal") not in {"compact", "normal", "loose"}:
        raise ValueError("连线粗细或间距无效。")
    nodes = doc["nodes"]
    for n in nodes.values():
        meta = n.get("meta", {})
        if not isinstance(meta, dict) or set(meta) - {"priority", "progress", "marker", "labels", "link", "image"}:
            raise ValueError("节点信息无效。")
        if meta.get("priority", 0) not in range(6) or meta.get("progress", -1) not in {-1, 0, 25, 50, 75, 100}:
            raise ValueError("优先级或任务进度无效。")
        if meta.get("marker", "") not in {"", "star", "flag", "question", "idea", "check"}:
            raise ValueError("图标无效。")
        labels = meta.get("labels", [])
        if not isinstance(labels, list) or len(labels) > 8 or any(not isinstance(v, str) or len(v) > 24 for v in labels):
            raise ValueError("最多 8 个标签，每个不超过 24 字。")
        if not valid_link(meta.get("link", "")):
            raise ValueError("链接仅支持 http、https、mailto。")
        image = meta.get("image", "")
        if not isinstance(image, str) or len(image) > 410000:
            raise ValueError("节点图片过大。")
        if image:
            match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", image)
            if not match:
                raise ValueError("图片仅支持 PNG、JPEG、WebP。")
            try:
                raw = base64.b64decode(match[2], validate=True)
            except ValueError:
                raise ValueError("图片编码无效。")
            if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"):
                raise ValueError("图片内容与格式不符。")
    for field in ("relationships", "annotations"):
        items = doc.get(field, [])
        if not isinstance(items, list) or len(items) > 300:
            raise ValueError("关系线/标注最多 300 个。")
        ids = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in ids:
                raise ValueError("关系线/标注 ID 无效。")
            ids.add(item["id"])
            if not isinstance(item.get("title", ""), str) or len(item.get("title", "")) > 120:
                raise ValueError("标注文字最多 120 字。")
            if field == "relationships":
                if item.get("from") not in nodes or item.get("to") not in nodes or item["from"] == item["to"]:
                    raise ValueError("关系线需要两个不同节点。")
            else:
                topics = item.get("topics", [])
                if item.get("kind") not in {"boundary", "summary"} or not isinstance(topics, list) or not topics or any(t not in nodes for t in topics):
                    raise ValueError("边界/概要节点无效。")
    if len(json.dumps(doc, ensure_ascii=False).encode()) > MAX_DOCUMENT:
        raise ValueError(f"导图超过 {MAX_DOCUMENT // 1024 // 1024} MB，请拆分导图或减少图片。")


def prune_references(doc):
    nodes = doc["nodes"]
    if "relationships" in doc:
        doc["relationships"] = [r for r in doc["relationships"] if r["from"] in nodes and r["to"] in nodes]
    if "annotations" in doc:
        doc["annotations"] = [{**a, "topics": [t for t in a["topics"] if t in nodes]} for a in doc["annotations"] if any(t in nodes for t in a["topics"])]


def extend_operation(doc, op, version):
    """Apply version-guarded feature operations to an already copied document."""
    if op.get("expected_version") != doc["version"]:
        raise ValueError("导图刚刚发生变化，请查看最新内容后重试。")
    nodes, kind = doc["nodes"], op.get("kind")
    if kind in {"style", "meta"}:
        targets = op.get("nodes", [op.get("node")])
        patch = op.get("patch")
        allowed = STYLE_FIELDS if kind == "style" else {"priority", "progress", "marker", "labels", "link", "image"}
        if not isinstance(targets, list) or not targets or not isinstance(patch, dict) or set(patch) - allowed:
            raise ValueError("样式或节点信息格式无效。")
        for ident in dict.fromkeys(targets):
            if ident not in nodes:
                raise ValueError("节点已被删除。")
            value = nodes[ident].setdefault(kind, {})
            for key, val in patch.items():
                if val is None:
                    value.pop(key, None)
                else:
                    value[key] = val
            nodes[ident]["rev"][kind] = version
        return {}
    if kind == "settings":
        patch = op.get("patch")
        if not isinstance(patch, dict) or set(patch) - (set(DOC_FIELDS) - {"relationships", "annotations"}):
            raise ValueError("画布设置无效。")
        for key, val in patch.items():
            if val is None:
                doc.pop(key, None)
            else:
                doc[key] = val
        if op.get("clearStyles"):
            for n in nodes.values():
                n.pop("style", None)
                n["rev"]["style"] = version
        return {}
    if kind in {"relationship", "annotation"}:
        field = "relationships" if kind == "relationship" else "annotations"
        items = doc.setdefault(field, [])
        if op.get("delete"):
            doc[field] = [i for i in items if i["id"] != op["delete"]]
        elif op.get("update"):
            item = next((i for i in items if i["id"] == op["update"]), None)
            title = op.get("title")
            if item is None:
                raise ValueError("要修改的关系或标注不存在。")
            if not isinstance(title, str) or len(title.strip()) > 120:
                raise ValueError("标注文字应为 0–120 个字符。")
            item["title"] = title.strip()
        else:
            item = op.get("item")
            if not isinstance(item, dict):
                raise ValueError("标注格式无效。")
            clean = {key: val for key, val in item.items() if key in ({"from", "to", "title"} if kind == "relationship" else {"topics", "kind", "title"})}
            if kind == "relationship":
                source, target = clean.get("from"), clean.get("to")
                if source not in nodes or target not in nodes or source == target:
                    raise ValueError("关系线需要连接两个不同的主题。")
                if any({existing.get("from"), existing.get("to")} == {source, target} for existing in items):
                    raise ValueError("这两个主题之间已经存在关系线。")
            clean["id"] = new_id()
            items.append(clean)
        return {}
    if kind == "add_parent":
        old = nodes.get(op.get("node"))
        if not old or old["id"] == doc["root"]:
            raise ValueError("不能在中心主题之上插入父节点。")
        parent = nodes[old["parent"]]
        ident = new_id()
        n = {"id": ident, "parent": parent["id"], "title": "父主题", "notes": "", "color": old["color"], "children": [old["id"]], "style": {"shape": "underline"}, "rev": dict.fromkeys(("title", "notes", "color", "parent"), version)}
        parent["children"][parent["children"].index(old["id"])] = ident
        nodes[ident] = n
        old["parent"], old["rev"]["parent"] = ident, version
        return {"selected": ident}
    if kind == "paste":
        parent = nodes.get(op.get("parent"))
        forest, branch = op.get("trees"), op.get("branch")
        if not parent:
            raise ValueError("粘贴目标或内容无效。")

        def make_node(source, parent_id):
            ident = new_id()
            n = {"id": ident, "parent": parent_id, "title": source.get("title", "新主题"), "notes": source.get("notes", ""), "color": source.get("color", parent["color"]), "children": [], "style": {"shape": "underline"}, "rev": dict.fromkeys(("title", "notes", "color", "parent"), version)}
            for field in ("style", "meta"):
                if field in source:
                    n[field] = copy.deepcopy(source[field])
            nodes[ident] = n
            return ident

        added = []
        if isinstance(branch, dict):
            roots, sources = branch.get("roots"), branch.get("nodes")
            if not isinstance(roots, list) or not roots or not isinstance(sources, dict):
                raise ValueError("粘贴内容无效。")
            seen = set()
            stack = [(source_id, parent["id"], None) for source_id in reversed(roots)]
            while stack:
                source_id, parent_id, target_children = stack.pop()
                source = sources.get(source_id)
                if source_id in seen or not isinstance(source_id, str) or not isinstance(source, dict):
                    raise ValueError("粘贴内容包含循环、重复或缺失节点。")
                children = source.get("children", [])
                if not isinstance(children, list) or any(not isinstance(child, str) for child in children):
                    raise ValueError("粘贴内容的子节点结构无效。")
                seen.add(source_id)
                ident = make_node(source, parent_id)
                if target_children is None:
                    added.append(ident)
                else:
                    target_children.append(ident)
                for child in reversed(children):
                    stack.append((child, ident, nodes[ident]["children"]))
        else:
            if not isinstance(forest, list) or not forest:
                raise ValueError("粘贴目标或内容无效。")
            stack = [(source, parent["id"], None) for source in reversed(forest)]
            while stack:
                source, parent_id, target_children = stack.pop()
                if not isinstance(source, dict):
                    raise ValueError("粘贴内容的节点结构无效。")
                children = source.get("children", [])
                if not isinstance(children, list):
                    raise ValueError("粘贴内容的子节点结构无效。")
                ident = make_node(source, parent_id)
                if target_children is None:
                    added.append(ident)
                else:
                    target_children.append(ident)
                for child in reversed(children):
                    stack.append((child, ident, nodes[ident]["children"]))
        parent["children"].extend(added)
        return {"selected": added[0]}
    raise ValueError("未知操作。")


def export_xmind(doc):
    """Write a portable XMind ZIP; extra JSON preserves unsupported editor settings."""
    stream = io.BytesIO()
    assets = {}
    shape_map = {"roundedRect": "roundedRect", "rectangle": "rectangle", "ellipse": "ellipse", "underline": "underline", "diamond": "diamond"}
    def topic(ident):
        n = doc["nodes"][ident]
        value = {"id": ident, "class": "topic", "title": n["title"]}
        if n["notes"]:
            value["notes"] = {"plain": {"content": n["notes"]}}
        style = n.get("style", {})
        props = {source: style[key] for key, source in {"fill": "svg:fill", "text": "fo:color", "line": "line-color", "border": "border-line-color"}.items() if key in style}
        if "fontSize" in style:
            props["fo:font-size"] = f'{style["fontSize"]}pt'
        for key, prop, yes, no in (("bold", "fo:font-weight", "bold", "normal"), ("italic", "fo:font-style", "italic", "normal")):
            if key in style:
                props[prop] = yes if style[key] else no
        if "shape" in style:
            props["shape-class"] = "org.xmind.topicShape." + shape_map[style["shape"]]
        if props:
            value["style"] = {"id": new_id(), "properties": props}
        meta = n.get("meta", {})
        if meta.get("labels"):
            value["labels"] = meta["labels"]
        if meta.get("link"):
            value["href"] = meta["link"]
        markers = []
        if meta.get("priority"):
            markers.append({"markerId": f'priority-{meta["priority"]}'})
        if meta.get("progress", -1) >= 0:
            markers.append({"markerId": {0: "task-start", 25: "task-quarter", 50: "task-half", 75: "task-3quar", 100: "task-done"}[meta["progress"]]})
        if markers:
            value["markers"] = markers
        if meta.get("image"):
            head, content = meta["image"].split(",", 1)
            ext = head.split("/")[1].split(";")[0]
            path = f"resources/{ident}.{ext}"
            assets[path] = base64.b64decode(content)
            value["image"] = {"src": "xap:" + path, "width": 180, "height": 96}
        return value
    root = topic(doc["root"])
    stack = [(doc["root"], root)]
    while stack:
        ident, value = stack.pop()
        children = doc["nodes"][ident]["children"]
        if children:
            attached = [topic(child) for child in children]
            value["children"] = {"attached": attached}
            stack.extend(zip(reversed(children), reversed(attached)))
    root["structureClass"] = {"balanced": "org.xmind.ui.map.unbalanced", "right": "org.xmind.ui.logic.right", "left": "org.xmind.ui.logic.left", "down": "org.xmind.ui.org-chart.down", "up": "org.xmind.ui.org-chart.up"}.get(doc.get("layout"), "org.xmind.ui.map.unbalanced")
    sheet = {"id": new_id(), "class": "sheet", "title": doc["nodes"][doc["root"]]["title"], "rootTopic": root,
             "relationships": [{"id": r["id"], "end1Id": r["from"], "end2Id": r["to"], "title": r.get("title", "")} for r in doc.get("relationships", [])]}
    if doc.get("background"):
        sheet["theme"] = {"map": {"properties": {"svg:fill": doc["background"]}}}
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.json", tree_json_dumps([sheet]))
        archive.writestr("metadata.json", json.dumps({"creator": {"name": "GNN", "version": "0.2.0"}}))
        archive.writestr("manifest.json", json.dumps({"file-entries": {name: {} for name in ["content.json", "metadata.json", "mindcollab.json", *assets]}}))
        archive.writestr("mindcollab.json", json.dumps(doc, ensure_ascii=False))
        for path, data in assets.items():
            archive.writestr(path, data)
    return stream.getvalue()
