"""Tool registry: the @tool decorator and schema helpers."""


TOOLS = {}


def S(d, **kw):
    return dict({"type": "string", "description": d}, **kw)


def I(d):
    return {"type": "integer", "description": d}


def B(d):
    return {"type": "boolean", "description": d}


def L(d):
    return {"type": "array", "description": d, "items": {"type": "string"}}


def tool(name, desc, props, required=()):
    def deco(fn):
        TOOLS[name] = {"fn": fn, "schema": {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}}
        return fn
    return deco
