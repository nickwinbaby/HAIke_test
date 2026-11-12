"""Small, single-process, server-authoritative collaborative mind map."""
import asyncio
import base64
import copy
import io
import json
import os
import re
import sqlite3
import sys
import uuid
import zipfile
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from features import DOC_FIELDS, export_xmind, extend_operation, prune_references, validate_features
from limits import MAX_FILE, MAX_MESSAGE
from tree_json import loads as tree_json_loads

BASE = Path(__file__).resolve().parent
STATIC = Path(getattr(sys, "_MEIPASS", BASE)) / "static"
TRASH_DAYS = 30
HISTORY_LIMIT = 3000
HISTORY_PAGE_SIZE = 100
COLORS = {
    "blue", "teal", "amber", "rose", "violet", "slate",
    "coral", "orange", "yellow", "green", "mint", "cyan", "sky",
    "indigo", "fuchsia", "brown",
}
DEFAULT_TOPIC_SHAPE = "underline"


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def clean_display_name(value):
    if not isinstance(value, str):
        raise ValueError("请输入你的真实姓名。")
    value = " ".join(value.strip().split())
    letters = [char for char in value if char.isalpha()]
    allowed_marks = " ·•.'’-‐-"
    if not 2 <= len(value) <= 24 or len(letters) < 2 or any(
            not char.isalpha() and char not in allowed_marks for char in value):
        raise ValueError("请输入 2–24 个字的真实姓名，只能包含文字、空格、间隔点、连字符或撇号。")
    if value.casefold() in {"访客", "游客", "匿名", "guest", "anonymous"}:
        raise ValueError("不能使用“访客”或“匿名”，请输入你的真实姓名。")
    return value


def clean_style(properties):
    """Keep only supported, safe SVG style values from XMind properties."""
    result = {}
    if not isinstance(properties, dict):
        return result
    for source, target in {"svg:fill": "fill", "fo:color": "text", "line-color": "line",
                           "border-line-color": "border"}.items():
        value = str(properties.get(source, ""))
        if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value):
            result[target] = value
        elif source == "svg:fill" and value == "none":
            result[target] = "none"
    size = re.fullmatch(r"(\d+(?:\.\d+)?)(?:pt|px)?", str(properties.get("fo:font-size", "")))
    if size:
        result["fontSize"] = max(10, min(32, float(size[1])))
    if properties.get("fo:font-weight") in {"bold", "700", "normal", "400"}:
        result["bold"] = properties["fo:font-weight"] in {"bold", "700"}
    if properties.get("fo:font-style") in {"italic", "normal"}:
        result["italic"] = properties["fo:font-style"] == "italic"
    shape = properties.get("shape-class", "")
    if shape == "org.xmind.topicShape.ellipserect":
        shape = "org.xmind.topicShape.roundedRect"
    if shape in {"org.xmind.topicShape.rectangle", "org.xmind.topicShape.roundedRect",
                 "org.xmind.topicShape.ellipse", "org.xmind.topicShape.underline"}:
        result["shape"] = shape.rsplit(".", 1)[-1]
    return result


def node(title, parent=None, color="blue"):
    result = {"id": uid(), "parent": parent, "title": title, "notes": "",
              "color": color, "children": [], "rev": {"title": 0, "notes": 0, "color": 0, "parent": 0}}
    # The central topic retains its themed rounded card; ordinary topics start as underlined text.
    if parent is not None:
        result["style"] = {"shape": DEFAULT_TOPIC_SHAPE}
    return result


def new_document(title="未命名导图", example=False):
    root = node(title)
    doc = {"id": uid(), "root": root["id"], "nodes": {root["id"]: root}, "version": 0,
           "layout": "balanced", "theme": "original", "lineType": "elbow",
           "lineWidth": 2, "spacing": "normal", "relationships": [], "annotations": []}
    if example:
        for name, color, children in [
            ("从这里开始", "blue", ["双击节点修改文字", "Tab 添加子节点", "拖动节点改变层级"]),
            ("一起讨论", "teal", ["复制链接，邀请同事", "修改实时同步", "断线重连后自动读取最新内容"]),
            ("带入你的想法", "amber", ["导入 XMind 文件", "保存为 JSON 备份", "查看历史版本"]),
        ]:
            branch = node(name, root["id"], color)
            root["children"].append(branch["id"])
            doc["nodes"][branch["id"]] = branch
            for text in children:
                leaf = node(text, branch["id"], color)
                branch["children"].append(leaf["id"])
                doc["nodes"][leaf["id"]] = leaf
    return doc


class Conflict(ValueError):
    pass


def descendants(doc, ident):
    result, stack = [], [ident]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(doc["nodes"][current]["children"])
    return result


