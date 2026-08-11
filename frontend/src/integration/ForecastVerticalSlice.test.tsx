import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ForecastGenerationView } from '../views/ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';
const MODEL = '22222222-2222-4222-8222-222222222222';
const GENERATION = '33333333-3333-4333-8333-333333333333';

afterEach(() => vi.unstubAllGlobals());

describe('Forecast React vertical slice', () => {
  it('submits canonical inputs and renders the durable draft Model without fake progress', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ models: [{
        model_id: BASE, display_name: '2026 Actual', model_type: 'ACTUAL', model_year: 2026,
        start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1',
      }], dto_version: '1' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        generation_id: GENERATION, model_id: MODEL, display_name: 'Forecast Model', model_year: 2026,
        start_month: 7, end_month: 7, is_published: false, is_default: false,
        workbook_sha256: 'a'.repeat(64), idempotency_replayed: false,
        execution_mode: 'SYNCHRONOUS', dto_version: '1',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByText(/2026 Actual/);
    fireEvent.click(screen.getByRole('button', { name: 'Forecast Model 생성' }));
    await screen.findByText('Forecast 생성 완료');
    expect(screen.getByText(/비공개 \/ non-default/)).toBeInTheDocument();
    expect(screen.queryByText(/23%|64%|90%/)).not.toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[1];
    const body = JSON.parse(String(init.body));
    expect(body.base_model_id).toBe(BASE);
    expect(body.months[0].month).toBe(7);
    expect(body.idempotency_key).toBeTruthy();
  });

  it('keeps the same idempotency key when a network retry is made without editing', async () => {
    const requests: string[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/api/models')) return new Response(JSON.stringify({ models: [{
        model_id: BASE, display_name: 'Base', model_type: 'ACTUAL', model_year: 2026,
        start_month: 1, end_month: 12, is_published: true, is_default: false,
      }] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      requests.push(JSON.parse(String(init?.body)).idempotency_key);
      if (requests.length === 1) throw new TypeError('timeout');
      return new Response(JSON.stringify({ generation_id: GENERATION, model_id: MODEL,
        display_name: 'Forecast Model', model_year: 2026, start_month: 7, end_month: 7,
        is_published: false, is_default: false, workbook_sha256: 'b'.repeat(64),
        idempotency_replayed: true, execution_mode: 'SYNCHRONOUS', dto_version: '1' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />); await screen.findByText(/Base/);
    fireEvent.click(screen.getByRole('button', { name: 'Forecast Model 생성' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Forecast Model 생성' }));
    await screen.findByText('Forecast 생성 완료');
    expect(requests[0]).toBe(requests[1]);
  });
});
