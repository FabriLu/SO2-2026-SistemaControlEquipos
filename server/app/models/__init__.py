from datetime import datetime, timezone
from uuid import uuid4

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from server.app import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    hostname = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    os_version = db.Column(db.String(120), nullable=True)
    agent_version = db.Column(db.String(40), nullable=True)
    last_seen = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    lock_status = db.Column(db.String(24), nullable=False, default="unknown")
    cpu_percent = db.Column(db.Float, nullable=True)
    ram_percent = db.Column(db.Float, nullable=True)
    disk_percent = db.Column(db.Float, nullable=True)
    proxmox_vmid = db.Column(db.Integer, nullable=True)
    proxmox_node = db.Column(db.String(64), nullable=True, default="pve")
    last_screenshot_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    credentials = db.relationship("AgentCredential", back_populates="device", cascade="all, delete-orphan")
    commands = db.relationship("Command", back_populates="device", cascade="all, delete-orphan", lazy="dynamic")

    def connection_status(self, timeout_seconds):
        if self.last_seen is None:
            return "disconnected"
        seen = self.last_seen
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = (utcnow() - seen).total_seconds()
        return "connected" if age <= timeout_seconds else "disconnected"

    def to_dict(self, timeout_seconds):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "os_version": self.os_version,
            "agent_version": self.agent_version,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "connection_status": self.connection_status(timeout_seconds),
            "lock_status": self.lock_status,
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "disk_percent": self.disk_percent,
            "proxmox_vmid": self.proxmox_vmid,
            "proxmox_node": self.proxmox_node,
            "last_screenshot_at": self.last_screenshot_at.isoformat() if self.last_screenshot_at else None,
            "has_screenshot": self.last_screenshot_at is not None,
            "screenshot_url": f"/api/admin/devices/{self.id}/screenshot" if self.last_screenshot_at else None,
        }


class AgentCredential(db.Model):
    __tablename__ = "agent_credentials"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    device = db.relationship("Device", back_populates="credentials")


class Command(db.Model):
    __tablename__ = "commands"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    type = db.Column(db.String(40), nullable=False)  # lock, unlock, message, shutdown, reboot
    payload = db.Column(db.JSON, nullable=True)  # e.g. {"message": "..."}
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending, delivered, completed, failed
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    result_code = db.Column(db.String(80), nullable=True)
    result_message = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    idempotency_key = db.Column(db.String(80), unique=True, nullable=True)

    device = db.relationship("Device", back_populates="commands")

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "type": self.type,
            "payload": self.payload or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result_code": self.result_code,
            "result_message": self.result_message,
        }


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    command_id = db.Column(db.String(36), db.ForeignKey("commands.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
