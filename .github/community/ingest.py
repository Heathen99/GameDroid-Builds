#!/usr/bin/env python3
"""
Files a GameDroid community submission (a GitHub issue opened from the app) into community/.

Issue title: "[benchmark] <game>" or "[layout] <game>". Body contains a fenced block:
    ```gamedroid
    <json, or "gz:" + base64(gzip(json))>
    ```
Everything from the issue is untrusted: it is only read from the event JSON, parsed, validated against a
whitelist and re-serialised. Nothing from it reaches a shell. Output: writes files and prints a result line
("OK <message>" / "INVALID <reason>") to $GITHUB_OUTPUT as result=... and message=...
"""
import base64, gzip, json, os, re, sys, time

MAX_BLOCK = 200_000          # characters in the fenced block
MAX_LAYOUT_JSON = 150_000    # bytes of decompressed layout
MAX_RESULTS = 300            # benchmark results kept per game
MAX_LAYOUTS = 40             # layouts kept per game
APP_RE = re.compile(r"^(STEAM|GOG|EPIC|AMAZON)_[A-Za-z0-9_-]{1,64}$")
ROOT = "community"


def out(result, message):
    print(result, message)
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"result={result}\n")
            f.write("message<<__END__\n" + message.replace("__END__", "") + "\n__END__\n")


def text(v, n):
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v))[:n].strip() if v is not None else ""


def num(v, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 2) if lo <= x <= hi else None


def payload(body):
    m = re.search(r"```gamedroid\s*\n(.*?)\n```", body or "", re.S)
    if not m:
        raise ValueError("no ```gamedroid block in the issue body")
    block = m.group(1).strip()
    if len(block) > MAX_BLOCK:
        raise ValueError("submission too large")
    if block.startswith("gz:"):
        raw = gzip.decompress(base64.b64decode(block[3:], validate=False))
        if len(raw) > MAX_LAYOUT_JSON * 2:
            raise ValueError("submission too large")
        block = raw.decode("utf-8")
    data = json.loads(block)
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")


def bump_index(kind, app, count, name):
    idx = load(f"{ROOT}/index.json", {})
    idx.setdefault(kind, {})[app] = {"count": count, "name": name}
    save(f"{ROOT}/index.json", idx)


def benchmark(data, author, created):
    app = text(data.get("app"), 80)
    if not APP_RE.match(app):
        raise ValueError("bad app id")
    avg = num(data.get("avgFps"), 0.5, 1000)
    if avg is None:
        raise ValueError("avgFps missing or out of range")
    r = {
        "avgFps": avg,
        "low1": num(data.get("low1"), 0, 1000),
        "low01": num(data.get("low01"), 0, 1000),
        "seconds": num(data.get("seconds"), 5, 3600),
        "fpsCap": num(data.get("fpsCap"), 0, 1000),
        "resolution": text(data.get("resolution"), 16) if re.match(r"^\d{3,4}x\d{3,4}$", str(data.get("resolution", ""))) else "",
        "cpuAvg": num(data.get("cpuAvg"), 0, 100),
        "gpuAvg": num(data.get("gpuAvg"), 0, 100),
        "gpuTempMax": num(data.get("gpuTempMax"), 0, 150),
        "powerW": num(data.get("powerW"), 0, 100),
        "model": text(data.get("model"), 40),
        "soc": text(data.get("soc"), 40),
        "gpu": text(data.get("gpu"), 60),
        "driver": text(data.get("driver"), 80),
        "dxwrapper": text(data.get("dxwrapper"), 80),
        "frameGen": num(data.get("frameGen"), 0, 4),
        "build": text(data.get("build"), 20),
        "author": text(author, 40),
        "time": created,
    }
    r = {k: v for k, v in r.items() if v not in (None, "")}
    name = text(data.get("name"), 100)
    path = f"{ROOT}/benchmarks/{app}.json"
    doc = load(path, {"app": app, "name": name, "results": []})
    doc["name"] = name or doc.get("name", "")
    doc["results"] = (doc.get("results", []) + [r])[-MAX_RESULTS:]
    save(path, doc)
    bump_index("benchmarks", app, len(doc["results"]), doc["name"])
    return f"Thanks! Benchmark for {doc['name'] or app} saved ({avg:.0f} fps average)."


def layout(data, author, created, number):
    app = text(data.get("app"), 80)
    if not APP_RE.match(app):
        raise ValueError("bad app id")
    kind = data.get("kind")
    if kind not in ("touch", "controller"):
        raise ValueError("kind must be touch or controller")
    profile = data.get("profile")
    if not isinstance(profile, dict) or not isinstance(profile.get("elements", []), list):
        raise ValueError("profile must be a controls profile object")
    allowed = {"name", "cursorSpeed", "elements", "controllers", "radialMenus"}
    profile = {k: v for k, v in profile.items() if k in allowed}
    profile["id"] = 0
    if len(json.dumps(profile)) > MAX_LAYOUT_JSON:
        raise ValueError("layout too large")
    title = text(data.get("title"), 60) or "Layout"
    name = text(data.get("name"), 100)
    path = f"{ROOT}/layouts/{app}.json"
    doc = load(path, {"app": app, "name": name, "layouts": []})
    doc["name"] = name or doc.get("name", "")
    entry = {
        "id": str(number),
        "title": title, "kind": kind, "author": text(author, 40), "time": created,
        "model": text(data.get("model"), 40), "build": text(data.get("build"), 20), "profile": profile,
    }
    doc["layouts"] = (doc.get("layouts", []) + [entry])[-MAX_LAYOUTS:]
    save(path, doc)
    bump_index("layouts", app, len(doc["layouts"]), doc["name"])
    return f"Thanks! Layout \"{title}\" for {doc['name'] or app} is now shared."


def main():
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    issue = event.get("issue") or {}
    title = issue.get("title") or ""
    author = (issue.get("user") or {}).get("login", "")
    created = (issue.get("created_at") or "")[:19]
    try:
        data = payload(issue.get("body") or "")
        if title.startswith("[benchmark]"):
            out("OK", benchmark(data, author, created))
        elif title.startswith("[layout]"):
            out("OK", layout(data, author, created, issue.get("number", int(time.time()))))
        else:
            out("INVALID", "unknown submission type")
    except Exception as e:  # noqa: BLE001 - every failure becomes a comment on the issue
        out("INVALID", f"Couldn't file this submission: {text(e, 200)}")


if __name__ == "__main__":
    sys.exit(main())
