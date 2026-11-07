"""Anthropic Messages API: converts the internal (OpenAI-style) messages and tools to Anthropic's format, and reads the
answer back into the same shape the rest of the program uses: (message, finish_reason, usage, reasoning)."""

import json
import time

from lumo.state import ApiError

STOP_MAP = {"end_turn": "stop", "stop_sequence": "stop", "pause_turn": "stop", "refusal": "stop",
            "max_tokens": "length", "tool_use": "tool_calls"}


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return "" if content is None else str(content)


def convert_messages(messages):
    """Returns (system_text, anthropic_messages). Consecutive turns of one role are merged, tool results come first in a
    user turn, and the conversation always starts with a user turn, as the API requires."""
    system, out = [], []

    def push(role, blocks):
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            if _text(content).strip():
                system.append(_text(content))
        elif role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id") or "", "content": _text(content) or "(no output)"}])
        elif role == "assistant":
            blocks = []
            if _text(content).strip():
                blocks.append({"type": "text", "text": _text(content)})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc.get("id") or "call_0", "name": fn.get("name", ""),
                               "input": args if isinstance(args, dict) else {"value": args}})
            if blocks:
                push("assistant", blocks)
        else:
            txt = _text(content)
            push("user", [{"type": "text", "text": txt if txt.strip() else "(empty)"}])
    for m in out:
        if m["role"] == "user":
            m["content"].sort(key=lambda b: 0 if b["type"] == "tool_result" else 1)     # stable: results first
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(start)"}]})
    return "\n\n".join(system), out


def convert_tools(tools):
    res = []
    for t in tools or []:
        fn = t.get("function") or {}
        schema = fn.get("parameters") or {"type": "object", "properties": {}}
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": {}}
        res.append({"name": fn.get("name", ""), "description": fn.get("description", ""), "input_schema": schema})
    return res


def build_body(model, messages, tools, max_tokens, temperature, stream):
    system, msgs = convert_messages(messages)
    body = {"model": model, "max_tokens": int(max_tokens or 8192), "messages": msgs, "stream": bool(stream)}
    if temperature is not None:
        body["temperature"] = temperature
    if system:
        body["system"] = system
    if tools:
        body["tools"] = convert_tools(tools)
        body["tool_choice"] = {"type": "auto"}
    return body


def _usage(u):
    u = u or {}
    prompt = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
    comp = u.get("output_tokens") or 0
    return {"prompt_tokens": prompt, "completion_tokens": comp, "total_tokens": prompt + comp}


def _error_kind(err_type):
    return {"rate_limit_error": "rate", "overloaded_error": "server", "api_error": "server", "authentication_error": "auth",
            "permission_error": "forbidden", "not_found_error": "notfound", "request_too_large": "ctx"}.get(err_type, "server")


def _message(text_parts, calls):
    msg = {"role": "assistant", "content": "".join(text_parts) or None}
    tcs = []
    for i, c in enumerate(calls):
        if c["name"]:
            tcs.append({"id": c["id"] or "toolu_%d_%d" % (int(time.time()), i), "type": "function",
                        "function": {"name": c["name"], "arguments": c["args"] or "{}"}})
    if tcs:
        msg["tool_calls"] = tcs
    return msg


def read_json(resp, on_text):
    data = json.loads(resp.read().decode("utf-8", "replace"))
    if data.get("type") == "error":
        e = data.get("error") or {}
        raise ApiError(e.get("message") or "provider error", retryable=True, kind=_error_kind(e.get("type")))
    texts, calls, thinking = [], [], []
    for b in data.get("content") or []:
        if b.get("type") == "text":
            texts.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            calls.append({"id": b.get("id"), "name": b.get("name", ""), "args": json.dumps(b.get("input") or {})})
        elif b.get("type") == "thinking":
            thinking.append(b.get("thinking", ""))
    if texts:
        on_text("".join(texts))
    return _message(texts, calls), STOP_MAP.get(data.get("stop_reason"), "stop"), _usage(data.get("usage")), "".join(thinking)


def read_stream(resp, on_text, on_status, emitted, stall_secs, max_secs):
    blocks, usage, finish = {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None
    thinking, stopped = [], False
    t0 = last = time.time()
    for raw in resp:
        now = time.time()
        if now - t0 > max_secs:
            raise ApiError("response took too long (> %d s)" % max_secs, retryable=not emitted[0], kind="stall")
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            if now - last > stall_secs:
                raise ApiError("model silent for %d s with no output" % stall_secs, retryable=not emitted[0], kind="stall")
            continue
        try:
            ev = json.loads(line[5:].strip())
        except ValueError:
            continue
        kind = ev.get("type")
        if kind != "ping":
            last = now
        if kind == "message_start":
            usage = _usage((ev.get("message") or {}).get("usage"))
        elif kind == "content_block_start":
            cb = ev.get("content_block") or {}
            idx = ev.get("index", len(blocks))
            blocks[idx] = {"type": cb.get("type"), "id": cb.get("id"), "name": cb.get("name", ""), "text": cb.get("text", "") or "", "args": ""}
            if cb.get("type") == "tool_use":
                emitted[0] = True
                if on_status and cb.get("name"):
                    on_status("preparing " + cb["name"])
            elif blocks[idx]["text"]:
                emitted[0] = True
                on_text(blocks[idx]["text"])
        elif kind == "content_block_delta":
            d = ev.get("delta") or {}
            b = blocks.setdefault(ev.get("index", 0), {"type": "text", "id": None, "name": "", "text": "", "args": ""})
            if d.get("type") == "text_delta" and d.get("text"):
                b["text"] += d["text"]
                emitted[0] = True
                on_text(d["text"])
            elif d.get("type") == "input_json_delta":
                b["args"] += d.get("partial_json") or ""
                emitted[0] = True
            elif d.get("type") == "thinking_delta":
                thinking.append(d.get("thinking") or "")
                if on_status:
                    on_status("thinking")
        elif kind == "message_delta":
            d = ev.get("delta") or {}
            if d.get("stop_reason"):
                finish = STOP_MAP.get(d["stop_reason"], "stop")
            u = ev.get("usage") or {}
            if u.get("output_tokens") is not None:
                usage["completion_tokens"] = u["output_tokens"]
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        elif kind == "message_stop":
            stopped = True
            break
        elif kind == "error":
            e = ev.get("error") or {}
            raise ApiError(e.get("message") or "the provider returned an error mid-stream", retryable=not emitted[0], kind=_error_kind(e.get("type")))
    if not stopped and finish is None:
        raise ApiError("connection dropped mid-answer (stream did not finish)", retryable=not emitted[0], kind="net")
    ordered = [blocks[i] for i in sorted(blocks)]
    texts = [b["text"] for b in ordered if b["type"] == "text"]
    calls = [b for b in ordered if b["type"] == "tool_use"]
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return _message(texts, calls), finish or "stop", usage, "".join(thinking)
