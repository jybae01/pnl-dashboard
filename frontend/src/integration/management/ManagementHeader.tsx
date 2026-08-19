import { Search, Settings2 } from 'lucide-react';

type ModelType = 'PLAN' | 'ACTUAL' | 'FORECAST';
type PublicationFilter = 'ALL' | 'PUBLISHED' | 'UNPUBLISHED';

export function ManagementHeader({
  typeFilter,
  publicationFilter,
  search,
  onTypeFilterChange,
  onPublicationFilterChange,
  onSearchChange,
  onNavigateToForecast,
  onNavigateToAnalysis,
}: {
  typeFilter: 'ALL' | ModelType;
  publicationFilter: PublicationFilter;
  search: string;
  onTypeFilterChange: (value: 'ALL' | ModelType) => void;
  onPublicationFilterChange: (value: PublicationFilter) => void;
  onSearchChange: (value: string) => void;
  onNavigateToForecast?: () => void;
  onNavigateToAnalysis?: () => void;
}) {
  return <header className="view-header-bar data-management__header">
    <div className="data-management__title">
      <Settings2 size={16} aria-hidden="true" />
      <h1 id="management-page-heading">손익 모형 데이터 관리</h1>
    </div>

    <div className="data-management__header-controls" aria-label="모형 목록 필터">
      <div className="data-management__filter-item">
        <span className="data-management__filter-label">모형 구분:</span>
        <div className="data-management__segmented-control" role="group" aria-label="유형 필터">
          {(['ALL', 'ACTUAL', 'PLAN', 'FORECAST'] as const).map((value) => <button
            key={value}
            type="button"
            className={`data-management__segmented-button ${typeFilter === value ? 'is-active' : ''}`}
            aria-pressed={typeFilter === value}
            onClick={() => onTypeFilterChange(value)}
          >
            {value === 'ALL' ? '전체' : value === 'ACTUAL' ? '실적' : value === 'PLAN' ? '계획' : '추정'}
          </button>)}
        </div>
      </div>

      <label className="data-management__filter-item">
        <span className="data-management__filter-label">공개 상태:</span>
        <select
          aria-label="공개 상태 필터"
          className="data-management__filter-control"
          value={publicationFilter}
          onChange={(event) => onPublicationFilterChange(event.target.value as PublicationFilter)}
        >
          <option value="ALL">전체 상태</option>
          <option value="PUBLISHED">공개</option>
          <option value="UNPUBLISHED">비공개</option>
        </select>
      </label>

      <label className="data-management__search">
        <Search size={13} aria-hidden="true" />
        <input
          aria-label="모형 검색"
          placeholder="모형명·파일명·기간 검색"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      {(onNavigateToForecast || onNavigateToAnalysis) && <div className="data-management__header-actions">
        {onNavigateToForecast && <button type="button" className="data-management__secondary data-management__compact-action" onClick={onNavigateToForecast}>추정 산출</button>}
        {onNavigateToAnalysis && <button type="button" className="data-management__secondary data-management__compact-action" onClick={onNavigateToAnalysis}>손익분석 결과</button>}
      </div>}
    </div>
  </header>;
}
