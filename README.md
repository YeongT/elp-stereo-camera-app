# ELP Stereo Camera App

ELP 계열 side-by-side USB 스테레오 카메라 콘솔 — 라이브 뷰어, 녹화·스냅샷·타임랩스,
스테레오 캘리브레이션, 카메라 프로필 관리. 기준 하드웨어는 ELP-3DGS1200P01
(OmniVision OG02B10 ×2, global shutter, SBS MJPEG 합성 출력)이고, 렌즈·해상도
변형은 앱 안의 프로필로 관리한다.

캘리브레이션 산출물(npz + json, `.runtime/calibration/`)은 다운스트림 depth
파이프라인(StereoSGBM → Q 역투영)이 그대로 소비할 수 있다.

## 실행

```
uv sync
uv run python main.py              # 별도 GUI 프로세스 시작 후 콘솔 반환
uv run python main.py --foreground # 현재 콘솔에 붙여 실행 (디버깅용)
uv run python main.py --version    # 앱 버전 출력
```

Windows 실행 파일 빌드·검증·GitHub Release 절차는
[Windows release runbook](docs/WINDOWS_RELEASE.md)를 따른다.

## 화면 구성

- **헤더** — 스트림 시작/정지와 상태 표시. 어느 탭에서든 스트림을 제어한다.
- **라이브** — 프로필·장치·모드는 상단 바, 보기·캡처·장치 도구는 우측 패널에
  그룹핑. 하단 로그 패널은 상태 줄의 로그 버튼으로 접을 수 있다.
- **캘리브레이션** — 서브탭 3개: 수집·실행(체스보드 쌍 → 스테레오 캘리브레이션,
  `.runtime/calibration/` 저장), 정렬 검증(보정 전후 비교 + 에피폴라 가이드),
  뎁스(SGBM disparity map 라이브, 컬러맵·파라미터 조절, hover 지점 거리 mm).
- **라이브러리** — 저장 폴더의 녹화/스냅샷 목록과 앱 내 재생·미리보기.

세부 동작·단축 설명은 각 컨트롤의 툴팁이 담당한다. 생성물 경로는
`elp_console/paths.py`가 단일 소스다.

## 캡처 파이프라인

USB 링크가 불량하면 MJPEG 프레임이 잘린 채 도착하고, 일반 디코더는 이를 오류
없이 회색/초록으로 채워 표시한다. 기본 경로(FFmpeg/PyAV)는 dshow raw 패킷을
직접 받아 SOI/EOI 마커 → 디코드 → 채움 행 검증을 통과한 프레임만 표시하고,
드롭 비율을 상태 칩에 노출한다. OpenCV 폴백(MSMF/DSHOW)은 size → fps → fourcc
순서로 설정해야 YUY2로 떨어지는 카메라 펌웨어 문제를 피한다.

프레임 처리 순서는 `디코드 → 교체/회전 → (캘리브레이션 캡처) → 렉티피케이션 →
스냅샷/녹화 → 표시 합성`. 캘리브레이션 캡처가 렉티피케이션보다 앞에 있는 것이
의도 — 캘리브레이션은 왜곡된 원본을 봐야 한다.

## 테스트·도구

```
uv run pytest                          # 단위 테스트
uv run python tools/screenshot_ui.py   # UI 상태별 스크린샷 (.artifacts/ui/)
uv run python tools/selftest_live.py   # 실 카메라로 메인 창 자체 점검
uv run python tools/probe_camera.py    # 백엔드·설정 순서 조합별 협상 결과
```

기타 진단 스크립트는 `tools/` 참고.

## 문제 해결

"드롭" 칩이 10%를 넘으면 소프트웨어가 아니라 USB 링크 문제다. UVC 영상은
isochronous 전송이라 손상 패킷을 재전송 없이 버린다: USB 2.0 A 케이블 직결,
메인보드 후면 포트 사용, USB 허브 전원 절약 해제를 먼저 시도할 것.

## 라이선스

All rights reserved — 열람·참고용 공개. 사용·복제·수정·배포는 사전 서면 허가
필요. 상세는 [LICENSE](LICENSE).
