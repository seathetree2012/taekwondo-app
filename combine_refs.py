import json
import os
from datetime import datetime

SRC_DIR = os.path.join(os.path.dirname(__file__), "extract_results")
DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_poomsae_refs.json")

# 매핑: 파일명 -> 품새 이름
FILE_TO_NAME = {
    "tg1.json": "태극1장",
    "태극2장.json": "태극2장",
    "태극3장.json": "태극3장",
    "태극4장.json": "태극4장",
    "태극5장.json": "태극5장",
    "태극6장.json": "태극6장",
    "태극7장.json": "태극7장",
    "태극8장.json": "태극8장",
    "고려.json": "고려",
    "금강.json": "금강",
}

YT_SOURCES = {
    "태극1장": "https://www.youtube.com/watch?v=WhkjRruCBTo",
    "태극2장": "https://www.youtube.com/watch?v=tGlrUplKHh8",
    "태극3장": "https://www.youtube.com/watch?v=ksSqKt0UkWo",
    "태극4장": "https://www.youtube.com/watch?v=Lt917gacJho",
    "태극5장": "https://www.youtube.com/watch?v=VdqNEAHWCBM",
    "태극6장": "https://www.youtube.com/watch?v=jcBwWo4wN7c",
    "태극7장": "https://www.youtube.com/watch?v=RI1bX0gUJpo",
    "태극8장": "https://www.youtube.com/watch?v=Gr_Je2ZkgkI",
    "고려": "https://www.youtube.com/watch?v=mGa60JDtWmg",
    "금강": "https://www.youtube.com/watch?v=CRGVSOmaQaY",
}

merged_refs = {}
issues = []

for fname, pname in FILE_TO_NAME.items():
    path = os.path.join(SRC_DIR, fname)
    if not os.path.exists(path):
        issues.append(f"{pname}: 파일 없음")
        continue
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        issues.append(f"{pname}: 파싱 실패 ({e})")
        continue

    if data.get("mismatch") or not data.get("sequence"):
        issues.append(f"{pname}: 시퀀스 비어있음 또는 mismatch (note: {data.get('summary_note', '')[:80]})")
        continue

    seq = data.get("sequence", [])
    merged_refs[pname] = {
        "sequence": seq,
        "total_movements": data.get("total_movements", len(seq)),
        "summary_note": data.get("summary_note", ""),
        "source_url": YT_SOURCES.get(pname, ""),
        "extracted_at": datetime.utcnow().isoformat() + "Z",
    }
    print(f"✅ {pname}: {len(seq)}동작")

# 기존 파일 읽고 합치기 (구조 유지)
existing = {"_note": "기본 표준 시퀀스 — Kukkiwon/WT 공식 영상에서 dev 도구로 추출", "_version": 1}
if os.path.exists(DEFAULTS_PATH):
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
            existing.update({k: v for k, v in old.items() if k != "refs"})
    except Exception:
        pass

existing["refs"] = merged_refs
existing["_note"] = "기본 표준 시퀀스 — Kukkiwon/WT 공식 영상에서 dev 도구로 추출 (2026-05-09)"
existing["_updated_at"] = datetime.utcnow().isoformat() + "Z"

with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)

print(f"\n저장: {DEFAULTS_PATH}")
print(f"성공: {len(merged_refs)}/{len(FILE_TO_NAME)}")
if issues:
    print("\n⚠️ 문제:")
    for i in issues:
        print(f"  - {i}")
