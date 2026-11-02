#!/usr/bin/env python3
"""
SFT Dataset Preparation Script.
Ingests PDF files from data/reference_cases/, parses them via Docling,
and structures the text into SFT conversational JSON format.
"""
import os
import sys
import json
from pathlib import Path
from loguru import logger

# Add project root directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion import IngestionEngine
from src.llm_client import get_llm_client, Role

def extract_case_meta(company_key: str, parsed_text: str) -> dict:
    """Uses LLM (Gemini Flash) to extract the metadata properties of the reference case study."""
    logger.info(f"Extracting metadata properties and structural blocks for case: {company_key}")
    
    system_prompt = (
        "You are an academic case study annotator. Analyze the parsed text of this business school case study "
        "and extract: (1) Target Company Name, (2) Industry Sector, (3) Key Protagonist Name & Designation, "
        "(4) The Decision Dilemma description, (5) Learning Objectives. "
        "Return the output as a valid JSON object with the keys: company, sector, protagonist, dilemma, objectives."
    )
    
    # We take the first 10,000 characters of the parsed text which usually contains the intro and background
    text_snippet = parsed_text[:12000]
    
    client = get_llm_client()
    try:
        raw_json_str = client.complete(
            prompt=f"Case Study Text Snippet:\n{text_snippet}\n\nExtract JSON metadata:",
            role=Role.BULK,
            system=system_prompt,
            temperature=0.1,
            max_tokens=1024
        )
        # Parse output ensuring no Markdown fences interfere
        cleaned_json = raw_json_str.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_json)
    except Exception as e:
        logger.error(f"Failed to extract metadata via LLM: {str(e)}")
        # Return fallback values
        return {
            "company": company_key,
            "sector": "General Management",
            "protagonist": "CEO",
            "dilemma": "How to scale operations without degrading quality standards.",
            "objectives": ["Analyze operational scaling", "Evaluate quality management frameworks"]
        }

def prepare_sft_dataset(input_dir: str = "data/reference_cases", output_file: str = "data/sft_training_dataset.json"):
    """Loop through reference cases, parse them, extract details, and save in SFT format."""
    logger.info(f"Starting SFT Reference Dataset Assembly from: {input_dir}")
    
    input_path = Path(input_dir)
    if not input_path.exists():
        logger.error(f"Reference directory does not exist: {input_path}")
        return
        
    pdf_files = list(input_path.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF reference case studies located in {input_dir}")
        return

    ingestion = IngestionEngine()
    sft_data = []
    
    for pdf in pdf_files:
        logger.info(f"Processing reference document: {pdf.name}")
        company_key = pdf.stem.split(" Case")[0].split(" ,")[0].strip()
        
        try:
            # Step 1: Parse PDF
            parsed_text = ingestion.parse_pdf_via_docling(pdf)
            
            # Step 2: Extract core meta
            meta = extract_case_meta(company_key, parsed_text)
            
            # Step 3: Map to SFT Conversation format
            system_msg = (
                "You are an expert case writer. Frame data as an academic case study: "
                "open with an immediate protagonist dilemma, use strict past-tense, "
                "and map content backward from learning outcomes."
            )
            
            user_msg = (
                f"Company Name: {meta.get('company')} | Sector: {meta.get('sector')} | "
                f"Protagonist: {meta.get('protagonist')} | Dilemma: {meta.get('dilemma')}"
            )
            
            # Target output contains the full professional case structure
            target_output = parsed_text
            
            conversation_block = {
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": target_output}
                ],
                "metadata": {
                    "company": meta.get('company'),
                    "sector": meta.get('sector'),
                    "objectives": meta.get('objectives')
                }
            }
            
            sft_data.append(conversation_block)
            logger.success(f"Successfully processed and formatted conversational block for {company_key}")
            
        except Exception as e:
            logger.error(f"Failed to process {pdf.name}: {str(e)}")
            
    if sft_data:
        # Step 4: Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sft_data, f, indent=2, ensure_ascii=False)
            
        logger.success(f"SFT Training Dataset compiled! Mapped {len(sft_data)} conversations into: {output_file}")
    else:
        logger.error("No SFT data could be compiled from reference documents.")

if __name__ == "__main__":
    prepare_sft_dataset()
