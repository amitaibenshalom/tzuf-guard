from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import DoorInvitation, DoorMembership, User, utcnow
from app.security import generate_secure_token, hash_reset_token, normalize_email
from app.serializers import door_invitation_to_dict, door_membership_to_dict
from app.services.email import email_service
from app.validation import email_field, require_json, string_field
from .common import current_user_required, get_door_access_or_404, require_door_owner

sharing_bp = Blueprint("sharing", __name__)


def invitation_is_pending(invitation, now=None):
    now = now or utcnow()
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return (
        invitation.accepted_at is None
        and invitation.declined_at is None
        and invitation.revoked_at is None
        and expires_at > now
    )


def get_invitation_or_404(invitation_id):
    invitation = db.session.get(DoorInvitation, invitation_id)
    if invitation is None:
        raise ApiError("Invitation was not found or has expired.", 404, "invitation_not_found")
    return invitation


def accept_invitation(invitation, current_user):
    if normalize_email(current_user.email) != invitation.email:
        raise ApiError(
            "Sign in with the email address this invitation was sent to.",
            403,
            "invitation_email_mismatch",
        )
    if invitation.door.user_id == current_user.id:
        raise ApiError("You already own this door.", 409, "already_door_owner")

    membership = DoorMembership.query.filter_by(
        door_id=invitation.door_id,
        user_id=current_user.id,
    ).first()
    if membership is not None:
        invitation.accepted_at = invitation.accepted_at or utcnow()
        db.session.commit()
        return membership
    if not invitation_is_pending(invitation):
        raise ApiError("This invitation has expired or is no longer active.", 410, "invitation_expired")

    membership = DoorMembership(door_id=invitation.door_id, user_id=current_user.id)
    invitation.accepted_at = utcnow()
    db.session.add(membership)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError("This invitation could not be accepted.", 409, "invitation_conflict") from exc
    return membership


@sharing_bp.get("/invitations/preview")
def preview_invitation():
    raw_token = string_field(request.args, "token", max_length=128)
    invitation = DoorInvitation.query.filter_by(
        token_hash=hash_reset_token(raw_token)
    ).first()
    if invitation is None or not invitation_is_pending(invitation):
        raise ApiError("This invitation has expired or is no longer active.", 410, "invitation_expired")

    return jsonify(
        {
            "invitation": {
                "id": invitation.id,
                "email": invitation.email,
                "door_name": invitation.door.name,
                "door_location": invitation.door.location,
                "inviter_name": invitation.invited_by.name or invitation.invited_by.email,
                "expires_at": invitation.expires_at.isoformat(),
            }
        }
    )


@sharing_bp.get("/invitations/pending")
@current_user_required
def list_pending_invitations(current_user):
    invitations = DoorInvitation.query.filter_by(
        email=normalize_email(current_user.email),
        accepted_at=None,
        declined_at=None,
        revoked_at=None,
    ).order_by(DoorInvitation.created_at.desc()).all()
    invitations = [item for item in invitations if invitation_is_pending(item)]
    return jsonify(
        {
            "invitations": [
                {
                    **door_invitation_to_dict(item),
                    "door_id": item.door_id,
                    "door_name": item.door.name,
                    "door_location": item.door.location,
                }
                for item in invitations
            ]
        }
    )


@sharing_bp.post("/invitations/accept")
@current_user_required
def accept_invitation_by_token(current_user):
    data = require_json(request)
    raw_token = string_field(data, "token", max_length=128)
    invitation = DoorInvitation.query.filter_by(
        token_hash=hash_reset_token(raw_token)
    ).first()
    if invitation is None:
        raise ApiError("Invitation was not found or has expired.", 404, "invitation_not_found")
    membership = accept_invitation(invitation, current_user)
    return jsonify({"message": "Invitation accepted.", "door_id": membership.door_id})


@sharing_bp.post("/invitations/<int:invitation_id>/accept")
@current_user_required
def accept_pending_invitation(current_user, invitation_id):
    invitation = get_invitation_or_404(invitation_id)
    membership = accept_invitation(invitation, current_user)
    return jsonify({"message": "Invitation accepted.", "door_id": membership.door_id})


@sharing_bp.post("/invitations/<int:invitation_id>/decline")
@current_user_required
def decline_invitation(current_user, invitation_id):
    invitation = get_invitation_or_404(invitation_id)
    if normalize_email(current_user.email) != invitation.email:
        raise ApiError("Invitation was not found.", 404, "invitation_not_found")
    if not invitation_is_pending(invitation):
        raise ApiError("This invitation is no longer active.", 410, "invitation_expired")
    invitation.declined_at = utcnow()
    db.session.commit()
    return jsonify({"message": "Invitation declined."})


