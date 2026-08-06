from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.auth import password_hash
from cue.models import AuditEvent, Collection, CollectionVersion, Role, User, UserRole


def write_audit(
    session: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    detail: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            detail_json=json.dumps(detail or {}, sort_keys=True),
        )
    )


def create_admin(session: Session, username: str, password: str) -> User:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("Username must not be empty")
    if session.scalar(select(User).where(User.username == normalized_username)):
        raise ValueError("Username already exists")
    role = session.scalar(select(Role).where(Role.name == "administrator"))
    if role is None:
        role = Role(name="administrator")
        session.add(role)
        session.flush()
    user = User(username=normalized_username, password_hash=password_hash.hash(password))
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    write_audit(
        session,
        actor_id=user.id,
        action="user.bootstrap_created",
        entity_type="user",
        entity_id=user.id,
        detail={"username": user.username},
    )
    return user


def bootstrap_admin(session: Session, username: str | None, password: str | None) -> None:
    if not username or not password or session.scalar(select(User.id).limit(1)) is not None:
        return
    create_admin(session, username, password)
    session.commit()


def create_collection(session: Session, owner: User, name: str, recipe: dict[str, object]) -> Collection:
    collection = Collection(owner_id=owner.id, name=name.strip())
    session.add(collection)
    session.flush()
    session.add(
        CollectionVersion(
            collection_id=collection.id,
            version=1,
            recipe_json=json.dumps(recipe, sort_keys=True),
            created_by_id=owner.id,
        )
    )
    write_audit(
        session,
        actor_id=owner.id,
        action="collection.created",
        entity_type="collection",
        entity_id=collection.id,
        detail={"name": collection.name},
    )
    return collection


def revoke_token(session: Session, token_id: int, actor: User) -> bool:
    from cue.models import ApiToken

    token = session.get(ApiToken, token_id)
    if token is None or token.user_id != actor.id or token.revoked_at is not None:
        return False
    token.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    write_audit(
        session,
        actor_id=actor.id,
        action="token.revoked",
        entity_type="api_token",
        entity_id=token.id,
    )
    return True
