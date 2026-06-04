from models.places import ChatPlace
from models.chat import ChatContext
from services.chat_service import build_places_context, _ensure_alternating_roles


def test_build_context_none():
    assert build_places_context(None) == ""


def test_build_context_empty():
    ctx = ChatContext(address=None, places=[])
    assert build_places_context(ctx) == ""


def test_build_context_address_only():
    ctx = ChatContext(address="Тверская 10", places=[])
    result = build_places_context(ctx)
    assert "Тверская 10" in result
    assert "Places" not in result


def test_build_context_places_only():
    ctx = ChatContext(
        address=None,
        places=[
            ChatPlace(name="Кафе Пушкин", category="cafe", address="Тверской бульвар", distance_label="200 м"),
        ]
    )
    result = build_places_context(ctx)
    assert "1. Кафе Пушкин - cafe - Тверской бульвар - 200 м" in result


def test_build_context_places_no_optional_fields():
    ctx = ChatContext(
        address=None,
        places=[ChatPlace(name="Бар Нора")]
    )
    result = build_places_context(ctx)
    assert "1. Бар Нора" in result


def test_build_context_multiple_places():
    ctx = ChatContext(
        address="Москва",
        places=[
            ChatPlace(name="Кафе А", category="cafe", distance_label="100 м"),
            ChatPlace(name="Ресторан Б", category="restaurant", distance_label="500 м"),
        ]
    )
    result = build_places_context(ctx)
    assert "User address: Москва" in result
    assert "1. Кафе А - cafe - 100 м" in result
    assert "2. Ресторан Б - restaurant - 500 м" in result


def test_build_context_place_all_fields_none():
    ctx = ChatContext(
        address=None,
        places=[ChatPlace(name=None, address=None, category=None, distance_label=None)]
    )
    result = build_places_context(ctx)
    assert result.strip() == "Places:"


# ---------------------------------------------------------------------------
# _ensure_alternating_roles
# ---------------------------------------------------------------------------


def test_ensure_empty():
    assert _ensure_alternating_roles([]) == []


def test_ensure_single_message():
    msgs = [{"role": "user", "content": "hello"}]
    assert _ensure_alternating_roles(msgs) == msgs


def test_ensure_already_alternating():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "how are you"},
    ]
    expected = msgs[:]
    assert _ensure_alternating_roles(msgs) == expected


def test_ensure_consecutive_user():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hey"},
    ]
    result = _ensure_alternating_roles(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "hi\nhello"
    assert result[1]["role"] == "assistant"


def test_ensure_consecutive_assistant():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "assistant", "content": "anything else?"},
    ]
    result = _ensure_alternating_roles(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "hello\nanything else?"


def test_ensure_all_same_role():
    msgs = [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    result = _ensure_alternating_roles(msgs)
    assert len(result) == 1
    assert result[0]["content"] == "a\nb\nc"
