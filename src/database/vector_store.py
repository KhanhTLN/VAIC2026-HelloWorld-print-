import chromadb
from chromadb.utils import embedding_functions
import sys

# Cấu hình stdout hiển thị tốt Tiếng Việt trên terminal Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

_client = None
_default_ef = None

def get_vector_client():
    global _client, _default_ef
    if _client is not None:
        return _client, _default_ef

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
