"""Intake + extraction.

The LLM reads each document into `ExtractedDocument`. Results are cached on disk keyed by
sha256 + prompt version + model so reruns are byte-identical and free (ADR-0003).
"""
from __future__ import annotations

import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from pydantic import ValidationError

from .config import Config
from .models import ExtractedDocument
from .util import sha256_file

SUPPORTED = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".gif": "image/gif", ".webp": "image/webp", ".docx": "docx", ".txt": "text/plain"}


@dataclass
class IntakeDoc:
    path: Path
    sha256: str
    kind: str  # mime-ish
    text: str  # text layer ('' for images)
    pages: int
    role: str = "bill"  # bill (inbox) | reference (PO / subcontract / agreement)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def supdoc_id(self) -> str:
        return self.path.stem

    @property
    def has_text_layer(self) -> bool:
        return len(self.text.strip()) > 40


class ExtractionUnavailable(RuntimeError):
    pass


def _docx_text(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    out = []
    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = "".join(n.text or "" for n in child.iter() if n.tag.endswith("}t"))
            if t.strip():
                out.append(t)
        elif tag == "tbl":
            for row in child.iter():
                if row.tag.endswith("}tr"):
                    cells = []
                    for c in row:
                        if c.tag.endswith("}tc"):
                            cells.append(" ".join((n.text or "") for n in c.iter() if n.tag.endswith("}t")).strip())
                    out.append(" | ".join(cells))
    return "\n".join(out)


def intake(path: Path, role: str = "bill") -> IntakeDoc:
    ext = path.suffix.lower()
    kind = SUPPORTED.get(ext, "unsupported")
    text, pages = "", 0
    if kind == "application/pdf":
        import pdfplumber

        try:
            with pdfplumber.open(path) as pdf:
                pages = len(pdf.pages)
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:  # corrupt PDF: still hashable, extraction will decide
            text = ""
    elif kind == "docx":
        text, pages = _docx_text(path), 1
    elif kind == "text/plain":
        text, pages = path.read_text(errors="replace"), 1
    elif kind.startswith("image/"):
        pages = 1
    return IntakeDoc(path=path, sha256=sha256_file(path), kind=kind, text=text, pages=pages, role=role)


def list_inbox(inbox: Path) -> list[Path]:
    return sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith(".") and p.name != "Thumbs.db")


# --------------------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------------------

class Extractor(Protocol):
    def extract(self, doc: IntakeDoc) -> tuple[ExtractedDocument, str]: ...


