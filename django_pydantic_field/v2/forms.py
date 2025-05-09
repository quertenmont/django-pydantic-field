from __future__ import annotations

import typing as ty
import warnings

import pydantic
from django.core.exceptions import ValidationError
from django.forms.fields import InvalidJSONInput, JSONField, JSONString
from django.utils.translation import gettext_lazy as _

from django_pydantic_field.compat import deprecation

from . import types

if ty.TYPE_CHECKING:
    import typing_extensions as te
    from django.forms.widgets import Widget


__all__ = ("SchemaField", "JSONFormSchemaWidget")


class SchemaField(JSONField, ty.Generic[types.ST]):
    adapter: types.SchemaAdapter[types.ST]
    default_error_messages = {
        "schema_error": _("Schema didn't match for %(title)s."),
    }

    def __init__(
        self,
        schema: type[types.ST] | te.Annotated[type[types.ST], ...] | ty.ForwardRef | str,
        config: pydantic.ConfigDict | None = None,
        allow_null: bool | None = None,
        *args,
        **kwargs,
    ):
        deprecation.truncate_deprecated_v1_export_kwargs(kwargs)

        self.schema = schema
        self.config = config
        self.export_kwargs = types.SchemaAdapter.extract_export_kwargs(kwargs)
        self.adapter = types.SchemaAdapter(schema, config, None, None, allow_null, **self.export_kwargs)

        widget = kwargs.get("widget")
        if widget is not None:
            kwargs["widget"] = _prepare_jsonform_widget(widget, self.adapter)

        super().__init__(*args, **kwargs)

    def get_bound_field(self, form: ty.Any, field_name: str):
        if not self.adapter.is_bound:
            self.adapter.bind(form, field_name)
        return super().get_bound_field(form, field_name)

    def bound_data(self, data: ty.Any, initial: ty.Any):
        if self.disabled:
            return self.adapter.validate_python(initial)
        if data is None:
            return None
        try:
            return self.adapter.validate_json(data)
        except pydantic.ValidationError:
            return InvalidJSONInput(data)

    def to_python(self, value: ty.Any) -> ty.Any:
        if self.disabled:
            return value
        if value in self.empty_values:
            return None

        try:
            value = self._try_coerce(value)
        except pydantic.ValidationError as exc:
            error_params = {"value": value, "title": exc.title, "detail": exc.json(), "errors": exc.errors()}
            raise ValidationError(self.error_messages["schema_error"], code="invalid", params=error_params) from exc

        if isinstance(value, str):
            value = JSONString(value)

        return value

    def prepare_value(self, value):
        if value is None:
            return None

        if isinstance(value, InvalidJSONInput):
            return value

        value = self._try_coerce(value)
        return self.adapter.dump_json(value).decode()

    def has_changed(self, initial: ty.Any | None, data: ty.Any | None) -> bool:
        try:
            initial = self._try_coerce(initial)
            data = self._try_coerce(data)
            return self.adapter.dump_python(initial) != self.adapter.dump_python(data)
        except pydantic.ValidationError:
            return True

    def _try_coerce(self, value):
        if not isinstance(value, (str, bytes)):
            # The form data may contain python objects for some cases (e.g. using django-constance).
            value = self.adapter.validate_python(value)
        elif not isinstance(value, JSONString):
            # Otherwise, try to parse incoming JSON according to the schema.
            value = self.adapter.validate_json(value)

        return value


try:
    from django_jsonform.widgets import JSONFormWidget as _JSONFormWidget  # type: ignore[import-untyped]
except ImportError:
    from django.forms.widgets import Textarea

    def _prepare_jsonform_widget(widget, adapter: types.SchemaAdapter[types.ST]) -> Widget | type[Widget]:
        return widget

    class JSONFormSchemaWidget(Textarea):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "The 'django_jsonform' package is not installed. Please install it to use the widget.",
                ImportWarning,
            )
            super().__init__(*args, **kwargs)

else:

    def _prepare_jsonform_widget(widget, adapter: types.SchemaAdapter[types.ST]) -> Widget | type[Widget]:  # type: ignore[no-redef]
        if not isinstance(widget, type):
            return widget

        if issubclass(widget, JSONFormSchemaWidget):
            widget = widget(
                schema=adapter.prepared_schema,
                config=adapter.config,
                export_kwargs=adapter.export_kwargs,
                allow_null=adapter.allow_null,
            )
        elif issubclass(widget, _JSONFormWidget):
            widget = widget(schema=adapter.json_schema())  # type: ignore[call-arg]

        return widget

    class JSONFormSchemaWidget(_JSONFormWidget, ty.Generic[types.ST]):  # type: ignore[no-redef]
        def __init__(
            self,
            schema: type[types.ST] | te.Annotated[type[types.ST], ...] | ty.ForwardRef | str,
            config: pydantic.ConfigDict | None = None,
            allow_null: bool | None = None,
            export_kwargs: types.ExportKwargs | None = None,
            **kwargs,
        ):
            if export_kwargs is None:
                export_kwargs = {}
            adapter = types.SchemaAdapter[types.ST](schema, config, None, None, allow_null, **export_kwargs)
            super().__init__(adapter.json_schema(), **kwargs)
