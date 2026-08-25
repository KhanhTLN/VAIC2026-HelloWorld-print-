# Fix Product Category Mixing, State Reset, and Out-of-Stock Apologies

This plan addresses three main issues identified during testing of the AI advisor:
1. **Natural Out-of-Stock/Non-Existent Product Apologies**: When a user queries a specific product model that is out of stock or does not exist, the AI should apologize and explain the situation clearly before suggesting alternatives.
2. **State Management on Category Switch**: When switching categories, previous query parameters (e.g., brand, budget, room size) must be completely reset so they do not contaminate the new category.
3. **Product Category Mixing (Loạn sản phẩm)**: Recommending wrong categories (e.g., air conditioners instead of refrigerators) due to category/brand leakage from parsing assistant messages.

## User Review Required

> [!IMPORTANT]
> - We will **disable parsing assistant messages for intent accumulation**. The assistant's own messages (e.g. giving examples like "Daikin, Panasonic, LG") were incorrectly modifying the category and brand states. Intent tracking will now rely solely on user messages.
> - We will implement **explicit Python-level out-of-stock checking**. When a user requests a specific model but it is not retrieved from the database, we pass an explicit instruction to the LLM to apologize and explain the stock status before suggesting alternatives.

## Proposed Changes

### AI Advisor Logic

#### [MODIFY] [agent_logic.py](file:///d:/dienmayxanh-ai-advisor/src/agents/agent_logic.py)

- **Initialize Tracking Variables Globally**: At the start of `generate_advisor_response_stream`, initialize variables like `is_specific_model`, `model_keywords`, `is_out_of_stock`, and `requested_model`.
- **Remove Assistant Intent Parsing**: Remove the `elif role == "assistant"` block in the history parsing loop to prevent assistant suggestions from contaminating the conversation state.
- **Improve Category Switch Reset**: In the `role == "user"` history parsing, when the category changes, copy the new query's parameters (`prev_intent.get(...)`) instead of setting them to `None`. This correctly discards the old category's parameters while retaining any new ones.
- **Add Python-Level Out-of-Stock Verification**:
  - Extract the specific model terms from the user query if a specific model is detected.
  - Check if any retrieved products match those terms.
  - If no products match, set `is_out_of_stock = True` and capture the `requested_model` name.
- **Instruct LLM to Apologize**: If `is_out_of_stock` is `True`, append a clear instruction to `upsell_instruction` telling the LLM to start its response with a polite apology and explanation about the stock status before introducing the list of similar products.

## Verification Plan

### Automated Tests
- Run `python test_agent_logic.py` and inspect the output stream for all test cases.
- Verify Test 6 (`tư vấn giúp tôi iphone 15 pro max`) outputs a polite apology before recommending the in-stock `iPhone 15 Plus`.

### Manual Verification
- Start the backend server (`python server.py`) and Streamlit app (`streamlit run app.py`).
- **Test Case 1 (Out of stock)**: Query `"tư vấn iPhone 15 Pro Max"` and verify it apologizes for the out-of-stock status before recommending the `iPhone 15 Plus`.
- **Test Case 2 (Category Switch)**: 
  - Query `"tư vấn điện thoại giá 20 triệu"`.
  - Query `"tôi muốn tư vấn về tủ lạnh"`. Verify it asks for refrigerator parameters and does not carry over the 20 million budget or mention phones.
- **Test Case 3 (No product mixing)**: 
  - Query `"tôi muốn tư vấn về tủ lạnh"`.
  - Query `"giá tầm khoảng 20 triệu"`. Verify it recommends actual refrigerators under 20 million, and does not recommend LG air conditioners.
