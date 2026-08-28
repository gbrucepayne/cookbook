import json
import os
from typing import Any

import requests

LLM_URL = os.environ.get('COOKBOOK_LLM_URL')


def parse_recipe_with_ollama(raw_text: str):
    """Attempt to use LLM to parse recipe data and metadata from derived text."""
    recipe_data = {
        "title": "Unknown",
        "description": None,
        "notes": None,
        "ingredients": [],
        "instructions": [],
        "servings": None,
        "prep_time": None,
        "cook_time": None,        
    }
    if LLM_URL:
        try:
            prompt = f"""
            You are a precise recipe parsing backend engine. Analyze the following extracted raw text.
            It was scanned from a cookbook page and may contain horizontal text bleed where parallel columns have merged inline.
            Un-bleed the columns, sort the ingredients, and organize everything into a clean JSON structure.
            
            CRITICAL RULES:
            1. Do not invent ingredients or steps.
            2. Separate ingredients that got merged horizontally onto the same line.
            3. Return ONLY a valid JSON object. Do not include any conversational text or markdown code blocks.

            Expected JSON Keys:
            - title (string)
            - description (string)
            - prep_time (integer minutes, combine prep/cook/total times here)
            - servings (integer)
            - notes (string)
            - ingredients (list of clean strings)
            - instructions (list of ordered step strings)

            Raw Text Input:
            {raw_text}
            """
            
            # Call your local Ollama web port
            response = requests.post(LLM_URL, json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False,
                "format": "json"
            })
            parsed: dict[str, Any] = json.loads(response.json()['response'])
            for key, val in parsed.items():
                if key.lower() in recipe_data:
                    recipe_data[key.lower()] = val
        except Exception as e:
            print(f'LLM Parsing engine failed: {e}')
    
    if recipe_data['title'] == "Unknown":
        raw_lines = [l for l in raw_text.split('\n') if l.strip()]
        if len(raw_lines) > 0:
            recipe_data['title'] = raw_lines[0]
            recipe_data['ingredients'] = raw_lines[1:]
        
    return recipe_data
