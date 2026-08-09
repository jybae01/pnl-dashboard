# Golden Model 구조·계산 E2E 검증 보고서

검증일: 2026-08-09

검증 브랜치: `agent/phase2-worker-viewer`
판정: **CHECK — 실제 Supabase 프로젝트 연결 전 정책/매핑 확정 필요**

숫자를 맞추기 위한 Plugging은 사용하지 않았다. 기존 결정론적 공식과 Residual 부호도 변경하지 않았다.

## 1. 사용 workbook 및 식별정보

| 구분 | 파일 | SHA-256 | 용도 |
|---|---|---|---|
| Base | `★손익추정 시뮬레이션_rev1_1~6월 실적 입력_v1.3.xlsx` | `ff082c07350ef81a942e6ed8258fcd4ad5a5b17e486325d13e9fefa7e5df4a7b` | 회사 Golden Model과 동일한 행·열 구조의 검증 원본 |
| Comparison | 검증 중 `ForecastEngine`으로 생성한 비커밋 산출물 | `98776b930b1c476888a6a607b34dc49675aaf05a973fa05a658d0555a9bf5f46` | 2026년 7월 판매·생산·MCM·제조경비·판관비·JPY 변동 시나리오 |

원본은 `Data` 단일 시트, 1,810행×34열이다. E:J는 1~6월 실적, K:P는 7~12월 계획이다. 숨김 행/열은 없고 병합셀은 `B2:D3`, `B1245:D1246`, Defined Name은 14개다. 원본 파일은 읽기 전용으로 사용했고 저장소에 포함하지 않았다.

원본 1~6월 독립 합계도 확인했다. 매출 111,420,782,225.661원, 매출원가 72,422,146,443.589원, 매출총이익 38,998,635,782.072원, 판매비 15,892,425,793.707원, 일반관리비 11,653,534,987.609원, 영업이익 11,452,675,000.756원이다. `매출-매출원가=매출총이익` 차이는 0원, `매출총이익-판매비-일반관리비=영업이익` 차이는 0.0000019원이다.

## 2. 전체 구조검증 결과

Base와 Comparison 모두 Pre-flight를 통과했다. 분석 대상은 대소문자를 무시해 정확히 `Data`인 시트로 제한하며, 분석 무관 STP 시트나 Defined Name은 무시한다.

| 검증항목 | 원천셀/행 | 결과 | 비고 |
|---|---:|---|---|
| 1~12월 헤더/기간유형 | `E2:P3` | PASS | 1~12월 연속, 실적/추정/계획만 허용 |
| JPY 환율 | 9 | PASS | 숫자/수식 형식 확인 |
| 전공정 부직포 | 205~207 | PASS | 숫자/수식 형식 확인 |
| 부직포 제외 전공정 | 208~210 | PASS | 숫자/수식 형식 확인 |
| 전공정 원재료 합계 | 211 | PASS | 실제 라벨 `생산출고 계` 허용, 위치 고정 |
| 제조경비 | 287/289~319/321 | PASS | 시작·종료 Anchor 및 전체 mapped account 확인 |
| 전공정 배부율 | 345~347 | PASS | 숫자/수식 형식 확인 |
| FS 생산 | 119/122/125 | PASS | 길이(m) source 확인 |
| SW/BW/LC 생산 | 556~560 | PASS | PCS source 및 LC 포함 확인 |
| MCM | 568~571 | PASS | 빈 값 허용, 문자열 불허 |
| 후공정 원재료 | 684~699 | PASS | 합계 699행 위치 고정 |
| 판관비/P&L | 1166/1244/1248~1306 | PASS | 블록 및 주요 P&L source 확인 |
| 병합/숨김/수식/Defined Name | workbook 구조 | PASS | 핵심 source 구조를 바꾸지 않으면 허용 |

## 3. P&L 결과

허용오차는 금액 기준 `max(1원, |독립값|×1e-9)`이다.

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| 매출 delta | `Data!K1248` | 840,203,867.133 | 840,203,867.133 | 0 | 1원 이상 상대허용 | PASS | Comparison-Base |
| 매출원가 delta | `Data!K1268` | -78,588,912.823 | -78,588,912.823 | 0 | 동일 | PASS | Comparison-Base |
| 매출총이익 delta | `Data!K1298` | 918,792,779.955 | 918,792,779.955 | 0 | 동일 | PASS | P&L identity도 일치 |
| 판매비 delta | `Data!K1302` | 53,000,000.000 | 53,000,000.000 | 0 | 동일 | PASS | 관세 13m 포함 |
| 일반관리비 delta | `Data!K1303` | 20,000,000.000 | 20,000,000.000 | 0 | 동일 | PASS |  |
| 영업이익 delta | `Data!K1306` | 845,792,779.955 | 845,792,779.955 | 0 | 동일 | PASS | Comparison-Base |

