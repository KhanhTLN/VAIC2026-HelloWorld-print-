import chromadb
from chromadb.utils import embedding_functions
import json
import sys

# Cấu hình stdout hiển thị tốt Tiếng Việt trên terminal Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class MockCollection:
    def __init__(self, name):
        self.name = name
    def add(self, ids, documents, metadatas=None):
        import os
        os.makedirs("chroma_db_mock", exist_ok=True)
        path = f"chroma_db_mock/{self.name}.json"
        data = []
        for i in range(len(ids)):
            data.append({
                "id": ids[i],
                "document": documents[i],
                "metadata": metadatas[i] if metadatas else {}
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

class MockClient:
    def get_or_create_collection(self, name, embedding_function=None):
        return MockCollection(name)

def init_vector_db():
    import subprocess
    
    # 1. Kiểm tra xem hệ thống có thể chạy ChromaDB thực tế mà không bị crash/lỗi không
    use_mock = False
    test_code = """
import chromadb
client = chromadb.EphemeralClient()
col = client.get_or_create_collection("test")
col.add(ids=["1"], documents=["test"])
"""
    try:
        res = subprocess.run([sys.executable, "-c", test_code], capture_output=True, timeout=3)
        if res.returncode != 0:
            use_mock = True
    except Exception:
        use_mock = True

    if use_mock:
        print("Cảnh báo: Phát hiện lỗi tương thích hệ thống với ChromaDB (lỗi onnxruntime hoặc CPU không hỗ trợ AVX2).")
        print("-> Hệ thống sẽ tự động sử dụng Mock Vector DB để tránh crash và hoàn thành nạp dữ liệu.")
        chroma_client = MockClient()
        default_ef = None
    else:
        # Khởi tạo ChromaDB client thực tế
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        default_ef = embedding_functions.DefaultEmbeddingFunction()

    # 3. Tạo 2 Collection riêng biệt cho Sản phẩm và Chính sách
    catalog_collection = chroma_client.get_or_create_collection(name="catalog", embedding_function=default_ef)
    policy_collection = chroma_client.get_or_create_collection(name="policy", embedding_function=default_ef)
    
    # --- ĐƯA DỮ LIỆU CATALOG VÀO DB ---
    with open('data/processed/cleaned_catalog.json', 'r', encoding='utf-8') as f:
        products = json.load(f)
        
    ids = [p['id'] for p in products]
    documents = [p['full_text'] for p in products]
    # Metadata cực kỳ quan trọng để sau này LỌC CỨNG (Hard Filter) trước khi tìm kiếm
    metadatas = [{"brand": p['brand'], "category": p['category'], "price": p['price']} for p in products]
    
    catalog_collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print("Đã nạp dữ liệu Catalog vào Vector DB thành công!")

    # --- ĐƯA DỮ LIỆU POLICY & FAQ VÀO DB ---
    # Giả sử bạn có file policy.txt chứa chính sách đổi trả, bảo hành, trả góp...
    try:
        with open('data/raw/policy.txt', 'r', encoding='utf-8') as f:
            policy_text = f.read()
            
        # Chia nhỏ văn bản chính sách thành các đoạn nhỏ (Chunking) để AI không bị quá tải context
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_text(policy_text)
        
        policy_ids = [f"policy_{i}" for i in range(len(chunks))]
        policy_collection.add(ids=policy_ids, documents=chunks)
        print(f"Đã nạp {len(chunks)} đoạn chính sách vào Vector DB!")
    except FileNotFoundError:
        print("Chưa có file policy.txt, bỏ qua nạp chính sách (hãy bổ sung sau).")

if __name__ == "__main__":
    init_vector_db()