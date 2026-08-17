# Harness of Minervini v2 그린필드 재구축 계획

## 1. 목표와 완료 기준

v2는 Minervini의 SEPA를 핵심 헌법으로 삼고 TraderLion의 실행·운영 지식을 선택적으로 통합한 미국 주식 분석 하네스다. 단순히 전문가의 말투를 흉내 내는 것이 아니라, 결정론적 데이터·차트 해석·시장 맥락·위험 통제가 수렴할 때만 판단하는 분석 시스템을 만든다.

사용자가 다음 세 가지 작업을 맡길 수 있어야 한다.

- 현재 시장과 유망한 섹터·인더스트리를 평가하고, 그 안에서 실제 후보 티커를 발굴한다. 적합한 후보가 없으면 추천 수는 0개가 될 수 있다.
- 특정 티커를 분석하고 `BUY-READY`, `WAIT`, `AVOID`, `INCOMPLETE` 중 하나로 판정하면서 진입 조건·무효화 조건·확인해야 할 증거를 제시한다.
- 사용자가 이미 보유한 종목을 분석하고 `HOLD`, `SELL`, `INCOMPLETE`를 판정한다.

완료된 하네스는 다음 기준을 만족해야 한다.

- 미국 거래소 상장 보통주와 ADR만 추천 대상으로 삼는다. ETF는 시장·섹터 맥락에만 이용한다.
- 포트폴리오 비중·수량·자산배분은 제안하지 않는다.
- 암호화폐, OTC, SPAC·셸 기업, 비미국 상장 종목, 공매도, 인트라데이 매매는 범위 밖이다.
- 정밀 가격·재무·RS·시장 수치는 지정된 결정론적 모듈에서만 얻으며 기억이나 WebSearch로 보충하지 않는다.
- 모든 분석은 마지막으로 완료된 미국 정규 세션을 기본 기준일로 사용하고, 현재 진행 중인 일봉은 기술적 게이트에 포함하지 않는다.
- 데이터 부재와 명시적인 게이트 실패를 구분한다.
- Claude Code와 Codex가 동일한 실제 하네스 파일을 사용하며 호스트별 사본을 두지 않는다.
- v1과의 호환성보다 분석 정확도·감사 가능성·시점 무결성을 우선한다.

## 2. 설계 원칙과 정보 배치

### Principle over rail

`CLAUDE.md`에는 정해진 명령 순서가 아니라 판단 헌법을 둔다. 하네스는 모든 분석에서 고정 파이프라인을 무조건 실행하지 않고, 현재 질문과 이미 확보된 증거에 따라 다음 능력을 선택한다.

불변 원칙은 다음과 같다.

- 손실 가능성을 상승 가능성보다 먼저 평가한다.
- 거래하지 않음을 강한 기본값으로 삼는다.
- 강한 기업, 좋은 차트, 좋은 시장 중 하나만으로 거래를 정당화하지 않는다.
- 알려진 하드 게이트 실패를 서사·가치평가·다른 방법론으로 우회하지 않는다.
- 빠진 증거는 통과나 실패로 변환하지 않는다.
- 수치가 먼저 결정하고 차트의 시각적 해석은 질적 모호성을 해소한다.
- 웹 정보는 촉매와 서사를 설명할 수 있지만 결정론적 수치를 대체하지 않는다.

### Interface over document

명령 구문, 인자, 기본값, 출력 필드는 CLI 인터페이스가 소유한다.

- `capabilities`는 사용 가능한 능력을 열거한다.
- `describe <capability>`는 해당 능력의 입력·출력·전제조건·부작용·오류 의미를 JSON으로 반환한다.
- 각 명령의 `--help`는 구문과 플래그를 사람이 읽는 형태로 설명한다.
- 스킬에는 모든 명령과 플래그를 복제하지 않고, 언제 어떤 능력을 사용하며 결과를 어떻게 해석할지만 기록한다.
- 모델은 세션 시작 때 전체 CLI 문서를 읽지 않는다. 필요한 능력을 고른 뒤 해당 `describe` 또는 `--help`만 읽는다.
- CLI의 help, describe, JSON Schema는 동일한 capability 정의에서 생성하거나 정적 테스트로 의미 일치를 보장한다.

### Dense information과 점진적 공개

정보 소유권을 다음처럼 분리한다.

