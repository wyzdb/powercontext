"""Select the task context from the seekdb index and render it.

Selection is a two-hop closure over explicit references:

1. rank specification clauses, code symbols and tests by the inverted index
   (``sdd_terms``) for the task text;
2. pull in the symbols and tests a selected clause declares in its front
   matter, the tests that cite a selected symbol, and the symbols and clauses a
   selected target test cites.

The result is deterministic for unchanged data and names every source with a
repository path and line range.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from sdd_context.config import Settings
from sdd_context.models import Match, TaskState
from sdd_context.store import SeekdbStore, new_id
from sdd_context.tokenizer import tokenize


def _split(value: object) -> list[str]:
    return [item for item in str(value or "").split(",") if item]


def _score_map(matches: Iterable[Match]) -> dict[str, Match]:
    return {match.ref_id: match for match in matches}


class ContextBuilder:
    """Build one context payload for a development task."""

    def __init__(
        self,
        store: SeekdbStore,
        settings: Settings,
        *,
        clause_limit: int = 10,
        symbol_limit: int = 8,
        test_limit: int = 10,
    ) -> None:
        self.store = store
        self.settings = settings
        self.clause_limit = clause_limit
        self.symbol_limit = symbol_limit
        self.test_limit = test_limit

    def build(
        self,
        task_text: str,
        *,
        task_id: str | None = None,
        title: str | None = None,
        state: TaskState | None = None,
    ) -> dict[str, Any]:
        terms = tokenize(task_text)
        matches = self.store.search_terms(terms, limit=80, task_id=task_id)
        scores = _score_map(matches)

        matched_clause_ids = [
            m.ref_id for m in matches if m.ref_kind == "spec"
        ][: self.clause_limit]
        clause_ids = list(matched_clause_ids)
        symbol_ids = [m.ref_id for m in matches if m.ref_kind == "code"][: self.symbol_limit]
        test_ids = [m.ref_id for m in matches if m.ref_kind == "test"][: self.test_limit]

        clauses = self.store.load_clauses(clause_ids, task_id)
        clause_ids = [clause["clause_id"] for clause in clauses]
        symbols = {row["symbol_id"]: row for row in self.store.load_symbols(symbol_ids, task_id)}
        tests = {row["test_id"]: row for row in self.store.load_tests(test_ids, task_id)}

        # Hop 0: target tests cite the clauses they enforce; pull any cited
        # clause that the keyword ranking did not surface (for example the
        # shared error-envelope clause).
        cited: list[str] = []
        for test in tests.values():
            if test["kind"] == "target":
                cited.extend(_split(test["spec_refs"]))
        missing = [ref for ref in dict.fromkeys(cited) if ref not in set(clause_ids)]
        if missing:
            clauses.extend(self.store.load_clauses(missing[:4], task_id))

        spec_ids = sorted({str(clause["spec_id"]) for clause in clauses})

        # Hop 1: definitions the selected clauses point at.
        declared_symbols: list[str] = []
        for clause in clauses:
            declared_symbols.extend(_split(clause["applies_to"]))
        for symbol_id in dict.fromkeys(declared_symbols):
            if symbol_id not in symbols:
                for row in self.store.load_symbols([symbol_id], task_id):
                    symbols[row["symbol_id"]] = row

        # Hop 2: verification tests for the selected specifications and symbols.
        for row in self.store.tests_for_specs(spec_ids, task_id):
            tests.setdefault(row["test_id"], row)
        for row in self.store.tests_for_symbols(list(symbols), task_id):
            tests.setdefault(row["test_id"], row)

        # Hop 3: target tests may name the symbols they exercise directly.
        for test in list(tests.values()):
            for symbol_id in _split(test["code_refs"]):
                if symbol_id not in symbols:
                    for row in self.store.load_symbols([symbol_id], task_id):
                        symbols[row["symbol_id"]] = row

        change_targets = self._change_targets(clauses, tests)

        matched = set(matched_clause_ids)
        spec_entries = [
            self._spec_entry(clause, scores, explicit=clause["clause_id"] in matched)
            for clause in clauses
        ]
        code_entries = [
            self._code_entry(symbol, scores, symbol_id in change_targets)
            for symbol_id, symbol in symbols.items()
        ]
        test_entries = [self._test_entry(test, scores) for test in tests.values()]

        spec_entries.sort(key=lambda item: (item["status"] != "proposed", item["clause_id"]))
        code_entries.sort(key=lambda item: (item["role"] != "modify", item["symbol_id"]))
        test_entries.sort(key=lambda item: (item["kind"] != "target", item["test_id"]))

        context_id = new_id("ctx")
        payload: dict[str, Any] = {
            "context_id": context_id,
            "task_id": task_id,
            "task": task_text,
            "title": title or task_text.strip().splitlines()[0][:120],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "engine": "seekdb",
                "host": self.settings.db_host,
                "port": self.settings.db_port,
                "database": self.settings.db_database,
                "tables": [
                    "sdd_spec_clauses",
                    "sdd_code_symbols",
                    "sdd_tests",
                    "sdd_terms",
                ],
            },
            "terms": terms,
            "specs": spec_entries,
            "code": code_entries,
            "tests": test_entries,
            "change_targets": sorted(change_targets),
            "state": state.to_mapping() if state is not None else None,
            "summary": {
                "spec_clauses": len(spec_entries),
                "code_symbols": len(code_entries),
                "change_targets": len(change_targets),
                "target_tests": sum(1 for item in test_entries if item["kind"] == "target"),
                "regression_tests": sum(
                    1 for item in test_entries if item["kind"] == "regression"
                ),
                "queries": len(self.store.last_query_stats),
            },
            "queries": [dict(item) for item in self.store.last_query_stats],
        }
        self.store.save_context(context_id, task_id or "unbound", payload)
        return payload

    # -- entry builders -------------------------------------------------
    def _change_targets(
        self, clauses: Sequence[dict[str, Any]], tests: dict[str, dict[str, Any]]
    ) -> set[str]:
        targets: set[str] = set()
        for clause in clauses:
            if clause["status"] == "proposed":
                targets.update(_split(clause["applies_to"]))
        for test in tests.values():
            if test["kind"] == "target":
                targets.update(_split(test["code_refs"]))
        return targets

    def _spec_entry(
        self, clause: dict[str, Any], scores: dict[str, Match], *, explicit: bool
    ) -> dict[str, Any]:
        match = scores.get(str(clause["clause_id"]))
        return {
            "clause_id": clause["clause_id"],
            "spec_id": clause["spec_id"],
            "title": clause["spec_title"],
            "version": int(clause["version"]),
            "status": clause["status"],
            "heading": clause["heading"],
            "body": clause["body"],
            "role": "required" if clause["status"] == "proposed" else "constraint",
            "source": {
                "path": clause["path"],
                "line_start": int(clause["line_start"]),
                "line_end": int(clause["line_end"]),
            },
            "score": match.score if match else 0,
            "reason": "任务关键词命中" if explicit else "规格引用补全",
        }

    def _code_entry(
        self, symbol: dict[str, Any], scores: dict[str, Match], is_target: bool
    ) -> dict[str, Any]:
        match = scores.get(str(symbol["symbol_id"]))
        return {
            "symbol_id": symbol["symbol_id"],
            "path": symbol["path"],
            "qualified_name": symbol["qualified_name"],
            "kind": symbol["kind"],
            "line_start": int(symbol["line_start"]),
            "line_end": int(symbol["line_end"]),
            "signature": symbol["signature"],
            "doc": symbol["doc"],
            "role": "modify" if is_target else "context",
            "source": {
                "path": symbol["path"],
                "line_start": int(symbol["line_start"]),
                "line_end": int(symbol["line_end"]),
            },
            "score": match.score if match else 0,
            "reason": "规格 applies_to 或目标测试指向" if is_target else "相关实现上下文",
        }

    def _test_entry(self, test: dict[str, Any], scores: dict[str, Match]) -> dict[str, Any]:
        match = scores.get(str(test["test_id"]))
        return {
            "test_id": test["test_id"],
            "path": test["path"],
            "name": test["name"],
            "kind": test["kind"],
            "spec_refs": _split(test["spec_refs"]),
            "code_refs": _split(test["code_refs"]),
            "line_start": int(test["line_start"]),
            "line_end": int(test["line_end"]),
            "source": {
                "path": test["path"],
                "line_start": int(test["line_start"]),
                "line_end": int(test["line_end"]),
            },
            "score": match.score if match else 0,
        }


def render_markdown(payload: dict[str, Any]) -> str:
    """Render the payload for reviewers and for the agent prompt."""

    lines: list[str] = []
    lines.append(f"# SDD 上下文 {payload['context_id']}")
    lines.append("")
    lines.append(f"- 任务：{payload['task']}")
    lines.append(f"- 生成时间：{payload['generated_at']}")
    lines.append(
        "- 数据库：seekdb {host}:{port}/{database}（表 {tables}）".format(
            host=payload["database"]["host"],
            port=payload["database"]["port"],
            database=payload["database"]["database"],
            tables="、".join(payload["database"]["tables"]),
        )
    )
    lines.append(f"- 关键词：{'、'.join(payload['terms'][:16])}")
    lines.append("")

    lines.append(f"## 适用规格（{len(payload['specs'])} 条）")
    for spec in payload["specs"]:
        role = "必需" if spec["role"] == "required" else "约束"
        lines.append("")
        lines.append(
            f"### {spec['clause_id']} {spec['heading']}（{spec['title']} v{spec['version']}，"
            f"{spec['status']}，{role}）"
        )
        lines.append(
            f"来源：{spec['source']['path']}:{spec['source']['line_start']}-{spec['source']['line_end']}"
        )
        lines.append("")
        lines.append(spec["body"])
    lines.append("")

    lines.append(f"## 代码上下文（{len(payload['code'])} 个符号，{len(payload['change_targets'])} 个需要修改）")
    for code in payload["code"]:
        marker = "修改" if code["role"] == "modify" else "上下文"
        lines.append(
            f"- [{marker}] `{code['symbol_id']}`（{code['signature']}）"
            f" 来源：{code['source']['path']}:{code['source']['line_start']}-{code['source']['line_end']}"
        )
    lines.append("")

    lines.append("## 验证测试")
    for test in payload["tests"]:
        kind = "目标功能" if test["kind"] == "target" else "回归兼容"
        covers = "、".join(test["spec_refs"]) or "-"
        lines.append(
            f"- [{kind}] `{test['test_id']}` 覆盖 {covers}"
            f" 来源：{test['source']['path']}:{test['source']['line_start']}"
        )
    lines.append("")

    state = payload.get("state")
    lines.append("## 任务状态（PowerContext）")
    if not state:
        lines.append("- 暂无已保存状态")
    else:
        lines.append(f"- 状态：{state.get('status')} / 步骤：{state.get('step')} / 修订：{state.get('revision')}")
        for item in state.get("done") or []:
            lines.append(f"- 已完成：{item}")
        for item in state.get("todo") or []:
            lines.append(f"- 待办：{item}")
        for item in state.get("verifications") or []:
            lines.append(
                "- 已有验证：{command} → exit {code}".format(
                    command=item.get("command", "?"), code=item.get("exit_code", "?")
                )
            )
    lines.append("")
    lines.append("## 本次数据库查询")
    for query in payload["queries"]:
        lines.append(
            f"- {query['purpose']}：{query['row_count']} 行 / {query['duration_ms']} ms"
            f"（sql_sha {query['sql_sha'][:12]}）"
        )
    return "\n".join(lines) + "\n"


def write_context_files(settings: Settings, payload: dict[str, Any]) -> tuple[Path, Path]:
    """Persist the JSON payload and its Markdown rendering under ``records``."""

    directory = settings.records_dir / "contexts"
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{payload['context_id']}.json"
    md_path = directory / f"{payload['context_id']}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path
