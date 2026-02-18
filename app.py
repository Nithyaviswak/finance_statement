import os
import re
import uuid
import pandas as pd
import pdfplumber
from flask import Flask, request, render_template, send_file, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "research_portal_secret_2024"

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB max

# ─── Line Item Alias Mapping ───────────────────────────────────────────────────

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


# ─── Helper: Allowed File ──────────────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Step 1: Extract Raw Text from PDF ────────────────────────────────────────

def extract_text(pdf_path):
    """
    Extracts raw text from all pages of a PDF using pdfplumber.
    Returns a list of strings, one per page.
    """
    pages_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    except Exception as e:
        print(f"[ERROR] Text extraction failed: {e}")
    return pages_text


# ─── Step 2: Detect Currency ──────────────────────────────────────────────────

def detect_currency(all_text):
    """
    Scans full document text for currency hints.
    Returns a dict: { "currency": "USD", "units": "Millions" }
    """
    combined = " ".join(all_text).lower()

    # Currency detection
    currency = "Unclear"
    if "usd" in combined or "u.s. dollar" in combined or "$" in combined:
        currency = "USD"
    elif "inr" in combined or "₹" in combined or "indian rupee" in combined:
        currency = "INR"
    elif "eur" in combined or "euro" in combined or "€" in combined:
        currency = "EUR"
    elif "gbp" in combined or "£" in combined or "british pound" in combined:
        currency = "GBP"
    elif "cny" in combined or "rmb" in combined or "yuan" in combined:
        currency = "CNY"

    # Unit detection
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


# ─── Step 3: Detect Years in Document ────────────────────────────────────────

def detect_years(all_text):
    """
    Finds all 4-digit years in the document that look like fiscal years (1990–2099).
    Returns a sorted list of unique years found.
    """
    combined = " ".join(all_text)
    years = re.findall(r'\b((?:19|20)\d{2})\b', combined)
    unique_years = sorted(set(int(y) for y in years))
    # Filter to plausible fiscal years only
    unique_years = [y for y in unique_years if 1990 <= y <= 2030]
    return unique_years


# ─── Step 4: Parse Numeric Value from String ─────────────────────────────────

def parse_number(raw):
    """
    Converts raw string representations of numbers to float.
    Handles:
      - Comma-separated: "1,234,567" → 1234567.0
      - Negative in parentheses: "(500)" → -500.0
      - Plain negatives: "-500" → -500.0
    Returns None if parsing fails.
    """
    if not raw:
        return None
    raw = raw.strip()
    # Parentheses = negative
    if re.match(r'^\([\d,\.]+\)$', raw):
        raw = "-" + raw[1:-1]
    # Remove commas
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


# ─── Step 5: Match Line in Text to Known Item ────────────────────────────────

def match_line_item(line_lower):
    """
    Tries to match a lowercase text line to one of our known line item categories.
    Returns the canonical line item name or None.
    """
    for canonical, aliases in LINE_ITEM_ALIASES.items():
        for alias in aliases:
            if alias in line_lower:
                return canonical
    return None


# ─── Step 6: Extract Financial Lines ─────────────────────────────────────────

def extract_financial_lines(pages_text, detected_years):
    """
    Main extraction logic. Scans each page line by line looking for:
    - Known financial line items
    - Associated numeric values (ideally year-aligned)

    Returns a list of dicts:
      { line_item, year, value, confidence }
    """
    results = []

    # Regex: match a line that starts with text and ends with 1–4 numbers
    # Covers patterns like:  "Revenue    1,234   1,100   980   850"
    row_pattern = re.compile(
        r'^(.+?)\s+([\(\d][\d,\.\(\)]*(?:\s+[\(\d][\d,\.\(\)]*){0,3})\s*$'
    )
    # Single number at end of line
    single_num_pattern = re.compile(
        r'^(.+?)\s+([\-\(]?[\d,]+(?:\.\d+)?\)?)$'
    )

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

            # Try to extract numbers from this line
            numbers_raw = re.findall(r'[\(\-]?[\d,]+(?:\.\d+)?\)?', line)
            # Filter out 4-digit years from numbers list
            numbers_raw = [n for n in numbers_raw if not re.match(r'^\d{4}$', n.replace(",", ""))]

            if not numbers_raw:
                # Line item found but no numbers
                results.append({
                    "line_item": canonical,
                    "year": "Unknown",
                    "value": None,
                    "confidence": "Missing"
                })
                continue

            # Associate numbers with years if we have matching count
            if detected_years and len(numbers_raw) == len(detected_years):
                for yr, raw_val in zip(sorted(detected_years, reverse=True), numbers_raw):
                    val = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": yr,
                        "value": val,
                        "confidence": "OK" if val is not None else "Low Confidence"
                    })
            elif detected_years and len(numbers_raw) >= 1:
                # More or fewer numbers than years — assign to most recent years
                sorted_years = sorted(detected_years, reverse=True)
                for i, raw_val in enumerate(numbers_raw):
                    yr = sorted_years[i] if i < len(sorted_years) else "Unknown"
                    val = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": yr,
                        "value": val,
                        "confidence": "OK" if val is not None else "Low Confidence"
                    })
            else:
                # No year context — just store with Unknown year
                for raw_val in numbers_raw:
                    val = parse_number(raw_val)
                    results.append({
                        "line_item": canonical,
                        "year": "Unknown",
                        "value": val,
                        "confidence": "OK" if val is not None else "Low Confidence"
                    })

    return results


