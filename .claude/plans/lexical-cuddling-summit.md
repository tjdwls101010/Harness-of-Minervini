# Harness of Minervini v2.5 — 판단 평면 재작성 계획

## Context

이 레포는 Minervini SEPA(+ TraderLion 실무 계층)를 클로드(코덱스)가 실행하는 투자 분석가 하네스다. 목표는 "Minervini를 채택하되 능가하는 복제인간", 기준은 오직 퀄리티. 성진의 문제의식("최선인지 모르겠다, 판단 품질 의심")을 검증하기 위해 이 계획 세션에서 5개 독립 소스로 전면 감사를 수행했다: ① 메인(Fable) 직접 판독, ② codex(gpt-5.6-sol, xhigh) 독립 적대 감사, ③ codex 원전 채굴(매도 26규칙 + 셋업 30측정치), ④ sonnet 18-에이전트 커버리지 맵(원전 708 지식 단위 매칭), ⑤ sonnet 4프레임 정적 감사.

**감사 판정(5소스 수렴): 부분 재작성.** 인프라 계층 — 프로바이더·point-in-time 규율·envelope 계약·Trend Template 게이트·완결 스탑 경로 감사·캐시(208 테스트 통과) — 은 우수하므로 보존한다. **판단 평면** — 셋업 정량화, 매도/포지션 관리, 시장 리더십 행동, 펀더멘털 깊이, 최종 조합 무결성 — 이 빈약하다: 원전 지식의 55%가 부재(고영향 167건), 기존 행동 검증 30리포트는 거부 규율만 증명했고 판단 품질 시나리오는 0건이었다. 성진의 의심이 정확했다.

감사 원자료(재확인용): sonnet 커버리지 맵 `<세션 스크래치패드>`, codex 채굴 전문 `<클로드 프로젝트 tool-results>`, codex 감사 `.codex-runs/20260824-204125-harness-audit-c39f/`. 유실 시 원 소스(`.tmp/*.db`)에서 재채굴 가능.

## 확정된 사용자 결정 (스코프)

1. **'능가' = 확장형**: Minervini 하드 게이트 불가침, 암묵지 정량화, TL·현대 증거 계층 추가.
2. **부분 청산 허용**: 포지션 내 비율 관리(절반/3분의 1 매도)는 매도 규율로 허용. 계좌 대비 종목 비중·자금 배분만 계속 금지. CLAUDE.md 스코프 문구를 이 구분으로 수정.
3. **완결 봉 유지**: 인트라데이 전술은 계속 범위 밖. "돌파일 볼륨 확인은 완결 봉 사후"라는 한계를 응답에 명시.
4. **어닝스 날짜 프로바이더 추가**: 셀업 어닝 근접 게이트·보유 리스크 판단을 결정론화.
5. **사이징 의존 규칙은 정성 가이드로만**: progressive exposure 등은 숫자 없는 활동량/공격성 언어로 반영.
6. **응답 언어**: 질문 언어 추종 + 판정 상태어(BUY-READY/WAIT/AVOID/INCOMPLETE/HOLD/SELL)는 영어. Response standard에 "계약 어휘를 평이한 결정 언어로 번역" 규칙 추가.
7. **trade traction 유지**: 미제공 시 사용자에게 평문으로 질문하는 UX 지침 추가.

## 실행 중 확정된 추가 결정 (2026-08-24~25 세션)

계획을 지도로 쓰라는 지시에 따라, 구현 중 드러난 사실로 계획 세부가 바뀐 지점을 여기 기록한다. 아래 결정들은 `harness-spec.md` Change history에도 반영돼 있다.

8. **임계값 단일 소유 메커니즘 = 레지스트리 조회.** 리듀서는 `doctrine.threshold()` / `evaluate_gate()` / `evaluate_band()`로 읽는다. 파리티 테스트가 아니라 조회를 택한 이유는, 리터럴이 값과 같은지 비교하는 테스트는 "오늘 일치한다"만 증명하기 때문이다. 검증 방식은 레지스트리 값을 옮기고 판정이 따라오는지 보는 것(`tests/260824/doctrine/test_reducer_threshold_parity.py`).

