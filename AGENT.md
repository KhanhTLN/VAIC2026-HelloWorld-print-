# AGENT.md

# AI Shopping Assistant Backend

## Project Overview

Đây là backend của một hệ thống AI Shopping Assistant dành cho Hackathon Điện Máy Xanh.

Hệ thống **không phải chatbot thông thường**.

LLM **không truy cập trực tiếp database**.

LLM chỉ làm hai nhiệm vụ:

1. Hiểu ý định người dùng (Need Extraction)
2. Sinh câu trả lời cuối cùng (Response Generation)

Toàn bộ business logic, truy vấn database, ranking và trade-off đều được xử lý ở backend.

---

# Tech Stack

Backend

- Python 3.12
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL
- Alembic

Database

- PostgreSQL
- JSONB
- pgvector (Sprint 5)

AI

- Ollama Qwen2-7B
- Embedding Model
- RAG

---

# Architecture

```
User
    │
    ▼
AI Controller
    │
    ▼
Need Extraction (LLM)
    │
    ▼
Search Service
    │
    ▼
Ranking Engine
    │
    ▼
Trade-off Engine
    │
    ▼
Response Generator (LLM)
    │
    ▼
User
```

LLM KHÔNG được phép:

- query PostgreSQL
- tạo SQL
- truy cập database

LLM chỉ trả về JSON.

---

# Project Structure

```
app/

    core/

    models/

    schemas/

    repositories/

    services/

    routers/

    importer/

    utils/

main.py
```

---

# Database Design

1. Install ORM
Add the ORM to your project.
Code:
File: Code
```
npm install prisma --save-dev
```

File: Code
```
npx prisma init
```

2. Configure ORM
Set up your ORM configuration.
Code:
File: .env.local
```
# Connect to Postgres via the shared transaction-mode pooler (IPv4-only)
DATABASE_URL="postgresql://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true"

# Connect to Postgres via the shared session-mode pooler (used for migrations)
DIRECT_URL="postgresql://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
```

File: prisma/schema.prisma
```
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider  = "postgresql"
  url       = env("postgresql://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true")
  directUrl = env("postgresql://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")
}
```

3. Install Agent Skills (Optional)
Agent Skills give AI coding tools ready-made instructions, scripts, and resources for working with Supabase more accurately and efficiently.
Details:
npx skills add supabase/agent-skills
Code:
File: Code
```
npx skills add supabase/agent-skills
```

## Metadata

Mỗi Product gồm các field chung:

- id
- name
- sku
- model_code
- product_id_web
- category_id
- brand_id
- description
- original_price
- sale_price
- thumbnail
- rating
- review_count
- stock

---

## Specifications

Các thông số riêng của từng ngành hàng được lưu trong JSONB.

Ví dụ Laptop

```json
{
    "cpu":"Apple M4",
    "ram":16,
    "ssd":512,
    "gpu":"Integrated",
    "weight":1.24
}
```

Ví dụ Refrigerator

```json
{
    "usable_capacity":620,
    "cooling_technology":"Twin Cooling",
    "energy_saving":"Digital Inverter"
}
```

Không tạo riêng 200 cột cho Product.

Không tạo Entity riêng cho LaptopSpec hoặc PhoneSpec.

Mọi thông số đều lưu trong JSONB.

---

# JSON Naming Convention

Database KHÔNG sử dụng tiếng Việt.

CSV

```
Dung lượng sử dụng
```

↓

Database

```
usable_capacity
```

CSV

```
Khối lượng máy
```

↓

Database

```
weight
```

CSV

```
Công nghệ làm lạnh
```

↓

Database

```
cooling_technology
```

Frontend sẽ map sang tiếng Việt khi hiển thị.

---

# CSV Import

Pipeline

```
CSV

↓

Read CSV

↓

Field Mapping

↓

Metadata

+

Specifications(JSONB)

↓

Validation

↓

Insert Product

↓

Generate Embedding (Future)
```

Không import CSV trực tiếp.

---

# Search Flow

Ví dụ user hỏi

"Tôi cần laptop dưới 25 triệu RAM 16GB"

LLM trả

```json
{
    "category":"Laptop",
    "filters":{
        "ram":16,
        "max_price":25000000
    }
}
```

Backend nhận JSON.

Backend build query.

Không để AI sinh SQL.

---

# Search Service

SearchService nhận

```
SearchRequest
```

bao gồm

```
category

brand

price

filters
```

Backend thực hiện

```
PostgreSQL

↓

Candidate Products
```

---

# Ranking Engine

Sau khi SearchService trả về Candidate Products

