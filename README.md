# Financial Research Portal

A minimal internal research tool that extracts **Income Statement line items** from PDF annual reports and financial statements, and outputs structured **CSV / Excel** files ready for analysis.

---

## Setup & Installation

### 1. Clone / Download

```bash
git clone <your-repo-url>
cd research_portal
```

### 2. (Optional) Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the App

```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## How to Use

1. Open the portal in your browser.
2. Upload a PDF annual report or financial statement (max 32 MB).
3. Wait a few seconds while the system extracts data.
4. Download the generated **CSV** or **Excel (.xlsx)** file.

---

## Example Input

Any PDF with a text-based (not scanned) Income Statement. Works best with:

- Corporate annual reports (10-K, 10-Q filings)
- Standalone financial statements
- Investor presentations that contain tabular P&L data

**Sample text the system recognises:**

```
Revenue                   45,000    42,000    38,500
Cost of Goods Sold        18,000    17,200    15,400
Gross Profit              27,000    24,800    23,100
Operating Expenses         8,500     8,200     7,900
Net Income                 9,800     8,700     7,600
```

---

## Output Format

| Column           | Description                                        |
|------------------|----------------------------------------------------|
| Line Item        | Canonical name (e.g., "Revenue", "Net Income")     |
| Year             | Fiscal year detected from document                 |
| Value            | Numeric value, or `NULL` if not found              |
| Currency         | Detected currency (USD, INR, EUR, etc.)            |
| Units            | Detected units (Millions, Thousands, Crores, etc.) |
| Confidence Flag  | `OK`, `Low Confidence`, `Missing`, or `Review Required` |

---

## Extracted Line Items

| Canonical Name          | Aliases Recognised                                      |
|-------------------------|---------------------------------------------------------|
| Revenue                 | Net Sales, Total Revenue, Sales                         |
| Cost of Goods Sold      | COGS, Cost of Sales, Cost of Revenue                    |
| Gross Profit            | Gross Margin, Gross Income                              |
| Operating Expenses      | Operating Costs, SG&A                                   |
| Research & Development  | R&D Expenses                                            |
| Operating Income        | Operating Profit, EBIT, Income from Operations          |
| Interest Expense        | Finance Costs, Interest Cost                            |
| Profit Before Tax       | PBT, Income Before Tax, Pre-tax Income                  |
| Tax Expense             | Income Tax, Provision for Income Taxes                  |
| Net Income              | Net Profit, PAT, Profit After Tax, Net Earnings         |
| Depreciation & Amortization | D&A                                                |
| EBITDA                  | Earnings Before Interest Tax Depreciation Amortization  |

---

## Limitations

- **Scanned / image PDFs are not supported.** The system requires text-extractable PDFs. For scanned documents, an OCR step (e.g., `pytesseract`) would be needed before processing.
- **Complex layouts** (e.g., multi-column PDFs, sideways tables) may produce incomplete extractions.
- **Currency / unit detection** is heuristic. If the document doesn't contain clear keywords, these will be marked "Unclear".
- **Year attribution** is best-effort. If the number of values in a row doesn't match the number of detected years, the system assigns values to the most recent years first.
- The portal does **not** use an LLM — all extraction is rule-based for transparency and reproducibility.

---

## Possible Improvements

- **OCR support** via `pytesseract` or `easyocr` for scanned PDFs.
- **LLM hybrid mode**: use an LLM to handle ambiguous rows that rule-based logic misses.
- **Table extraction**: use `pdfplumber`'s `extract_table()` for structured table parsing instead of line-by-line text.
- **Multi-document batch upload**: process several PDFs in one session.
- **Database storage**: persist results in SQLite for historical comparison.
- **Review UI**: allow users to correct low-confidence rows in-browser before download.
- **Balance Sheet & Cash Flow**: extend the alias dictionary for other financial statement types.

---

## Project Structure

```
research_portal/
├── app.py                  # Flask app + extraction pipeline
├── templates/
│   └── index.html          # Upload & results UI
├── static/
│   └── style.css           # Minimal clean stylesheet
├── uploads/                # Temporary PDF storage (auto-created)
├── output/                 # Generated CSV / Excel files (auto-created)
├── requirements.txt
└── README.md
```

---

## Dependencies

| Package      | Purpose                          |
|--------------|----------------------------------|
| Flask        | Web framework                    |
| pdfplumber   | PDF text extraction              |
| pandas       | DataFrame & file export          |
| openpyxl     | Excel (.xlsx) writing            |
| werkzeug     | Secure filename handling         |