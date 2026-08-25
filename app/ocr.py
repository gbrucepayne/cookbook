import os
import re

import cv2
import pytesseract


def extract_text_from_image(image_path: str) -> str:
    """
    Advanced document layout engine that removes smartphone shadows,
    binarizes text, and keeps parallel multi-column lists structured.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return ""
            
        # 1. Convert to Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. Flatten Shadows & Lighting Gradients
        # Uses a large structural element to map background lighting, then divides the image by it
        struct_element = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 51))
        background = cv2.morphologyEx(gray, cv2.MORPH_DILATE, struct_element)
        background = cv2.GaussianBlur(background, (51, 51), 0)
        normalized = cv2.divide(gray, background, scale=255)
        
        # 3. Bilateral Filtering
        # Cleans out paper grain and sensor noise without blurring the sharp text stroke borders
        filtered = cv2.bilateralFilter(normalized, 9, 75, 75)
        
        # 4. Clear High-Contrast Binarization
        processed_thresh = cv2.adaptiveThreshold(
            filtered, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 31, 15
        )
        
        # 5. Clear Edge Border Noise Artifacts
        h, w = processed_thresh.shape
        margin_w, margin_h = int(w * 0.03), int(h * 0.03)
        cv2.rectangle(processed_thresh, (0, 0), (w, margin_h), (255), -1)
        cv2.rectangle(processed_thresh, (0, h - margin_h), (w, h), (255), -1)
        cv2.rectangle(processed_thresh, (0, 0), (margin_w, h), (255), -1)
        cv2.rectangle(processed_thresh, (w - margin_w, 0), (w, h), (255), -1)

        # 6. Execute OCR running Tesseract under Page Segmentation Mode 3
        # Mandates the preservation of inter-word whitespace gaps to keep columns apart
        custom_config = r'--psm 3 -c preserve_interword_spaces=1'
        extracted_text = pytesseract.image_to_string(processed_thresh, config=custom_config)
        
        # 7. Structure & Clean Output Stream Rows
        cleaned_lines = []
        for line in extracted_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # Clean up typical OCR artifact noise symbols
            sanitized = re.sub(r'[\/\\|§_~—\-°‘\'’"“„•.·:;=,\[\]\(\)]', '', stripped).strip()
            
            # Count the remaining alphanumeric characters vs total characters
            letter_count = sum(c.isalpha() for c in sanitized)
            digit_count = sum(c.isdigit() for c in sanitized)
            total_valid_chars = letter_count + digit_count
            
            # SAFEGUARD FILTER: Skip any lines that are just noise clusters
            # Valid recipe lines will always have actual words or numbers.
            if total_valid_chars < 3:
                continue
                
            # If the line contains mostly random punctuation marks, discard it
            if len(sanitized) > 0 and (total_valid_chars / len(stripped)) < 0.30:
                continue
                
            # Post-cleaning reconstruction adjustments
            final_line = stripped.replace('|', '').replace('§', '').replace('—', '').strip()
            if final_line:
                cleaned_lines.append(final_line)
                    
        return '\n'.join(cleaned_lines)
        
    except Exception as e:
        print(f"Advanced Document OCR engine failure: {e}")
        return ""

def isolate_and_crop_embedded_image(source_image_path: str, upload_folder: str) -> str | None:
    """
    Robust shape classifier. Instead of using unstable color tracking, 
    it actively parses contours to identify distinct graphic elements on the page.
    """
    try:
        img = cv2.imread(source_image_path)
        if img is None: 
            return None
            
        h, w, _ = img.shape
        total_area = h * w
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 30))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best_contour = None
        max_area = 0
        
        for ctr in contours:
            x, y, cw, ch = cv2.boundingRect(ctr)
            aspect_ratio = float(cw) / ch
            area = cw * ch
            
            # Stricter image layout filters: A valid embedded illustration must be a large
            # block that does not stretch horizontally or vertically like a typical text block.
            if (total_area * 0.15) < area < (total_area * 0.60):
                if 0.6 < aspect_ratio < 1.8:
                    # Verify internal density: Text rows leave empty spaces, whereas
                    # photographic fields present unified, dense blocks.
                    roi = closed[y:y+ch, x:x+cw]
                    density = cv2.countNonZero(roi) / float(area)
                    
                    if density > 0.45: # High internal pixel consistency indicates a photograph
                        if area > max_area:
                            max_area = area
                            best_contour = (x, y, cw, ch)
                            
        if best_contour:
            x, y, cw, ch = best_contour
            cropped_img = img[max(0, y-5):min(h, y+ch+5), max(0, x-5):min(w, x+cw+5)]
            
            base_name = os.path.basename(source_image_path)
            dish_filename = f"dish_{base_name}"
            cv2.imwrite(os.path.join(upload_folder, dish_filename), cropped_img)
            return dish_filename
            
    except Exception as e:
        print(f"OpenCV layout contour matching crash: {e}")
        
    return None
