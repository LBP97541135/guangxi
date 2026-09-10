import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.database import create_engine_from_url, init_db, make_session_factory
from app.models import QuoteStatus, Session
from app import repository as repo


@pytest.fixture
def db() -> OrmSession:
    engine = create_engine_from_url("sqlite://")
    init_db(engine)
    factory = make_session_factory(engine)
    session = factory()
    yield session
    session.close()


def test_create_and_get_session(db):
    created = repo.create_session(db, status="QUESTION_1", current_round=1)
    db.commit()

    fetched = repo.get_session(db, created.id)

    assert fetched is not None
    assert fetched.status == "QUESTION_1"
    assert fetched.current_round == 1
    assert fetched.created_at is not None


def test_get_missing_session_returns_none(db):
    assert repo.get_session(db, "00000000-0000-0000-0000-000000000000") is None


def test_three_answers_saved(db):
    session_row = repo.create_session(db, status="QUESTION_1", current_round=1)
    for round_no in (1, 2, 3):
        repo.add_answer(db, session_row.id, round_no, "text", None, f"答案{round_no}")
    db.commit()

    answers = repo.list_answers(db, session_row.id)

    assert [a.round_no for a in answers] == [1, 2, 3]


def test_duplicate_round_answer_violates_unique_constraint(db):
    session_row = repo.create_session(db, status="QUESTION_1", current_round=1)
    repo.add_answer(db, session_row.id, 1, "text", None, "第一次")
    db.commit()

    with pytest.raises(IntegrityError):
        repo.add_answer(db, session_row.id, 1, "text", None, "第二次")
        db.commit()
    db.rollback()

    answers = repo.list_answers(db, session_row.id)
    assert len(answers) == 1
    assert answers[0].content == "第一次"


def test_second_quote_violates_unique_constraint(db):
    from app.models import Quote

    session_row = repo.create_session(db, status="QUESTION_1", current_round=1)
    repo.ensure_quote(db, session_row.id, model="fake")
    db.commit()

    with pytest.raises(IntegrityError):
        db.add(Quote(session_id=session_row.id, status=QuoteStatus.GENERATING))
        db.commit()
    db.rollback()

    quotes = db.query(Quote).filter(Quote.session_id == session_row.id).all()
    assert len(quotes) == 1


def test_failed_transaction_leaves_no_partial_answer(db):
    session_row = repo.create_session(db, status="QUESTION_1", current_round=1)
    db.commit()

    try:
        repo.add_answer(db, session_row.id, 1, "text", None, "有效答案")
        repo.add_answer(db, session_row.id, 1, "text", None, "违反约束的重复答案")
        db.commit()
    except IntegrityError:
        db.rollback()

    answers = repo.list_answers(db, session_row.id)
    state = repo.get_session(db, session_row.id)
    assert answers == []
    assert state.status == "QUESTION_1"


def test_quote_lifecycle(db):
    session_row = repo.create_session(db, status="GENERATING", current_round=3)
    quote = repo.ensure_quote(db, session_row.id, model="fake")
    assert quote.status == QuoteStatus.GENERATING.value
    db.commit()

    quote = repo.get_quote(db, session_row.id)
    attempts = repo.count_attempts(quote)
    repo.mark_quote_succeeded(db, quote, "其实，你……", model="fake")
    db.commit()

    quote = repo.get_quote(db, session_row.id)
    assert quote.content == "其实，你……"
    assert quote.status == QuoteStatus.SUCCEEDED.value
    assert quote.generation_attempts == attempts == 1


def test_update_session_state(db):
    session_row = repo.create_session(db, status="QUESTION_1", current_round=1)
    db.commit()

    fetched = repo.get_session(db, session_row.id)
    repo.update_session_state(db, fetched, status="QUESTION_2", current_round=2)
    db.commit()

    assert repo.get_session(db, session_row.id).status == "QUESTION_2"


def test_session_ids_unique_and_unpredictable(db):
    first = repo.create_session(db, status="QUESTION_1", current_round=1)
    second = repo.create_session(db, status="QUESTION_1", current_round=1)
    db.commit()

    assert first.id != second.id
    assert len(first.id) == 36
