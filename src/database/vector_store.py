try:
    import chromadb
    from chromadb.utils import embedding_functions
except Exception:
    chromadb = None
    embedding_functions = None
import json
import sys
import os

# Thêm thư mục gốc dự án vào sys.path để tránh lỗi import "No module named 'src'"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Cấu hình stdout hiển thị tốt Tiếng Việt trên terminal Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class MockCollection:
    def __init__(self, name):
        self.name = name
    def count(self):
        path = f"chroma_db_mock/{self.name}.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data)
        except Exception:
            return 0
            
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

    def query(self, query_texts, n_results=1, where=None):
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
        
        # Áp dụng bộ lọc where (ChromaDB metadata query syntax)
        filtered_data = []
        if where:
            def eval_filter(meta, expr):
                for k, v in expr.items():
                    if k == "$and":
                        return all(eval_filter(meta, sub) for sub in v)
                    if k == "$or":
                        return any(eval_filter(meta, sub) for sub in v)
                    
                    if k not in meta:
                        return False
                    val = meta[k]
                    if isinstance(v, dict):
                        for op, op_val in v.items():
                            if op == "$lte" and not (val <= op_val): return False
                            if op == "$lt" and not (val < op_val): return False
                            if op == "$gte" and not (val >= op_val): return False
                            if op == "$gt" and not (val > op_val): return False
                            if op == "$eq" and not (val == op_val): return False
                            if op == "$ne" and not (val != op_val): return False
                    else:
                        if val != v:
                            return False
                return True
                
            for item in data:
                if eval_filter(item.get("metadata", {}), where):
                    filtered_data.append(item)
        else:
            filtered_data = data
            
        for q in query_texts:
            q_words = set(q.lower().split())
            scored_docs = []
            for item in filtered_data:
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
    
    _use_mock = False
    if chromadb is None or embedding_functions is None:
        _use_mock = True
    else:
        import subprocess
        test_code = """
import chromadb
client = chromadb.EphemeralClient()
col = client.get_or_create_collection("test")
col.add(ids=["1"], documents=["test"])
"""
        try:
            res = subprocess.run([sys.executable, "-c", test_code], capture_output=True, timeout=30)
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
                p.spec_product,
                p.url_image,
                p.url
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
            
            # Chuẩn hóa thương hiệu sang dạng chuẩn hoa để khớp bộ lọc
            raw_brand = (row[2] or '').strip().lower()
            norm_brand = "KHÁC"
            brand_map = {
                "iphone": "APPLE", "apple": "APPLE", "samsung": "SAMSUNG", "oppo": "OPPO", 
                "xiaomi": "XIAOMI", "redmi": "XIAOMI", "realme": "REALME", "vivo": "VIVO", 
                "lg": "LG", "sharp": "SHARP", "hitachi": "HITACHI", "panasonic": "PANASONIC", 
                "toshiba": "TOSHIBA", "daikin": "DAIKIN", "casper": "CASPER", "asus": "ASUS", 
                "hp": "HP", "acer": "ACER", "lenovo": "LENOVO", "dell": "DELL", "msi": "MSI", 
                "sony": "SONY", "jbl": "JBL", "marshall": "MARSHALL"
            }
            for kw, b in brand_map.items():
                if kw in raw_brand:
                    norm_brand = b
                    break

            products.append({
                "id": str(row[0]),
                "name": str(row[1]),
                "brand": norm_brand,
                "category_name": str(row[3]) if row[3] else "Khác",
                "category": normalized_cat,
                "price": price,
                "original_price": float(row[5]) if row[5] is not None else 0.0,
                "promotion": str(row[6]) if row[6] is not None else "",
                "outstanding": str(row[7]) if row[7] is not None else "",
                "spec_product": json.dumps(row[8], ensure_ascii=False) if row[8] is not None else "",
                "url_image": str(row[9]) if row[9] is not None else "",
                "url": str(row[10]) if row[10] is not None else "",
                "full_text": full_text
            })
            
        cursor.close()
        conn.close()
        
        if products:
            ids = [p['id'] for p in products]
            documents = [p['full_text'] for p in products]
            metadatas = [{
                "brand": p['brand'], 
                "category": p['category'], 
                "price": p['price'],
                "product_id": p['id'],
                "name": p['name'],
                "category_name": p['category_name'],
                "original_price": p['original_price'],
                "promotion": p['promotion'],
                "outstanding": p['outstanding'],
                "spec_product": p['spec_product'],
                "url_image": p['url_image'],
                "url": p['url']
            } for p in products]
            
            # Chia nhỏ dữ liệu thành các batch (ví dụ: mỗi batch tối đa 2000 sản phẩm) để tránh giới hạn của ChromaDB
            batch_size = 2000
            for i in range(0, len(products), batch_size):
                batch_ids = ids[i:i + batch_size]
                batch_docs = documents[i:i + batch_size]
                batch_metas = metadatas[i:i + batch_size]
                catalog_collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
                
            print("Đã nạp dữ liệu Catalog vào Vector DB thành công!")
        else:
            print("Không tìm thấy sản phẩm nào trong DB để nạp.")
    except Exception as e:
        print(f"Không thể nạp dữ liệu Catalog vào Vector DB: {e}")

    # --- ĐƯA DỮ LIỆU POLICY & FAQ VÀO DB ---
    try:
        with open('data/raw/policy.txt', 'r', encoding='utf-8') as f:
            policy_text = f.read()
            
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_text(policy_text)
        
        policy_ids = [f"policy_{i}" for i in range(len(chunks))]
        # Chia nhỏ dữ liệu chính sách thành các batch
        batch_size = 2000
        for i in range(0, len(chunks), batch_size):
            batch_ids = policy_ids[i:i + batch_size]
            batch_docs = chunks[i:i + batch_size]
            policy_collection.add(ids=batch_ids, documents=batch_docs)
            
        print(f"Đã nạp {len(chunks)} đoạn chính sách vào Vector DB!")
    except FileNotFoundError:
        print("Chưa có file policy.txt, bỏ qua nạp chính sách (hãy bổ sung sau).")

