import os
import json
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = "gemini-2.5-flash"
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "127.0.0.1")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
INLINE_LIMIT = 20 * 1024 * 1024  # 20MB — under this we use inline base64

with open(os.path.join(APP_DIR, "criteria.json"), "r", encoding="utf-8") as f:
    CRITERIA = json.load(f)

DEFAULT_POOMSAE_REFS = {}
try:
    with open(os.path.join(APP_DIR, "default_poomsae_refs.json"), "r", encoding="utf-8") as f:
        _data = json.load(f)
        DEFAULT_POOMSAE_REFS = _data.get("refs", {}) or {}
except FileNotFoundError:
    pass
except Exception as _e:
    print(f"기본 품새 데이터 로드 실패: {_e}")

CATEGORY_FOCUS = {
    "품새": "동작 순서의 정확함, 각 자세의 정확도, 흐름과 전환의 부드러움, 호흡과 기합 타이밍",
    "발차기": "발차기 동작의 자세 정확도 — 무릎 들기, 디딤발 회전, 타격 부위, 회수 속도, 균형",
    "겨루기": "풋워크, 거리(간격), 타이밍, 콤비네이션, 방어와 공격의 전환",
}

AGE_PROFILE = {
    "유아초등저": {
        "tone": "유아·초등 저학년(5~9세). 단어 매우 쉽게, 짧게. 칭찬 중심. 친근한 반말, 이모지 1~2개 OK.",
        "expectation": "기준 낮게. 기본 모양 비슷하면 OK. 디테일 요구 X. 안전·즐거움 위주로 칭찬.",
    },
    "초등중등": {
        "tone": "초등 고학년·중학생(10~14세). 또래 친구 코치 느낌. 친근한 반말.",
        "expectation": "중급 기준. 기본 자세는 정확해야 함. 미세 디테일까진 X. 성장 단계로 보고 응원.",
    },
    "고등성인": {
        "tone": "고등학생·성인(15+). 진지·구체적 톤. 기술 용어 OK.",
        "expectation": "시연 기준. 자세·호흡·기합·시선·체중 분배·연결까지 모두 봄.",
    },
}

PROFESSIONAL_PROFILE = {
    "tone": "WT 국제 시연 기준 코치 톤. 존댓말. 기술 용어 적극 사용 (회전축, 체중 분배, 디딤발 회전각, 회수 속도, 골반 정렬, 시선 처리 등). 추상적 칭찬 X — 무엇이 왜 좋고/나쁜지 구체적으로 짚기. 점수·등급은 절대 X.",
    "expectation": "시연 기준. 자세·호흡·기합·시선·체중 분배·연결·타이밍까지 전부 평가. 미세 디테일까지 짚되 개선법은 한 단계씩 명확하게. 어린이/어른 구분 없이 동일 기준.",
}


def get_kick_text():
    lines = ["[참고: 발차기 기준 — WT 국제 기준]"]
    for name, info in CRITERIA["stances"].items():
        if info.get("category") != "차기":
            continue
        bullets = " / ".join(info["criteria"])
        lines.append(f"- {name}: {bullets}")
    return "\n".join(lines)


def get_poomsae_text():
    poomsae = CRITERIA.get("poomsae", {})
    lines = ["[참고: 품새 정보 — WT 국제 기준, 태극 1~8장 + 고려 + 금강]"]
    for name, info in poomsae.items():
        if name.startswith("_"):
            continue
        techs = ", ".join(info.get("main_techniques", []))
        stances = ", ".join(info.get("main_stances", []))
        lines.append(
            f"- {name} ({info.get('level','')}): 의미={info.get('meaning','')} / "
            f"동작 {info.get('movements','?')}개 / 주요 동작={techs} / 주요 서기={stances} / "
            f"흐름={info.get('flow','')}"
        )
    lines.append("주의: 한 동작 한 동작 정확한 순서는 사범님 감수 권장. 영상에서 보이는 동작·흐름 위주로 평가.")
    return "\n".join(lines)


def get_sparring_text():
    sparring = CRITERIA.get("sparring", {})
    lines = ["[참고: 겨루기 기준 — WT 국제 기준]"]
    for key, info in sparring.items():
        if key.startswith("_"):
            continue
        bullets = " / ".join(info.get("criteria", []))
        lines.append(f"- {info.get('name', key)}: {bullets}")
    lines.append("주의: 점수·승패 표시 X. 풋워크·거리·타이밍·기술 정확도·방어 위주로 평가.")
    return "\n".join(lines)


