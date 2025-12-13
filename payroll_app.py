import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
from fpdf import FPDF
from num2words import num2words
import base64

# ================= 配置与连接 =================
st.set_page_config(page_title="SDG Payroll System", layout="wide")
st.title("☁️ SDG Tech Payroll (Google Sheets版)")

# 建立与 Google Sheets 的连接
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 辅助函数：读取数据 ---
def get_data(worksheet_name):
    # 读取指定分页的数据，如果表是空的，返回一个空的 DataFrame
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0) # ttl=0 表示每次都强制刷新，不使用缓存
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()

# --- 辅助函数：写入数据 ---
def update_data(worksheet_name, df):
    conn.update(worksheet=worksheet_name, data=df)
    st.cache_data.clear() # 清除缓存，确保下次读取是最新的

# ================= 侧边栏菜单 =================
menu = st.sidebar.selectbox("Menu", ["Manage Employees", "Payroll Center", "History Records"])

# ================= 1. 员工管理 (Manage Employees) =================
if menu == "Manage Employees":
    st.header("👥 Employee Management")
    
    # 读取当前员工列表
    df_emps = get_data("Employees")
    
    # 确保有基本的列名（防止表格完全空白时报错）
    required_columns = ["EmpID", "Name", "Role", "BasicSalary", "Allowance", "JoinDate"]
    if df_emps.empty:
        df_emps = pd.DataFrame(columns=required_columns)
    else:
        # 确保所有列都存在
        for col in required_columns:
            if col not in df_emps.columns:
                df_emps[col] = ""

    # --- 添加新员工表单 ---
    with st.expander("➕ Add New Employee", expanded=False):
        with st.form("add_emp_form"):
            col1, col2 = st.columns(2)
            e_id = col1.text_input("Employee ID (e.g., E001)")
            e_name = col2.text_input("Full Name")
            e_role = col1.selectbox("Role", ["Manager", "Developer", "Designer", "HR", "Intern"])
            e_date = col2.date_input("Join Date")
            e_salary = col1.number_input("Basic Salary (RM)", min_value=0.0, step=100.0)
            e_allowance = col2.number_input("Fixed Allowance (RM)", min_value=0.0, step=50.0)
            
            submitted = st.form_submit_button("Save Employee")
            
            if submitted:
                if e_id and e_name:
                    # 检查 ID 是否重复
                    if not df_emps.empty and str(e_id) in df_emps['EmpID'].astype(str).values:
                        st.error(f"Error: Employee ID {e_id} already exists!")
                    else:
                        new_emp = pd.DataFrame([{
                            "EmpID": str(e_id),
                            "Name": e_name,
                            "Role": e_role,
                            "BasicSalary": float(e_salary),
                            "Allowance": float(e_allowance),
                            "JoinDate": str(e_date)
                        }])
                        # 合并旧数据和新数据
                        updated_df = pd.concat([df_emps, new_emp], ignore_index=True)
                        update_data("Employees", updated_df)
                        st.success(f"Employee {e_name} added successfully!")
                        st.rerun()
                else:
                    st.warning("Please fill in ID and Name.")

    # --- 显示现有员工 ---
    st.subheader("Current Employee List")
    if not df_emps.empty:
        st.dataframe(df_emps)
    else:
        st.info("No employees found. Please add one above.")