def query_products(query_text, category=None, brand=None, budget=None, n_results=3):
    """Truy vấn sản phẩm bằng Vector DB kết hợp lọc Metadata (Hybrid RAG)"""
    try:
        client, ef = get_vector_client()
        
        # Tự động khởi tạo dữ liệu nếu Collection trống trơn
        try:
            collection = client.get_collection(name="catalog", embedding_function=ef)
            if collection.count() == 0:
                print("Vector DB trống, đang tự động nạp dữ liệu...")
                init_vector_db()
                collection = client.get_collection(name="catalog", embedding_function=ef)
        except Exception:
            print("Chưa tạo Collection catalog, đang tự động khởi tạo...")
            init_vector_db()
            collection = client.get_collection(name="catalog", embedding_function=ef)

        # Chuẩn bị bộ lọc where cho ChromaDB
        where_clauses = []
        if category:
            where_clauses.append({"category": category})
        if brand:
            where_clauses.append({"brand": brand.strip().upper()})
        if budget:
            where_clauses.append({"price": {"$lte": budget}})
            
        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}
            
        # Nếu query_text rỗng, dùng tên ngành hàng làm query mặc định
        search_query = query_text.strip() if query_text else ""
        if not search_query:
            if category == 'dien-thoai': search_query = "điện thoại smartphone"
            elif category == 'laptop': search_query = "máy tính laptop xách tay"
            elif category == 'may-lanh': search_query = "máy lạnh điều hòa nhiệt độ"
            elif category == 'tu-lanh': search_query = "tủ lạnh bảo quản thực phẩm"
            elif category == 'tai-nghe': search_query = "tai nghe bluetooth"
            else: search_query = "sản phẩm"
            
        is_upsell = False
        results = collection.query(query_texts=[search_query], n_results=n_results, where=where)
        
        # Fallback TIER 1.5: Nếu lọc thương hiệu mà trống -> Thử truy vấn bỏ lọc thương hiệu để tránh lệch ký tự hoa thường
        if brand and (not results or not results.get("metadatas") or len(results["metadatas"][0]) == 0):
            where_clauses_no_brand = [c for c in where_clauses if "brand" not in c]
            where_no_brand = None
            if len(where_clauses_no_brand) == 1:
                where_no_brand = where_clauses_no_brand[0]
            elif len(where_clauses_no_brand) > 1:
                where_no_brand = {"$and": where_clauses_no_brand}
            results = collection.query(query_texts=[search_query], n_results=n_results, where=where_no_brand)
            
        # Fallback TIER 2: Nếu lọc theo ngân sách mà trống -> Truy vấn cận biên (Upsell) bằng cách bỏ lọc giá
        if budget and (not results or not results.get("metadatas") or len(results["metadatas"][0]) == 0):
            is_upsell = True
            # Giữ lại bộ lọc category để không bị nhảy sang ngành hàng khác
            where_fallback = {"category": category} if category else None
            results = collection.query(query_texts=[search_query], n_results=2, where=where_fallback)
            
        products = []
        if results and results.get("metadatas") and len(results["metadatas"]) > 0:
            for meta in results["metadatas"][0]:
                spec_str = meta.get("spec_product", "")
                spec_data = None
                if spec_str:
                    try:
                        spec_data = json.loads(spec_str)
                    except Exception:
                        spec_data = spec_str
                
                products.append({
                    "product_id": meta.get("product_id"),
                    "name": meta.get("name"),
                    "brand": meta.get("brand"),
                    "category_name": meta.get("category_name"),
                    "sale_price": meta.get("price"),
                    "original_price": meta.get("original_price"),
                    "promotion": meta.get("promotion"),
                    "outstanding": meta.get("outstanding"),
                    "spec_product": spec_data,
                    "url_image": meta.get("url_image", ""),
                    "url": meta.get("url", "")
                })
        return products, is_upsell
    except Exception as e:
        print(f"Lỗi truy vấn sản phẩm bằng Vector DB: {e}")
    return [], False

if __name__ == "__main__":
    init_vector_db()