Base/Comparison 각 금액과 delta 총 18개 P&L 검사는 모두 PASS다.

## 4. 판매효과 결과

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| 판매수량 | 제품군 수량/GP + 운반비 | 242,748,501.794 | 242,748,501.794 | 0 | 1원 | PASS |  |
| 제품 Mix | SW/BW/LC/FS/신사업 | -55,990,588.518 | -55,990,588.518 | 0 | 1원 | PASS | PCS/LENGTH 별 가중계산 |
| 판매단가 | 제품군 매출/수량 + 운반비 단가 | -848,219,432.920 | -848,219,432.920 | 0 | 1원 | PASS | 관세 제외 |
| 매출환율 | USD 대칭분해 | 859,494,650.281 | 859,494,650.281 | 0 | 1원 | PASS |  |
| 판매효과 합계 | 상기 합계(관세 제외) | 198,033,130.637 | 198,033,130.637 | 0 | 1원 | PASS | 수량+Mix+단가+FX |
| 기준 GP율 가중평균 | 제품군 amount/cogs | 31.6718458484% | 31.6718458484% | 0 | 1e-12 | PASS |  |

추가 격리검증에서 SW400만 변경하면 원천 OP 효과와 현재 SW 그룹 집계 효과 사이 2,248,583.069원 Residual이 생겼다. 현재 어댑터가 SW400/SW440을 `SW_CORE`로 묶기 때문이다. SKU 내부 Mix를 별도 효과로 볼지는 업무정책 확인이 필요하며, 임의 COGS 배부는 하지 않았다.

## 5. 원부재료 결과

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| SW | mapped rows | -10,236,071.122 | -10,236,071.122 | 0 | 1원 | PASS |  |
| BW | mapped rows | -12,700,898.293 | -12,700,898.293 | 0 | 1원 | PASS |  |
| LC | mapped rows | -251,997.429 | -251,997.429 | 0 | 1원 | PASS |  |
| FS | mapped rows | -2,712,669.892 | -2,712,669.892 | 0 | 1원 | PASS |  |
| 부직포 단가(환율 제외) | 205~207, mapped input | 18,332,329.184 | 18,332,329.184 | 0 | 1원 | PASS |  |
| 부직포 엔화 | `K9`, 205~207 | -44,581,148.058 | -44,581,148.058 | 0 | 1원 | PASS | KRW/JPY 직접 적용, `/100` 없음 |
| 부직포 제외 원재료 | 208~211, 684~699 | 347,182.140 | 347,182.140 | 0 | 1원 | PASS |  |
| 원부재료 총효과 | 세 효과 합계 | -25,901,636.735 | -25,901,636.735 | 0.000000004 | 1원 | PASS |  |

수율/사용량 효과는 생성되지 않았고 MCM도 독립 Bridge 효과로 생성되지 않았다.

`raw_material_basis=direct` 경로는 별도 CHECK다. 이 workbook에서 211/699행 변경은 K321까지만 전파되고 P&L 계보로 이어지지 않아, source를 +30m 바꿔도 OP는 0인데 material bridge는 -34.645m이 된다. 정확한 P&L driver mapping을 승인하기 전에는 이 입력 모드의 실배포를 차단해야 하며, 211/699를 임의로 P&L에 연결하지 않았다.

## 6. 제조경비 결과

27개 계정의 Base/Comparison, 분류, 기준모형 345~347행 배부율, 조업도/원단위/고정비/실현 전/최종효과 총 192개 검사가 모두 PASS다. 비교모형에도 기준모형 배부율을 동일 적용했다.

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| 전공정 조업도 | 119+122+125 | 원천합계 | Engine 합계 | 0 | 1원 | PASS | FS 생산입고 길이(m) |
| 후공정 조업도 | 556~560 | 원천합계 | Engine 합계 | 0 | 1원 | PASS | SW+BW+LC PCS, LC 포함 |
| 실현 전 효과 | 289~319 | -70,000,000.000 | -70,000,000.000 | 0.00000003 | 1원 | PASS | 조업도+원단위+고정비 |
| 재고실현율 | COGS/current mfg input | 102.8390196602% | 102.8390196602% | 0 | 1e-9 | PASS | 100% 상한 미적용 |
| 최종 손익효과 | 실현 전×실현율 | -71,987,313.762 | -71,987,313.762 | 0.00000004 | 1원 | PASS |  |

