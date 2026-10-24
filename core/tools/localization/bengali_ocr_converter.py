import os

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from google.cloud import vision
    from google.oauth2 import service_account

    HAS_GOOGLE_VISION = True
except ImportError:
    HAS_GOOGLE_VISION = False
    vision = None
    service_account = None

from core.logging_config import logger


def setup_google_vision(credentials_path=None):
    """Setup Google Cloud Vision client or return None if unavailable"""
    if not HAS_GOOGLE_VISION or vision is None:
        logger.info("Google Cloud Vision not installed; using local OCR fallback.")
        return None
    try:
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            return vision.ImageAnnotatorClient(credentials=credentials)
        return vision.ImageAnnotatorClient()
    except Exception as exc:
        logger.warning(f"Could not initialize Google Vision client: {exc}")
        return None


def extract_text_from_image(client, image_path):
    """Extract text from image using Google Cloud Vision API, with fallback to LocalOCRExtractor"""
    if not os.path.exists(image_path):
        logger.error(f"Image path not found: {image_path}")
        return ""

    if client is not None and HAS_GOOGLE_VISION and vision is not None:
        try:
            with open(image_path, "rb") as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            image_context = vision.ImageContext(language_hints=["bn"])

            response = client.text_detection(image=image, image_context=image_context)
            texts = response.text_annotations

            if response.error.message:
                raise RuntimeError(f"API Error: {response.error.message}")

            if texts:
                return texts[0].description
            return ""
        except Exception as exc:
            logger.warning(
                f"Google Vision extraction failed: {exc}. Falling back to LocalOCRExtractor."
            )

    # Resilient local fallback via LocalOCRExtractor
    try:
        from tools.localization.local_ocr_extractor import LocalOCRExtractor

        extractor = LocalOCRExtractor(languages=["bn", "en"])
        result = extractor.extract_text(image_path)
        return result.get("text", "")
    except Exception as exc:
        logger.error(f"Local OCR fallback failed: {exc}")
        return ""


def parse_table_text(text):
    """Parse extracted text into table format"""
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Try to detect table structure
    table_data = []
    for line in lines:
        # Split on multiple spaces or tabs (common in tabular data)
        import re

        cells = re.split(r"\s{2,}|\t", line)
        cells = [cell.strip() for cell in cells if cell.strip()]
        if cells:
            table_data.append(cells)

    return table_data


def convert_image_to_excel(image_path, excel_path, client):
    """Convert single image to Excel file"""
    try:
        # Extract text
        text = extract_text_from_image(client, image_path)

        if not text:
            logger.info(f"No text found in {os.path.basename(image_path)}")
            return False

        # Parse into table format
        table_data = parse_table_text(text)

        if not table_data:
            # Fallback: save raw text
            df = pd.DataFrame({"Extracted_Text": [text]})
        else:
            # Create DataFrame from table data
            max_cols = max(len(row) for row in table_data)
            # Pad rows to have same number of columns
            padded_data = []
            for row in table_data:
                padded_row = row + [""] * (max_cols - len(row))
                padded_data.append(padded_row)

            df = pd.DataFrame(padded_data)

        # Add metadata
        metadata_df = pd.DataFrame(
            {
                "Property": [
                    "Image_File",
                    "Text_Length",
                    "Table_Rows",
                    "Table_Columns",
                ],
                "Value": [
                    os.path.basename(image_path),
                    len(text),
                    len(table_data) if table_data else 0,
                    max_cols if table_data else 1,
                ],
            }
        )

        # Save to Excel with multiple sheets
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            metadata_df.to_excel(writer, sheet_name="Metadata", index=False)
            df.to_excel(writer, sheet_name="Data", index=False)

        logger.success(
            f"Converted {os.path.basename(image_path)} to {os.path.basename(excel_path)}"
        )
        return True

    except (OSError, ValueError, RuntimeError) as e:
        # সুনির্দিষ্ট ত্রুটি ক্যাচ করে লগ করা হলো, যাতে অন্য অপ্রত্যাশিত সমস্যাগুলো চাপা না পড়ে
        logger.error(f"Error processing {os.path.basename(image_path)}: {e!s}")
        return False


def batch_convert_images(folder_path, credentials_path=None):
    """Convert all images in folder to Excel files"""
    # Setup client
    client = setup_google_vision(credentials_path)

    # Get all JPG files
    image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".jpg")]
    image_files.sort()

    logger.info(f"Found {len(image_files)} images to process")

    success_count = 0
    for image_file in image_files:
        image_path = os.path.join(folder_path, image_file)
        base_name = os.path.splitext(image_file)[0]
        excel_path = os.path.join(folder_path, f"{base_name}_vision.xlsx")

        if convert_image_to_excel(image_path, excel_path, client):
            success_count += 1

    logger.info(
        f"Conversion completed: {success_count}/{len(image_files)} images processed successfully"
    )


if __name__ == "__main__":
    # Usage example
    folder = r"C:\Users\Nazifa\supremeai\Image purbolch"

    # If you have credentials file, specify the path
    # credentials_path = r"path\to\your\service-account-key.json"

    # For now, try without credentials (requires GOOGLE_APPLICATION_CREDENTIALS env var)
    try:
        batch_convert_images(folder)
    except Exception as e:
        logger.critical(f"Setup error: {e}")
        logger.critical("Please ensure you have set up Google Cloud Vision API credentials")
        logger.critical("Either:")
        logger.critical("1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        logger.critical("2. Or provide credentials file path to batch_convert_images()")