9. **임계값에 `role` 도입 — 이번 세션의 가장 큰 스코프 변경.** 성진의 문제 제기("34.9%면 의미가 없어지나? 임계로 signal을 만들되 구체값을 줘서 경직되게 판단하지 않게")에서 출발했고, 채굴 결과가 이를 뒷받침했다 — 원전은 대부분 "generally", "most commonly", "in most cases"로 헤지된 서술이고 이를 pass/fail로 컴파일하면 저자가 긋지 않은 경계가 생긴다. 실제로 기존 레지스트리는 원전이 범위로 준 것의 느슨한 끝만 취하고 있었다(3~5주 깊이 "25 to 35" → 35 단일값, Power Play 플래그 하락 "20 to 25" → 25 단일값).
   - `gate` — 원전이 필터 언어로 진술한 한계("If a stock doesn't meet the Trend Template criteria, I don't consider it"). pass/fail을 결정하고 근접성 논변을 허용하지 않는다. 리스크 스파인도 여기 — 승자에 대한 서술이 아니라 트레이더 행동에 대한 제약이므로.
   - `band` — 원전이 범위로 준 것. 측정치·범위·범위 내 위치(`band_position`)·어느 쪽 끝이 좋은지(`direction`)를 보고하고, 수렴에 기여하되 **단독으로 판정을 내지 못한다.**
   - `reference` — 모집단 통계. 종목에 평가되지 않는다.
   - 게이트는 16개이고 전부 코어 12 claims 안에 있다. 채굴된 claim은 단 하나도 게이트로 승격되지 않았다.
   - **Phase 2·6에 번짐**: VCP 정량 엔진의 측정치는 이 스키마 위에 올라간다(Phase 2가 그만큼 줄어든다). 응답 표준에 "모든 band 측정치는 값과 원전 범위를 함께 명시" 규칙 추가(Phase 6 프로즈 작업의 일부를 선반영).

10. **band 공시는 조건 없이 항상.** "느슨한 가장자리에 가까울 때만 명시"는 "가깝다"의 컷오프를 발명해야 하므로 채택하지 않았다. 모든 band 측정치를 값·범위와 함께 보고하면 26%와 34.9%의 차이가 독자에게 그대로 전달되고 발명되는 숫자가 없다.

11. **실무자 불일치는 병합하지 않는다.** `Minervini.db` row 15는 이전 채굴이 한 번도 열지 않은 65,000자 다중 실무자 Q&A였고, 네 실무자(Minervini/Ryan/Zanger/Ritchie II)가 기록상 서로 불일치한다(돌파 볼륨만 4가지 기준, ROE는 둘이 아예 안 본다고 명시). 각각 별도 claim에 `attributed_to`로 남기고 `disagrees_with`로 교차 참조한다. **Minervini 기준이 하네스 기본값**이고 나머지는 대조 자료 — 측정치가 두 기준 사이에 떨어질 때만 인용한다. Minervini 외 귀속 claim은 게이트를 들 수 없다(검증기가 강제).

12. **포지션 사이징 독트린은 기록하되 배선 금지.** row 15에 실제 노출 수치가 나온다(Ryan 5%/10%, Zanger FTD 전 50% 상한·시장 신호 시 60~80% 축소). `out_of_scope: "position_sizing"` + `consumers: ["doctrine audit"]`로 등재하고, `validate()`가 이런 레코드를 capability에 배선하는 레지스트리를 **거부**하며 `threshold()`가 값 반환 자체를 거부한다. 금지가 기억이 아니라 구조가 된다. 결정 5(정성 가이드로만)의 구현 형태.

13. **`quarantine.ch12_failure_cascade` 삭제.** 재채굴 결과 두 코퍼스 어디에도 근거 구절이 없었다 — 약한 증거가 아니라 무증거. 격리는 실행하기엔 약한 증거를 담는 자리이지 증거가 없는 것을 담는 자리가 아니다.

14. **`layer`에 `harness` 추가.** `scope.data_integrity`와 `tactic.early_entry_confirmation_debt`는 책 근거가 없고 없는 게 맞다 — 하네스 자신의 운영 규칙이다. 인용 요구에서 면제하되 provenance에 그 사실을 명시하고, 하드 게이트는 될 수 없다.

