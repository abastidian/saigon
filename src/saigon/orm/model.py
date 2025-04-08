from typing import Type, Mapping, TypeVar, Dict, Set

from pydantic import BaseModel

import sqlalchemy

ModelType = TypeVar('ModelType', bound=BaseModel)


def filter_unknown_model_fields(
    model_type: Type[ModelType], model_data: Mapping
) -> Mapping:
    return {
        name: value
        for name, value in model_data.items()
        if name in model_type.model_fields and value is not None
    }


def model_data_to_row_values(
        model_data: ModelType,
        include: Set[str] = None,
        exclude: Set[str] = None,
        exclude_unset=True,
        exclude_none=True,
        **extra
) -> Dict[str, str]:
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
        **kwargs
) -> ModelType:
    return model_type(
        **dict(
            filter_unknown_model_fields(model_type, row_mapping),
            **kwargs
        )
    )