- `CLAUDE.md`: 정체성, 범위, 불변 위험 원칙, 데이터 정책, 스킬 라우팅.
- `.claude/skills/market-scan`: 시장·섹터·인더스트리·후보 발굴의 판단 과정.
- `.claude/skills/ticker-analysis`: prospective entry와 active risk의 판단 과정.
- doctrine registry: 원칙·게이트·예외·전술의 정규화된 단일 원천.
- CLI help/describe: 명령 사용법과 데이터 계약.
- 코드: 계산·검증·provider adapter·판정 로직.
- 테스트: 공개 계약과 금지 동작.

`trade-review`는 v2 범위에서 제거한다. 고정된 긴 워크플로 문서, 중복 명령 카탈로그, 호스트별 중복 프롬프트도 만들지 않는다.

## 3. 도메인 교리와 판정 모델

### Doctrine registry

교리는 사람이 읽는 장문의 출처 문서 대신 claim 단위 레지스트리로 관리한다. 각 claim은 안정적인 중립 ID를 가지며 다음 필드를 포함한다.

- 정규화된 원칙 또는 규칙
- `constitution`, `hard_gate`, `default`, `tactic`, `interpretation`, `exception`, `quarantine` 분류
- 적용되는 분석 문맥과 필요한 입력
- 실패·누락·모호함의 의미
- 다른 claim과의 우선순위 또는 충돌 관계
- 소스 corpus와 위치, 추출 근거, 충돌 해결 사유를 담은 유지보수용 provenance
- 코드·스킬·테스트가 참조할 수 있는 기계 판독 메타데이터

런타임 스킬은 책·페이지·DB 경로나 상시적인 Minervini/TraderLion 출처 라벨을 노출하지 않는다. 출처 정보는 유지보수와 감사에 필요한 registry 및 기계 메타데이터에 보존하고, 사용자 응답에는 판단에 실제로 사용된 `doctrine_ids`만 필요에 따라 제시한다.

교리 우선순위는 다음과 같이 고정한다.

1. 범위·안전·데이터 무결성
2. Minervini의 자격·위험 하드 게이트
3. 근거가 확인된 명시적 예외
4. TraderLion의 실행·운영 기본값
5. 현재 서사와 보조적 맥락

`.tmp/Minervini.db`와 `.tmp/TraderLion.db`는 구축 시 교리 추출에만 사용한다. 런타임 시장 분석에서는 읽지 않는다. 원문이 약하거나 alt-text 등에 의존해 검증하기 어려운 TraderLion 규칙은 `quarantine` 상태로 남기고 실행 규칙으로 승격하지 않는다.

### 자격 경로

Prospective entry에는 두 개의 명시적인 자격 경로만 둔다.

- 표준 경로: Stage 2와 Minervini Trend Template 8개 조건을 모두 AND 게이트로 평가한다. 충분한 거래 이력이 있는 종목이 하락 중인 200일선 아래에 있거나 한 조건이라도 명시적으로 실패하면 심층 분석으로 우회하지 않는다.
- Recent IPO Primary Base 경로: 충분한 장기 이동평균 이력이 없어 표준 경로를 평가할 수 없는 신규 상장 종목에만 적용한다. corpus에서 확인된 Primary Base 조건을 별도 claim으로 구현하며, 알려진 표준 게이트 실패를 IPO라는 이유로 면제하지 않는다. 정량화할 수 없는 베이스 품질은 `needs_chart`로 보내고 차트 검토 전에는 통과시키지 않는다.

Power Play는 세 번째 자격 경로가 아니라 fundamentals 정책이다. 기술적 자격, 시장 정렬, VCP 품질과 위험 통제는 그대로 요구한다. 검증 가능한 현재 성장 수치가 약하거나 부족하더라도 source-faithful Power Play 조건이 충족되면 맥락으로 허용할 수 있지만, 회계 무결성·계속기업 위험·과도한 희석 같은 치명적 결함은 면제하지 않는다.

TraderLion의 early entry, 이동평균 관리, 실행 전술은 Minervini 자격을 통과한 뒤에만 적용한다. early entry가 최선의 진입이라 판단되면 `[TL-EARLY]`로 명시하고 다음을 함께 제공한다.

- 아직 갚지 않은 confirmation debt
- 이후 확인되어야 할 Minervini pivot 또는 breakout
- 조기 진입을 즉시 무효화할 정확한 조건
- 일반 breakout보다 높은 오판 가능성

