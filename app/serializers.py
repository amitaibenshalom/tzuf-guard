from datetime import timezone

from app.device_state import door_is_online


def isoformat(value):
    if value is None:
        return None
    # SQLite-compatible drivers may return a naive value even for a timezone
    # column. Stored application timestamps are UTC, so make that explicit for
    # browsers before they convert to the viewer's local timezone.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def user_to_dict(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_at": isoformat(user.created_at),
        "updated_at": isoformat(user.updated_at),
    }


def door_to_dict(door, include_events=False, events=None, viewer=None):
    viewer_id = getattr(viewer, "id", viewer)
    membership = None
    if viewer_id is not None and door.user_id != viewer_id:
        membership = next(
            (item for item in door.memberships if item.user_id == viewer_id),
            None,
        )
    data = {
        "id": door.id,
        "name": door.name,
        "location": door.location,
        "last_status": door.last_status,
        "status_changed_at": isoformat(door.status_changed_at),
        "last_seen_at": isoformat(door.last_seen_at),
        "last_heartbeat_at": isoformat(door.last_heartbeat_at),
        "is_online": door_is_online(door),
        "offline_since": isoformat(door.offline_since),
        "device_name": door.device_name,
        "firmware_version": door.firmware_version,
        "firmware_update_requested_at": isoformat(door.firmware_update_requested_at),
        "firmware_update_target_version": door.firmware_update_target_version,
        "notifications_enabled": membership.notifications_enabled if membership else door.notifications_enabled,
        "is_pinned": membership.is_pinned if membership else door.is_pinned,
        "left_open_minutes": membership.left_open_minutes if membership else door.left_open_minutes,
        "access_role": "member" if membership else "owner",
        "member_count": len(door.memberships),
        "created_at": isoformat(door.created_at),
        "updated_at": isoformat(door.updated_at),
    }
    if events is not None:
        data["events"] = [door_event_to_dict(event) for event in events]
    elif include_events:
        data["events"] = [door_event_to_dict(event) for event in door.events]
    return data


def door_membership_to_dict(membership):
    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "name": membership.user.name,
        "email": membership.user.email,
        "notifications_enabled": membership.notifications_enabled,
        "is_pinned": membership.is_pinned,
        "joined_at": isoformat(membership.created_at),
    }


def door_invitation_to_dict(invitation):
    return {
        "id": invitation.id,
        "email": invitation.email,
        "inviter_name": invitation.invited_by.name or invitation.invited_by.email,
        "created_at": isoformat(invitation.created_at),
        "expires_at": isoformat(invitation.expires_at),
    }


def door_event_to_dict(event):
    return {
        "id": event.id,
        "door_id": event.door_id,
        "status": event.status,
        "device_name": event.device_name,
        "received_at": isoformat(event.received_at),
    }


def push_device_to_dict(push_device):
    return {
        "id": push_device.id,
        "platform": push_device.platform,
        "push_token": push_device.push_token,
        "created_at": isoformat(push_device.created_at),
        "updated_at": isoformat(push_device.updated_at),
    }
