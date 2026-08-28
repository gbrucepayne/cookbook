# Family Recipe Archive

A simple database and web server to display recipes from a local server.
All content is stored locally to prevent data loss from changes to websites or access.

* Manually upload recipes
* Reference URL links to download recipes
* Edit recipes with notes and ratings
* Search by title or ingredient
* Import single or multi-page recipe scans from a magazine or book

## Prerequisites

The scan import functions use OCR and optionally LLM techniques to
interpret scanned images and extract the dish image and blocks of text.

### Debian / Ubuntu
```
sudo apt update
sudo apt install -y tesseract-ocr libtesseract-dev
```

### Mac OS
```
brew install tesseract
```