# ─── Step 7: Deduplicate Results ──────────────────────────────────────────────

def deduplicate_results(results):
    """
    For each (line_item, year) pair, keep the entry with the best confidence.
    Priority: OK > Low Confidence > Missing
    """
    priority = {"OK": 0, "Low Confidence": 1, "Missing": 2, "Review Required": 3}
    best = {}
    for row in results:
        key = (row["line_item"], row["year"])
        if key not in best:
            best[key] = row
        else:
            if priority.get(row["confidence"], 9) < priority.get(best[key]["confidence"], 9):
                best[key] = row
    return list(best.values())


# ─── Step 8: Fill Missing Line Items ─────────────────────────────────────────

def fill_missing_items(results, detected_years):
    """
    For any canonical line item not found at all, adds a NULL placeholder row.
    """
    found_items = set(r["line_item"] for r in results)
    years_to_use = detected_years if detected_years else ["Unknown"]

    for canonical in LINE_ITEM_ALIASES:
        if canonical not in found_items:
            for yr in years_to_use:
                results.append({
                    "line_item": canonical,
                    "year": yr,
                    "value": None,
                    "confidence": "Missing"
                })
    return results


# ─── Step 9: Generate Output File ────────────────────────────────────────────

def generate_output_file(results, currency_info, output_folder, base_name):
    """
    Converts results list to a pandas DataFrame and saves as both CSV and Excel.
    Returns paths to the generated files.
    """
    rows = []
    for r in results:
        rows.append({
            "Line Item": r["line_item"],
            "Year": r["year"],
            "Value": r["value"] if r["value"] is not None else "NULL",
            "Currency": currency_info["currency"],
            "Units": currency_info["units"],
            "Confidence Flag": r["confidence"]
        })

    df = pd.DataFrame(rows)

    # Sort for readability
    df = df.sort_values(["Line Item", "Year"]).reset_index(drop=True)

    uid = str(uuid.uuid4())[:8]
    csv_filename = f"{base_name}_{uid}.csv"
    xlsx_filename = f"{base_name}_{uid}.xlsx"

    csv_path = os.path.join(output_folder, csv_filename)
    xlsx_path = os.path.join(output_folder, xlsx_filename)

    df.to_csv(csv_path, index=False)

    # Excel with basic formatting
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Financial Data")
        ws = writer.sheets["Financial Data"]
        # Auto-size columns
        for col in ws.columns:
            max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    return csv_path, xlsx_path


# ─── Flask Routes ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    file = request.files["pdf_file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Only PDF files are accepted.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(pdf_path)

    # ── Processing Pipeline ──
    pages_text = extract_text(pdf_path)

    if not pages_text:
        flash("Could not extract text from the PDF. It may be scanned/image-based.", "error")
        return redirect(url_for("index"))

    currency_info = detect_currency(pages_text)
    detected_years = detect_years(pages_text)

    # Limit to at most 5 most recent years to avoid false positives
    detected_years = sorted(detected_years)[-5:] if detected_years else []

    raw_results = extract_financial_lines(pages_text, detected_years)
    deduped = deduplicate_results(raw_results)
    final_results = fill_missing_items(deduped, detected_years)

    base_name = os.path.splitext(filename)[0]
    csv_path, xlsx_path = generate_output_file(
        final_results, currency_info, app.config["OUTPUT_FOLDER"], base_name
    )

    # Clean up upload
    try:
        os.remove(pdf_path)
    except Exception:
        pass

    csv_filename = os.path.basename(csv_path)
    xlsx_filename = os.path.basename(xlsx_path)

    flash("Extraction complete! Download your file below.", "success")
    return render_template(
        "index.html",
        csv_file=csv_filename,
        xlsx_file=xlsx_filename,
        currency=currency_info["currency"],
        units=currency_info["units"],
        years=detected_years,
        row_count=len([r for r in final_results if r["confidence"] != "Missing"])
    )


@app.route("/download/<filename>")
def download(filename):
    # Security: only allow files from output folder, no path traversal
    safe_name = secure_filename(filename)
    file_path = os.path.join(app.config["OUTPUT_FOLDER"], safe_name)
    if not os.path.exists(file_path):
        flash("File not found or expired.", "error")
        return redirect(url_for("index"))
    return send_file(file_path, as_attachment=True)


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)