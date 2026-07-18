import chromadb
from chromadb.utils import embedding_functions
import sys
import json

# Cấu hình stdout hiển thị tốt Tiếng Việt trên terminal Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class MockCollection:
    def __init__(self, name):
        self.name = name
    def query(self, query_texts, n_results=1):
        path = f"chroma_db_mock/{self.name}.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
            
        results = {
            "ids": [],
            "documents": [],
            "metadatas": [],
            "distances": []
        }
        
        for q in query_texts:
            q_words = set(q.lower().split())
            scored_docs = []
            for item in data:
                doc = item["document"]
                doc_words = set(doc.lower().split())
                intersection = q_words.intersection(doc_words)
                union = q_words.union(doc_words)
                score = len(intersection) / len(union) if union else 0.0
                scored_docs.append((score, item))
                
            scored_docs.sort(key=lambda x: x[0], reverse=True)
            top_docs = scored_docs[:n_results]
            
            results["ids"].append([x[1]["id"] for x in top_docs])
            results["documents"].append([x[1]["document"] for x in top_docs])
            results["metadatas"].append([x[1]["metadata"] for x in top_docs])
            results["distances"].append([1.0 - x[0] for x in top_docs])
            
        return results

class MockClient:
    def get_collection(self, name, embedding_function=None):
        return MockCollection(name)

# 1. Kiểm tra tương thích hệ thống với ChromaDB
use_mock = False
test_code = """
import chromadb
client = chromadb.EphemeralClient()
col = client.get_or_create_collection("test")
col.add(ids=["1"], documents=["test"])
"""
try:
    import subprocess
    res = subprocess.run([sys.executable, "-c", test_code], capture_output=True, timeout=3)
    if res.returncode != 0:
        use_mock = True
except Exception:
    use_mock = True

if use_mock:
    print("Cảnh báo: Đang chạy ở chế độ Mock Vector DB (do lỗi tương thích ChromaDB/onnxruntime trên máy của bạn).")
    chroma_client = MockClient()
    default_ef = None
else:
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    default_ef = embedding_functions.DefaultEmbeddingFunction()

catalog_collection = chroma_client.get_collection(name="catalog", embedding_function=default_ef)

# Thử tìm kiếm một câu bằng ngôn ngữ tự nhiên của khách
results = catalog_collection.query(
    query_texts=["Tôi muốn mua điện thoại iphone chụp hình đẹp"],
    n_results=1
)

print("Kết quả tìm kiếm thử nghiệm trong DB:")
print(results["documents"])