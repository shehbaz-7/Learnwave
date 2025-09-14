# Learnwave: Your Personal AI-Powered Learning Environment

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-black?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![Google Gemini](https://img.shields.io/badge/Google-Gemini_Pro-4285F4?style=for-the-badge&logo=google)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

Learnwave is a sophisticated, local-first desktop application designed to transform your study materials—PDFs and YouTube videos—into an interactive and intelligent learning hub. Powered by Google's Gemini Pro, it goes beyond simple file storage to create a personalized educational experience right on your machine.

*(Placeholder for an application screenshot or GIF)*
`![Learnwave Demo]()`

---

## Core Features

*   🧠 **AI-Powered Semantic Search & Chat:** Ask complex questions in natural language. The application understands the *context* of your query, searches its vector index for the most relevant passages from your documents, and uses Gemini to synthesize a comprehensive answer with precise source citations.

*   📚 **Multi-Content Repository:** Effortlessly index and manage both PDF documents and YouTube videos. The system automatically processes content, performs OCR on image-based pages, and analyzes video transcripts to make everything searchable.

*   🎓 **Automated Study Tools:** Instantly generate multiple-choice quizzes and flashcard decks from any document. You can specify the difficulty level and number of questions to create tailored study sessions that reinforce learning.

*   🚀 **Interactive Learning Paths:** The "God-level" feature. Learnwave can analyze an entire document and automatically generate a multi-step, interactive learning path. Each step is a self-contained, beautifully animated HTML module designed to explain a core concept visually.

*   ☁️ **Google Drive Synchronization:** Designed for educational settings, an administrator can maintain a master library of content in Google Drive. Users (grouped by academic year) can then sync this curated library to their local machines, ensuring everyone has the latest materials.

*   🔒 **Private & Secure:** The entire application runs locally. Your documents, search indices, and API keys are stored on your device, ensuring your data remains private.

---

## Tech Stack

*   **Backend:** Python, Flask, Waitress
*   **AI & Machine Learning:**
    *   Google Gemini Pro for chat, analysis, and content generation.
    *   `sentence-transformers` for creating text embeddings.
    *   `faiss` (from Facebook AI) for efficient similarity search in the vector database.
*   **Database:** SQLAlchemy with SQLite for application and user data.
*   **File Processing:** PyPDF2 for text extraction, Google Drive API for cloud sync.
*   **Frontend:** Standard HTML, CSS, JavaScript with Bootstrap 5 for styling.
*   **Packaging:** PyInstaller (intended use) to create a standalone desktop application.

---

## Setup and Installation

Follow these steps to get a local development environment running.

### Prerequisites

*   Python 3.9+ and `pip`
*   Git
*   A Google Account

### 1. Set Up Google Drive API Credentials

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project.
3.  Enable the **Google Drive API** for your project.
4.  Go to "Credentials", click "Create Credentials" -> "OAuth client ID".
5.  Choose "Desktop app" as the application type.
6.  Download the JSON file. Rename it to `credentials.json` and place it in the root directory of this project. **This file is critical for authentication.**

### 2. Set Up Your Gemini API Key

1.  Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2.  Click "Create API key" and copy your new key. You will need to enter this in the application's UI after registering.

### 3. Clone & Install Dependencies

```bash
# Clone the repository
git clone https://github.com/your-username/learnwave.git
cd learnwave

# Create and activate a virtual environment
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate

# Install the required packages
pip install -r requirements.txt
```
*(Note: A `requirements.txt` file would need to be generated with `pip freeze > requirements.txt`)*

### 4. Configure Google Drive Folders

1.  In Google Drive, create folders for each academic year and an "Admin" folder.
2.  Get the ID for each folder from its URL (`https://drive.google.com/drive/folders/THIS_IS_THE_ID`).
3.  In `main.py`, update the `YEAR_FOLDER_IDS` dictionary with your folder IDs.

### 5. Run the Application

```bash
python run.py
```

The application will start two servers:
*   A preloader/startup server on `http://127.0.0.1:5000`
*   The main Flask application on `http://127.0.0.1:5001`

A browser window should automatically open to the startup loader. Once the backend initializes, it will redirect to the main application.

---

## How It Works

1.  **Initialization (`run.py`):** A lightweight Flask app (`preloader_app`) starts on port 5000, showing a loading screen while the main application initializes in a separate thread.
2.  **Authentication (`google_auth.py`):** The main app first authenticates with Google. On the first run, this opens a browser window for you to grant the app permission to access your Google Drive. It saves a `token.json` for future sessions.
3.  **User Registration:** You create a local account, providing your Gemini API key and selecting your academic year.
4.  **Syncing (`routes.py` -> `/loading`):** The app checks for local data corresponding to your selected year. If it doesn't exist, it syncs all the files from the configured Google Drive folder for that year.
5.  **Processing (Admin):** When an admin uploads a PDF or YouTube video, a background thread is spawned.
    *   **PDFs (`pdf_processor.py`):** Text is extracted from each page. If a page has little text, it's treated as an image and sent to Gemini's multimodal endpoint for visual analysis (OCR + description).
    *   **Videos (`youtube_processor.py`):** The video is sent to Gemini for a full, time-stamped transcript analysis.
    *   **Indexing:** The content of each page/segment is analyzed by Gemini to generate titles, topics, and a rich `ENHANCED_TEXT` description optimized for vector search.
6.  **Vector Database (`vector_db.py`):** The `ENHANCED_TEXT` from each chunk is converted into a vector embedding and stored in a local FAISS index. This allows for incredibly fast and accurate semantic search.
7.  **Chat (`routes.py` -> `/chat/message`):** Your question is first refined by Gemini based on conversation history. The refined query is used to search the FAISS index. The top results (context) are then sent back to Gemini along with your original question to generate a final, cited answer.

