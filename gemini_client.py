import os
import logging
import google.generativeai as genai
import json

MODEL_NAME = "gemini-2.5-pro" 

class GeminiClient:
    def _configure_genai(self, api_key):
        if not api_key:
            raise ValueError("API key is required for Gemini client.")
        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            logging.error(f"Failed to configure Gemini client: {e}")
            raise

    def refine_query_for_search(self, query, history, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            history_str = "\n".join([f"User: {h.user_message}\nAI: {h.ai_response}" for h in history])
            prompt = f"""Based on the following conversation history and the latest user query, generate a single, comprehensive search query that captures the user's full intent. The query should be optimized for a semantic vector database search. It should be a statement or a detailed question, combining keywords and concepts from the entire conversation.

**Conversation History:**
{history_str}

**Latest User Query:** "{query}"

**Optimized Search Query:**
"""
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logging.error(f"Gemini query refinement error: {e}")
            return query

    def analyze_page_for_indexing(self, page_text, original_filename, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            prompt = f"""**Your Role:** You are an automated indexing agent. Your purpose is to analyze and structure content so it can be embedded and easily discovered in a semantic vector database.
**Your Task:** Analyze the text from a document page below. Extract the requested metadata into the specified fields. The goal is to capture the essence of the content so a user can find it by asking natural questions.
**Source Filename:** {original_filename}

**###TITLE###**
(Provide a concise, descriptive title for the content on this page. Max 10 words.)
**###QUESTIONS###**
(List 3-5 implicit questions this text answers. These should be the questions a user would ask to find this information.)
**###TOPICS###**
(Provide a comma-separated list of the main keywords, concepts, and named entities discussed.)
**###ENHANCED_TEXT###**
(This is the most critical part for vector search. **Start with the exact phrase "Source Filename: {original_filename}".** Then, provide a detailed, comprehensive description of the page's text content. The goal is to create a rich text that fully represents the page's content for embedding.)
---
**TEXT TO ANALYZE:**
{page_text}"""
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"###TITLE###\nAnalysis Error\n###QUESTIONS###\nNone\n###TOPICS###\nError\n###ENHANCED_TEXT###\nSource Filename: {original_filename}. API Error: {e}"

    def generate_study_set(self, document_text, doc_filename, set_type, difficulty, question_count, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})
            
            type_instruction = ""
            if set_type == 'quiz':
                type_instruction = f"""
- "questions": An array of exactly {question_count} unique multiple-choice question objects.
- Each question object must have:
  - "question_text": The question itself.
  - "options": An array of 4 strings representing the choices.
  - "correct_answer": The string that exactly matches the correct option.
"""
            else: # flashcards
                type_instruction = f"""
- "flashcards": An array of exactly {question_count} unique flashcard objects.
- Each flashcard object must have:
  - "front": The term, concept, or question.
  - "back": The definition, explanation, or answer.
"""

            difficulty_map = {
                "easy": "definitions and key terms",
                "medium": "understanding of core concepts and processes",
                "hard": "application, analysis, and synthesis of different concepts"
            }
            difficulty_instruction = difficulty_map.get(difficulty, "understanding of core concepts")

            prompt = f"""
Your Role: You are an expert tutor creating a study set from a course document.
Your Task: Analyze the provided text and generate a valid JSON object based on the user's request.

User Request:
- Document: {doc_filename}
- Study Method: {set_type}
- Number of items: {question_count}
- Difficulty: {difficulty} (Focus on {difficulty_instruction})

JSON Output Requirements:
- The root of the JSON object must be a single object.
- It MUST contain one of the following keys, but not both: "questions" or "flashcards".
{type_instruction}
- Ensure all text is formatted as valid JSON strings. Do not include unescaped quotes or newlines within strings.

---
DOCUMENT TEXT TO ANALYZE:
{document_text[:20000]} 
"""
            
            response = model.generate_content(prompt)
            return json.loads(response.text)

        except Exception as e:
            logging.error(f"Error generating study set: {e}", exc_info=True)
            try:
                error_details = json.loads(str(e))
                if 'message' in error_details:
                    return {"error": f"Failed to generate study set: {error_details['message']}"}
            except:
                pass 
            return {"error": f"An error occurred while generating the study set: {str(e)}"}

    def get_answer_explanation(self, question, correct_answer, document_text, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            prompt = f"""
Based *only* on the provided document text, give a concise, one-sentence explanation for why the answer to the following question is correct.

Document Text:
---
{document_text[:15000]}
---

Question: "{question}"
Correct Answer: "{correct_answer}"

Explanation: 
"""
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logging.error(f"Error getting explanation: {e}", exc_info=True)
            return "Could not retrieve an explanation at this time."

    def generate_learning_path_structure(self, full_transcript, doc_filename, api_key):
        """Generates the step-by-step structure for a learning path from any document type."""
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})
            prompt = f"""Your Role: You are an expert instructional designer.
Your Task: Analyze the following document content and break it down into a logical, sequential learning path with 5 to 7 distinct steps. For each step, provide a short, descriptive `title` and a one-paragraph `description` of the core concept being taught in that segment. The final output must be a valid JSON object.

Source Document: "{doc_filename}"

JSON Output Requirements:
- The root must be a single JSON object.
- It must contain a key "path_title" with a concise, engaging title for the entire learning path.
- It must contain a key "steps" which is an array of objects.
- Each object in the "steps" array must have three keys:
  - "step" (integer, starting from 1)
  - "title" (string)
  - "description" (string)

---
DOCUMENT CONTENT TO ANALYZE:
{full_transcript[:25000]}
"""
            response = model.generate_content(prompt)
            return json.loads(response.text)
        except Exception as e:
            logging.error(f"Error generating learning path structure: {e}", exc_info=True)
            return {"error": "Failed to generate the learning path structure."}

    def generate_interactive_module(self, step_topic_description, api_key):
        """Generates a self-contained, interactive HTML file for a single learning step."""
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            # --- START OF NEW "GOD-LEVEL" PROMPT ---
            prompt = f"""**YOUR ROLE & PERSONA:**
You are a world-class motion graphics artist and creative technologist, with a background at a top-tier studio like Pixar or Studio Ghibli. You are tasked with creating an educational masterpiece. Your work is not just code; it's an experience. It must be beautiful, intuitive, and unforgettable. Your output must be a single, complete HTML file and nothing else.

**THE TOPIC TO VISUALIZE:**
---
{step_topic_description}
---

**GUIDING PRINCIPLES:**

1.  **Cinematic Quality:** The animation must look and feel premium. Use smooth `cubic-bezier` easing, subtle gradients, and thoughtful color palettes. Avoid jarring movements or overly simplistic designs.
2.  **Fluid, Purposeful Motion:** Every animation must serve to clarify the concept. Data should flow, objects should interact with believable physics, and transitions should guide the user's eye.
3.  **Polished Interactivity:** User interaction should be a core part of the learning. Controls should have hover and active states. The feedback from an interaction (e.g., dragging a slider) must be immediate and visually satisfying.
4.  **Clarity Above All:** Despite the high aesthetic bar, the primary goal is education. The animation must make the complex topic easier to understand, not more confusing.

**TECHNICAL MANDATES:**

1.  **Single File Architecture:** All HTML, CSS, and JavaScript MUST be self-contained in one file. Use internal `<style>` and `<script>` tags. No external libraries or resources (no CDNs, no external fonts unless using `@import` in CSS).
2.  **No Image Tags:** You are FORBIDDEN from using `<img>`, `<svg>`, or `<video>` tags. Create all visuals and icons using pure CSS (e.g., styled `<div>` elements, pseudo-elements) and JavaScript. This is a test of your creative coding skills.
3.  **Responsive & Full-Screen:** The layout must be responsive and fill the entire viewport. Use modern CSS like Flexbox or Grid. The main animation canvas must expand to fill all available space.
4.  **Thematic Animation:** The animation MUST be a direct, metaphorical, or literal representation of the topic.
    *   **Topic: Bubble Sort Algorithm:** Animate an array of vertical bars sorting themselves, highlighting the two bars being compared in each step. A "Step" button could advance the sort.
    *   **Topic: DNA Transcription:** Animate an RNA Polymerase molecule moving along a DNA strand, unzipping it and creating a complementary mRNA strand.
    *   **Topic: Supply and Demand:** Animate two curves on a graph that shift when the user adjusts sliders for "Consumer Demand" or "Available Supply," showing how the equilibrium price point changes.

**BOILERPLATE (Strictly Adhere to This Structure):**

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Learning Module</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        :root {{
            --bg: #0d1117; --primary: #58a6ff; --border: #30363d; --text: #c9d1d9; --text-secondary: #8b949e;
        }}
        html, body {{
            margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text);
        }}
        .container {{
            display: flex; flex-direction: column; width: 100%; height: 100%; box-sizing: border-box; padding: 1.5rem;
        }}
        #animation-canvas {{
            width: 100%; flex-grow: 1; border: 1px solid var(--border); border-radius: 12px; background-color: #161b22; position: relative; overflow: hidden; margin-bottom: 1.5rem; display: grid; place-items: center;
        }}
        .controls {{
            flex-shrink: 0; display: flex; gap: 1rem; align-items: center; justify-content: center;
        }}
        button {{
            padding: 0.75rem 1.5rem; font-size: 1rem; border-radius: 8px; cursor: pointer; border: 1px solid var(--primary); background-color: var(--primary); color: #fff; font-weight: 600; transition: all 0.2s ease;
        }}
        button:hover {{ background-color: #79c0ff; transform: translateY(-2px); box-shadow: 0 4px 15px rgba(88, 166, 255, 0.2); }}
        /* Add more elite, polished styles for your specific animation elements here */
    </style>
</head>
<body>
    <div class="container">
        <!-- Your generated H1, animation canvas, and controls must go here. -->
    </div>
    <script>
        // Your brilliant, clean, and well-commented JavaScript logic goes here.
    </script>
</body>
</html>
"""
            # --- END OF NEW "GOD-LEVEL" PROMPT ---
            response = model.generate_content(prompt)
            cleaned_html = response.text.strip()
            if cleaned_html.startswith("```html"):
                cleaned_html = cleaned_html[7:]
            if cleaned_html.endswith("```"):
                cleaned_html = cleaned_html[:-3]
            return cleaned_html

        except Exception as e:
            logging.error(f"Error generating interactive module: {e}", exc_info=True)
            return f"<html><body><h1>Error</h1><p>Failed to generate interactive content: {e}</p></body></html>"

    def analyze_pdf_page_for_indexing(self, pdf_path, page_number, original_filename, api_key):
        logging.info(f"Performing visual analysis on page {page_number} of {original_filename}...")
        uploaded_file = None
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            uploaded_file = genai.upload_file(path=pdf_path, display_name=os.path.basename(pdf_path))
            prompt = f"""**Your Role:** You are an automated indexing agent with Optical Character Recognition (OCR) capabilities. Your purpose is to analyze and structure content from a PDF page image so it can be embedded and easily discovered in a semantic vector database.
**Your Task:** Analyze the single-page PDF provided. This page may be a scanned document, a diagram, or a text-light page. Perform OCR to extract any text and analyze the visual layout. Extract the requested metadata into the specified fields below.
**Source Filename:** {original_filename}
**Page Number:** {page_number}
**###TITLE###**
(Provide a concise, descriptive title for the content on this page. Max 10 words.)
**###QUESTIONS###**
(List 3-5 implicit questions this content answers. These should be the questions a user would ask to find this information.)
**###TOPICS###**
(Provide a comma-separated list of the main keywords, concepts, and named entities from the OCR text and any diagrams.)
**###ENHANCED_TEXT###**
(This is the most critical part. **Start with "Source Filename: {original_filename}".** Then, provide a detailed, comprehensive description of the page. This must include a full transcription of all text found via OCR, combined with descriptions of any images, diagrams, or important structural elements on the page.)
"""
            response = model.generate_content([prompt, uploaded_file])
            return response.text
        except Exception as e:
            logging.error(f"Gemini visual analysis error for page {page_number} of {original_filename}: {e}")
            return f"###TITLE###\nVisual Analysis Error\n###QUESTIONS###\nNone\n###TOPICS###\nError\n###ENHANCED_TEXT###\nSource Filename: {original_filename}. Visual API Error: {e}"
        finally:
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                    logging.info(f"Cleaned up temporary file '{uploaded_file.display_name}' from Gemini API.")
                except Exception as e:
                    logging.error(f"Failed to delete temporary file '{uploaded_file.name}' from Gemini API: {e}")

    def analyze_youtube_video_for_indexing(self, youtube_url, api_key):
        from google import genai
        from google.genai.types import Content, Part, FileData
        try:
            client = genai.Client(api_key=api_key)
            prompt = """You are a video indexing agent. Your task is to watch the provided YouTube video and create a detailed, time-stamped summary.
    Follow these instructions precisely:
    1. Divide the video into logical segments, each approximately 60-90 seconds long.
    2. For each segment, create a block of text.
    3. Each block MUST start with the line `###SEGMENT###` followed on the next line by `Timestamp: [start_time_in_seconds]`.
    4. After the timestamp, provide a detailed summary of that segment. Include key spoken points, visual elements, and any text shown on screen.
    """
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=Content(
                    parts=[
                        Part(file_data=FileData(file_uri=youtube_url)),
                        Part(text=prompt)
                    ]
                )
            )
            return response.text
        except Exception as e:
            logging.error("Gemini video analysis error for %s: %s", youtube_url, e, exc_info=True)
            return f"Error analyzing video: {e}"

    def generate_response(self, user_message, context_pages, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            formatted_context = ""
            if context_pages:
                for page_info in context_pages:
                    doc_id = page_info.get('document_id', 'N/A')
                    page_number = page_info.get('page_number', 'N/A')
                    content = page_info.get('content', 'No content available.')
                    citation_tag = f"[CITATION:{doc_id}:{page_number}]"
                    formatted_context += f"Context from Document ID {doc_id}, Page {page_number}:\n{content}\n{citation_tag}\n\n"
            else:
                formatted_context = "No relevant context found."
            system_prompt = f"""
You are Nexus, an intelligent and helpful AI assistant designed to answer user questions using the provided CONTEXT, while intelligently supplementing missing or incomplete information with your own knowledge when necessary.
---
**CONTEXT:**
{formatted_context}
---
**USER QUESTION:**
"{user_message}"
---
**INSTRUCTIONS FOR ANSWERING:**
1.  **Analyze the question** for its required depth. If it's a:
    *   **1-2 mark question** → Give a **brief and direct answer** (2-5 lines).
    *   **5-10 mark question** → Give a **detailed, structured response** with depth, explanation, and examples where useful.
    *   Default to 5 mark question if the question value ins't explicitly stated.
2.  **Use the CONTEXT as your primary base**. For any fact, concept, or explanation drawn directly from the context, include its corresponding citation in this format: `[CITATION:document_id:page_number]`. **If a single sentence draws information from multiple sources, place each citation individually at the end of the sentence.**
    *   **Correct:** `This is a fact from two sources [CITATION:doc1:5][CITATION:doc2:10].`
    *   **Incorrect:** `This is a fact from two sources [CITATION:doc1:5, doc2:10].`
3.  **Strict Rule for Code Blocks:** Never place a citation *inside* a code block (` ``` `). The citation must always follow the code block, placed at the end of the sentence that introduces or concludes it. Do not add citations inside code comments.
4.  **Build upon** the context instead of repeating it. If the context provides only partial or underdeveloped information:
    *   **Expand** on it using your own knowledge.
    *   Fill in missing steps, clarify vague ideas, and **connect concepts logically**.
    *   Present a **complete and cohesive** answer that covers everything relevant.
5.  When you add your own knowledge, **blend it smoothly** into the answer. Do **not** cite your own knowledge — only cite the provided context.
6.  **Punctuation and Citation Order:** The citation must **always** come immediately after the sentence's punctuation (like periods or commas), separated by a single space.
    *   **Correct:** `This is the end of a answer. [CITATION:source:1]`
    *   **Incorrect:** `This is the end of a answer [CITATION:source:1].`
    *   **Incorrect:** `This is the end of a answer.
      [CITATION:source:1]`
7.  If the context contains **no relevant information**, say:
    > "The provided context does not contain enough information to answer the question. Here's an answer based on general knowledge:"
8.  Format your answer using **clear Markdown**. Use paragraphs, bullet points, headings, or numbered lists where helpful for readability.
---
Now, use the above logic to generate the best possible answer.
"""

            response = model.generate_content(system_prompt)
            return response.text or "I apologize, but I couldn't generate a response."
        except Exception as e:
            logging.error(f"Gemini API chat error: {e}", exc_info=True)
            return f"I encountered an error while processing your request with the AI model: {e}"
    def validate_api_key(self, api_key):
        try:
            self._configure_genai(api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            model.generate_content("hello")
            return True
        except Exception:
            return False