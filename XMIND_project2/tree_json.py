"""JSON interchange without Python's call-stack limit on nested XMind topics."""
import io
import json

import ijson


def loads(data):
    try:
        return json.loads(data)
    except RecursionError:
        # The streaming parser builds containers using a stack, even for deep maps.
        raw = data.encode("utf-8") if isinstance(data, str) else data
        try:
            return next(ijson.items(io.BytesIO(raw), "", use_float=True))
        except (ijson.JSONError, StopIteration) as exc:
            raise ValueError("JSON 内容无效或不完整。") from exc


def dumps(value):
    """Serialize nested topics iteratively; ordinary scalars use the JSON codec."""
    output = io.StringIO()
    active = set()
    stack = [("value", value)]
    while stack:
        kind, item = stack.pop()
        if kind == "text":
            output.write(item)
        elif kind == "end":
            active.remove(id(item))
            output.write("}" if isinstance(item, dict) else "]")
        elif isinstance(item, (dict, list)):
            if id(item) in active:
                raise ValueError("JSON 内容包含循环引用。")
            active.add(id(item))
            output.write("{" if isinstance(item, dict) else "[")
            stack.append(("end", item))
            entries = list(item.items()) if isinstance(item, dict) else list(enumerate(item))
            for index in range(len(entries) - 1, -1, -1):
                key, child = entries[index]
                stack.append(("value", child))
                if isinstance(item, dict):
                    stack.append(("text", json.dumps(str(key), ensure_ascii=False) + ":"))
                if index:
                    stack.append(("text", ","))
        else:
            output.write(json.dumps(item, ensure_ascii=False, allow_nan=False))
    return output.getvalue()