class CacheStore:
    def __init__(self, cfg: Config):
        s = cfg.settings["extraction"]
        self.dir = cfg.state_dir / "extractions"
        self.model = s["model"]
        self.prompt_version = s["prompt_version"]

    def key(self, sha: str, role: str, model: str | None = None) -> Path:
        return self.dir / f"{sha}.{self.prompt_version}.{role}.{model or self.model}.json"

    def get(self, sha: str, role: str = "bill") -> tuple[ExtractedDocument, str] | None:
        for p in sorted(self.dir.glob(f"{sha}.{self.prompt_version}.{role}.*.json")):
            data = json.loads(p.read_text())
            return ExtractedDocument.model_validate(data["extraction"]), f"cache:{data['meta']['model']}"
        return None

    def put(self, doc: IntakeDoc, ex: ExtractedDocument, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        meta = {"file_name": doc.name, "sha256": doc.sha256, "prompt_version": self.prompt_version,
                "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta}
        self.key(doc.sha256, doc.role, meta.get("model")).write_text(
            json.dumps({"meta": meta, "extraction": ex.model_dump(mode="json")}, indent=2, sort_keys=True))


class CachedExtractor:
    """Cache first; on a miss, call the inner extractor (if any) and store the result."""

    def __init__(self, cfg: Config, inner: Extractor | None):
        self.cache = CacheStore(cfg)
        self.inner = inner

    def extract(self, doc: IntakeDoc) -> tuple[ExtractedDocument, str]:
        hit = self.cache.get(doc.sha256, doc.role)
        if hit:
            return hit
        if self.inner is None:
            raise ExtractionUnavailable("not in extraction cache and running --offline")
        ex, src, meta = self.inner.extract_with_meta(doc)  # type: ignore[attr-defined]
        self.cache.put(doc, ex, meta)
        return ex, src


_API_SCHEMA: dict[str, dict] = {}
_NUM_HINT = "Number as plain digits, e.g. 1118.67 or -2160.00 (no $ or commas). Empty string if not on the document."


def _nullable_inner(node: dict) -> dict | None:
    """For anyOf [X, null] return X, else None."""
    opts = node.get("anyOf")
    if isinstance(opts, list) and len(opts) == 2 and {"type": "null"} in opts:
        return next(o for o in opts if o != {"type": "null"})
    return None


# Each request carries only the fields its document type needs: smaller grammar, fewer output tokens.
REFERENCE_FIELDS = ["doc_kind", "vendor_name", "vendor_id_printed", "document_number", "document_date", "ref_project_text", "ref_status",
                    "ref_lines", "ref_total", "original_contract_sum", "change_orders", "monthly_fee", "term_start", "term_end",
                    "extraction_warnings", "observations"]
BILL_EXCLUDE = {"vendor_id_printed", "ref_project_text", "ref_status", "ref_lines", "ref_total", "original_contract_sum",
                "change_orders", "monthly_fee", "term_start", "term_end"}


def _subset(schema: dict, role: str) -> dict:
    props = schema["properties"]
    keep = REFERENCE_FIELDS if role == "reference" else [k for k in props if k not in BILL_EXCLUDE]
    out = dict(schema, properties={k: props[k] for k in keep})
    used = set()
    def refs(n):
        if isinstance(n, dict):
            if "$ref" in n:
                name = n["$ref"].split("/")[-1]
                if name not in used:
                    used.add(name)
                    refs(schema["$defs"][name])
            for v in n.values():
                refs(v)
        elif isinstance(n, list):
            for v in n:
                refs(v)
    refs(out["properties"])
    out["$defs"] = {k: v for k, v in schema.get("$defs", {}).items() if k in used}
    if not out["$defs"]:
        out.pop("$defs")
    return out


def api_schema(role: str = "bill") -> dict:
    """ExtractedDocument as a strict structured-output schema with NO optional fields and NO union types.

    Structured outputs cap both optional properties and anyOf/union parameters, so absence is encoded without unions:
    missing text → "", missing numbers → number-as-string or "", missing nested section → empty list.
    `from_api()` converts the reply back; the internal Pydantic model (labels, tests) is unchanged.
    """
    if role in _API_SCHEMA:
        return _API_SCHEMA[role]

    def conv(node):
        if isinstance(node, list):
            return [conv(v) for v in node]
        if not isinstance(node, dict):
            return node
        desc = node.get("description")
        inner = _nullable_inner(node)
        if inner is not None:
            if "$ref" in inner:
                out = {"type": "array", "items": {"$ref": inner["$ref"]}, "description": ((desc or "") + " Empty list if absent; at most one item.").strip()}
            elif inner.get("type") in ("number", "integer"):
                out = {"type": "string", "description": ((desc + " ") if desc else "") + _NUM_HINT}
            elif "enum" in inner:
                out = {"type": "string", "enum": list(inner["enum"]) + [""], **({"description": desc} if desc else {})}
            else:
                out = {"type": "string", "description": ((desc + " ") if desc else "") + "Empty string if not on the document."}
            return out
        node = {k: conv(v) for k, v in node.items() if k not in ("default", "title")}
        if node.get("type") in ("number", "integer"):
            node = {"type": "string", "description": ((desc + " ") if desc else "") + _NUM_HINT.replace(" Empty string if not on the document.", "")}
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
        return node

    _API_SCHEMA[role] = conv(_subset(ExtractedDocument.model_json_schema(), role))
    return _API_SCHEMA[role]


def _to_float(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = v.replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    f = float(s.strip("()"))
    return -f if neg else f


def to_api(data, node: dict | None = None, defs: dict | None = None):
    """Inverse of from_api (used by tests to simulate API replies)."""
    if node is None:
        node = ExtractedDocument.model_json_schema()
        defs = node.get("$defs", {})
        data = data.model_dump(mode="json") if isinstance(data, ExtractedDocument) else data
    if "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    inner = _nullable_inner(node)
    if inner is not None:
        if "$ref" in inner:
            return [] if data is None else [to_api(data, inner, defs)]
        if data is None:
            return ""
        return f"{data}" if inner.get("type") in ("number", "integer") else data
    t = node.get("type")
    if t in ("number", "integer"):
        return f"{data}"
    if t == "object" and isinstance(data, dict):
        return {k: to_api(v, node["properties"][k], defs) for k, v in data.items() if k in node.get("properties", {})}
    if t == "array" and isinstance(data, list):
        return [to_api(v, node.get("items", {}), defs) for v in data]
    return data


def from_api(data, node: dict | None = None, defs: dict | None = None):
    """Convert an api_schema() reply back into the shape of ExtractedDocument."""
    if node is None:
        node = ExtractedDocument.model_json_schema()
        defs = node.get("$defs", {})
    if "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    inner = _nullable_inner(node)
    if inner is not None:
        if data in ("", None, []):
            return None
        if "$ref" in inner:
            return from_api(data[0] if isinstance(data, list) else data, inner, defs)
        if inner.get("type") in ("number", "integer"):
            return _to_float(data)
        return data
    t = node.get("type")
    if t in ("number", "integer"):
        f = _to_float(data)
        return 0.0 if f is None else f
    if t == "object" and isinstance(data, dict):
        props = node.get("properties", {})
        return {k: from_api(v, props[k], defs) if k in props else v for k, v in data.items()}
    if t == "array" and isinstance(data, list):
        return [from_api(v, node.get("items", {}), defs) for v in data]
    return data


class ClaudeExtractor:
    """Claude reads one document into ExtractedDocument.

    Token-efficiency practices (see governance/TECH_STACK.md):
      - read each file once: results are cached by SHA-256 (CachedExtractor), so reruns cost 0 tokens
      - role-specific schemas (bill vs reference): each request carries only the fields it needs
      - the system prompt + schema are byte-stable and marked for prompt caching (cache reads ≈ 0.05× input price)
      - the first request of a batch warms that cache before the rest run in parallel (extract_many)
      - effort is configurable and chosen by measurement (`ap eval-extraction`), not set to max by default
      - a repair turn is sent only when validation fails, and carries just the validation errors
    Output enforcement per role: "grammar" (API-enforced JSON schema) or "validated_json" (schema in the prompt + strict
    Pydantic validation + one repair turn). If the API rejects a schema as too large, that role switches to validated_json.
    """

    def __init__(self, cfg: Config):
        import anthropic

        s = cfg.settings["extraction"]
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=s.get("max_retries", 4))
        self.model = s["model"]
        self.fallback = s.get("fallback_model")
        self.effort = s.get("effort", "medium")
        self.max_tokens = s.get("max_tokens", 16000)
        self.base_prompt = (cfg.root / cfg.settings["paths"]["prompt"]).read_text()
        self.mode = dict(s.get("output_mode") or {"bill": "validated_json", "reference": "grammar"})
        self._systems: dict[tuple[str, str], list[dict]] = {}

    def _system(self, role: str, mode: str) -> list[dict]:
        key = (role, mode)
        if key not in self._systems:
            text = self.base_prompt
            if mode == "validated_json":
                text += ("\n\nOUTPUT FORMAT: reply with ONE JSON object and nothing else (no prose, no code fences). It must validate "
                         "against this JSON Schema. Every property is required: use \"\" for absent text or numbers, [] for absent lists. "
                         "Write numbers as digit strings exactly as the schema says.\n"
                         + json.dumps(api_schema(role), separators=(",", ":")))
            self._systems[key] = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        return self._systems[key]

    def _content(self, doc: IntakeDoc) -> list[dict]:
        if doc.kind == "application/pdf":
            data = base64.standard_b64encode(doc.path.read_bytes()).decode()
            block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
        elif doc.kind.startswith("image/"):
            data = base64.standard_b64encode(doc.path.read_bytes()).decode()
            block = {"type": "image", "source": {"type": "base64", "media_type": doc.kind, "data": data}}
        elif doc.kind in ("docx", "text/plain"):
            block = {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": doc.text or "(empty)"}}
        else:
            raise ExtractionUnavailable(f"unsupported file type {doc.path.suffix}")
        kind = "purchase order / subcontract / service agreement" if doc.role == "reference" else "AP inbox document"
        return [block, {"type": "text", "text": f"File name: {doc.name} ({kind}). Transcribe it into the schema."}]

    def _call(self, model: str, doc: IntakeDoc, mode: str, messages: list[dict]):
        oc: dict = {"effort": self.effort}
        if mode == "grammar":
            oc["format"] = {"type": "json_schema", "schema": api_schema(doc.role)}
        return self.client.messages.create(model=model, max_tokens=self.max_tokens, system=self._system(doc.role, mode),
                                           output_config=oc, messages=messages)

    @staticmethod
    def _text(resp) -> str:
        return next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "") or ""

    @staticmethod
    def _parse(text: str) -> ExtractedDocument:
        t = text.strip()
        if not t.startswith("{"):
            a, b = t.find("{"), t.rfind("}")
            if a < 0 or b < a:
                raise ValueError("reply contains no JSON object")
            t = t[a:b + 1]
        return ExtractedDocument.model_validate(from_api(json.loads(t)))

    def extract_with_meta(self, doc: IntakeDoc) -> tuple[ExtractedDocument, str, dict]:
        errors: list[str] = []
        for model in [self.model] + ([self.fallback] if self.fallback else []):
            t0, usage, repaired = time.time(), {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                                                 "cache_creation_input_tokens": 0}, False
            messages = [{"role": "user", "content": self._content(doc)}]
            try:
                for attempt in range(3):
                    mode = self.mode.get(doc.role, "validated_json")
                    try:
                        resp = self._call(model, doc, mode, messages)
                    except self.anthropic.BadRequestError as e:
                        if mode == "grammar" and any(w in str(e).lower() for w in ("grammar", "too many", "schema")):
                            self.mode[doc.role] = "validated_json"  # self-heal: schema too large for grammar enforcement
                            continue
                        raise
                    for k in usage:
                        usage[k] += getattr(resp.usage, k, 0) or 0
                    if resp.stop_reason == "refusal":
                        raise ExtractionUnavailable("refusal")
                    if resp.stop_reason == "max_tokens":
                        raise ExtractionUnavailable("output truncated (max_tokens)")
                    text = self._text(resp)
                    try:
                        ex = self._parse(text)
                    except (ValueError, ValidationError) as ve:
                        if repaired:
                            raise ExtractionUnavailable(f"output failed validation after one repair: {str(ve)[:300]}")
                        repaired = True  # one repair turn, carrying only the validation errors
                        messages += [{"role": "assistant", "content": text},
                                     {"role": "user", "content": f"That JSON failed validation:\n{str(ve)[:1500]}\nReturn the corrected JSON object only."}]
                        continue
                    meta = {"model": model, "mode": mode, "effort": self.effort, "repaired": repaired,
                            "seconds": round(time.time() - t0, 1), **usage}
                    return ex, f"claude:{model}", meta
                raise ExtractionUnavailable("no valid output")
            except ExtractionUnavailable as e:
                errors.append(f"{model}: {e}")
            except self.anthropic.APIError as e:  # SDK already retried 408/409/429/5xx with backoff
                errors.append(f"{model}: {type(e).__name__}: {str(e)[:200]}")
        raise ExtractionUnavailable("; ".join(errors))

    def extract(self, doc: IntakeDoc) -> tuple[ExtractedDocument, str]:
        ex, src, _ = self.extract_with_meta(doc)
        return ex, src


class LabelExtractor:
    """Reads hand-labelled ground truth (tests / evaluation): <labels_dir>/<file stem>.json."""

    def __init__(self, labels_dirs: list[Path]):
        self.dirs = labels_dirs

    def extract(self, doc: IntakeDoc) -> tuple[ExtractedDocument, str]:
        for d in self.dirs:
            p = d / f"{doc.path.stem}.json"
            if p.exists():
                return ExtractedDocument.model_validate_json(p.read_text()), f"label:{p.parent.name}"
        raise ExtractionUnavailable(f"no label for {doc.name}")


def make_extractor(cfg: Config, mode: str = "auto", labels_dirs: list[Path] | None = None) -> Extractor:
    """mode: auto (cache, then Claude) | offline (cache only) | labels."""
    if mode == "labels":
        return LabelExtractor(labels_dirs or [])
    if mode == "offline":
        return CachedExtractor(cfg, None)
    inner = ClaudeExtractor(cfg) if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else None
    return CachedExtractor(cfg, inner)


def extract_many(extractor: Extractor, docs: list[IntakeDoc], concurrency: int = 8,
                 on_done: Callable[[IntakeDoc], None] | None = None) -> dict[str, tuple[ExtractedDocument | None, str]]:
    """Extract concurrently. A failure on one document never fails the batch (fault isolation)."""

    def one(d: IntakeDoc):
        try:
            if d.kind == "unsupported":
                raise ExtractionUnavailable(f"unsupported file type '{d.path.suffix}'")
            res = extractor.extract(d)
        except ExtractionUnavailable as e:
            res = (None, f"unavailable: {e}")
        except Exception as e:  # noqa: BLE001 - isolate anything unexpected to this document
            res = (None, f"unavailable: {type(e).__name__}: {e}")
        if on_done:
            on_done(d)
        return d.sha256, res

    if not docs:
        return {}
    first = one(docs[0])  # warms the prompt cache so the parallel requests read it instead of each writing it
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict([first] + list(pool.map(one, docs[1:])))
