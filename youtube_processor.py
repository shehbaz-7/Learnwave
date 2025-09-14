import logging
from gemini_client import GeminiClient
import re

gemini_client = GeminiClient()

class YouTubeProcessor:

    def _parse_timestamp_to_seconds(self, time_str: str) -> int:
        """
        Parses a timestamp string (e.g., "HH:MM:SS", "MM:SS", "SS") into total seconds.
        """
        if not time_str or not time_str.strip():
            return 0
        
        parts = list(map(int, time_str.strip().split(':')))
        
        if len(parts) == 3:  # HH:MM:SS
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:  # MM:SS
            return parts[0] * 60 + parts[1]
        elif len(parts) == 1:  # SS
            return parts[0]
        else:
            logging.warning(f"Could not parse unrecognized timestamp format: '{time_str}'. Defaulting to 0.")
            return 0

    def process_video(self, youtube_url, doc_id, api_key, original_filename):
        try:
            logging.info(f"Starting Gemini analysis for YouTube URL: {youtube_url}")
            
            full_analysis = gemini_client.analyze_youtube_video_for_indexing(youtube_url, api_key)
            
            if not full_analysis or "###SEGMENT###" not in full_analysis:
                logging.error("Gemini analysis for video did not return valid segments.")
                analysis_result = gemini_client.analyze_page_for_indexing(full_analysis, original_filename, api_key)
                yield {"page_data": {
                    'page_number': 1, 'start_time_seconds': 0, 'text_content': full_analysis,
                    'gemini_analysis': analysis_result
                }}
                return

            segments = full_analysis.split("###SEGMENT###")[1:]
            total_segments = len(segments)
            yield {"status_text": f"Analyzing video segments (0/{total_segments})"}
            
            for i, segment_text in enumerate(segments):
                yield {"status_text": f"Processing segment {i+1}/{total_segments}"}
                
                # --- START OF MODIFICATION ---
                # Use a more robust regex to find the timestamp line, then parse it.
                time_match = re.search(r"Timestamp:\s*([\d:]+)", segment_text)
                time_str = time_match.group(1) if time_match else "0"
                total_seconds = self._parse_timestamp_to_seconds(time_str)
                # --- END OF MODIFICATION ---
                
                content = re.sub(r"Timestamp:\s*[\d:]+\s*\n", "", segment_text).strip()
                
                gemini_analysis_for_segment = gemini_client.analyze_page_for_indexing(content, original_filename, api_key)

                yield {"page_data": {
                    'page_number': i + 1, 
                    'start_time_seconds': total_seconds, # Save the correctly calculated total seconds
                    'text_content': content, 
                    'gemini_analysis': gemini_analysis_for_segment
                }}

        except Exception as e:
            logging.error(f"Error processing YouTube video {youtube_url}: {str(e)}", exc_info=True)
            raise