KICK_REFERENCE = get_kick_text()
POOMSAE_REFERENCE = get_poomsae_text()
SPARRING_REFERENCE = get_sparring_text()


PHOTO_ANNOTATION_INSTRUCTIONS = (
    "[시각 표시 — 사진]\n"
    "annotations 배열에 잘한 부분(type=\"good\") 1~3개, 개선할 부분(type=\"bad\") 1~3개를 좌표로 표시.\n"
    "- x, y: 사진 안에서의 위치 (0~100 퍼센트, 왼쪽 위 0,0 / 오른쪽 아래 100,100)\n"
    "- type: \"good\" 또는 \"bad\"\n"
    "- label: 매우 짧게 (10자 이내). 예: \"무릎 들기 부족\", \"허리 안정적\"\n"
    "- 진짜로 그 위치에 표시할 게 있을 때만. 억지로 만들지 X.\n"
    "- 좌표는 신체 부위 정확한 위치에.\n"
    "- moments 배열은 빈 배열로 (영상 아니니까).\n"
)

VIDEO_MOMENTS_INSTRUCTIONS = (
    "[시각 표시 — 영상]\n"
    "moments 배열에 영상에서 가장 중요한 순간 2~4개를 timestamp(초)와 함께 짚어줘.\n"
    "각 moment 안에 그 시점의 annotations(좌표 표시)도 1~3개 포함.\n"
    "- timestamp: 그 순간이 영상 몇 초인지 (소수점 가능, 예: 1.5, 7.2)\n"
    "- description: 그 순간이 왜 중요한지 짧게 (예: \"발차기 임팩트 순간\", \"준비 자세 마지막\")\n"
    "- annotations: 그 시점의 화면 안 좌표 (사진과 동일한 형식 — x, y, type, label)\n"
    "- 정말 중요한 순간만. 억지로 만들지 X.\n"
    "- annotations 배열(top-level)은 빈 배열로 (사진 아니니까).\n"
)


