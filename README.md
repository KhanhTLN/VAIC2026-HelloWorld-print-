# Trợ lý AI Điện Máy Xanh - Vietnam Innovation Challenge 2026

## 1) Cài đặt môi trường
```bash
pip install -r requirements.txt
```

## 2) Khởi chạy ứng dụng Streamlit
```bash
streamlit run app.py
```

## 3) Workflow backend mới
Luồng xử lý đã tách theo kiến trúc:
- `src/schemas`: contract dữ liệu pipeline (`NeedExtraction`, `SearchFilters`, `RankingInput`, `TradeoffOutput`, `ResponsePayload`)
- `src/repositories`: chỉ truy cập PostgreSQL (`ProductRepository`)
- `src/services`: validation, search, ranking, trade-off, orchestration
- `src/routers`: API boundary cho workflow (`workflow_router`)
- `src/agents/agent_logic.py`: orchestrator mỏng cho giao diện chat

Pipeline:
1. LLM Need Extraction (JSON-only)
2. Backend validation
3. PostgreSQL + JSONB filtering
4. Deterministic ranking
5. Deterministic trade-off
6. LLM response generation từ payload backend

## 4) Chạy unit tests
```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```
