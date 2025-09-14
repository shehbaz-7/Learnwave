import os
import logging
import PyPDF2
from PyPDF2 import PdfWriter
from concurrent.futures import ThreadPoolExecutor, as_completed
from gemini_client import GeminiClient

gemini_client = GeminiClient()

def _extract_enhanced_text_from_analysis(analysis_text):
    """Helper to robustly extract ENHANCED_TEXT from Gemini's analysis output."""
    if not analysis_text:
        return ""
    try:
        # Find the start of the enhanced text section
        start_tag = "###ENHANCED_TEXT###"
        start_index = analysis_text.find(start_tag)
        if start_index == -1:
            # If the tag is missing, return the whole text as a fallback
            return analysis_text.strip()
        
        start_index += len(start_tag)
        
        # Find the start of the *next* ### section to ensure we only get the enhanced text
        next_section_index = analysis_text.find("###", start_index)
        
        if next_section_index != -1:
            # If another section exists, slice the string
            return analysis_text[start_index:next_section_index].strip()
        else:
            # If it's the last section, take the rest of the string
            return analysis_text[start_index:].strip()
            
    except Exception as e:
        logging.error(f"Error parsing enhanced text: {e}")
        return analysis_text.strip() # Fallback to returning the full analysis

class PDFProcessor:
    def __init__(self, config):
        self.config = config

    def _analyze_page_worker(self, page_job):
        job_type, data, page_number, original_filename, api_key = page_job
        
        analysis_result = ""
        raw_text = ""
        
        if job_type == 'text':
            raw_text = self._clean_text(data)
            analysis_result = gemini_client.analyze_page_for_indexing(raw_text, original_filename, api_key)
        elif job_type == 'image':
            single_page_path = data
            analysis_result = gemini_client.analyze_pdf_page_for_indexing(single_page_path, page_number, original_filename, api_key)
            
            # --- START OF THE FIX ---
            # After visual analysis, extract the rich text and use it as the primary text_content.
            # This ensures that even image-based pages have their text available for all features.
            raw_text = _extract_enhanced_text_from_analysis(analysis_result)
            # --- END OF THE FIX ---

            if os.path.exists(single_page_path):
                os.remove(single_page_path)

        return {
            'page_number': page_number,
            'text_content': raw_text, # This will now always have content if analysis was successful
            'gemini_analysis': analysis_result,
        }

    def process_pdf(self, file_path, doc_id, api_key, original_filename):
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                
                yield {"status_text": f"Extracting text (0/{num_pages})"}
                
                page_jobs = []
                for i in range(num_pages):
                    page = pdf_reader.pages[i]
                    raw_text = page.extract_text() or ""
                    page_number = i + 1
                    
                    if len(raw_text.strip()) < 100:
                        single_page_path = self._extract_single_page(file_path, i)
                        if single_page_path:
                            page_jobs.append(('image', single_page_path, page_number, original_filename, api_key))
                    else:
                        page_jobs.append(('text', raw_text, page_number, original_filename, api_key))
                
                processed_count = 0
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_page = {executor.submit(self._analyze_page_worker, job): job for job in page_jobs}
                    
                    for future in as_completed(future_to_page):
                        try:
                            result = future.result()
                            processed_count += 1
                            yield {"status_text": f"Processing page {processed_count}/{num_pages}"}
                            yield {"page_data": result}
                        except Exception as exc:
                            page_num_err = future_to_page[future][2]
                            logging.error(f'Page {page_num_err} generated an exception: {exc}')

        except Exception as e:
            logging.error(f"Error processing PDF file {file_path}: {str(e)}", exc_info=True)
            raise

    def _extract_single_page(self, original_path, page_index):
        try:
            base, _ = os.path.splitext(os.path.basename(original_path))
            temp_filename = f"{base}_page_{page_index + 1}_temp_{os.urandom(4).hex()}.pdf"
            temp_path = os.path.join(self.config['UPLOAD_FOLDER'], temp_filename)
            
            with open(original_path, 'rb') as infile:
                reader = PyPDF2.PdfReader(infile)
                writer = PdfWriter()
                if page_index < len(reader.pages):
                    writer.add_page(reader.pages[page_index])
                    with open(temp_path, 'wb') as outfile:
                        writer.write(outfile)
                    return temp_path
                return None
        except Exception as e:
            logging.error(f"Failed to extract page {page_index + 1} from {original_path}: {e}")
            return None

    def _clean_text(self, text):
        if not text: return ""
        text = ' '.join(text.split())
        text = text.replace('\x00', '').replace('\ufeff', '')
        return text.strip()
