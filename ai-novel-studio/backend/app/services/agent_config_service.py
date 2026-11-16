"""Per-agent model bindings (plan §7.2, gap 1.5).

``agent_configs`` used to be a table nobody read: model selection only ever
looked at ``AIRequest.model_config_id`` and then at the writer's default model,
so "让润色用便宜的小模型" was impossible to express. This service gives the
table its readers:

* the AI service resolves a model **per operation** (see
  :func:`operation_agent_type`), and
* the settings page can list and upsert the bindings.

Only *model selection* is driven by these rows. ``temperature`` / ``max_tokens``
/ ``system_prompt`` are stored and returned for the future agent runtime, but are
deliberately **not** applied to a request yet — silently overriding sampling
parameters the author tuned on the model row would be surprising.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.ids import new_id
from app.core.logging import get_logger
from app.db.session import Database
from app.models.studio import AgentConfig, ModelConfig

logger = get_logger(__name__)

#: Writing operation → ``agent_configs.agent_type``. One-to-one on purpose:
#: guessing that ``continue`` shares the row of a hypothetical ``writing`` agent
#: would bind a model the author never picked, and it would do so silently.
#: Operations missing from this map fall back to the default model.
OPERATION_AGENT_TYPES: dict[str, str] = {
    "outline": "outline",
    "write": "write",
    "continue": "continue",
    "expand": "expand",
    "rewrite": "rewrite",
    "polish": "polish",
    "review": "review",
    #: ``POST /api/ai/outline/{chapter_id}`` persists to ``outlines``; it shares
    #: the outline agent so one setting covers both outline flavours.
    "outline_persist": "outline",
    #: L1 memory distillation is its own agent, not a writing operation.
    "summary": "memory",
}

#: Marks "the caller did not send this field" so an upsert can tell it apart
#: from an explicit ``null`` (= clear the override).
_UNSET: Any = object()


def operation_agent_type(operation: str) -> str | None:
    """Return the agent row an operation is bound to, if any."""
    return OPERATION_AGENT_TYPES.get(operation)


class AgentConfigService:
    def __init__(self, studio_db: Database) -> None:
        self.db = studio_db

    # -- queries ----------------------------------------------------------
    def list(self) -> list[AgentConfig]:
        with self.db.session() as session:
            statement = select(AgentConfig).order_by(AgentConfig.agent_type, AgentConfig.id)
            return list(session.scalars(statement))

    def get(self, agent_type: str) -> AgentConfig | None:
        with self.db.session() as session:
            return session.scalar(
                select(AgentConfig)
                .where(AgentConfig.agent_type == agent_type)
                .order_by(AgentConfig.id)
                .limit(1)
            )

    def resolve_for_operation(self, operation: str) -> AgentConfig | None:
        """Return the active binding for *operation*, or ``None`` for the default."""
        agent_type = operation_agent_type(operation)
        if agent_type is None:
            return None
        row = self.get(agent_type)
        if row is None or not row.is_active:
            return None
        return row

    # -- mutations --------------------------------------------------------
    def upsert(
        self,
        agent_type: str,
        *,
        display_name: str | None = None,
        model_config_id: str | None = _UNSET,
        temperature: float | None = _UNSET,
        max_tokens: int | None = _UNSET,
        system_prompt: str | None = _UNSET,
    ) -> AgentConfig:
        """Create or update the single row for *agent_type*.

        ``agent_type`` is the natural key: a second PUT updates in place (and
        bumps ``row_version``) instead of adding a duplicate binding.
        """
        fields: dict[str, Any] = {}
        if display_name is not None:
            fields["display_name"] = display_name
        if model_config_id is not _UNSET:
            fields["model_config_id"] = model_config_id
        if temperature is not _UNSET:
            fields["temperature"] = temperature
        if max_tokens is not _UNSET:
            fields["max_tokens"] = max_tokens
        if system_prompt is not _UNSET:
            fields["system_prompt"] = system_prompt

        with self.db.session() as session:
            self._require_model(session, fields.get("model_config_id"))
            row = session.scalar(
                select(AgentConfig)
                .where(AgentConfig.agent_type == agent_type)
                .order_by(AgentConfig.id)
                .limit(1)
            )
            if row is None:
                values: dict[str, Any] = {
                    "agent_type": agent_type,
                    "display_name": display_name or agent_type,
                    "system_prompt": "",
                    "params": {},
                    "is_active": True,
                }
                values.update(fields)
                row = AgentConfig(id=new_id("agt"), **values)
                session.add(row)
                session.flush()
                logger.info("agent_config_created", agent_type=agent_type, agent_id=row.id)
            else:
                for field, value in fields.items():
                    if field == "system_prompt" and value is None:
                        value = ""
                    setattr(row, field, value)
                row.row_version += 1
                row.updated_at = datetime.now(UTC)
                session.flush()
                logger.info(
                    "agent_config_updated",
                    agent_type=agent_type,
                    agent_id=row.id,
                    fields=sorted(fields),
                )
            session.refresh(row)
            return row

    @staticmethod
    def _require_model(session: Session, model_config_id: Any) -> None:
        """Reject a binding to a model id that does not exist.

        The column has a ``SET NULL`` foreign key, so without this check a typo
        would surface as an ``IntegrityError`` (500) instead of a 404.
        """
        if not isinstance(model_config_id, str) or not model_config_id:
            return
        if session.get(ModelConfig, model_config_id) is None:
            raise NotFound(f"Model configuration {model_config_id} not found")
