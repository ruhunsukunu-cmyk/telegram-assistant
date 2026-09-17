"""Repeatable local benchmark for the Telegram assistant's non-network core."""

import ast
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def percentile(values, percent):
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percent / 100))
    return ordered[index]


def timed(operation, runs=300):
    durations = []
    for _ in range(runs):
        started = time.perf_counter()
        operation()
        durations.append((time.perf_counter() - started) * 1000)
    return {
        "median_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 95), 3),
    }


def source_metrics():
    files = [ROOT / "bot.py", ROOT / "database.py", *sorted((ROOT / "services").glob("*.py"))]
    functions = []
    source_lines = 0
    for path in files:
        source = path.read_text(encoding="utf-8")
        source_lines += len(source.splitlines())
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": f"{path.name}:{node.name}",
                    "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                })
    test_lines = sum(
        len(path.read_text(encoding="utf-8").splitlines())
        for path in (ROOT / "tests").glob("test_*.py")
    )
    largest = max(functions, key=lambda item: item["lines"])
    return {
        "source_lines": source_lines,
        "test_lines": test_lines,
        "function_count": len(functions),
        "largest_function": largest,
    }


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["DB_PATH"] = str(Path(temp_dir) / "benchmark.db")
        os.environ["DATABASE_URL"] = ""

        import database
        from services.natural_language import extract_future_datetime

        database.init_db()
        counter = iter(range(1, 10_000))

        insert = timed(lambda: database.add_task(1, f"Benchmark görevi {next(counter)}"))
        tasks = database.get_tasks(1)
        read = timed(lambda: database.get_enriched_tasks(1))
        parse = timed(lambda: extract_future_datetime("yarın saat 10 doktoru hatırlat"))

        print(json.dumps({
            "database_insert": insert,
            "database_read_300_rows": read,
            "turkish_intent_parse": parse,
            "rows": len(tasks),
            "source": source_metrics(),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
