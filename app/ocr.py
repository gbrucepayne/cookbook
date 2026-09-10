import logging
import os
import re
from typing import Any

import cv2
import pytesseract

from app.image import optimize_and_save_image_stream
from app.models import Recipe

DYNAMIC_UPSCALING = False
BILATERAL_FILTERING = False
CLEAR_EDGE_BORDER_NOISE = False
DEFAULT_K_WIDTH = 15
DEFAULT_K_HEIGHT = 8
DEFAULT_Y_TOLERANCE = 15

logger = logging.getLogger(__name__)


def extract_recipe_ocr(image_paths: list[str], image_folder: str, **kwargs) -> str:
    """
    Accepts a list of file paths (handles single or multi-page recipes),
    extracts text from each sequentially, and stitches them together.
    """
    recipe = Recipe()
    
    for candidate in image_paths:
        dish_image = isolate_and_crop_embedded_image(
            source_image_path=candidate, 
            upload_folder=image_folder,
        )
        if dish_image:
            raise NotImplementedError("TODO: optimize extracted dish image")
            # TODO: pass stream from file/name
            # TODO: remove cropped area from text selection?
            optimize_and_save_image_stream()
            break

    all_pages_text = []
    
    for index, path in enumerate(image_paths):
        page_text = _process_single_page_ocr(path, **kwargs)
        if page_text:
            # Inject a logical divider for multi-page parsing models downstream
            if index > 0:
                all_pages_text.append(f"\n--- RECIPE PAGE {index + 1} ---")
            all_pages_text.append(page_text)
        os.remove(path)
            
    recipe.notes = "\n".join(all_pages_text)
    return recipe


def get_bounding_boxes(image_path: str, **kwargs) -> dict[str, Any]:
    """TODO: reusable function to interact with UI for box/row selection.
    Identify hero image and text blocks/rows for extraction.
    """
    img = cv2.imread(image_path)
    if img is None:
        return { 'boxes': [], 'rows_count': 0 }
    raise NotImplementedError("TODO: bounding box interaction")
    k_width = int(kwargs.get('k_width', DEFAULT_K_WIDTH))
    k_height = int(kwargs.get('k_height', DEFAULT_K_HEIGHT))
    y_tolerance = int(kwargs.get('y_tolerance', DEFAULT_Y_TOLERANCE))
    dynamic_upscaling = kwargs.get('dynamic_upscaling', DYNAMIC_UPSCALING)
    clear_lighting_gradients = kwargs.get('clear_lighting_gradients', False)
    bilateral_filtering = kwargs.get('bilateral_filtering', BILATERAL_FILTERING)
    quick = bool(kwargs.get('quick', False))
    dish_image_contour = kwargs.get('dish_image_contour')
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Run your exact binarization steps using our threshold fix
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 31, 15
    )
    
    # DYNAMIC CONFIGURATION: Plug the incoming slider widths straight into the brush kernel!
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, k_height))
    dilated = cv2.dilate(thresh, kernel, iterations=2)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bounding_boxes = []
    for ctr in contours:
        x, y, w, h = cv2.boundingRect(ctr)
        # Match your exact filtering rules
        if w > gray.shape[1] * 0.15 and h > 20:
            bounding_boxes.append({"x": x, "y": y, "w": w, "h": h})
            
    # Sort and calculate layout row distribution counts using the custom y_tolerance
    # ... (Your standard row-sorting loop logic goes here using your y_tolerance variable)
    total_rows_detected = 6 # Example fallback computed value summary reference
    
    # 3. Stream the raw coordinate array back down to the browser instantly
    return {
        "boxes": bounding_boxes,
        "rows_count": total_rows_detected,
        "image_orig_width": gray.shape[1],
        "image_orig_height": gray.shape[0]
    }