### 분석 축

심층 분석은 하나의 불투명한 종합 점수 대신 다음 축을 분리해 반환한다.

- 시장 환경과 실제 리더의 traction
- 기술적 자격과 lifecycle stage
- 섹터·인더스트리 상대 강도
- setup, VCP, 공급 흡수와 진입 시점
- EPS·매출·마진·추정치 변화와 재무 품질
- 회사 유형과 리더십 프로파일
- 위험, 예상 행동, 시간 정지 조건과 보상 대 위험
- 데이터 완전성·신선도·출처 충돌

시장·그룹 랭킹은 가격 모멘텀, breadth, 고점 근접도, RS 집중도, Stage 2 후보 수, 실제 리더의 행동을 투명한 signal vector로 제시한다. 임의의 단일 점수가 최종 추천을 자동 결정하지 않는다.

### 판정 규칙

Prospective verdict는 다음처럼 결정한다.

- `BUY-READY`: 허용된 자격 경로가 통과했고, 진입 트리거가 현재 충족됐으며, 시장·setup·필요한 fundamentals·위험이 수렴하고, 치명적인 누락 증거가 없다.
- `WAIT`: 자격은 유지되지만 pivot, 공급 흡수, 시장 정렬, reward-to-risk 또는 확인 증거가 아직 충분하지 않다.
- `AVOID`: 범위 위반, 명시적 하드 게이트 실패, 구조적 파손, 치명적 재무 위험 또는 합리적인 2R 경로 부재가 확인됐다.
- `INCOMPLETE`: 결론에 필수적인 데이터가 없거나, provider 실패·RS 신선도 문제·필수 차트 모호성 때문에 통과와 실패를 정직하게 구분할 수 없다.

Active verdict는 다음처럼 결정한다.

- `HOLD`: 사용자의 진입 정보와 무효화 기준을 포함한 필수 증거가 있고 객관적인 매도 조건이 발생하지 않았다.
- `SELL`: hard stop, 구조적 무효화 또는 명시적인 매도 규칙이 발생했다.
- `INCOMPLETE`: 판단에 필요한 포지션 맥락이나 데이터가 없다.

Active 분석에는 진입 가격·진입일과 현재 stop 또는 무효화 기준을 요구한다. 보유 수량과 계좌 규모는 요구하거나 저장하지 않는다. 사용자가 명시적으로 실시간 stop 확인을 요청하고 stop 가격을 제공한 경우에만 현재 부분 세션의 객관적인 hard-stop breach가 `SELL`을 발생시킬 수 있다. 그 외 모든 기술 판정은 완료된 세션만 사용한다.

개인 평균 수익률을 제공한 경우 stop 상한에 `평균 수익의 절반` 제약을 추가한다. 제공하지 않은 경우에도 구조적 무효화, 10% 절대 상한, 평균 손실 6–7% 지향, 최소 2R 저항 분석으로 일반 판정을 완료할 수 있다.

## 4. 데이터·시점·provider 구조

### Security master와 추천 universe

SEC와 Nasdaq Trader 데이터를 결합해 안정적인 `instrument_id`, 현재 심볼, 거래소, instrument type, ADR 여부와 CIK를 관리한다. 심볼 변경과 재사용 때문에 심볼 문자열만을 영구 식별자로 사용하지 않는다.

추천 universe에는 미국 거래소 상장 보통주와 ADR만 포함한다. ETF는 시장 및 그룹 맥락에만 사용하고, SPAC·셸·OTC·우선주·워런트 등은 필터링 사유를 구조화해 반환한다.

### Provider 책임

- yfinance: 일·주 가격과 거래량.
- `ibd-rs-rating==0.5.0`: SEPA RS percentile의 유일한 권위 있는 출처.
- SEC filed facts: 제출 시점이 확인되는 재무 수치의 source of record.
- FMP: API 키가 있을 때 사용하는 선택적 추정치·추가 재무·분류 enrichment.
- Finviz-derived data: discovery와 현재 시장·그룹 맥락.
- WebSearch: 현재 촉매, 회사·인더스트리 서사와 정성적 설명.

FMP와 SEC 수치가 충돌하면 평균내지 않는다. SEC 제출 수치를 기준값으로 두고 FMP 값과 차이를 함께 표시한다. ADR은 SEC에 보고된 IFRS 또는 US-GAAP 기준을 그대로 명시한다.

