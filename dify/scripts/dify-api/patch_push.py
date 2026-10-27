# -*- coding: utf-8 -*-
"""修正已生成图里的字段并重新推送。"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
APP_ID = "ab2c10d4-71c8-45e6-80ac-30e7f02b0cf0"
HERE = os.path.dirname(os.path.abspath(__file__))


def token():
    with open(os.path.join(os.environ["TEMP"], "dify_token.txt"), encoding="utf-8") as f:
        return f.read().strip()


def call(method, path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    with open(os.path.join(HERE, "graph_pushed.json"), encoding="utf-8") as f:
        graph = json.load(f)

    # assigner 的 operation 枚举是 over-write（带连字符）
    for n in graph["nodes"]:
        for it in n.get("data", {}).get("items", []) or []:
            if it.get("operation") == "overwrite":
                it["operation"] = "over-write"

        # 知识检索：reranking_mode 必须是字符串，weights 不能是 null
        data = n.get("data", {})
        if data.get("type") == "knowledge-retrieval":
            cfg = data.get("multiple_retrieval_config") or {}
            if not cfg.get("reranking_mode"):
                cfg["reranking_mode"] = "reranking_model"
            if cfg.get("weights") is None:
                cfg["weights"] = {"keyword_weight": 0.3, "vector_weight": 0.7} \
                    if cfg.get("reranking_mode") == "weighted_score" else None
                if cfg["weights"] is None:
                    cfg.pop("weights", None)
            data["multiple_retrieval_config"] = cfg

    # if-else 的两个分支句柄是 true / false，不是 source
    if_id = next((n["id"] for n in graph["nodes"] if n["data"]["type"] == "if-else"), None)
    if if_id:
        for e in graph["edges"]:
            if e["source"] == if_id:
                tgt_type = next((n["data"]["type"] for n in graph["nodes"] if n["id"] == e["target"]), "")
                e["sourceHandle"] = "true" if tgt_type == "http-request" else "false"
                e["data"]["sourceType"] = "if-else"

    # 模板转换节点的输出变量名是 output，不是 text
    for n in graph["nodes"]:
        if n["data"]["type"] == "answer":
            n["data"]["answer"] = "{{#tpl01.output#}}"

    # LLM 提示词：不允许编造旧战绩；两人按牌桌人数出场
    system_prompt = (
        "你是斗地主残局牌桌上的看客，只负责说话，不负责打牌。\n\n"
        "角色：\n"
        "- 老K（左家）：四十岁，跑江湖的老油条，说话慢、阴阳怪气。\n"
        "- 小七（右家）：二十出头，莽撞咋呼。\n\n"
        "铁律：\n"
        "1. 牌局结果、手牌、胜负以「牌桌」为准，不得修改、不得编造牌。\n"
        "2. 不要复述牌桌信息，不要解释规则，不要给建议——除非玩家明确问「怎么打」。\n"
        "3. 玩家出错牌被系统拒绝时，只调侃，不能替他改牌。\n"
        "4. 「旧战绩」为空时，当作第一次见面：禁止出现“上次/上回/之前/又”这类暗示旧事的说法。\n"
        "5. 「旧战绩」不为空时，必须具体提起（哪一关、怎么输的）。\n"
        "6. 牌桌上没有“右家”时，只让老K说话；出现“右家”时小七才可以开口。\n"
        "7. 输出 2-3 句，每句不超过 40 字，用「老K：」「小七：」开头。\n\n"
        "旧战绩（可能为空）：\n{{#parsemem01.content#}}\n\n"
        "讲解素材（可能为空）：\n{{#know01.result#}}"
    )
    for n in graph["nodes"]:
        if n["data"]["type"] == "llm":
            n["data"]["prompt_template"][0]["text"] = system_prompt
            n["data"]["model"]["completion_params"]["temperature"] = 0.5
            # 把旧战绩放进 user 消息，并给出硬性句式要求
            n["data"]["prompt_template"][1]["text"] = (
                "牌桌：\n{{#engine01.message#}}\n\n"
                "玩家刚说：{{#sys.query#}}\n\n"
                "【旧战绩】（为空就当我第一次来，不准提“上次/上回/之前/又”）\n"
                "{{#parsemem01.content#}}\n\n"
                "要求：如果【旧战绩】不为空，你的第一句必须点名引用其中某一关的结果，"
                "句式类似“上回第X关你……”，然后再说这一手牌。"
            )

    # 加一个确定性过滤器：两人关不许出现“小七”
    ids = {n["id"] for n in graph["nodes"]}
    if "filter01" not in ids:
        llm = next(n for n in graph["nodes"] if n["data"]["type"] == "llm")
        filt = {
            "id": "filter01",
            "type": "custom",
            "position": {"x": llm["position"]["x"] + 300, "y": llm["position"]["y"]},
            "positionAbsolute": {"x": llm["position"]["x"] + 300, "y": llm["position"]["y"]},
            "width": 244, "height": 90, "selected": False,
            "sourcePosition": "right", "targetPosition": "left",
            "data": {
                "type": "code", "title": "过滤台词", "selected": False, "desc": "",
                "code_language": "python3",
                "code": (
                    "def main(text: str, table: str) -> dict:\n"
                    "    lines = [l for l in (text or '').splitlines() if l.strip()]\n"
                    "    if '右家' not in (table or ''):\n"
                    "        lines = [l for l in lines if not l.strip().startswith('小七')]\n"
                    "    return {'talk': '\\n'.join(lines)}\n"
                ),
                "variables": [
                    {"variable": "text", "value_selector": [llm["id"], "text"]},
                    {"variable": "table", "value_selector": ["engine01", "message"]},
                ],
                "outputs": {"talk": {"type": "string", "children": None}},
            },
        }
        graph["nodes"].append(filt)

        # 连线：LLM -> 过滤 -> IF；删掉原来的 LLM -> IF
        for e in list(graph["edges"]):
            if e["source"] == llm["id"] and e["target"] == "if01":
                graph["edges"].remove(e)
        graph["edges"].append({
            "id": "llm01-source-filter01-target", "type": "custom",
            "source": "llm01", "target": "filter01",
            "sourceHandle": "source", "targetHandle": "target",
            "data": {"sourceType": "llm", "targetType": "code", "isInLoop": False}, "zIndex": 0,
        })
        graph["edges"].append({
            "id": "filter01-source-if01-target", "type": "custom",
            "source": "filter01", "target": "if01",
            "sourceHandle": "source", "targetHandle": "target",
            "data": {"sourceType": "code", "targetType": "if-else", "isInLoop": False}, "zIndex": 0,
        })

    # 模板改用过滤后的台词
    for n in graph["nodes"]:
        if n["data"]["type"] == "template-transform":
            for v in n["data"]["variables"]:
                if v["variable"] == "table_talk":
                    v["value_selector"] = ["filter01", "talk"]

    # 记忆解析：只取 item 正文，去掉 PowerContext 的固定前缀
    mem_code = (
        "import json\n"
        "\n"
        "def main(body: str) -> dict:\n"
        "    raw = body or ''\n"
        "    try:\n"
        "        d = json.loads(raw) if raw else {}\n"
        "    except Exception:\n"
        "        d = {}\n"
        "    if not isinstance(d, dict):\n"
        "        d = {}\n"
        "    content = d.get('content') or ''\n"
        "    text = content\n"
        "    try:\n"
        "        s = content.index('BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1') + len('BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1')\n"
        "        e = content.index('END_POWERCONTEXT_PREPARED_CONTEXT_V1')\n"
        "        payload = json.loads(content[s:e].strip())\n"
        "        text = '\\n'.join(str(it.get('content', '')) for it in payload.get('items', []))\n"
        "    except Exception:\n"
        "        pass\n"
        "    return {'content': text.strip(), 'mem_status': str(d.get('status') or '')}\n"
    )
    for n in graph["nodes"]:
        if n["id"] == "parsemem01":
            n["data"]["code"] = mem_code

    with open(os.path.join(HERE, "draft_backup.json"), encoding="utf-8-sig") as f:
        old = json.load(f)

    st, txt = call("GET", "/console/api/apps/%s/workflows/draft" % APP_ID)
    if st != 200:
        print("GET draft failed", st, txt[:300])
        sys.exit(1)
    payload = {
        "graph": graph,
        "features": old["features"],
        "environment_variables": old["environment_variables"],
        "conversation_variables": old["conversation_variables"],
        "rag_pipeline_variables": [],
        "hash": json.loads(txt).get("hash"),
    }

    feats = payload["features"]
    feats["opening_statement"] = (
        "客官里边请——哦，是你啊。\n"
        "（老K低头拨着算盘，眼皮都没抬）残局摆好了，几步之内出完，自己看着办。\n\n"
        "出牌直接写牌面，比如 5 6 7 8 9；不想出写「过」；不会打写「提示」。"
    )
    feats["suggested_questions"] = ["5 6 7 8 9", "过", "提示", "下一关"]
    status, text = call("POST", "/console/api/apps/%s/workflows/draft" % APP_ID, payload)
    print("POST ->", status, text[:600])
    if status == 200:
        with open(os.path.join(HERE, "graph_pushed.json"), "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
