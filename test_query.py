import sys

from src.database.vector_store import get_vector_client

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

chroma_client, default_ef = get_vector_client()
catalog_collection = chroma_client.get_collection(name="catalog", embedding_function=default_ef)

results = catalog_collection.query(
    query_texts=["Tôi muốn mua điện thoại iphone chụp hình đẹp"],
    n_results=1,
)

print("Kết quả tìm kiếm thử nghiệm trong ChromaDB:")
print(results["documents"])
