from tensemem.core.models import Cardinality
from tensemem.core.slots import slot_key


def test_one_slot_ignores_object() -> None:
    bangalore = slot_key(
        scope_id=1,
        subject_id=2,
        predicate_id=3,
        cardinality=Cardinality.ONE,
        object_norm="bangalore",
    )
    pune = slot_key(
        scope_id=1,
        subject_id=2,
        predicate_id=3,
        cardinality=Cardinality.ONE,
        object_norm="pune",
    )
    assert bangalore == pune


def test_many_slot_includes_object() -> None:
    rust = slot_key(
        scope_id=1,
        subject_id=2,
        predicate_id=3,
        cardinality=Cardinality.MANY,
        object_norm="rust",
    )
    go = slot_key(
        scope_id=1,
        subject_id=2,
        predicate_id=3,
        cardinality=Cardinality.MANY,
        object_norm="go",
    )
    assert rust != go


def test_different_scopes_do_not_share_a_slot() -> None:
    a = slot_key(scope_id=1, subject_id=2, predicate_id=3, cardinality=Cardinality.ONE)
    b = slot_key(scope_id=9, subject_id=2, predicate_id=3, cardinality=Cardinality.ONE)
    assert a != b
