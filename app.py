import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# 1. 페이지 기본 설정
st.set_page_config(page_title="월별 손익계산서 분석표", layout="wide")

# [HTML/CSS] 디자인 및 아코디언(접기/펴기) 애니메이션 CSS
st.markdown("""
<style>
.custom-tbl { width: 100%; border-collapse: collapse; font-size: 13px; font-family: "Pretendard", "Malgun Gothic", sans-serif; margin-bottom: 20px; }
.custom-tbl th { text-align: center !important; padding: 10px 8px; border: 1px solid rgba(128, 128, 128, 0.2); white-space: nowrap; background-color: rgba(128, 128, 128, 0.05); color: inherit; }
.custom-tbl td { text-align: right !important; padding: 8px; border: 1px solid rgba(128, 128, 128, 0.2); white-space: nowrap; }
.custom-tbl td:first-child { text-align: center !important; font-weight: bold; background-color: rgba(128, 128, 128, 0.02); }

.pnl-container tr:has(.child-qty) { display: none; }
.pnl-container tr:has(.child-sales) { display: none; }
#toggle-qty:checked ~ table tr:has(.child-qty) { display: table-row; }
#toggle-sales:checked ~ table tr:has(.child-sales) { display: table-row; }

.icon-qty::before, .icon-sales::before { content: "[+]"; color: #3B82F6; font-weight: 900; margin-right: 6px; display: inline-block; width: 18px; }
#toggle-qty:checked ~ table .icon-qty::before { content: "[-]"; color: #EF4444; }
#toggle-sales:checked ~ table .icon-sales::before { content: "[-]"; color: #EF4444; }
label[for="toggle-qty"], label[for="toggle-sales"] { cursor: pointer; margin: 0; display: block; width: 100%; }
</style>
""", unsafe_allow_html=True)

def render_html_table(df):
    html = df.to_html(index=False, classes="custom-tbl", escape=False)
    st.markdown(f'<div style="width:100%; overflow-x:auto;">{html}</div>', unsafe_allow_html=True)

def render_pnl_table(df):
    html = df.to_html(index=False, classes="custom-tbl", escape=False)
    wrapper = f"""
    <div class="pnl-container" style="width:100%; overflow-x:auto;">
        <input type="checkbox" id="toggle-qty" style="display:none;">
        <input type="checkbox" id="toggle-sales" style="display:none;">
        {html}
    </div>
    """
    st.markdown(wrapper, unsafe_allow_html=True)

months = [f"{i}월" for i in range(1, 13)]

# --- 1. 사이드바 (엑셀 템플릿 및 업로드) ---
st.sidebar.markdown("### 📁 데이터 연동 관리")

