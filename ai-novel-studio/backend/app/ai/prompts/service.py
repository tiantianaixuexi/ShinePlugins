"""Prompt template storage and rendering.

Built-ins are seeded into ``prompt_templates`` once; from then on the table is
authoritative, so editing a prompt in the UI takes effect immediately and the
change is recorded per generation.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.ai.prompts.builtin import OPERATIONS, PROMPTS, PROMPTS_BY_KEY, PromptSpec
from app.core.logging import get_logger
from app.db.session import Database
from app.models.studio import PromptTemplate

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render(template: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    """Substitute ``{{name}}`` placeholders.

    Returns the rendered text and the names that had no value, so callers can
    log a malformed prompt instead of silently sending an empty section.
    """
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            missing.append(name)
            return ""
        return variables[name]

    return _PLACEHOLDER_RE.sub(replace, template), missing


class PromptService:
    """Read and render prompt templates."""

    def __init__(self, studio_db: Database) -> None:
        self.db = studio_db

    # -- seeding ----------------------------------------------------------
    def ensure_builtins(self) -> int:
        """Insert any built-in prompt that is missing. Returns the count added."""
        with self.db.session() as session:
            existing = set(session.scalars(select(PromptTemplate.key)))
            added = 0
            for spec in PROMPTS:
                if spec.key in existing:
                    continue
                session.add(
                    PromptTemplate(
                        key=spec.key,
                        name=spec.name,
                        version=1,
                        content=self._compose(spec),
                        variables=list(spec.variables),
                        description=spec.description,
                        is_active=True,
                    )
                )
                added += 1
            if added:
                logger.info("prompts_seeded", count=added)
        return added

    @staticmethod
    def _compose(spec: PromptSpec) -> str:
        """Store system + user in one column, separated by a marker line."""
        return f"### system\n{spec.system}\n### user\n{spec.user}"

    @staticmethod
    def _split(content: str, fallback: PromptSpec) -> tuple[str, str]:
        """Split the stored ``### system`` / ``### user`` form back apart."""
        if "### system" in content and "### user" in content:
            _, _, rest = content.partition("### system")
            system_text, _, user_text = rest.partition("### user")
            system_text = system_text.strip()
            user_text = user_text.strip()
            if system_text or user_text:
                return system_text or fallback.system, user_text or fallback.user
        return fallback.system, fallback.user or content

    # -- queries ----------------------------------------------------------
    def list(self) -> list[PromptTemplate]:
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(PromptTemplate).order_by(PromptTemplate.key, PromptTemplate.version)
                )
            )

    def upsert_override(
        self,
        key: str,
        content: str,
        *,
        name: str | None = None,
        variables: list[str] | None = None,
        description: str | None = None,
    ) -> PromptTemplate:
        """Store a new version of *key*, leaving earlier versions untouched.

        Old rows stay in the table so a generation recorded against version *n*
        can still be traced back; :meth:`resolve` picks the highest active
        version. Raises ``KeyError`` for a key that is not a known built-in, so
        a typo in the authoring UI can never create a prompt nobody renders.
        """
        fallback = PROMPTS_BY_KEY.get(key)
        if fallback is None:
            raise KeyError(key)
        with self.db.session() as session:
            latest = session.scalars(
                select(PromptTemplate)
                .where(PromptTemplate.key == key)
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            ).first()
            row = PromptTemplate(
                key=key,
                name=name if name is not None else (latest.name if latest else fallback.name),
                version=(latest.version + 1) if latest else 1,
                content=content,
                variables=(
                    list(variables)
                    if variables is not None
                    else (list(latest.variables) if latest else list(fallback.variables))
                ),
                description=(
                    description
                    if description is not None
                    else (latest.description if latest else fallback.description)
                ),
                is_active=True,
            )
            session.add(row)
            session.flush()
        logger.info("prompt_override_saved", key=key, version=row.version)
        return row

    def resolve(self, key: str) -> PromptSpec:
        """Return the database row if present, otherwise the built-in."""
        fallback = PROMPTS_BY_KEY.get(key)
        if fallback is None:
            raise KeyError(key)
        with self.db.session() as session:
            rows = list(
                session.scalars(
                    select(PromptTemplate)
                    .where(PromptTemplate.key == key, PromptTemplate.is_active.is_(True))
                    .order_by(PromptTemplate.version.desc())
                )
            )
        if not rows:
            return fallback
        row = rows[0]
        system, user = self._split(row.content, fallback)
        return PromptSpec(
            key=row.key,
            name=row.name,
            operation=fallback.operation,
            system=system,
            user=user,
            variables=tuple(row.variables) or fallback.variables,
            description=row.description or fallback.description,
        )

    def render_for(
        self, operation: str, variables: dict[str, str]
    ) -> tuple[list[dict[str, str]], str, list[str]]:
        """Render one operation into chat messages.

        Returns ``(messages, prompt_key, missing_variables)``.
        """
        key = OPERATIONS.get(operation)
        if key is None:
            raise KeyError(operation)
        spec = self.resolve(key)

        system_text, system_missing = render(spec.system, variables)
        user_text, user_missing = render(spec.user, variables)
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        return messages, key, sorted(set(system_missing + user_missing))

    def key_for(self, operation: str) -> str:
        key = OPERATIONS.get(operation)
        if key is None:
            raise KeyError(operation)
        return key
