import os
import re
import uuid

import pandas as pd
import pdfplumber
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "research_portal_secret_2024")

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

allowed_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if allowed_origins_env == "*":
    CORS(app, resources={r"/api/*": {"origins": "*"}})
else:
    allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

LINE_ITEM_ALIASES = {
    "Revenue": [
        "revenue", "net sales", "total revenue", "net revenue",
        "sales", "total net revenue", "total sales", "gross revenue"
    ],
    "Cost of Goods Sold": [
        "cost of goods sold", "cost of sales", "cost of revenue",
        "cogs", "cost of products sold"
    ],
    "Gross Profit": [
        "gross profit", "gross margin", "gross income"
    ],
    "Operating Expenses": [
        "operating expenses", "operating costs", "total operating expenses",
        "selling general and administrative", "sg&a", "operating expenditure"
    ],
    "Research & Development": [
        "research and development", "r&d", "r & d expenses",
        "research & development expenses"
    ],
    "Operating Income": [
        "operating income", "operating profit", "income from operations",
        "profit from operations", "ebit"
    ],
    "Interest Expense": [
        "interest expense", "finance costs", "interest cost",
        "interest charges", "net interest expense"
    ],
    "Profit Before Tax": [
        "profit before tax", "pbt", "income before tax",
        "earnings before tax", "pre-tax income", "pretax income"
    ],
    "Tax Expense": [
        "income tax", "tax expense", "provision for income taxes",
        "income tax expense", "income taxes"
    ],
    "Net Income": [
        "net income", "net profit", "profit after tax", "pat",
        "net earnings", "profit for the year", "profit for the period",
        "net income attributable", "net profit after tax"
    ],
    "Depreciation & Amortization": [
        "depreciation", "amortization", "depreciation and amortization",
        "d&a", "depreciation & amortization"
    ],
    "EBITDA": [
        "ebitda", "earnings before interest tax depreciation amortization"
    ],
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(pdf_path):
    pages_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    except Exception as exc:
        print(f"[ERROR] Text extraction failed: {exc}")
    return pages_text


def detect_currency(all_text):
    combined = " ".join(all_text).lower()

    currency = "Unclear"
    if "usd" in combined or "u.s. dollar" in combined or "$" in combined:
        currency = "USD"
    elif "inr" in combined or "indian rupee" in combined:
        currency = "INR"
    elif "eur" in combined or "euro" in combined:
        currency = "EUR"
    elif "gbp" in combined or "british pound" in combined:
        currency = "GBP"
    elif "cny" in combined or "rmb" in combined or "yuan" in combined:
        currency = "CNY"

    units = "Unclear"
    if "in crores" in combined or "crore" in combined:
        units = "Crores"
    elif "in millions" in combined or "million" in combined:
        units = "Millions"
    elif "in thousands" in combined or "thousand" in combined:
        units = "Thousands"
    elif "in billions" in combined or "billion" in combined:
        units = "Billions"

    return {"currency": currency, "units": units}


def detect_years(all_text):
    combined = " ".join(all_text)
    years = re.findall(r"\b((?:19|20)\d{2})\b", combined)
    unique_years = sorted(set(int(year) for year in years))
    return [year for year in unique_years if 1990 <= year <= 2030]


def parse_number(raw):
    if not raw:
        return None

    raw = raw.strip()
    if re.match(r"^\([\d,\.]+\)$", raw):
        raw = "-" + raw[1:-1]
    raw = raw.replace(",", "")

    try:
        return float(raw)
    except ValueError:
        return None


def match_line_item(line_lower):
    for canonical, aliases in LINE_ITEM_ALIASES.items():
        for alias in aliases:
            if alias in line_lower:
                return canonical
    return None


def extract_financial_lines(pages_text, detected_years):
    results = []

    for page_text in pages_text:
        lines = page_text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()
            canonical = match_line_item(line_lower)
            if not canonical:
                continue

            numbers_raw = re.findall(r"[\(\-]?[\d,]+(?:\.\d+)?\)?", line)
            numbers_raw = [n for n in numbers_raw if not re.match(r"^\d{4}$", n.replace(",", ""))]

            if not numbers_raw:
                results.append({
                    "line_item": canonical,
                    "year": "Unknown",
                    "value": None,
                    "confidence": "Missing"
                })
                continue

            if detected_years and len(numbers_raw) == len(detected_years):
                for year, raw_val in zip(sorted(detected_years, reverse=True), numbers_raw):
                    value = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": year,
                        "value": value,
                        "confidence": "OK" if value is not None else "Low Confidence"
                    })
            elif detected_years and len(numbers_raw) >= 1:
                sorted_years = sorted(detected_years, reverse=True)
                for i, raw_val in enumerate(numbers_raw):
                    year = sorted_years[i] if i < len(sorted_years) else "Unknown"
                    value = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": year,
                        "value": value,
                        "confidence": "OK" if value is not None else "Low Confidence"
                    })
            else:
                for raw_val in numbers_raw:
                    value = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": "Unknown",
                        "value": value,
                        "confidence": "OK" if value is not None else "Low Confidence"
                    })

    return results


