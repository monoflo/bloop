import declare

from .column import Column
from .index import GlobalSecondaryIndex, LocalSecondaryIndex


__all__ = ["new_base", "BaseModel"]

_MISSING = object()


def new_base():
    """Return an unbound, abstract base model"""
    class Model(BaseModel, metaclass=ModelMetaclass):
        class Meta:
            abstract = True
    return Model


class ModelMetaclass(declare.ModelMetaclass):
    def __new__(mcs, name, bases, attrs):
        model = super().__new__(mcs, name, bases, attrs)
        meta = model.Meta
        meta.model = model
        # new_class will set abstract to true, all other models are assumed
        # to be concrete unless specified
        setdefault(meta, "abstract", False)
        setdefault(meta, "write_units", 1)
        setdefault(meta, "read_units", 1)

        setup_columns(meta)
        setup_indexes(meta)

        # Entry point for model population. By default this is the
        # class's __init__ function. Custom models can specify the
        # Meta attr `init`, which must be a function taking no
        # arguments that returns an instance of the class
        setdefault(meta, "init", model)
        setdefault(meta, "table_name", model.__name__)

        return model


def setdefault(obj, field, default):
    """Set an object's field to default if it doesn't have a value"""
    setattr(obj, field, getattr(obj, field, default))


def setup_columns(meta):
    """Filter columns from fields, identify hash and range keys"""

    # This is a set instead of a list, because set uses __hash__
    # while some list operations uses __eq__ which will break
    # with the ComparisonMixin
    meta.columns = set(filter(
        lambda field: isinstance(field, Column), meta.fields))

    meta.hash_key = None
    meta.range_key = None
    meta.keys = set()
    for column in meta.columns:
        if column.hash_key:
            if meta.hash_key:
                raise ValueError("Model hash_key over-specified")
            meta.hash_key = column
            meta.keys.add(column)
        elif column.range_key:
            if meta.range_key:
                raise ValueError("Model range_key over-specified")
            meta.range_key = column
            meta.keys.add(column)
        column.model = meta.model


def setup_indexes(meta):
    """Filter indexes from fields, compute projection for each index"""
    # These are sets instead of lists, because sets use __hash__
    # while some list operations use __eq__ which will break
    # with the ComparisonMixin
    meta.gsis = set(filter(
        lambda field: isinstance(field, GlobalSecondaryIndex),
        meta.fields))
    meta.lsis = set(filter(
        lambda field: isinstance(field, LocalSecondaryIndex),
        meta.fields))
    meta.indexes = set.union(meta.gsis, meta.lsis)

    for index in meta.indexes:
        index._bind(meta.model)


class BaseModel:
    """
    Do not subclass directly; use new_base.

    Example:

        BaseModel = new_base()

        class MyModel(BaseModel):
            ...

        engine = bloop.Engine()
        engine.bind(base=BaseModel)
    """
    def __init__(self, **attrs):
        # Only set values from **attrs if there's a
        # corresponding `model_name` for a column in the model
        for column in self.Meta.columns:
            value = attrs.get(column.model_name, _MISSING)
            if value is not _MISSING:
                setattr(self, column.model_name, value)

    @classmethod
    def _load(cls, attrs, *, context, **kwargs):
        """ dict (dynamo name) -> obj """
        if attrs is None:
            attrs = {}
        obj = cls.Meta.init()
        # We want to expect the exact attributes that are passed,
        # since any superset will mark missing fields as expected.
        expected = filter(lambda col: col.dynamo_name in attrs, cls.Meta.columns)
        context["engine"]._update(obj, attrs, expected, **kwargs)
        return obj

    @classmethod
    def _dump(cls, obj, *, context, **kwargs):
        """ obj -> dict """
        if obj is None:
            return None
        dump = context["engine"]._dump
        filtered = filter(
            lambda item: item[1] is not None,
            ((
                column.dynamo_name,
                dump(column.typedef, getattr(obj, column.model_name, None), context=context, **kwargs)
            ) for column in cls.Meta.columns))
        return dict(filtered) or None

    def __str__(self):  # pragma: no cover
        attrs = ", ".join((
            "{}={}".format(column.model_name, getattr(self, column.model_name, None))
            for column in self.Meta.columns
        ))
        return "{}({})".format(self.__class__.__name__, attrs)
    __repr__ = __str__

    __hash__ = object.__hash__

    def __eq__(self, other):
        """ Only checks defined columns. """
        if self is other:
            return True
        cls = self.__class__
        if not isinstance(other, cls):
            return False
        for column in cls.Meta.columns:
            value = getattr(self, column.model_name, None)
            other_value = getattr(other, column.model_name, None)
            if value != other_value:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)
