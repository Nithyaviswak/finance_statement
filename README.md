# Financial Research Portal

PDF-based income statement extractor with:
- Flask backend API (Render)
- Static frontend (Netlify)

## Project Layout

- `research_portal/app.py`: Flask app + processing pipeline
- `research_portal/templates/index.html`: server-rendered UI (optional)
- `research_portal/frontend/`: Netlify static frontend
- `research_portal/requirements.txt`: backend dependencies

## Backend Deploy (Render)

Use the `research_portal` directory as your Render service root.

1. Create a new **Web Service** in Render and connect your repo.
2. Set:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
3. Add env vars:
   - `FLASK_SECRET_KEY`: any strong random string
   - `CORS_ALLOW_ORIGINS`: your Netlify site URL (or `*` while testing)
4. Deploy.
5. Verify health endpoint:
   - `https://finance-statement.onrender.com/api/health`

## Frontend Deploy (Netlify)

Use the `research_portal/frontend` directory for Netlify.

1. In Netlify, import your repo.
2. Configure:
   - Base directory: `research_portal/frontend`
   - Build command: *(leave empty)*
   - Publish directory: `.`
3. Deploy site.
4. Frontend calls backend via `API_BASE` in:
   - `research_portal/frontend/assets/app.js`
   - Default is already set to `https://finance-statement.onrender.com`

## API Used by Frontend

- `POST /api/upload`
  - Form field: `pdf_file` (PDF)
  - Returns metadata and download URLs for CSV/XLSX.

## Local Run (Backend)

```bash
cd research_portal
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.
