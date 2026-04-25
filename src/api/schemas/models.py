from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    name: str


class ProviderInfo(BaseModel):
    id: str
    name: str
    configured: bool
    default_model: str
    models: list[ModelInfo]
