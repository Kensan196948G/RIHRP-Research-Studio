"""OpenAPI を docs/api/openapi.yaml に出力する。

    python infra/db/export_openapi.py            # 出力
    python infra/db/export_openapi.py --check    # 差分があれば exit 1（CI 用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))

import yaml  # noqa: E402

from rihrp.main import create_app  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml"


def render() -> str:
    schema = create_app().openapi()
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("openapi.yaml が実装と一致しません。再生成してください。", file=sys.stderr)
            return 1
        print("openapi.yaml: OK")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
