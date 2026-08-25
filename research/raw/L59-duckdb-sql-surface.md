# L59 — T9 interfaces: DuckDB SQL over graph tables as agent query surface

(recovered from lane transcript)

{"command":"python3 - <<'EOF'\nimport json\nsrc = \"/home/malcolmjones/.omp/profiles/ox-alpha/agent/sessions/-Projects-Codex-V3/2026-08-24T21-43-19-749Z_01a035ba-57c5-7140-b5cc-3df817e29c87.jsonl\"\nbest = \"\"\nfor line in open(src):\n    try: d = json.loads(line)\n    except Exception: continue\n    def scan(o):\n        global best\n        if isinstance(o, dict):\n            for k, v in o.items():\n                if isinstance(v, str) and \"graph_sql\" in v and \"|Item|\" in v.replace(\" \",\"\") and len(v) > len(best): best = v\n                else: scan(v)\n        elif isinstance(o, list):\n            for x in o: scan(x)\n    scan(d)\nhdr = \"# L59 — T9 interfaces: DuckDB SQL over graph tables as agent query surface\\n\\n(recovered from lane transcript)\\n\\n\"\nopen(\"/home/malcolmjones/Projects/Graphify/research/raw/L59-duckdb-sql-surface.md\",\"w\").write(hdr + best)\nprint(\"L59:\", len(best))\nEOF","i":"Persisting L59 DuckDB SQL surface findings"}

## Verdict
Hybrid: add ONE graph_sql read-only DuckDB tool (memory_limit 1GB, read_only connect, SELECT/WITH-only + mandatory LIMIT, wall-clock interrupt) beside existing query|path|explain verbs; verbs keep PPR/fusion/rerank. sqlite extension ATTACHes the existing graph DB zero-ETL; model-SQL literacy evidence favors SQL over bespoke verb grammars (BIRD 81.95% SOTA vs BFCL ~78%); duckpgq rejected (pins 1.4.4).
