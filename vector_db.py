import os
import pickle
import logging
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy import create_engine
from models import PDFPage

MODEL_NAME = 'all-MiniLM-L6-v2'

class VectorDatabase:
    def __init__(self, index_base_path):
        if not index_base_path:
            raise ValueError("VectorDatabase requires a valid index_base_path.")
            
        self.model = SentenceTransformer(MODEL_NAME)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self.faiss_index = None
        self.page_map = {}
        
        self.index_path_base = index_base_path
        os.makedirs(self.index_path_base, exist_ok=True)
        
        self.faiss_index_path = os.path.join(self.index_path_base, 'faiss_index.idx')
        self.page_map_path = os.path.join(self.index_path_base, 'page_map.pkl')
        
        self.load_index()

    def _initialize_faiss_index(self):
        index = faiss.IndexFlatL2(self.dimension)
        self.faiss_index = faiss.IndexIDMap(index)
        self.page_map = {}
        logging.info("Initialized a new, empty FAISS IndexIDMap.")

    def build_full_index(self):
        logging.info(f"Performing full index rebuild in '{self.index_path_base}'...")
        db_path = os.path.join(self.index_path_base, "library.db")
        if not os.path.exists(db_path):
            logging.warning("Cannot build index: library.db not found.")
            self._initialize_faiss_index()
            self.save_index()
            return

        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            self._initialize_faiss_index()
            pages = session.query(PDFPage).options(joinedload(PDFPage.document)).filter(PDFPage.gemini_analysis != None).all()
            if not pages:
                logging.warning("No processable pages found in the database.")
                self.save_index()
                return

            all_texts = [self._extract_section(p.gemini_analysis, "ENHANCED_TEXT") for p in pages]
            all_ids = np.array([p.id for p in pages], dtype=np.int64)

            for page in pages:
                self.page_map[page.id] = {
                    'document_id': page.document.id, 'page_number': page.page_number,
                    'document_name': page.document.original_filename, 
                    'doc_type': page.document.doc_type, 'start_time_seconds': page.start_time_seconds,
                    'content': self._extract_section(page.gemini_analysis, "ENHANCED_TEXT")
                }
            
            logging.info(f"Encoding {len(all_texts)} documents...")
            embeddings = self.model.encode(all_texts, convert_to_tensor=False, show_progress_bar=True)
            self.faiss_index.add_with_ids(embeddings.astype('float32'), all_ids)
            self.save_index()
            logging.info(f"Full index rebuild complete. Index contains {self.faiss_index.ntotal} vectors.")

        except Exception as e:
            logging.error(f"Error during full index rebuild: {e}", exc_info=True)
        finally:
            session.close()

    def add_document(self, doc_id):
        logging.info(f"Incrementally adding document {doc_id} to index.")
        db_path = os.path.join(self.index_path_base, "library.db")
        if not os.path.exists(db_path):
            logging.error(f"Cannot add document: library.db not found at {db_path}")
            return
            
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            if self.faiss_index is None: self._initialize_faiss_index()

            if not isinstance(self.faiss_index, faiss.IndexIDMap):
                logging.warning("Index was not an IndexIDMap. Re-wrapping.")
                base_index = self.faiss_index
                new_index = faiss.IndexIDMap(faiss.clone_index(base_index))
                new_index.add_with_ids(base_index.reconstruct_n(0, base_index.ntotal), np.arange(base_index.ntotal))
                self.faiss_index = new_index
            
            pages = session.query(PDFPage).options(joinedload(PDFPage.document)).filter(PDFPage.document_id == doc_id, PDFPage.gemini_analysis != None).all()
            if not pages: return

            texts_to_add = []
            ids_to_add = []
            for page in pages:
                enhanced_text = self._extract_section(page.gemini_analysis, "ENHANCED_TEXT")
                texts_to_add.append(enhanced_text)
                ids_to_add.append(page.id)
                self.page_map[page.id] = {
                    'document_id': page.document.id, 'page_number': page.page_number,
                    'document_name': page.document.original_filename, 
                    'doc_type': page.document.doc_type, 'start_time_seconds': page.start_time_seconds,
                    'content': enhanced_text
                }

            if texts_to_add:
                embeddings = self.model.encode(texts_to_add, convert_to_tensor=False)
                self.faiss_index.add_with_ids(embeddings.astype('float32'), np.array(ids_to_add, dtype=np.int64))
                self.save_index()
                logging.info(f"Added {len(ids_to_add)} pages for doc {doc_id}. Index has {self.faiss_index.ntotal} vectors.")
        except Exception as e:
            logging.error(f"Failed to add document {doc_id} to index: {e}", exc_info=True)
        finally:
            session.close()

    def remove_document(self, doc_id):
        if self.faiss_index is None or self.faiss_index.ntotal == 0: return
        logging.info(f"Incrementally removing document {doc_id} from index.")
        db_path = os.path.join(self.index_path_base, "library.db")
        if not os.path.exists(db_path): return
            
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            pages_to_remove = session.query(PDFPage.id).filter(PDFPage.document_id == doc_id).all()
            ids_to_remove = np.array([page.id for page in pages_to_remove], dtype=np.int64)
            if len(ids_to_remove) == 0: return

            removed_count = self.faiss_index.remove_ids(faiss.IDSelectorArray(ids_to_remove))
            for page_id in ids_to_remove: self.page_map.pop(int(page_id), None)
            self.save_index()
            logging.info(f"Removed {removed_count} vectors for doc {doc_id}. Index has {self.faiss_index.ntotal} vectors.")
        except Exception as e:
            logging.error(f"Failed to remove document {doc_id} from index: {e}", exc_info=True)
        finally:
            session.close()

    def search(self, query, top_k=10, content_type_filter='all'):
        if self.faiss_index is None or self.faiss_index.ntotal == 0:
            logging.warning("Search attempted but index is empty or not loaded.")
            return []
        try:
            # Increase initial search size to account for filtering
            search_k = top_k * 5 if content_type_filter != 'all' else top_k
            search_k = min(search_k, self.faiss_index.ntotal)

            query_vector = self.model.encode([query], convert_to_tensor=False).astype('float32')
            distances, page_ids = self.faiss_index.search(query_vector, search_k)
            
            results = []
            if page_ids.size == 0 or page_ids[0][0] == -1: return []

            for i, page_id in enumerate(page_ids[0]):
                if page_id == -1 or len(results) >= top_k: continue
                page_id = int(page_id)
                
                page_info = self.page_map.get(page_id)
                if not page_info: continue

                # Apply the content type filter
                if content_type_filter != 'all' and page_info.get('doc_type') != content_type_filter:
                    continue

                score = 1.0 / (1.0 + distances[0][i])
                results.append({'page_id': page_id, **page_info, 'score': score, 'snippet': self._create_snippet(page_info.get('content', ''), query)})
            return results
        except Exception as e:
            logging.error(f"Error performing search: {e}", exc_info=True)
            return []
            
    def _extract_section(self, text, section_name):
        try:
            start_tag = f"###{section_name}###"
            end_tag = "###"
            start_index = text.find(start_tag)
            if start_index == -1: return ""
            start_index += len(start_tag)
            next_section_start = text.find(end_tag, start_index)
            return text[start_index:next_section_start].strip() if next_section_start != -1 else text[start_index:].strip()
        except Exception: return ""

    def _create_snippet(self, text, query, length=250):
        if not text or not query: return (text or '')[:length]
        pos = text.lower().find(query.lower())
        start = max(0, pos - (length // 2)) if pos != -1 else 0
        snippet = text[start:start+length]
        return f"{'...' if start > 0 else ''}{snippet}{'...' if (start + length) < len(text) else ''}"

    def save_index(self):
        try:
            faiss.write_index(self.faiss_index, self.faiss_index_path)
            with open(self.page_map_path, 'wb') as f: pickle.dump(self.page_map, f)
            logging.info(f"Index with {self.faiss_index.ntotal} vectors saved to {self.index_path_base}")
        except Exception as e:
            logging.error(f"Error saving index: {e}", exc_info=True)
    def load_index(self):
        if os.path.exists(self.faiss_index_path) and os.path.exists(self.page_map_path):
            try:
                self.faiss_index = faiss.read_index(self.faiss_index_path)
                with open(self.page_map_path, 'rb') as f: self.page_map = pickle.load(f)
                logging.info(f"Index with {self.faiss_index.ntotal} vectors loaded from {self.index_path_base}.")
            except Exception as e:
                logging.error(f"Error loading index files: {e}. Re-initializing.")
                self._initialize_faiss_index()
        else:
            self._initialize_faiss_index()