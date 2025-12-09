"""
Context manager for disabling Pydantic validation when loading data from database.

This module provides a thread-safe, async-safe mechanism to temporarily bypass
Pydantic validation using contextvars.
"""

from __future__ import annotations

import contextvars

__all__ = ("DisableValidation", "is_validation_disabled")


# Context variable for validation bypass state
_validation_disabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'validation_disabled', default=False
)


def is_validation_disabled() -> bool:
    """Check if validation is currently disabled in this context.
    
    Returns:
        bool: True if validation is disabled, False otherwise.
    """
    return _validation_disabled.get()


class DisableValidation:
    """Context manager to temporarily disable Pydantic validation when loading data from database.
    
    This is useful when you have data in the database that doesn't conform to your current schema
    and you need to retrieve it for inspection or correction.
    
    This context manager is:
    - Thread-safe: Each thread has independent validation state
    - Async-safe: Works correctly with asyncio and other async frameworks
    - Exception-safe: Validation state is restored even if errors occur
    
    Example:
        >>> from django_pydantic_field import DisableValidation
        >>> with DisableValidation():
        ...     # Validation is disabled for all PydanticSchemaField instances
        ...     invalid_records = MyModel.objects.filter(...)  # Won't raise ValidationError
        ...     for record in invalid_records:
        ...         # Fix the data manually
        ...         record.schema_field = corrected_value
        ...         record.save()
    
    Warning:
        When validation is disabled, you'll receive the raw data from the database as-is.
        This means you won't get Pydantic model instances, but plain Python dicts/lists instead.
        Be careful when working with this data.
        
    Note:
        This only affects data loading from the database (from_db_value, to_python).
        It does NOT disable validation when saving data (.save(), .create(), .update()).
    """
    
    def __init__(self):
        self._token = None
    
    def __enter__(self):
        self._token = _validation_disabled.set(True)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _validation_disabled.reset(self._token)
        return False
