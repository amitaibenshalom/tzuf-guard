def isoformat(value):
    return value.isoformat() if value else None


def user_to_dict(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_at": isoformat(user.created_at),
        "updated_at": isoformat(user.updated_at),
    }


def door_to_dict(door, include_events=False):
    data = {
        "id": door.id,
        "name": door.name,
        "location": door.location,
        "last_status": door.last_status,
        "last_seen_at": isoformat(door.last_seen_at),
        "battery_mv": door.battery_mv,
        "device_name": door.device_name,
        "created_at": isoformat(door.created_at),
        "updated_at": isoformat(door.updated_at),
    }
    if include_events:
        data["events"] = [door_event_to_dict(event) for event in door.events]
    return data


def door_event_to_dict(event):
    return {
        "id": event.id,
        "door_id": event.door_id,
        "status": event.status,
        "battery_mv": event.battery_mv,
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
