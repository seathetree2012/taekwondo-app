# 태권도 자세 분석 앱

태권도 동작 영상/사진을 AI(Gemini Vision)가 분석해서 자세 피드백 + 성장 추적.

## 핵심 원칙
**점수 X, 성장 ✅** — 한국 학원 압박 문화 완화 목적.

## 기능
- 21개 동작 공식 기준 (서기/손/차기) + 품새 + 겨루기
- AI 자세 분석 (Gemini 2.5 Flash + Files API)
- 시각 표시 (잘함/단점 좌표 오버레이)
- 사용자별 성장 일기 + 비교 모드 (이전↔지금)
- PWA (홈 화면 추가, 오프라인 일부 캐시)

## 환경변수
- `GEMINI_API_KEY` (필수)
- `PORT` (기본 8080)
- `HOST` (기본 127.0.0.1, 클라우드 배포 시 0.0.0.0)

## 실행
```bash
python server.py
```

## Render 배포
- Build command: (없음)
- Start command: `HOST=0.0.0.0 python server.py`
- Environment variables: `GEMINI_API_KEY`
