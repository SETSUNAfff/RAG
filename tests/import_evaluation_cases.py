"""One-time import for the offline evaluation set."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from config.mysql_engine import async_session
from schemas.evaluation import CaseImportItem
from services.evaluation import import_cases


async def main(path: str, replace: bool = False) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = [CaseImportItem(**case) for case in payload.get("cases", [])]
    async with async_session() as db:
        result = await import_cases(db, items, replace=replace)
    print(
        f"导入完成: 新增={result.created} 更新={result.updated} "
        f"已解析={result.resolved} 过期={result.stale} 跳过={result.skipped}"
    )
    if result.errors:
        print("错误明细:")
        for error in result.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    default_path = Path(__file__).parent / "evaluation_cases.json"
    replace = "--replace" in sys.argv
    positional = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    path = positional[0] if positional else str(default_path)
    asyncio.run(main(path, replace=replace))
