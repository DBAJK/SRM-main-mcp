"""벤더 데이터 부트스트랩 — 1회 실행. (B 소유)

    5G-Marketplace/data/vendors.json   →   data/vendors.json
    + 각 벤더에 "regions": [...] 추가 (location 문자열에서 유도)

정정 G — 벤더 데이터가 두 벌이고 호환되지 않는다.

                모델 A (채택)                       모델 B (폐기)
    파일        5G-Marketplace/data/vendors.json    .../vendor_registry/*.json
    구조        리스트 5개, 중첩 offerings          dict, offering_id 평탄화 (6건)
    rating      있음 (4.5~4.9)                     **없음**

engine.py:792 의 점수 계산은 모델 A만 읽는다. 모델 B를 쓰면 rating 이 항상 기본값 3.0으로
떨어져 ⑤의 레이팅 갱신이 점수에 전혀 반영되지 않는다.

부수 효과로 engine.py:115 의 await 누락 버그가 고칠 필요 없이 사라진다 (해당 경로 미사용).

⚠️ warm 모드에서 data/vendors.json 은 실행에 걸쳐 누적된다 (설계서 §5.0). 재실행하면
   누적 레이팅이 초기화되므로 --force 없이는 덮어쓰지 않는다.

    python tools/bootstrap_vendors.py          # 없을 때만 생성
    python tools/bootstrap_vendors.py --force  # cold 모드. 레이팅 초기화
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.store import read_json, write_json  # noqa: E402

# location 문자열 → region 코드. 모델 A 의 벤더 5곳이 전부다.
LOCATION_TO_REGION = {
    "New York, USA": "us-east",
    "London, UK": "eu-west",
    "Tokyo, Japan": "ap-northeast",
    "Berlin, Germany": "eu-central",
    "Singapore": "ap-southeast",
}


def derive_regions(vendor: dict) -> list[str]:
    """location 문자열 → regions 리스트.

    매핑에 없는 location 이 들어오면 조용히 넘기지 않는다 — region 필터가 아무것도
    못 찾는 상태로 실험이 돌아가면 조달 분기가 통째로 죽는다.
    """
    location = vendor.get("location", "")
    if location not in LOCATION_TO_REGION:
        raise KeyError(
            f"알 수 없는 location: {location!r} (vendor {vendor.get('id')}). "
            f"LOCATION_TO_REGION 에 추가할 것."
        )
    return [LOCATION_TO_REGION[location]]


def bootstrap(force: bool = False) -> int:
    src = paths.SRC_VENDORS_JSON
    dst = paths.VENDORS_JSON

    if not src.exists():
        print(f"원본이 없다: {src}", file=sys.stderr)
        return 1

    if dst.exists() and not force:
        print(f"이미 있다: {dst}\n  누적 레이팅을 버리려면 --force")
        return 0

    vendors = read_json(src)
    if not isinstance(vendors, list):
        print(f"모델 A 가 아니다 (리스트가 아님): {src}", file=sys.stderr)
        return 1

    for vendor in vendors:
        vendor["regions"] = derive_regions(vendor)

    write_json(dst, vendors)

    print(f"{src}\n  → {dst}  (벤더 {len(vendors)}곳)")
    for vendor in vendors:
        print(f"  {vendor['id']:10} {vendor['name']:22} rating {vendor['rating']:.2f}"
              f"  regions {vendor['regions']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true",
                   help="이미 있는 data/vendors.json 을 덮어쓴다 (누적 레이팅 소실)")
    sys.exit(bootstrap(**vars(p.parse_args())))