original_format_items = [
    ('★손익계산서', '대분류', '소분류', '세분류'),
    ('Ⅰ.매출액', '1.제품 매출액', '금액(천원)', '제품매출입력'),
    ('Ⅰ.매출액', '2.반제품 매출액', '금액(천원)', '반제품매출입력'),
    ('Ⅰ.매출액', '3.상품 매출액', '금액(천원)', '상품매출입력'),
    ('Ⅰ.매출액', '4.기타 매출액', '금액(천원)', '기타매출입력'),
    ('Ⅰ.매출액', '5.판매장려금', '금액(천원)', '판매장려금입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '판매량(pcs)', 'SW수량입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '판매량(pcs)', 'BW수량입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '판매량(pcs)', 'LS수량입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '판매량(pcs)', 'FS수량입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '단가(원)', 'SW단가입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '단가(원)', 'BW단가입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '단가(원)', 'LS단가입력'),
    ('Ⅰ.매출액', '1.제품 매출액', '단가(원)', 'FS단가입력'),
    ('Ⅱ.매출원가', '1.제품 매출원가', '원부재료', '원부재료비입력'),
    ('Ⅱ.매출원가', '1.제품 매출원가', '노무비', '노무비입력'),
    ('Ⅱ.매출원가', '1.제품 매출원가', '외주가공비', '외주가공비입력'),
    ('Ⅱ.매출원가', '1.제품 매출원가', '기타경비', '기타경비입력'),
    ('Ⅳ.판매관리비', '1.판매비', '급여', '급여입력'),
    ('Ⅳ.판매관리비', '1.판매비', '복리후생비', '복리후생비입력'),
    ('Ⅳ.판매관리비', '2.일반관리비', '임차료', '임차료입력'),
    ('Ⅳ.판매관리비', '2.일반관리비', '경상연구개발비', '경상개발비입력'),
    ('Ⅳ.판매관리비', '2.일반관리비', '기타판관비', '기타판관비입력'),
    ('참고데이터', 'Item별 원가', '8인치 SW', '8인치 SW 매출원가'),
    ('참고데이터', 'Item별 원가', '8인치 BW', '8인치 BW 매출원가'),
    ('참고데이터', 'Item별 판관비', '8인치 SW', '8인치 SW 판관비'),
    ('참고데이터', 'Item별 판관비', '8인치 BW', '8인치 BW 판관비'),
]

tpl_rows = []
for row in original_format_items:
    if row[0] == '★손익계산서': tpl_rows.append(list(row) + months)
    else: tpl_rows.append(list(row) + [None]*12)

df_template = pd.DataFrame(tpl_rows)

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    df_template.to_excel(writer, index=False, header=False, sheet_name='Sheet1')
    try:
        from openpyxl.styles import PatternFill, Font
        worksheet = writer.sheets['Sheet1']
        for col, width in zip(['A','B','C','D'], [15, 15, 15, 15]): worksheet.column_dimensions[col].width = width
        for col in range(5, 17): worksheet.column_dimensions[worksheet.cell(row=1, column=col).column_letter].width = 12
        header_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
        for cell in worksheet[1]: cell.fill = header_fill; cell.font = Font(bold=True)
        worksheet.freeze_panes = 'E2'
    except: pass

st.sidebar.download_button(
    label="📥 데이터 입력용 엑셀 양식 다운로드",
    data=buffer.getvalue(),
    file_name="손익계산서_입력양식.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="하나의 양식을 다운받아 '계획용'과 '실적용'으로 각각 저장 후 업로드하세요."
)

st.sidebar.markdown("---")
plan_file = st.sidebar.file_uploader("📤 1. 계획(Plan) 데이터 업로드", type=['xlsx'])
actual_file = st.sidebar.file_uploader("📤 2. 실적(Actual) 데이터 업로드", type=['xlsx'])


# --- 2. 상단 헤더 및 연도 선택 ---
st.title("손익계산서 조회") 
col1, col2, col3 = st.columns(3)
with col1:
    inner_col1, inner_col2 = st.columns([1, 1])
    with inner_col1: selected_year = st.selectbox("연도", ["2026년", "2025년"])

# --- 3. 데이터 할당 및 파싱 로직 ---
def extract_series(keyword, df_data, col_start=4):
    for idx, row in df_data.iterrows():
        if keyword in str(row[2]) or keyword in str(row[3]):
            return pd.to_numeric(row[col_start:col_start+12], errors='coerce').fillna(0).values
    return None

def safe_extract(keyword, df_data, default_val=None):
    res = extract_series(keyword, df_data)
    if res is not None: return res
    if default_val is not None: return default_val
    return np.zeros(12)

# (1) 더미 데이터 (기본값)
np.random.seed(42)
qty_sw_a = np.random.randint(100, 300, 12); qty_sw_p = qty_sw_a * np.random.uniform(0.9, 1.2, 12)
qty_bw_a = np.random.randint(50, 150, 12);  qty_bw_p = qty_bw_a * np.random.uniform(0.9, 1.2, 12)
qty_ls_a = np.random.randint(200, 500, 12); qty_ls_p = qty_ls_a * np.random.uniform(0.9, 1.2, 12)
qty_fs_a = np.random.randint(80, 200, 12);  qty_fs_p = qty_fs_a * np.random.uniform(0.9, 1.2, 12)

price_sw_a = np.full(12, 50.0); price_sw_p = np.full(12, 50.0)
price_bw_a = np.full(12, 80.0); price_bw_p = np.full(12, 80.0)

sales_prod_a = np.random.randint(10000, 20000, 12).astype(float); sales_prod_p = sales_prod_a * 1.1
sales_semi_a = np.random.randint(2000, 5000, 12).astype(float);   sales_semi_p = sales_semi_a * 1.1
sales_md_a = np.random.randint(1000, 3000, 12).astype(float);     sales_md_p = sales_md_a * 1.1
sales_etc_a = np.random.randint(500, 1000, 12).astype(float);     sales_etc_p = sales_etc_a * 1.1
sales_inc_a = np.random.randint(-500, -100, 12).astype(float);    sales_inc_p = sales_inc_a * 1.1

_tmp_sales_a = sales_prod_a + sales_semi_a + sales_md_a + sales_etc_a + sales_inc_a
_tmp_sales_p = sales_prod_p + sales_semi_p + sales_md_p + sales_etc_p + sales_inc_p

_tmp_cogs_a = _tmp_sales_a * np.random.uniform(0.6, 0.7, 12); _tmp_cogs_p = _tmp_sales_p * 0.65
cogs_rm_a = _tmp_cogs_a * 0.55; cogs_rm_p = _tmp_cogs_p * 0.55
cogs_lb_a = _tmp_cogs_a * 0.20; cogs_lb_p = _tmp_cogs_p * 0.20
cogs_os_a = _tmp_cogs_a * 0.15; cogs_os_p = _tmp_cogs_p * 0.15
cogs_oh_a = _tmp_cogs_a * 0.10; cogs_oh_p = _tmp_cogs_p * 0.10

_tmp_sga_a = _tmp_sales_a * np.random.uniform(0.1, 0.15, 12); _tmp_sga_p = _tmp_sales_p * 0.12
sga_salary_a = _tmp_sga_a * 0.42; sga_salary_p = _tmp_sga_p * 0.40
sga_welfare_a = _tmp_sga_a * 0.11; sga_welfare_p = _tmp_sga_p * 0.10
sga_rent_a = _tmp_sga_a * 0.14; sga_rent_p = _tmp_sga_p * 0.15
sga_rnd_a = _tmp_sga_a * 0.18; sga_rnd_p = _tmp_sga_p * 0.20
sga_others_a = _tmp_sga_a * 0.15; sga_others_p = _tmp_sga_p * 0.15

cogs_sw_a = (qty_sw_a*price_sw_a) * np.random.uniform(0.55, 0.65, 12); cogs_sw_p = (qty_sw_p*price_sw_p) * 0.6
cogs_bw_a = (qty_bw_a*price_bw_a) * np.random.uniform(0.6, 0.7, 12);  cogs_bw_p = (qty_bw_p*price_bw_p) * 0.65
sga_sw_a = (qty_sw_a*price_sw_a) * np.random.uniform(0.1, 0.15, 12);   sga_sw_p = (qty_sw_p*price_sw_p) * 0.12
sga_bw_a = (qty_bw_a*price_bw_a) * np.random.uniform(0.1, 0.15, 12);   sga_bw_p = (qty_bw_p*price_bw_p) * 0.12

if plan_file is None and actual_file is None:
    st.sidebar.info("💡 계획 또는 실적 파일을 업로드하시면 해당 데이터가 즉시 연동됩니다.")

# (2) 계획 파일 파싱
if plan_file is not None:
    try:
        df_p = pd.read_excel(plan_file, header=None)
        qty_sw_p = safe_extract('SW수량입력', df_p)
        qty_bw_p = safe_extract('BW수량입력', df_p)
        qty_ls_p = safe_extract('LS수량입력', df_p)
        qty_fs_p = safe_extract('FS수량입력', df_p)
        price_sw_p = safe_extract('SW단가입력', df_p)
        price_bw_p = safe_extract('BW단가입력', df_p)
        
        sales_prod_p = safe_extract('제품매출입력', df_p)
        sales_semi_p = safe_extract('반제품매출입력', df_p)
        sales_md_p = safe_extract('상품매출입력', df_p)
        sales_etc_p = safe_extract('기타매출입력', df_p)
        sales_inc_p = safe_extract('판매장려금입력', df_p)
        
        cogs_rm_p = safe_extract('원부재료비입력', df_p)
        cogs_lb_p = safe_extract('노무비입력', df_p)
        cogs_os_p = safe_extract('외주가공비입력', df_p)
        cogs_oh_p = safe_extract('기타경비입력', df_p)
        
        sga_salary_p = safe_extract('급여입력', df_p)
        sga_welfare_p = safe_extract('복리후생비입력', df_p)
        sga_rent_p = safe_extract('임차료입력', df_p)
        sga_rnd_p = safe_extract('경상개발비입력', df_p)
        sga_others_p = safe_extract('기타판관비입력', df_p)
        
        cogs_sw_p = safe_extract('8인치 SW 매출원가', df_p, (qty_sw_p*price_sw_p)*0.6)
        cogs_bw_p = safe_extract('8인치 BW 매출원가', df_p, (qty_bw_p*price_bw_p)*0.65)
        sga_sw_p = safe_extract('8인치 SW 판관비', df_p, (qty_sw_p*price_sw_p)*0.12)
        sga_bw_p = safe_extract('8인치 BW 판관비', df_p, (qty_bw_p*price_bw_p)*0.12)
    except: st.error("계획 엑셀 파일 형식이 올바르지 않습니다.")

# (3) 실적 파일 파싱
if actual_file is not None:
    try:
        df_a = pd.read_excel(actual_file, header=None)
        qty_sw_a = safe_extract('SW수량입력', df_a)
        qty_bw_a = safe_extract('BW수량입력', df_a)
        qty_ls_a = safe_extract('LS수량입력', df_a)
        qty_fs_a = safe_extract('FS수량입력', df_a)
        price_sw_a = safe_extract('SW단가입력', df_a)
        price_bw_a = safe_extract('BW단가입력', df_a)
        
        sales_prod_a = safe_extract('제품매출입력', df_a)
        sales_semi_a = safe_extract('반제품매출입력', df_a)
        sales_md_a = safe_extract('상품매출입력', df_a)
        sales_etc_a = safe_extract('기타매출입력', df_a)
        sales_inc_a = safe_extract('판매장려금입력', df_a)
        
        cogs_rm_a = safe_extract('원부재료비입력', df_a)
        cogs_lb_a = safe_extract('노무비입력', df_a)
        cogs_os_a = safe_extract('외주가공비입력', df_a)
        cogs_oh_a = safe_extract('기타경비입력', df_a)
        
        sga_salary_a = safe_extract('급여입력', df_a)
        sga_welfare_a = safe_extract('복리후생비입력', df_a)
        sga_rent_a = safe_extract('임차료입력', df_a)
        sga_rnd_a = safe_extract('경상개발비입력', df_a)
        sga_others_a = safe_extract('기타판관비입력', df_a)
        
        cogs_sw_a = safe_extract('8인치 SW 매출원가', df_a, (qty_sw_a*price_sw_a)*0.6)
        cogs_bw_a = safe_extract('8인치 BW 매출원가', df_a, (qty_bw_a*price_bw_a)*0.65)
        sga_sw_a = safe_extract('8인치 SW 판관비', df_a, (qty_sw_a*price_sw_a)*0.12)
        sga_bw_a = safe_extract('8인치 BW 판관비', df_a, (qty_bw_a*price_bw_a)*0.12)
    except: st.error("실적 엑셀 파일 형식이 올바르지 않습니다.")

# --- 4. 전사 파생 변수 최종 연산 ---

# 매출수량 총계 (FS 제외 로직 반영)
qty_total_a = qty_sw_a + qty_bw_a + qty_ls_a
qty_total_p = qty_sw_p + qty_bw_p + qty_ls_p

# 매출액 총계
sales_total_a = sales_prod_a + sales_semi_a + sales_md_a + sales_etc_a + sales_inc_a
sales_total_p = sales_prod_p + sales_semi_p + sales_md_p + sales_etc_p + sales_inc_p

cogs_total_a = cogs_rm_a + cogs_lb_a + cogs_os_a + cogs_oh_a
cogs_total_p = cogs_rm_p + cogs_lb_p + cogs_os_p + cogs_oh_p

sga_total_a = sga_salary_a + sga_welfare_a + sga_rent_a + sga_rnd_a + sga_others_a
sga_total_p = sga_salary_p + sga_welfare_p + sga_rent_p + sga_rnd_p + sga_others_p

gp_total_a = sales_total_a - cogs_total_a; gp_total_p = sales_total_p - cogs_total_p
op_actual = gp_total_a - sga_total_a; op_plan = gp_total_p - sga_total_p

total_sales_actual_sum = sum(sales_total_a)
total_sales_plan_sum = sum(sales_total_p)
sales_achieve_rate = (total_sales_actual_sum / total_sales_plan_sum) * 100 if total_sales_plan_sum else 0

total_op_actual_sum = sum(op_actual)
total_op_plan_sum = sum(op_plan)
op_achieve_rate = (total_op_actual_sum / total_op_plan_sum) * 100 if total_op_plan_sum else 0

with col2: st.metric(label="매출액", value=f"{total_sales_actual_sum:,.0f} 백만원", delta=f"달성률 {sales_achieve_rate:.1f}%", delta_color="normal")
with col3: st.metric(label="영업이익", value=f"{total_op_actual_sum:,.0f} 백만원", delta=f"달성률 {op_achieve_rate:.1f}%", delta_color="normal")

st.markdown("---")

# 5. 차트
st.markdown("##### 📈 월별 영업이익 추이")
fig = go.Figure()
op_margin_actual = np.where(sales_total_a > 0, (op_actual / sales_total_a) * 100, 0)
fig.add_trace(go.Bar(x=months, y=op_plan, name='계획 (Plan)', marker_color='#F3F4F6', yaxis='y1', text=[f"{val:,.0f}" if val!=0 else "" for val in op_plan], textposition='inside', insidetextanchor='end', textfont=dict(size=11, color='#9CA3AF'))) 
fig.add_trace(go.Bar(x=months, y=op_actual, name='실적 (Actual)', marker_color=['#F43F5E' if val >= 0 else '#3B82F6' for val in op_actual], yaxis='y1', text=[f"{val:,.0f}" if val!=0 else "" for val in op_actual], textposition='outside', cliponaxis=False, textfont=dict(size=12, color='black', weight='bold'))) 
fig.add_trace(go.Scatter(x=months, y=op_margin_actual, name='영업이익률(%)', mode='lines+markers+text', text=[f"{val:.1f}%" if val!=0 else "" for val in op_margin_actual], textposition='top center', cliponaxis=False, textfont=dict(size=13, color='#4338CA', weight='bold'), marker=dict(color='white', size=10, line=dict(color='#4338CA', width=2.5)), line=dict(color='#4338CA', width=3, shape='spline'), yaxis='y2'))

max_bar, min_bar = max(max(op_plan), max(op_actual)), min(min(op_plan), min(op_actual))
if max_bar == 0 and min_bar == 0: max_bar = 100
y1_range = [min_bar * 1.5 if min_bar < 0 else -max_bar * 0.1, max_bar * 2.5]
margin_span = max(op_margin_actual) - min(op_margin_actual)
if margin_span == 0: margin_span = 10
y2_range = [min(op_margin_actual) - (margin_span * 2.0), max(op_margin_actual) + (margin_span * 0.2)]

fig.update_layout(barmode='group', margin=dict(l=0, r=0, t=50, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), plot_bgcolor='white', height=450, yaxis=dict(showgrid=True, gridcolor='#F3F4F6', zeroline=True, zerolinecolor='#9CA3AF', zerolinewidth=1, range=y1_range, showticklabels=False), yaxis2=dict(overlaying='y', side='right', showgrid=False, range=y2_range, showticklabels=False))
st.plotly_chart(fig, use_container_width=True)

# 6. 손익계산서 테이블
col_title, col_toggle = st.columns([2, 1])
with col_title: st.markdown("##### 📊 손익계산서")
with col_toggle: view_mode = st.radio("표시 기준 선택", ["실적만 보기", "계획/실적 비교 보기"], horizontal=True, label_visibility="collapsed", key="pnl_toggle")

st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-bottom: 5px;'>(단위: 백만원, pcs, m, %)</div>", unsafe_allow_html=True)

items = [
    '<label for="toggle-sales"><span class="icon-sales"></span> 매출액</label>', 
    '<span class="child-sales"> - 제품</span>', 
    '<span class="child-sales"> - 반제품</span>', 
    '<span class="child-sales"> - 상품</span>', 
    '<span class="child-sales"> - 기타</span>', 
    '<span class="child-sales"> - 판매장려금</span>',
    '<label for="toggle-qty"><span class="icon-qty"></span> 매출수량</label>', 
    '<span class="child-qty"> - 8인치 SW</span>', 
    '<span class="child-qty"> - 8인치 BW</span>', 
    '<span class="child-qty"> - LS</span>', 
    '<span class="child-qty"> - FS</span>',
    '매출원가', '매출원가율', '매출총이익', '매출총이익률', '판관비', '영업이익', '영업이익률'
]

cogs_ratio_a = np.where(sales_total_a > 0, (cogs_total_a / sales_total_a) * 100, 0)
cogs_ratio_p = np.where(sales_total_p > 0, (cogs_total_p / sales_total_p) * 100, 0)

actual_rows = [
    sales_total_a, sales_prod_a, sales_semi_a, sales_md_a, sales_etc_a, sales_inc_a, 
    qty_total_a, qty_sw_a, qty_bw_a, qty_ls_a, qty_fs_a, 
    cogs_total_a, cogs_ratio_a, gp_total_a, (gp_total_a/sales_total_a)*100 if sum(sales_total_a) else np.zeros(12), 
    sga_total_a, op_actual, (op_actual/sales_total_a)*100 if sum(sales_total_a) else np.zeros(12)
]
plan_rows = [
    sales_total_p, sales_prod_p, sales_semi_p, sales_md_p, sales_etc_p, sales_inc_p, 
    qty_total_p, qty_sw_p, qty_bw_p, qty_ls_p, qty_fs_p, 
    cogs_total_p, cogs_ratio_p, gp_total_p, (gp_total_p/sales_total_p)*100 if sum(sales_total_p) else np.zeros(12), 
    sga_total_p, op_plan, (op_plan/sales_total_p)*100 if sum(sales_total_p) else np.zeros(12)
]

actual_sums = [sum(row) for row in actual_rows]
plan_sums = [sum(row) for row in plan_rows]
idx_sales, idx_cogs, idx_gp, idx_op = 0, 11, 13, 16

actual_sums[12] = (actual_sums[idx_cogs] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] else 0
actual_sums[14] = (actual_sums[idx_gp] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] else 0
actual_sums[17] = (actual_sums[idx_op] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] else 0
plan_sums[12] = (plan_sums[idx_cogs] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] else 0
plan_sums[14] = (plan_sums[idx_gp] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] else 0
plan_sums[17] = (plan_sums[idx_op] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] else 0

def format_cell(val, is_margin):
    if val == 0: return ""
    if is_margin: return f"{val:.1f}%"
    return f"{val:,.0f}"

if view_mode == "실적만 보기":
    df_table = pd.DataFrame({'항목': items})
    for i, month in enumerate(months): df_table[month] = [row[i] for row in actual_rows]
    df_table['합계'] = actual_sums
    for col in df_table.columns:
        if col != '항목': df_table[col] = df_table.apply(lambda row: format_cell(row[col], '율' in str(row['항목']) or '률' in str(row['항목'])), axis=1)
    render_pnl_table(df_table)
else:
    tuples = [('항목', '')]
    for m in months: tuples.extend([(m, '계획'), (m, '실적')])
    tuples.extend([('합계', '계획'), ('합계', '실적')])
    c_rows = []
    for i, item in enumerate(items):
        r_data = [item]
        for m_idx in range(12): r_data.extend([plan_rows[i][m_idx], actual_rows[i][m_idx]])
        r_data.extend([plan_sums[i], actual_sums[i]])
        c_rows.append(r_data)
    df_table = pd.DataFrame(c_rows, columns=pd.MultiIndex.from_tuples(tuples))
    for col in df_table.columns:
        if col != ('항목', ''): df_table[col] = df_table.apply(lambda row: format_cell(row[col], '율' in str(row[('항목', '')]) or '률' in str(row[('항목', '')])), axis=1)
    render_pnl_table(df_table)


# 7. 매출원가 명세서
st.markdown("---")
st.markdown("##### 🔍 매출원가 명세서")
st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-bottom: 5px;'>(단위: 백만원, %)</div>", unsafe_allow_html=True)
cogs_items = ['원부재료', '노무비', '외주가공비', '기타경비', '매출원가 총계']
cogs_rows_a = [cogs_rm_a, cogs_lb_a, cogs_os_a, cogs_oh_a, cogs_total_a]
cogs_sums_a = [sum(row) for row in cogs_rows_a]
sales_total_sum_a = sum(sales_total_a)
tuples_cogs = [('항목', '')]
for m in months: tuples_cogs.extend([(m, '실적금액'), (m, '매출비율')])
tuples_cogs.extend([('합계', '실적금액'), ('합계', '매출비율')])
combined_rows_cogs = []
for i, item in enumerate(cogs_items):
    row_data = [item]
    for m_idx in range(12):
        amt = cogs_rows_a[i][m_idx]
        ratio = (amt / sales_total_a[m_idx]) * 100 if sales_total_a[m_idx] else 0
        row_data.extend([amt, f"{ratio:.1f}%" if amt != 0 else ""])
    sum_amt = cogs_sums_a[i]
    sum_ratio = (sum_amt / sales_total_sum_a) * 100 if sales_total_sum_a else 0
    row_data.extend([sum_amt, f"{sum_ratio:.1f}%" if sum_amt != 0 else ""])
    combined_rows_cogs.append(row_data)
df_cogs = pd.DataFrame(combined_rows_cogs, columns=pd.MultiIndex.from_tuples(tuples_cogs))
for col in df_cogs.columns:
    if col[1] == '실적금액': df_cogs[col] = df_cogs[col].apply(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and x != 0 else ("" if x == 0 else x))
render_html_table(df_cogs)
st.markdown("<br>", unsafe_allow_html=True)


# 8. 판매관리비 명세서
st.markdown("---")
col_title_sga, col_toggle_sga = st.columns([2, 1])
with col_title_sga: st.markdown("##### 🔍 판매관리비 명세서")
with col_toggle_sga: view_mode_sga = st.radio("판관비 표시 기준 선택", ["실적만 보기", "계획/실적 비교 보기"], horizontal=True, label_visibility="collapsed", key="sga_toggle")
st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-bottom: 5px;'>(단위: 백만원)</div>", unsafe_allow_html=True)

sga_items = ['급여', '복리후생비', '임차료', '경상연구개발비', '기타판관비', '판관비 총계']
sga_actual_rows = [sga_salary_a, sga_welfare_a, sga_rent_a, sga_rnd_a, sga_others_a, sga_total_a]
sga_plan_rows = [sga_salary_p, sga_welfare_p, sga_rent_p, sga_rnd_p, sga_others_p, sga_total_p]
sga_actual_sums = [sum(row) for row in sga_actual_rows]
sga_plan_sums = [sum(row) for row in sga_plan_rows]

if view_mode_sga == "실적만 보기":
    df_sga = pd.DataFrame({'항목': sga_items})
    for i, month in enumerate(months): df_sga[month] = [row[i] for row in sga_actual_rows]
    df_sga['합계'] = sga_actual_sums
    for col in df_sga.columns:
        if col != '항목': df_sga[col] = df_sga[col].apply(lambda x: f"{x:,.0f}" if x != 0 else "")
    render_html_table(df_sga)
else:
    tuples_sga = [('항목', '')]
    for m in months:
        tuples_sga.extend([(m, '계획'), (m, '실적')])
    tuples_sga.extend([('합계', '계획'), ('합계', '실적')])
    combined_rows_sga = []
    for i, item in enumerate(sga_items):
        row_data = [item]
        for m_idx in range(12): r_data.extend([sga_plan_rows[i][m_idx], sga_actual_rows[i][m_idx]])
        row_data.extend([sga_plan_sums[i], sga_actual_sums[i]])
        combined_rows_sga.append(row_data)
    df_sga_comp = pd.DataFrame(combined_rows_sga, columns=pd.MultiIndex.from_tuples(tuples_sga))
    for col in df_sga_comp.columns:
        if col != ('항목', ''): df_sga_comp[col] = df_sga_comp[col].apply(lambda x: f"{x:,.0f}" if x != 0 else "")
    render_html_table(df_sga_comp)


# 9. Item별 구분손익
st.markdown("---")
col_title_type, col_toggle_type = st.columns([2, 1])
with col_title_type: st.markdown("##### 🔍 Item별 구분손익")
with col_toggle_type: view_mode_type = st.radio("구분손익 표시 기준 선택", ["실적만 보기", "계획/실적 비교 보기"], horizontal=True, label_visibility="collapsed", key="type_toggle")
st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-bottom: 5px;'>(단위: 백만원, pcs, 원, %)</div>", unsafe_allow_html=True)

def build_type_pnl(qty_a, qty_p, price_a, price_p, cogs_a, cogs_p, sga_a, sga_p):
    sales_a = qty_a * price_a
    sales_p = qty_p * price_p
    
    gp_a, gp_p = sales_a - cogs_a, sales_p - cogs_p
    op_a, op_p = gp_a - sga_a, gp_p - sga_p
    
    cr_a = np.where(sales_a > 0, (cogs_a / sales_a) * 100, 0)
    cr_p = np.where(sales_p > 0, (cogs_p / sales_p) * 100, 0)
    gpr_a = np.where(sales_a > 0, (gp_a / sales_a) * 100, 0)
    gpr_p = np.where(sales_p > 0, (gp_p / sales_p) * 100, 0)
    opr_a = np.where(sales_a > 0, (op_a / sales_a) * 100, 0)
    opr_p = np.where(sales_p > 0, (op_p / sales_p) * 100, 0)

    rows_a = [sales_a, qty_a, price_a, cogs_a, cr_a, gp_a, gpr_a, sga_a, op_a, opr_a]
    rows_p = [sales_p, qty_p, price_p, cogs_p, cr_p, gp_p, gpr_p, sga_p, op_p, opr_p]

    s_sales_a, s_sales_p = sum(sales_a), sum(sales_p)
    avg_price_a = s_sales_a / sum(qty_a) if sum(qty_a) else 0
    avg_price_p = s_sales_p / sum(qty_p) if sum(qty_p) else 0
    
    sums_a = [s_sales_a, sum(qty_a), avg_price_a, sum(cogs_a), (sum(cogs_a)/s_sales_a*100) if s_sales_a else 0, sum(gp_a), (sum(gp_a)/s_sales_a*100) if s_sales_a else 0, sum(sga_a), sum(op_a), (sum(op_a)/s_sales_a*100) if s_sales_a else 0]
    sums_p = [s_sales_p, sum(qty_p), avg_price_p, sum(cogs_p), (sum(cogs_p)/s_sales_p*100) if s_sales_p else 0, sum(gp_p), (sum(gp_p)/s_sales_p*100) if s_sales_p else 0, sum(sga_p), sum(op_p), (sum(op_p)/s_sales_p*100) if s_sales_p else 0]
    return rows_a, sums_a, rows_p, sums_p

type_items = ['매출액', '매출수량(pcs)', '단가(원)', '매출원가', '매출원가율', '매출총이익', '매출총이익률', '판관비', '영업이익', '영업이익률']

sw_rows_a, sw_sums_a, sw_rows_p, sw_sums_p = build_type_pnl(qty_sw_a, qty_sw_p, price_sw_a, price_sw_p, cogs_sw_a, cogs_sw_p, sga_sw_a, sga_sw_p)
bw_rows_a, bw_sums_a, bw_rows_p, bw_sums_p = build_type_pnl(qty_bw_a, qty_bw_p, price_bw_a, price_bw_p, cogs_bw_a, cogs_bw_p, sga_bw_a, sga_bw_p)

def render_type_table(rows_a, sums_a, rows_p, sums_p, view_mode):
    if view_mode == "실적만 보기":
        df = pd.DataFrame({'항목': type_items})
        for i, m in enumerate(months): df[m] = [r[i] for r in rows_a]
        df['합계'] = sums_a
        for col in df.columns:
            if col != '항목': df[col] = df.apply(lambda row: format_cell(row[col], '율' in str(row['항목']) or '률' in str(row['항목'])), axis=1)
        render_html_table(df)
    else:
        tuples = [('항목', '')]
        for m in months: tuples.extend([(m, '계획'), (m, '실적')])
        tuples.extend([('합계', '계획'), ('합계', '실적')])
        c_rows = []
        for i, item in enumerate(type_items):
            r_data = [item]
            for m_idx in range(12): r_data.extend([rows_p[i][m_idx], rows_a[i][m_idx]])
            r_data.extend([sums_p[i], sums_a[i]])
            c_rows.append(r_data)
        df = pd.DataFrame(c_rows, columns=pd.MultiIndex.from_tuples(tuples))
        for col in df.columns:
            if col != ('항목', ''): df[col] = df.apply(lambda row: format_cell(row[col], '율' in str(row[('항목', '')]) or '률' in str(row[('항목', '')])), axis=1)
        render_html_table(df)

tab1, tab2 = st.tabs(["8인치 SW", "8인치 BW"])
with tab1: st.markdown("**■ 8인치 SW 손익 명세**"); render_type_table(sw_rows_a, sw_sums_a, sw_rows_p, sw_sums_p, view_mode_type)
with tab2: st.markdown("**■ 8인치 BW 손익 명세**"); render_type_table(bw_rows_a, bw_sums_a, bw_rows_p, bw_sums_p, view_mode_type)