def validate(doc):
    nodes = doc.get("nodes", {})
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError("导图必须包含至少一个节点。")
    root = doc.get("root")
    if root not in nodes:
        raise ValueError("缺少中心节点。")
    if "background" in doc and (not isinstance(doc["background"], str) or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", doc["background"])):
        raise ValueError("画布背景色无效。")
    seen = set()
    stack = [(root, None, 0)]
    while stack:
        ident, parent, depth = stack.pop()
        if not isinstance(ident, str) or ident not in nodes:
            raise ValueError("子节点引用无效或节点缺失。")
        if ident in seen:
            raise ValueError("节点结构存在循环或重复引用。")
        seen.add(ident)
        n = nodes[ident]
        if not isinstance(n, dict) or n.get("id") != ident or n.get("parent") != parent:
            raise ValueError("节点结构无效。")
        if not isinstance(n.get("title"), str) or not n["title"].strip():
            raise ValueError("节点标题不能为空。")
        if not isinstance(n.get("notes"), str) or len(n["notes"]) > 10000:
            raise ValueError("备注不能超过 10000 个字符。")
        if n.get("color") not in COLORS or not isinstance(n.get("children"), list):
            raise ValueError("节点颜色或子节点列表无效。")
        style = n.get("style", {})
        if not isinstance(style, dict) or set(style) - {"fill", "text", "line", "border", "fontSize", "bold", "italic", "shape"}:
            raise ValueError("节点样式无效。")
        for key in {"fill", "text", "line", "border"} & set(style):
            if key == "fill" and style[key] == "none":
                continue
            if not isinstance(style[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", style[key]):
                raise ValueError("节点颜色格式无效。")
        if "fontSize" in style and (not isinstance(style["fontSize"], (int, float)) or not 10 <= style["fontSize"] <= 32):
            raise ValueError("字号超出范围。")
        if any(key in style and not isinstance(style[key], bool) for key in ("bold", "italic")):
            raise ValueError("粗斜体格式无效。")
        if style.get("shape", DEFAULT_TOPIC_SHAPE) not in {"rectangle", "roundedRect", "ellipse", "underline", "diamond"}:
            raise ValueError("节点形状无效。")
        stack.extend((child, ident, depth + 1) for child in n["children"])
    if len(seen) != len(nodes):
        raise ValueError("包含无法到达的节点。")
    validate_features(doc)


def apply_operation(original, op):
    doc = copy.deepcopy(original)
    nodes = doc["nodes"]
    kind, ident = op.get("kind"), op.get("node")
    version = doc["version"] + 1
    if kind == "rename":
        if op.get("expected_version") != original["version"]:
            raise Conflict("导图刚刚发生变化，请重新命名。")
        value = op.get("value")
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
            raise ValueError("导图名称应为 1–200 个字符。")
        root = nodes[doc["root"]]
        root["title"] = value.strip()
        root["rev"]["title"] = version
        result = {}
    elif kind == "add":
        parent = nodes.get(op.get("parent"))
        if parent is None:
            raise Conflict("父节点已被删除，请重新选择。")
        n = node("新想法", parent["id"], parent["color"])
        nodes[n["id"]] = n
        after = op.get("after")
        index = parent["children"].index(after) + 1 if after in parent["children"] else len(parent["children"])
        parent["children"].insert(index, n["id"])
        result = {"selected": n["id"]}
    elif kind == "edit":
        n = nodes.get(ident)
        field, value = op.get("field"), op.get("value")
        if n is None:
            raise Conflict("该节点已被删除。")
        if field not in {"title", "notes", "color"}:
            raise ValueError("不支持的字段。")
        if op.get("expected") != n["rev"][field]:
            raise Conflict("同事刚刚修改了这个字段；你的草稿已保留，请查看最新内容后再提交。")
        if not isinstance(value, str):
            raise ValueError("字段必须是文字。")
        n[field] = value.strip() if field == "title" else value
        if field == "color":
            n["style"] = {k: v for k, v in n.get("style", {}).items() if k not in {"fill", "text", "line", "border"}}
        n["rev"][field] = version
        result = {}
    elif kind in {"delete", "move", "reorder"}:
        n = nodes.get(ident)
        if n is None or ident == doc["root"]:
            raise Conflict("该节点不存在，或正在操作中心节点。")
        # Structural operations use the whole document version, so a concurrent
        # descendant edit cannot be silently discarded by a stale delete/move.
        if op.get("expected_version") != doc["version"]:
            raise Conflict("导图刚刚发生变化，请确认最新结构后重试。")
        old_parent = nodes[n["parent"]]
        if kind == "delete":
            old_parent["children"].remove(ident)
            for child in descendants(doc, ident):
                del nodes[child]
            result = {"selected": old_parent["id"]}
        elif kind == "move":
            parent = nodes.get(op.get("parent"))
            if parent is None or parent["id"] in descendants(doc, ident):
                raise ValueError("不能移入自身或自己的子节点。")
            old_parent["children"].remove(ident)
            parent["children"].append(ident)
            n["parent"] = parent["id"]
            n["rev"]["parent"] = version
            result = {}
        else:
            children = old_parent["children"]
            index = children.index(ident)
            direction = op.get("direction")
            if direction not in {-1, 1}:
                raise ValueError("排序方向无效。")
            target = max(0, min(len(children) - 1, index + direction))
            children[index], children[target] = children[target], children[index]
            result = {}
    else:
        result = extend_operation(doc, op, version)
    doc["version"] = version
    prune_references(doc)
    validate(doc)
    return doc, result


def audit_label(value, limit=48):
    """Make document text safe and compact for a one-line history entry."""
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def topic_label(doc, ident):
    topic = doc.get("nodes", {}).get(ident, {})
    return f"「{audit_label(topic.get('title'), 36) or '已删除主题'}」"


def history_summary(original, doc, op):
    """Describe the committed operation without exposing internal node IDs."""
    kind = op.get("kind")
    ident = op.get("node")
    if kind == "rename":
        return f"重命名导图：{topic_label(original, original['root'])} → {topic_label(doc, doc['root'])}"
    if kind == "add":
        created = next((node_id for node_id in doc["nodes"] if node_id not in original["nodes"]), None)
        return f"在 {topic_label(original, op.get('parent'))} 下添加子主题 {topic_label(doc, created)}"
    if kind == "edit":
        field = op.get("field")
        before = original.get("nodes", {}).get(ident, {}).get(field, "")
        after = doc.get("nodes", {}).get(ident, {}).get(field, "")
        if field == "title":
            return f"修改主题标题：{topic_label(original, ident)} → 「{audit_label(after)}」"
        if field == "notes":
            return f"修改 {topic_label(doc, ident)} 的备注：{len(str(before))} 字 → {len(str(after))} 字"
        if field == "color":
            return f"修改 {topic_label(doc, ident)} 的颜色：{before} → {after}"
    if kind == "delete":
        removed = len(original.get("nodes", {})) - len(doc.get("nodes", {})) - 1
        suffix = f"及其 {removed} 个子主题" if removed > 0 else ""
        return f"删除主题 {topic_label(original, ident)}{suffix}"
    if kind == "move":
        return f"将主题 {topic_label(original, ident)} 移动到 {topic_label(original, op.get('parent'))} 下"
    if kind == "reorder":
        return f"调整主题 {topic_label(original, ident)} 的同级顺序"
    if kind == "undo":
        return "撤销一次已提交的修改"
    if kind in {"style", "meta"}:
        names = {"style": "样式", "meta": "主题信息"}
        fields = "、".join(map(str, (op.get("patch") or {}).keys())) or "设置"
        targets = op.get("nodes", [op.get("node")])
        return f"更新 {len(targets)} 个主题的{names[kind]}：{fields}"
    if kind == "settings":
        fields = "、".join(map(str, (op.get("patch") or {}).keys())) or "设置"
        if op.get("clearStyles"):
            fields += "、清除自定义样式"
        return f"修改画布设置：{fields}"
    if kind in {"relationship", "annotation"}:
        field = "relationships" if kind == "relationship" else "annotations"
        label = "关系线" if kind == "relationship" else "概要/边界"
        if op.get("delete"):
            item = next((value for value in original.get(field, []) if value["id"] == op["delete"]), {})
            return f"删除{label}「{audit_label(item.get('title')) or '未命名'}」"
        if op.get("update"):
            item = next((value for value in original.get(field, []) if value["id"] == op["update"]), {})
            return f"修改{label}说明：「{audit_label(item.get('title'))}」→「{audit_label(op.get('title'))}」"
        item = op.get("item") or {}
        if kind == "relationship":
            return f"添加关系线：{topic_label(original, item.get('from'))} ↔ {topic_label(original, item.get('to'))}"
        annotation = "概要" if item.get("kind") == "summary" else "边界"
        return f"添加{annotation}（关联 {len(item.get('topics', []))} 个主题）"
    if kind == "add_parent":
        created = next((node_id for node_id in doc["nodes"] if node_id not in original["nodes"]), None)
        return f"在 {topic_label(original, ident)} 上方插入父主题 {topic_label(doc, created)}"
    if kind == "paste":
        count = len(doc["nodes"]) - len(original["nodes"])
        return f"在 {topic_label(original, op.get('parent'))} 下粘贴 {count} 个主题"
    return "修改导图内容"


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            first_run = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() is None
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, updated TEXT NOT NULL,
                    deleted_at TEXT);
                CREATE TABLE IF NOT EXISTS history (
                    document TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
                    created TEXT NOT NULL, actor TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(document, version));
                CREATE TABLE IF NOT EXISTS undo_actions (
                    token TEXT PRIMARY KEY, document TEXT NOT NULL, body TEXT NOT NULL, version INTEGER NOT NULL);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
            if "deleted_at" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN deleted_at TEXT")
            history_columns = {row[1] for row in conn.execute("PRAGMA table_info(history)")}
            if "summary" not in history_columns:
                conn.execute("ALTER TABLE history ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
        self.purge_expired()
        if first_run:
            self.create(new_document("我的协作空间", example=True))

    def create(self, doc, actor="创建文档", summary=None):
        validate(doc)
        with self.connect() as conn:
            self.write(conn, doc, actor, summary or f"创建导图 {topic_label(doc, doc['root'])}")
        return doc

    def create_many(self, documents, actor, filename):
        """Commit an imported workbook and all its history entries atomically."""
        for doc in documents:
            validate(doc)
        with closing(self.connect()) as conn, conn:
            for doc in documents:
                sheet = doc.get("source", {}).get("sheet_title")
                summary = f"导入文件「{audit_label(filename)}」"
                if sheet:
                    summary += f" · 工作表「{audit_label(sheet)}」"
                self.write(conn, doc, actor, summary)

    def write(self, conn, doc, actor, summary=""):
        stamp, body = now(), json.dumps(doc, ensure_ascii=False)
        title = doc["nodes"][doc["root"]]["title"]
        conn.execute("INSERT INTO documents (id,title,body,updated,deleted_at) VALUES (?, ?, ?, ?, NULL) ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body, updated=excluded.updated",
                     (doc["id"], title, body, stamp))
        conn.execute("INSERT INTO history (document,version,body,created,actor,summary) VALUES (?, ?, ?, ?, ?, ?)",
                     (doc["id"], doc["version"], body, stamp, actor, summary))
        conn.execute("DELETE FROM history WHERE document=? AND version NOT IN (SELECT version FROM history WHERE document=? ORDER BY version DESC LIMIT ?)",
                     (doc["id"], doc["id"], HISTORY_LIMIT))

    def get(self, ident):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM documents WHERE id=? AND deleted_at IS NULL", (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        return json.loads(row[0])

    def get_any(self, ident):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM documents WHERE id=? AND deleted_at IS NULL", (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        return json.loads(row[0])

    def list(self):
        self.purge_expired()
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT id,title,updated,json_extract(body, '$.source.sheet_title') AS sheet_title FROM documents WHERE deleted_at IS NULL ORDER BY updated DESC")]

    def trash_list(self):
        self.purge_expired()
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT id,title,updated,deleted_at FROM documents WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")]

    def purge_expired(self):
        cutoff = (datetime.now(timezone.utc).timestamp() - TRASH_DAYS * 86400)
        with self.connect() as conn:
            rows = conn.execute("SELECT id,deleted_at FROM documents WHERE deleted_at IS NOT NULL").fetchall()
            expired = [row[0] for row in rows if self._timestamp(row[1]) <= cutoff]
            for ident in expired:
                conn.execute("DELETE FROM undo_actions WHERE document=?", (ident,))
                conn.execute("DELETE FROM history WHERE document=?", (ident,))
                conn.execute("DELETE FROM documents WHERE id=?", (ident,))
        return expired

    @staticmethod
    def _timestamp(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            return 0

    def trash(self, ident, expected_version):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body,deleted_at FROM documents WHERE id=?", (ident,)).fetchone()
            if row is None or row[1] is not None:
                raise KeyError(ident)
            if json.loads(row[0])["version"] != expected_version:
                raise Conflict("导图刚被修改，请查看最新内容后重新确认删除。")
            conn.execute("UPDATE documents SET deleted_at=?,updated=? WHERE id=?", (now(), now(), ident))

    def restore(self, ident):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id,deleted_at FROM documents WHERE id=?", (ident,)).fetchone()
            if row is None or row[1] is None:
                raise KeyError(ident)
            conn.execute("UPDATE documents SET deleted_at=NULL,updated=? WHERE id=?", (now(), ident))

    def purge(self, ident):
        """Permanently remove a document that is already in the recycle bin."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id,deleted_at FROM documents WHERE id=?", (ident,)).fetchone()
            if row is None or row[1] is None:
                raise KeyError(ident)
            conn.execute("DELETE FROM undo_actions WHERE document=?", (ident,))
            conn.execute("DELETE FROM history WHERE document=?", (ident,))
            conn.execute("DELETE FROM documents WHERE id=?", (ident,))

    def delete(self, ident, expected_version):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body FROM documents WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            if json.loads(row[0])["version"] != expected_version:
                raise Conflict("导图刚被修改，请查看最新内容后重新确认删除。")
            conn.execute("DELETE FROM undo_actions WHERE document=?", (ident,))
            conn.execute("DELETE FROM history WHERE document=?", (ident,))
            conn.execute("DELETE FROM documents WHERE id=?", (ident,))

    def update(self, ident, op, actor):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body FROM documents WHERE id=? AND deleted_at IS NULL", (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            original = json.loads(row[0])
            if op.get("kind") == "undo":
                action = conn.execute("SELECT body FROM undo_actions WHERE token=? AND document=?",
                                      (str(op.get("token", "")), ident)).fetchone()
                if action is None:
                    raise Conflict("该撤销记录已过期，请使用历史版本。")
                changes = json.loads(action[0])
                doc = copy.deepcopy(original)
                for change in changes:
                    if "node" in change:
                        actual = doc["nodes"].get(change["node"])
                        expected = change["after"]
                        comparable = lambda value: {k: v for k, v in value.items() if k != "rev"} if value else value
                        matches = comparable(actual) == comparable(expected)
                    else:
                        actual_exists = change["property"] in doc
                        matches = actual_exists == change.get("after_exists", True) and (not actual_exists or doc[change["property"]] == change.get("after"))
                    if not matches:
                        raise Conflict("相关内容已被其他操作修改，为避免覆盖协作者的内容，本次不能撤销。可查看历史版本。")
                for change in changes:
                    if "node" in change:
                        restored = copy.deepcopy(change["before"])
                        if restored is None:
                            doc["nodes"].pop(change["node"], None)
                        else:
                            doc["nodes"][change["node"]] = restored
                    elif change.get("before_exists", True):
                        doc[change["property"]] = copy.deepcopy(change.get("before"))
                    else:
                        doc.pop(change["property"], None)
                doc["version"] += 1
                # Refresh field revisions to prevent old editor drafts from overwriting a restored value.
                for change in changes:
                    if "node" in change and change["node"] in doc["nodes"]:
                        doc["nodes"][change["node"]]["rev"] = dict.fromkeys(("title", "notes", "color", "parent"), doc["version"])
                validate(doc)
                conn.execute("DELETE FROM undo_actions WHERE token=?", (str(op["token"]),))
                result = {"selected": op.get("selected") if op.get("selected") in doc["nodes"] else doc["root"]}
            else:
                doc, result = apply_operation(original, op)
            changes = [{"node": key, "before": original["nodes"].get(key), "after": doc["nodes"].get(key)}
                       for key in original["nodes"].keys() | doc["nodes"].keys()
                       if original["nodes"].get(key) != doc["nodes"].get(key)]
            for key in DOC_FIELDS:
                if original.get(key) != doc.get(key) or (key in original) != (key in doc):
                    changes.append({"property": key, "before_exists": key in original,
                                    "before": original.get(key), "after_exists": key in doc,
                                    "after": doc.get(key)})
            token = uid()
            conn.execute("INSERT INTO undo_actions VALUES (?, ?, ?, ?)",
                         (token, ident, json.dumps(changes, ensure_ascii=False), doc["version"]))
            conn.execute("DELETE FROM undo_actions WHERE document=? AND token NOT IN (SELECT token FROM undo_actions WHERE document=? ORDER BY version DESC LIMIT 200)", (ident, ident))
            result["undo_token"] = token
            self.write(conn, doc, actor, history_summary(original, doc, op))
        return doc, result

    def versions(self, ident):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT version,created,actor,COALESCE(NULLIF(summary,''),'未记录详细操作（旧版本）') AS summary FROM history WHERE document=? ORDER BY version DESC", (ident,))]

    def history_page(self, ident, before=None, limit=HISTORY_PAGE_SIZE):
        limit = max(1, min(int(limit), HISTORY_PAGE_SIZE))
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM history WHERE document=?", (ident,)).fetchone()[0]
            query = "SELECT version,created,actor,COALESCE(NULLIF(summary,''),'未记录详细操作（旧版本）') AS summary FROM history WHERE document=?"
            params = [ident]
            if before is not None:
                query += " AND version<?"
                params.append(before)
            query += " ORDER BY version DESC LIMIT ?"
            params.append(limit + 1)
            rows = [dict(row) for row in conn.execute(query, params)]
        return {"items": rows[:limit], "has_more": len(rows) > limit, "total": total}

    def history(self, ident, version):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM history WHERE document=? AND version=?", (ident, version)).fetchone()
        if row is None:
            raise KeyError(version)
        return json.loads(row[0])


def import_documents(data, filename):
    """Parse every sheet before saving anything; no worksheet is silently skipped."""
    warnings = []
    if filename.lower().endswith(".json"):
        doc = tree_json_loads(data.decode("utf-8-sig"))
        validate(doc)
        doc["id"], doc["version"] = uid(), 0
        for n in doc["nodes"].values():
            n["rev"] = {key: 0 for key in ("title", "notes", "color", "parent")}
        return [doc], warnings
    if not filename.lower().endswith(".xmind"):
        raise ValueError("请选择 .xmind 或本应用导出的 .json 文件。")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        def read(name):
            info = archive.getinfo(name)
            if info.file_size > MAX_FILE:
                raise ValueError(f"XMind 内容「{name}」解压后超过 {MAX_FILE // 1024 // 1024} MB，请拆分文件或减少图片。")
            return archive.read(name)
        modern = False
        sheets = tree_json_loads(read("content.json")) if "content.json" in archive.namelist() else None
        if sheets is not None and (not isinstance(sheets, list) or not sheets):
            raise ValueError("没有找到 XMind 工作表。")
        if "mindcollab.json" in archive.namelist() and (
                (sheets is not None and len(sheets) == 1) or
                (sheets is None and "content.xml" not in archive.namelist())):
            doc = tree_json_loads(read("mindcollab.json"))
            validate(doc)
            doc["id"], doc["version"] = uid(), 0
            for n in doc["nodes"].values():
                n["rev"] = {key: 0 for key in ("title", "notes", "color", "parent")}
            warnings.append("已从 GNN 数据完整恢复；原 XMind 文件未被修改。")
            return [doc], warnings
        if "content.json" in archive.namelist():
            modern = True
            def style(t, depth):
                theme_key = "centralTopic" if depth == 0 else "mainTopic" if depth == 1 else "subTopic"
                base = theme.get(theme_key, {})
                base = base.get("properties", {}) if isinstance(base, dict) else {}
                local = t.get("style", {})
                local = local.get("properties", {}) if isinstance(local, dict) else {}
                base = base if isinstance(base, dict) else {}
                local = local if isinstance(local, dict) else {}
                return clean_style({**base, **local})
            def structure(t):
                return t.get("structureClass", "")
            def children(t):
                groups = t.get("children", {})
                if not isinstance(groups, dict) or any(not isinstance(groups.get(key, []), list) for key in ("attached", "detached")):
                    raise ValueError("XMind 子主题列表无效。")
                return groups.get("attached", []) + groups.get("detached", [])
            def title(t):
                return t.get("title", "未命名")
            def notes(t):
                value = t.get("notes", {}).get("plain", {})
                return value.get("content", "") if isinstance(value, dict) else ""
            def topic_meta(t):
                result = {}
                labels = t.get("labels", [])
                if isinstance(labels, list):
                    result["labels"] = [str(v)[:24] for v in labels[:8]]
                if isinstance(t.get("href"), str) and (not t["href"] or t["href"].startswith(("http://", "https://", "mailto:"))):
                    result["link"] = t["href"]
                for marker in t.get("markers", []) if isinstance(t.get("markers", []), list) else []:
                    marker_id = marker.get("markerId", "") if isinstance(marker, dict) else ""
                    if marker_id.startswith("priority-") and marker_id[-1:] in "12345":
                        result["priority"] = int(marker_id[-1])
                    tasks = {"task-start": 0, "task-quarter": 25, "task-half": 50, "task-3quar": 75, "task-done": 100}
                    if marker_id in tasks:
                        result["progress"] = tasks[marker_id]
                image = t.get("image", {})
                source = image.get("src", "") if isinstance(image, dict) else ""
                if source.startswith("xap:"):
                    path = source[4:].lstrip("/")
                    if path in archive.namelist() and archive.getinfo(path).file_size <= 300000:
                        raw = read(path)
                        suffix = Path(path).suffix.lower()
                        mime = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}.get(suffix)
                        if mime:
                            result["image"] = f"data:image/{mime};base64," + base64.b64encode(raw).decode()
                return result
        elif "content.xml" in archive.namelist():
            raw = read("content.xml")
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("不支持带有外部实体的 XML。")
            xml = ET.fromstring(raw)
            ns = {"x": "urn:xmind:xmap:xmlns:content:2.0"}
            sheets = xml.findall("x:sheet", ns)
            if not sheets:
                raise ValueError("没有找到旧版 XMind 工作表。")
            styles = {}
            background = None
            theme = {}
            if "styles.xml" in archive.namelist():
                style_raw = read("styles.xml")
                if b"<!DOCTYPE" in style_raw.upper() or b"<!ENTITY" in style_raw.upper():
                    raise ValueError("不支持带有外部实体的样式 XML。")
                style_xml = ET.fromstring(style_raw)
                for element in style_xml.iter():
                    if element.tag.rsplit("}", 1)[-1] == "style" and element.get("id"):
                        properties = {}
                        for child in element:
                            for key, value in child.attrib.items():
                                if key.startswith("{"):
                                    namespace, local = key[1:].split("}", 1)
                                    prefix = "svg:" if "svg" in namespace else "fo:" if "xsl" in namespace else ""
                                    key = prefix + local
                                properties[key] = value
                        styles[element.get("id")] = clean_style(properties)
            def style(t, depth):
                family = "centralTopic" if depth == 0 else "mainTopic" if depth == 1 else "subTopic"
                return {**theme.get(family, {}), **styles.get(t.get("style-id"), {})}
            def structure(t):
                return t.get("structure-class", "")
            def children(t):
                return t.findall("x:children/x:topics/x:topic", ns)
            def title(t):
                return t.findtext("x:title", "未命名", ns)
            def notes(t):
                return t.findtext("x:notes/x:plain", "", ns)
            def topic_meta(t):
                return {}
        else:
            raise ValueError("未找到 content.json 或 content.xml。")
        documents, workbook = [], uid()
        for sheet_index, sheet in enumerate(sheets):
            if modern:
                if not isinstance(sheet, dict) or not isinstance(sheet.get("rootTopic"), dict):
                    raise ValueError(f"第 {sheet_index + 1} 个工作表缺少有效的中心主题。")
                topic = sheet["rootTopic"]
                sheet_title = str(sheet.get("title") or title(topic) or f"工作表 {sheet_index + 1}")
                theme = sheet.get("theme", {})
                theme = theme if isinstance(theme, dict) else {}
                map_theme = theme.get("map", {})
                background = clean_style(map_theme.get("properties", {}) if isinstance(map_theme, dict) else {}).get("fill")
            else:
                topic = sheet.find("x:topic", ns)
                sheet_title = sheet.findtext("x:title", "", ns) or f"工作表 {sheet_index + 1}"
                theme, background = {}, None
                if "styles.xml" in archive.namelist():
                    theme_element = next((element for element in style_xml.iter()
                                          if sheet.get("theme") and element.get("id") == sheet.get("theme")), None)
                    if theme_element is not None:
                        for element in theme_element.iter():
                            if element.tag.rsplit("}", 1)[-1] == "default-style":
                                theme[element.get("style-family")] = styles.get(element.get("style-id"), {})
                    background = theme.get("map", {}).get("fill")
            doc = {"id": uid(), "root": None, "nodes": {}, "version": 0}
            doc["source"] = {"filename": Path(filename).name, "kind": "xmind",
                             "workbook": workbook, "sheet_id": sheet.get("id"),
                             "sheet_title": sheet_title, "sheet_index": sheet_index, "sheet_count": len(sheets)}
            if background and background != "none":
                doc["background"] = background
            if topic is None:
                raise ValueError(f"第 {sheet_index + 1} 个工作表「{sheet_title}」缺少中心主题。")
            root_structure = structure(topic)
            doc["layout"] = ("right" if root_structure.endswith(".right") else "left" if root_structure.endswith(".left")
                             else "down" if root_structure.endswith(".down") else "up" if root_structure.endswith(".up") else "balanced")
            source_ids = {}
            stack = [(topic, None, 0)]
            while stack:
                t, parent, depth = stack.pop()
                if t is None or (modern and not isinstance(t, dict)):
                    raise ValueError("XMind 包含无效的主题内容。")
                n = node(str(title(t) or "未命名"), parent)
                n["notes"] = str(notes(t))
                n["style"] = style(t, depth)
                meta = topic_meta(t)
                if meta:
                    n["meta"] = meta
                doc["nodes"][n["id"]] = n
                if parent is None:
                    doc["root"] = n["id"]
                else:
                    doc["nodes"][parent]["children"].append(n["id"])
                if isinstance(t.get("id"), str):
                    source_ids[t.get("id")] = n["id"]
                stack.extend((child, n["id"], depth + 1) for child in reversed(children(t)))
            relationships = sheet.get("relationships", []) if modern else [
                {"end1Id": r.get("end1"), "end2Id": r.get("end2"), "title": r.findtext("x:title", "", ns)}
                for r in sheet.findall("x:relationships/x:relationship", ns)]
            doc["relationships"] = [{"id": uid(), "from": source_ids[r["end1Id"]], "to": source_ids[r["end2Id"]], "title": str(r.get("title", ""))[:120]}
                                    for r in relationships if isinstance(r, dict) and r.get("end1Id") in source_ids and r.get("end2Id") in source_ids and r.get("end1Id") != r.get("end2Id")]
            validate(doc)
            documents.append(doc)
        warnings.append("已导入节点层级、纯文本备注及可识别的样式、布局、标签、任务标记、链接、节点图片和关系线。附件、公式、复杂主题效果及部分边界/概要不能完全还原；原文件不会被覆盖。")
        return documents, warnings


def import_data(data, filename):
    """Compatibility helper for callers that require exactly one document."""
    documents, warnings = import_documents(data, filename)
    if len(documents) != 1:
        raise ValueError("文件包含多个工作表，请使用全部工作表导入入口。")
    return documents[0], warnings


class Rooms:
    def __init__(self):
        self.peers, self.locks = {}, {}

    def lock(self, ident):
        return self.locks.setdefault(ident, asyncio.Lock())

    async def broadcast(self, ident, message):
        for ws in list(self.peers.get(ident, {})):
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=2)
            except Exception:
                self.peers[ident].pop(ws, None)

    async def presence(self, ident):
        await self.broadcast(ident, {"type": "presence", "users": list(self.peers.get(ident, {}).values())})


def create_app(database=None):
    store = Store(database or os.environ.get("MINDCOLLAB_DB", BASE / "data" / "mindcollab.sqlite3"))
    rooms = Rooms()

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title="GNN 协作思维导图", lifespan=lifespan)
    app.state.store = store
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def request_actor(request):
        raw = request.headers.get("x-gnn-name", "")
        try:
            return clean_display_name(unquote(raw))
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.middleware("http")
    async def local_origin_guard(request: Request, call_next):
        # No account system in this LAN prototype. Reject cross-origin writes.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "不允许跨站写入。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/documents")
    async def documents():
        return store.list()

    @app.get("/api/trash")
    async def trash():
        return store.trash_list()

    @app.post("/api/trash/{ident}/restore")
    async def restore(ident: str, request: Request):
        request_actor(request)
        try:
            store.restore(ident)
        except KeyError:
            raise HTTPException(404, "回收站中没有这张导图，或已自动清理。")
        # A restore changes the workspace list just like a delete. Notify
        # every connected document room so other open workspaces refresh.
        for room in list(rooms.peers):
            await rooms.broadcast(room, {"type": "document_restored", "id": ident})
        return store.get(ident)

    @app.delete("/api/trash/{ident}")
    async def purge_trash(ident: str, request: Request):
        request_actor(request)
        async with rooms.lock(ident):
            try:
                store.purge(ident)
            except KeyError:
                raise HTTPException(404, "回收站中没有这张导图，或已被彻底删除。")
            for room in list(rooms.peers):
                await rooms.broadcast(room, {"type": "document_purged", "id": ident})
        return {"purged": ident}

    @app.get("/api/storage")
    async def storage():
        return {"database": str(store.path.resolve()), "original_files_modified": False}

    @app.post("/api/documents")
    async def create(request: Request):
        return store.create(new_document(), request_actor(request))

    @app.get("/api/documents/{ident}")
    async def get(ident: str):
        try:
            return store.get(ident)
        except KeyError:
            raise HTTPException(404, "文档不存在。")

    @app.get("/api/documents/{ident}/export/xmind")
    async def download_xmind(ident: str):
        from urllib.parse import quote
        try:
            doc = store.get(ident)
        except KeyError:
            raise HTTPException(404, "文档不存在。")
        filename = re.sub(r'[\\/:*?"<>|]', "_", doc["nodes"][doc["root"]]["title"])[:60] or "mindmap"
        return Response(export_xmind(doc), media_type="application/x-xmind",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}.xmind"})

    @app.delete("/api/documents/{ident}")
    async def delete_document(ident: str, expected_version: int, request: Request):
        request_actor(request)
        async with rooms.lock(ident):
            try:
                store.trash(ident, expected_version)
            except KeyError:
                raise HTTPException(404, "文档不存在。")
            except Conflict as exc:
                raise HTTPException(409, str(exc))
            # Notify every connected workspace so each sidebar refreshes. The
            # client only closes its editor when the deleted id is active.
            for room in list(rooms.peers):
                await rooms.broadcast(room, {"type": "document_deleted", "id": ident})
        return {"trashed": ident}

    @app.get("/api/documents/{ident}/history")
    async def history(ident: str, before: int | None = None):
        return store.history_page(ident, before)

    @app.post("/api/documents/{ident}/history/{version}/copy")
    async def copy_version(ident: str, version: int, request: Request):
        actor = request_actor(request)
        try:
            doc = store.history(ident, version)
        except KeyError:
            raise HTTPException(404, "历史版本不存在。")
        doc["id"], doc["version"] = uid(), 0
        root = doc["nodes"][doc["root"]]
        root["title"] = (root["title"][:175] + f" · v{version} 副本")[:200]
        for n in doc["nodes"].values():
            n["rev"] = {key: 0 for key in ("title", "notes", "color", "parent")}
        return store.create(doc, actor, f"从历史版本 v{version} 创建副本")

    @app.post("/api/import")
    async def import_file(request: Request, file: UploadFile):
        actor = request_actor(request)
        data = await file.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise HTTPException(413, f"文件超过 {MAX_FILE // 1024 // 1024} MB，请拆分文件或减少图片。")
        try:
            documents, warnings = import_documents(data, file.filename or "")
            store.create_many(documents, actor, file.filename or "未命名文件")
            imported = [{"id": doc["id"], "title": doc["nodes"][doc["root"]]["title"],
                         "sheet_title": doc.get("source", {}).get("sheet_title"),
                         "node_count": len(doc["nodes"])} for doc in documents]
            return {"document": documents[0], "documents": imported, "warnings": warnings}
        except (ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile, ET.ParseError, RecursionError) as exc:
            raise HTTPException(400, f"无法导入：{str(exc)[:200]}")

    @app.websocket("/ws/{ident}")
    async def collaborate(ws: WebSocket, ident: str):
        origin = ws.headers.get("origin")
        if origin and urlsplit(origin).netloc != ws.headers.get("host"):
            await ws.close(code=1008)
            return
        await ws.accept()
        peer_id = uid()
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=15)
            identity = json.loads(raw)
            if not isinstance(identity, dict) or identity.get("type") != "identify":
                raise ValueError("请先输入姓名后再打开导图。")
            name = clean_display_name(identity.get("name"))
        except (asyncio.TimeoutError, json.JSONDecodeError, TypeError, ValueError) as exc:
            message = str(exc) or "请输入姓名后重试。"
            await ws.send_json({"type": "error", "message": message[:300], "request": ""})
            await ws.close(code=1008, reason="姓名无效")
            return
        lock = rooms.lock(ident)
        try:
            async with lock:
                try:
                    doc = store.get(ident)
                except KeyError:
                    await ws.close(code=1008, reason="文档不存在")
                    return
                rooms.peers.setdefault(ident, {})[ws] = {"id": peer_id, "name": name, "selected": None}
                await ws.send_json({"type": "welcome", "peer": peer_id, "document": doc})
                await rooms.presence(ident)
            while True:
                raw = await ws.receive_text()
                if len(raw.encode("utf-8")) > MAX_MESSAGE:
                    await ws.send_json({"type": "error", "message": "操作数据超过 128 MB，请分批粘贴。", "request": ""})
                    continue
                message = None
                try:
                    message = tree_json_loads(raw)
                    if not isinstance(message, dict):
                        raise ValueError("消息格式无效。")
                    async with lock:
                        if ws not in rooms.peers.get(ident, {}):
                            await ws.close(code=1011)
                            break
                        if message.get("type") == "presence":
                            peer = rooms.peers[ident][ws]
                            peer["selected"] = message.get("selected") if isinstance(message.get("selected"), str) else None
                            await rooms.presence(ident)
                        elif message.get("type") == "operation":
                            op = message.get("op")
                            if not isinstance(op, dict):
                                raise ValueError("操作格式无效。")
                            doc, result = store.update(ident, op, name)
                            await rooms.broadcast(ident, {"type": "state", "document": doc, "source": peer_id,
                                                          "request": str(message.get("request", ""))[:80], "result": result})
                        else:
                            raise ValueError("未知消息类型。")
                except (ValueError, TypeError, KeyError) as exc:
                    await ws.send_json({"type": "error", "message": str(exc)[:300],
                                        "request": str(message.get("request", ""))[:80] if isinstance(message, dict) else ""})
        except WebSocketDisconnect:
            pass
        finally:
            async with lock:
                rooms.peers.get(ident, {}).pop(ws, None)
                await rooms.presence(ident)

    return app


app = create_app()