def build_prompt(is_video, category, age, mode="pro", reference_sequence=None):
    medium = "영상" if is_video else "사진"
    if mode == "easy":
        profile = AGE_PROFILE.get(age, AGE_PROFILE["초등중등"])
    else:
        profile = PROFESSIONAL_PROFILE
    focus = CATEGORY_FOCUS.get(category, CATEGORY_FOCUS["발차기"])

    parts = [
        f"이 {medium}은 태권도 {category}이에요.",
        "",
        "[기준 출처] 모든 평가는 WT(World Taekwondo, 세계태권도연맹) 국제 기준을 따라요.",
        "",
        "[톤]",
        profile["tone"],
        "",
        "[평가 기준 - 매우 중요]",
        profile["expectation"],
        "",
        f"[이번 분석에서 특히 볼 것] {focus}",
        "",
    ]

    if category == "발차기":
        parts.append(KICK_REFERENCE)
        parts.append("")
        parts.append("발차기 평가 시: 영상 속 어떤 발차기인지 먼저 식별하고(앞·옆·돌려·뒤·내려), 그 발차기의 핵심 포인트(무릎·디딤발·타격 부위·회수·균형) 위주로 봄.")
        parts.append("")
    elif category == "품새":
        parts.append(POOMSAE_REFERENCE)
        parts.append("")
        parts.append("품새 평가 시:")
        parts.append("1. 어떤 품새인지 먼저 식별. 알아낸 품새 이름을 feedback 도입부에 명시.")
        parts.append("2. **동작 순서 검증** — 영상 속 실제 동작을 단계별로 표준과 대조.")
        if reference_sequence:
            parts.append("   - 아래 [등록된 표준 시퀀스]와 직접 비교 (사용자가 등록한 우리 도장 기준).")
        else:
            parts.append("   - 표준 WT 순서(머릿속 학습된 지식) 기반. 100% 확신 못할 때는 단점 끝에 \"(사범님 감수 권장)\" 추가.")
        parts.append("   - 순서 어긋난 단계가 있으면 단점에 명확히: \"N번째 동작 — 표준은 X(예: 아래막기)인데 실제는 Y(예: 얼굴지르기)\"")
        parts.append("   - 빠진 동작 / 추가된 동작도 마찬가지로 짚기")
        parts.append("3. 자세·흐름·기합 타이밍·시선 처리도 같이 평가 (순서만 보지 말기).")
        parts.append("")
        if reference_sequence:
            parts.append("[등록된 표준 시퀀스 — 우리 도장 기준 (1개 이상 품새 가능)]")
            parts.append("아래 목록 중 영상의 품새와 일치하는 항목을 골라서 그 시퀀스를 표준으로 비교하세요.")
            try:
                parts.append(json.dumps(reference_sequence, ensure_ascii=False, indent=1))
            except Exception:
                parts.append(str(reference_sequence))
            parts.append("")
    elif category == "겨루기":
        parts.append(SPARRING_REFERENCE)
        parts.append("")
        parts.append("겨루기 평가 시: 점수 매기지 말고, 풋워크·거리감·타이밍·기술 정확도·방어 자세를 봄. 잘한 장면과 개선할 장면을 골라서 코멘트.")
        parts.append("")

    parts.append("규칙: 점수/등급/비등수 X. 장점과 단점을 **명확히** 구분해서 적기. 두루뭉실 X. 가짜 피드백 X (없는 거 억지로 만들지 마).")
    parts.append("")
    parts.append("[feedback 필드 형식 — 기본]")
    parts.append("✅ 장점: 2~3개 (구체적으로 — 어느 부분이 어떻게 잘됐는지)")
    parts.append("⚠️ 단점: 1~3개 (구체적으로 — 무엇이 왜 잘못됐는지. '더 멋지게', '~하면 좋을 것 같아' 같은 부드러운 표현 금지. '디딤발 회전각 부족', '시선이 목표를 벗어남' 같은 명확한 지적)")
    parts.append("💪 응원 메시지: 1~2줄 (단점이 많아도 따뜻하게)")
    parts.append("")
    parts.append("[feedback 필드 예외 형식 — 가짜 피드백 방지]")
    parts.append("• 정말 트집 잡을 게 없을 만큼 잘했으면 → ⚠️ 단점 통째로 빼고 (✅ + 💪)만")
    parts.append("• 많이 어려워하고 진심으로 칭찬할 부분이 거의 없으면 → ✅ 빼고 (⚠️ + 💪)만 적되, 단점은 따뜻하게 작은 단계로 풀어서 + 💪로 마무리")
    parts.append("• 💪 응원 메시지는 항상 포함")
    parts.append("• 점수·등급·등수·\"몇 점\" 같은 표현 절대 X")
    parts.append("• 단점은 부드럽게 말하지 말 것 — 코치는 단점을 단점이라고 말해야 함. 단, 인격 비난 X (자세를 지적, 사람을 지적하지 X)")
    parts.append("")
    if is_video:
        parts.append(VIDEO_MOMENTS_INSTRUCTIONS)
    else:
        parts.append(PHOTO_ANNOTATION_INSTRUCTIONS)

    return "\n".join(parts)


def build_extract_prompt(poomsae_name):
    return "\n".join([
        f"이 영상은 태권도 품새 '{poomsae_name}'의 표준 시연이에요.",
        "처음부터 끝까지 모든 동작을 단계별로 순서대로 정확히 추출해주세요.",
        "",
        "각 동작마다:",
        "- n: 동작 번호 (1부터 시작)",
        "- stance: 서기 (예: 왼앞서기, 오른앞서기, 주춤서기, 앞굽이, 뒷굽이, 학다리서기 등)",
        "- technique: 기술 (예: 아래막기, 얼굴막기, 몸통막기, 얼굴지르기, 몸통지르기, 앞차기, 옆차기, 돌려차기 등)",
        "- direction: 진행 방향 (정면, 좌측, 우측, 뒤, 좌45도 등)",
        "- timestamp_sec: 영상에서 그 동작 시작 시간 (초, 소수점 가능)",
        "- kihap: 그 동작에서 기합을 넣는지 (true/false)",
        "- notes: 특이사항 (없으면 빈 문자열)",
        "",
        "중요:",
        "- 영상에 보이는 그대로 추출 (학습 데이터 짐작 X). 추출 못한 단계가 있으면 그대로 비워두지 말고 빠진 번호로 표시.",
        "- 정확히 식별하기 어려운 부분은 notes에 \"불확실\" 표시.",
        "- 영상이 정말 해당 품새가 아니면 mismatch=true로 표시하고 sequence는 빈 배열.",
    ])


