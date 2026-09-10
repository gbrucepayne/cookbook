function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    // modal.setAttribute('open', 'true');
    modal.showModal();
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    // modal.removeAttribute('open');
    modal.close();
  }
}

function submitScaleWithScroll() {
  const form = document.getElementById('scale-form');
  const scrollInput = document.getElementById('scroll-pos-input');
  
  // Grab the current window scroll pixel position coordinate
  scrollInput.value = window.scrollY; 
  form.submit();
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

  // // Allow for custom local OCR parameters
  // const kWidth = document.getElementById('val-k-width').innerText || '';
  // const kHeight = document.getElementById('val-k-height').innerText || '';
  // const yTolerance = document.getElementById('val-y-tol').innerText || '';
  // if (kWidth !== '') formData.append('k_width', Number(kWidth));
  // if (kHeight !== '') formData.append('k_height', Number(kHeight));
  // if (yTolerance !== '') formData.append('y_tolerance', Number(yTolerance));

  submitBtn.disabled = true;
  statusIndicator.setAttribute('aria-busy', 'true');

  try {
    const response = await fetch('/scan_ocr', {
      method: 'POST',
      body: formData
    });

    // const data = await response.json();

    if (!response.ok) {
      throw new Error('Parsing pipeline processing fault.');
    }
    const newModal = await response.text();
    // console.debug(`Received HTML: ${newModal}`);
    const oldModal = document.getElementById('modal-manual');
    if (!oldModal) throw new Error('Target modal not found in DOM.');

    // Close the scanner/wait modal before touching DOM
    closeModal('modal-ocr');

    oldModal.outerHTML = newModal;
    // document.getElementById('title').placeholder = "Scanned Cookbook Entry";
    // document.getElementById('notes').value = data.extracted_text || '';
    // document.getElementById('ingredients').placeholder = "Review text data contents inside notes block above.";
    // document.getElementById('instructions').placeholder = "Review text data contents inside notes block above.";

    openModal('modal-manual');

  } catch (err) {
    alert(`OCR Server Disconnect: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    statusIndicator.setAttribute('aria-busy', 'false');
  }
}
