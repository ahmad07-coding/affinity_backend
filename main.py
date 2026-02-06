"""
IRS Form 990 PDF Text Extractor API
FastAPI application for extracting data from Form 990 PDFs
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import shutil
import uuid
from datetime import datetime
import logging

from models import ExtractionResponse, ExtractionResult, HealthResponse, ExtractionResponseV2
from services.pdf_processor import PDFProcessor
from services.field_extractor import FieldExtractor
import aiofiles

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="IRS Form 990 PDF Extractor",
    description="API for extracting financial and organizational data from IRS Form 990 PDFs",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
pdf_processor = PDFProcessor()
field_extractor = FieldExtractor()

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check"""
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )


@app.post("/api/extract", response_model=ExtractionResponse)
async def extract_form_990(
    file: UploadFile = File(...),
    force_ocr: bool = False
):
    """
    Extract data from an IRS Form 990 PDF
    
    Args:
        file: PDF file to process
        force_ocr: If True, use OCR instead of text extraction
        
    Returns:
        ExtractionResponse with extracted fields
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")
    
    try:
        # Save uploaded file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Processing file: {file.filename}")
        
        # Process PDF
        full_text, pages_data, extraction_method = pdf_processor.process_pdf(
            temp_path, 
            force_ocr=force_ocr
        )
        
        # Extract fields
        result = field_extractor.extract_all_fields(
            full_text, 
            pages_data, 
            file.filename
        )
        result.extraction_method = extraction_method
        
        logger.info(f"Successfully extracted data from {file.filename}")
        
        return ExtractionResponse(
            success=True,
            message=f"Successfully extracted data from {file.filename}",
            data=result
        )
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )
        
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {e}")


@app.post("/api/extract/v2", response_model=ExtractionResponseV2)
async def extract_form_990_v2(
    file: UploadFile = File(...),
    confidence_threshold: float = 0.7,
    fail_fast: bool = True
):
    """
    Enhanced Form 990 extraction with confidence scoring (V2)

    Features:
    - Dual PDF extraction (pdfplumber + pdfminer.six)
    - Form 990 page detection (skips Form 8868, cover pages)
    - OCR artifact cleaning
    - Per-field confidence scores
    - Cross-field validation
    - Fail-fast with configurable threshold

    Args:
        file: PDF file to process
        confidence_threshold: Minimum confidence score (0.0-1.0, default 0.7)
        fail_fast: If True, reject extractions below threshold

    Returns:
        ExtractionResponseV2 with confidence scores and validation
    """
    if not file.filename.lower().endswith('.pdf'):
        return ExtractionResponseV2(
            success=False,
            message="Only PDF files are supported",
            confidence=0.0
        )

    # Save uploaded file
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    async with aiofiles.open(filepath, 'wb') as f:
        content = await file.read()
        await f.write(content)

    try:
        # Use hybrid extraction (V2 infrastructure + V1 field extraction)
        from services.field_extractor_hybrid import HybridFieldExtractor
        extractor = HybridFieldExtractor()
        result = extractor.extract_all_fields_v2_hybrid(filepath)

        # Check fail-fast threshold
        if fail_fast and result.overall_confidence < confidence_threshold:
            return ExtractionResponseV2(
                success=False,
                message=f"Extraction confidence ({result.overall_confidence:.2f}) below threshold ({confidence_threshold}). Manual review required.",
                data=result,
                confidence=result.overall_confidence
            )

        logger.info(f"Successfully extracted {file.filename} with confidence {result.overall_confidence:.2f}")

        return ExtractionResponseV2(
            success=True,
            message=f"Extraction completed successfully with confidence {result.overall_confidence:.2f}",
            data=result,
            confidence=result.overall_confidence
        )

    except Exception as e:
        logger.error(f"V2 Extraction error for {file.filename}: {e}")
        return ExtractionResponseV2(
            success=False,
            message=f"Extraction failed: {str(e)}",
            confidence=0.0
        )
    finally:
        # Clean up temp file
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {e}")


@app.post("/api/extract-batch", response_model=dict)
async def extract_batch(files: list[UploadFile] = File(...)):
    """
    Extract data from multiple Form 990 PDFs
    
    Args:
        files: List of PDF files to process
        
    Returns:
        Dictionary with results for each file
    """
    results = []
    
    for file in files:
        try:
            # Process each file using the single extraction endpoint logic
            if not file.filename.lower().endswith('.pdf'):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Only PDF files are supported"
                })
                continue
            
            file_id = str(uuid.uuid4())
            temp_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")
            
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            full_text, pages_data, extraction_method = pdf_processor.process_pdf(temp_path)
            result = field_extractor.extract_all_fields(full_text, pages_data, file.filename)
            result.extraction_method = extraction_method
            
            results.append({
                "filename": file.filename,
                "success": True,
                "data": result.model_dump()
            })
            
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total_files": len(files),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