_SEQUENCE_ITEM = {
    "type": "object",
    "properties": {
        "n": {"type": "integer"},
        "stance": {"type": "string"},
        "technique": {"type": "string"},
        "direction": {"type": "string"},
        "timestamp_sec": {"type": "number"},
        "kihap": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["n", "stance", "technique", "direction"],
}

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "poomsae": {"type": "string"},
        "mismatch": {"type": "boolean"},
        "total_movements": {"type": "integer"},
        "sequence": {"type": "array", "items": _SEQUENCE_ITEM},
        "summary_note": {"type": "string"},
    },
    "required": ["poomsae", "sequence"],
}


def build_compare_prompt(category, age, date1, feedback1, date2, feedback2):
    profile = AGE_PROFILE.get(age, AGE_PROFILE["초등중등"])
    parts = [
        f"[성장 비교 — 태권도 {category}, 같은 사용자, 같은 카테고리]",
        "",
        "[톤]",
        profile["tone"],
        "",
        f"[이전 ({date1})]",
        feedback1 or "(피드백 없음)",
        "",
        f"[지금 ({date2})]",
        feedback2 or "(피드백 없음)",
        "",
        "규칙:",
        "- 점수·등수·랭킹·\"몇 점\" X. 본인 vs 본인 비교만.",
        "- 거짓말로 좋아진 척 X. 진짜 같으면 그냥 '유지된 강점'으로 적기.",
        "- 따뜻한 응원 톤. 칭찬 위주, 도전은 작은 단계로.",
        "- 짧게 (5~7줄, 너무 길게 X).",
        "",
        "형식:",
        "🌱 좋아진 점: 1~2개 (구체적으로 — 어디가 어떻게 달라졌는지)",
        "🔁 변함없이 좋은 점: 1개 (선택 — 진짜 있을 때만)",
        "🎯 다음 도전: 1개 (작은 단계로)",
        "💌 한 마디: 따뜻한 응원 1~2줄",
    ]
    return "\n".join(parts)


_ANNOTATION_ITEM = {
    "type": "object",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "type": {"type": "string", "enum": ["good", "bad"]},
        "label": {"type": "string"},
    },
    "required": ["x", "y", "type", "label"],
}

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback": {"type": "string"},
        "annotations": {
            "type": "array",
            "items": _ANNOTATION_ITEM,
        },
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "number"},
                    "description": {"type": "string"},
                    "annotations": {
                        "type": "array",
                        "items": _ANNOTATION_ITEM,
                    },
                },
                "required": ["timestamp", "description", "annotations"],
            },
        },
    },
    "required": ["feedback", "annotations", "moments"],
}


def call_gemini(parts, timeout, schema=None):
    body = {"contents": [{"parts": parts}]}
    if schema is not None:
        body["generationConfig"] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]