`ibd-rs-rating`의 계산식을 하네스에 복제하지 않는다. adapter는 라이브러리 버전, rating 기준일, coverage, freshness와 library-declared metadata를 반환한다. 대상 ticker의 rating이 없거나 데이터가 오래됐거나 전체 coverage가 붕괴하면 RS 게이트를 자체 계산으로 대체하지 않고 `INCOMPLETE`로 처리한다. 과거 `--as-of` 요청에는 해당 날짜까지 실제로 저장된 RS snapshot만 사용할 수 있으며 현재 rating을 과거에 소급 적용하지 않는다.

### 시점 무결성

모든 capability는 `--as-of`를 지원한다. 기본값은 미국 거래소 기준 마지막 완료 세션이다.

- 가격 게이트는 해당 기준일까지 완료된 daily/weekly bar만 사용한다.
- 재무 수치는 `filed_at <= as_of`인 제출물만 사용한다.
- 추정치와 분류도 가능한 경우 관측 시점을 함께 보존한다.
- 미래 데이터가 historical analysis에 섞이면 테스트 실패로 처리한다.
- 현재 부분 세션의 가격·거래량은 일반 게이트, breakout, VCP, market regime 판정에 사용하지 않는다.

Provider 실패는 동일 요청을 한 번만 재시도한다. 두 번째 실패 후에는 해당 증거를 `unavailable`로 반환하며 웹 값이나 수기 계산으로 보충하지 않는다.

캐시는 provider, instrument, capability, as-of, adapter 버전과 옵션을 키에 포함한다. `--no-cache`는 읽기와 쓰기를 모두 우회한다.

## 5. 공개 CLI와 데이터 계약

canonical invocation은 저장소 루트에서 다음 형태를 유지한다.

```text
bash scripts/bootstrap.sh
scripts/.venv/bin/python scripts/pipeline <capability> [arguments] [flags]
```

단일 composable CLI가 다음 capability를 제공한다.

- Meta: `capabilities`, `describe`, `health`, `clock`, `doctrine show`
- Market: `market snapshot`, `market candidates`
- Ticker: `ticker qualify`, `ticker setup`, `ticker fundamentals`, `ticker peers`, `ticker risk`, `ticker chart`
- Research ledger: `watchlist show`, `watchlist history`, `watchlist record`, `watchlist annotate`, `watchlist export`

`market candidates`의 `limit`과 cursor는 전송량과 pagination만 제어한다. 최종 추천 수를 고정하지 않는다. 어떤 후보도 충분하지 않으면 분석 응답은 0개 추천으로 끝난다.

모든 JSON capability는 stdout에 정확히 하나의 v2 envelope를 출력한다.

```text
schema_version
operation
request
as_of
status
data
signals
missing
sources
doctrine_ids
next_capabilities
side_effects
```

`status`는 `ok`, `partial`, `unavailable`, `needs_input` 중 하나다. 하드 게이트만 `pass` 또는 `fail`을 사용하고, 그 외 signal은 `supports`, `contradicts`, `mixed`, `observed`, `unavailable`, `needs_input`, `needs_chart`, `not_applicable` 중 하나를 사용한다.

- 정상 또는 정직한 부분 결과는 exit 0.
- 잘못된 사용자 입력은 exit 2와 JSON 오류 envelope.
- 내부 계약 위반은 exit 3과 JSON 오류 envelope.
- `--help`만 plain text 출력의 예외다.
- `compact`와 `full` 출력은 정보량만 다르고 verdict·signal·누락 의미는 동일해야 한다.

각 capability는 버전이 고정된 JSON Schema를 갖는다. `ticker chart`가 차트 artifact를 만들면 ignored cache 위치에 기록하고 envelope의 `side_effects`와 artifact manifest에 경로·데이터 기준일·렌더링 입력 hash를 남긴다.

## 6. 연구 ledger와 부작용

ledger는 추천 기록과 판단 변화 추적을 위한 로컬 ignored SQLite DB다. 기본 위치는 저장소 내부 ignored state 디렉터리이며 환경변수로 경로를 교체할 수 있다.

일반 시장·티커 분석은 ledger를 생성하거나 수정하지 않는다. 쓰기는 `watchlist record`, `watchlist annotate`, 명시적인 file export에서만 발생한다.

저장할 수 있는 정보는 다음으로 제한한다.

