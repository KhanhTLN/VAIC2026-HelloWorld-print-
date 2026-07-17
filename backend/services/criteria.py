from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from utils.spec_dictionary import SpecDictionary, normalize_text


# Metadata slots that are always askable (not JSONB keys).
META_BRAND = "brand"
META_MAX_PRICE = "max_price"

# Preferred question order: match against normalized spec key substrings.
_SPEC_PRIORITY_PATTERNS: tuple[tuple[str, int], ...] = (
    ("dung tích", 100),
    ("dung luong", 95),
    ("khối lượng", 90),
    ("công suất", 85),
    ("số cửa", 80),
    ("cánh", 78),
    ("loại sản phẩm", 70),
    ("công nghệ", 60),
    ("inverter", 55),
)


def prioritize_ask_fields(spec_keys: list[str]) -> list[str]:
    """
    Order fields to ask: brand + price + high-value spec keys from this category.
    """
    scored: list[tuple[int, str]] = []
    for key in spec_keys:
        norm = normalize_text(key)
        score = 20
        for pattern, weight in _SPEC_PRIORITY_PATTERNS:
            if pattern in norm:
                score = max(score, weight)
                break
        scored.append((score, key))

    scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    ordered_specs = [key for _, key in scored]

    # Ask brand & budget interleaved with top specs.
    result: list[str] = []
    if ordered_specs:
        result.append(ordered_specs[0])
    result.append(META_BRAND)
    result.extend(ordered_specs[1:4])
    result.append(META_MAX_PRICE)
    # Deduplicate preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for field in result:
        if field not in seen:
            seen.add(field)
            unique.append(field)
    return unique


def question_for_field(field: str) -> str:
    if field == META_BRAND:
        return "Bạn muốn mua của hãng nào ạ? (ví dụ: Panasonic, Samsung, LG…)"
    if field == META_MAX_PRICE:
        return "Bạn dự kiến tầm giá khoảng bao nhiêu?"

    norm = normalize_text(field)
    if "dung tích" in norm or "dung luong" in norm:
        return f"Bạn cần {field} khoảng bao nhiêu (ví dụ: 400 lít)?"
    if "cửa" in norm or "cánh" in norm:
        return f"Bạn muốn thế nào về “{field}”? (ví dụ: 1 cửa, 2 cửa, hai cánh…)"
    if "công suất" in norm:
        return f"Bạn cần {field} khoảng bao nhiêu?"
    return f"Bạn có yêu cầu gì về “{field}” không ạ?"


def extract_price(message: str) -> Decimal | None:
    text = message.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(triệu|tr|m)\b", text)
    if m:
        return Decimal(str(float(m.group(1)) * 1_000_000))
    m = re.search(r"(\d{6,})", text.replace(".", ""))
    if m:
        return Decimal(m.group(1))
    return None


def extract_capacity_liters(message: str) -> str | None:
    text = message.lower()
    m = re.search(r"(\d+)\s*(lít|lit|l)\b", text)
    if m:
        return m.group(1)
    # "tủ lạnh 400l" / "400L"
    m = re.search(r"(\d+)\s*l\b", text)
    if m:
        return m.group(1)
    return None


def pick_capacity_key(spec_keys: list[str]) -> str | None:
    matches = [
        key
        for key in spec_keys
        if "dung tích" in normalize_text(key) or "dung luong" in normalize_text(key)
    ]
    if not matches:
        return None
    matches.sort(key=len)
    # Prefer "Dung tích tổng" / general capacity over soft-freeze niche.
    for key in matches:
        if "tổng" in normalize_text(key) or normalize_text(key) in {"dung tích", "dung luong"}:
            return key
    return matches[0]


def extract_door_value(message: str) -> str | None:
    text = message.lower()
    if any(k in text for k in ("hai cánh", "2 cánh", "hai cửa", "2 cửa", "side by side")):
        return "2"
    if any(k in text for k in ("một cánh", "1 cánh", "một cửa", "1 cửa")):
        return "1"
    if any(k in text for k in ("ba cánh", "3 cánh", "3 cửa", "multi")):
        return "3"
    return None


def pick_door_key(spec_keys: list[str]) -> str | None:
    for key in spec_keys:
        norm = normalize_text(key)
        if "số cửa" in norm or norm == "cửa" or "cánh" in norm:
            return key
    return None


async def extract_criteria_from_message(
    message: str,
    *,
    spec_keys: list[str],
    brand_names: list[str],
    pending_field: str | None,
    spec_dictionary: SpecDictionary,
) -> dict[str, Any]:
    """
    Pull any criteria the user volunteered in free text.
    Also maps answer onto pending_field when they reply to a question.
    """
    found: dict[str, Any] = {}
    text = message.strip()
    text_lower = text.lower()
    allowed = set(spec_keys)

    # Brand (longest name first to avoid short false positives).
    for brand in sorted(brand_names, key=len, reverse=True):
        if brand and brand.lower() in text_lower:
            found[META_BRAND] = brand
            break

    # Soft brand pattern: "của panasonic", "hãng LG"
    if META_BRAND not in found:
        m = re.search(
            r"(?:hãng|hang|của|cua|brand)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-\s]{1,30})",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            found[META_BRAND] = m.group(1).strip(" .,!")

    price = extract_price(text)
    if price is not None:
        found[META_MAX_PRICE] = price

    liters = extract_capacity_liters(text)
    if liters is not None:
        cap_key = pick_capacity_key(spec_keys)
        if cap_key:
            found[cap_key] = liters

    door_value = extract_door_value(text)
    if door_value is not None:
        door_key = pick_door_key(spec_keys)
        if door_key:
            found[door_key] = door_value

    # If user mentions a spec key name explicitly: "dung tích tổng 500"
    for key in spec_keys:
        key_norm = normalize_text(key)
        if len(key_norm) >= 4 and key_norm in normalize_text(text):
            # Try capture trailing value after key mention.
            pattern = re.compile(
                re.escape(key) + r"\s*[:\-]?\s*([^\.,;]+)",
                re.IGNORECASE,
            )
            m = pattern.search(text)
            if m:
                found[key] = m.group(1).strip()

    # Pending question answer: if user didn't fill that slot yet via extract.
    if pending_field and pending_field not in found:
        answer = text.strip()
        if pending_field == META_BRAND:
            cleaned = re.sub(
                r"^(tôi\s+)?(muốn\s+)?mua\s+(của\s+|hang\s+|hãng\s+)?",
                "",
                answer,
                flags=re.IGNORECASE,
            ).strip(" .,!")
            found[META_BRAND] = found.get(META_BRAND) or cleaned or answer
        elif pending_field == META_MAX_PRICE:
            found[META_MAX_PRICE] = found.get(META_MAX_PRICE) or extract_price(answer) or answer
        else:
            matches = (
                spec_dictionary.resolve_field(pending_field, allowed)
                if allowed
                else [pending_field]
            )
            target = matches[0] if matches else pending_field
            if target not in found:
                if liters and (
                    "dung tích" in normalize_text(target)
                    or "dung luong" in normalize_text(target)
                ):
                    found[target] = liters
                else:
                    found[target] = answer

    return found


def next_field_to_ask(session_ask_order: list[str], criteria: dict[str, Any], asked: list[str]) -> str | None:
    for field in session_ask_order:
        if field in criteria:
            continue
        if field in asked:
            continue
        return field
    # Ask any remaining unfilled from order even if asked? prefer unasked first.
    for field in session_ask_order:
        if field not in criteria:
            return field
    return None
