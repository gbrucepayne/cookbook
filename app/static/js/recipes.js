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

    if (!response.ok) {
      throw new Error('Parsing pipeline processing fault.');
    }
    const newModalHtml = await response.text();
    // console.debug(`Received HTML: ${newModal}`);
    const oldModal = document.getElementById('modal-edit');
    if (!oldModal) throw new Error('Target modal not found in DOM.');

    // Close the scanner/wait modal before touching DOM
    closeModal('modal-ocr');

    oldModal.outerHTML = newModalHtml;

    openModal('modal-edit');

  } catch (err) {
    alert(`OCR Server Disconnect: ${err.error || err.message}`);
  } finally {
    submitBtn.disabled = false;
    statusIndicator.setAttribute('aria-busy', 'false');
  }
}

// Global variable container to store our active screen lock handle reference
let wakeLockHandle = null;

/**
 * Main orchestration entry point triggered by the Pico CSS switch element toggle action.
 */
async function toggleCookingMode(toggleInput) {
  const statusLabel = document.getElementById('cooking-mode-status');

  if (toggleInput.checked) {
    // 1. Verify browser feature support engine coverage
    if ('wakeLock' in navigator) {
      try {
        // Request screen lock token
        wakeLockHandle = await navigator.wakeLock.request('screen');
        
        statusLabel.innerText = "Active: Screen lock enabled. Your iPad will stay awake.";
        statusLabel.style.color = "var(--pico-ins-color)"; // Tint green for visual clarity

        // 2. Setup automatic re-lock tracking rule
        document.addEventListener('visibilitychange', reacquireWakeLockOnFocus);
        
      } catch (err) {
        console.error(`Wake Lock failed to establish: ${err.message}`);
        statusLabel.innerText = "Error initializing sleep blocker engine.";
        toggleInput.checked = false;
      }
    } else {
      alert("Wake Lock API is not supported on this browser version. (Requires iOS 15.6+ / Safari 16+)");
      statusLabel.innerText = "Unsupported browser feature.";
      toggleInput.checked = false;
    }
  } else {
    // 3. User manually toggled off the behavior
    disableCookingMode();
  }
}

/**
 * Safely releases the screen handle and updates the status labels.
 */
function disableCookingMode() {
  const statusLabel = document.getElementById('cooking-mode-status');
  const toggleInput = document.getElementById('cooking-mode-toggle');

  if (wakeLockHandle !== null) {
    wakeLockHandle.release().then(() => {
      wakeLockHandle = null;
      document.removeEventListener('visibilitychange', reacquireWakeLockOnFocus);
      
      if (statusLabel) {
        statusLabel.innerText = "Inactive: Standard system auto-sleep times restored.";
        statusLabel.style.color = "var(--pico-muted-color)";
      }
    });
  }
}

/**
 * Re-acquires the lock if the user leaves the tab and returns later.
 */
async function reacquireWakeLockOnFocus() {
  const toggleInput = document.getElementById('cooking-mode-toggle');
  
  if (wakeLockHandle !== null && document.visibilityState === 'visible') {
    try {
      wakeLockHandle = await navigator.wakeLock.request('screen');
      console.debug("Wake lock successfully re-acquired on tab refocus.");
    } catch (err) {
      console.error(`Failed to automatically re-secure lock asset: ${err.message}`);
    }
  }
}

// Run when navigating away from the active recipe view
window.addEventListener('beforeunload', () => {
  if (wakeLockHandle !== null) {
    wakeLockHandle.release();
  }
});
