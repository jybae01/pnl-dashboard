import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AnalysisPresentationPanel, formatQuantity } from './AnalysisPresentationPanel';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture, TEST_RESULT } from './presentationTestFixture';
import {
  CANONICAL_EFFECT_ORDER,
  calculateContributionRate,
  formatContributionRate,
  mapAnalysisPresentation,
} from './analysisPresentation';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('analysis presentation vertical slice', () => {
  it('renders canonical UI labels, residual, LC and separate activity units', () => {
    const value = presentationFixture();
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByText('영업이익 증감')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '펼치기' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('미설명 잔여차이')).not.toBeInTheDocument();
    for (const label of ['수량', '판가', '매출환율', '원재료', '변동비', '고정비', '재고 차이 등', '기타 요인']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.queryByTestId('effect-row-manufacturing_realized')).not.toBeInTheDocument();
    expect(screen.queryByText(/재고·원가 반영시차|재고 원가 반영 시차/)).not.toBeInTheDocument();
    expect(screen.queryByText('판매단가')).not.toBeInTheDocument();
    expect(screen.queryByText('제조경비 손익실현')).not.toBeInTheDocument();
    expect(screen.queryByText('UNEXPLAINED')).not.toBeInTheDocument();
    for (const category of ['내부', '외부', '비용']) {
      expect(screen.getAllByText(category).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('손익 영향 총액')).toBeInTheDocument();
    expect(screen.queryByText(/Effect 총액/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '손익 변동 요인 분석표' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '펼치기' }));
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.getAllByText('PCS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('m').length).toBeGreaterThan(0);
    expect(screen.queryByText(/MCM.*Effect/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(1);
    expect(screen.getAllByText(/백만원/).length).toBeGreaterThan(0);
  });

  it('maps canonical order and labels without deriving totals', () => {
    const value = presentationFixture();
    value.effects = [...value.effects].reverse();
    const mapping = mapAnalysisPresentation(value);
    expect(mapping.effects.map((effect) => effect.code)).toEqual([
      'sales_quantity', 'sales_price', 'sales_fx', 'material_total', 'sga_variable', 'sga_fixed', 'inventory_timing',
    ]);
    expect(mapping.effects.map((effect) => effect.uiLabel)).toEqual([
      '수량', '판가', '매출환율', '원재료', '변동비', '고정비', '재고 차이 등',
    ]);
    expect(mapping.effects.map((effect) => effect.uiCategoryLabel)).toEqual([
      '내부', '내부', '외부', '비용', '비용', '비용', '비용',
    ]);
    expect(mapping.residual.uiLabel).toBe('기타 요인');
    expect(mapping.residual.amount).toBe(value.residual.amount);
    expect(mapping.waterfallBars.find((bar) => bar.id === 'residual')?.delta).toBe(value.residual.amount);
  });

  it('derives the approved signed contribution metric once from effect amount and OP delta', () => {
    expect(calculateContributionRate(250, 320)).toBeCloseTo(78.125);
    expect(calculateContributionRate(90, 320)).toBeCloseTo(28.125);
    expect(calculateContributionRate(-30, 320)).toBeCloseTo(-9.375);
    expect(formatContributionRate(calculateContributionRate(250, 320))).toBe('+78.1%');
    expect(formatContributionRate(calculateContributionRate(90, 320))).toBe('+28.1%');
    expect(formatContributionRate(calculateContributionRate(-30, 320))).toBe('-9.4%');
    expect(formatContributionRate(-0.01)).toBe('0.0%');
    expect(calculateContributionRate(30, 0)).toBeNull();
    expect(formatContributionRate(calculateContributionRate(30, 0))).toBe('—');
  });

  it('builds exactly three executive cards with icons, group totals, dots and a separate residual footer', () => {
    const value = presentationFixture();
    const mapping = mapAnalysisPresentation(value);
    expect(mapping.executiveGroups).toHaveLength(3);
    expect(mapping.executiveGroups.map((group) => group.title)).toEqual(['판매 효과', '환율 효과', '비용 효과']);
    expect(mapping.executiveGroups.reduce((sum, group) => sum + group.profitEffect, 0) + mapping.residual.amount)
      .toBe(value.kpis.operating_profit_delta);

    render(<AnalysisPresentationPanel value={value} role="admin" />);
    const executive = screen.getByTestId('analysis-executive-narrative');
    const cards = Array.from(executive.querySelectorAll('.variance-analysis__narrative-group'));
    expect(cards).toHaveLength(3);
    for (const card of cards) {
      expect(card.querySelector('.variance-analysis__narrative-group-icon svg')).toBeInTheDocument();
      expect(within(card as HTMLElement).getAllByText('손익 영향').length).toBeGreaterThan(0);
      for (const effect of Array.from(card.querySelectorAll('.variance-analysis__narrative-effect'))) {
        expect(effect.querySelector('.variance-analysis__effect-dot')).toBeInTheDocument();
        expect(effect.textContent).toContain('손익 영향');
      }
    }
    expect(executive.querySelector('.variance-analysis__effect-dot.is-positive')).toBeInTheDocument();
    expect(executive.querySelector('.variance-analysis__effect-dot.is-negative')).toBeInTheDocument();
    expect(executive.querySelector('.variance-analysis__effect-dot.is-zero')).toBeInTheDocument();
    const residual = executive.querySelector('.variance-analysis__residual-summary');
    expect(residual).toBeInTheDocument();
    expect(residual?.closest('.variance-analysis__narrative-group')).toBeNull();
  });

  it('uses the exact eight-column main table and separate six-column bordered drilldown table', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const detail = screen.getByTestId('analysis-detail-section');
    expect(within(detail).getByRole('heading', { name: '손익 변동 요인 분석표' })).toBeInTheDocument();
    const main = detail.querySelector('.variance-analysis__effect-table') as HTMLTableElement;
    expect(Array.from(main.tHead?.rows[0].cells ?? []).map((cell) => cell.textContent)).toEqual([
      '구분', '손익 변동 원인', '단위', '계획', '실적', '원인변동', '손익 영향 금액', '기여율',
    ]);
    expect(within(detail).queryAllByRole('columnheader', { name: '근거' })).toHaveLength(0);
    expect(within(detail).queryAllByRole('columnheader', { name: '비고' })).toHaveLength(0);
    expect(detail.querySelector('.variance-analysis__category-pill')).toHaveTextContent('내부');

    const container = screen.getByTestId('drilldown-container-sales_quantity');
    expect(container).toBeInTheDocument();
    expect(within(container).getByRole('heading', { name: '↳ [수량] 요인 세부 내역:' }))
      .toHaveClass('variance-analysis__drilldown-heading');
    const inner = container.querySelector('table') as HTMLTableElement;
    expect(inner).not.toBe(main);
    expect(Array.from(inner.tHead?.rows[0].cells ?? []).map((cell) => cell.textContent)).toEqual([
      '세부 항목', '단위', '계획', '실적', '차이', '손익 영향 금액',
    ]);
    expect(container.closest('td')).toHaveAttribute('colspan', '8');
    expect(screen.getByTestId('effect-row-sales_quantity').lastElementChild).toHaveTextContent('+75.0%');
    expect(screen.getByTestId('effect-row-sales_fx').lastElementChild).toHaveTextContent('-20.0%');
  });

  it('partitions every manufacturing account between variable and fixed cost without overlap or double counting', () => {
    const value = presentationFixture();
    const canonicalVariable = value.effects.find((effect) => effect.code === 'sga_variable')!.profit_effect
      + value.effects.find((effect) => effect.code === 'tariff')!.profit_effect;
    const canonicalManufacturing = value.effects.find((effect) => effect.code === 'manufacturing_realized')!.profit_effect;
    const mapping = mapAnalysisPresentation(value);
    const variable = mapping.effects.find((effect) => effect.code === 'sga_variable')!;
    const fixed = mapping.effects.find((effect) => effect.code === 'sga_fixed')!;
    const variableManufacturing = variable.drilldown.rows.filter((row) => row.row_id.startsWith('manufacturing:'));
    const fixedManufacturing = fixed.drilldown.rows.filter((row) => row.row_id.startsWith('manufacturing:'));

    expect(variable.drilldown.rows.map((row) => row.label)).toEqual(expect.arrayContaining([
      '수도광열비', '소모품비', '원자재운반비', '외주가공비',
    ]));
    expect(fixedManufacturing.map((row) => row.label)).toEqual(['감가상각비']);
    expect(new Set([...variableManufacturing, ...fixedManufacturing].map((row) => row.row_id)).size)
      .toBe(variableManufacturing.length + fixedManufacturing.length);
    expect([...variableManufacturing, ...fixedManufacturing]).toHaveLength(5);
    expect(variable.profit_effect).toBe(-6);
    expect(fixed.profit_effect).toBe(-2);
    expect(variable.profit_effect + fixed.profit_effect).toBe(
      canonicalVariable + canonicalManufacturing + value.effects.find((effect) => effect.code === 'sga_fixed')!.profit_effect,
    );
    expect(mapping.effects.find((effect) => effect.code === 'manufacturing_realized')).toBeUndefined();
    expect(mapping.effects.reduce((sum, effect) => sum + effect.profit_effect, 0)).toBe(value.kpis.effects_total);
    expect(mapping.residual.amount).toBe(value.residual.amount);

    render(<AnalysisPresentationPanel value={value} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '변동비 상세 펼치기' }));
    for (const account of ['수도광열비', '소모품비', '원자재운반비', '외주가공비']) {
      expect(screen.getByText(account)).toBeInTheDocument();
      expect(screen.queryByText(`일반관리비_${account}`)).not.toBeInTheDocument();
    }
  });

  it('renders separate variable-cost SG&A and manufacturing tables with section toggles and clean account labels', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '변동비 상세 펼치기' }));

    const sga = screen.getByTestId('sga_variable-sga-subgroup');
    const manufacturing = screen.getByTestId('sga_variable-manufacturing-subgroup');
    expect(within(sga).getByRole('heading', { name: '판관비 변동비' })).toBeInTheDocument();
    expect(within(manufacturing).getByRole('heading', { name: '제조경비 변동비' })).toBeInTheDocument();
    expect(within(sga).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      '구분', '계정명', '단위', '계획', '실적', '차이', '손익 영향 금액',
    ]);
    expect(within(sga).getByRole('button', { name: '판매비' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(sga).getByText('운반비')).toBeInTheDocument();
    expect(within(sga).getByText('관세')).toBeInTheDocument();
    expect(within(sga).queryByText('판매비_운반비')).not.toBeInTheDocument();

    fireEvent.click(within(sga).getByRole('button', { name: '일반관리비' }));
    expect(within(sga).getByText('소모품비')).toBeInTheDocument();
    expect(within(sga).queryByText('일반관리비_소모품비')).not.toBeInTheDocument();
    expect(within(manufacturing).getAllByText('제조').length).toBe(4);
    for (const account of ['수도광열비', '소모품비', '원자재운반비', '외주가공비']) {
      expect(within(manufacturing).getByText(account)).toBeInTheDocument();
    }
    expect(within(manufacturing).queryByRole('button', { name: /판매비|일반관리비/ })).not.toBeInTheDocument();
  });

  it('uses the authoritative section when selling and general-admin accounts share the same name', () => {
    const value = presentationFixture();
    const sgaVariable = value.effects.find((effect) => effect.code === 'sga_variable')!;
    sgaVariable.drilldown.rows[0].label = '운반비';
    sgaVariable.drilldown.rows[1].label = '운반비';
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '변동비 상세 펼치기' }));
    const sga = screen.getByTestId('sga_variable-sga-subgroup');
    expect(within(sga).getByText('운반비')).toBeInTheDocument();
    expect(within(sga).getAllByText('판매비').length).toBeGreaterThan(0);
    fireEvent.click(within(sga).getByRole('button', { name: '일반관리비' }));
    expect(within(sga).getByText('운반비')).toBeInTheDocument();
    expect(within(sga).getAllByText('일반관리비').length).toBeGreaterThan(0);
  });

  it('renders separate fixed-cost SG&A and manufacturing tables and keeps remaining manufacturing accounts fixed', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '고정비 상세 펼치기' }));

    const sga = screen.getByTestId('sga_fixed-sga-subgroup');
    const manufacturing = screen.getByTestId('sga_fixed-manufacturing-subgroup');
    expect(within(sga).getByRole('heading', { name: '판관비 고정비' })).toBeInTheDocument();
    expect(within(sga).getByText('광고선전비')).toBeInTheDocument();
    fireEvent.click(within(sga).getByRole('button', { name: '일반관리비' }));
    expect(within(sga).getByText('인건비')).toBeInTheDocument();
    expect(within(manufacturing).getByText('감가상각비')).toBeInTheDocument();
    expect(within(manufacturing).getByText('제조')).toBeInTheDocument();
    for (const variableAccount of ['수도광열비', '소모품비', '원자재운반비', '외주가공비']) {
      expect(within(manufacturing).queryByText(variableAccount)).not.toBeInTheDocument();
    }
  });

  it('removes drilldown controls from sales FX and inventory while preserving click selection', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    expect(screen.queryByRole('button', { name: /매출환율 상세/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /재고 차이 등 상세/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('effect-select-sales_fx'));
    expect(screen.getByTestId('effect-select-sales_fx')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByTestId('drilldown-container-sales_fx')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('effect-select-inventory_timing'));
    expect(screen.getByTestId('effect-select-inventory_timing')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByTestId('drilldown-container-inventory_timing')).not.toBeInTheDocument();
  });

  it('keeps additional evidence collapsed by default and exposes both evidence tables through one button', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const evidence = screen.getByTestId('analysis-additional-evidence');
    const content = evidence.querySelector('#analysis-additional-evidence-content');
    expect(within(evidence).getByRole('button', { name: '펼치기' })).toHaveAttribute('aria-expanded', 'false');
    expect(content).toHaveAttribute('hidden');
    expect(within(evidence).queryByRole('heading', { name: '판매 수량/매출' })).not.toBeInTheDocument();
    fireEvent.click(within(evidence).getByRole('button', { name: '펼치기' }));
    expect(within(evidence).getByRole('button', { name: '접기' })).toHaveAttribute('aria-expanded', 'true');
    expect(content).not.toHaveAttribute('hidden');
    expect(within(evidence).getByRole('heading', { name: '판매 수량/매출' })).toBeInTheDocument();
    expect(within(evidence).getByRole('heading', { name: '생산 수량' })).toBeInTheDocument();
    fireEvent.click(within(evidence).getByRole('button', { name: '접기' }));
    expect(content).toHaveAttribute('hidden');
  });

  it('keeps selection synchronized between Effect table and Waterfall, including residual', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const qtyBar = screen.getByTestId('waterfall-bar-sales_quantity');
    fireEvent.click(qtyBar);
    expect(screen.getByTestId('effect-select-sales_quantity')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('effect-row-sales_quantity')).toHaveClass('row-active');

    fireEvent.click(screen.getByTestId('effect-select-residual'));
    expect(screen.getByTestId('waterfall-bar-residual')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('effect-row-residual')).toHaveClass('row-active');
  });

  it('uses profit-effect sign classes for positive, negative and zero values', () => {
    const value = presentationFixture();
    value.effects[0] = { ...value.effects[0], profit_effect: 0 };
    value.effects[1] = { ...value.effects[1], profit_effect: 0 };
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByTestId('effect-tone-sales_quantity')).toHaveClass('variance-analysis__tone--zero');
    expect(screen.getByTestId('effect-tone-sales_price')).toHaveClass('variance-analysis__tone--positive');
    expect(screen.getByTestId('effect-tone-sales_fx')).toHaveClass('variance-analysis__tone--negative');
    expect(screen.getByTestId('effect-tone-residual')).toHaveClass('variance-analysis__tone--positive');
  });

  it('uses the same unfavorable tone for a negative residual', () => {
    const value = presentationFixture();
    value.residual.amount = -20;
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByTestId('effect-tone-residual')).toHaveClass('variance-analysis__tone--negative');
    expect(screen.getByTestId('waterfall-bar-residual')).toHaveClass('variance-analysis__waterfall-bar--negative');
  });

  it('keeps hover visual-only while click and keyboard activation update the selected detail', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const quantitySelect = screen.getByTestId('effect-select-sales_quantity');
    expect(quantitySelect).toHaveAttribute('aria-pressed', 'true');

    for (const code of ['sales_quantity', 'sga_variable', 'sga_fixed', 'residual']) {
      fireEvent.mouseEnter(screen.getByTestId(`waterfall-bar-${code}`));
      expect(quantitySelect).toHaveAttribute('aria-pressed', 'true');
      fireEvent.mouseLeave(screen.getByTestId(`waterfall-bar-${code}`));
    }

    fireEvent.click(screen.getByTestId('waterfall-bar-sga_fixed'));
    expect(screen.getByTestId('effect-select-sga_fixed')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.keyDown(screen.getByTestId('waterfall-bar-sga_variable'), { key: 'Enter' });
    expect(screen.getByTestId('effect-select-sga_variable')).toHaveAttribute('aria-pressed', 'true');
  });

  it('uses the mockup result hierarchy and opens the first available drilldown', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const summary = screen.getByTestId('analysis-summary-header');
    const narrative = screen.getByTestId('analysis-executive-narrative');
    const waterfall = screen.getByTestId('analysis-waterfall-card');
    const detail = screen.getByTestId('analysis-detail-section');
    const evidence = screen.getByTestId('analysis-additional-evidence');

    expect(summary.compareDocumentPosition(narrative) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(narrative.compareDocumentPosition(waterfall) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(waterfall.compareDocumentPosition(detail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(detail.compareDocumentPosition(evidence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId('analysis-effect-group-sales')).toBeInTheDocument();
    expect(screen.getByTestId('analysis-effect-group-fx')).toBeInTheDocument();
    expect(screen.getByTestId('analysis-effect-group-cost')).toBeInTheDocument();
    expect(within(screen.getByTestId('analysis-effect-group-sales')).getAllByRole('button').map((button) => button.textContent)).toEqual([
      expect.stringContaining('수량'),
      expect.stringContaining('판가'),
    ]);
    expect(within(screen.getByTestId('analysis-effect-group-fx')).getAllByRole('button')).toHaveLength(1);
    expect(within(screen.getByTestId('analysis-effect-group-cost')).getAllByRole('button')).toHaveLength(4);
    expect(screen.queryByText('긍정 요인')).not.toBeInTheDocument();
    expect(screen.queryByText('부정 요인')).not.toBeInTheDocument();
    expect(screen.queryByText(/Residual 서버 값/i)).not.toBeInTheDocument();
    expect(within(summary).getByRole('button', { name: '분석 근거 엑셀 내려받기' })).toBeInTheDocument();
    expect(waterfall.querySelector('.variance-analysis__waterfall-svg')).toHaveAttribute('viewBox', '0 0 960 295');
    expect(detail.querySelector('.variance-analysis__table-scroll')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '수량 상세 접기' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('uses the approved Waterfall copy, two-line totals, short inventory label and gradients', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const waterfall = screen.getByTestId('analysis-waterfall-card');
    expect(within(waterfall).getByText('손익영향 Waterfall 분석')).toBeInTheDocument();
    expect(within(waterfall).getByText('단위: 억원 · 막대 클릭 시 하단 세부 내역 연동')).toBeInTheDocument();
    for (const label of ['기준(계획)', '이익증가 (+)', '이익감소 (-)', '비교(실적)', '영업이익', '재고 차이 등']) {
      expect(within(waterfall).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByTestId('waterfall-gradient-definitions').querySelectorAll('linearGradient')).toHaveLength(5);
    expect(screen.getByTestId('waterfall-bar-sales_quantity').querySelector('.variance-analysis__waterfall-rect'))
      .toHaveAttribute('fill', 'url(#waterfall-gradient-positive)');
  });

  it('removes visible remark headers, centers every header and uses approved evidence titles', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    expect(screen.queryAllByRole('columnheader', { name: /^(비고|Remarks|Note)$/i })).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '펼치기' }));
    expect(screen.getByRole('heading', { name: '판매 수량/매출' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '생산 수량' })).toBeInTheDocument();
    expect(screen.getByText('단위: 백만원, %, PCS, m')).toBeInTheDocument();
    expect(screen.getByText('수량: PCS, m · 금액: 백만원')).toBeInTheDocument();
    expect(screen.getByText('단위: PCS, m')).toBeInTheDocument();
    expect(screen.queryByText(/DTO 값 유지|상세 값은 서버 DTO|서버가 제공한 판매 수량/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '제품군 근거' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '제조 조업도 근거' })).not.toBeInTheDocument();
    const tables = Array.from(screen.getByTestId('analysis-presentation').querySelectorAll('table'));
    for (const table of tables) {
      const headers = Array.from(table.tHead?.rows[0]?.cells ?? []);
      expect(headers.length).toBeGreaterThan(0);
      expect(table.tHead).toHaveClass('variance-analysis__table-head');
      for (const header of headers) {
        expect(header).not.toHaveClass('text-right');
      }
      for (const row of Array.from(table.tBodies[0]?.rows ?? [])) {
        const occupiedColumns = Array.from(row.cells).reduce((count, cell) => count + cell.colSpan, 0);
        expect(occupiedColumns).toBe(headers.length);
      }
    }
  });

  it('formats every Analysis quantity as a rounded integer with grouping', () => {
    expect(formatQuantity(100)).toBe('100');
    expect(formatQuantity(100.4)).toBe('100');
    expect(formatQuantity(100.6)).toBe('101');
    expect(formatQuantity(12345.7)).toBe('12,346');

    const value = presentationFixture();
    value.product_groups[0].baseline_quantity = 100.6;
    value.manufacturing_activities[0].comparison = 12345.7;
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '펼치기' }));
    expect(screen.getByText('101')).toBeInTheDocument();
    expect(screen.getByText('12,346')).toBeInTheDocument();
  });

  it('rejects an identity mismatch without correcting the payload or showing Evidence', async () => {
    const malformed = presentationFixture();
    malformed.kpis.effects_total += 1;
    vi.stubGlobal('fetch', vi.fn(() => json(malformed)));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText('서버 응답 형식이 올바르지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByTestId('analysis-presentation')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
  });

  it('clears READY presentation and Evidence together when Viewer availability changes', async () => {
    let reads = 0;
    vi.stubGlobal('fetch', vi.fn(() => {
      reads += 1;
      return reads === 1
        ? json(presentationFixture())
        : json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available' } }, 404);
    }));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByTestId('analysis-presentation')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '분석 근거 엑셀 내려받기' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(screen.queryByTestId('analysis-presentation')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
    expect(screen.getByTestId('viewer-empty')).toBeInTheDocument();
  });

  it('does not let an older Viewer response overwrite the latest Result', async () => {
    let resolveFirst!: (response: Response) => void;
    const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(() => {
      calls += 1;
      if (calls === 1) return first;
      const current = presentationFixture();
      current.identity.baseline_model_name = 'Latest Base';
      return json(current);
    }));
    render(<CoreAnalysisView role="viewer" />);
    const input = screen.getByLabelText('Result ID');
    fireEvent.change(input, { target: { value: '55555555-5555-4555-8555-555555555555' } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    fireEvent.change(input, { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText(/Latest Base/)).toBeInTheDocument();
    const old = presentationFixture();
    old.identity.baseline_model_name = 'Old Base';
    resolveFirst(new Response(JSON.stringify(old), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await waitFor(() => expect(screen.queryByText(/Old Base/)).not.toBeInTheDocument());
    expect(screen.getByText(/Latest Base/)).toBeInTheDocument();
  });
});
