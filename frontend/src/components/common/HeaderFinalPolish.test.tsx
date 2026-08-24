import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { Header } from './Header';


describe('global header final title', () => {
  it('uses the exact system title without duplicating the logo brand and keeps the narrow layout unclipped', () => {
    render(<Header session={{ authenticated: true, role: 'viewer', expires_at: '2026-08-23T00:00:00Z', dto_version: '1' }} />);
    expect(screen.getByText('손익 분석 업무 시스템')).toBeInTheDocument();
    expect(screen.queryByText('NANOH2O 손익 분석 업무 시스템')).not.toBeInTheDocument();
    expect(screen.getByText('Management Accounting & P&L Planning')).toBeInTheDocument();
    expect(screen.queryByText('제조업 손익분석 시스템')).not.toBeInTheDocument();
    const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf8');
    expect(css).toContain('@media (max-width: 520px)');
    expect(css).toMatch(/\.env-tag\s*\{\s*display:\s*none/);
    expect(css).toMatch(/--nano-logo-height:\s*12px/);
  });
});
