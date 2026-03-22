import streamlit as st
from langchain_openai import ChatOpenAI
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt
from fpdf import FPDF
import json
import re
import io

st.set_page_config(page_title="ATS Resume & PDF/Word Generator", page_icon="📄", layout="wide")

# --- 1. ROBUST TEXT CLEANING (Fixes PDF Generation Errors) ---
def clean_for_pdf(text):
    """Replaces non-Latin-1 characters that cause FPDF to crash."""
    if not text:
        return ""
    # Replace common problematic characters
    replacements = {
        "\u2013": "-", # en dash
        "\u2014": "-", # em dash
        "\u2018": "'", # left single quote
        "\u2019": "'", # right single quote
        "\u201c": '"', # left double quote
        "\u201d": '"', # right double quote
        "\u2022": "*", # bullet point
        "\u2026": "...", # ellipsis
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final fallback: encode to latin-1 and ignore anything else
    return text.encode('latin-1', 'replace').decode('latin-1')

# --- 2. HELPERS: TEXT EXTRACTION ---
def extract_text(uploaded_file):
    if uploaded_file is None:
        return ""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    try:
        if file_ext == 'pdf':
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            return "\n".join([page.get_text() for page in doc])
        elif file_ext == 'docx':
            doc = Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return ""
    return ""

# --- 3. HELPERS: WORD (.DOCX) GENERATION ---
def create_docx(data):
    doc = Document()
    
    # Name and Header
    header = doc.add_paragraph()
    run = header.add_run(data.get("name", "RESUME").upper())
    run.bold = True
    run.font.size = Pt(18)
    header.alignment = 1 # Center
    
    contact = doc.add_paragraph()
    contact.add_run(f"{data.get('email', '')}  |  {data.get('phone', '')}  |  {data.get('location', '')}")
    contact.alignment = 1
    
    def add_section(title, content):
        if content:
            doc.add_heading(title.upper(), level=1)
            p = doc.add_paragraph(content)
            p.style.font.size = Pt(11)

    add_section("Professional Summary", data.get("Professional_Summary"))
    add_section("Core Competencies", data.get("Core_Competencies"))
    add_section("Work Experience", data.get("Work_Experience"))
    add_section("Education", data.get("Education"))
    add_section("Certifications", data.get("Certifications"))

    file_stream = io.BytesIO()
    doc.save(file_stream)
    return file_stream.getvalue()

# --- 4. HELPERS: PDF GENERATION (The Fix is Here) ---
def create_pdf(data):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Name
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, clean_for_pdf(data.get("name", "RESUME")).upper(), ln=True, align='C')
        
        # Contact
        pdf.set_font("Helvetica", '', 10)
        contact_info = f"{data.get('email', '')} | {data.get('phone', '')} | {data.get('location', '')}"
        pdf.cell(0, 5, clean_for_pdf(contact_info), ln=True, align='C')
        pdf.ln(5)

        sections = [
            ("Professional Summary", "Professional_Summary"),
            ("Core Competencies", "Core_Competencies"),
            ("Work Experience", "Work_Experience"),
            ("Education", "Education"),
            ("Certifications", "Certifications")
        ]
        
        for title, key in sections:
            content = data.get(key, "")
            if content:
                pdf.set_font("Helvetica", 'B', 12)
                pdf.set_fill_color(240, 240, 240)
                pdf.cell(0, 8, title.upper(), ln=True, fill=True)
                pdf.ln(2)
                
                pdf.set_font("Helvetica", '', 10)
                # Clean the content specifically for PDF output
                pdf.multi_cell(0, 5, clean_for_pdf(content))
                pdf.ln(4)
                
        return pdf.output() # In fpdf2, .output() returns bytes by default
    except Exception as e:
        st.error(f"PDF Generation Failed: {e}")
        return None

# --- 5. MAIN UI ---
st.title("🎯 ATS Resume Master")
st.markdown("Optimizing for Job Descriptions & Generating PDF/Word Files")

with st.sidebar:
    st.header("🔑 Authentication")
    api_key = st.secrets.get("OPENAI_API_KEY") or st.text_input("OpenAI API Key", type="password")
    st.divider()
    st.info("This app cleans all special AI characters to ensure the PDF renders perfectly.")

c1, c2 = st.columns(2)
with c1:
    jd_input = st.text_area("📋 Paste Job Description (JD):", height=250)
with c2:
    res_file = st.file_uploader("📄 Upload your Resume (PDF/Docx):", type=["pdf", "docx"])
    res_input = st.text_area("Or Paste Current Resume Text:", height=150)

if st.button("🚀 Optimize & Create Downloads", type="primary"):
    final_res = res_input if res_input else extract_text(res_file)
    
    if not jd_input or not final_res or not api_key:
        st.error("Please provide JD, Resume, and API Key.")
    else:
        try:
            with st.spinner("Analyzing keywords and formatting..."):
                llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
                
                prompt = f"""
                Act as an expert ATS Resume Writer. Rewrite this resume for the following Job Description.
                Use keywords from the JD. Format in STAR method. Keep it professional.
                
                JD: {jd_input}
                RESUME: {final_res}
                
                OUTPUT strictly as JSON:
                {{
                  "name": "Full Name",
                  "email": "Email",
                  "phone": "Phone",
                  "location": "City, State",
                  "Professional_Summary": "text",
                  "Core_Competencies": "list",
                  "Work_Experience": "bullet points",
                  "Education": "text",
                  "Certifications": "text"
                }}
                """
                
                response = llm.invoke(prompt)
                json_str = re.search(r"\{.*\}", response.content, re.DOTALL).group()
                resume_data = json.loads(json_str)
                
                # Create Files
                docx_bytes = create_docx(resume_data)
                pdf_bytes = create_pdf(resume_data)
                
                if pdf_bytes and docx_bytes:
                    st.success("✅ Both PDF and Word files generated successfully!")
                    
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            label="📥 Download ATS Word (.docx)",
                            data=docx_bytes,
                            file_name="ATS_Optimized_Resume.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    with col_dl2:
                        st.download_button(
                            label="📥 Download ATS PDF (.pdf)",
                            data=pdf_bytes,
                            file_name="ATS_Optimized_Resume.pdf",
                            mime="application/pdf"
                        )
                else:
                    st.error("There was a problem generating the files. Check your content for unusual symbols.")

        except Exception as e:
            st.error(f"Process Error: {e}")
