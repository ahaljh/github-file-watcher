# github-file-watcher

외부 GitHub의 특정 브랜치에 **의존성 파일이 변경**되면 Slack으로 알려주는 AWS Lambda.

외부망에서 개발하고 내부망(제한된 아웃바운드 + Nexus)으로 반영하는 구조에서,
`pyproject.toml` / `uv.lock` 이 바뀌면 내부 Nexus에 새 패키지를 미리 반영해야 한다.
이 서비스는 그 변경을 감지해 담당자에게 빠르게 알린다.

## 동작 방식

```
외부 GitHub (push to develop)
        │  POST + X-Hub-Signature-256
        ▼
Lambda Function URL  ──►  lambda_handler
        │  1) HMAC-SHA256 서명 검증
        │  2) event=push & repo별 감시 대상(WATCH_TARGETS) 선택 + 브랜치 필터
        │  3) commits[].{added,modified,removed} 에서 감시 파일 매칭
        │  4) 매칭 시 Slack Incoming Webhook 으로 POST
        ▼
Slack 채널 알림
```

- **런타임 의존성 없음** — Python stdlib(`hmac`, `urllib` 등)만 사용. 소스만 zip으로 배포한다.
- GitHub Action은 쓰지 않고 **webhook + Lambda** 조합으로만 동작한다.

## 설정 (환경변수)

| 변수 | 필수 | 기본값 | 설명 |
|------|:---:|--------|------|
| `GITHUB_WEBHOOK_SECRET` | ✅ | — | GitHub webhook secret. `X-Hub-Signature-256` 검증용 |
| `SLACK_WEBHOOK_URL` | ✅ | — | Slack Incoming Webhook URL |
| `WATCH_TARGETS` | ✅ | — | 감시할 repo별 브랜치/파일 패턴 JSON (아래 참고) |
| `SLACK_USERNAME` | | `github-file-watcher` | Slack 발신자 이름 (레거시 webhook에서만 적용) |
| `SLACK_ICON_EMOJI` | | `:owl:` | Slack 발신자 아이콘 이모지 (레거시 webhook에서만 적용) |
| `SLACK_ICON_URL` | | — | Slack 발신자 아이콘 이미지 URL (레거시 webhook에서만 적용) |
| `LOG_LEVEL` | | `INFO` | 로깅 레벨 |

### Slack 발신자 이름/아이콘 (`SLACK_USERNAME` / `SLACK_ICON_EMOJI` / `SLACK_ICON_URL`)

메시지 payload에 `username` / `icon_emoji` / `icon_url` 을 넣어 보낸다. 다만 **적용 여부는 webhook 종류에 달려 있다.**

| webhook 종류 | 적용 여부 |
|------|------|
| 레거시 **"Incoming WebHooks"** 커스텀 통합 | ✅ 적용된다 |
| **Slack App** 에서 발급한 webhook (현재 표준) | ❌ 무시된다. App 설정(Basic Information → Display Information)의 이름/아이콘이 표시된다 |

- 아무것도 설정하지 않으면 `github-file-watcher` / `:owl:` 로 보낸다.
- `SLACK_ICON_URL` 만 설정하면 기본 이모지를 넣지 않는다. 이모지가 URL보다 우선 적용돼 이미지가 가려지기 때문이다.
- 이모지 이름은 Slack 이모지 선택 창에서 마우스를 올리면 나오는 `:name:` 을 그대로 쓴다.

### 감시 대상 (`WATCH_TARGETS`)

Lambda 하나로 여러 repo를 감시한다. `WATCH_TARGETS` 에 repo별 규칙을 JSON 객체로 넣는다.
알림은 모두 같은 `SLACK_WEBHOOK_URL` 채널로 가며, 메시지 헤더에 `[owner/repo]` 가 표시돼 구분된다.

```json
{
  "acme/backend":  {"branch": "develop", "files": ["pyproject.toml", "uv.lock"]},
  "acme/frontend": {"files": ["package.json", "package-lock.json"]}
}
```

- 키: `owner/repo` (대소문자 무시)
- `files` (필수): 파일 패턴 리스트 또는 콤마 구분 문자열.
- `branch` (선택): 생략하면 `develop`
- 목록에 없는 repo에서 온 push는 `ignored (repo mismatch)` 로 무시한다.
- AWS 콘솔 환경변수 값에는 위 JSON을 **한 줄로** 붙여 넣으면 된다.

### 파일 패턴 규칙

`files` 패턴은 **레포 루트 기준 전체 경로**를 `fnmatch` glob으로 비교한다(파일 이름만 비교하는 게 아니다).
GitHub이 주는 변경 파일 경로가 `pyproject.toml`, `services/api/pyproject.toml` 처럼 레포-상대 경로이기 때문이다.

- `pyproject.toml` 처럼 이름만 쓰면 **루트에 있는 파일만** 매칭한다.
- `fnmatch` 의 `*` 는 일반 glob과 달리 `/` 도 건너뛴다. 위치와 무관하게 이름으로 잡으려면 `*pyproject.toml` 처럼 쓴다.
- 특정 하위 경로만 보려면 `services/api/pyproject.toml` 처럼 경로 전체를 지정한다.

