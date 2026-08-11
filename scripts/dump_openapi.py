"""OpenAPI 스펙을 docs/openapi.json 으로 떨군다.

BE 는 이 파일 하나로 계약 전체를 검토할 수 있다. 서버를 띄우지 않아도 된다.

    python -m scripts.dump_openapi           # 파일 갱신
    python -m scripts.dump_openapi --check   # 최신인지만 확인 (CI 용)

`--check` 는 파일이 코드와 어긋나면 1 로 끝난다. 계약이 조용히 바뀌는 것을
막는 장치다.
"""
import argparse
import json
import os
import sys
from pathlib import Path


OUTPUT = Path("docs/openapi.json")


def render() -> str:
    # 스펙 생성은 모델을 적재하지 않는 스텁 모드에서 한다. 모드는 스펙에
    # 영향을 주지 않지만, ONNX 세션을 만들 이유가 없다.
    os.environ.setdefault("INFERENCE_MODE", "stub")

    from app.main import create_app

    spec = create_app().openapi()
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="파일을 쓰지 않고 최신 여부만 확인한다",
    )
    args = parser.parse_args()

    rendered = render()

    if args.check:
        if not OUTPUT.exists():
            print(f"{OUTPUT} is missing; run: python -m scripts.dump_openapi")
            return 1
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            print(
                f"{OUTPUT} is stale; run: python -m scripts.dump_openapi"
            )
            return 1
        print(f"{OUTPUT} is up to date.")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