# ================= 2. 发薪中心 (Payroll Center) =================
elif menu == "Payroll Center":
    st.header("💰 Payroll Generator")
    
    df_emps = get_data("Employees")
    
    if df_emps.empty:
        st.warning("Please add employees in the 'Manage Employees' tab first.")
    else:
        # 选择员工
        emp_list = df_emps['Name'].tolist()
        selected_emp_name = st.selectbox("Select Employee", emp_list)
        
        # 自动填充该员工的基本信息
        emp_data = df_emps[df_emps['Name'] == selected_emp_name].iloc[0]
        
        st.info(f"Generating Payslip for: **{selected_emp_name}** ({emp_data['Role']})")
        
        # 输入当月变动数据
        col1, col2, col3 = st.columns(3)
        salary_basic = col1.number_input("Basic Salary", value=float(emp_data['BasicSalary']), disabled=True)
        allowance = col2.number_input("Allowance", value=float(emp_data['Allowance']), disabled=True)
        
        bonus = col3.number_input("Bonus / Commission (RM)", min_value=0.0, value=0.0)
        overtime = col1.number_input("Overtime Pay (RM)", min_value=0.0, value=0.0)
        deduction = col2.number_input("Deductions (Unpaid Leave/Tax)", min_value=0.0, value=0.0)
        
        month_str = st.date_input("For Month", datetime.today()).strftime("%B %Y")
        
        # 计算
        gross_income = salary_basic + allowance + bonus + overtime
        net_salary = gross_income - deduction
        
        st.markdown("---")
        st.metric(label="Total Net Salary", value=f"RM {net_salary:,.2f}")
        
        if st.button("Confirm & Generate Payslip PDF"):
            # 1. 保存到 Records (历史记录)
            df_records = get_data("Records")
            required_rec_cols = ["Date", "Name", "Month", "Basic", "Additions", "Deductions", "NetPay"]
            if df_records.empty:
                df_records = pd.DataFrame(columns=required_rec_cols)
            
            new_record = pd.DataFrame([{
                "Date": datetime.today().strftime("%Y-%m-%d %H:%M:%S"),
                "Name": selected_emp_name,
                "Month": month_str,
                "Basic": salary_basic,
                "Additions": allowance + bonus + overtime,
                "Deductions": deduction,
                "NetPay": net_salary
            }])
            
            updated_records = pd.concat([df_records, new_record], ignore_index=True)
            update_data("Records", updated_records)
            
            # 2. 生成 PDF
            class PDF(FPDF):
                def header(self):
                    self.set_font('Arial', 'B', 16)
                    self.cell(0, 10, 'SDG TECH PAYSLIP', 0, 1, 'C')
                    self.line(10, 20, 200, 20)
                    self.ln(10)

            pdf = PDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            
            # 内容
            pdf.cell(0, 10, f"Employee: {selected_emp_name}", ln=True)
            pdf.cell(0, 10, f"Role: {emp_data['Role']}", ln=True)
            pdf.cell(0, 10, f"Period: {month_str}", ln=True)
            pdf.ln(5)
            
            # 表格
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(100, 10, "Description", 1, 0, 'C', 1)
            pdf.cell(50, 10, "Amount (RM)", 1, 1, 'C', 1)
            
            pdf.cell(100, 10, "Basic Salary", 1, 0)
            pdf.cell(50, 10, f"{salary_basic:,.2f}", 1, 1, 'R')
            
            pdf.cell(100, 10, "Fixed Allowance", 1, 0)
            pdf.cell(50, 10, f"{allowance:,.2f}", 1, 1, 'R')
            
            if bonus > 0:
                pdf.cell(100, 10, "Bonus / Commission", 1, 0)
                pdf.cell(50, 10, f"{bonus:,.2f}", 1, 1, 'R')
                
            if overtime > 0:
                pdf.cell(100, 10, "Overtime", 1, 0)
                pdf.cell(50, 10, f"{overtime:,.2f}", 1, 1, 'R')
                
            if deduction > 0:
                pdf.set_text_color(200, 0, 0)
                pdf.cell(100, 10, "Deductions", 1, 0)
                pdf.cell(50, 10, f"- {deduction:,.2f}", 1, 1, 'R')
                pdf.set_text_color(0, 0, 0)
                
            # 总计
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(100, 12, "NET PAYABLE", 1, 0)
            pdf.cell(50, 12, f"{net_salary:,.2f}", 1, 1, 'R')
            
            # 转为文本 (RM ...)
            try:
                amt_words = num2words(net_salary, lang='en') + " ringgit only"
                pdf.ln(10)
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(0, 10, f"Amount in words: {amt_words.capitalize()}", ln=True)
            except:
                pass
            
            # 生成下载链接
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            b64 = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/pdf;base64,{b64}" download="Payslip_{selected_emp_name}_{month_str}.pdf" style="padding:10px; background-color:green; color:white; text-decoration:none; border-radius:5px;">📥 Download Payslip PDF</a>'
            
            st.success("Payslip generated and saved to Google Sheets!")
            st.markdown(href, unsafe_allow_html=True)

# ================= 3. 历史记录 (History) =================
elif menu == "History Records":
    st.header("📜 Payroll History")
    df_rec = get_data("Records")
    if not df_rec.empty:
        st.dataframe(df_rec)
    else:
        st.info("No payroll records found yet.")
