const API_BASE = "https://finance-statement.onrender.com";

const fileInput = document.getElementById("pdf_file");
const submitBtn = document.getElementById("submitBtn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const metaEl = document.getElementById("meta");
const csvLink = document.getElementById("csvLink");
const xlsxLink = document.getElementById("xlsxLink");
const backendUrlEl = document.getElementById("backendUrl");

backendUrlEl.textContent = API_BASE;

submitBtn.addEventListener("click", async () => {
  const file = fileInput.files?.[0];

  if (!file) {
    statusEl.textContent = "Please choose a PDF file.";
    return;
  }

  submitBtn.disabled = true;
  resultEl.classList.add("hidden");
  statusEl.textContent = "Uploading and processing...";

  const formData = new FormData();
  formData.append("pdf_file", file);

  try {
    const response = await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "Request failed");
    }

    const data = payload.data;
    csvLink.href = data.files.csv.url;
    xlsxLink.href = data.files.xlsx.url;

    const years = data.years?.length ? data.years.join(", ") : "Unknown";
    metaEl.textContent = `Currency: ${data.currency} | Units: ${data.units} | Years: ${years} | Rows: ${data.row_count}`;

    resultEl.classList.remove("hidden");
    statusEl.textContent = "Done. Use the download buttons below.";
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  } finally {
    submitBtn.disabled = false;
  }
});