def upload_to_files_api(file_bytes, mime_type, display_name="upload"):
    """Resumable upload to Gemini Files API. Returns file info dict."""
    metadata = json.dumps({"file": {"display_name": display_name}}).encode()
    start_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={API_KEY}"
    start_req = urllib.request.Request(
        start_url,
        data=metadata,
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(file_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(start_req, timeout=30) as resp:
        upload_url = resp.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("Files API: 업로드 URL을 못 받음")

    upload_req = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            "Content-Length": str(len(file_bytes)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        method="POST",
    )
    with urllib.request.urlopen(upload_req, timeout=600) as resp:
        result = json.loads(resp.read())
    return result["file"]


def wait_for_active(file_name, max_wait=180):
    """Poll Files API until state == ACTIVE. file_name is like 'files/abc123'."""
    deadline = time.time() + max_wait
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={API_KEY}"
    while time.time() < deadline:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        state = data.get("state", "")
        if state == "ACTIVE":
            return data
        if state == "FAILED":
            raise RuntimeError("Gemini가 영상을 처리 못 함")
        time.sleep(2)
    raise RuntimeError("영상 처리 시간 초과")


def parse_multipart(content_type_header, rfile, content_length):
    """Minimal multipart/form-data parser. Returns (fields_dict, file_dict_or_None)."""
    boundary = None
    for token in content_type_header.split(";"):
        token = token.strip()
        if token.lower().startswith("boundary="):
            boundary = token.split("=", 1)[1].strip().strip('"')
            break
    if not boundary:
        return {}, None

    body = rfile.read(content_length)
    delimiter = b"--" + boundary.encode()
    raw_parts = body.split(delimiter)
    raw_parts = raw_parts[1:-1] if len(raw_parts) >= 2 else []

    fields = {}
    file_part = None

    for part in raw_parts:
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        sep = part.find(b"\r\n\r\n")
        if sep == -1:
            continue
        header_text = part[:sep].decode("utf-8", errors="replace")
        content = part[sep + 4:]

        name = None
        filename = None
        content_type_value = None
        for line in header_text.split("\r\n"):
            lower = line.lower()
            if lower.startswith("content-disposition:"):
                for kv in line.split(";")[1:]:
                    kv = kv.strip()
                    lk = kv.lower()
                    if lk.startswith("name="):
                        name = kv.split("=", 1)[1].strip().strip('"')
                    elif lk.startswith("filename="):
                        filename = kv.split("=", 1)[1].strip().strip('"')
            elif lower.startswith("content-type:"):
                content_type_value = line.split(":", 1)[1].strip()

        if filename is not None and name == "file":
            file_part = {
                "filename": filename,
                "mime": content_type_value or "application/octet-stream",
                "data": content,
            }
        elif name:
            fields[name] = content.decode("utf-8", errors="replace")

    return fields, file_part


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/manifest.json": ("manifest.json", "application/manifest+json; charset=utf-8"),
            "/icon.svg": ("icon.svg", "image/svg+xml"),
            "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
        }
        if self.path in static_files:
            filename, ctype = static_files[self.path]
            try:
                with open(os.path.join(APP_DIR, filename), "rb") as f:
                    self._send(200, f.read(), ctype)
            except FileNotFoundError:
                self._send(404, f"{filename} not found".encode(), "text/plain; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path == "/compare":
            self._handle_compare()
            return
        if self.path == "/extract_sequence":
            self._handle_extract()
            return
        if self.path != "/analyze":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))

        if not ctype.startswith("multipart/form-data"):
            self._send(400, json.dumps({"error": "잘못된 요청 형식"}, ensure_ascii=False))
            return

        try:
            fields, file_part = parse_multipart(ctype, self.rfile, length)
        except Exception as e:
            self._send(400, json.dumps({"error": f"업로드 처리 실패: {e}"}, ensure_ascii=False))
            return

        youtube_url = (fields.get("youtube_url") or "").strip()

        if not file_part and not youtube_url:
            self._send(400, json.dumps({"error": "파일 또는 YouTube URL이 필요해요"}, ensure_ascii=False))
            return

        category = fields.get("category", "발차기")
        age = fields.get("age", "초등중등")
        mode = fields.get("mode", "pro")
        if mode not in ("pro", "easy"):
            mode = "pro"
        reference_sequence_raw = fields.get("reference_sequence", "")
        client_refs = []
        if reference_sequence_raw:
            try:
                client_refs = json.loads(reference_sequence_raw) or []
            except (json.JSONDecodeError, TypeError):
                client_refs = []

        # 사용자 덮어쓴 품새 + 기본값 병합 (사용자 우선)
        reference_sequence = None
        if category == "품새":
            user_keys = set()
            merged = []
            for item in client_refs:
                if isinstance(item, dict) and item.get("poomsae"):
                    merged.append({
                        "poomsae": item["poomsae"],
                        "sequence": item.get("sequence", []),
                        "source": "user",
                    })
                    user_keys.add(item["poomsae"])
            for name, data in DEFAULT_POOMSAE_REFS.items():
                if name in user_keys:
                    continue
                seq = data.get("sequence") if isinstance(data, dict) else None
                if seq:
                    merged.append({
                        "poomsae": name,
                        "sequence": seq,
                        "source": "default",
                    })
            if merged:
                reference_sequence = merged

        try:
            if youtube_url and not file_part:
                is_video = True
                prompt = build_prompt(True, category, age, mode, reference_sequence)
                parts = [
                    {"text": prompt},
                    {"file_data": {"file_uri": youtube_url}},
                ]
                timeout = 300
            else:
                mime = file_part["mime"]
                is_video = mime.startswith("video/")
                prompt = build_prompt(is_video, category, age, mode, reference_sequence)
                size = len(file_part["data"])

                if size <= INLINE_LIMIT and not is_video:
                    import base64
                    b64 = base64.b64encode(file_part["data"]).decode()
                    parts = [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                    timeout = 60
                else:
                    file_info = upload_to_files_api(file_part["data"], mime, file_part["filename"])
                    file_name = file_info["name"]
                    file_uri = file_info["uri"]
                    if is_video:
                        wait_for_active(file_name)
                    parts = [
                        {"text": prompt},
                        {"file_data": {"mime_type": mime, "file_uri": file_uri}},
                    ]
                    timeout = 300 if is_video else 90

            text = call_gemini(parts, timeout, schema=ANALYZE_SCHEMA)
            try:
                parsed = json.loads(text)
                feedback_text = parsed.get("feedback", "") or ""
                annotations = parsed.get("annotations", []) or []
                moments = parsed.get("moments", []) or []
            except (json.JSONDecodeError, TypeError):
                feedback_text = text
                annotations = []
                moments = []
            self._send(200, json.dumps(
                {"feedback": feedback_text, "annotations": annotations, "moments": moments},
                ensure_ascii=False,
            ))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            msg = f"Gemini 에러 {e.code}"
            if "exceeds" in err_body.lower() or "too large" in err_body.lower():
                msg = "파일이 너무 커요"
            self._send(500, json.dumps({"error": msg}, ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": f"문제 발생: {e}"}, ensure_ascii=False))

    def _handle_extract(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        if not ctype.startswith("multipart/form-data"):
            self._send(400, json.dumps({"error": "잘못된 요청 형식"}, ensure_ascii=False))
            return
        try:
            fields, file_part = parse_multipart(ctype, self.rfile, length)
        except Exception as e:
            self._send(400, json.dumps({"error": f"업로드 처리 실패: {e}"}, ensure_ascii=False))
            return

        poomsae_name = (fields.get("poomsae_name") or "").strip()
        youtube_url = (fields.get("youtube_url") or "").strip()
        if not poomsae_name:
            self._send(400, json.dumps({"error": "품새 이름이 필요해요"}, ensure_ascii=False))
            return
        if not file_part and not youtube_url:
            self._send(400, json.dumps({"error": "영상 또는 YouTube URL이 필요해요"}, ensure_ascii=False))
            return

        prompt = build_extract_prompt(poomsae_name)

        try:
            if youtube_url and not file_part:
                parts = [
                    {"text": prompt},
                    {"file_data": {"file_uri": youtube_url}},
                ]
                timeout = 300
            else:
                mime = file_part["mime"]
                file_info = upload_to_files_api(file_part["data"], mime, file_part["filename"])
                wait_for_active(file_info["name"])
                parts = [
                    {"text": prompt},
                    {"file_data": {"mime_type": mime, "file_uri": file_info["uri"]}},
                ]
                timeout = 300

            text = call_gemini(parts, timeout, schema=EXTRACT_SCHEMA)
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                self._send(500, json.dumps({"error": "Gemini 응답 파싱 실패"}, ensure_ascii=False))
                return
            self._send(200, json.dumps(parsed, ensure_ascii=False))
        except urllib.error.HTTPError as e:
            self._send(500, json.dumps({"error": f"Gemini 에러 {e.code}"}, ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": f"문제 발생: {e}"}, ensure_ascii=False))

    def _handle_compare(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        if "application/json" not in ctype.lower():
            self._send(400, json.dumps({"error": "JSON 요청만 받아요"}, ensure_ascii=False))
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._send(400, json.dumps({"error": f"JSON 파싱 실패: {e}"}, ensure_ascii=False))
            return
        f1 = (body.get("feedback1") or "").strip()
        f2 = (body.get("feedback2") or "").strip()
        cat = body.get("category") or ""
        age = body.get("age") or "초등중등"
        d1 = body.get("date1") or ""
        d2 = body.get("date2") or ""
        if not f1 or not f2:
            self._send(400, json.dumps({"error": "비교할 피드백 두 개가 필요해요"}, ensure_ascii=False))
            return
        prompt = build_compare_prompt(cat, age, d1, f1, d2, f2)
        try:
            text = call_gemini([{"text": prompt}], 30)
            self._send(200, json.dumps({"summary": text}, ensure_ascii=False))
        except urllib.error.HTTPError as e:
            self._send(500, json.dumps({"error": f"Gemini 에러 {e.code}"}, ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": f"문제 발생: {e}"}, ensure_ascii=False))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"태권도 앱 시작! {HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
