"""制度知识库维护脚本（唯一入口）。

用法：
    python scripts/build_doc_kb.py --rebuild
    python scripts/build_doc_kb.py --doc DOC-002
    python scripts/build_doc_kb.py --doc DOC-002 --status archived
    python scripts/build_doc_kb.py --doc DOC-003 --status current
    python scripts/build_doc_kb.py --dry-run
    python scripts/build_doc_kb.py --list
"""

import argparse
import sys
from pathlib import Path

# 允许在 backend 目录下直接执行 `python scripts/build_doc_kb.py`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.doc_kb_service import (  # noqa: E402
    build_documents,
    list_documents,
    set_document_status,
)


def _print_stats(stats: dict) -> None:
    print(f"文档数：{stats['documents']}")
    print(f"片段数：{stats['segments']}")
    print(f"最长片段：{stats['max_chars']} 字符")
    print(f"最短片段：{stats['min_chars']} 字符")
    print(f"表格块：{stats['table_chunks']}")
    for item in stats.get("details", []):
        print(f"  - {item['document_id']} {item['document_name']}：{item['chunks']} 段")


def main() -> int:
    parser = argparse.ArgumentParser(description="制度知识库构建与维护")
    parser.add_argument("--rebuild", action="store_true", help="全量重建所有制度文档")
    parser.add_argument("--doc", help="只处理指定文档编号，如 DOC-002")
    parser.add_argument(
        "--status",
        choices=["current", "archived"],
        help="切换文档状态：archived 移除索引，current 恢复并重建",
    )
    parser.add_argument("--dry-run", action="store_true", help="只输出切分统计，不落库")
    parser.add_argument("--list", action="store_true", help="列出已入库文档")
    args = parser.parse_args()

    if args.dry_run:
        # dry-run 只做切分统计，不连数据库，便于无 MySQL 环境下校验切分效果
        stats = build_documents(None, only_document_id=args.doc, dry_run=True)
        print("[dry-run] 仅统计，未落库")
        _print_stats(stats)
        return 0

    init_db()
    db = SessionLocal()
    try:
        if args.list:
            documents = list_documents(db)
            if not documents:
                print("暂无已入库文档")
            for doc in documents:
                print(
                    f"{doc['document_id']} | {doc['document_name']} | v{doc['version']} | "
                    f"{doc['status']} | {doc['chunk_count']} 段"
                )
            return 0

        if args.status and not args.doc:
            parser.error("--status 需要配合 --doc 使用")

        if args.doc and args.status:
            result = set_document_status(db, args.doc, args.status)
            print(f"{args.doc} 状态已切换为 {args.status}：{result}")
            return 0

        if not (args.rebuild or args.doc or args.dry_run):
            parser.error("请指定 --rebuild / --doc / --dry-run / --list 之一")

        stats = build_documents(
            db,
            only_document_id=args.doc,
            dry_run=args.dry_run,
        )
        print("[dry-run] 仅统计，未落库" if args.dry_run else "构建完成")
        _print_stats(stats)
        return 0
    except Exception as e:
        print(f"执行失败：{e}")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
