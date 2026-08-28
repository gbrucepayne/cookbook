function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.setAttribute('open', 'true');
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.removeAttribute('open');
}

async function executeMultiPageOCR() {
  const fileInput = document.getElementById('ocr-files');
  const statusIndicator = document.getElementById('ocr-status-indicator');
  const submitBtn = document.getElementById('btn-trigger-ocr');

  if (!fileInput.files || fileInput.files.length === 0) {
    alert('Please pick at least one page snapshot before execution.');
    return;
  }

  const formData = new FormData();
  for (let i = 0; i < fileInput.files.length; i++) {
    formData.append('image_files', fileInput.files[i]);
  }

  const csrfInput = document.querySelector('input[name="csrf_token"]');
  if (csrfInput) {
    formData.append('csrf_token', csrfInput.value);
  }

  submitBtn.disabled = true;
  statusIndicator.setAttribute('aria-busy', 'true');

  try {
    const response = await fetch('/scan_ocr', {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    if (!response.ok || data.error) {
      throw new Error(data.error || 'Parsing pipeline processing fault.');
    }

    closeModal('modal-ocr');

    document.getElementById('m-title').placeholder = "Scanned Cookbook Entry";
    document.getElementById('m-notes').value = data.extracted_text || '';
    document.getElementById('m-ingredients').placeholder = "Review text data contents inside notes block above.";
    document.getElementById('m-instructions').placeholder = "Review text data contents inside notes block above.";

    openModal('modal-manual');

  } catch (err) {
    alert(`OCR Server Disconnect: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    statusIndicator.setAttribute('aria-busy', 'false');
  }
}