15. **`scripts/verify_doctrine_quotations.py` 신설.** `validate()`는 인용이 형식을 갖췄는지만 볼 수 있고 그 글자가 저자의 것인지는 못 본다. 이 도구가 그걸 본다. 빌드 타임 전용(`.tmp/*.db`가 있을 때만 동작, 없으면 스킵). 157건 중 10건이 주장과 달랐다. PDF 추출의 하이픈 분절·러닝헤드·folio·figure 블록은 무시하되 **비인접은 무시하지 않는다**. 인용은 연속된 원문이거나, 무엇을 건넜는지 `assembled_from`으로 선언하거나 둘 중 하나다. 선언은 비인접만 설명하며 소스에 없는 조각을 면제하지 못한다(적대 리뷰가 이 우회를 실제로 통과시켜 보여준 뒤 수정).
   - 보고 수치는 **verified와 declared를 분리**한다. 현재 190 verified + 6 declared.

16. **Trend Template 순서를 원전 번호대로 재정렬.** `eligibility.py`가 "in source-map order"라고 주장하면서 실제로는 다른 순서로 저장하고 있었다(원전 5번 `price_above_50sma`가 8번 자리에).

## 실행 단계

각 단계 공통 게이트: `tdd` 스킬 선행(공개 시임 합의 → RED → GREEN, 테스트는 `./tests` 아래 레포 관례대로 — 기존 `tests/260817`은 보존하고 이번 재작성 스위트는 새 날짜 디렉터리 `tests/2608xx/`에 작성) → codex(sol, xhigh) diff 리뷰 → `validate_harness.py` 0 에러 → `harness-spec.md` Change history 동기 갱신 → 브랜치/PR(한국어 커밋 규칙, 스쿼시 머지). 큰 단계는 구현 전 codex 설계 리뷰 추가.

### Phase 0 — 즉효 결함 수정 (외과적, 소규모)

검증된 버그 4건. 파일: `scripts/minervini/risk.py`, `technical.py`, `eligibility.py`, `operations.py`.

- **P0-1** `risk.py`: 액티브 무효화 가격을 현재가·완결 저가 경로와 실제 비교(현재 상태 플래그만 봄 — 현재가 90/무효화가 95에서 HOLD 반환하는 버그).
- **P0-2** `risk.py` + `capabilities.py`: `average_gain_pct` 미제공 시 half-average-gain 게이트가 조용히 생략된 채 BUY-READY 불가 — 필수화하거나 명시적 `missing`으로 강등. 공식 예제 수정.
- **P0-3** `technical.py`/`eligibility.py`: Primary Base ①~1년 베이스 50% 깊이 밴드(독트린 명시) 구현, ②ATH 미돌파를 hard fail(AVOID)이 아닌 WAIT/incomplete로.
- **P0-4** `operations.py`: `from .chart import`를 차트 연산 내부로 지연 임포트 — `--help`/`capabilities`가 matplotlib 없이 완전 오프라인 동작.

완료 판정: 각 버그의 재현 테스트가 RED→GREEN, 전체 스위트 통과, read-only 환경에서 `capabilities` 성공.

### Phase 1 — 독트린 레지스트리 대확장

파일: `doctrine/claims.json`, `scripts/minervini/doctrine.py`, `tests/260817/doctrine/`.

- 12 → 약 60~80 claims로 확장. 소스: codex 채굴 56건(매도/관리 26 + 셋업/VCP 30) + sonnet 커버리지 맵 고영향 부재 항목(펀더멘털 임계값, 시장 사이클, 리더십, Stage 1/3/4 특징, 베이스 카운팅, 추격 한계, 실무자별 볼륨 프로파일).
- **출처 규율**: 모든 claim에 book row id + 원문 인용(현재의 제네릭 `canonical_method/...` 라벨 대체). 책이 임계값을 안 주면 발명 금지 — 측정치 반환 + 판단 필드로 인코딩.
- **임계값 단일 소유**: 수치는 레지스트리가 소유하고 리듀서는 `doctrine.py` 조회 또는 파리티 테스트로 강제(메커니즘은 tdd 시임 합의에서 확정). RS≥70처럼 코드에만 있는 값을 레지스트리로 흡수.
- TL 항목은 `[TL]` 태그 유지, 기존 ch12 격리 항목은 채굴에서 확보한 실제 인용으로 재구성 가능한 것만 승격.

