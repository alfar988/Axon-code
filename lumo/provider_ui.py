"""/provider and /key: choose the AI provider and store one API key per provider."""

from lumo import providers
from lumo.models import auto_pick_model
from lumo.state import ensure_key, key_of, mask_key, prompt_key, save_config, validate_key
from lumo.ui import acc, bold, clip, dim, err, ok, out, rl, rule, tw, warn


def provider_rows(ctx):
    out()
    out(rule("Providers"))
    cur = providers.active(ctx.cfg)["id"]
    for i, p in enumerate(providers.PROVIDERS, 1):
        has = (not providers.needs_key(p)) or bool(providers.key_for(ctx.cfg, p))
        mark = ok("●") if p["id"] == cur else (ok("✓") if has else " ")
        out("  %s %s %s %s" % (mark, acc("%2d" % i), p["name"].ljust(30)[:30], dim(clip(p["note"], max(8, tw() - 42)))))
    out("  " + dim("● active · ✓ key saved · switch: /provider <name or number> · key for another provider: /key <name>"))


def pick(name):
    name = str(name or "").strip()
    if name.isdigit() and 1 <= int(name) <= len(providers.PROVIDERS):
        return providers.PROVIDERS[int(name) - 1]
    return providers.find(name)


def choose_provider(ctx, first_run=False):
    """Interactive menu (first run and --setup). Returns the provider, or None when the user gave up."""
    provider_rows(ctx)
    try:
        ans = input(rl("  " + acc("▍") + " " + dim("choose a provider (Enter = 1, OpenRouter with free models) › "))).strip()
    except EOFError:
        ans = ""
    prov = pick(ans or "1")
    if not prov:
        out("  " + err("no such provider"))
        return None
    return use_provider(ctx, prov, ask_key=False)


def use_provider(ctx, prov, ask_key=True):
    if prov.get("custom") and not ctx.cfg.get("custom_base"):
        try:
            base = input(rl("  " + acc("▍") + " " + dim("base URL of the OpenAI-compatible API (for example https://host/v1) › "))).strip()
        except EOFError:
            base = ""
        if not base.startswith(("http://", "https://")):
            out("  " + err("a base URL must start with http:// or https://"))
            return None
        ctx.cfg["custom_base"] = base.rstrip("/")
    providers.switch(ctx.cfg, prov["id"])
    ctx.key = None
    ctx.override = None
    ctx.models_all = None
    ctx.models_provider = None
    save_config(ctx.cfg)
    if ask_key and providers.needs_key(prov) and not key_of(ctx):
        if not ensure_key(ctx, force=True):
            out("  " + warn("no key saved for %s yet; set it with /key" % prov["name"]))
    return prov


def cmd_provider(ctx, arg):
    if not arg:
        provider_rows(ctx)
        return
    prov = pick(" ".join(arg))
    if not prov:
        out("  " + err("unknown provider: %s" % " ".join(arg)) + dim("  (see /provider)"))
        return
    if use_provider(ctx, prov):
        out("  " + ok("✓ provider: ") + prov["name"])
        if providers.needs_key(prov) and not key_of(ctx):
            return
        model = auto_pick_model(ctx)
        out("  " + dim("model ") + (model or "none yet: /models"))
        out("  " + dim("list the models: /models · remaining limit: /checklimit"))


def cmd_key(ctx, arg):
    """/key sets the key of the active provider; /key <provider> sets the key of another one without switching."""
    prov = pick(arg[0]) if arg else providers.active(ctx.cfg)
    if not prov:
        out("  " + err("unknown provider: %s" % arg[0]) + dim("  (see /provider)"))
        return
    if not providers.needs_key(prov):
        out("  " + dim("%s needs no key." % prov["name"]))
        return
    active = providers.active(ctx.cfg)["id"] == prov["id"]
    if active:
        ensure_key(ctx, force=True)
    else:
        prompt_key(ctx, prov)
