import React from 'react';
import { ProductGroup, PRODUCT_GROUPS } from '../../types/common';
import { Layers } from 'lucide-react';

interface ProductGroupSelectorProps {
  value: ProductGroup;
  onChange: (group: ProductGroup) => void;
  disabled?: boolean;
}

export const ProductGroupSelector: React.FC<ProductGroupSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="filter-item">
      <span className="filter-label">
        <Layers size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
        제품군:
      </span>
      <div className="segmented-control">
        {PRODUCT_GROUPS.map((g) => (
          <button
            key={g.code}
            type="button"
            className={`segmented-btn ${value === g.code ? 'active' : ''}`}
            onClick={() => !disabled && onChange(g.code)}
            disabled={disabled}
            title={g.shortDesc}
          >
            {g.code === 'ALL' ? '전체' : g.code}
          </button>
        ))}
      </div>
    </div>
  );
};