- instrument_id와 당시 심볼
- 분석 기준일과 capability output hash
- verdict, 조건, 무효화 기준과 사용자 메모
- 사용한 doctrine ID와 evidence quality
- 이후 상태 변경 이력

포지션 수량, 계좌 가치, 배분 비율은 schema 자체에 넣지 않는다. versioned migration과 이전 schema 호환성은 테스트한다.

## 7. 하네스 파일과 양쪽 호스트 공유

실제 파일 소유권은 다음처럼 고정한다.

```text
CLAUDE.md                         실제 파일
AGENTS.md -> CLAUDE.md            심볼릭 링크
.claude/skills/                  실제 스킬 디렉터리
.agents/skills -> ../.claude/skills
```

기존 `.codex/skills`는 제거한다. Claude와 Codex용 동일 내용을 별도 파일로 생성하지 않는다.

`.claude/settings.json`에는 Claude Code의 permissions 및 필요한 hook wiring만 둔다. 교리, 워크플로 또는 명령 설명을 복제하지 않는다. hooks는 JSON 계약 검증처럼 보편적이고 결정론적인 안전장치에만 사용하며 투자 판단을 고정된 순서로 강제하지 않는다.

정적 테스트는 다음을 검증한다.

- 두 심볼릭 링크의 상대 target과 해석된 realpath
- 실제 스킬 파일의 inode/hash 동일성
- 호스트별 복제된 `SKILL.md`, 교리 문서 또는 명령 카탈로그가 없음
- 루트 문서와 스킬 사이에 서로 모순되는 범위·판정 용어가 없음
- `.codex/skills`가 존재하지 않음

## 8. 서브에이전트 운용

서브에이전트 수는 고정하지 않는다. 분석 범위와 후보 수, 데이터 모호성에 따라 0개부터 필요한 만큼만 사용한다.

- 넓은 탐색과 개별 후보 gate 검증은 병렬 scout가 수행할 수 있다.
- 질적 차트 판단이 필요한 후보만 chart-review 작업으로 보낸다.
- 여러 후보나 상충 증거를 종합할 때만 최종 synthesis·adversarial review를 추가한다.
- 알려진 하드 게이트 실패가 확인된 후보는 심층 분석 fan-out을 중단한다.
- 하위 에이전트는 최종 투자 판정을 독립적으로 확정하지 않고 구조화된 증거를 반환한다.
- 최종 응답은 원시 결과를 복사하지 않고 모순·중복·누락을 해결한 하나의 판단으로 합성한다.

행동 E2E는 Claude가 아니라 Codex 서브에이전트를 반복 실행해 검증한다. Claude Code는 동일 파일 발견, skill routing, 링크 무결성과 정적 호환성까지만 검증한다.

## 9. TDD 및 검증 계획

구현 세션은 어떤 테스트 코드도 쓰기 전에 `tdd` 스킬을 읽는다. 모든 v2 테스트, fixture, evaluator, baseline과 helper는 `tests/260817` 아래에 둔다.

권장 구조는 다음과 같다.

```text
tests/260817/contracts/
tests/260817/doctrine/
tests/260817/unit/
tests/260817/integration/
tests/260817/fixtures/
tests/260817/e2e/
tests/260817/live/
tests/260817/baselines/v1/
```

테스트는 내부 함수가 아니라 다음 공개 seam부터 RED로 작성한다.

1. capability definition과 JSON Schema
2. market clock과 `--as-of`
3. provider adapter 계약
4. eligibility route와 verdict truth table
5. CLI exit code·stdout 계약
6. ledger의 명시적 부작용
7. skill routing과 호스트 링크
8. 전체 행동 E2E

필수 결정론적 시나리오는 다음과 같다.

- 표준 Stage 2 및 8/8 통과
- 한 개의 알려진 게이트 실패와 여러 증거 누락의 구분
- 장기 이력이 부족한 recent IPO의 Primary Base 경로
- 차트 모호성이 `needs_chart` 및 `INCOMPLETE`를 발생시키는 경우
- Power Play가 fundamentals만 제한적으로 예외 처리하는 경우
- `[TL-EARLY]`의 confirmation debt와 무효화
- 현재 부분 bar가 breakout 또는 시장 판정을 오염시키지 않는 경우
- historical `--as-of`에 미래 가격·재무·RS가 섞이지 않는 경우
- provider 1회 재시도 후 unavailable 처리
- RS stale·missing·coverage collapse
- SEC와 FMP 값 충돌
- 제외 대상 instrument와 심볼 변경
- 후보가 0개인 시장 응답과 pagination
- active 분석의 필수 입력 누락
- 명시적인 live hard-stop breach
- 분석 명령이 ledger를 암묵적으로 생성하지 않는 경우
- compact/full의 의미 동일성
- help, describe, schema의 일치
- 심볼릭 링크와 중복 파일 금지
- 구형 command·skill·workflow 참조의 완전 제거

