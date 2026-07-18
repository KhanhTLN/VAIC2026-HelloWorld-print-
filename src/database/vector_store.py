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
    def get_or_create_collection(self, name, embedding_function=None):
        return MockCollection(name)
    def get_collection(self, name, embedding_function=None):
        return MockCollection(name)

_client = None
_default_ef = None
_use_mock = None

def get_vector_client():
    global _client, _default_ef, _use_mock
    if _client is not None:
        return _client, _default_ef
    
    import subprocess
    _use_mock = False
    test_code = """
import chromadb
client = chromadb.EphemeralClient()
col = client.get_or_create_collection("test")
col.add(ids=["1"], documents=["test"])
"""
    try:
        res = subprocess.run([sys.executable, "-c", test_code], capture_output=True, timeout=3)
        if res.returncode != 0:
            _use_mock = True
    except Exception:
        _use_mock = True

    if _use_mock:
        print("Cảnh báo: Phát hiện lỗi tương thích hệ thống với ChromaDB (lỗi onnxruntime hoặc CPU không hỗ trợ AVX2).")
        print("-> Hệ thống sẽ tự động sử dụng Mock Vector DB để tránh crash.")
        _client = MockClient()
        _default_ef = None
    else:
        _client = chromadb.PersistentClient(path="./chroma_db")
        _default_ef = embedding_functions.DefaultEmbeddingFunction()
        
    return _client, _default_ef

def query_policy(query_text, n_results=3):
    try:
        client, ef = get_vector_client()
        collection = client.get_collection(name="policy", embedding_function=ef)
        results = collection.query(query_texts=[query_text], n_results=n_results)
        if results and results.get("documents") and len(results["documents"]) > 0:
            return results["documents"][0]
    except Exception as e:
        print(f"Lỗi truy vấn policy: {e}")
    return []

def init_vector_db():
    chroma_client, default_ef = get_vector_client()

    # 3. Tạo 2 Collection riêng biệt cho Sản phẩm và Chính sách
    catalog_collection = chroma_client.get_or_create_collection(name="catalog", embedding_function=default_ef)
    policy_collection = chroma_client.get_or_create_collection(name="policy", embedding_function=default_ef)
    
    # --- ĐƯA DỮ LIỆU CATALOG VÀO DB ---
    try:
        from src.database.sync_supabase import get_db_connection, safe_int, format_price, normalize_category
        print("Connecting to Supabase to fetch catalog data...")
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT 
                p.product_id, 
                p.name, 
                p.brand, 
                c.category_name, 
                p.sale_price, 
                p.original_price,
                p.promotion, 
                p.outstanding,
                p.spec_product
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        products = []
        for row in rows:
            price = safe_int(row[4])
            specs_data = row[8]
            specs_str = ""
            if specs_data:
                if isinstance(specs_data, dict):
                    specs_str = " - ".join([f"{k}: {v}" for k, v in specs_data.items()])
                elif isinstance(specs_data, list):
                    specs_str = " - ".join([str(item) for item in specs_data])
                else:
                    specs_str = str(specs_data)
            
            formatted_price_str = format_price(price)
            description = row[7] or ""
            normalized_cat = normalize_category(row[3])
            
            full_text = (
                f"Sản phẩm: {row[1]}. "
                f"Thương hiệu: {row[2] or 'Khác'}. "
                f"Ngành hàng: {row[3] or 'Khác'}. "
                f"Giá: {formatted_price_str}. "
                f"Thông số: {specs_str}. "
                f"Mô tả: {description}"
            )
            
            products.append({
                "id": str(row[0]),
                "brand": (row[2] or '').strip().upper(),
                "category": normalized_cat,
                "price": price,
                "full_text": full_text
            })
            
        cursor.close()
        conn.close()
        
        if products:
            ids = [p['id'] for p in products]
            documents = [p['full_text'] for p in products]
            metadatas = [{"brand": p['brand'], "category": p['category'], "price": p['price']} for p in products]
            
            catalog_collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print("Đã nạp dữ liệu Catalog vào Vector DB thành công!")
        else:
            print("Không tìm thấy sản phẩm nào trong DB để nạp.")
    except Exception as e:
        print(f"Không thể nạp dữ liệu Catalog vào Vector DB: {e}")

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