다만 제조 급료만 +50m인 격리 시나리오에서 workbook OP 반영은 -11.443m, 현 정책 효과는 -53.154m로 41.711m Residual이 생겼다. 102~106% 실현율은 현재 승인 공식에는 맞지만 실제 Golden P&L의 한계 반영률과 다르다. 공식 실현율 source/정의 승인 전 계산 공식을 바꾸지 않았다.

## 7. MCM 검증 결과

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| 외주가공비 후공정 분모 | 556~560 minus 568~571 | 41,038.833458 | 41,038.833458 | 0 | 1e-9 | PASS | MCM 제외 |
| 독립 MCM Bridge | effects code | 없음 | 없음 | 0 | 정확일치 | PASS | 원부재료 pool 내 회계분류만 유지 |

격리 시나리오에서도 일반 생산 +500, MCM +100이면 전체 후공정은 +500이지만 외주분모는 +400만 증가해 제외 규칙을 확인했다.

## 8. 판관비 결과

52개 실제 계정의 Base/Comparison 금액과 효과 총 159개 검사가 모두 PASS다.

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| 변동 판관비 | 전체 variable 계정 | -10,000,000 | -10,000,000 | 0 | 1원 | PASS |  |
| 고정 판관비 | 전체 fixed 계정 | -20,000,000 | -20,000,000 | 0 | 1원 | PASS |  |
| 고객배송 운반비 | 실제 계정/판매효과 | 계정 표시, SGA 효과 0 | 동일 | 0 | 정확일치 | PASS | 이중계산 없음 |
| 관세 | 외부 직접입력 | -13,000,000 | -13,000,000 | 0 | 1원 | PASS | 한 번만 반영 |

기타 판관비로 임의 합산하지 않았다.

## 9. 환율 총효과 결과

| 검증항목 | 원천셀/행 | 독립계산값 | Engine 값 | 차이 | 허용오차 | PASS/CHECK | 비고/원인 |
|---|---|---:|---:|---:|---:|---|---|
| `fx_total` | sales FX + nonwoven JPY | 814,913,502.222 | 814,913,502.222 | 0 | 1원 | PASS | 표시 재분류 |
| `raw_material_excl_fx` | material total - material FX | 18,679,511.324 | 18,679,511.324 | 0.000000004 | 1원 | PASS | 표시 재분류 |
| effects_total 불변 | deterministic effects 합 | 57,144,180.140 | 57,144,180.140 | 0 | 1원 | PASS | 재분류를 추가 효과로 더하지 않음 |

## 10. OP Bridge / Residual 결과

| 검증항목 | 독립계산값 | Engine 값 | 차이 | PASS/CHECK | 비고 |
|---|---:|---:|---:|---|---|
| effects_total | 57,144,180.140 | 57,144,180.140 | 0 | PASS | 모든 deterministic effect 합 |
| 현재 계약: effects + residual = OP delta | 845,792,779.955 | 845,792,779.955 | 0 | PASS | residual = OP delta - effects |
| 이번 요청: effects - residual = OP delta | -731,504,419.675 | 845,792,779.955 | 1,577,297,199.630 | CHECK | 기존 계약과 부호 충돌 |

Residual은 **788,648,599.815원**, OP delta 대비 절대비율 **93.2437%**다. 상업/P&L source gap 612,170,736.496원과 COGS source gap 176,477,863.320원의 합으로 정확히 재조정된다. 주요 원인은 (1) 그룹 집계 수준과 workbook SKU 한계효과 차이, (2) 원재료 direct source의 P&L 비연결, (3) 제조 재고실현율 정책과 실제 한계 반영률 차이, (4) 복합 입력 상호작용이다. 이는 정상적인 미세 residual이 아니라 실배포 전에 해결해야 할 매핑/정책 CHECK다. Residual을 기타 효과에 숨기거나 조정하지 않았다.

동일 workbook을 Base/Comparison으로 둔 대조군에서는 OP delta, effects_total, residual이 모두 0이고 `reconciled=True`였다.

## 11. Anchor Negative Test

| 케이스 | 기대 | 결과 | 사용자 메시지 |
|---|---|---|---|
| 핵심 Anchor label 변경 | FAIL | PASS(테스트가 실패를 검출) | 필수 Anchor를 찾을 수 없음 |
| 핵심 행 이동 | FAIL | PASS(검출) | 지정 행의 Anchor 누락/위치 오류 |
| 필수 행 삭제 | FAIL | PASS(검출) | 핵심 source 숫자/수식 누락 |
| 1~12월 header 훼손 | FAIL | PASS(검출) | 월 헤더가 1~12 연속이 아님 |
| 숫자 셀에 문자열 | FAIL | PASS(검출) | 숫자 또는 수식이어야 함 |
| Data 시트명 변경 | FAIL | PASS(검출) | 승인된 Data 시트를 찾을 수 없음 |
| STP/Defined Name 추가 | 통과 | PASS | 분석 무관 구조 허용 |
| 무관 병합셀/숨김행 | 통과 | PASS | 핵심 source 위치/값 유지 시 허용 |

