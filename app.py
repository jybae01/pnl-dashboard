import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import re
import os

# 1. 페이지 기본 설정 (반드시 최상단에 위치)
st.set_page_config(page_title="월별 손익계산서 분석표", layout="wide")

# --- [보안] 관리자 및 조회자 이중 인증 로직 ---
try:
    VIEWER_CODE = st.secrets["VIEWER_CODE"]   
    ADMIN_CODE = st.secrets["ADMIN_CODE"]     
except Exception:
    VIEWER_CODE = "2026!"
    ADMIN_CODE = "admin!"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.role = None

if not st.session_state.authenticated:
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 15% 20%, rgba(59,130,246,.12), transparent 30%),
            radial-gradient(circle at 85% 82%, rgba(16,185,129,.10), transparent 32%),
            #F8FAFC;
    }
    [data-testid="stHeader"] { background: transparent; }
    .login-hero { text-align: center; margin: 15vh 0 22px; }
    .login-mark {
        display: inline-flex; align-items: center; justify-content: center;
        width: 48px; height: 48px; border-radius: 14px; margin-bottom: 12px;
        background: linear-gradient(135deg, #2563EB, #0F766E);
        color: white; font-size: 23px; box-shadow: 0 10px 22px rgba(37,99,235,.22);
    }
    .login-hero h1 { margin: 0; color: #172033; font-size: 27px; letter-spacing: -.6px; }
    .login-hero p { margin: 8px 0 0; color: #64748B; font-size: 14px; }
    div[data-testid="stForm"] {
        max-width: 380px; margin: 0 auto; padding: 24px 24px 20px;
        border: 1px solid #E2E8F0; border-radius: 16px; background: rgba(255,255,255,.94);
        box-shadow: 0 18px 42px rgba(15,23,42,.10);
    }
    div[data-testid="stForm"] input {
        height: 44px; border-radius: 9px; border-color: #CBD5E1; font-size: 14px;
    }
    div[data-testid="stForm"] input:focus { border-color: #2563EB; box-shadow: 0 0 0 3px rgba(37,99,235,.12); }
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stForm"] button[kind="secondaryFormSubmit"] {
        height: 42px; border: 0; border-radius: 9px; background: #2563EB; color: white;
        font-weight: 700; letter-spacing: -.1px;
    }
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button:hover,
    div[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover { background: #1D4ED8; }
    .login-help { text-align: center; color: #94A3B8; font-size: 12px; margin-top: 14px; }
    </style>
    <div class="login-hero">
        <div class="login-mark">▦</div>
        <h1>손익 데이터 모니터링</h1>
        <p>접속 코드를 입력하여 대시보드를 확인하세요.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            entered_code = st.text_input("Access Code", type="password", label_visibility="collapsed", placeholder="접속 코드를 입력하세요")
            submitted = st.form_submit_button("접속", use_container_width=True)
            
            if submitted:
                if entered_code == VIEWER_CODE:
                    st.session_state.authenticated = True
                    st.session_state.role = "viewer"
                    st.rerun()
                elif entered_code == ADMIN_CODE:
                    st.session_state.authenticated = True
                    st.session_state.role = "admin"
                    st.rerun()
                else:
                    st.error("⚠️ 접속 코드가 일치하지 않습니다.")
        st.markdown("<div class='login-help'>권한이 필요한 경우 관리자에게 문의해 주세요.</div>", unsafe_allow_html=True)
    
    st.stop()
# ---------------------------------------------


# [HTML/CSS] 디자인 최적화 (라디오버튼 강제 중앙정렬 & YTD 표 자연스러운 간격 복구)
st.markdown("""
<style>
/* 💡 라디오 버튼 그룹 강제 중앙 정렬 */
div[role="radiogroup"] {
    display: flex !important;
    justify-content: center !important;
    margin-bottom: 5px !important;
}

/* 💡 드롭다운 사이즈 최소화 및 여백 제거 */
div[data-baseweb="select"] {
    font-size: 13px !important;
}
div[data-baseweb="select"] div[role="combobox"] {
    justify-content: center !important;
}
div[data-baseweb="select"] div[role="combobox"] input {
    text-align: center !important;
}

.custom-tbl { 
    width: 100%; min-width: 1100px; border-collapse: collapse; font-size: 13px; 
    font-family: "Pretendard", "Malgun Gothic", sans-serif; margin-bottom: 20px; 
    table-layout: fixed; 
}
.custom-tbl.compare-mode {
    min-width: 1900px; 
}
.ytd-wrapper { 
    display: flex; justify-content: center; width: 100%; overflow-x: auto; 
}

/* 💡 YTD 전용 테이블: 보기 좋은 간격(600px)으로 콤팩트하게 복구 */
.custom-tbl.ytd-mode {
    width: 600px !important; 
    min-width: 600px !important;
    max-width: 600px !important;
    margin: 0 auto;
}
.custom-tbl.ytd-mode td, .custom-tbl.ytd-mode th {
    padding: 6px 8px !important; 
}

.custom-tbl th { 
    text-align: center !important; padding: 10px 4px; border: 1px solid rgba(128, 128, 128, 0.2); 
    background-color: rgba(128, 128, 128, 0.05); color: inherit; white-space: nowrap; vertical-align: middle;
}
.custom-tbl td { 
    text-align: right !important; padding: 8px 10px; border: 1px solid rgba(128, 128, 128, 0.2); 
    white-space: nowrap; 
}
.custom-tbl.ytd-mode thead th {
    text-align: center !important;
}
.custom-tbl tbody td:first-child, .custom-tbl thead th.col-item { 
    width: 140px; text-align: left !important; font-weight: bold; 
    background-color: rgba(128, 128, 128, 0.02); padding-left: 10px; 
}

.pnl-container tr:has(.child-qty) { display: none; }
.pnl-container tr:has(.child-sales) { display: none; }
.pnl-container tr:has(.child-cogs) { display: none; }

#toggle-qty:checked ~ table tr:has(.child-qty) { display: table-row; }
#toggle-sales:checked ~ table tr:has(.child-sales) { display: table-row; }
#toggle-cogs:checked ~ table tr:has(.child-cogs) { display: table-row; }

.icon-qty::before, .icon-sales::before, .icon-cogs::before { content: "[+]"; color: #3B82F6; font-weight: 900; margin-right: 6px; display: inline-block; width: 18px; }
#toggle-qty:checked ~ table .icon-qty::before { content: "[-]"; color: #EF4444; }
#toggle-sales:checked ~ table .icon-sales::before { content: "[-]"; color: #EF4444; }
#toggle-cogs:checked ~ table .icon-cogs::before { content: "[-]"; color: #EF4444; }

label[for="toggle-qty"], label[for="toggle-sales"], label[for="toggle-cogs"] { cursor: pointer; margin: 0; display: block; width: 100%; }
</style>
""", unsafe_allow_html=True)

def format_cell(val, is_margin):
    if pd.isna(val) or val == 0 or np.isinf(val): 
        return ""
    if is_margin: 
        return f"{val:.1f}%"
    return f"{val:,.0f}"

def clean_multiindex_html(html, is_multi=False):
    if is_multi:
        if '<th>항목</th>' in html:
            html = html.replace('<th>항목</th>', '<th class="col-item" rowspan="2" style="vertical-align: middle; border-bottom: 1px solid rgba(128,128,128,0.2);">항목</th>', 1)
            html = re.sub(r'<th[^>]*>(?:&nbsp;|\s*)</th>', '', html, count=1)
            html = re.sub(r'<th[^>]*>Unnamed[^<]*</th>', '', html)
    else:
        html = html.replace('<th>항목</th>', '<th class="col-item">항목</th>')
    return html

def render_html_table(df, mode=""):
    mode_class = " compare-mode" if mode == "compare" else (" ytd-mode" if mode == "ytd" else "")
    html = df.to_html(index=False, classes=f"custom-tbl{mode_class}", escape=False)
    html = clean_multiindex_html(html, mode in ["compare", "ytd"])
    html = html.replace("\n", "").replace("\r", "")
    wrapper_class = "ytd-wrapper" if mode == "ytd" else ""
    wrapper = f'<div class="{wrapper_class}" style="width:100%; overflow-x:auto;">{html}</div>'
    st.markdown(wrapper, unsafe_allow_html=True)

def render_pnl_table(df, mode=""):
    mode_class = " compare-mode" if mode == "compare" else (" ytd-mode" if mode == "ytd" else "")
    html = df.to_html(index=False, classes=f"custom-tbl{mode_class}", escape=False)
    html = clean_multiindex_html(html, mode in ["compare", "ytd"])
    html = html.replace("\n", "").replace("\r", "")
    wrapper_class = "pnl-container ytd-wrapper" if mode == "ytd" else "pnl-container"
    wrapper = f'<div class="{wrapper_class}" style="width:100%; overflow-x:auto;"><input type="checkbox" id="toggle-qty" style="display:none;"><input type="checkbox" id="toggle-sales" style="display:none;"><input type="checkbox" id="toggle-cogs" style="display:none;">{html}</div>'
    st.markdown(wrapper, unsafe_allow_html=True)

def render_table_unit(unit_text, is_period_compare=False):
    """표 폭에 맞춰 단위 표기를 배치한다."""
    if is_period_compare:
        style = "width: 600px; margin: 0 auto 5px auto; text-align: right;"
    else:
        style = "width: 100%; margin-bottom: 5px; text-align: right;"
    st.markdown(
        f"<div style='{style} font-size: 12px; font-weight: bold; color: #4B5563;'>{unit_text}</div>",
        unsafe_allow_html=True,
    )

def render_centered_period_selectors(months, start_key, end_key):
    """기간 비교용 선택기를 중앙의 표 바로 위에 배치한다."""
    # 중앙 열 안에서 문구와 선택 상자를 한 그룹으로 배치해 표 중심과 맞춘다.
    # 오른쪽 여백을 더 주어 설정 그룹을 눈에 띄게 왼쪽으로 이동한다.
    _, selector_area, _ = st.columns([0.7, 1, 1.3], gap="small")
    with selector_area:
        selector_cols = st.columns([1.4, 0.75, 0.15, 0.75], gap="small")
    with selector_cols[0]:
        st.markdown("<div style='text-align: right; font-weight: 600; margin-top: 7px; white-space: nowrap; transform: translateX(-18px);'>기간 설정 :</div>", unsafe_allow_html=True)
    with selector_cols[1]:
        start_month = st.selectbox("시작", months, index=0, key=start_key, label_visibility="collapsed")
    with selector_cols[2]:
        st.markdown("<div style='text-align: center; font-weight: bold; margin-top: 5px; font-size: 16px; color: #4B5563;'>~</div>", unsafe_allow_html=True)
    with selector_cols[3]:
        end_month = st.selectbox("종료", months, index=0, key=end_key, label_visibility="collapsed")
    return start_month, end_month

months = [f"{i}월" for i in range(1, 13)]

# --- 사이드바 (관리자 전용 데이터 업로드 및 양식 다운로드) ---
if st.session_state.role == "admin":
    st.sidebar.markdown("### 📁 데이터 연동 관리 (Admin)")
    
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
        ('Ⅱ.매출원가', '1.제품 원가(투입)', '원부재료', '원부재료비입력'),
        ('Ⅱ.매출원가', '1.제품 원가(투입)', '노무비', '노무비입력'),
        ('Ⅱ.매출원가', '1.제품 원가(투입)', '외주가공비', '외주가공비입력'),
        ('Ⅱ.매출원가', '1.제품 원가(투입)', '기타경비', '기타경비입력'),
        ('Ⅱ.매출원가', '2.반제품 원가(투입)', '원부재료', '반제품_원부재료비입력'),
        ('Ⅱ.매출원가', '2.반제품 원가(투입)', '노무비', '반제품_노무비입력'),
        ('Ⅱ.매출원가', '2.반제품 원가(투입)', '외주가공비', '반제품_외주가공비입력'),
        ('Ⅱ.매출원가', '2.반제품 원가(투입)', '기타경비', '반제품_기타경비입력'),
        ('Ⅱ.매출원가', '3.반제품 매출원가(총액)', '금액(천원)', '반제품매출원가입력'),
        ('Ⅱ.매출원가', '4.상품 매출원가', '금액(천원)', '상품매출원가입력'),
        ('Ⅱ.매출원가', '5.기타 매출원가', '금액(천원)', '기타매출원가입력'),
        ('Ⅱ.매출원가', '6.표준 매출원가 차이', '금액(천원)', '표준원가차이입력'),
        ('Ⅱ.매출원가', '7.재고자산 평가손실', '금액(천원)', '재고평가손입력'),
        ('Ⅲ.매출총이익', '1.매출총이익', '금액(천원)', '매출총이익입력'), 
        ('Ⅳ.판매관리비', '1.일반관리비', '인건비', '일반관리비_인건비입력'),
        ('Ⅳ.판매관리비', '1.일반관리비', '감가상각비', '일반관리비_감가상각비입력'),
        ('Ⅳ.판매관리비', '1.일반관리비', '경상개발비', '일반관리비_경상개발비입력'),
        ('Ⅳ.판매관리비', '1.일반관리비', '수수료', '일반관리비_수수료입력'),
        ('Ⅳ.판매관리비', '1.일반관리비', '기타', '일반관리비_기타입력'),
        ('Ⅳ.판매관리비', '2.판매비', '운반비', '판매비_운반비입력'),
        ('Ⅳ.판매관리비', '2.판매비', '수수료', '판매비_수수료입력'),
        ('Ⅳ.판매관리비', '2.판매비', '브랜드사용료', '판매비_브랜드사용료입력'),
        ('Ⅳ.판매관리비', '2.판매비', '인건비', '판매비_인건비입력'),
        ('Ⅳ.판매관리비', '2.판매비', '견본비', '판매비_견본비입력'),
        ('Ⅳ.판매관리비', '2.판매비', '대손상각', '판매비_대손상각입력'),
        ('Ⅳ.판매관리비', '2.판매비', '잡비', '판매비_잡비입력'),
        ('Ⅳ.판매관리비', '2.판매비', '기타', '판매비_기타입력'),
        ('Ⅴ.영업이익', '1.영업이익', '금액(천원)', '영업이익입력'),
        ('Ⅴ.영업이익', '2.조정 영업이익', '금액(천원)', '조정영업이익입력'),
        ('참고데이터', 'Item별 원가', '8인치 SW', '8인치 SW 매출원가'),
        ('참고데이터', 'Item별 원가', '8인치 BW', '8인치 BW 매출원가'),
        ('참고데이터', 'Item별 판관비', '8인치 SW', '8인치 SW 판관비'),
        ('참고데이터', 'Item별 판관비', '8인치 BW', '8인치 BW 판관비'),
    ]

    tpl_rows = []
    for row in original_format_items:
        if row[0] == '★손익계산서':
            tpl_rows.append(['구분', '입력 항목', '입력 키'] + months)
        else:
            tpl_rows.append([row[0], f'{row[1]} · {row[2]}', row[3]] + [None]*12)

    df_template = pd.DataFrame(tpl_rows)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, header=False, sheet_name='Sheet1')
        try:
            from openpyxl.styles import PatternFill, Font
            worksheet = writer.sheets['Sheet1']
            for col, width in zip(['A','B','C'], [18, 28, 22]): worksheet.column_dimensions[col].width = width
            for col in range(4, 16): worksheet.column_dimensions[worksheet.cell(row=1, column=col).column_letter].width = 12
            header_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
            for cell in worksheet[1]: cell.fill = header_fill; cell.font = Font(bold=True)
            worksheet.freeze_panes = 'D2'
        except: pass

    st.sidebar.download_button(
        label="📥 엑셀 양식 다운로드",
        data=buffer.getvalue(),
        file_name="손익계산서_입력양식.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.sidebar.markdown("---")
    plan_file = st.sidebar.file_uploader("📤 1. 계획(Plan) 업로드", type=['xlsx'])
    actual_file = st.sidebar.file_uploader("📤 2. 실적(Actual) 업로드", type=['xlsx'])

    if plan_file is not None:
        with open("saved_plan.xlsx", "wb") as f:
            f.write(plan_file.getbuffer())
        st.sidebar.success("✅ 계획 데이터가 서버에 배포되었습니다.")

    if actual_file is not None:
        with open("saved_actual.xlsx", "wb") as f:
            f.write(actual_file.getbuffer())
        st.sidebar.success("✅ 실적 데이터가 서버에 배포되었습니다.")

    if st.sidebar.button("🗑️ 서버 데이터 초기화 (더미로 복구)"):
        if os.path.exists("saved_plan.xlsx"): os.remove("saved_plan.xlsx")
        if os.path.exists("saved_actual.xlsx"): os.remove("saved_actual.xlsx")
        st.rerun()

# --- 상단 헤더 및 연도 선택 ---
st.title("손익계산서 조회") 

available_years = ["2026년"]
if os.path.exists("saved_plan_2025.xlsx") or os.path.exists("saved_actual_2025.xlsx"):
    available_years.append("2025년")

col1, col2, col3, col4 = st.columns(4)
with col1:
    inner_col1, inner_col2 = st.columns([1, 1])
    with inner_col1: selected_year = st.selectbox("연도", available_years)

# --- 데이터 파싱 로직 ---
def extract_series(keyword, df_data):
    # 간소화 양식(A~C 정보 열)과 기존 양식(A~D 정보 열)을 모두 지원한다.
    col_start = 4 if df_data.shape[1] >= 16 else 3
    for idx, row in df_data.iterrows():
        if keyword in str(row[2]) or keyword in str(row[3]):
            return pd.to_numeric(row[col_start:col_start+12], errors='coerce').fillna(0).values
    return None

def safe_extract(keyword, df_data, unit='money', default_val=None):
    res = extract_series(keyword, df_data)
    if res is not None:
        if unit == 'money': return res / 1000000.0
        return res
    if default_val is not None:
        return default_val
    return np.zeros(12)

# (1) 샘플 더미 데이터 세팅 
np.random.seed(42)
qty_sw_a = np.random.randint(15000, 30000, 12); qty_sw_p = qty_sw_a * np.random.uniform(0.9, 1.2, 12)
qty_bw_a = np.random.randint(10000, 20000, 12); qty_bw_p = qty_bw_a * np.random.uniform(0.9, 1.2, 12)
qty_ls_a = np.random.randint(5000, 10000, 12);  qty_ls_p = qty_ls_a * np.random.uniform(0.9, 1.2, 12)
qty_fs_a = np.random.randint(2000, 5000, 12);   qty_fs_p = qty_fs_a * np.random.uniform(0.9, 1.2, 12)

price_sw_a = np.full(12, 55000.0); price_sw_p = np.full(12, 55000.0)
price_bw_a = np.full(12, 85000.0); price_bw_p = np.full(12, 85000.0)

sales_prod_a = np.random.randint(3000, 5000, 12).astype(float); sales_prod_p = sales_prod_a * 1.1
sales_semi_a = np.random.randint(1000, 2000, 12).astype(float); sales_semi_p = sales_semi_a * 1.1
sales_md_a = np.random.randint(500, 1000, 12).astype(float);    sales_md_p = sales_md_a * 1.1
sales_etc_a = np.random.randint(100, 300, 12).astype(float);    sales_etc_p = sales_etc_a * 1.1
sales_inc_a = np.random.randint(-100, -50, 12).astype(float);   sales_inc_p = sales_inc_a * 1.1

_tmp_sales_a = sales_prod_a + sales_semi_a + sales_md_a + sales_etc_a + sales_inc_a
_tmp_sales_p = sales_prod_p + sales_semi_p + sales_md_p + sales_etc_p + sales_inc_p

_tmp_cogs_a = _tmp_sales_a * np.random.uniform(0.6, 0.7, 12); _tmp_cogs_p = _tmp_sales_p * 0.65

cogs_semi_a = _tmp_cogs_a * 0.10; cogs_semi_p = _tmp_cogs_p * 0.10
cogs_md_a = _tmp_cogs_a * 0.05; cogs_md_p = _tmp_cogs_p * 0.05
cogs_etc_a = _tmp_cogs_a * 0.02; cogs_etc_p = _tmp_cogs_p * 0.02
cogs_std_a = np.zeros(12); cogs_std_p = np.zeros(12)
cogs_inv_a = np.zeros(12); cogs_inv_p = np.zeros(12)

_dummy_cogs_prod_a = _tmp_cogs_a - (cogs_semi_a + cogs_md_a + cogs_etc_a + cogs_std_a + cogs_inv_a)
_dummy_cogs_prod_p = _tmp_cogs_p - (cogs_semi_p + cogs_md_p + cogs_etc_p + cogs_std_p + cogs_inv_p)

# 제품 더미 데이터
cogs_rm_a = _dummy_cogs_prod_a * 0.60; cogs_rm_p = _dummy_cogs_prod_p * 0.60
cogs_lb_a = _dummy_cogs_prod_a * 0.20; cogs_lb_p = _dummy_cogs_prod_p * 0.20
cogs_os_a = _dummy_cogs_prod_a * 0.15; cogs_os_p = _dummy_cogs_prod_p * 0.15
cogs_oh_a = _dummy_cogs_prod_a - cogs_rm_a - cogs_lb_a - cogs_os_a
cogs_oh_p = _dummy_cogs_prod_p - cogs_rm_p - cogs_lb_p - cogs_os_p

# 반제품 더미 데이터
cogs_semi_rm_a = cogs_semi_a * 0.60; cogs_semi_rm_p = cogs_semi_p * 0.60
cogs_semi_lb_a = cogs_semi_a * 0.20; cogs_semi_lb_p = cogs_semi_p * 0.20
cogs_semi_os_a = cogs_semi_a * 0.15; cogs_semi_os_p = cogs_semi_p * 0.15
cogs_semi_oh_a = cogs_semi_a - cogs_semi_rm_a - cogs_semi_lb_a - cogs_semi_os_a
cogs_semi_oh_p = cogs_semi_p - cogs_semi_rm_p - cogs_semi_lb_p - cogs_semi_os_p

_tmp_sga_a = _tmp_sales_a * np.random.uniform(0.1, 0.15, 12); _tmp_sga_p = _tmp_sales_p * 0.12

_tmp_adm_a = _tmp_sga_a * 0.5; _tmp_adm_p = _tmp_sga_p * 0.5
adm_labor_a = _tmp_adm_a * 0.4; adm_labor_p = _tmp_adm_p * 0.4
adm_depr_a = _tmp_adm_a * 0.15; adm_depr_p = _tmp_adm_p * 0.15
adm_rnd_a = _tmp_adm_a * 0.2; adm_rnd_p = _tmp_adm_p * 0.2
adm_fee_a = _tmp_adm_a * 0.15; adm_fee_p = _tmp_adm_p * 0.15
adm_etc_a = _tmp_adm_a * 0.1; adm_etc_p = _tmp_adm_p * 0.1

_tmp_sel_a = _tmp_sga_a * 0.5; _tmp_sel_p = _tmp_sga_p * 0.5
sel_trans_a = _tmp_sel_a * 0.2; sel_trans_p = _tmp_sel_p * 0.2
sel_fee_a = _tmp_sel_a * 0.15; sel_fee_p = _tmp_sel_p * 0.15
sel_brand_a = _tmp_sel_a * 0.1; sel_brand_p = _tmp_sel_p * 0.1
sel_labor_a = _tmp_sel_a * 0.25; sel_labor_p = _tmp_sel_p * 0.25
sel_sample_a = _tmp_sel_a * 0.1; sel_sample_p = _tmp_sel_p * 0.1
sel_bad_a = _tmp_sel_a * 0.05; sel_bad_p = _tmp_sel_p * 0.05
sel_misc_a = _tmp_sel_a * 0.05; sel_misc_p = _tmp_sel_p * 0.05
sel_etc_a = _tmp_sel_a * 0.1; sel_etc_p = _tmp_sel_p * 0.1

gp_input_a = _tmp_sales_a - _tmp_cogs_a
gp_input_p = _tmp_sales_p - _tmp_cogs_p
op_input_a = gp_input_a - _tmp_sga_a
op_input_p = gp_input_p - _tmp_sga_p
adj_op_input_a = op_input_a + adm_depr_a
adj_op_input_p = op_input_p + adm_depr_p

cogs_sw_a = ((qty_sw_a*price_sw_a)/1000000.0) * np.random.uniform(0.55, 0.65, 12); cogs_sw_p = ((qty_sw_p*price_sw_p)/1000000.0) * 0.6
cogs_bw_a = ((qty_bw_a*price_bw_a)/1000000.0) * np.random.uniform(0.6, 0.7, 12);  cogs_bw_p = ((qty_bw_p*price_bw_p)/1000000.0) * 0.65
sga_sw_a = ((qty_sw_a*price_sw_a)/1000000.0) * np.random.uniform(0.1, 0.15, 12);   sga_sw_p = ((qty_sw_p*price_sw_p)/1000000.0) * 0.12
sga_bw_a = ((qty_bw_a*price_bw_a)/1000000.0) * np.random.uniform(0.1, 0.15, 12);   sga_bw_p = ((qty_bw_p*price_bw_p)/1000000.0) * 0.12

# (2) 계획 파일 파싱
if os.path.exists("saved_plan.xlsx"):
    try:
        df_p = pd.read_excel("saved_plan.xlsx", header=None)
        qty_sw_p = safe_extract('SW수량입력', df_p, 'qty'); qty_bw_p = safe_extract('BW수량입력', df_p, 'qty')
        qty_ls_p = safe_extract('LS수량입력', df_p, 'qty'); qty_fs_p = safe_extract('FS수량입력', df_p, 'qty')
        price_sw_p = safe_extract('SW단가입력', df_p, 'qty'); price_bw_p = safe_extract('BW단가입력', df_p, 'qty')
        
        sales_prod_p = safe_extract('제품매출입력', df_p, 'money'); sales_semi_p = safe_extract('반제품매출입력', df_p, 'money')
        sales_md_p = safe_extract('상품매출입력', df_p, 'money'); sales_etc_p = safe_extract('기타매출입력', df_p, 'money')
        sales_inc_p = safe_extract('판매장려금입력', df_p, 'money')
        
        # 제품 파싱
        cogs_rm_p = safe_extract('원부재료비입력', df_p, 'money'); cogs_lb_p = safe_extract('노무비입력', df_p, 'money')
        cogs_os_p = safe_extract('외주가공비입력', df_p, 'money'); cogs_oh_p = safe_extract('기타경비입력', df_p, 'money')
        
        # 반제품 파싱
        cogs_semi_rm_p = safe_extract('반제품_원부재료비입력', df_p, 'money'); cogs_semi_lb_p = safe_extract('반제품_노무비입력', df_p, 'money')
        cogs_semi_os_p = safe_extract('반제품_외주가공비입력', df_p, 'money'); cogs_semi_oh_p = safe_extract('반제품_기타경비입력', df_p, 'money')
        
        cogs_semi_p = safe_extract('반제품매출원가입력', df_p, 'money')
        cogs_md_p = safe_extract('상품매출원가입력', df_p, 'money')
        cogs_etc_p = safe_extract('기타매출원가입력', df_p, 'money')
        cogs_std_p = safe_extract('표준원가차이입력', df_p, 'money')
        cogs_inv_p = safe_extract('재고평가손입력', df_p, 'money')
        
        gp_input_p = safe_extract('매출총이익입력', df_p, 'money', gp_input_p)
        op_input_p = safe_extract('영업이익입력', df_p, 'money', op_input_p)
        adj_op_input_p = safe_extract('조정영업이익입력', df_p, 'money', adj_op_input_p)
        
        adm_labor_p = safe_extract('일반관리비_인건비입력', df_p, 'money'); adm_depr_p = safe_extract('일반관리비_감가상각비입력', df_p, 'money')
        adm_rnd_p = safe_extract('일반관리비_경상개발비입력', df_p, 'money'); adm_fee_p = safe_extract('일반관리비_수수료입력', df_p, 'money')
        adm_etc_p = safe_extract('일반관리비_기타입력', df_p, 'money')
        
        sel_trans_p = safe_extract('판매비_운반비입력', df_p, 'money'); sel_fee_p = safe_extract('판매비_수수료입력', df_p, 'money')
        sel_brand_p = safe_extract('판매비_브랜드사용료입력', df_p, 'money'); sel_labor_p = safe_extract('판매비_인건비입력', df_p, 'money')
        sel_sample_p = safe_extract('판매비_견본비입력', df_p, 'money'); sel_bad_p = safe_extract('판매비_대손상각입력', df_p, 'money')
        sel_misc_p = safe_extract('판매비_잡비입력', df_p, 'money'); sel_etc_p = safe_extract('판매비_기타입력', df_p, 'money')
        
        cogs_sw_p = safe_extract('8인치 SW 매출원가', df_p, 'money', (qty_sw_p*price_sw_p/1000000.0)*0.6)
        cogs_bw_p = safe_extract('8인치 BW 매출원가', df_p, 'money', (qty_bw_p*price_bw_p/1000000.0)*0.65)
        sga_sw_p = safe_extract('8인치 SW 판관비', df_p, 'money', (qty_sw_p*price_sw_p/1000000.0)*0.12)
        sga_bw_p = safe_extract('8인치 BW 판관비', df_p, 'money', (qty_bw_p*price_bw_p/1000000.0)*0.12)
    except Exception as e: st.error(f"계획 엑셀 파일 파싱 오류: {e}")

# (3) 실적 파일 파싱
if os.path.exists("saved_actual.xlsx"):
    try:
        df_a = pd.read_excel("saved_actual.xlsx", header=None)
        qty_sw_a = safe_extract('SW수량입력', df_a, 'qty'); qty_bw_a = safe_extract('BW수량입력', df_a, 'qty')
        qty_ls_a = safe_extract('LS수량입력', df_a, 'qty'); qty_fs_a = safe_extract('FS수량입력', df_a, 'qty')
        price_sw_a = safe_extract('SW단가입력', df_a, 'qty'); price_bw_a = safe_extract('BW단가입력', df_a, 'qty')
        
        sales_prod_a = safe_extract('제품매출입력', df_a, 'money'); sales_semi_a = safe_extract('반제품매출입력', df_a, 'money')
        sales_md_a = safe_extract('상품매출입력', df_a, 'money'); sales_etc_a = safe_extract('기타매출입력', df_a, 'money')
        sales_inc_a = safe_extract('판매장려금입력', df_a, 'money')
        
        # 제품 파싱
        cogs_rm_a = safe_extract('원부재료비입력', df_a, 'money'); cogs_lb_a = safe_extract('노무비입력', df_a, 'money')
        cogs_os_a = safe_extract('외주가공비입력', df_a, 'money'); cogs_oh_a = safe_extract('기타경비입력', df_a, 'money')

        # 반제품 파싱
        cogs_semi_rm_a = safe_extract('반제품_원부재료비입력', df_a, 'money'); cogs_semi_lb_a = safe_extract('반제품_노무비입력', df_a, 'money')
        cogs_semi_os_a = safe_extract('반제품_외주가공비입력', df_a, 'money'); cogs_semi_oh_a = safe_extract('반제품_기타경비입력', df_a, 'money')
        
        cogs_semi_a = safe_extract('반제품매출원가입력', df_a, 'money')
        cogs_md_a = safe_extract('상품매출원가입력', df_a, 'money')
        cogs_etc_a = safe_extract('기타매출원가입력', df_a, 'money')
        cogs_std_a = safe_extract('표준원가차이입력', df_a, 'money')
        cogs_inv_a = safe_extract('재고평가손입력', df_a, 'money')
        
        gp_input_a = safe_extract('매출총이익입력', df_a, 'money', gp_input_a)
        op_input_a = safe_extract('영업이익입력', df_a, 'money', op_input_a)
        adj_op_input_a = safe_extract('조정영업이익입력', df_a, 'money', adj_op_input_a)
        
        adm_labor_a = safe_extract('일반관리비_인건비입력', df_a, 'money'); adm_depr_a = safe_extract('일반관리비_감가상각비입력', df_a, 'money')
        adm_rnd_a = safe_extract('일반관리비_경상개발비입력', df_a, 'money'); adm_fee_a = safe_extract('일반관리비_수수료입력', df_a, 'money')
        adm_etc_a = safe_extract('일반관리비_기타입력', df_a, 'money')
        
        sel_trans_a = safe_extract('판매비_운반비입력', df_a, 'money'); sel_fee_a = safe_extract('판매비_수수료입력', df_a, 'money')
        sel_brand_a = safe_extract('판매비_브랜드사용료입력', df_a, 'money'); sel_labor_a = safe_extract('판매비_인건비입력', df_a, 'money')
        sel_sample_a = safe_extract('판매비_견본비입력', df_a, 'money'); sel_bad_a = safe_extract('판매비_대손상각입력', df_a, 'money')
        sel_misc_a = safe_extract('판매비_잡비입력', df_a, 'money'); sel_etc_a = safe_extract('판매비_기타입력', df_a, 'money')
        
        cogs_sw_a = safe_extract('8인치 SW 매출원가', df_a, 'money', (qty_sw_a*price_sw_a/1000000.0)*0.6)
        cogs_bw_a = safe_extract('8인치 BW 매출원가', df_a, 'money', (qty_bw_a*price_bw_a/1000000.0)*0.65)
        sga_sw_a = safe_extract('8인치 SW 판관비', df_a, 'money', (qty_sw_a*price_sw_a/1000000.0)*0.12)
        sga_bw_a = safe_extract('8인치 BW 판관비', df_a, 'money', (qty_bw_a*price_bw_a/1000000.0)*0.12)
    except Exception as e: st.error(f"실적 엑셀 파일 파싱 오류: {e}")

# --- 4. 전사 파생 변수 최종 역산 로직 ---
qty_total_a = qty_sw_a + qty_bw_a + qty_ls_a
qty_total_p = qty_sw_p + qty_bw_p + qty_ls_p

sales_total_a = sales_prod_a + sales_semi_a + sales_md_a + sales_etc_a + sales_inc_a
sales_total_p = sales_prod_p + sales_semi_p + sales_md_p + sales_etc_p + sales_inc_p

adm_total_a = adm_labor_a + adm_depr_a + adm_rnd_a + adm_fee_a + adm_etc_a
adm_total_p = adm_labor_p + adm_depr_p + adm_rnd_p + adm_fee_p + adm_etc_p

sel_total_a = sel_trans_a + sel_fee_a + sel_brand_a + sel_labor_a + sel_sample_a + sel_bad_a + sel_misc_a + sel_etc_a
sel_total_p = sel_trans_p + sel_fee_p + sel_brand_p + sel_labor_p + sel_sample_p + sel_bad_p + sel_misc_p + sel_etc_p

sga_total_a = adm_total_a + sel_total_a
sga_total_p = adm_total_p + sel_total_p

# [역산 1] 매출총이익과 영업이익은 입력값 고정
gp_total_a = gp_input_a; gp_total_p = gp_input_p
op_actual = op_input_a; op_plan = op_input_p

# [역산 2] 총 매출원가 = 매출액 - 입력 매출총이익
cogs_total_a = sales_total_a - gp_total_a
cogs_total_p = sales_total_p - gp_total_p

# [역산 3] 제품 매출원가 = 총 매출원가 - (반제품+상품+기타+표준+평가손)
cogs_prod_a = cogs_total_a - (cogs_semi_a + cogs_md_a + cogs_etc_a + cogs_std_a + cogs_inv_a)
cogs_prod_p = cogs_total_p - (cogs_semi_p + cogs_md_p + cogs_etc_p + cogs_std_p + cogs_inv_p)

def calculate_annual_progress(actual_values, plan_values):
    """누적 실적 ÷ 연간(1~12월) 전체 계획으로 진도율을 계산한다."""
    cumulative_actual = sum(actual_values)
    annual_plan = sum(plan_values)
    progress_rate = (cumulative_actual / annual_plan) * 100 if annual_plan else 0
    variance_rate = ((cumulative_actual - annual_plan) / annual_plan) * 100 if annual_plan else 0
    return cumulative_actual, annual_plan, progress_rate, variance_rate

total_sales_actual_sum, total_sales_plan_sum, sales_progress_rate, sales_variance_rate = calculate_annual_progress(sales_total_a, sales_total_p)
total_op_actual_sum, total_op_plan_sum, op_progress_rate, op_variance_rate = calculate_annual_progress(op_actual, op_plan)
total_adj_op_actual_sum, total_adj_op_plan_sum, adj_op_progress_rate, adj_op_variance_rate = calculate_annual_progress(adj_op_input_a, adj_op_input_p)

with col2: st.metric(label="매출액", value=f"{total_sales_actual_sum:,.0f} 백만원", delta=f"진도율 {sales_progress_rate:.1f}% | 계획 대비 달성률 {sales_variance_rate:+.1f}%", delta_color="normal")
with col3: st.metric(label="영업이익", value=f"{total_op_actual_sum:,.0f} 백만원", delta=f"진도율 {op_progress_rate:.1f}% | 계획 대비 달성률 {op_variance_rate:+.1f}%", delta_color="normal")
with col4: st.metric(label="조정 영업이익", value=f"{total_adj_op_actual_sum:,.0f} 백만원", delta=f"진도율 {adj_op_progress_rate:.1f}% | 계획 대비 달성률 {adj_op_variance_rate:+.1f}%", delta_color="normal")

st.markdown("---")

# 5. 차트 1: 매출액 추이
col_sales_title, col_sales_unit = st.columns([1, 1])
with col_sales_title: st.markdown("##### 📈 월별 매출액 추이")
with col_sales_unit: st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-top: 10px;'>(단위: 백만원)</div>", unsafe_allow_html=True)

fig_sales = go.Figure()
fig_sales.add_trace(go.Bar(x=months, y=sales_total_p, name='계획 (Plan)', marker_color='#E5E7EB', text=[f"{val:,.0f}" if val!=0 else "" for val in sales_total_p], textposition='inside', insidetextanchor='end', textfont=dict(size=11, color='#6B7280'))) 
fig_sales.add_trace(go.Bar(x=months, y=sales_total_a, name='실적 (Actual)', marker_color='#10B981', text=[f"{val:,.0f}" if val!=0 else "" for val in sales_total_a], textposition='outside', cliponaxis=False, textfont=dict(size=12, color='black', weight='bold'))) 

max_bar_sales = max(max(sales_total_p), max(sales_total_a)) if len(sales_total_p)>0 else 100
min_bar_sales = min(min(sales_total_p), min(sales_total_a)) if len(sales_total_p)>0 else 0
if max_bar_sales == 0 and min_bar_sales == 0: max_bar_sales = 100
y1_range_sales = [min_bar_sales * 1.5 if min_bar_sales < 0 else 0, max_bar_sales * 1.3]

fig_sales.update_layout(
    barmode='group', margin=dict(l=0, r=0, t=20, b=30), 
    legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), 
    plot_bgcolor='white', height=400, 
    yaxis=dict(showgrid=True, gridcolor='#F3F4F6', zeroline=True, zerolinecolor='#9CA3AF', zerolinewidth=1, range=y1_range_sales, showticklabels=False)
)
st.plotly_chart(fig_sales, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# 6-1. 차트 2: 영업이익 추이
col_op_title, col_op_unit = st.columns([1, 1])
with col_op_title: st.markdown("##### 📈 월별 영업이익 추이")
with col_op_unit: st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-top: 10px;'>(단위: 백만원, %)</div>", unsafe_allow_html=True)

fig_op = go.Figure()
op_margin_actual = np.zeros(12)
for i in range(12):
    if sales_total_a[i] != 0:
        op_margin_actual[i] = (op_actual[i] / sales_total_a[i]) * 100

fig_op.add_trace(go.Bar(x=months, y=op_plan, name='계획 (Plan)', marker_color='#F3F4F6', yaxis='y1', text=[f"{val:,.0f}" if val!=0 else "" for val in op_plan], textposition='inside', insidetextanchor='end', textfont=dict(size=11, color='#9CA3AF'))) 
fig_op.add_trace(go.Bar(x=months, y=op_actual, name='실적 (Actual)', marker_color=['#F43F5E' if val >= 0 else '#3B82F6' for val in op_actual], yaxis='y1', text=[f"{val:,.0f}" if val!=0 else "" for val in op_actual], textposition='outside', cliponaxis=False, textfont=dict(size=12, color='black', weight='bold'))) 
fig_op.add_trace(go.Scatter(x=months, y=op_margin_actual, name='영업이익률(%)', mode='lines+markers+text', text=[f"{val:.1f}%" if val!=0 and not pd.isna(val) and not np.isinf(val) else "" for val in op_margin_actual], textposition='top center', cliponaxis=False, textfont=dict(size=13, color='#4338CA', weight='bold'), marker=dict(color='white', size=10, line=dict(color='#4338CA', width=2.5)), line=dict(color='#4338CA', width=3, shape='spline'), yaxis='y2'))

max_bar = max(max(op_plan), max(op_actual)) if len(op_plan)>0 else 100
min_bar = min(min(op_plan), min(op_actual)) if len(op_plan)>0 else 0
if max_bar == 0 and min_bar == 0: max_bar = 100
y1_range = [min_bar * 1.5 if min_bar < 0 else -max_bar * 0.1, max_bar * 2.5]

margin_span = max(op_margin_actual) - min(op_margin_actual) if len(op_margin_actual)>0 else 10
if margin_span == 0 or pd.isna(margin_span): margin_span = 10
y2_range = [min(op_margin_actual) - (margin_span * 2.0) if not pd.isna(min(op_margin_actual)) else 0, max(op_margin_actual) + (margin_span * 0.2) if not pd.isna(max(op_margin_actual)) else 100]

fig_op.update_layout(barmode='group', margin=dict(l=0, r=0, t=20, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), plot_bgcolor='white', height=400, yaxis=dict(showgrid=True, gridcolor='#F3F4F6', zeroline=True, zerolinecolor='#9CA3AF', zerolinewidth=1, range=y1_range, showticklabels=False), yaxis2=dict(overlaying='y', side='right', showgrid=False, range=y2_range, showticklabels=False))
st.plotly_chart(fig_op, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# 6-2. 차트 3: 조정 영업이익 추이 
col_adj_op_title, col_adj_op_unit = st.columns([1, 1])
with col_adj_op_title: st.markdown("##### 📈 월별 조정 영업이익 추이")
with col_adj_op_unit: st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-top: 10px;'>(단위: 백만원, %)</div>", unsafe_allow_html=True)

adj_op_plan = adj_op_input_p
adj_op_actual = adj_op_input_a

adj_op_margin_actual = np.zeros(12)
for i in range(12):
    if sales_total_a[i] != 0:
        adj_op_margin_actual[i] = (adj_op_actual[i] / sales_total_a[i]) * 100

fig_adj_op = go.Figure()
fig_adj_op.add_trace(go.Bar(x=months, y=adj_op_plan, name='계획 (Plan)', marker_color='#E5E7EB', text=[f"{val:,.0f}" if val!=0 else "" for val in adj_op_plan], textposition='inside', insidetextanchor='end', textfont=dict(size=11, color='#9CA3AF'))) 
# 조정 영업이익 바 차트 색상: 오렌지(흑자) / 스카이블루(적자)
fig_adj_op.add_trace(go.Bar(x=months, y=adj_op_actual, name='실적 (Actual)', marker_color=['#F97316' if val >= 0 else '#0EA5E9' for val in adj_op_actual], yaxis='y1', text=[f"{val:,.0f}" if val!=0 else "" for val in adj_op_actual], textposition='outside', cliponaxis=False, textfont=dict(size=12, color='black', weight='bold'))) 
fig_adj_op.add_trace(go.Scatter(x=months, y=adj_op_margin_actual, name='조정 영업이익률(%)', mode='lines+markers+text', text=[f"{val:.1f}%" if val!=0 and not pd.isna(val) and not np.isinf(val) else "" for val in adj_op_margin_actual], textposition='top center', cliponaxis=False, textfont=dict(size=13, color='#8B5CF6', weight='bold'), marker=dict(color='white', size=10, line=dict(color='#8B5CF6', width=2.5)), line=dict(color='#8B5CF6', width=3, shape='spline'), yaxis='y2'))

max_bar_adj = max(max(adj_op_plan), max(adj_op_actual)) if len(adj_op_plan)>0 else 100
min_bar_adj = min(min(adj_op_plan), min(adj_op_actual)) if len(adj_op_plan)>0 else 0
if max_bar_adj == 0 and min_bar_adj == 0: max_bar_adj = 100
y1_range_adj = [min_bar_adj * 1.5 if min_bar_adj < 0 else -max_bar_adj * 0.1, max_bar_adj * 2.5]

margin_span_adj = max(adj_op_margin_actual) - min(adj_op_margin_actual) if len(adj_op_margin_actual)>0 else 10
if margin_span_adj == 0 or pd.isna(margin_span_adj): margin_span_adj = 10
y2_range_adj = [min(adj_op_margin_actual) - (margin_span_adj * 2.0) if not pd.isna(min(adj_op_margin_actual)) else 0, max(adj_op_margin_actual) + (margin_span_adj * 0.2) if not pd.isna(max(adj_op_margin_actual)) else 100]

fig_adj_op.update_layout(barmode='group', margin=dict(l=0, r=0, t=20, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), plot_bgcolor='white', height=400, yaxis=dict(showgrid=True, gridcolor='#F3F4F6', zeroline=True, zerolinecolor='#9CA3AF', zerolinewidth=1, range=y1_range_adj, showticklabels=False), yaxis2=dict(overlaying='y', side='right', showgrid=False, range=y2_range_adj, showticklabels=False))
st.plotly_chart(fig_adj_op, use_container_width=True)


# 7. 손익계산서 테이블
st.markdown("---")
# 💡 디자인 최적화: 라디오 버튼 중앙 고정, 기간 설정 시 드롭박스를 아래로 배치하며 극한으로 크기 축소
pnl_mode = st.session_state.get("pnl_toggle", "실적만 보기")
st.markdown("##### 📊 손익계산서")
st.radio("표시 기준 선택", ["실적만 보기", "계획/실적 비교", "기간 설정 비교"], horizontal=True, label_visibility="collapsed", key="pnl_toggle")

if pnl_mode == "기간 설정 비교":
    selected_start_m, selected_end_m = render_centered_period_selectors(months, "st_pnl", "ed_pnl")
    start_idx = months.index(selected_start_m)
    end_idx = months.index(selected_end_m)
else:
    start_idx = 0
    end_idx = 0
    selected_start_m = "1월"
    selected_end_m = "1월"

view_mode = st.session_state["pnl_toggle"]

render_table_unit("(단위: 백만원, pcs, m, %)", view_mode == "기간 설정 비교")

items = [
    '<label for="toggle-sales"><span class="icon-sales"></span> 매출액</label>', 
    '<span class="child-sales"> - 제품</span>', '<span class="child-sales"> - 반제품</span>', '<span class="child-sales"> - 상품</span>', '<span class="child-sales"> - 기타</span>', '<span class="child-sales"> - 판매장려금</span>',
    '<label for="toggle-qty"><span class="icon-qty"></span> 매출수량</label>', 
    '<span class="child-qty"> - 8인치 SW</span>', '<span class="child-qty"> - 8인치 BW</span>', '<span class="child-qty"> - LS</span>', '<span class="child-qty"> - FS</span>',
    '<label for="toggle-cogs"><span class="icon-cogs"></span> 매출원가</label>', 
    '<span class="child-cogs"> - 제품</span>', '<span class="child-cogs"> - 반제품</span>', '<span class="child-cogs"> - 상품</span>', '<span class="child-cogs"> - 기타</span>', '<span class="child-cogs"> - 표준</span>', '<span class="child-cogs"> - 재고자산 평가손</span>',
    '매출원가율', '매출총이익', '매출총이익률', '판관비', '영업이익', '영업이익률', '조정 영업이익', '조정 영업이익률'
]

cogs_ratio_a = np.zeros(12); cogs_ratio_p = np.zeros(12)
gp_ratio_a = np.zeros(12); gp_ratio_p = np.zeros(12)
op_ratio_a = np.zeros(12); op_ratio_p = np.zeros(12)
adj_op_ratio_a = np.zeros(12); adj_op_ratio_p = np.zeros(12)

for i in range(12):
    if sales_total_a[i] != 0:
        cogs_ratio_a[i] = (cogs_total_a[i] / sales_total_a[i]) * 100
        gp_ratio_a[i] = (gp_total_a[i] / sales_total_a[i]) * 100
        op_ratio_a[i] = (op_actual[i] / sales_total_a[i]) * 100
        adj_op_ratio_a[i] = (adj_op_actual[i] / sales_total_a[i]) * 100
    if sales_total_p[i] != 0:
        cogs_ratio_p[i] = (cogs_total_p[i] / sales_total_p[i]) * 100
        gp_ratio_p[i] = (gp_total_p[i] / sales_total_p[i]) * 100
        op_ratio_p[i] = (op_plan[i] / sales_total_p[i]) * 100
        adj_op_ratio_p[i] = (adj_op_plan[i] / sales_total_p[i]) * 100

actual_rows = [
    sales_total_a, sales_prod_a, sales_semi_a, sales_md_a, sales_etc_a, sales_inc_a, 
    qty_total_a, qty_sw_a, qty_bw_a, qty_ls_a, qty_fs_a, 
    cogs_total_a, cogs_prod_a, cogs_semi_a, cogs_md_a, cogs_etc_a, cogs_std_a, cogs_inv_a, 
    cogs_ratio_a, gp_total_a, gp_ratio_a, 
    sga_total_a, op_actual, op_ratio_a, adj_op_actual, adj_op_ratio_a
]
plan_rows = [
    sales_total_p, sales_prod_p, sales_semi_p, sales_md_p, sales_etc_p, sales_inc_p, 
    qty_total_p, qty_sw_p, qty_bw_p, qty_ls_p, qty_fs_p, 
    cogs_total_p, cogs_prod_p, cogs_semi_p, cogs_md_p, cogs_etc_p, cogs_std_p, cogs_inv_p, 
    cogs_ratio_p, gp_total_p, gp_ratio_p, 
    sga_total_p, op_plan, op_ratio_p, adj_op_plan, adj_op_ratio_p
]

actual_sums = [sum(row) for row in actual_rows]
plan_sums = [sum(row) for row in plan_rows]

idx_sales, idx_cogs, idx_gp, idx_op = 0, 11, 19, 22

actual_sums[18] = (actual_sums[idx_cogs] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] != 0 else 0
actual_sums[20] = (actual_sums[idx_gp] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] != 0 else 0
actual_sums[23] = (actual_sums[idx_op] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] != 0 else 0
actual_sums[25] = (actual_sums[24] / actual_sums[idx_sales]) * 100 if actual_sums[idx_sales] != 0 else 0
plan_sums[18] = (plan_sums[idx_cogs] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] != 0 else 0
plan_sums[20] = (plan_sums[idx_gp] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] != 0 else 0
plan_sums[23] = (plan_sums[idx_op] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] != 0 else 0
plan_sums[25] = (plan_sums[24] / plan_sums[idx_sales]) * 100 if plan_sums[idx_sales] != 0 else 0

if view_mode == "기간 설정 비교":
    if start_idx > end_idx:
        st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 기간 설정 오류</h4><p style='color: #7F1D1D; margin-top: 10px;'>시작월이 종료월보다 이후일 수 없습니다.</p></div>", unsafe_allow_html=True)
    else:
        missing_actuals = any(sales_total_a[i] == 0 for i in range(start_idx, end_idx + 1))
        if missing_actuals:
            st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 실적이 없습니다</h4><p style='color: #7F1D1D; margin-top: 10px;'>선택하신 기간 중 <b>실적 데이터가 입력되지 않은 월</b>이 포함되어 비교가 불가능합니다.</p></div>", unsafe_allow_html=True)
        else:
            ytd_plan = [sum(row[start_idx:end_idx+1]) for row in plan_rows]
            ytd_actual = [sum(row[start_idx:end_idx+1]) for row in actual_rows]
            
            if ytd_plan[idx_sales] != 0:
                ytd_plan[18] = (ytd_plan[idx_cogs] / ytd_plan[idx_sales]) * 100
                ytd_plan[20] = (ytd_plan[idx_gp] / ytd_plan[idx_sales]) * 100
                ytd_plan[23] = (ytd_plan[idx_op] / ytd_plan[idx_sales]) * 100
            else:
                ytd_plan[18] = ytd_plan[20] = ytd_plan[23] = 0
                
            if ytd_actual[idx_sales] != 0:
                ytd_actual[18] = (ytd_actual[idx_cogs] / ytd_actual[idx_sales]) * 100
                ytd_actual[20] = (ytd_actual[idx_gp] / ytd_actual[idx_sales]) * 100
                ytd_actual[23] = (ytd_actual[idx_op] / ytd_actual[idx_sales]) * 100
            else:
                ytd_actual[18] = ytd_actual[20] = ytd_actual[23] = 0
                
            diff_vals = [a - p for a, p in zip(ytd_actual, ytd_plan)]
            
            ytd_tuples = [('항목', ''), (f'{selected_start_m}~{selected_end_m} 누계', '계획'), (f'{selected_start_m}~{selected_end_m} 누계', '실적'), (f'{selected_start_m}~{selected_end_m} 누계', '차이(실적-계획)')]
            ytd_rows_data = []
            
            for i, item in enumerate(items):
                is_ratio = ('율' in str(item) or '률' in str(item))
                if pd.isna(diff_vals[i]) or np.isinf(diff_vals[i]): diff_str = ""
                elif is_ratio: diff_str = f"{diff_vals[i]:+.1f}%p" if diff_vals[i] != 0 else "0.0%p"
                else: diff_str = f"{diff_vals[i]:+,.0f}" if diff_vals[i] != 0 else "0"
                ytd_rows_data.append([item, format_cell(ytd_plan[i], is_ratio), format_cell(ytd_actual[i], is_ratio), diff_str])
                
            df_ytd = pd.DataFrame(ytd_rows_data, columns=pd.MultiIndex.from_tuples(ytd_tuples))
            render_pnl_table(df_ytd, "ytd")

elif view_mode == "계획/실적 비교":
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
    render_pnl_table(df_table, "compare")
else:
    df_table = pd.DataFrame({'항목': items})
    for i, month in enumerate(months): df_table[month] = [row[i] for row in actual_rows]
    df_table['합계'] = actual_sums
    for col in df_table.columns:
        if col != '항목': df_table[col] = df_table.apply(lambda row: format_cell(row[col], '율' in str(row['항목']) or '률' in str(row['항목'])), axis=1)
    render_pnl_table(df_table, "")

# 8. 제품/반제품 매출원가 내역
st.markdown("---")
st.markdown("##### 🔍 제품/반제품(FS) 매출원가 내역")

cogs_prod_input_sum_a = cogs_rm_a + cogs_lb_a + cogs_os_a + cogs_oh_a
cogs_semi_input_sum_a = cogs_semi_rm_a + cogs_semi_lb_a + cogs_semi_os_a + cogs_semi_oh_a
comb_input_sum_a = cogs_prod_input_sum_a + cogs_semi_input_sum_a

cogs_prod_input_sum_p = cogs_rm_p + cogs_lb_p + cogs_os_p + cogs_oh_p
cogs_semi_input_sum_p = cogs_semi_rm_p + cogs_semi_lb_p + cogs_semi_os_p + cogs_semi_oh_p
comb_input_sum_p = cogs_prod_input_sum_p + cogs_semi_input_sum_p

target_comb_cogs_a = cogs_prod_a + cogs_semi_a
target_comb_cogs_p = cogs_prod_p + cogs_semi_p

mismatched_months_a = [f"{i+1}월" for i in range(12) if abs(target_comb_cogs_a[i] - comb_input_sum_a[i]) >= 1.0]
mismatched_months_p = [f"{i+1}월" for i in range(12) if abs(target_comb_cogs_p[i] - comb_input_sum_p[i]) >= 1.0]

if mismatched_months_a or mismatched_months_p:
    st.markdown("<div style='padding: 15px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; margin-bottom: 15px;'>", unsafe_allow_html=True)
    st.markdown("<p style='color: #B91C1C; font-weight: bold; margin: 0;'>⚠️ [합계 오류] 손익계산서 상 제품/반제품 매출원가와 하단 내역의 합계가 일치하지 않습니다.</p>", unsafe_allow_html=True)
    if mismatched_months_p:
        st.markdown(f"<p style='color: #7F1D1D; margin: 5px 0 0 0;'>• <b>계획(Plan) 점검 필요:</b> {', '.join(mismatched_months_p)}</p>", unsafe_allow_html=True)
    if mismatched_months_a:
        st.markdown(f"<p style='color: #7F1D1D; margin: 5px 0 0 0;'>• <b>실적(Actual) 점검 필요:</b> {', '.join(mismatched_months_a)}</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='text-align: right; font-size: 12px; font-weight: bold; color: #4B5563; margin-bottom: 5px;'>(단위: 백만원, %)</div>", unsafe_allow_html=True)

comb_rm_a = cogs_rm_a + cogs_semi_rm_a
comb_lb_a = cogs_lb_a + cogs_semi_lb_a
comb_os_a = cogs_os_a + cogs_semi_os_a
comb_oh_a = cogs_oh_a + cogs_semi_oh_a

cogs_items = ['원부재료', '노무비', '외주가공비', '기타경비', '합계'] 
cogs_rows_a = [comb_rm_a, comb_lb_a, comb_os_a, comb_oh_a, comb_input_sum_a]
cogs_sums_a = [sum(row) for row in cogs_rows_a]

sales_denom_a = sales_total_a
sales_denom_sum_a = sum(sales_denom_a)

tuples_cogs = [('항목', '')]
for m in months: tuples_cogs.extend([(m, '실적금액'), (m, '매출비율')])
tuples_cogs.extend([('합계', '실적금액'), ('합계', '매출비율')])

combined_rows_cogs = []
for i, item in enumerate(cogs_items):
    row_data = [item]
    for m_idx in range(12):
        amt = cogs_rows_a[i][m_idx]
        ratio = (amt / sales_denom_a[m_idx]) * 100 if sales_denom_a[m_idx] != 0 else 0
        row_data.extend([amt, format_cell(ratio, True) if amt != 0 else ""])
    sum_amt = cogs_sums_a[i]
    sum_ratio = (sum_amt / sales_denom_sum_a) * 100 if sales_denom_sum_a != 0 else 0
    row_data.extend([sum_amt, format_cell(sum_ratio, True) if sum_amt != 0 else ""])
    combined_rows_cogs.append(row_data)

df_cogs = pd.DataFrame(combined_rows_cogs, columns=pd.MultiIndex.from_tuples(tuples_cogs))
for col in df_cogs.columns:
    if col[1] == '실적금액': df_cogs[col] = df_cogs[col].apply(lambda x: format_cell(x, False))
render_html_table(df_cogs, "compare")
st.markdown("<br>", unsafe_allow_html=True)

# 9. 판매관리비 명세서
st.markdown("---")
sga_mode = st.session_state.get("sga_toggle", "실적만 보기")
st.markdown("##### 🔍 판매관리비 명세서")
st.radio("판관비 표시 기준 선택", ["실적만 보기", "계획/실적 비교", "기간 설정 비교"], horizontal=True, label_visibility="collapsed", key="sga_toggle")

if sga_mode == "기간 설정 비교":
    selected_st_sga, selected_ed_sga = render_centered_period_selectors(months, "st_sga", "ed_sga")
    start_idx_sga = months.index(selected_st_sga)
    end_idx_sga = months.index(selected_ed_sga)
else:
    start_idx_sga = 0
    end_idx_sga = 0
    selected_st_sga = "1월"
    selected_ed_sga = "1월"

view_mode_sga = st.session_state["sga_toggle"]

render_table_unit("(단위: 백만원)", view_mode_sga == "기간 설정 비교")

sga_items = [
    '【 일반관리비 소계 】', ' - 인건비', ' - 감가상각비', ' - 경상개발비', ' - 수수료', ' - 기타',
    '【 판매비 소계 】', ' - 운반비', ' - 수수료', ' - 브랜드사용료', ' - 인건비', ' - 견본비', ' - 대손상각', ' - 잡비', ' - 기타',
    '▶ 판관비 총계'
]

sga_actual_rows = [
    adm_total_a, adm_labor_a, adm_depr_a, adm_rnd_a, adm_fee_a, adm_etc_a,
    sel_total_a, sel_trans_a, sel_fee_a, sel_brand_a, sel_labor_a, sel_sample_a, sel_bad_a, sel_misc_a, sel_etc_a,
    sga_total_a
]

sga_plan_rows = [
    adm_total_p, adm_labor_p, adm_depr_p, adm_rnd_p, adm_fee_p, adm_etc_p,
    sel_total_p, sel_trans_p, sel_fee_p, sel_brand_p, sel_labor_p, sel_sample_p, sel_bad_p, sel_misc_p, sel_etc_p,
    sga_total_p
]

sga_actual_sums = [sum(row) for row in sga_actual_rows]
sga_plan_sums = [sum(row) for row in sga_plan_rows]

if view_mode_sga == "기간 설정 비교":
    if start_idx_sga > end_idx_sga:
        st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 기간 설정 오류</h4><p style='color: #7F1D1D; margin-top: 10px;'>시작월이 종료월보다 이후일 수 없습니다.</p></div>", unsafe_allow_html=True)
    else:
        missing_actuals = any(sales_total_a[i] == 0 for i in range(start_idx_sga, end_idx_sga + 1))
        if missing_actuals:
            st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 실적이 없습니다</h4><p style='color: #7F1D1D; margin-top: 10px;'>선택하신 기간 중 <b>실적 데이터가 입력되지 않은 월</b>이 포함되어 비교가 불가능합니다.</p></div>", unsafe_allow_html=True)
        else:
            ytd_plan_sga = [sum(row[start_idx_sga:end_idx_sga+1]) for row in sga_plan_rows]
            ytd_actual_sga = [sum(row[start_idx_sga:end_idx_sga+1]) for row in sga_actual_rows]
            diff_vals_sga = [a - p for a, p in zip(ytd_actual_sga, ytd_plan_sga)]
            
            ytd_tuples_sga = [('항목', ''), (f'{selected_st_sga}~{selected_ed_sga} 누계', '계획'), (f'{selected_st_sga}~{selected_ed_sga} 누계', '실적'), (f'{selected_st_sga}~{selected_ed_sga} 누계', '차이(실적-계획)')]
            ytd_rows_data_sga = []
            for i, item in enumerate(sga_items):
                diff_str = f"{diff_vals_sga[i]:+,.0f}" if diff_vals_sga[i] != 0 else "0"
                ytd_rows_data_sga.append([item, format_cell(ytd_plan_sga[i], False), format_cell(ytd_actual_sga[i], False), diff_str])
            
            df_ytd_sga = pd.DataFrame(ytd_rows_data_sga, columns=pd.MultiIndex.from_tuples(ytd_tuples_sga))
            render_html_table(df_ytd_sga, "ytd")
            
elif view_mode_sga == "계획/실적 비교":
    tuples_sga = [('항목', '')]
    for m in months: tuples_sga.extend([(m, '계획'), (m, '실적')])
    tuples_sga.extend([('합계', '계획'), ('합계', '실적')])
    combined_rows_sga = []
    for i, item in enumerate(sga_items):
        row_data = [item]
        for m_idx in range(12): row_data.extend([sga_plan_rows[i][m_idx], sga_actual_rows[i][m_idx]])
        row_data.extend([sga_plan_sums[i], sga_actual_sums[i]])
        combined_rows_sga.append(row_data)
    df_sga_comp = pd.DataFrame(combined_rows_sga, columns=pd.MultiIndex.from_tuples(tuples_sga))
    for col in df_sga_comp.columns:
        if col != ('항목', ''): df_sga_comp[col] = df_sga_comp[col].apply(lambda x: format_cell(x, False))
    render_html_table(df_sga_comp, "compare")
else:
    df_sga = pd.DataFrame({'항목': sga_items})
    for i, month in enumerate(months): df_sga[month] = [row[i] for row in sga_actual_rows]
    df_sga['합계'] = sga_actual_sums
    for col in df_sga.columns:
        if col != '항목': df_sga[col] = df_sga[col].apply(lambda x: format_cell(x, False))
    render_html_table(df_sga, "")

# 10. Item별 구분손익
st.markdown("---")
type_mode = st.session_state.get("type_toggle", "실적만 보기")
st.markdown("##### 🔍 Item별 구분손익")
st.radio("구분손익 표시 기준 선택", ["실적만 보기", "계획/실적 비교", "기간 설정 비교"], horizontal=True, label_visibility="collapsed", key="type_toggle")

if type_mode == "기간 설정 비교":
    selected_st_type, selected_ed_type = render_centered_period_selectors(months, "st_type", "ed_type")
    start_idx_type = months.index(selected_st_type)
    end_idx_type = months.index(selected_ed_type)
else:
    start_idx_type = 0
    end_idx_type = 0
    selected_st_type = "1월"
    selected_ed_type = "1월"

view_mode_type = st.session_state["type_toggle"]

render_table_unit("(단위: 백만원, pcs, 원, %)", view_mode_type == "기간 설정 비교")

def build_type_pnl(qty_a, qty_p, price_a, price_p, cogs_a, cogs_p, sga_a, sga_p):
    sales_a = (qty_a * price_a) / 1000000.0
    sales_p = (qty_p * price_p) / 1000000.0
    
    gp_a, gp_p = sales_a - cogs_a, sales_p - cogs_p
    op_a, op_p = gp_a - sga_a, gp_p - sga_p
    
    cr_a = np.zeros(12); cr_p = np.zeros(12)
    gpr_a = np.zeros(12); gpr_p = np.zeros(12)
    opr_a = np.zeros(12); opr_p = np.zeros(12)
    for i in range(12):
        if sales_a[i] != 0:
            cr_a[i] = (cogs_a[i] / sales_a[i]) * 100
            gpr_a[i] = (gp_a[i] / sales_a[i]) * 100
            opr_a[i] = (op_a[i] / sales_a[i]) * 100
        if sales_p[i] != 0:
            cr_p[i] = (cogs_p[i] / sales_p[i]) * 100
            gpr_p[i] = (gp_p[i] / sales_p[i]) * 100
            opr_p[i] = (op_p[i] / sales_p[i]) * 100

    rows_a = [sales_a, qty_a, price_a, cogs_a, cr_a, gp_a, gpr_a, sga_a, op_a, opr_a]
    rows_p = [sales_p, qty_p, price_p, cogs_p, cr_p, gp_p, gpr_p, sga_p, op_p, opr_p]

    s_sales_a, s_sales_p = sum(sales_a), sum(sales_p)
    avg_price_a = (s_sales_a * 1000000.0) / sum(qty_a) if sum(qty_a) else 0
    avg_price_p = (s_sales_p * 1000000.0) / sum(qty_p) if sum(qty_p) else 0
    
    sums_a = [s_sales_a, sum(qty_a), avg_price_a, sum(cogs_a), (sum(cogs_a)/s_sales_a*100) if s_sales_a else 0, sum(gp_a), (sum(gp_a)/s_sales_a*100) if s_sales_a else 0, sum(sga_a), sum(op_a), (sum(op_a)/s_sales_a*100) if s_sales_a else 0]
    sums_p = [s_sales_p, sum(qty_p), avg_price_p, sum(cogs_p), (sum(cogs_p)/s_sales_p*100) if s_sales_p else 0, sum(gp_p), (sum(gp_p)/s_sales_p*100) if s_sales_p else 0, sum(sga_p), sum(op_p), (sum(op_p)/s_sales_p*100) if s_sales_p else 0]
    return rows_a, sums_a, rows_p, sums_p

type_items = ['매출액', '매출수량(pcs)', '단가(원)', '매출원가', '매출원가율', '매출총이익', '매출총이익률', '판관비', '영업이익', '영업이익률']

sw_rows_a, sw_sums_a, sw_rows_p, sw_sums_p = build_type_pnl(qty_sw_a, qty_sw_p, price_sw_a, price_sw_p, cogs_sw_a, cogs_sw_p, sga_sw_a, sga_sw_p)
bw_rows_a, bw_sums_a, bw_rows_p, bw_sums_p = build_type_pnl(qty_bw_a, qty_bw_p, price_bw_a, price_bw_p, cogs_bw_a, cogs_bw_p, sga_bw_a, sga_bw_p)

def render_type_table(rows_a, sums_a, rows_p, sums_p, view_mode, st_idx=0, ed_idx=0, st_month="", ed_month=""):
    if view_mode == "기간 설정 비교":
        if st_idx > ed_idx:
            st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 기간 설정 오류</h4><p style='color: #7F1D1D; margin-top: 10px;'>시작월이 종료월보다 이후일 수 없습니다.</p></div>", unsafe_allow_html=True)
            return
            
        missing_actuals = any(rows_a[0][i] == 0 for i in range(st_idx, ed_idx + 1))
        if missing_actuals:
            st.markdown("<div style='padding: 20px; background-color: #FEE2E2; border-left: 5px solid #EF4444; border-radius: 4px; text-align: center; width: 600px; margin: 0 auto;'><h4 style='color: #B91C1C; margin: 0;'>⚠️ 실적이 없습니다</h4><p style='color: #7F1D1D; margin-top: 10px;'>선택하신 기간 중 <b>실적 데이터가 입력되지 않은 월</b>이 포함되어 비교가 불가능합니다.</p></div>", unsafe_allow_html=True)
            return
            
        ytd_plan = [sum(r[st_idx:ed_idx+1]) for r in rows_p]
        ytd_actual = [sum(r[st_idx:ed_idx+1]) for r in rows_a]
        
        for ytd_arr in [ytd_plan, ytd_actual]:
            if ytd_arr[0] != 0:
                ytd_arr[4] = (ytd_arr[3] / ytd_arr[0]) * 100
                ytd_arr[6] = (ytd_arr[5] / ytd_arr[0]) * 100
                ytd_arr[9] = (ytd_arr[8] / ytd_arr[0]) * 100
                ytd_arr[2] = (ytd_arr[0] * 1000000.0) / ytd_arr[1] if ytd_arr[1] != 0 else 0
            else:
                ytd_arr[4] = ytd_arr[6] = ytd_arr[9] = ytd_arr[2] = 0
                
        diff_vals = [a - p for a, p in zip(ytd_actual, ytd_plan)]
        tuples = [('항목', ''), (f'{st_month}~{ed_month} 누계', '계획'), (f'{st_month}~{ed_month} 누계', '실적'), (f'{st_month}~{ed_month} 누계', '차이(실적-계획)')]
        c_rows = []
        for i, item in enumerate(type_items):
            is_ratio = ('율' in str(item) or '률' in str(item))
            diff_str = ""
            if pd.isna(diff_vals[i]) or np.isinf(diff_vals[i]): diff_str = ""
            elif is_ratio: diff_str = f"{diff_vals[i]:+.1f}%p" if diff_vals[i] != 0 else "0.0%p"
            else: diff_str = f"{diff_vals[i]:+,.0f}" if diff_vals[i] != 0 else "0"
            c_rows.append([item, format_cell(ytd_plan[i], is_ratio), format_cell(ytd_actual[i], is_ratio), diff_str])
            
        df = pd.DataFrame(c_rows, columns=pd.MultiIndex.from_tuples(tuples))
        render_html_table(df, "ytd")
        
    elif view_mode == "계획/실적 비교":
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
        render_html_table(df, "compare")
    else:
        df = pd.DataFrame({'항목': type_items})
        for i, m in enumerate(months): df[m] = [r[i] for r in rows_a]
        df['합계'] = sums_a
        for col in df.columns:
            if col != '항목': df[col] = df.apply(lambda row: format_cell(row[col], '율' in str(row['항목']) or '률' in str(row['항목'])), axis=1)
        render_html_table(df, "")


tab1, tab2 = st.tabs(["8인치 SW", "8인치 BW"])
with tab1: 
    st.markdown("**■ 8인치 SW 손익 명세**")
    render_type_table(sw_rows_a, sw_sums_a, sw_rows_p, sw_sums_p, view_mode_type, start_idx_type, end_idx_type, selected_st_type, selected_ed_type)
with tab2: 
    st.markdown("**■ 8인치 BW 손익 명세**")
    render_type_table(bw_rows_a, bw_sums_a, bw_rows_p, bw_sums_p, view_mode_type, start_idx_type, end_idx_type, selected_st_type, selected_ed_type)