완료 판정: 레지스트리 스키마 검증 통과, 전 claim 인용 존재, 리듀서 소비 파리티 테스트 통과.

### Phase 2 — 셋업/VCP 정량 엔진 재작성

파일: `scripts/minervini/setup_evidence.py`, `setup.py`, `capabilities.py`, `cli.py`(ticker.setup 계약).

- **결정론 측정 엔진**: VCP 수축 시퀀스(스윙 분할 후 깊이·연속비·개수 2-6), 타이트니스(range%, 종가변화율, ADR 대비), 볼륨 상태(20/50일 SMA 대비 ±25% — 현행 5:6세션 비율 대체), 최종 수축 볼륨 드라이업, DCR 공식, 구조적 피벗(현행 20세션 최고가는 후보 생성기로 강등), 돌파 볼륨 실무자 프로파일(Minervini/Ryan/Zanger 태그 분리), 추격 한계(TL +1.5% 존/Minervini "a few %"), 치트 존·회복분율(1/3-1/2, 5-10% pause), 플랫베이스(4-7주 10-15%), 쇼크아웃/서포트 리클레임/oops 리버설, 스쿼트/리커버리 윈도, 시간 압축, 베이스 카운트(4+ = late_stage_risk), 어닝 근접 게이트(Phase 4 프로바이더 의존 — 인터페이스만 선반영).
- **Power Play 평가기 신설**(C6): 100%+/8주 추력, 플래그 3-6주·≤25% 깊이, ≤10% 타이트 or VCP — 실측 후 불변 결과를 fundamentals에 전달. 실측 없는 자기주장 발동 차단.
- **차트 판단 스키마**(C3): `--price-geometry pass` 같은 불리언을 감사가능한 구조화 판단(베이스 경계, 수축 목록, 오버헤드 서플라이, 판정 근거)으로 대체. 결정론 측정치가 판단을 구속·검증(측정과 모순되는 pass 거부).
- **TL 조기 전술 분화**(C8): 제네릭 tl_early를 명명된 전술(upside reversal, range breakout, inside day, consolidation pivot, key-level reclaim, oops)로 분리 — 전술별 전제조건·무효화·확인 부채, 전부 옵트인 유지, doctrine_ids 배선.

완료 판정: 표류 바 21개 + pass 플래그 → READY가 되는 기존 결함의 재현 테스트가 신 엔진에서 거부됨. 원전 인용 기반 골든 케이스(교과서 VCP vs 유사 불량 패턴) 분별 테스트 통과.

### Phase 3 — 매도/포지션 관리 재작성

파일: `scripts/minervini/risk.py`(+ 신규 관리 리듀서), `capabilities.py`, `cli.py`(ticker.risk 계약).

- **어휘 확장**: HOLD/SELL/INCOMPLETE 유지 + `management_actions: REDUCE | RAISE_STOP | REVIEW`(강제 전량 청산만 SELL). 부분 청산 비율(절반, 1/3) 허용 — 사용자 결정 2 반영.
- 채굴 26규칙 구현: 하드스탑(갭스루 기록), 3R 브레이크이븐 RAISE_STOP, TL +5% 절반매도·브레이크이븐(`[TL]` 단계별 기본값), TL 2-MA-closes(21EMA 스윙/50SMA 포지션 — 신호 품질 증거 필드 포함), Stage 2 최대 낙폭 신호, Stage 3 전환 특징 벡터, 클라이맥스/소진 갭 리뷰, 베이스 카운트 컨텍스트, 돌파 후 악화(20일선, 테니스볼 테스트, 저볼륨 돌파+고볼륨 매도), D+2 시간 증거 메트릭, 어닝 전 리뷰, 시장 방어 컨텍스트(스탑 상향 유도, 티커 SELL은 불가).
- 죽은 독트린 `management.ema21_sma50_roles`를 실소비자에 배선.