| 패턴 | 매칭되는 경로 |
|------|------|
| `pyproject.toml` | 루트 `pyproject.toml` (하위 폴더는 제외) |
| `*pyproject.toml` | 루트 + 모든 하위 폴더의 `pyproject.toml` |
| `**/pyproject.toml` | 하위 폴더의 `pyproject.toml` (⚠️ 루트는 제외) |

## 로컬 개발 / 테스트

```bash
uv sync            # dev 의존성(pytest) 설치
uv run pytest      # 단위/통합 테스트
```

## 배포 (zip 빌드 + AWS 콘솔)

런타임 의존성이 없으므로 소스만 zip으로 묶어 콘솔에서 업로드하면 된다.

### 1) 아티팩트 빌드

```bash
./scripts/build.sh          # dist/function.zip 생성
```

zip 내부 구조는 아래와 같아야 하며(핸들러 경로와 일치), `build.sh` 가 이 구조로 묶어준다.

```
function.zip
└── github_file_watcher/
    ├── __init__.py
    ├── handler.py
    ├── config.py
    ├── github.py
    └── slack.py
```

### 2) Lambda 함수 생성 (AWS 콘솔)

**Lambda 콘솔 → Create function**

- **Author from scratch** 선택
- **Function name**: `github-file-watcher` (원하는 이름)
- **Runtime**: `Python 3.13`
- **Architecture**: 기본값(`x86_64`) — 순수 파이썬이라 아키텍처 무관
- 실행 역할: 기본 옵션(*Create a new role with basic Lambda permissions*)이면 충분
- **Create function** 클릭

### 3) 코드 업로드

함수 상세 화면 → **Code** 탭 → **Upload from ▾ → .zip file** → `dist/function.zip` 선택 → **Save**

### 4) 핸들러 지정

**Code** 탭 아래 **Runtime settings → Edit** →
**Handler** 를 `github_file_watcher.handler.lambda_handler` 로 설정 → **Save**

### 5) 환경변수 설정

**Configuration → Environment variables → Edit → Add environment variable** 로 아래를 등록한다.

| Key | Value (예시) |
|-----|------|
| `GITHUB_WEBHOOK_SECRET` | `<github webhook secret>` |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/XXX/YYY/ZZZ` |
| `WATCH_TARGETS` | `{"acme/backend": {"files": ["pyproject.toml", "uv.lock"]}, "acme/frontend": {"files": ["package.json", "package-lock.json"]}}` |

> 필수: `GITHUB_WEBHOOK_SECRET`, `SLACK_WEBHOOK_URL`, `WATCH_TARGETS`.

### 6) 타임아웃 조정 (권장)

**Configuration → General configuration → Edit** → **Timeout** 을 `15초` 정도로 설정 → **Save**
(Slack 전송 네트워크 지연 여유. 기본 3초로도 대개 동작함)

### 7) Function URL 생성

**Configuration → Function URL → Create function URL**

- **Auth type**: `NONE` (GitHub이 서명하고, 코드에서 HMAC으로 검증하므로)
- **Create** 후 표시되는 **Function URL** 을 복사해 둔다 → GitHub webhook에 등록.

### 8) 코드 갱신 시

이후 코드를 바꾸면 `./scripts/build.sh` 로 다시 zip을 만들고,
**Code 탭 → Upload from → .zip file** 로 새 `dist/function.zip` 을 올리면 된다.
(환경변수/핸들러는 유지되므로 다시 설정할 필요 없음)

### 9) GitHub Webhook 등록

감시할 **각 repo마다** → **Settings → Webhooks → Add webhook** (여러 repo면 repo마다 반복)

- **Payload URL**: 7)에서 복사한 Function URL
- **Content type**: `application/json`
- **Secret**: `GITHUB_WEBHOOK_SECRET` 과 **동일한 값** (여러 repo 모두 같은 시크릿 사용)
- **Which events**: *Just the push event*

## 검증

1. GitHub Webhook 화면의 **Recent Deliveries** 에서 `ping` 이벤트가 200(`pong`)인지 확인.
2. `develop` 에 `pyproject.toml` 또는 `uv.lock` 을 변경해 push → Slack 알림 수신 확인.
   - 다른 브랜치이거나 감시 파일이 아니면 200 + `ignored` 로 응답하고 알림은 오지 않는다.
3. 문제 시 CloudWatch Logs 에서 함수 로그 확인.

## 한계

- GitHub push payload의 `commits` / 파일 목록은 **대량 push 시 truncate** 될 수 있다.
  일상적인 develop push에는 충분하지만, 완전 정확성이 필요하면 `before`/`after` SHA 로
  Compare API 를 호출하는 폴백을 추가할 수 있다(GitHub 토큰 필요).
- **중복 전달(`X-GitHub-Delivery`)을 거르지 않는다.** GitHub은 webhook을 자동 재시도하지 않으므로
  중복은 사용자가 Recent Deliveries 에서 **Redeliver** 를 누를 때만 생기고, 이는 대개 의도된 재전송이다
  (예: Slack 전송 실패로 502 응답을 받은 delivery 재시도). 따라서 이미 성공한 delivery를 Redeliver 하면
  알림이 한 번 더 간다. Lambda는 상태가 없어 확실한 중복 제거에는 DynamoDB 같은 외부 저장소가 필요하다.