자동화 결과는 8개 전부 PASS다. 모든 실제 source 구조 파괴는 `GenericComparisonEngine` 실행 전에 `PreflightValidationError`로 차단된다.

## 12. 발견한 실제 코드 결함 및 수정

신사업은 의도적으로 생산/원재료가 없는 sales-only 레코드인데, 기존 원부재료 검증이 매출이 있고 생산분모가 0이라는 이유로 오류를 만들었다. `ProductRecord.material_applicable_flag`를 추가하고 Golden adapter가 sales-only 레코드에 `False`를 명시하도록 수정했다. 원부재료 계산은 이 명시적 레코드만 제외한다. 실제 원재료비가 있는 SW 등의 생산분모 0 오류는 계속 CHECK로 남는 회귀 테스트를 추가했다.

`raw_material_basis=direct` P&L 비연결과 SKU 내부 Mix/제조 실현율 차이는 업무정책·Golden mapping 승인이 필요한 사항이라 공식을 변경하지 않았다.

## 13. 테스트 및 회귀검증

| 실행 묶음 | 정확한 결과 | 판정/설명 |
|---|---:|---|
| Golden 구조 Negative test | 8 passed | 핵심 훼손 6종 차단, 무관 장식 2종 허용 |
| Phase 1/2 | 41 passed | foundation, queue, migration, worker, viewer, preflight 포함 |
| 변경 관련 및 비-private 회귀 | 97 passed, 1 deselected | 알려진 `sales_fx` monkeypatch 1건만 명시적으로 제외 |
| 전체 pytest | 98 passed, 16 failed | 15건은 비공개 `models/golden_model.xlsx` 미존재, 1건은 기존 `sales_fx` monkeypatch signature 문제 |
| 실제 workbook E2E harness | 실행 성공 | P&L 18, 판매 6, 원부재료 10, 제조 192, 판관비 159, FX 3, MCM 1 PASS; 요청의 minus-residual identity 1 CHECK |
| `compileall` | PASS | `forecast`, `scripts`, `tests` |
| `git diff --check` | PASS | whitespace error 없음 |

전체 pytest의 16건은 이번 변경에서 새로 발생한 회귀가 아니다. 검증 원본은 저장소의 고정 `models/golden_model.xlsx`가 아니라 사용자 Downloads 경로에서 읽기 전용으로 사용했으므로, 기존 private fixture 의존 테스트에는 자동 주입하지 않았다.

## 14. 현재 검증이 보장하는 범위

- 이 검증 workbook의 행·열/Anchor/월 헤더가 현재 mapping과 일치한다.
- `GenericComparisonEngine`이 실제 Base/Comparison에서 `ComparisonResult`까지 생성한다.
- P&L, 판매, 원부재료, 제조경비, 판관비, FX 재분류, MCM 제외의 엔진값이 독립 원천셀 재계산과 일치한다.
- JPY는 KRW/JPY이며 `/100`이 없고, 재고실현율은 100%를 넘겨도 cap하지 않는다.
- FX 표시 재분류는 effects_total을 늘리지 않는다.
- Residual은 Plugging 없이 별도로 보존된다.

## 15. 실제 회사 Golden Model에서만 추가 확인할 항목

- 회사 파일의 실제 수식 계보와 이 검증 파일의 cached formula 결과가 완전히 같은지
- 판매 USD 환율의 공식 source cell/mapping
- `raw_material_basis=direct`의 진짜 P&L driver cell
- SKU 내부 Mix를 V1 Mix로 볼지 제품군 내부 residual로 둘지
- 제조경비 재고실현율의 공식 source/정의와 100% 초과 운영정책
- 실제 MCM 유상사급 원가 계정과 P&L 반영 계보
- Supabase Queue/Worker에서 signed upload 원본 checksum과 이 보고서 checksum이 같은지

## 16. 결론 및 다음 단계

구조 gate와 개별 계산식은 실증됐지만 OP Bridge Residual이 중요하고 부호 계약도 상충한다. 따라서 현재는 **실제 Supabase 프로젝트 연결 단계로 진행 가능**이라고 결론내리지 않는다.

다음 순서는 (1) residual 부호 계약을 `+` 또는 `-` 중 하나로 확정, (2) direct material P&L driver mapping 승인, (3) SKU Mix 범위와 제조 실현율 정책 확정, (4) 회사 Golden Model 읽기 전용 Live E2E, (5) 모두 PASS 후 Supabase staging 연결이다.