완료 판정: "스탑 미접촉 + 구조 악화" 케이스가 HOLD가 아닌 REVIEW/REDUCE 증거를 반환하는 골든 케이스 통과. 기존 완결 스탑 경로 테스트 무회귀.

### Phase 4 — 펀더멘털 재설계 + 어닝스 캘린더 프로바이더

파일: `scripts/minervini/fundamentals.py`, `providers/sec.py`, 신규 `providers/` 어닝스 캘린더(후보: 기존 FMP enrichment 확장 — 구현 시 확정), `capabilities.py`.

- **라이브 경로 수리**(C2): 평가기를 SEC가 실제로 내보내는 사실 중심으로 재설계. 프로바이더가 못 주는 integrity 필드는 계산 가능한 대체(재무 수치 기반)로 바꾸거나 명시적 미구현 처리 — 상시 INCOMPLETE 구조 제거. `leader_category`의 filing 유래 시임 제거(분류는 사용자/분석 입력으로).
- **가속 보상**: Code 33(EPS·매출·마진 트리플 가속), 최소 성장률(20-25% YoY, 슈퍼퍼포먼스 구간 30-40%+), 어닝 서프라이즈·추정치 상향(±5%), 재고·매출채권 vs 매출 괴리, 일회성 항목 인지, ROE 동종업계 상대 비교(~15-17%), P/E 확장 배수 추적(2-3x = 후기 신호), 카테고리별 해석(턴어라운드 2분기 강세 요건, 시클리컬 역P/E 사이클), 20-F 연간 주기 인지.
- **어닝스 캘린더**: 프로바이더 규율(타입드 불가용성, 메타데이터, 캐싱, PIT) 준수. `ticker.setup` 어닝 근접 게이트·`ticker.risk` 보유 리스크가 소비.

완료 판정: 실 SEC 픽스처로 fundamentals_state가 incomplete 고착 없이 산출. 어닝 근접 셀업 패스 골든 케이스 통과.

### Phase 5 — 시장/리더십 행동 증거

파일: `scripts/minervini/market_evidence.py`, `market.py`, `operations.py`.

- **도달 가능한 레짐 판정**(C4): 리더 행동을 완결 봉에서 계산(지수 저점 대비 리더 고점 유지·신고가 참여·돌파 추종률) — 상시 `observed` 고착 제거.
- 그룹 벡터 실계산: Stage 2 카운트, 신고가 근접, 돌파/실패 비율. 스크린 결과 수 게이지, 신강세장 첫 4-8주 리더 식별, RS라인 선행 신호, 사이클 단계 컨텍스트(`[TL]` FTD·스트레스 테스트는 실무 계층 태그).
- `market.candidates`의 상시 `not_recommended` 필드 정리(구현 or 인터페이스 정직화).

완료 판정: 실 프로바이더 모양 데이터로 favorable/defensive가 실제 도달 가능함을 통합 테스트로 증명.

### Phase 6 — 조합 무결성 + 인터페이스/프로즈 계층

파일: `scripts/minervini/operations.py`, `cli.py`, `capabilities.py`, `CLAUDE.md`, `.claude/skills/*/SKILL.md`.

- **조합 출처 연계**(C5): `ticker.risk` 최종 판정이 컴포넌트 envelope 참조(티커·세션·해시) 검증 — 무출처 수동 enum 조합으로 BUY-READY 불가.
- CIK 조회 capability(SEC company_tickers.json), 프로즈-인터페이스 중복 제거(envelope 계약 4문장 등), 스킬-CLAUDE.md 중복 제거(Power Play·시장 방어·사이징 금지 반복), 스킬 frontmatter 스코프 문구 동기화.
- CLAUDE.md 갱신: 부분 청산 허용 스코프 문구(결정 2), 응답 언어 규칙(결정 6), 계약 어휘 번역 규칙, 어닝 리스크 문장, 베이스 카운트 문장, trade traction 질문 UX(결정 7), "time as evidence"에 D+2 측정 앵커 연결, 6분류 카테고리별 해석 차이 명시. 111줄 예산 준수 — 늘어난 만큼 중복 제거로 상쇄.

완료 판정: `validate_harness.py` 0 에러, 도움말/스키마 파리티 테스트 통과, 스킬 description 재검토.