def _process_single_page_ocr(image_path: str, **kwargs) -> str:
    """
    Finds text paragraph blocks using OpenCV contours.
    Sorts blocks top-to-bottom, processes side-by-side columns
    left-to-right, and sends isolated crops to Tesseract.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return ""
            
        k_width = int(kwargs.get('k_width', DEFAULT_K_WIDTH))
        k_height = int(kwargs.get('k_height', DEFAULT_K_HEIGHT))
        y_tolerance = int(kwargs.get('y_tolerance', DEFAULT_Y_TOLERANCE))
        dynamic_upscaling = kwargs.get('dynamic_upscaling', DYNAMIC_UPSCALING)
        clear_lighting_gradients = kwargs.get('clear_lighting_gradients',
                                              False)
        bilateral_filtering = kwargs.get('bilateral_filtering',
                                         BILATERAL_FILTERING)
        
        # Convert to Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h_orig, w_orig = gray.shape
        
        # Dynamic Upscaling (Crucial for fine/scrambled print on book pages)
        # Scaled up slightly using cubic interpolation to sharpen text edges
        if dynamic_upscaling and w_orig < 2000: 
            gray = cv2.resize(gray,
                              None,
                              fx=1.5,
                              fy=1.5,
                              interpolation=cv2.INTER_CUBIC)

        # Clean background lighting gradients
        if clear_lighting_gradients:
            struct_element = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 51))
            background = cv2.morphologyEx(gray, cv2.MORPH_DILATE, struct_element)
            background = cv2.GaussianBlur(background, (51, 51), 0)
            normalized = cv2.divide(gray, background, scale=255)
        
        # Bilateral Filtering
        filtered = (cv2.bilateralFilter(normalized, 9, 75, 75) 
                    if bilateral_filtering else normalized)
        
        # Binarize (invert text to white blocks on black background for contouring)
        thresh = cv2.adaptiveThreshold(
            src=filtered,
            maxValue=255, 
            adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            thresholdType=cv2.THRESH_BINARY_INV,
            blockSize=31,
            C=15,
        )

        # Clear Edge Border Noise Artifacts (Keeps binding shadows from producing junk characters)
        if CLEAR_EDGE_BORDER_NOISE:
            h, w = thresh.shape
            margin_w, margin_h = int(w * 0.04), int(h * 0.04) # Slightly wider margins
            cv2.rectangle(thresh, (0, 0), (w, margin_h), (255), -1)
            cv2.rectangle(thresh, (0, h - margin_h), (w, h), (255), -1)
            cv2.rectangle(thresh, (0, 0), (margin_w, h), (255), -1)
            cv2.rectangle(thresh, (w - margin_w, 0), (w, h), (255), -1)
        
        # Morphological morph to merge words into solid "paragraph boxes"
        # A wide horizontal kernel bridges characters and words into a unified block row
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, k_height))
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        
        # Find bounding boxes of all major text blocks
        contours, _ = cv2.findContours(
            dilated,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        bounding_boxes = []
        for ctr in contours:
            x, y, w, h = cv2.boundingRect(ctr)
            # Filter our minor specks and lines too small to be paragraphs
            if w > w_orig * 0.15 and h > 20:
                bounding_boxes.append((x, y, w, h))
        logger.debug("Total text boxes matching area filter: %d",
                     len(bounding_boxes))
        if not bounding_boxes:
            return pytesseract.image_to_string(filtered, config=r'--psm 4')
        # Sort boxes top-to-bottom by their Y coordinate
        bounding_boxes = sorted(bounding_boxes, key=lambda b: b[1])
        # Group boxes that sit on the same horizontal plane (detect colummns)
        grouped_rows = []
        current_row = [bounding_boxes[0]]
        for box in bounding_boxes[1:]:
            # If this box's top coordinate is roughly aligned with the previous one
            if abs(box[1] - current_row[0][1]) < y_tolerance:
                current_row.append(box)
            else:
                # Sort the completed row left-to-right by X coordinate
                current_row = sorted(current_row, key=lambda b: b[0])
                grouped_rows.append(current_row)
                current_row = [box]
        # Append the final remaining row
        current_row = sorted(current_row, key=lambda b: b[0])
        grouped_rows.append(current_row)
        logger.debug("Layout engine split boxes into %d rows",
                     len(grouped_rows))
        for i, row in enumerate(grouped_rows):
            logger.debug('-> Row %d contains %d horizontal text block columns',
                         i+1, len(row))
        
        # Iterate through sorted layout rows and extract text crops sequentially
        extracted_text = []
        for row in grouped_rows:
            for (x, y, w, h) in row:
                # Crop slightly outside the bounding box margin to avoid cropping edges
                pad = 9
                crop_y1 = max(0, y - pad)
                crop_y2 = min(h_orig, y + h + pad)
                crop_x1 = max(0, x - pad)
                crop_x2 = min(w_orig, x + w + pad)
                cropped_text_block = filtered[crop_y1:crop_y2, crop_x1:crop_x2]
                # Use PSM 4 (assume sigle column text block of variable size)
                config = r'--psm 4'
                block_text = pytesseract.image_to_string(
                    cropped_text_block,
                    config=config.strip(),
                )
                if block_text:
                    extracted_text.append(block_text)
        
        # Structure & Clean Output Stream Rows Safely
        cleaned_lines = []
        for text_block in extracted_text:
            lines = text_block.split('\n')
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                
                # SAFEGUARD: Replace dangerous character noise variations without destroying structure
                # Notice we leave periods, colons, forward slashes, and hyphens completely alone!
                sanitized = re.sub(r'[\/\\|§_~—„•·;=\[\]]', '', stripped).strip()
                
                # Count alphanumeric elements for noise floor filtration
                letter_count = sum(c.isalpha() for c in sanitized)
                digit_count = sum(c.isdigit() for c in sanitized)
                total_valid_chars = letter_count + digit_count
                
                # Drop pure noise lines, but keep valid short lines like "1 egg" (5 chars total)
                if total_valid_chars < 3:
                    continue
                    
                # Ensure the line isn't a massive strip of text artifact garbage
                if len(sanitized) > 0 and (total_valid_chars / len(sanitized)) < 0.40:
                    continue
                    
                cleaned_lines.append(sanitized)
                    
        return '\n'.join(cleaned_lines)
        
    except Exception as e:
        logger.error(f"Advanced Document OCR engine failure: {e}")
        return ""


def isolate_and_crop_embedded_image(source_image_path: str, upload_folder: str) -> str | None:
    """Attempt to identify and extract a dish image from a scanned page."""
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
            if (total_area * 0.10) < area < (total_area * 0.70): # Expanded slightly to catch non-standard framing
                if 0.5 < aspect_ratio < 2.0:
                    roi = closed[y:y+ch, x:x+cw]
                    density = cv2.countNonZero(roi) / float(area)
                    if density > 0.40: 
                        if area > max_area:
                            max_area = area
                            best_contour = (x, y, cw, ch)
                            
        if best_contour:
            x, y, cw, ch = best_contour
            cropped_img = img[max(0, y-10):min(h, y+ch+10), max(0, x-10):min(w, x+cw+10)]
            
            base_name = os.path.basename(source_image_path)
            dish_filename = f"dish_{base_name}"
            cv2.imwrite(os.path.join(upload_folder, dish_filename), cropped_img)
            return dish_filename
            
    except Exception as e:
        logger.error(f"OpenCV layout contour matching crash: {e}")
        
    return None
