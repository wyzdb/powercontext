"""向量化：IDF 加权哈希（离线）/ 百炼 (需 Key)。

哈希向量的问题不是"假"，是**均匀加权**：`共享` 这种满篇都是的 bigram，
权重和只出现一次的 `伪共` 一样大，于是「伪共享」和「共享内存」分不开。

改成 TF-IDF 加权后，罕见 bigram 权重高、常见 bigram 权重低，
排序就能拉开差距——而且完全离线、确定、可复现。

`EMBED_PROVIDER=dashscope` 时走真实语义向量；两条路维度都必须是 EMBED_DIM。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from pathlib import Path

DIM = int(os.getenv("EMBED_DIM", "1024"))
PROVIDER = os.getenv("EMBED_PROVIDER", "hash").strip().lower()
IDF_PATH = Path(__file__).resolve().parents[1] / "data" / "idf.json"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


def load_env() -> None:
    """读项目根目录的 .env，不覆盖已存在的环境变量。

    不引第三方依赖：python-dotenv 不在评审的必装清单里。
    """
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_env()
DIM = int(os.getenv("EMBED_DIM", "1024"))
PROVIDER = os.getenv("EMBED_PROVIDER", "hash").strip().lower()

_idf_cache: dict[str, float] | None = None
_default_idf: float = math.log(2.0)


def _grams(text: str) -> list[str]:
    """中文 bigram + ASCII 词，中英混排都能落到桶里。"""
    grams: list[str] = []
    cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    grams += ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]

    word = ""
    for ch in text + " ":
        if ch.isascii() and ch.isalnum():
            word += ch.lower()
        elif word:
            grams.append(word)
            word = ""
    return grams


def fit_idf(texts: list[str]) -> dict[str, float]:
    """算 IDF 并存盘。ingest 时调一次，检索侧读同一份。"""
    global _idf_cache, _default_idf
    df: dict[str, int] = {}
    for t in texts:
        for g in set(_grams(t)):
            df[g] = df.get(g, 0) + 1
    n = len(texts)
    idf = {g: math.log((1 + n) / (1 + d)) + 1.0 for g, d in df.items()}
    _default_idf = math.log(1 + n) + 1.0
    _idf_cache = idf
    IDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    IDF_PATH.write_text(json.dumps(
        {"n": n, "default": _default_idf, "idf": idf}, ensure_ascii=False), encoding="utf-8")
    return idf


def _load_idf() -> tuple[dict[str, float], float]:
    global _idf_cache, _default_idf
    if _idf_cache is not None:
        return _idf_cache, _default_idf
    if IDF_PATH.exists():
        blob = json.loads(IDF_PATH.read_text(encoding="utf-8"))
        _idf_cache = blob["idf"]
        _default_idf = blob["default"]
    else:
        _idf_cache = {}
    return _idf_cache, _default_idf


def hash_embed(text: str, dim: int = DIM) -> list[float]:
    """每个 bigram 按 IDF 加权后打进两个桶，最后 L2 归一化。"""
    idf, fallback = _load_idf()
    vec = [0.0] * dim
    for gram in _grams(text):
        w = idf.get(gram, fallback)
        h = hashlib.blake2b(gram.encode("utf-8"), digest_size=16).digest()
        for k in (0, 6):
            idx = int.from_bytes(h[k:k + 6], "big") % dim
            vec[idx] += w
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm > 0 else vec


def dashscope_embed(texts: list[str], batch: int = 10) -> list[list[float]]:
    key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("EMBED_API_KEY")
    if not key:
        raise RuntimeError("EMBED_PROVIDER=dashscope 但没有 DASHSCOPE_API_KEY")
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        body = json.dumps({
            "model": os.getenv("EMBED_MODEL", "text-embedding-v3"),
            "input": texts[i:i + batch], "dimensions": DIM,
        }).encode()
        req = urllib.request.Request(
            DASHSCOPE_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        out.extend(item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"]))
    return out


def openai_compat_embed(texts: list[str], batch: int = 10) -> list[list[float]]:
    """任意 OpenAI 兼容的 /v1/embeddings 接口。

    百炼、硅基流动、自建网关都能用，只需配三样：
        EMBED_BASE_URL=https://api.siliconflow.cn/v1
        EMBED_API_KEY=sk-xxx
        EMBED_MODEL=BAAI/bge-m3
    """
    base = (os.getenv("EMBED_BASE_URL") or "").rstrip("/")
    key = os.getenv("EMBED_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    model = os.getenv("EMBED_MODEL", "text-embedding-v3")
    if not base or not key:
        raise RuntimeError("EMBED_PROVIDER=openai 需要 EMBED_BASE_URL 和 EMBED_API_KEY")

    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": model, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(
            f"{base}/embeddings", data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        items = sorted(data["data"], key=lambda x: x.get("index", 0))
        out.extend(item["embedding"] for item in items)
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    if PROVIDER in ("dashscope", "openai"):
        vecs = (dashscope_embed if PROVIDER == "dashscope"
                else openai_compat_embed)(texts)
    else:
        vecs = [hash_embed(t) for t in texts]
    for v in vecs:
        if len(v) != DIM:
            raise ValueError(f"向量维度 {len(v)} 与 EMBED_DIM={DIM} 不符")
    return vecs


def to_sql_vector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