### Phase 7 — 판단 품질 행동 검증 재구축

파일: `tests/260817/e2e/scenarios.json`(신규 시나리오), `.claude/harness-spec.md`.

- **골든 케이스 신설**(C10 공백): 유효 BUY-READY 전체 경로, 교과서 VCP vs 유사 불량 VCP 분별, 비스탑 SELL(구조 악화), 후기 베이스 경고, 리더 vs 고RS 랙가드, Power Play 실측 검증, 부분 청산 가이드, 어닝 근접 거부, 정량 측정과 모순되는 차트 판단 거부.
- **충분한 E2E를 양 호스트에서**: 클로드 측 행동 프로브는 sonnet 서브에이전트가 실세션으로 수행하고, codex(sol, xhigh)가 독립 행동 채점을 재연 — 크리티컬 어서션 3회 독립 통과, 적대적 최종 종합(가짜 BUY-READY·데이터 조작·게이트 우회 탐지). 라이브 스모크(읽기 전용).
- **크로스 호스트 하네스 사용성**: codex가 공유 하네스(`AGENTS.md → CLAUDE.md`, `.codex/skills → ../.claude/skills`)로 동일 분석을 수행할 수 있는지 E2E 확인. 사전 검증은 계획 세션에서 1회 수행함(아래 '코덱스 호스트 검증' 참조) — Phase 7에서 재작성된 하네스로 재확인.
- `harness-spec.md` 전면 갱신(새 topology·정보 소유권·검증 전략), 감사·재작성 이력 기록.

완료 판정: 신구 전체 스위트 + 행동 게이트 통과, 스펙-실체 드리프트 0.

## 코덱스 호스트 검증 (계획 세션에서 수행, 2026-08-24)

codex 실증 프로브(run `20260824-211802-harness-usability-probe`, gpt-5.6-sol, workspace-write, 파일 변경 0) 결과 **통과**:

- `AGENTS.md → CLAUDE.md` 주입 확인 — 역할·스코프·독트린 우선순위를 원문 인용으로 증빙.
- `market-scan`·`ticker-analysis`가 코덱스 런타임 스킬 카탈로그에 실제 등록됨(`.codex/skills → ../.claude/skills` 심링크 경유, 소스 경로는 `.claude/skills`로 표기).
- `pipeline capabilities`(status ok, as_of 2026-08-21)와 `describe ticker.qualify` 계약 판독 정상, 라우팅 판단("NVDA 매수 분석 → ticker-analysis, 오리엔테이션 3단계") 정확.
- 문서화된 호스트 차이: 코덱스에는 Claude식 `Skill` 호출 치환·`allowed-tools` 사전승인·Task 도구가 없어 스킬 본문을 직접 읽음(현 스킬은 이 방식과 호환). matplotlib 캐시 경고 재현 — P0-4(지연 임포트) 근거 재확인.
- 시사점: 하네스 수정 시 두 호스트 호환을 유지하려면 스킬 본문이 Claude 전용 치환(`${CLAUDE_SKILL_DIR}` 등)에 의존하지 않게 유지한다(현재 스킬은 `allowed-tools` frontmatter 외 치환 없음 — 유지). 스펙의 `.agents/skills` 표기는 실제 `.codex/skills`로 정정 필요(Phase 6).

## 실행 독트린 (사용자 명시 지시)

**계획은 지도이지 레일이 아니다.** 구현 중 드러난 사실이 계획 세부와 충돌하면 세부가 아니라 목적(100점 하네스)과 불변 원칙(하드 게이트 불가침, 증거 규율, 인용 없는 임계값 발명 금지)이 우선한다. 수정은 이 파일과 `harness-spec.md`에 기록하고, 방향이 갈리는 수정(스코프·게이트 해석)은 성진에게 AskUserQuestion으로 확인한다.

**멀티에이전트 기본값.** sonnet 팬아웃 — 구현 대 원전 인용 대조, 경계값 교차 검토, 병렬 탐색. codex(gpt-5.6-sol, xhigh, 사용량 무제약) — 단계별 독립 적대 검증(설계 리뷰 → diff 리뷰 → 행동 채점), 공동 저자가 아닌 검증자. 최종 종합·판정은 메인(Fable). 코드 변경은 `tdd` 스킬 RED→GREEN 계약.

