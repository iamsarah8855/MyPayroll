import streamlit as st
import pandas as pd
import json
import streamlit.components.v1 as components
from fpdf import FPDF
from num2words import num2words
from datetime import datetime, date
import calendar
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 0. APP CONFIGURATION & CSS
# ==========================================
st.set_page_config(page_title="SDG Tech Payroll", layout="wide", page_icon="🏢")

# 建立连接 (全局)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 注入 JS 脚本：专门解决手机 Sidebar 不自动收回的问题 ---
st.markdown("""
<script>
    // 监听 Radio Button 的点击事件
    const radios = window.parent.document.querySelectorAll('input[type="radio"]');
    radios.forEach(radio => {
        radio.addEventListener('click', () => {
            // 找到 Sidebar 的关闭按钮并模拟点击
            const closeBtn = window.parent.document.querySelector('button[kind="header"]');
            if (closeBtn) {
                closeBtn.click();
            }
        });
    });
</script>
<style>
    /* --- GLOBAL FONT FIX --- */
    html, body, [class*="css"] {
        font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
    }
    
    /* --- TABLE SCROLL FIX (手机横向滚动) --- */
    [data-testid="stDataFrame"] {
        width: 100%;
        overflow-x: auto;
        display: block;
        white-space: nowrap;
    }
    
    /* --- SIDEBAR --- */
    [data-testid="stSidebar"] { background-color: #1a1f36; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    .stRadio > div[role="radiogroup"] > label {
        background-color: transparent; color: white; padding: 10px 15px; border-radius: 8px; margin-bottom: 5px; border: 1px solid transparent;
    }
    .stRadio > div[role="radiogroup"] > label:hover { background-color: #2c3350; cursor: pointer; }

    /* --- METRICS --- */
    .metric-card-purple { background-color: #7f56d9; color: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .metric-card-blue { background-color: #0070f3; color: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .metric-label { font-size: 14px; font-weight: 500; opacity: 0.9; margin-bottom: 5px; }
    .metric-value { font-size: 28px; font-weight: 700; }

    /* --- STATUS PILLS --- */
    .pill-paid { 
        background-color: #e6f4ea; color: #1e7e34; 
        padding: 3px 10px; border-radius: 20px; 
        font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
        display: inline-block;
    }
    .pill-pending { 
        background-color: #fff3cd; color: #856404; 
        padding: 3px 10px; border-radius: 20px; 
        font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
        display: inline-block;
    }
    .input-label-spacer { height: 28px; } 

    /* ====================================================================
       MOBILE ULTRA-COMPACT LAYOUT (手机极度紧凑模式)
       ==================================================================== */
    @media (max-width: 800px) {
        /* 1. 强制容器宽度变窄，消灭中间的空白 */
        .main .block-container {
            min-width: 380px !important; 
            max-width: 100vw !important;
            padding-left: 2px !important;
            padding-right: 2px !important;
            overflow-x: auto !important;
        }
        
        html, body {
            overflow-x: auto !important;
        }

        /* 2. 强制横向，且间距 (gap) 设为 0 */
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 0px !important; 
        }
        
        /* 3. 允许列被压缩，并缩小字体 */
        div[data-testid="column"] {
            width: auto !important;
            flex: 1 1 auto !important;
            min-width: 0px !important;
            padding: 0px !important;
        }

        /* 4. 缩小所有文字 */
        div[data-testid="column"] p, 
        div[data-testid="column"] span,
        div[data-testid="column"] div {
            font-size: 11px !important; 
        }
        
        /* 5. 调整按钮大小 */
        .stButton button {
            padding: 0px 4px !important;
            font-size: 10px !important;
            height: 28px !important;
            min-height: 28px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. AUTHENTICATION LOGIC (SECURE)
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["username"] == st.secrets["credentials"]["username"] and st.session_state["password"] == st.secrets["credentials"]["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]; del st.session_state["username"]
        else: st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("🔒 SDG Tech Login")
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.button("Login", on_click=password_entered, type="primary")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("🔒 SDG Tech Login")
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.button("Login", on_click=password_entered, type="primary")
            st.error("😕 User not known or password incorrect")
        return False
    else: return True

if check_password():

    # ==========================================
    # 2. MAIN APPLICATION
    # ==========================================
    
    def load_db():
        default_db = {"employees": {}, "records": [], "leave_records": [], "settings": {"usd_rate": 4.45}}
        try:
            df_settings = conn.read(worksheet="Settings", ttl=0)
            if not df_settings.empty and 'usd_rate' in df_settings.columns:
                default_db['settings']['usd_rate'] = float(df_settings.iloc[0]['usd_rate'])

            df_emp = conn.read(worksheet="Employees", ttl=0)
            if not df_emp.empty:
                for _, row in df_emp.iterrows():
                    emp_name = row['name']
                    try: l_inc = json.loads(row['last_increment']) if row['last_increment'] else None
                    except: l_inc = None
                    try: l_bon = json.loads(row['last_bonus']) if row['last_bonus'] else None
                    except: l_bon = None

                    default_db['employees'][emp_name] = {
                        "name": row['name'],
                        "designation": row['designation'],
                        "join_date": row['join_date'],
                        "date_of_birth": row['date_of_birth'],
                        "currency": row['currency'],
                        "bank_name": row['bank_name'],
                        "account_number": str(row['account_number']),
                        "basic_salary": float(row['basic_salary']),
                        "status": row['status'],
                        "master_remark": row['master_remark'] if pd.notna(row['master_remark']) else "",
                        "last_increment": l_inc,
                        "last_bonus": l_bon
                    }

            df_rec = conn.read(worksheet="Records", ttl=0)
            if not df_rec.empty:
                for _, row in df_rec.iterrows():
                    try: earn_list = json.loads(row['earnings_list'])
                    except: earn_list = []
                    try: ded_list = json.loads(row['deductions_list'])
                    except: ded_list = []
                    
                    default_db['records'].append({
                        "id": row['id'],
                        "employee_id": row['employee_id'],
                        "month_label": row['month_label'],
                        "payment_date": row['payment_date'],
                        "earnings_list": earn_list,
                        "deductions_list": ded_list,
                        "net_salary": float(row['net_salary']),
                        "currency": row['currency'],
                        "remarks": row['remarks'] if pd.notna(row['remarks']) else "",
                        "status": row['status'],
                        "exchange_rate": float(row['exchange_rate']) if pd.notna(row['exchange_rate']) else 0.0
                    })
            return default_db
        except Exception as e:
            return default_db

    def save_db(data):
        df_set = pd.DataFrame([{"usd_rate": data['settings']['usd_rate']}])
        conn.update(worksheet="Settings", data=df_set)

        emp_list = []
        for name, info in data['employees'].items():
            emp_list.append({
                "name": info['name'],
                "designation": info['designation'],
                "join_date": info['join_date'],
                "date_of_birth": info.get('date_of_birth', ''),
                "currency": info['currency'],
                "bank_name": info['bank_name'],
                "account_number": info['account_number'],
                "basic_salary": info['basic_salary'],
                "status": info['status'],
                "master_remark": info.get('master_remark', ''),
                "last_increment": json.dumps(info['last_increment']) if info['last_increment'] else None,
                "last_bonus": json.dumps(info['last_bonus']) if info['last_bonus'] else None
            })
        if emp_list:
            conn.update(worksheet="Employees", data=pd.DataFrame(emp_list))
        
        rec_list = []
        for r in data['records']:
            rec_list.append({
                "id": r['id'],
                "employee_id": r['employee_id'],
                "month_label": r['month_label'],
                "payment_date": r['payment_date'],
                "earnings_list": json.dumps(r['earnings_list']),
                "deductions_list": json.dumps(r['deductions_list']),
                "net_salary": r['net_salary'],
                "currency": r['currency'],
                "remarks": r['remarks'],
                "status": r['status'],
                "exchange_rate": r['exchange_rate']
            })
        if rec_list:
            conn.update(worksheet="Records", data=pd.DataFrame(rec_list))
        st.cache_data.clear()

    def get_last_record(emp_id, db):
        emp_records = [r for r in db['records'] if r['employee_id'] == emp_id]
        if not emp_records: return None
        return sorted(emp_records, key=lambda x: x['id'])[-1]

    def convert_record_to_myr(record, default_rate):
        try:
            currency = str(record.get('currency', '')).upper()
            net_pay = float(record.get('net_salary', 0.0))
            if "USD" in currency:
                rate = record.get('exchange_rate')
                if rate is None or rate == 0: rate = default_rate
                return net_pay * float(rate)
            return net_pay
        except: return 0.0

    def format_date_short(date_str):
        try:
            if isinstance(date_str, (datetime, type(date.today()))):
                return date_str.strftime("%d %b %Y")
            return datetime.strptime(str(date_str), "%Y-%m-%d").strftime("%d %b %Y")
        except: return str(date_str)

    def calculate_tenure(join_date_str):
        try:
            start_date = datetime.strptime(join_date_str, "%d %b %Y").date()
            today = date.today()
            years = today.year - start_date.year
            months = today.month - start_date.month
            if months < 0: years -= 1; months += 12
            return f"{years}y{months}m"
        except: return "0y0m"

    if "db" not in st.session_state: st.session_state.db = load_db()
    if "edit_target" not in st.session_state: st.session_state.edit_target = None

    # --- PDF GENERATOR ---
    def create_pdf(record, emp_static):
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        COLOR_NAVY = (33, 47, 61); COLOR_WHITE = (255, 255, 255); COLOR_TEXT = (50, 50, 50)
        pdf.set_fill_color(*COLOR_NAVY); pdf.rect(0, 0, 210, 45, 'F') 
        pdf.set_y(15); pdf.set_font("Times", 'B', 36); pdf.set_text_color(*COLOR_WHITE); pdf.cell(0, 10, "SDG Tech", 0, 1, 'C')
        pdf.set_font("Arial", 'B', 9); pdf.set_text_color(200, 200, 200)
        pay_year = record['payment_date'].split('-')[0]
        pdf.cell(0, 8, f"PAYSLIP FOR {record['month_label'].upper()} {pay_year}", 0, 1, 'C'); pdf.ln(15)
        pdf.set_text_color(*COLOR_TEXT); y_start = pdf.get_y(); left_x, right_x = 15, 110; line_h = 7
        fmt_date = format_date_short(record['payment_date'])
        
        pdf.set_xy(left_x, y_start); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Name", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['name']}", 0, 1)
        pdf.set_x(left_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Designation", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['designation']}", 0, 1)
        pdf.set_x(left_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Join Date", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['join_date']}", 0, 1)
        
        pdf.set_xy(right_x, y_start); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Payment Date", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {fmt_date}", 0, 1)
        pdf.set_x(right_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Currency", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['currency']}", 0, 1)
        pdf.set_x(right_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Bank Name", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['bank_name']}", 0, 1)
        pdf.set_x(right_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Account No.", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": {emp_static['account_number']}", 0, 1)
        
        if record.get('exchange_rate') and "USD" in record['currency']:
            pdf.set_x(right_x); pdf.set_font("Arial", 'B', 10); pdf.cell(35, line_h, "Exchange Rate", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(50, line_h, f": 1 USD = {record['exchange_rate']:.3f} MYR", 0, 1)
        pdf.ln(10)

        w_desc, w_amt, h_row = 150, 30, 9
        def draw_section(title, items, total_val, is_deduct=False):
            pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 10); 
            pdf.cell(w_desc + w_amt, 8, f"  {title}", 0, 1, 'L', True); pdf.set_font("Arial", '', 10); 
            for item in items:
                if item.get('Amount', 0) > 0:
                    pdf.cell(w_desc, h_row, "  " + item['Description'], 0, 0, 'L', False)
                    pdf.cell(w_amt, h_row, f"{item['Amount']:,.2f}  ", 0, 1, 'R', False)
            pdf.set_fill_color(255, 255, 255); pdf.set_font("Arial", 'B', 10); 
            label = "Total Deductions" if is_deduct else "Total Earnings"; 
            curr = emp_static['currency'].split("(")[0].strip()
            pdf.cell(w_desc, 8, f"{label}  ", "T", 0, 'R', False); 
            pdf.cell(w_amt, 8, f"{curr} {total_val:,.2f}  ", "T", 1, 'R', False); 
            pdf.ln(5)

        earn_items = [i for i in record['earnings_list'] if i.get('Amount', 0) > 0]; total_earn = sum(i['Amount'] for i in earn_items)
        draw_section("EARNINGS", earn_items, total_earn, False)
        deduct_items = [i for i in record['deductions_list'] if i.get('Amount', 0) > 0]; total_deduct = sum(i['Amount'] for i in deduct_items)
        draw_section("DEDUCTIONS", deduct_items, total_deduct, True)
        
        net_pay = total_earn - total_deduct; curr = emp_static['currency'].split("(")[0].strip()
        pdf.set_fill_color(33, 47, 61); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 12)
        pdf.cell(w_desc, 12, "  NET PAYABLE", 0, 0, 'L', True); pdf.cell(w_amt, 12, f"{curr} {net_pay:,.2f}  ", 0, 1, 'R', True)
        pdf.set_text_color(*COLOR_TEXT); pdf.ln(5)
        
        try:
            net_val = round(net_pay, 2)
            dollars = int(net_val); cents = int(round((net_val - dollars) * 100))
            dollars_txt = num2words(dollars, lang='en').upper().replace(",", "")
            cents_txt = num2words(cents, lang='en').upper().replace(",", "")
            if "RM" in emp_static['currency']:
                amount_in_words = f"{dollars_txt} RINGGIT AND {cents_txt} SEN ONLY" if cents > 0 else f"{dollars_txt} RINGGIT ONLY"
            else:
                amount_in_words = f"{dollars_txt} DOLLARS AND {cents_txt} CENTS ONLY" if cents > 0 else f"{dollars_txt} DOLLARS ONLY"
            pdf.set_font("Arial", 'B', 9); pdf.cell(35, 5, "Amount in Words:", 0, 0, 'L')
            pdf.set_font("Arial", 'I', 9); pdf.multi_cell(0, 5, amount_in_words, 0, 'L')
        except Exception as e: pdf.set_font("Arial", 'I', 9); pdf.multi_cell(0, 5, f"ERROR: {str(e)}", 0, 'L')
        
        if record.get('remarks'):
            pdf.ln(5); pdf.set_font("Arial", 'B', 9); pdf.cell(20, 5, "Comment:", 0, 0, 'L')
            pdf.set_font("Arial", '', 9); pdf.multi_cell(0, 5, record['remarks'], 0, 'L')

        pdf.ln(15); pdf.set_font("Arial", 'I', 8); pdf.set_text_color(150, 150, 150); 
        pdf.cell(0, 5, "This is computer generated no signature required.", 0, 1, 'C')
        return pdf.output(dest='S').encode('latin-1', errors='replace')

    # --- SIDEBAR NAV (JS Optimized) ---
    with st.sidebar:
        st.markdown("<h1>SDG Tech</h1>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        # ⚠️ 注意：这里去掉了 on_change=st.rerun，解决了 Warning
        page = st.radio("MENU", ["Dashboard", "Payroll Center", "Leave Tracker", "Manage Employees", "⚙️ Settings"], label_visibility="collapsed")
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if st.button("Log Out"):
            del st.session_state["password_correct"]
            st.rerun()
        st.caption("v17.11 Final JS")

    today = date.today(); default_month_idx = (today.month - 2) % 12 
    month_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    # --- DASHBOARD ---
    if page == "Dashboard":
        st.markdown("<h2>Executive Dashboard</h2>", unsafe_allow_html=True)
        current_global_rate = st.session_state.db['settings']['usd_rate']
        
        col_d1, col_d2 = st.columns([1, 4])
        dash_month = col_d1.selectbox("View Month", month_list, index=default_month_idx)
        dash_year = col_d2.number_input("Year", value=today.year, step=1)
        
        all_recs = st.session_state.db['records']
        month_recs = [r for r in all_recs if r['month_label'] == dash_month and str(dash_year) in r['payment_date']]
        
        total_payout_myr = sum(convert_record_to_myr(r, current_global_rate) for r in month_recs if r['status'] == 'Paid')
        
        paid_recs_count = sum(1 for r in month_recs if r['status'] == 'Paid')
        active_emp_count = sum(1 for e in st.session_state.db['employees'].values() if e.get('status') == 'Active')
        
        m1, m2 = st.columns(2)
        with m1: st.markdown(f'<div class="metric-card-purple"><div class="metric-label">TOTAL PAYOUT (Est. MYR)</div><div class="metric-value">RM {total_payout_myr:,.2f}</div></div>', unsafe_allow_html=True)
        with m2: st.markdown(f'<div class="metric-card-blue"><div class="metric-label">PAID EMPLOYEES ({dash_month})</div><div class="metric-value">{paid_recs_count} / {active_emp_count}</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        c_chart, c_summary = st.columns([3, 1])
        with c_chart:
            st.markdown('<div class="chart-box"><div style="font-size:16px; font-weight:600; margin-bottom:15px;">Payroll Cost Overview (MYR)</div>', unsafe_allow_html=True)
            chart_data = {"Month": [], "Expense (MYR)": []}
            for i, m_short in enumerate([calendar.month_abbr[i] for i in range(1, 13)]):
                m_full = month_list[i]; m_total = 0.0
                for r in all_recs:
                    if r['month_label'] == m_full and r['status'] == 'Paid' and str(dash_year) in r['payment_date']:
                        m_total += convert_record_to_myr(r, current_global_rate)
                chart_data["Month"].append(m_short); chart_data["Expense (MYR)"].append(m_total)
            st.bar_chart(pd.DataFrame(chart_data), x="Month", y="Expense (MYR)", color="#7f56d9", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with c_summary:
            year_total_myr = sum(convert_record_to_myr(r, current_global_rate) for r in all_recs if r['status'] == 'Paid' and str(dash_year) in r['payment_date'])
            st.markdown(f'<div class="summary-card-right"><div class="summary-title">TOTAL PAID {dash_year}</div><div class="summary-val">RM {year_total_myr:,.0f}</div><div style="color:#888; font-size:12px; margin-top:5px;">Est. in MYR</div></div>', unsafe_allow_html=True)

        # [DASHBOARD TABLE]
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Payroll Data")
        
        if st.session_state.db['employees']:
            month_rec_map = {r['employee_id']: r for r in month_recs}
            table_data = []
            idx_counter = 1 
            for emp_id, info in st.session_state.db['employees'].items():
                if info.get('status') != 'Active' and emp_id not in month_rec_map: continue
                rec = month_rec_map.get(emp_id)
                
                row = {"No.": idx_counter, "Employee": emp_id, "Role": info["designation"]}
                if rec:
                    curr_sym = info['currency'].split('(')[0]
                    row["Net Pay"] = f"{curr_sym} {rec['net_salary']:,.2f}"
                    row["Status"] = rec['status']
                else:
                    row["Net Pay"] = "-"
                    row["Status"] = "Pending"
                table_data.append(row)
                idx_counter += 1
            
            if table_data:
                # [MODIFICATION 1] No Scrollbar on Dashboard + Date Removed
                df_dash = pd.DataFrame(table_data)
                h_dash = (len(df_dash) + 1) * 35 + 3 
                st.dataframe(df_dash, use_container_width=True, hide_index=True, height=h_dash)
            else:
                st.info("No data available.")
        else: st.info("No data available.")

    # --- PAYROLL CENTER ---
    elif page == "Payroll Center":
        st.header("Payroll Center")
        
        c_month, c_year, c_btn = st.columns([2, 1.5, 3])
        with c_month: sel_month = st.selectbox("Month", month_list, index=default_month_idx)
        with c_year: sel_year = st.selectbox("Year", [today.year - 1, today.year, today.year + 1], index=1)
        
        active_emps_only = [e for e, d in st.session_state.db['employees'].items() if d.get('status') == 'Active']
        btn_text = f"Generate {sel_month[:3]} Payroll"
        
        with c_btn:
            st.markdown('<div class="input-label-spacer"></div>', unsafe_allow_html=True)
            if st.button(btn_text, type="primary", use_container_width=True):
                count_gen = 0
                default_rate = st.session_state.db['settings']['usd_rate']
                current_recs_ids = [r['employee_id'] for r in st.session_state.db['records'] if r['month_label'] == sel_month and str(sel_year) in r['payment_date']]
                
                for emp_id in active_emps_only:
                    if emp_id in current_recs_ids: continue 
                    emp_data = st.session_state.db['employees'][emp_id]
                    last_rec = get_last_record(emp_id, st.session_state.db)
                    new_earnings = last_rec['earnings_list'] if last_rec else [{"Description": "Basic Salary", "Amount": emp_data.get('basic_salary', 0.0)}]
                    new_deductions = last_rec['deductions_list'] if last_rec else [{"Description": "Unpaid Leave", "Amount": 0.0}]
                    use_rate = last_rec['exchange_rate'] if last_rec else default_rate
                    net = sum(e['Amount'] for e in new_earnings) - sum(d['Amount'] for d in new_deductions)
                    
                    st.session_state.db['records'].append({
                        "id": f"{emp_id}_{sel_month}_{sel_year}", "employee_id": emp_id, "month_label": sel_month, "payment_date": str(date.today()),
                        "earnings_list": new_earnings, "deductions_list": new_deductions,
                        "net_salary": net, "currency": emp_data['currency'], "remarks": "", "status": "Unpaid", "exchange_rate": use_rate
                    })
                    count_gen += 1
                save_db(st.session_state.db)
                if count_gen > 0: st.success(f"Generated {count_gen} records!")
                else: st.warning("No new records.")
                st.rerun()

        st.markdown("<div style='margin-bottom: 5px'></div>", unsafe_allow_html=True)

        all_emps = [e_id for e_id, e_data in st.session_state.db['employees'].items() if e_data.get('status', 'Active') == 'Active']
        
        if not all_emps: st.warning("No 'Active' employees found.")
        else:
            st.subheader("1. Workbench (Edit/Create)")
            c_emp1, c_emp2 = st.columns([1, 2])
            edit_target_id = st.session_state.get('edit_target')
            try: sel_idx = all_emps.index(edit_target_id) if edit_target_id in all_emps else 0
            except: sel_idx = 0
            with c_emp1: sel_emp = st.selectbox("Select Employee:", all_emps, index=sel_idx)
            
            if edit_target_id and sel_emp != edit_target_id:
                st.session_state.edit_target = None
                st.rerun()

            emp_leaves = [l for l in st.session_state.db['leave_records'] if l['employee_id'] == sel_emp]
            leave_txt = "No recent leaves."
            if emp_leaves:
                l_df = pd.DataFrame(emp_leaves); l_df['dt'] = pd.to_datetime(l_df['date'])
                last_leave = l_df.sort_values('dt', ascending=False).iloc[0]
                leave_txt = f"Recent: {last_leave['date']} ({last_leave['reason']}, {last_leave['days']}d)"
            
            with c_emp2:
                st.markdown('<div class="input-label-spacer"></div>', unsafe_allow_html=True)
                st.info(f"Context: {leave_txt}")

            emp_static = st.session_state.db['employees'][sel_emp]
            last_rec = get_last_record(sel_emp, st.session_state.db)
            curr_rec = next((r for r in st.session_state.db['records'] if r['employee_id'] == sel_emp and r['month_label'] == sel_month and str(sel_year) in r['payment_date']), None)
            
            master_basic = emp_static.get('basic_salary', 0.0)
            default_earnings = [{"Description": "Basic Salary", "Amount": master_basic}]
            d_earn = curr_rec['earnings_list'] if curr_rec else (last_rec['earnings_list'] if last_rec else default_earnings)
            d_deduct = curr_rec['deductions_list'] if curr_rec else (last_rec['deductions_list'] if last_rec else [{"Description": "Unpaid Leave", "Amount": 0.0}])
            rem_val = curr_rec.get('remarks', "") if curr_rec else ""
            default_rate = st.session_state.db['settings']['usd_rate']
            saved_rate = curr_rec.get('exchange_rate', default_rate) if curr_rec else default_rate
            
            try: val_date = datetime.strptime(curr_rec['payment_date'], "%Y-%m-%d").date() if curr_rec else date.today()
            except: val_date = date.today()

            with st.form("payroll_form"):
                if "USD" in emp_static['currency']:
                    c_rate, c_space = st.columns([1, 3])
                    txn_rate = c_rate.number_input("💱 Exchange Rate (1 USD = ? MYR)", value=float(saved_rate), step=0.01)
                else: txn_rate = 1.0
                ce1, ce2 = st.columns(2)
                with ce1: st.caption("Earnings (+)"); e_earn = st.data_editor(pd.DataFrame(d_earn), num_rows="dynamic", key=f"e_{sel_emp}", column_config={"Amount": st.column_config.NumberColumn(format="%.2f")}, use_container_width=True)
                with ce2: st.caption("Deductions (-)"); e_deduct = st.data_editor(pd.DataFrame(d_deduct), num_rows="dynamic", key=f"d_{sel_emp}", column_config={"Amount": st.column_config.NumberColumn(format="%.2f")}, use_container_width=True)
                cr1, cr2 = st.columns([3, 1])
                rem = cr1.text_input("Remarks (Press Enter to Save)", value=rem_val)
                pay_date = cr2.date_input("Payment Date", value=val_date)
                
                if st.form_submit_button("💾 Save Calculation", type="primary"):
                    net = e_earn['Amount'].sum() - e_deduct['Amount'].sum()
                    st.session_state.db['records'] = [r for r in st.session_state.db['records'] if not (r['employee_id'] == sel_emp and r['month_label'] == sel_month and str(sel_year) in r['payment_date'])]
                    st.session_state.db['records'].append({
                        "id": f"{sel_emp}_{sel_month}_{sel_year}", "employee_id": sel_emp, "month_label": sel_month, "payment_date": str(pay_date),
                        "earnings_list": e_earn.to_dict('records'), "deductions_list": e_deduct.to_dict('records'),
                        "net_salary": net, "currency": emp_static['currency'], "remarks": rem, "status": "Unpaid", "exchange_rate": txn_rate
                    })
                    st.session_state.edit_target = None
                    save_db(st.session_state.db); st.success(f"Saved for {sel_emp}!"); st.rerun()

            st.markdown("---")
            st.subheader(f"2. Payslip Records ({sel_month} {sel_year})")
            month_recs = {r['employee_id']: r for r in st.session_state.db['records'] if r['month_label'] == sel_month and str(sel_year) in r['payment_date']}
            
            # --- PAYSLIP TABLE ---
            table_rows = []
            idx_counter = 1 
            for emp_id in all_emps:
                emp_static = st.session_state.db['employees'][emp_id]
                rec = month_recs.get(emp_id)
                
                if rec:
                    curr_sym = emp_static['currency'].split('(')[0]
                    row = {
                        "No.": idx_counter,
                        "Employee": emp_id,
                        "Net Pay": f"{curr_sym} {rec['net_salary']:,.2f}",
                        "Status": "✅ Paid" if rec['status'] == 'Paid' else "⏳ Pending"
                    }
                else:
                    row = {
                        "No.": idx_counter,
                        "Employee": emp_id,
                        "Net Pay": "-",
                        "Status": "Unprocessed"
                    }
                table_rows.append(row)
                idx_counter += 1
            
            # Overview Table
            if table_rows:
                # [MODIFICATION 2] Payslip Table - Auto Expand Height + No Date
                df_pay = pd.DataFrame(table_rows)
                h_pay = (len(df_pay) + 1) * 35 + 3
                st.dataframe(df_pay, use_container_width=True, hide_index=True, height=h_pay)
            
            # Actions Area
            st.markdown("### 🛠️ Actions (Manage)")
            for emp_id in all_emps:
                if emp_id in month_recs:
                    rec = month_recs[emp_id]
                    with st.expander(f"Manage: {emp_id}"):
                        # [FIX] Buttons side-by-side [1, 1, 5] ratio
                        c_a, c_b, c_space = st.columns([1, 1, 5])
                        
                        if c_a.button("Edit", key=f"edt_{emp_id}"): 
                            st.session_state.edit_target = emp_id; st.rerun()
                        
                        pdf_bytes = create_pdf(rec, st.session_state.db['employees'][emp_id])
                        safe_name = emp_id.replace(" ", "_")
                        c_b.download_button("Download", data=pdf_bytes, file_name=f"Payslip_{safe_name}.pdf", mime="application/pdf", key=f"btn_{emp_id}")
                        
                        is_paid = (rec['status'] == 'Paid')
                        def update_status(rid=rec['id']):
                            for r in st.session_state.db['records']:
                                if r['id'] == rid: r['status'] = 'Unpaid' if r['status'] == 'Paid' else 'Paid'
                            save_db(st.session_state.db)
                        st.checkbox("Mark as Paid", value=is_paid, key=f"chk_{emp_id}", on_change=update_status, args=(rec['id'],))

    # --- MANAGE EMPLOYEES ---
    elif page == "Manage Employees":
        st.header("Manage Employees")
        st.markdown("### Add New Employee")
        with st.container():
            c1, c2 = st.columns(2); name = c1.text_input("Name"); role = c2.text_input("Designation")
            # [DATE FIX] Allow dates from 1900
            c3, c4 = st.columns(2); join = c3.date_input("Join Date", min_value=date(1980,1,1)); dob = c4.date_input("Date of Birth", min_value=date(1900,1,1), max_value=date.today())
            c5, c6 = st.columns(2); curr = c5.selectbox("Currency", ["RM (MYR)", "$ (USD)"]); bank = c6.text_input("Bank")
            c7, c8 = st.columns(2); acc = c7.text_input("A/C No"); 
            if st.button("Save New Employee", type="primary"):
                if name:
                    st.session_state.db['employees'][name] = {
                        "name": name, "designation": role, "join_date": join.strftime("%d %b %Y"), "date_of_birth": dob.strftime("%d %b %Y"),
                        "currency": curr, "bank_name": bank, "account_number": acc,
                        "basic_salary": 0.0, "status": "Active", "master_remark": "",
                        "last_increment": None, "last_bonus": None
                    }
                    save_db(st.session_state.db); st.success("Added!"); st.rerun()

        st.markdown("---")
        st.subheader("Employee Details")
        data_list = []
        for e_id, e in st.session_state.db['employees'].items():
            inc_txt = f"{e['last_increment']['date']} (+{e['last_increment']['percentage']}%)" if e.get("last_increment") else "-"
            bon_txt = f"{e['last_bonus']['year']}: {e['last_bonus']['amount']:,.0f}" if e.get("last_bonus") else "-"
            st_flag = "🟢" if e.get('status') == 'Active' else "⚪"
            dob_txt = e.get('date_of_birth', '-')

            data_list.append({
                "Status": st_flag, "Name": e['name'], "Role": e['designation'],
                "Basic Salary": e.get('basic_salary', 0.0), "Join Date": e['join_date'],
                "Tenure": calculate_tenure(e['join_date']), "Date of Birth": dob_txt,
                "Last Increment": inc_txt, "Last Bonus": bon_txt,
                "Remark": e.get('master_remark', ''), "✏️": False, "🗑️": False
            })
        
        if data_list:
            # [MODIFICATION 3] Manage Employees Table - Auto Expand Height
            df = pd.DataFrame(data_list)
            h_manage = (len(df) + 1) * 35 + 3
            edited_df = st.data_editor(
                df, use_container_width=True, height=h_manage,
                column_config={
                    "Status": st.column_config.TextColumn(width="small", help="Green=Active, Grey=Inactive"),
                    "Basic Salary": st.column_config.NumberColumn(format="%.2f", disabled=True),
                    "Join Date": st.column_config.TextColumn(disabled=True),
                    "Date of Birth": st.column_config.TextColumn(disabled=True),
                    "Last Increment": st.column_config.TextColumn(disabled=True),
                    "Last Bonus": st.column_config.TextColumn(disabled=True),
                    "Tenure": st.column_config.TextColumn(help="YearsMonths", disabled=True),
                    "✏️": st.column_config.CheckboxColumn(label="✏️", help="Edit Details"),
                    "🗑️": st.column_config.CheckboxColumn(label="🗑️", help="Delete Employee")
                },
                disabled=["Status", "Name", "Role"], hide_index=True
            )
            
            changes_detected = False
            for index, row in edited_df.iterrows():
                nm = row['Name']
                orig = st.session_state.db['employees'][nm]
                if row['Remark'] != orig.get('master_remark', ''):
                    orig['master_remark'] = row['Remark']; changes_detected = True
            if changes_detected: save_db(st.session_state.db); st.toast("Updated remarks!")

            rows_to_delete = edited_df[edited_df['🗑️'] == True]
            if not rows_to_delete.empty:
                st.error(f"⚠️ Deleting {len(rows_to_delete)} employees.")
                if st.button("🚨 Confirm Delete"):
                    for idx, row in rows_to_delete.iterrows():
                        target = row['Name']
                        if target in st.session_state.db['employees']: del st.session_state.db['employees'][target]
                    save_db(st.session_state.db); st.success("Deleted!"); st.rerun()

            rows_to_edit = edited_df[edited_df['✏️'] == True]
            if not rows_to_edit.empty:
                st.markdown("### ✏️ Edit Employee Details")
                for idx, row in rows_to_edit.iterrows():
                    target_emp = row['Name']
                    curr_data = st.session_state.db['employees'][target_emp]
                    st.info(f"Editing: **{target_emp}**")
                    with st.form(f"edit_full_{target_emp}"):
                        c_a, c_b = st.columns(2)
                        status_opts = ["Active", "Inactive"]
                        c_stat = curr_data.get('status')
                        if c_stat == 'Resigned': c_stat = 'Inactive'
                        curr_status_idx = 0 if c_stat == 'Active' else 1
                        new_status = c_a.selectbox("Status", status_opts, index=curr_status_idx)
                        new_salary = c_b.number_input("Basic Salary", value=float(curr_data.get('basic_salary', 0.0)), step=100.0)
                        
                        try: def_join = datetime.strptime(curr_data['join_date'], "%d %b %Y").date()
                        except: def_join = date.today()
                        new_join = st.date_input("Join Date", value=def_join)
                        
                        try: def_dob = datetime.strptime(curr_data.get('date_of_birth', ''), "%d %b %Y").date()
                        except: def_dob = date.today()
                        # [DATE FIX]
                        new_dob = st.date_input("Date of Birth", value=def_dob, min_value=date(1900,1,1), max_value=date.today())

                        st.markdown("**Last Increment**"); ci1, ci2 = st.columns(2)
                        try: def_inc_date = datetime.strptime(curr_data['last_increment']['date'], "%d %b %Y").date()
                        except: def_inc_date = date.today()
                        def_inc_pct = float(curr_data['last_increment']['percentage']) if curr_data.get('last_increment') else 0.0
                        new_inc_date = ci1.date_input("Date", value=def_inc_date, key=f"id_{target_emp}")
                        new_inc_pct = ci2.number_input("Percentage (%)", value=def_inc_pct, step=1.0, key=f"ip_{target_emp}")
                        
                        st.markdown("**Last Bonus**"); cb1, cb2 = st.columns(2)
                        def_bon_year = int(curr_data['last_bonus']['year']) if curr_data.get('last_bonus') else date.today().year
                        def_bon_amt = float(curr_data['last_bonus']['amount']) if curr_data.get('last_bonus') else 0.0
                        new_bon_year = cb1.number_input("Year", value=def_bon_year, step=1, key=f"by_{target_emp}")
                        new_bon_amt = cb2.number_input("Amount", value=def_bon_amt, step=100.0, key=f"ba_{target_emp}")
                        
                        if st.form_submit_button("💾 Save Changes"):
                            curr_data['status'] = new_status
                            curr_data['basic_salary'] = new_salary
                            curr_data['join_date'] = new_join.strftime("%d %b %Y")
                            curr_data['date_of_birth'] = new_dob.strftime("%d %b %Y")
                            if new_inc_pct > 0: curr_data['last_increment'] = {"date": new_inc_date.strftime("%d %b %Y"), "percentage": new_inc_pct}
                            if new_bon_amt > 0: curr_data['last_bonus'] = {"year": int(new_bon_year), "amount": new_bon_amt}
                            save_db(st.session_state.db); st.success("Updated!"); st.rerun()
        else: st.info("No employees found.")

    elif page == "⚙️ Settings":
        st.header("System Settings")
        st.divider()
        st.info("Default Exchange Rate (1 USD = ? MYR)")
        current = st.session_state.db['settings']['usd_rate']
        new_rate = st.number_input("Rate", value=current, step=0.01)
        if st.button("Update Rate", type="primary"):
            st.session_state.db['settings']['usd_rate'] = new_rate
            save_db(st.session_state.db); st.success("Updated!")
