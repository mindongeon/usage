# Claude Usage Widget

Claude 구독 사용량(**5시간 한도**, **주간 한도**)을 퍼센트로 보여주는 작은 위젯입니다.

| OS | 표시 위치 | 모양 |
|---|---|---|
| Windows | 작업표시줄 (시계 왼쪽 빈 공간) | `5시간 ▓▓░░ 25%` / `주간 ▓░░░ 4%` 두 줄 + 게이지 |
| macOS | 상단 메뉴바 | `5h 19% · 7d 3%` |

게이지 색상: 50% 미만 초록 / 50~79% 주황 / 80% 이상 빨강. 오류가 나면 `!`로 표시됩니다.

**Windows 작업표시줄 위젯**
- Windows 11은 작업표시줄에 직접 붙는 위젯(deskband)을 막아 두었기 때문에, 작업표시줄 위에 투명 창을 겹쳐 띄웁니다.
- **좌클릭 드래그**: 가로 위치 이동 (저장됨)
- **우클릭**: 리셋 시각 보기, 계정 선택, 새로고침, 위치 초기화, Windows 시작 시 자동 실행, 종료
- 전체 화면 앱(게임·영상·발표) 실행 중이거나 작업표시줄이 자동 숨김 상태이면 같이 숨습니다.
- 다크/라이트 테마를 자동으로 따라갑니다.
- 기존 트레이 아이콘 방식을 원하면 `--tray` 옵션으로 실행하세요.

## 동작 방식

Claude Code의 `/usage`와 같은 엔드포인트(`https://api.anthropic.com/api/oauth/usage`)를 호출합니다.
로그인 토큰은 Claude Code가 저장한 것을 **읽기만** 합니다.

- macOS: 키체인 `Claude Code-credentials`
- Windows/Linux: `~/.claude/.credentials.json` (`CLAUDE_CONFIG_DIR` 존중)
- Windows에서는 WSL 안의 `~/.claude/.credentials.json`도 `wsl.exe`로 읽을 수 있음.
  Windows와 WSL에 서로 다른 계정으로 로그인했다면 **우클릭 → 계정**에서 고르세요
  (각 계정 이메일이 함께 표시됨). 기본값 "자동"은 Windows 로그인을 우선합니다.
- `CLAUDE_CREDENTIALS_PATH` 환경변수로 경로를 직접 지정할 수도 있음

토큰이 만료되면 위젯에 "토큰 만료"가 표시됩니다. Claude Code를 한 번 실행하면 갱신됩니다.

## 설치 & 실행

Python 3.10 이상이 필요합니다.

```bash
pip install -r requirements.txt
python -m claude_usage              # 위젯 실행 (기본 120초마다 갱신)
python -m claude_usage --interval 60
python -m claude_usage --once       # 위젯 없이 한 번만 출력
```

### Windows

- 콘솔 창 없이 실행: `run_widget.pyw` 더블클릭 (또는 `pythonw run_widget.pyw`)
- 로그인 시 자동 실행: 위젯 우클릭 → "Windows 시작 시 자동 실행"
- 설정 파일: `%APPDATA%\ClaudeUsage\config.json` (위치, 계정 선택)

### macOS

- 실행하면 Dock 아이콘 없이 메뉴바에만 나타납니다.
- 로그인 시 자동 실행: 시스템 설정 → 일반 → 로그인 항목에 실행 스크립트 추가,
  또는 아래에서 빌드한 `ClaudeUsage.app`을 로그인 항목에 등록하세요.
- 처음 실행 시 키체인 접근 허용 창이 뜨면 "항상 허용"을 누르세요.

## 실행 파일 빌드 (exe / dmg)

PyInstaller는 크로스 컴파일이 안 되므로 **각 OS에서** 빌드해야 합니다. 스크립트가 가상환경 생성부터 전부 처리합니다.

| OS | 명령 | 결과물 |
|---|---|---|
| Windows | `build_windows.bat` | `dist\ClaudeUsage.exe` (단일 파일, 콘솔 창 없음) |
| macOS | `./build_macos.sh` | `dist/ClaudeUsage.app`, `dist/ClaudeUsage.dmg` |

**GitHub Actions로 자동 빌드:** 이 폴더를 GitHub 저장소에 올린 뒤, Actions 탭에서 `build`를 수동으로 실행하거나
`v1.0.0` 같은 태그를 push하세요. 태그를 push하면 exe와 dmg가 Release에 첨부됩니다
(`.github/workflows/build.yml`).

**macOS 첫 실행:** 애플 개발자 인증서로 서명하지 않은(ad-hoc 서명) 앱이라 Gatekeeper 경고가 뜹니다.
Finder에서 앱을 **우클릭 → 열기**를 누르거나 아래 명령을 실행하세요.
```bash
xattr -dr com.apple.quarantine /Applications/ClaudeUsage.app
```
CI 빌드는 Apple Silicon(arm64)용입니다. Intel Mac에서는 해당 Mac에서 `build_macos.sh`로 직접 빌드하세요.

**Windows 첫 실행:** 서명되지 않은 exe라 SmartScreen 경고가 뜰 수 있습니다. "추가 정보 → 실행"을 누르세요.
부팅 시 자동 실행은 위젯 우클릭 메뉴에서 켜면 됩니다.

## 구조

```
claude_usage/
  api.py          자격 증명 로드 + 사용량 API 호출/파싱
  poller.py       백그라운드 주기 조회
  icons.py        트레이 아이콘 이미지(Pillow)
  taskbar_win.py  Windows 작업표시줄 위젯 (Win32 레이어드 창)
  tray.py         트레이 아이콘 방식 (Windows `--tray`, Linux)
  menubar_mac.py  macOS 메뉴바 (rumps)
  __main__.py     OS별 진입점
run_widget.pyw    Windows 콘솔 없는 실행기 (PyInstaller 진입점)
packaging/        PyInstaller 스펙, 앱 아이콘 생성기
build_windows.bat / build_macos.sh   exe / dmg 빌드 스크립트
.github/workflows/build.yml          두 OS 자동 빌드 + 릴리스
```

> 참고: 사용량 엔드포인트는 공개 문서화된 API가 아니므로 응답 형식이 바뀌면 `api.py`의
> `five_hour` / `seven_day` 파싱 부분을 조정해야 할 수 있습니다.
