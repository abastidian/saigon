from typing import Optional, Type, Dict

from ..interface import KeyValueRepository

from .client import UnleashClient, UnleashFeatureFlag
from ..utils import EnvironmentRepository

__all__ = [
    'UnleashFeatureFlagRepository'
]


class UnleashFeatureFlagRepository(KeyValueRepository):
    def __init__(
            self,
            url_or_client: str | UnleashClient,
            instance_id: str,
            environment: str
    ):
        client = (
            UnleashClient(url_or_client)
            if isinstance(url_or_client, str)
            else url_or_client
        )
        feature_response = client.fetch_feature_flags(
            instance_id, environment
        )
        self._flags: Dict[str, UnleashFeatureFlag] = {
            flag.name: flag
            for flag in feature_response.features
        }

    def get_by_name(
            self, key_type: Type[KeyValueRepository.ValueType], key: str
    ) -> Optional[KeyValueRepository.ValueType]:
        flag = self._flags.get(key.lower())
        if flag is None or not flag.enabled:
            return None

        value_parser = EnvironmentRepository._VALUE_PARSERS.get(key_type, key_type)
        return value_parser(flag.description)

    def set_by_name(
            self, key: str, value: KeyValueRepository.ValueType
    ) -> Optional[KeyValueRepository.ValueType]:
        raise NotImplementedError("Unsupported operation")
