"""Model configuration management.

The database row holds every non-secret setting; the API key lives in the
encrypted :class:`~app.core.keystore.SecretStore` under a label derived from the
row id, and only a boolean ``has_api_key`` ever crosses the wire.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.ids import new_id
from app.core.keystore import SecretStore, secret_label_for_model
from app.core.logging import get_logger
from app.db.session import Database
from app.models.studio import ModelConfig
from app.schemas.model_config import ModelConfigCreate, ModelConfigUpdate

logger = get_logger(__name__)

_COPYABLE = (
    "name",
    "provider",
    "base_url",
    "model_name",
    "temperature",
    "top_p",
    "max_tokens",
    "timeout_s",
    "retry_count",
    "context_window",
    "max_output_tokens",
    "supports_streaming",
    "supports_json_mode",
    "supports_vision",
    "supports_tools",
    "input_price_per_1m",
    "output_price_per_1m",
    "capabilities",
    "notes",
    "is_active",
    "fallback_ids",
)

#: Columns where an explicit ``null`` means "reset to empty" rather than
#: "leave unchanged" — these columns are NOT NULL in the database.
_NULL_DEFAULTS: dict[str, Any] = {
    "base_url": "",
    "notes": "",
    "capabilities": {},
    "fallback_ids": [],
}


class ModelConfigService:
    def __init__(self, studio_db: Database, data_dir: Path) -> None:
        self.db = studio_db
        self.secrets = SecretStore(data_dir)

    # -- queries ----------------------------------------------------------
    def list(self) -> list[ModelConfig]:
        with self.db.session() as session:
            statement = select(ModelConfig).order_by(
                ModelConfig.is_default.desc(), ModelConfig.name
            )
            return list(session.scalars(statement))

    def get(self, model_id: str) -> ModelConfig:
        with self.db.session() as session:
            model = session.get(ModelConfig, model_id)
            if model is None:
                raise NotFound(f"Model configuration {model_id} not found")
            return model

    def resolve(self, model_id: str) -> tuple[ModelConfig, str | None]:
        """Return a model and its decrypted key (backend-internal use only)."""
        model = self.get(model_id)
        return model, self.secrets.get(secret_label_for_model(model.id))

    def default_model(self) -> ModelConfig | None:
        with self.db.session() as session:
            return session.scalar(
                select(ModelConfig).where(ModelConfig.is_default.is_(True)).limit(1)
            )

    # -- mutations --------------------------------------------------------
    def create(self, payload: ModelConfigCreate) -> ModelConfig:
        model_id = new_id("mdl")
        values: dict[str, Any] = {"id": model_id, "is_default": False}
        for field in _COPYABLE:
            values[field] = getattr(payload, field)
        values["api_key_ref"] = secret_label_for_model(model_id)

        with self.db.session() as session:
            model = ModelConfig(**values)
            session.add(model)
            session.flush()
            if payload.api_key:
                self.secrets.set(secret_label_for_model(model.id), payload.api_key)
            session.refresh(model)
            logger.info("model_config_created", model_id=model.id, provider=model.provider)
            return model

    def update(self, model_id: str, payload: ModelConfigUpdate) -> ModelConfig:
        with self.db.session() as session:
            model = session.get(ModelConfig, model_id)
            if model is None:
                raise NotFound(f"Model configuration {model_id} not found")

            if payload.row_version is not None and payload.row_version != model.row_version:
                raise Conflict(
                    "Model configuration was modified elsewhere; reload and retry.",
                    details={"expected": payload.row_version, "actual": model.row_version},
                )

            changes = payload.model_dump(exclude_unset=True, exclude={"row_version", "api_key"})
            for field, value in changes.items():
                if field not in _COPYABLE:
                    continue
                if value is None:
                    if field in _NULL_DEFAULTS:
                        value = _NULL_DEFAULTS[field]
                    else:
                        continue
                setattr(model, field, value)

            if payload.api_key is not None:
                label = secret_label_for_model(model.id)
                if payload.api_key == "":
                    self.secrets.delete(label)
                    model.api_key_ref = None
                else:
                    self.secrets.set(label, payload.api_key)
                    model.api_key_ref = label

            model.row_version += 1
            model.updated_at = datetime.now(UTC)
            session.flush()
            session.refresh(model)
            logger.info("model_config_updated", model_id=model.id, fields=sorted(changes))
            return model

    def delete(self, model_id: str) -> None:
        with self.db.session() as session:
            model = session.get(ModelConfig, model_id)
            if model is None:
                raise NotFound(f"Model configuration {model_id} not found")
            self.secrets.delete(secret_label_for_model(model.id))
            session.delete(model)
            logger.info("model_config_deleted", model_id=model_id)

    def set_default(self, model_id: str) -> ModelConfig:
        """Promote one model to the writer's default."""
        with self.db.session() as session:
            model = session.get(ModelConfig, model_id)
            if model is None:
                raise NotFound(f"Model configuration {model_id} not found")
            for other in session.scalars(select(ModelConfig)):
                other.is_default = other.id == model.id
            session.flush()
            session.refresh(model)
            logger.info("model_config_default", model_id=model.id)
            return model


def to_out(model: ModelConfig, service: ModelConfigService) -> dict[str, Any]:
    """Serialise a model row plus the derived ``has_api_key`` flag."""
    from app.schemas.model_config import ModelConfigOut

    payload = ModelConfigOut.model_validate(model)
    payload.has_api_key = service.secrets.has(secret_label_for_model(model.id))
    return payload.model_dump()


def ensure_default_model(session: Session, service: ModelConfigService) -> None:
    """Create a starter configuration when the studio has none.

    A fresh install should not dead-end on "no model configured": a disabled
    OpenAI-compatible template gives the user something to edit instead.
    """
    existing = session.scalar(select(ModelConfig).limit(1))
    if existing is not None:
        return
    template = ModelConfigCreate(
        name="本地 / OpenAI 兼容",
        provider="openai_compatible",
        base_url="http://127.0.0.1:11434/v1",
        model_name="qwen2.5:14b",
        temperature=0.8,
        context_window=32768,
        max_output_tokens=4096,
        supports_streaming=True,
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        notes="示例配置：指向任意 OpenAI 兼容端点（Ollama / LM Studio / 自建网关）。",
        is_active=True,
    )
    created = service.create(template)
    # Promote it, so a fresh install has a usable default and the user only has
    # to fill in a URL and key rather than configure the app twice.
    service.set_default(created.id)
    logger.info("model_config_template_created", model_id=created.id)
