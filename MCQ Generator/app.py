import os
from flask import Flask, render_template, request, send_file
import pdfplumber
import docx
from werkzeug.utils import secure_filename
import google.generativeai as genai
from fpdf import FPDF

# --- Configuration ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'docx'}

# --- Gemini API Setup ---
os.environ["GOOGLE_API_KEY"] = "AIzaSyAXYbHEDbbXh-Vzr53YN395eeKIfXmb7iI"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

# --- Utilities ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            return ''.join([page.extract_text() for page in pdf.pages if page.extract_text()])
    elif ext == 'docx':
        doc = docx.Document(file_path)
        return ' '.join([para.text for para in doc.paragraphs])
    elif ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    return None

def Question_mcqs_generator(input_text, num_questions):
    prompt = f"""
    You are an AI assistant helping generate multiple-choice questions (MCQs) based on the following text:
    '{input_text}'
    Please generate {num_questions} MCQs. Each MCQ should include:
    - A clear question
    - Four answer options labeled A), B), C), D)
    - A correct answer labeled "Correct Answer:"
    
    Format:
    ## MCQ
    Question: [question]
    A) [option A]
    B) [option B]
    C) [option C]
    D) [option D]
    Correct Answer: [correct option letter]
    """
    response = model.generate_content(prompt).text.strip()
    return response

def parse_mcqs(raw_text):
    parsed = []
    for mcq in raw_text.split("## MCQ"):
        mcq = mcq.strip()
        if not mcq:
            continue
        try:
            question = mcq.split("A)")[0].replace("Question:", "").strip()
            option_a = mcq.split("A)")[1].split("B)")[0].strip()
            option_b = mcq.split("B)")[1].split("C)")[0].strip()
            option_c = mcq.split("C)")[1].split("D)")[0].strip()
            option_d = mcq.split("D)")[1].split("Correct Answer:")[0].strip()
            correct = mcq.split("Correct Answer:")[1].strip()

            parsed.append({
                "question": question,
                "options": {
                    "A": option_a,
                    "B": option_b,
                    "C": option_c,
                    "D": option_d
                },
                "answer": correct
            })
        except Exception as e:
            print("Error parsing MCQ:", e)
    return parsed

def save_mcqs_to_file(mcqs, filename):
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(mcqs)
    return path

def create_pdf(mcqs, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for mcq in mcqs.split("## MCQ"):
        if mcq.strip():
            pdf.multi_cell(0, 10, mcq.strip())
            pdf.ln(5)
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(path)
    return path

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_mcqs():
    if 'file' not in request.files:
        return "No file uploaded."

    file = request.files['file']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        text = extract_text_from_file(file_path)
        if not text:
            return "Failed to extract text from file."

        num_questions = int(request.form['num_questions'])
        mcqs_raw = Question_mcqs_generator(text, num_questions)

        # Save files
        base_name = filename.rsplit('.', 1)[0]
        txt_filename = f"{base_name}_mcqs.txt"
        pdf_filename = f"{base_name}_mcqs.pdf"
        save_mcqs_to_file(mcqs_raw, txt_filename)
        create_pdf(mcqs_raw, pdf_filename)

        # Parse MCQs for HTML display
        parsed_mcqs = parse_mcqs(mcqs_raw)

        return render_template('results.html', mcqs=parsed_mcqs,
                               txt_filename=txt_filename,
                               pdf_filename=pdf_filename)
    return "Invalid file type."

@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    return send_file(path, as_attachment=True)

# --- Main Entry ---
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    app.run(debug=True)