Codex 행동 E2E는 최소 세 번의 독립 반복으로 다음 프롬프트군을 평가한다.

- 현재 유망한 섹터·인더스트리와 후보 추천
- 특정 ticker의 조건부 매수 분석
- 현재 보유 종목의 HOLD/SELL 분석
- recent IPO 분석
- 데이터 provider 장애 상태
- 값이 싸졌다는 이유로 broken leader 매수를 유도하는 질문
- 알려진 Trend Template 실패를 무시하라는 지시
- 웹 수치가 모듈 수치와 충돌하는 상황
- 포트폴리오 비중을 요구하는 범위 이탈 질문
- 추천할 만한 후보가 없는 약한 시장

다음은 release-blocking 오류다.

- 결정론적 시장 수치 조작 또는 기억 기반 보충
- 미래 데이터 누출
- 하드 게이트 우회
- 범위 밖 종목 추천
- 포트폴리오 비중 제안
- fixture의 verdict truth table 위반
- stdout JSON 계약 파손
- 동일 하네스 파일 공유 실패

결정론적·통합 테스트는 100% 통과해야 한다. 행동 E2E는 모든 critical assertion을 세 번 모두 통과하고, 비치명 평가 항목의 종합 점수가 90% 이상이어야 한다. live smoke에서 외부 provider 자체가 일시적으로 unavailable인 것은 비차단으로 기록하되, 설치 실패·지원하지 않는 schema·버전 불일치·파싱 계약 파손은 차단한다.

v1과의 A/B 비교는 회귀 진단 자료일 뿐이다. v1과 다른 결과만으로 v2 실패로 판정하지 않으며, v2가 더 엄격한 데이터 무결성이나 `INCOMPLETE` 판정을 내린 경우 그 근거를 평가한다.

## 10. 구현 순서와 단계별 완료 판정

### 1단계 — v1 진단 동결

- 현재 v1의 테스트 72개를 다시 실행하고 최종 commit SHA, capability, 알려진 결함과 대표 행동을 기록한다.
- `tests/260817/baselines/v1`에는 비교에 실제로 사용하는 compact manifest만 만든다.
- 완료 판정: v1 baseline이 commit/tag 후보와 연결되고 v2 테스트가 이를 진단 입력으로 읽을 수 있다.

### 2단계 — 교리 추출과 충돌 해결

- Minervini corpus에서 헌법·하드 게이트·예외를 추출하고 TraderLion corpus에서 실행·운영 보완 규칙을 추출한다.
- claim ID, 우선순위, 적용 문맥, 실패·누락 의미와 provenance를 확정한다.
- 불확실하거나 충돌하는 TraderLion 규칙은 quarantine한다.
- 완료 판정: 모든 실행 가능한 claim이 적어도 하나의 소비자와 테스트를 가지며 미해결 충돌이 0개다.

### 3단계 — 공개 계약 RED

- capability registry, schemas, status/signal vocabulary, exit code, verdict truth table에 대한 실패 테스트를 먼저 작성한다.
- 완료 판정: 아직 구현되지 않은 계약 때문에 의도한 테스트가 RED이고, 테스트가 내부 구현 세부사항에 결합하지 않는다.

### 4단계 — 시간·식별자·provider 기반

- market clock, security master, cache key와 provider adapter를 구현한다.
- yfinance, SEC, Finviz, first-party RS와 optional FMP 경계를 분리한다.
- 완료 판정: frozen fixture에서 point-in-time, retry, stale, discrepancy와 instrument filtering 테스트가 GREEN이다.

### 5단계 — 결정 엔진

- 표준 자격, Primary Base, Power Play, setup, fundamentals, leadership, risk와 verdict reducer를 구현한다.
- 완료 판정: 모든 truth-table 테스트가 GREEN이고 알려진 실패·누락·차트 모호성이 서로 다른 상태로 유지된다.

