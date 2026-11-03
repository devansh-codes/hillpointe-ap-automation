"""Export the AI usage record from a Claude Code session transcript (JSONL) into reviewable, redacted markdown.

Writes, into <out_dir> (the AI usage log is delivered separately from this repository):
  PROMPT_LEDGER.md   every human prompt, verbatim, with session, time, effort and resulting commits
  TRANSCRIPT.md      condensed transcript: each prompt -> the assistant's reply, tool calls counted
                     (tool inputs/outputs are omitted; the code and git history are the record of those)

Redaction is automatic and then verified: the export fails if anything key-like, an e-mail address or a local home path
survives. Raw transcripts are never committed (AGENTS.md).

  uv run python scripts/export_ai_log.py ~/.claude/projects/<project>/<session>.jsonl <out_dir>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Session boundaries (local time). Each human prompt belongs to the last session that started at or before it.
SESSIONS = [
    ("S01", "2026-11-02 11:00", "Discovery and planning"),
    ("S02", "2026-11-02 13:00", "Plan gap review against the AP domain walkthrough"),
    ("S03", "2026-11-02 13:10", "Live-session readiness review"),
    ("S04", "2026-11-02 13:25", "Model selection for document extraction"),
    ("S05", "2026-11-02 13:30", "Build and end-to-end testing"),
    ("S06", "2026-11-02 14:25", "Real-model integration and token efficiency"),
    ("S07", "2026-11-02 16:30", "Publish, evaluator guide and readiness audit"),
    ("S08", "2026-11-02 17:50", "Web UI for the AP team"),
    ("S09", "2026-11-02 19:20", "UI iteration, delete/import, interview drill pack"),
    ("S10", "2026-11-02 23:35", "Public demo, independent audit, release"),
    ("S11", "2026-11-03 00:20", "Deliverables: AI usage log"),
]

REDACT = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED: API key]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?!anthropic\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED: e-mail]"),
    (re.compile(r"/private/tmp/claude-\d+/[^\s`'\")]*"), "<scratch>"),
    (re.compile(r"/var/folders/[^\s`'\")]*"), "<tmp>"),
    (re.compile(r"/Users/[^/\s`'\")]+"), "~"),
    (re.compile(r"(?i)shop.?savvy"), "[unrelated project]"),
]
# Must never reach the export: keys, local paths, e-mail addresses, and the unrelated project whose instructions the
# tool loaded from the global agent file (it is context noise, not part of this work).
LEAKS = [re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), re.compile(r"/Users/[a-z]"), re.compile(r"(?i)shop.?savvy"),
         re.compile(r"[A-Za-z0-9._%+-]+@(?!anthropic\.com)[A-Za-z0-9.-]+\.(?:com|app|io|net|org)\b")]
SKIP_PREFIX = ("<task-notification", "<command-", "This session is being continued", "Caveat:", "[SYSTEM NOTIFICATION")


def redact(s: str) -> str:
    for pat, rep in REDACT:
        s = pat.sub(rep, s)
    return s


def local(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()


def session_of(t: datetime) -> tuple[str, str]:
    sid, title = SESSIONS[0][0], SESSIONS[0][2]
    for s, start, name in SESSIONS:
        if t.replace(tzinfo=None) >= datetime.strptime(start, "%Y-%m-%d %H:%M"):
            sid, title = s, name
    return sid, title


def clean_prompt(text: str) -> str:
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<ide_[a-z_]+>.*?</ide_[a-z_]+>", "", text, flags=re.S)
    return text.strip()


def parse(path: Path):
    """Turns: one per typed human prompt. Mid-turn messages are separate prompts attached to the running turn."""
    turns, cur = [], None
    for line in open(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = r.get("timestamp")
        if r.get("type") == "user" and not r.get("isMeta") and not r.get("isCompactSummary"):
            c = r.get("message", {}).get("content")
            parts = [c] if isinstance(c, str) else [x for x in (c or []) if isinstance(x, dict)]
            if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in parts):
                continue
            text = "\n".join(x if isinstance(x, str) else x.get("text", "") for x in parts if isinstance(x, str) or x.get("type") == "text")
            text = clean_prompt(text)
            if not text or text.startswith(SKIP_PREFIX) or "<task-notification>" in text:
                continue
            imgs = sum(1 for x in parts if isinstance(x, dict) and x.get("type") == "image")
            cur = {"prompts": [{"time": local(ts), "text": text, "images": imgs, "midturn": False}], "replies": [], "tools": Counter(),
                   "agents": [], "end": local(ts), "seen": set()}
            turns.append(cur)
        elif r.get("type") == "attachment" and cur is not None:  # a message the human sent while the AI was working
            a = r.get("attachment") or {}
            if a.get("type") == "queued_command" and (a.get("origin") or {}).get("kind") == "human" and a.get("source_uuid") not in cur["seen"]:
                cur["seen"].add(a.get("source_uuid"))
                text = "\n".join(x.get("text", "") for x in a.get("prompt", []) if isinstance(x, dict))
                cur["prompts"].append({"time": local(ts), "text": clean_prompt(text), "images": 0, "midturn": True})
        elif r.get("type") == "assistant" and cur is not None:
            cur["end"] = local(ts) if ts else cur["end"]
            for c in r["message"].get("content", []):
                if c.get("type") == "text" and c["text"].strip():
                    cur["replies"].append(c["text"].strip())
                elif c.get("type") == "tool_use":
                    cur["tools"][c["name"]] += 1
                    if c["name"] in ("Agent", "Task"):
                        cur["agents"].append(c["input"])
    return turns


def commits_between(a: datetime, b: datetime) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%h|%aI|%s"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    res = []
    for l in out:
        h, when, subj = l.split("|", 2)
        if a <= datetime.fromisoformat(when) <= b:
            res.append(f"`{h}` {subj}")
    return res


def pasted(text: str) -> tuple[str, list[str]]:
    """Replace pasted blocks with a short marker in the ledger; return the blocks for the transcript appendix."""
    blocks = re.findall(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", text, flags=re.S)
    short = re.sub(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>",
                   lambda m: f"[pasted text, {len(m.group(1).split())} words: “{' '.join(m.group(1).split()[:14])}…”]", text, flags=re.S)
    return short, blocks


def quote(s: str) -> str:
    return "\n".join("> " + l if l.strip() else ">" for l in s.splitlines())


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_ai_log.py <session.jsonl> <out_dir>")
    src, out = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    turns = parse(src)
    ledger = ["# Prompt ledger", "",
              "Every instruction the human gave the AI during the build, **verbatim** (typos kept), in order. Generated from the",
              "Claude Code session record by `scripts/export_ai_log.py`; secrets, e-mail addresses and local paths are redacted",
              "automatically and the export fails if any survive. Long pasted texts are shortened here and given in full in",
              "[TRANSCRIPT.md](TRANSCRIPT.md#pasted-material). *Mid-turn* = sent while the AI was still working on the previous prompt.", "",
              "| # | Session | Time (EST) | Prompt | AI effort | Commits |", "|---|---|---|---|---|---|"]
    transcript = ["# Condensed transcript", "",
                  "Each human prompt followed by the AI's reply to it, verbatim and redacted. Tool calls (shell, file edits, reads) are",
                  "counted, not reproduced: their effect is in the code and the git history. Context was compacted twice by the tool;",
                  "the record below is from the full session log, not the compacted context.", ""]
    all_pasted, n, cur_session = [], 0, None
    for i, t in enumerate(turns):
        nxt = turns[i + 1]["prompts"][0]["time"] if i + 1 < len(turns) else datetime.now(timezone.utc).astimezone()
        commits = commits_between(t["prompts"][0]["time"], nxt)
        sid, title = session_of(t["prompts"][0]["time"])
        if sid != cur_session:
            transcript += [f"## {sid} · {title}", ""]
            cur_session = sid
        tools = sum(t["tools"].values())
        mins = max(1, round((t["end"] - t["prompts"][0]["time"]).total_seconds() / 60))
        effort = f"{tools} tool calls, ~{mins} min" + (f", {len(t['agents'])} sub-agent(s)" if t["agents"] else "")
        for j, p in enumerate(t["prompts"]):
            n += 1
            short, blocks = pasted(redact(p["text"]))
            all_pasted += [(n, b) for b in blocks]
            cell = short.replace("\n", "<br>").replace("|", "\\|")
            tags = (" *(mid-turn)*" if p["midturn"] else "") + (f" *[+{p['images']} screenshot]*" if p["images"] else "")
            ledger.append(f"| P{n:02d} | {sid} | {p['time']:%m-%d %H:%M} | {cell}{tags} | {effort if j == 0 else '↑ same turn'} | "
                          f"{'<br>'.join(commits) if j == 0 and commits else ''} |")
            transcript += [f"### P{n:02d} · {p['time']:%Y-%m-%d %H:%M}{' · mid-turn' if p['midturn'] else ''}"
                           f"{f' · {p['images']} screenshot(s) attached' if p['images'] else ''}",
                           "", "**Human**", "", quote(short), ""]
        reply = redact(t["replies"][-1]) if t["replies"] else "*(reply in progress when this export was made)*"
        tool_mix = ", ".join(f"{k} {v}" for k, v in t["tools"].most_common())
        transcript += [f"**AI** · {effort}" + (f" ({tool_mix})" if tool_mix else ""), "", quote(reply), ""]
        for a in t["agents"]:
            transcript += [f"<details><summary>Prompt the AI wrote for a sub-agent: {redact(a.get('description', ''))}</summary>", "",
                           quote(redact(a.get("prompt", ""))), "", "</details>", ""]
        transcript.append("---\n")
    transcript += ["## Pasted material", ""]
    for k, b in all_pasted:
        transcript += [f"<details><summary>P{k:02d}: pasted text ({len(b.split())} words)</summary>", "", quote(b.strip()), "", "</details>", ""]
    totals = Counter()
    for t in turns:
        totals.update(t["tools"])
    ledger += ["", f"**Totals:** {n} human prompts · {sum(totals.values())} AI tool calls "
                   f"({', '.join(f'{k} {v}' for k, v in totals.most_common())}) · "
                   f"{sum(len(t['agents']) for t in turns)} delegated sub-agents."]
    for name, body in (("PROMPT_LEDGER.md", ledger), ("TRANSCRIPT.md", transcript)):
        text = "\n".join(body).rstrip() + "\n"
        for pat in LEAKS:
            if pat.search(text):
                raise SystemExit(f"refusing to write {name}: unredacted match for {pat.pattern}: {pat.search(text).group(0)[:12]}…")
        (out / name).write_text(text)
    print(f"{n} prompts, {len(turns)} turns -> {out}/PROMPT_LEDGER.md, TRANSCRIPT.md")


if __name__ == "__main__":
    main()