Ranking Engine tính điểm.

Ví dụ

```
Budget

Programming

Battery

Weight
```

Mỗi tiêu chí có trọng số.

Output

```
Top 3 Products
```

Không sử dụng LLM để ranking.

---

# Trade-off Engine

Input

Top 3 Products

Output

```json
{
    "strength":[...],
    "weakness":[...]
}
```

Trade-off được tính bằng backend.

Không dùng GPT để so sánh.

---

# Response Generator

Sau khi có

- User Need
- Top Products
- Trade-off

LLM sinh câu trả lời tiếng Việt tự nhiên.

Ví dụ

```
MacBook Air M4 phù hợp nhất vì...

Nếu ưu tiên pin...

Nếu ưu tiên gaming...
```

---

# Embedding

Embedding KHÔNG lưu trong Product.

Tạo bảng riêng

```
product_embeddings

product_id

embedding

indexed_text
```

indexed_text được tạo từ

```
Tên sản phẩm

+

Description

+

Thông số nổi bật
```

Ví dụ

```
MacBook Air M4

Laptop siêu nhẹ

16GB RAM

512GB SSD

Pin 18 giờ

Apple M4
```

↓

Embedding

---

# Coding Rules

## Không hardcode Category

Sai

```python
if category == "Laptop":
```

Đúng

Đọc từ database.

---

## Không hardcode Brand

Sai

```python
Samsung
Apple
LG
```

Đúng

Đọc từ bảng Brand.

---

## Không hardcode Specifications

Sai

```python
product.cpu
```

Đúng

```python
product.specifications["cpu"]
```

---

## Business Logic

Business logic chỉ nằm trong

```
services/
```

Repository chỉ CRUD.

Router chỉ nhận request.

Không viết business logic trong Router.

---

# Sprint Roadmap

## Sprint 1

- Database Connection
- Product CRUD
- Brand CRUD
- Category CRUD
- JSONB

## Sprint 2

- CSV Import
- Validation
- Mapping

## Sprint 3

- Dynamic Search
- PostgreSQL JSONB Query

## Sprint 4

- Ranking Engine
- Trade-off Engine

## Sprint 5

- Embedding
- Vector Search
- Hybrid Search

## Sprint 6

- Ollama Qwen2-7B
- Need Extraction
- Response Generation

---

# Goal

Agent phải luôn tuân thủ nguyên tắc sau:

- Ưu tiên business logic ở backend.
- LLM chỉ hiểu ngôn ngữ tự nhiên và tạo phản hồi.
- PostgreSQL là nguồn dữ liệu duy nhất (single source of truth).
- JSONB lưu toàn bộ thông số kỹ thuật.
- Không hardcode category, brand hoặc field.
- Mọi truy vấn phải thông qua Service và Repository.
- Thiết kế theo hướng dễ mở rộng để thêm ngành hàng mới mà không cần sửa schema database.


---

# Additional Technical Constraints (Bổ sung cho Agent)

## 1. Quy tắc Code Python & FastAPI
- **Async/Await:** Toàn bộ Router, Service, và Repository thao tác với DB BẮT BUỘC sử dụng `async/await` với SQLAlchemy AsyncSession.
- **Strict Typing:** Sử dụng Pydantic v2 để validate toàn bộ dữ liệu đầu vào/đầu ra tại Router. Mọi hàm trong Service/Repository phải có Type Hinting rõ ràng.
- **Diệt trừ Hardcode JSONB Key:** Khi build query động trên PostgreSQL JSONB, Agent phải dựa vào một bộ `Specification Dictionary` (đọc từ cấu trúc Metadata/Category) để đối chiếu, không tự ý hardcode chuỗi ký tự key.

## 2. Thiết kế API Error Handling
- Mọi API phải trả về cấu trúc lỗi đồng nhất qua `HTTPException` của FastAPI: `{"detail": "Lời nhắn lỗi chi tiết"}`.
- Trong trường hợp Search Service trả về 0 kết quả: Không được để hệ thống crash, phải trả về mảng rỗng kèm theo gợi ý sản phẩm bán chạy nhất (best-seller) của Category đó.

## 3. Định dạng chuẩn cho Need Extraction (Sprint 6)
LLM Need Extraction bắt buộc phải tuân thủ schema dạng cấu trúc điều kiện (nếu có):
- `field`: Tên cột trong Metadata hoặc key trong JSONB.
- `operator`: Chỉ gồm các giá trị `eq` (=), `gt` (>), `gte` (>=), `lt` (<), `lte` (<=), `like`.