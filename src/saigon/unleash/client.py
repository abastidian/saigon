from typing import List, Optional

from ..rest import RestClient

from pydantic import BaseModel

__all__ = [
    'UnleashClient',
    'UnleashFeatureFlag',
    'GetFeaturesResponse'
]


class UnleashFeatureFlag(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool


class GetFeaturesResponse(BaseModel):
    version: int
    features: List[UnleashFeatureFlag]


class UnleashClient(RestClient):
    def __init__(self, url, **kwargs):
        super().__init__(url, **kwargs)

    def fetch_feature_flags(
            self,
            instance_id: str,
            app_name: str
    ) -> GetFeaturesResponse:
        return super().get_resource(
            GetFeaturesResponse,
            "/client/features",
            headers={
                'UNLEASH-INSTANCEID': instance_id,
                'UNLEASH-APPNAME': app_name
            }
        )