def deduplicate_results(results):
    priority = {"OK": 0, "Low Confidence": 1, "Missing": 2, "Review Required": 3}
    best = {}

    for row in results:
        key = (row["line_item"], row["year"])
        if key not in best:
            best[key] = row
        elif priority.get(row["confidence"], 9) < priority.get(best[key]["confidence"], 9):
            best[key] = row

    return list(best.values())


def fill_missing_items(results, detected_years):
    found_items = set(row["line_item"] for row in results)
    years_to_use = detected_years if detected_years else ["Unknown"]

    for canonical in LINE_ITEM_ALIASES:
        if canonical not in found_items:
            for year in years_to_use:
                results.append({
                    "line_item": canonical,
                    "year": year,
                    "value": None,
                    "confidence": "Missing"
                })

    return results


def generate_output_file(results, currency_info, output_folder, base_name):
    rows = []
    for row in results:
        rows.append({
            "Line Item": row["line_item"],
            "Year": row["year"],
            "Value": row["value"] if row["value"] is not None else "NULL",
            "Currency": currency_info["currency"],
            "Units": currency_info["units"],
            "Confidence Flag": row["confidence"]
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["Line Item", "Year"]).reset_index(drop=True)

    uid = str(uuid.uuid4())[:8]
    csv_filename = f"{base_name}_{uid}.csv"
    xlsx_filename = f"{base_name}_{uid}.xlsx"

    csv_path = os.path.join(output_folder, csv_filename)
    xlsx_path = os.path.join(output_folder, xlsx_filename)

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Financial Data")
        ws = writer.sheets["Financial Data"]
        for col in ws.columns:
            max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    return csv_path, xlsx_path


def process_pdf_file(uploaded_file):
    if uploaded_file is None:
        raise ValueError("No file selected.")

    if uploaded_file.filename == "":
        raise ValueError("No file selected.")

    if not allowed_file(uploaded_file.filename):
        raise ValueError("Only PDF files are accepted.")

    filename = secure_filename(uploaded_file.filename)
    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    uploaded_file.save(pdf_path)

    try:
        pages_text = extract_text(pdf_path)
        if not pages_text:
            raise ValueError("Could not extract text from the PDF. It may be scanned/image-based.")

        currency_info = detect_currency(pages_text)
        detected_years = detect_years(pages_text)
        detected_years = sorted(detected_years)[-5:] if detected_years else []

        raw_results = extract_financial_lines(pages_text, detected_years)
        deduped = deduplicate_results(raw_results)
        final_results = fill_missing_items(deduped, detected_years)

        base_name = os.path.splitext(filename)[0]
        csv_path, xlsx_path = generate_output_file(
            final_results, currency_info, app.config["OUTPUT_FOLDER"], base_name
        )

        return {
            "csv_filename": os.path.basename(csv_path),
            "xlsx_filename": os.path.basename(xlsx_path),
            "currency": currency_info["currency"],
            "units": currency_info["units"],
            "years": detected_years,
            "row_count": len([row for row in final_results if row["confidence"] != "Missing"]),
        }
    finally:
        try:
            os.remove(pdf_path)
        except Exception:
            pass


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    uploaded_file = request.files.get("pdf_file")

    try:
        result = process_pdf_file(uploaded_file)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    except Exception:
        flash("Unexpected error while processing file.", "error")
        return redirect(url_for("index"))

    flash("Extraction complete! Download your file below.", "success")
    return render_template(
        "index.html",
        csv_file=result["csv_filename"],
        xlsx_file=result["xlsx_filename"],
        currency=result["currency"],
        units=result["units"],
        years=result["years"],
        row_count=result["row_count"],
    )


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/upload", methods=["POST"])
def api_upload():
    uploaded_file = request.files.get("pdf_file")

    try:
        result = process_pdf_file(uploaded_file)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Unexpected error: {exc}"}), 500

    csv_url = url_for("download", filename=result["csv_filename"], _external=True)
    xlsx_url = url_for("download", filename=result["xlsx_filename"], _external=True)

    return jsonify(
        {
            "success": True,
            "message": "Extraction complete.",
            "data": {
                "currency": result["currency"],
                "units": result["units"],
                "years": result["years"],
                "row_count": result["row_count"],
                "files": {
                    "csv": {"filename": result["csv_filename"], "url": csv_url},
                    "xlsx": {"filename": result["xlsx_filename"], "url": xlsx_url},
                },
            },
        }
    ), 200


@app.route("/download/<filename>")
def download(filename):
    safe_name = secure_filename(filename)
    file_path = os.path.join(app.config["OUTPUT_FOLDER"], safe_name)

    if not os.path.exists(file_path):
        flash("File not found or expired.", "error")
        return redirect(url_for("index"))

    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