@sharing_bp.get("/doors/<int:door_id>/sharing")
@current_user_required
def get_door_sharing(current_user, door_id):
    door, _membership = get_door_access_or_404(current_user, door_id)
    require_door_owner(current_user, door)
    invitations = [item for item in door.invitations if invitation_is_pending(item)]
    return jsonify(
        {
            "owner": {
                "id": door.user.id,
                "name": door.user.name,
                "email": door.user.email,
            },
            "members": [door_membership_to_dict(item) for item in door.memberships],
            "invitations": [door_invitation_to_dict(item) for item in invitations],
        }
    )


@sharing_bp.post("/doors/<int:door_id>/invitations")
@current_user_required
def create_door_invitation(current_user, door_id):
    door, _membership = get_door_access_or_404(current_user, door_id)
    require_door_owner(current_user, door)
    data = require_json(request)
    email = normalize_email(email_field(data))
    if email == normalize_email(current_user.email):
        raise ApiError("You already own this door.", 409, "already_door_owner")

    invited_user = User.query.filter_by(email=email).first()
    if invited_user and DoorMembership.query.filter_by(
        door_id=door.id,
        user_id=invited_user.id,
    ).first():
        raise ApiError("This person already has access to the door.", 409, "already_door_member")

    raw_token = generate_secure_token()
    now = utcnow()
    invitation = DoorInvitation.query.filter_by(door_id=door.id, email=email).first()
    if invitation is None:
        invitation = DoorInvitation(
            door_id=door.id,
            invited_by_user_id=current_user.id,
            email=email,
            token_hash=hash_reset_token(raw_token),
            expires_at=now + timedelta(days=current_app.config["DOOR_INVITATION_EXPIRES_DAYS"]),
        )
        db.session.add(invitation)
    else:
        invitation.invited_by_user_id = current_user.id
        invitation.token_hash = hash_reset_token(raw_token)
        invitation.expires_at = now + timedelta(days=current_app.config["DOOR_INVITATION_EXPIRES_DAYS"])
        invitation.accepted_at = None
        invitation.declined_at = None
        invitation.revoked_at = None
        invitation.created_at = now

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "An invitation for this email is already being created. Please try again.",
            409,
            "invitation_conflict",
        ) from exc

    try:
        email_sent = email_service.send_door_invitation(invitation, raw_token)
    except Exception:
        current_app.logger.exception("Door invitation email failed invitation_id=%s", invitation.id)
        email_sent = False

    email_queued = False
    if not email_sent:
        from app.services.background import queue_email_retry
        email_queued = queue_email_retry("invitation", invitation, raw_token)

    response = {
        "invitation": door_invitation_to_dict(invitation),
        "email_sent": email_sent,
        "email_delivery": "sent" if email_sent else "queued" if email_queued else "unavailable",
        "invitation_url": (
            f"{current_app.config['PUBLIC_APP_URL']}/invite?token={raw_token}"
        ),
    }
    return jsonify(response), 201


@sharing_bp.delete("/doors/<int:door_id>/invitations/<int:invitation_id>")
@current_user_required
def revoke_door_invitation(current_user, door_id, invitation_id):
    door, _membership = get_door_access_or_404(current_user, door_id)
    require_door_owner(current_user, door)
    invitation = DoorInvitation.query.filter_by(id=invitation_id, door_id=door.id).first()
    if invitation is None:
        raise ApiError("Invitation was not found.", 404, "invitation_not_found")
    if invitation.accepted_at is not None:
        raise ApiError("Accepted invitations are managed as members.", 409, "invitation_already_accepted")
    invitation.revoked_at = utcnow()
    db.session.commit()
    return jsonify({"message": "Invitation revoked."})


@sharing_bp.delete("/doors/<int:door_id>/members/<int:user_id>")
@current_user_required
def remove_door_member(current_user, door_id, user_id):
    door, _membership = get_door_access_or_404(current_user, door_id)
    require_door_owner(current_user, door)
    membership = DoorMembership.query.filter_by(door_id=door.id, user_id=user_id).first()
    if membership is None:
        raise ApiError("Door member was not found.", 404, "door_member_not_found")
    db.session.delete(membership)
    db.session.commit()
    return jsonify({"message": "Door access removed."})


@sharing_bp.delete("/doors/<int:door_id>/membership")
@current_user_required
def leave_shared_door(current_user, door_id):
    door, membership = get_door_access_or_404(current_user, door_id)
    if membership is None:
        raise ApiError("The door owner cannot leave their own door.", 409, "door_owner_cannot_leave")
    db.session.delete(membership)
    db.session.commit()
    return jsonify({"message": "You no longer have access to this door."})
