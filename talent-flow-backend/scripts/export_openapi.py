"""导出 OpenAPI 文档（yaml/json），与 app 实际路由保持一致。

用法:
    python scripts/export_openapi.py                      # 默认输出 openapi.yaml
    python scripts/export_openapi.py -o openapi.json      # 输出 json
    python scripts/export_openapi.py -o docs/api.yaml    # 自定义路径
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

# 允许 `python scripts/export_openapi.py` 直接运行（无需设置 PYTHONPATH）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def export(output: Path) -> None:
    schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.suffix.lower() == ".json":
        output.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        with output.open("w", encoding="utf-8") as f:
            yaml.dump(schema, f, allow_unicode=True, sort_keys=False, width=1000)

    print(f"WROTE {output} ({len(schema.get('paths', {}))} paths)")


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 OpenAPI 文档（yaml/json）")
    parser.add_argument(
        "-o", "--output",
        default="openapi.yaml",
        help="输出路径，后缀决定格式（.yaml/.yml -> yaml，.json -> json）",
    )
    args = parser.parse_args()

    out = Path(args.output)
    out = out if out.is_absolute() else ROOT / out
    export(out)


if __name__ == "__main__":
    main()
