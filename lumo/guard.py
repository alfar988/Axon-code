"""A first line of defence: blatant requests to build malware, fraud tools or weapons are refused on the spot,
before any model request is spent.

The real protection is prompts/safety-rules.md (always in the prompt) and skills/safety-skill.md. This module only
stops the obvious cases cheaply. It looks at one sentence at a time and stays quiet for defensive and educational
wording (detect, remove, explain, protect, what is ...), so ordinary security work is not blocked.
"""

import re

_MAKE = (r"(?:\b(?:build|make|create|write|code|develop|generate|program|script|design)\b|"
         r"\bhow (?:do i|to|can i|would i) (?:make|build|create|write|code)\b|"
         r"\b(?:buat|membuat|bikin|membikin|tulis|menulis|kembangkan|rancang|susun)(?:kan|in)?\b|\bcara (?:buat|bikin|membuat)\b)")

_TOOL = (r"(?:ransomware|key ?logger|info ?stealer|"
         r"(?:credential|password|cookie|token|session|wallet|discord token) ?(?:stealer|grabber|logger|harvester)|"
         r"botnet|remote access trojan|\bnj ?rat\b|\basync ?rat\b|rootkit|spyware|stalkerware|"
         r"computer virus|virus komputer|"
         r"ddos(?:er)?(?: tool| script| attack| bot| program| serangan)?|"
         r"phishing (?:page|site|kit|website|link|email)|(?:halaman|situs|link|web) phishing|fake (?:login|bank) (?:page|site)|"
         r"crypto ?drainer|wallet ?drainer|card ?skimmer|\bcarding\b|sim ?swap(?:ping)?|otp (?:bypass|interceptor|stealer)|"
         r"pencuri (?:password|akun|cookie|data))")

_TOOL_SOFT = r"(?:malware|trojan)"   # blocked too, unless the sentence is clearly about a game or a story

_DANGER = (r"(?:\b(?:how (?:do i|to|can i) (?:make|build|cook|synthesi[sz]e|produce)|make|build|synthesi[sz]e|cook|"
           r"cara (?:membuat|bikin|buat|meracik)|bikin|membuat|buatkan)\b "
           r"(?:a |an |the |some |real |homemade |pipe |nail |improvised )*"
           r"(?:bomb|explosives?|bom|bahan peledak|molotov(?: cocktail)?|napalm|nerve agent|sarin|ricin|"
           r"meth(?:amphetamine)?|sabu(?:-sabu)?|cocaine|heroin|fentanyl|ghost gun|senjata rakitan|racun mematikan))")

_SAFE = (r"(?:\b(?:detect|detection|protect|protection|defend|defense|defence|prevent|remove|clean|scan|scanner|analy[sz]e|"
         r"explain|understand|what is|how does|learn about|awareness|training|antivirus|mitigat\w*|harden\w*|"
         r"cegah|lindungi|melindungi|hapus|bersihkan|deteksi|apa itu|jelaskan|pelajari|cara kerja|waspada)\b)")

_GAME_OR_STORY = r"\b(?:game|roblox|minecraft|bomberman|story|novel|cerita|fiksi|fiction|film|cartoon|animasi|level|npc)\b"
_ID_WORDS = r"\b(?:buat(?:kan)?|bikin|tolong|saya|aku|gue|yang|dan|untuk|cara|dengan|membuat)\b"

REFUSAL_EN = ("I will not help build malware, account-theft or fraud tools, weapons, or anything meant to hurt people. "
              "If your goal is defensive (detect it, remove it, harden a system, or understand how it works), tell me that and I will help with it.")
REFUSAL_ID = ("Saya tidak akan membantu membuat malware, alat pencuri akun, penipuan, senjata, atau apa pun yang dimaksudkan untuk mencelakai orang. "
              "Kalau tujuanmu defensif (mendeteksi, membersihkan, memperkuat keamanan, atau memahami cara kerjanya), bilang saja dan saya bantu.")


def _sentences(text):
    for s in re.split(r"[.!?;\n]+", text[:3000]):
        s = s.strip().lower()
        if s:
            yield s


def blocked_reason(text):
    """'malware' or 'danger' when the request is blatantly harmful, else None."""
    for s in _sentences(text):
        if re.search(_SAFE, s):
            continue
        if re.search(_MAKE, s) and re.search(_TOOL, s):
            return "malware"
        if re.search(_MAKE, s) and re.search(_TOOL_SOFT, s) and not re.search(_GAME_OR_STORY, s):
            return "malware"
        if re.search(_DANGER, s) and not re.search(_GAME_OR_STORY, s):
            return "danger"
    return None


def check_request(text):
    """The refusal text (in the user's language) for a blatantly harmful request, or None."""
    if not blocked_reason(text or ""):
        return None
    return REFUSAL_ID if len(re.findall(_ID_WORDS, (text or "").lower())) >= 2 else REFUSAL_EN
