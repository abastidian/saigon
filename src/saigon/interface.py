from abc import abstractmethod
from typing import Protocol, Type

from pydantic import BaseModel

__all__ = ['SecretVault']


class SecretVault(Protocol):
    """
    Interface definition for vault-like component that safely retrieves secret
    data from a remote store.
    """

    @abstractmethod
    def get_secret[SecretModel: BaseModel](
            self,
            secret_model: Type[SecretModel],
            secret_key: str
    ) -> SecretModel:
        """
            Returns the secret specified by its `secret_key` represented as a `SecretModel`
            object.
        Args:
            secret_model: Type representation of the secret content
            secret_key: Secret unique identifier

        Returns:
            Secret data represented as the specified `SecretModel`
        """
        ...
