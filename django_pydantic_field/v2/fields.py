from __future__ import annotations

import typing as ty

import pydantic

from django.core import checks, exceptions
from django.core.serializers.json import DjangoJSONEncoder

from django.db.models.expressions import BaseExpression, Col
from django.db.models.fields.json import JSONField
from django.db.models.lookups import Transform
from django.db.models.query_utils import DeferredAttribute

from . import types, forms
from ..compat.django import GenericContainer


class SchemaAttribute(DeferredAttribute):
    field: PydanticSchemaField

    def __set__(self, obj, value):
        obj.__dict__[self.field.attname] = self.field.to_python(value)


class PydanticSchemaField(JSONField, ty.Generic[types.ST]):
    descriptor_class: type[DeferredAttribute] = SchemaAttribute
    adapter: types.SchemaAdapter

    def __init__(
        self,
        *args,
        schema: type[types.ST] | GenericContainer | ty.ForwardRef | str | None = None,
        config: pydantic.ConfigDict | None = None,
        **kwargs,
    ):
        kwargs.setdefault("encoder", DjangoJSONEncoder)

        self.export_kwargs = export_kwargs = types.SchemaAdapter.extract_export_kwargs(kwargs)
        super().__init__(*args, **kwargs)

        self.schema = schema
        self.config = config
        self.adapter = types.SchemaAdapter(schema, config, None, self.get_attname(), self.null, **export_kwargs)

    def __copy__(self):
        _, _, args, kwargs = self.deconstruct()
        copied = self.__class__(*args, **kwargs)
        copied.set_attributes_from_name(self.name)
        return copied

    def deconstruct(self) -> ty.Any:
        field_name, import_path, args, kwargs = super().deconstruct()
        kwargs.update(schema=GenericContainer.wrap(self.schema), config=self.config, **self.export_kwargs)
        return field_name, import_path, args, kwargs

    def contribute_to_class(self, cls: types.DjangoModelType, name: str, private_only: bool = False) -> None:
        self.adapter.bind(cls, name)
        super().contribute_to_class(cls, name, private_only)

    def check(self, **kwargs: ty.Any) -> list[checks.CheckMessage]:
        performed_checks = super().check(**kwargs)
        try:
            self.adapter.validate_schema()
        except types.ImproperlyConfiguredSchema as exc:
            performed_checks.append(checks.Error(exc.args[0], obj=self))
        return performed_checks

    def validate(self, value: ty.Any, model_instance: ty.Any) -> None:
        value = self.adapter.validate_python(value)
        return super(JSONField, self).validate(value, model_instance)

    def to_python(self, value: ty.Any):
        try:
            return self.adapter.validate_python(value)
        except pydantic.ValidationError as exc:
            error_params = {"errors": exc.errors(), "field": self}
            raise exceptions.ValidationError(exc.json(), code="invalid", params=error_params) from exc

    def get_prep_value(self, value: ty.Any):
        if isinstance(value, BaseExpression):
            # We don't want to perform coercion on database query expressions.
            return super().get_prep_value(value)

        prep_value = self.adapter.validate_python(value)
        plain_value = self.adapter.dump_python(prep_value)
        return super().get_prep_value(plain_value)

    def get_transform(self, lookup_name: str):
        transform: type[Transform] | SchemaKeyTransformAdapter | None
        transform = super().get_transform(lookup_name)
        if transform is not None:
            transform = SchemaKeyTransformAdapter(transform)
        return transform

    def get_default(self) -> types.ST:
        default_value = super().get_default()
        try:
            raw_value = dict(default_value)
            prep_value = self.adapter.validate_python(raw_value, strict=True)
        except (TypeError, ValueError):
            prep_value = self.adapter.validate_python(default_value)

        return prep_value

    def formfield(self, **kwargs):
        field_kwargs = dict(
            form_class=forms.SchemaField,
            # Trying to resolve the schema before passing it to the formfield, since in Django < 4.0,
            # formfield is unbound during form validation and is not able to resolve forward refs defined in the model.
            schema=self.adapter.prepared_schema,
            config=self.config,
            **self.export_kwargs,
        )
        field_kwargs.update(kwargs)
        return super().formfield(**field_kwargs)  # type: ignore


class SchemaKeyTransformAdapter:
    """An adapter for creating key transforms for schema field lookups."""

    def __init__(self, transform: type[Transform]):
        self.transform = transform

    def __call__(self, col: Col | None = None, *args, **kwargs) -> Transform | None:
        """All transforms should bypass the SchemaField's adaptaion with `get_prep_value`,
        and routed to JSONField's `get_prep_value` for further processing."""
        if isinstance(col, BaseExpression):
            col = col.copy()
            col.output_field = super(PydanticSchemaField, col.output_field)  # type: ignore
        return self.transform(col, *args, **kwargs)


def SchemaField(schema=None, config=None, *args, **kwargs):  # type: ignore
    return PydanticSchemaField(*args, schema=schema, config=config, **kwargs)
