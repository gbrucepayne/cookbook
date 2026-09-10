// Global memory tracking container variables
let activeBoxesData = [];
let imgOrigWidth = 950;  
let imgOrigHeight = 1100;
const currentImageFilename = "manual_muffin_scan.jpg"; // Pass via Jinja context dynamically

function updateOCRCalibration() {
  // 1. Sync visual slider labels
  document.getElementById('val-k-width').innerText = document.getElementById('slider-k-width').value;
  document.getElementById('val-k-height').innerText = document.getElementById('slider-k-height').value;
  document.getElementById('val-y-tol').innerText = document.getElementById('slider-y-tol').value;
  
  // 2. Fire an async background fetch network handshake payload to Flask
  fetch('/api/ocr/calculate-layout', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
    },
    body: JSON.stringify({
      k_width: document.getElementById('slider-k-width').value,
      k_height: document.getElementById('slider-k-height').value,
      y_tolerance: document.getElementById('slider-y-tol').value,
      image_filename: currentImageFilename
    })
  })
  .then(response => response.json())
  .then(data => {
    // 3. Capture the real numbers returned from OpenCV!
    activeBoxesData = data.boxes;
    imgOrigWidth = data.image_orig_width;
    imgOrigHeight = data.image_orig_height;
    
    document.getElementById('stat-boxes').innerText = data.boxes.length;
    document.getElementById('stat-rows').innerText = data.rows_count;
    
    // 4. Force canvas overlay to repaint with the precise layout coordinates
    drawBoundingBoxes();
  })
  .catch(err => console.error("OCR API Synchronizer crash:", err));
}

function drawBoundingBoxes() {
  const img = document.getElementById('calibration-img');
  const canvas = document.getElementById('ocr-overlay-canvas');
  if (!canvas || !img || !activeBoxesData.length) return;
  
  const ctx = canvas.getContext('2d');
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // Dynamically map high-resolution image matrices onto smaller screen boxes proportionally
  const scaleX = canvas.width / imgOrigWidth;
  const scaleY = canvas.height / imgOrigHeight;

  activeBoxesData.forEach(box => {
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#106ba3'; // Crisp accent outline bounding line
    ctx.fillStyle = 'rgba(16, 107, 163, 0.08)'; // Translucent core fill
    
    ctx.fillRect(box.x * scaleX, box.y * scaleY, box.w * scaleX, box.h * scaleY);
    ctx.strokeRect(box.x * scaleX, box.y * scaleY, box.w * scaleX, box.h * scaleY);
  });
}

// Bind an execution handler right onto image load to ensure boxes draw immediately
window.addEventListener('load', () => {
  setTimeout(drawBoundingBoxes, 300);
});
window.addEventListener('resize', drawBoundingBoxes);
