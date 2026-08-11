import React from 'react';
import { ProductGroupPnlItem } from '../../types/pnl';
import { Layers } from 'lucide-react';

interface ProductGroupTableProps {
  groups: ProductGroupPnlItem[];
  onSelectGroup?: (group: any) => void;
}

export const ProductGroupTable: React.FC<ProductGroupTableProps> = ({ groups, onSelectGroup }) => {
  const formatAmount = (val: number) => Math.round(val).toLocaleString();
  const formatDiff = (val: number) => (val > 0 ? `+${Math.round(val).toLocaleString()}` : Math.round(val).toLocaleString());

  const totalRev = groups.reduce((acc, g) => acc + g.revenue, 0);
  const totalPlanRev = groups.reduce((acc, g) => acc + g.planRevenue, 0);
  const totalOp = groups.reduce((acc, g) => acc + g.operatingProfit, 0);
  const totalPlanOp = groups.reduce((acc, g) => acc + g.planOperatingProfit, 0);

  return (
    <div className="financial-table-container">
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#f8fafc' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px' }}>
          <Layers size={15} color="#0f766e" />
          제품군별 손익 현황 (Product Group Breakdown)
        </div>
        <span className="unit-tag">단위: 백만원 / %</span>
      </div>

      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: '22%' }}>제품군 (Product Group)</th>
            <th className="text-right" style={{ width: '13%' }}>매출액 (실적)</th>
            <th className="text-right" style={{ width: '12%' }}>매출 계획</th>
            <th className="text-right" style={{ width: '11%' }}>달성률</th>
            <th className="text-right" style={{ width: '13%' }}>영업이익 (실적)</th>
            <th className="text-right" style={{ width: '11%' }}>이익 차이</th>
            <th className="text-right" style={{ width: '10%' }}>영업이익률</th>
            <th className="text-right" style={{ width: '8%' }}>매출비중</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr
              key={g.productGroup}
              style={{ cursor: onSelectGroup ? 'pointer' : 'default' }}
              onClick={() => onSelectGroup && onSelectGroup(g.productGroup)}
            >
              <td className="text-left" style={{ fontWeight: 600 }}>
                <span className={`model-pill model-pill-${g.productGroup.toLowerCase()}`} style={{ marginRight: 6 }}>
                  {g.productGroup}
                </span>
                {g.groupName}
              </td>
              <td className="text-right tabular-nums" style={{ fontWeight: 600 }}>{formatAmount(g.revenue)}</td>
              <td className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>{formatAmount(g.planRevenue)}</td>
              <td className={`text-right tabular-nums ${g.revenueAchievementRate >= 100 ? 'val-favorable' : 'val-unfavorable'}`}>
                {g.revenueAchievementRate.toFixed(1)}%
              </td>
              <td className="text-right tabular-nums" style={{ fontWeight: 700, color: '#1e3a8a' }}>{formatAmount(g.operatingProfit)}</td>
              <td className={`text-right tabular-nums ${g.opProfitVariance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                {formatDiff(g.opProfitVariance)}
              </td>
              <td className="text-right tabular-nums" style={{ fontWeight: 600 }}>
                {g.operatingMargin.toFixed(1)}%
              </td>
              <td className="text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                {g.shareOfRevenue.toFixed(1)}%
              </td>
            </tr>
          ))}

          {/* Total Row */}
          <tr className="row-total">
            <td className="text-left">전사 합계 (Total)</td>
            <td className="text-right tabular-nums">{formatAmount(totalRev)}</td>
            <td className="text-right tabular-nums">{formatAmount(totalPlanRev)}</td>
            <td className="text-right tabular-nums">
              {((totalRev / totalPlanRev) * 100).toFixed(1)}%
            </td>
            <td className="text-right tabular-nums">{formatAmount(totalOp)}</td>
            <td className="text-right tabular-nums val-favorable">
              {formatDiff(totalOp - totalPlanOp)}
            </td>
            <td className="text-right tabular-nums">
              {((totalOp / totalRev) * 100).toFixed(1)}%
            </td>
            <td className="text-right tabular-nums">100.0%</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};
