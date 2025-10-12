from typing import Type, Optional, Dict

import boto3
from mypy_boto3_ssm.client import SSMClient

from pydantic import BaseModel

__all__ = [
    'get_parameter_as_model',
    'get_parameter_mapping_as_model'
]


def get_parameter_as_model[TargetModel: BaseModel](
        model_type: Type[TargetModel],
        parameter: str,
        with_decryption: Optional[bool] = False,
        ssm_client: Optional[SSMClient] = None,
) -> TargetModel:
    """Retrieves a parameter from AWS SSM and deserializes it as JSON into a
    Pydantic model.

    Args:
        model_type (Type[TargetModel]): The Pydantic model class to deserialize the parameters into.
        parameter (str): Name or ARN of the parameter
        with_decryption (Optional[bool]): whether decrpytion is applied to the parameter
            Defaults to False.
        ssm_client (Optional[SSMClient]): An optional Boto3 SSM client.
            If None, a new client will be created. Defaults to None.

    Returns:
        ModelTypeDef: An instance of the specified Pydantic model validated from the
        parameter value as json
    """
    if ssm_client is None:
        ssm_client: SSMClient = boto3.client('ssm')

    response = ssm_client.get_parameter(Name=parameter, WithDecryption=with_decryption)
    return model_type.model_validate_json(response['Parameter']['Value'])


def get_parameter_mapping_as_model[TargetModel: BaseModel](
        model_type: Type[TargetModel],
        param_mapping: Dict[str, str],
        with_decryption: Optional[bool] = False,
        ssm_client: Optional[SSMClient] = None,
        **kwargs
) -> TargetModel:
    """Retrieves a list of parameters from AWS SSM and converts them into a
    Pydantic model.

    Args:
        model_type (Type[TargetModel]): The Pydantic model class to deserialize the parameters into.
        param_mapping (Dict[str]): Mapping of parameter names or ARNs to model attributes
        with_decryption (Optional[bool]): whether decrpytion is applied to the parameters.
            Defaults to False.
        ssm_client (Optional[SSMClient]): An optional Boto3 SSM client.
            If None, a new client will be created. Defaults to None.
        **kwargs: extra model parameters if necessary to successfully construct the
        model object.

    Returns:
        ModelTypeDef: An instance of the specified Pydantic model populated with
        the parameters values
    """
    if ssm_client is None:
        ssm_client: SSMClient = boto3.client('ssm')

    response = ssm_client.get_parameters(
        Names=list(param_mapping.keys()), WithDecryption=with_decryption
    )
    return model_type.model_validate(
        dict(
            {
                param_mapping[parameter['Name']]: parameter['Value']
                for parameter in response['Parameters']
            },
            **kwargs
        )
    )
