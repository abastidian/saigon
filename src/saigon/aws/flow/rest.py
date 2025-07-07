import tempfile
import json
from pathlib import Path
from typing import List, Callable, Generator

from pydantic import BaseModel

from ...model import QueryDataParams, QueryDataResult
from ...utils import EventHandler


__all__ = [
    'FetchResourceHandler'
]


class FetchResourceHandler[
    InputData, CustomQuerySelection, Result: Path | List[BaseModel]
](
    EventHandler[InputData, Result]
):
    def __init__(
            self,
            fetch_resource: Callable[[QueryDataParams[CustomQuerySelection]], QueryDataResult],
            build_query: Callable[[InputData], CustomQuerySelection],
            dump_to_file=True
    ):
        self._fetch_resource = fetch_resource
        self._build_query = build_query
        self._dump_to_file = dump_to_file

    def on_event(self, input_data: InputData) -> Generator[Result]:
        query_params = QueryDataParams(
            query=self._build_query(input_data)
        )
        result_elements = []
        with (
            tempfile.NamedTemporaryFile(
                mode='w+', delete=True, encoding='utf-8', dir='/tmp', suffix='.json'
            ) as output_file
        ):
            while True:
                result = self._fetch_resource(query_params)
                if self._dump_to_file:
                    for item in result.data:
                        json.dump(
                            item.model_dump(), output_file, indent=2
                        )
                else:
                    result_elements.extend(result.data)

                if result.pagination_token:
                    query_params = QueryDataParams(query=result.pagination_token)
                else:
                    break

            if result_elements:
                yield result_elements
            else:
                yield Path(output_file.name)
