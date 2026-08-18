import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AnalysisPresentationPanel, formatQuantity } from './AnalysisPresentationPanel';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture, TEST_RESULT } from './presentationTestFixture';
import { CANONICAL_EFFECT_ORDER, mapAnalysisPresentation } from './analysisPresentation';

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
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.queryByText('미설명 잔여차이')).not.toBeInTheDocument();
    for (const label of ['수량', '판가', '매출환율', '원재료', '변동비', '고정비', '제조', '재고·원가 반영시차', '기타 요인']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.queryByText('판매단가')).not.toBeInTheDocument();
    expect(screen.queryByText('제조경비 손익실현')).not.toBeInTheDocument();
    expect(screen.queryByText('UNEXPLAINED')).not.toBeInTheDocument();
    for (const category of ['내부', '외부', '비용']) {
      expect(screen.getAllByText(category).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('Effect 총액 (서버)')).toBeInTheDocument();
    expect(screen.getByText('판매수량 및 제품 Mix 변동 영향')).toBeInTheDocument();
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
      'sales_quantity', 'sales_price', 'sales_fx', 'material_total', 'sga_variable', 'sga_fixed', 'manufacturing_realized', 'inventory_timing',
    ]);
    expect(mapping.effects.map((effect) => effect.uiLabel)).toEqual([
      '수량', '판가', '매출환율', '원재료', '변동비', '고정비', '제조', '재고·원가 반영시차',
    ]);
    expect(mapping.effects.map((effect) => effect.uiCategoryLabel)).toEqual([
      '내부', '내부', '외부', '비용', '비용', '비용', '비용', '비용',
    ]);
    expect(mapping.residual.uiLabel).toBe('기타 요인');
    expect(mapping.residual.amount).toBe(value.residual.amount);
    expect(mapping.waterfallBars.find((bar) => bar.id === 'residual')?.delta).toBe(value.residual.amount);
  });

  it('moves exactly four authoritative manufacturing account effects into variable cost without double counting', () => {
    const value = presentationFixture();
    const canonicalVariable = value.effects.find((effect) => effect.code === 'sga_variable')!.profit_effect
      + value.effects.find((effect) => effect.code === 'tariff')!.profit_effect;
    const canonicalManufacturing = value.effects.find((effect) => effect.code === 'manufacturing_realized')!.profit_effect;
    const mapping = mapAnalysisPresentation(value);
    const variable = mapping.effects.find((effect) => effect.code === 'sga_variable')!;
    const manufacturing = mapping.effects.find((effect) => effect.code === 'manufacturing_realized')!;

    expect(variable.drilldown.rows.map((row) => row.label)).toEqual(expect.arrayContaining([
      '수도광열비', '소모품비', '원자재운반비', '외주가공비',
    ]));
    expect(manufacturing.drilldown.rows.map((row) => row.label)).not.toEqual(expect.arrayContaining([
      '수도광열비', '소모품비', '원자재운반비', '외주가공비',
    ]));
    expect(variable.profit_effect).toBe(-6);
    expect(manufacturing.profit_effect).toBe(-4);
    expect(variable.profit_effect + manufacturing.profit_effect).toBe(canonicalVariable + canonicalManufacturing);
    expect(mapping.effects.reduce((sum, effect) => sum + effect.profit_effect, 0)).toBe(value.kpis.effects_total);
    expect(mapping.residual.amount).toBe(value.residual.amount);

    render(<AnalysisPresentationPanel value={value} role="admin" />);
    fireEvent.click(screen.getByRole('button', { name: '변동비 상세 펼치기' }));
    for (const account of ['수도광열비', '소모품비', '원자재운반비', '외주가공비']) {
      expect(screen.getByText(account)).toBeInTheDocument();
      expect(screen.queryByText(`일반관리비_${account}`)).not.toBeInTheDocument();
    }
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

    for (const code of ['sales_quantity', 'sga_variable', 'manufacturing_realized', 'residual']) {
      fireEvent.mouseEnter(screen.getByTestId(`waterfall-bar-${code}`));
      expect(quantitySelect).toHaveAttribute('aria-pressed', 'true');
      fireEvent.mouseLeave(screen.getByTestId(`waterfall-bar-${code}`));
    }

    fireEvent.click(screen.getByTestId('waterfall-bar-manufacturing_realized'));
    expect(screen.getByTestId('effect-select-manufacturing_realized')).toHaveAttribute('aria-pressed', 'true');
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
    expect(within(screen.getByTestId('analysis-effect-group-cost')).getAllByRole('button')).toHaveLength(5);
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
    for (const label of ['기준(계획)', '이익증가 (+)', '이익감소 (-)', '비교(실적)', '영업이익', '재고차이 등']) {
      expect(within(waterfall).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByTestId('waterfall-gradient-definitions').querySelectorAll('linearGradient')).toHaveLength(5);
    expect(screen.getByTestId('waterfall-bar-sales_quantity').querySelector('.variance-analysis__waterfall-rect'))
      .toHaveAttribute('fill', 'url(#waterfall-gradient-positive)');
  });

  it('removes visible remark headers, centers every header and uses approved evidence titles', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    expect(screen.queryAllByRole('columnheader', { name: /^(비고|Remarks|Note)$/i })).toHaveLength(0);
    expect(screen.getByRole('heading', { name: '판매 수량/매출' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '생산 수량' })).toBeInTheDocument();
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