### 6단계 — composable CLI

- meta, market, ticker capability와 help/describe/schema를 구현한다.
- 완료 판정: 모든 명령이 단일 JSON envelope, 안정적인 exit code와 `next_capabilities`를 반환하고 help parity 테스트를 통과한다.

### 7단계 — ledger

- explicit-write SQLite schema, migration, history와 export를 구현한다.
- 완료 판정: read-only 분석 전후 DB와 filesystem state가 동일하고 명시적 write만 감사 가능한 변경을 만든다.

### 8단계 — 하네스 재작성

- 얇은 `CLAUDE.md`, 두 runtime skill, 필요한 최소 permissions/hooks와 정확한 심볼릭 링크를 구성한다.
- 완료 판정: static routing·중복·링크 검사가 통과하고 구형 command catalog가 스킬에 남지 않는다.

### 9단계 — Codex 행동 및 적대적 E2E

- 반복 Codex subagent 평가를 실행하고 실패 사례를 doctrine, interface 또는 code 수준에서 수정한다.
- 완료 판정: critical assertion 100%, 반복 종합 점수 90% 이상이다.

### 10단계 — live smoke와 품질 게이트

- 현재 시장, 대표 대형주, recent IPO, ADR, 제외 instrument, provider 장애를 실제 데이터로 점검한다.
- 완료 판정: 외부 availability를 제외한 schema·버전·설치·파싱 오류가 0개이고 모든 deterministic suite가 재통과한다.

### 11단계 — v1 보존과 v2 cutover

- v2 merge 직전 당시 `main`의 최종 v1 commit에 annotated tag `harness-v1-final`을 생성하고 원격에 push한다.
- 해당 tag로 GitHub Release를 발행한다.
- Release notes는 한국어로 v1의 목적, 최종 72-test 결과, 알려진 결함, 삭제 이유, v2 계획 및 cutover PR 링크, 복구 명령을 포함한다.
- 복구 명령은 `git switch --detach harness-v1-final`로 고정한다.
- v2 cutover PR은 삭제되는 v1 artifact와 각각의 v2 대체물을 명시적으로 매핑한다.
- v2가 실제로 소비하는 compact baseline·fixture가 아닌 v1 runtime code, 문서, 스킬, workflow, agent, 테스트는 main에서 삭제한다.
- `legacy/` 디렉터리와 compatibility shim은 만들지 않는다.
- `.tmp/Minervini.db`와 `.tmp/TraderLion.db`는 v1 runtime artifact가 아니라 교리 원천이므로 이 삭제 대상에 포함하지 않는다.
- 완료 판정: tag와 Release가 존재하고, baseline을 제외한 v1 잔존물이 없으며, `rg`로 구형 command·skill·workflow·`trade-review` 참조가 0건이다.

### 12단계 — PR과 최종 인수

- 구현은 `feat/minervini-harness-v2` 브랜치에서 논리적 단위로 커밋한다.
- cutover PR에는 새 공개 인터페이스, 삭제 내역, 교리 우선순위, 데이터 제한, 실제 검증 명령과 결과를 기록한다.
- 모든 차단 gate가 통과한 뒤 squash merge한다.
- 완료 판정: main이 v2만 포함하고, v1은 `harness-v1-final` tag와 GitHub Release로 완전히 복구 가능하다.

## 11. 명시적 비범위와 후속 확장

v2 최초 릴리스에는 다음을 포함하지 않는다.

- 포트폴리오 구성·비중·수량 추천
- 완료된 매매일지의 trade-review
- 공매도·옵션·암호화폐·인트라데이 전략
- TraderLion의 secondary/swing expansion 종목군
- Massive, Benzinga, Finnhub adapter
- 약한 근거의 source rule
- 고정 추천 개수와 고정 subagent 수
- v1 호환 계층

이 항목들은 v2 핵심 계약과 평가가 안정된 뒤 별도 계획으로 추가한다.

## 12. 계획 문서 인계

이 계획은 Plan Mode가 종료된 뒤 구현 없이 그대로 `docs/plans/260817/harness-v2-greenfield-plan.md`에 저장하고, 저장된 파일을 다시 읽어 누락·변형이 없는지 확인한다. 현재 계획 세션에서는 파일 수정, tag 생성, Release 발행 또는 Git 작업을 수행하지 않는다.
