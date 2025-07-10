from typing import Type, Mapping, TypeVar, Dict, Set, Any

from pydantic import BaseModel

import sqlalchemy

ModelType = TypeVar('ModelType', bound=BaseModel)


def filter_unknown_model_fields(
    model_type: Type[ModelType], model_data: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Filters a dictionary to include only keys that are fields in a given Pydantic model.

    Also excludes values that are `None`. This is useful when preparing data
    from a database row or an external source to be validated against a Pydantic model,
    preventing errors from unexpected fields.

    Args:
        model_type (Type[ModelType]): The Pydantic model class to filter against.
        model_data (Mapping[str, Any]): A dictionary of data, typically from a
            database row or similar source.

    Returns:
        Mapping[str, Any]: A new dictionary containing only the keys that
            match the `model_type`'s fields and have non-None values.

    Example::

        from pydantic import BaseModel

        class User(BaseModel):
            id: int
            name: str
            email: str
            age: int | None = None

        data = {
            "id": 1,
            "name": "Alice",
            "email": "alice@example.com",
            "unknown_field": "some_value",
            "age": None
        }
        filtered_data = filter_unknown_model_fields(User, data)
        print(filtered_data)
        # Expected output: {'id': 1, 'name': 'Alice', 'email': 'alice@example.com'}
    """
    return {
        name: value
        for name, value in model_data.items()
        if name in model_type.model_fields and value is not None
    }


def model_data_to_row_values(
        model_data: ModelType,
        include: Set[str] = None,
        exclude: Set[str] = None,
        exclude_unset: bool = True,
        exclude_none: bool = True,
        **extra: Any
) -> Dict[str, str]:
    """Converts a Pydantic model instance into a dictionary suitable for database row insertion/update.

    Serializes the model's data into a dictionary, with all values converted to
    strings, except for dictionaries, booleans, and lists which are kept as their
    native Python types (as they might be JSONB fields or similar).
    Allows for inclusion/exclusion of specific fields and adds extra key-value pairs.

    Args:
        model_data (ModelType): An instance of a Pydantic BaseModel.
        include (Set[str], optional): A set of field names to include. If None, all are included.
        exclude (Set[str], optional): A set of field names to exclude. If None, none are excluded.
        exclude_unset (bool): If True, fields that were not explicitly set on the model
            (even if they have a default value) are excluded. Defaults to True.
        exclude_none (bool): If True, fields whose value is `None` are excluded. Defaults to True.
        **extra (Any): Additional keyword arguments to include in the resulting dictionary.

    Returns:
        Dict[str, str]: A dictionary representing the model data, with values
            converted to strings (or kept as native types for dict, bool, list),
            ready for database operations.

    Example::

        from pydantic import BaseModel
        from typing import Dict, List, Optional

        class Product(BaseModel):
            id: int
            name: str
            price: float
            metadata: Dict[str, Any]
            tags: List[str]
            description: Optional[str] = None

        product_instance = Product(
            id=101,
            name="Laptop",
            price=1200.50,
            metadata={"weight_kg": 2.5, "color": "silver"},
            tags=["electronics", "portable"]
        )

        row_values = model_data_to_row_values(product_instance, extra={"created_by": "system"})
        print(row_values)
        # Expected output (order might vary):
        # {
        #     'id': '101', 'name': 'Laptop', 'price': '1200.5',
        #     'metadata': {'weight_kg': 2.5, 'color': 'silver'},
        #     'tags': ['electronics', 'portable'], 'created_by': 'system'
        # }

        # Example with exclude_unset (if description was not passed in __init__)
        product_instance_2 = Product(id=102, name="Monitor", price=300.0, metadata={}, tags=[])
        row_values_unset_excluded = model_data_to_row_values(product_instance_2, exclude_unset=True)
        print(row_values_unset_excluded)
        # Expected: {'id': '102', 'name': 'Monitor', 'price': '300.0', 'metadata': {}, 'tags': []}
        # 'description' is not included because it was not explicitly set and exclude_unset is True
    """
    return dict(
        {
            name: (
                value if (
                    isinstance(value, Dict) or isinstance(value, bool) or isinstance(value, list)
                )
                else str(value)
            )
            for name, value in model_data.model_dump(
                include=include,
                exclude=exclude,
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
            ).items()
        },
        **{
            name: value for name, value in extra.items()
        }
    )


def row_mapping_to_model_data(
        model_type: Type[ModelType],
        row_mapping: sqlalchemy.RowMapping,
        **kwargs: Any
) -> ModelType:
    """
    Converts a SQLAlchemy `RowMapping` object into an instance of a Pydantic model.

    It first filters out any keys in the `row_mapping` that are not defined
    as fields in the `model_type` and removes `None` values, then instantiates
    the Pydantic model.

    Args:
        model_type (Type[ModelType]): The Pydantic model class to convert the
            row mapping into.
        row_mapping (sqlalchemy.RowMapping): A SQLAlchemy `RowMapping` object,
            which is a dictionary-like view of a database row.
        **kwargs (Any): Additional keyword arguments to pass directly to the
            Pydantic model's constructor, which will override values from `row_mapping`
            if there are key conflicts.

    Returns:
        ModelType: An instance of the specified Pydantic model populated with
            data from the `row_mapping` and `kwargs`.

    Example::

        from pydantic import BaseModel
        import sqlalchemy

        class User(BaseModel):
            id: int
            name: str
            email: str

        # Simulate a SQLAlchemy RowMapping
        # In a real scenario, this would come from db_connector.fetch_one(...)._mapping
        mock_row_mapping = sqlalchemy.RowMapping({
            "id": 1,
            "name": "Charlie",
            "email": "charlie@example.com",
            "created_at": "2023-01-01" # Extra field not in User model
        })

        user_model = row_mapping_to_model_data(User, mock_row_mapping)
        print(user_model)
        # Expected output: id=1 name='Charlie' email='charlie@example.com'

        # Example with overriding kwargs
        user_model_override = row_mapping_to_model_data(User, mock_row_mapping, name="Charles")
        print(user_model_override)
        # Expected output: id=1 name='Charles' email='charlie@example.com'
    """
    return model_type(
        **dict(
            filter_unknown_model_fields(model_type, row_mapping),
            **kwargs
        )
    )