## 검증 (전체)

- 단계별: 재현/골든 테스트 RED→GREEN, 전체 `tests/260817` 스위트, 도움말/스키마 파리티, `validate_harness.py`, codex diff 리뷰.
- 최종: Phase 7 행동 게이트(판단 품질 시나리오 포함) + 라이브 스모크 + harness-spec 드리프트 0.
- 실사용 검증: 완료 후 성진의 실제 질문("유망 섹터/티커", "XXX 매수 조건")으로 시범 세션을 돌려 판단 품질을 최종 확인.


## 진행 상태 (2026-08-25 컴팩트 시점)

- **Phase 0 — 완료·머지됨** (PR #3, `b3aca97`). 계획의 버그 4건으로 시작해 codex 적대 리뷰 7라운드(6→4→3→3→2→1건 발견 후 ACCEPT)에서 12건이 추가로 나왔고 전부 수정. 마지막 세 커밋은 증상이 아니라 뿌리를 제거했다 — 같은 판단을 두 곳에서 각자의 말로 내리던 사본 3쌍(`settled_breach`, `declares_exit_plan`, `_status_word`)을 리듀서 단독 소유로 통합.
- **Phase 1 — 브랜치 `feat/doctrine-registry-expansion`에 커밋됨, 적대 리뷰 2라운드 진행 중.** 레지스트리 12 → 124 claims. 1라운드 REJECT(8건, P1 5건) 전부 수정 후 `e63a942`. 2라운드 codex run id: `20260825-000308-p1-doctrine-review-51ac` (`codex_bridge.py result --run <id>`로 회수).
  - 현재: 348 tests OK, `validate()` valid/124, 검증기 190 verified + 6 declared, `validate_harness.py` PASS.
  - PR 전 남은 것: 2라운드 판정 처리 → PR → 머지.
  - CLAUDE.md 114줄(계획 예산 111줄 대비 +3). band 공시·role 규칙 때문이며 Phase 6의 중복 제거로 상쇄 예정.
- **Phase 2~7 — 미착수.**

### 채굴 원자료 (스크래치패드, 세션 종료 시 소실 가능)

`<세션 스크래치패드>`에 `mined_eligibility.json`(31) · `mined_market.json`(25) · `mined_fundamentals.json`(32) · `mined_existing.json`(12) · `mined_practitioners.json`(34) · `codex_mining.txt`(매도 26 + 셋업 30) · `coverage_map.json`. 전부 `doctrine/claims.json`에 흡수됐으므로 소실돼도 치명적이지 않지만, Phase 2·3·4가 원 채굴 노트(특히 `codex_mining.txt`의 VCP 30측정치와 `mined_practitioners.json`의 실무자별 볼륨 프로파일)를 다시 참조할 수 있다.

### 에이전트 보고를 믿지 말 것 (이번 세션에서 4번 확인)

계획의 "다른 에이전트 결과를 액면 그대로 받지 말라"는 지시가 실제로 값을 했다.

- `mined_existing.json`이 "falling 200-day 조항은 하네스 발명"이라 보고 → row 11에 거의 그대로 있음. 같은 문장이 "펀더멘털이 기술적 실패를 못 덮는다"는 precedence 근거이기도 하다.
- 같은 파일이 "책에 ROE 수치 없음" 보고 → row 15에 있음. 이걸 확인하다가 **아무도 안 연 코퍼스(row 15)를 발견**했고, 거기서 실무자 불일치 34건이 나왔다.
- 같은 파일이 "두 달 최소 이력은 발명" 보고 → 개념은 row 4에 있고 40세션 환산만 하네스 몫이었다.
- 조립 에이전트가 "검증 3종 전부 그린" 보고 → 내가 나중에 추가한 4번째 검증(인용 검증기)은 안 돌린 상태였다. **자기가 돌린 검사에서 그린인 것은 그린이 아니다.**

반대로 에이전트가 나를 두 번 교정했다(rs69는 재배열이 아니라 누락, 곱셈기호는 추출 아티팩트가 아니라 오기). 양방향으로 대조하는 것 외에 방법이 없다.
