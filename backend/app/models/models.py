import uuid
from datetime import datetime, date as date_type
from typing import Optional, List
from sqlalchemy import (
    String, Integer, SmallInteger, Boolean, Date, DateTime, ForeignKey, Enum,
    UniqueConstraint, CheckConstraint, text
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    technician = "technician"
    farm = "farm"
    vet = "vet"


class CowStatus(str, enum.Enum):
    calf = "calf"
    heifer = "heifer"
    fresh = "fresh"
    open = "open"
    needling = "needling"
    inseminated = "inseminated"
    pregnant = "pregnant"
    dry = "dry"
    cull = "cull"
    sold = "sold"
    dead = "dead"


class SemenType(str, enum.Enum):
    sexed = "sexed"
    conventional = "conventional"
    beef = "beef"


class ProtocolType(str, enum.Enum):
    ovsynch = "ovsynch"
    prostaglandin_heat = "prostaglandin_heat"
    double_ovsynch = "double_ovsynch"
    presynch = "presynch"
    general_synch = "general_synch"
    general_synch_2 = "general_synch_2"


class EnrollmentStatus(str, enum.Enum):
    active = "active"
    # Final (AI-day) needling record completed — cow awaits insemination on the
    # Timed Breeding report before the enrollment is marked fully completed.
    completed_pending_ai = "completed_pending_ai"
    completed = "completed"
    cancelled = "cancelled"


class PregnancyResult(str, enum.Enum):
    pregnant = "pregnant"
    not_pregnant = "not_pregnant"


class CalfSex(str, enum.Enum):
    male = "male"
    female = "female"


class HealthStatus(str, enum.Enum):
    healthy = "healthy"
    sick = "sick"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String)
    employee_id: Mapped[Optional[str]] = mapped_column(String)
    region: Mapped[Optional[str]] = mapped_column(String)
    farm_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"))
    # Signup is open, so a new account is inert until an admin turns it on.
    # It can read its own profile (to be told it is waiting) and nothing else.
    # Defaults true so admin-created and pre-existing accounts are unaffected —
    # only POST /users/me writes false. See migration 0013.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    farm: Mapped[Optional["Farm"]] = relationship("Farm", foreign_keys=[farm_id], back_populates="farm_users")


class Farm(Base):
    __tablename__ = "farms"
    __table_args__ = (CheckConstraint("herd_size >= 0", name="ck_farms_herd_size_non_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[Optional[str]] = mapped_column(String)
    province: Mapped[Optional[str]] = mapped_column(String)
    postal_code: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    # Owner-reported herd size — NOT the same as the computed cow_count exposed in FarmOut.
    herd_size: Mapped[int] = mapped_column(Integer, default=0)
    assigned_technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # Which weekdays this farm is visited (Mon=0 … Sun=6), per the client:
    # a "5-day farm" is Mon–Fri, a "6-day farm" is Mon–Sat. Sunday is the day
    # off in both. Stored as the actual day set rather than a count, so a farm
    # on an irregular pattern (e.g. Mon/Thu only) needs no schema change.
    visit_weekdays: Mapped[List[int]] = mapped_column(
        ARRAY(SmallInteger), nullable=False,
        server_default=text("'{0,1,2,3,4,5}'::smallint[]"),
    )
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cows: Mapped[List["Cow"]] = relationship("Cow", back_populates="farm", foreign_keys="Cow.farm_id")
    farm_users: Mapped[List["User"]] = relationship("User", foreign_keys="User.farm_id", back_populates="farm")
    vet_assignments: Mapped[List["VetFarmAssignment"]] = relationship("VetFarmAssignment", back_populates="farm")
    visit_assignments: Mapped[List["FarmVisitAssignment"]] = relationship(
        "FarmVisitAssignment", back_populates="farm", cascade="all, delete-orphan"
    )


class Vet(Base):
    __tablename__ = "vets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    clinic: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    farm_assignments: Mapped[List["VetFarmAssignment"]] = relationship("VetFarmAssignment", back_populates="vet")


class VetFarmAssignment(Base):
    __tablename__ = "vet_farm_assignments"

    vet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vets.id"), primary_key=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), primary_key=True)

    vet: Mapped["Vet"] = relationship("Vet", back_populates="farm_assignments")
    farm: Mapped["Farm"] = relationship("Farm", back_populates="vet_assignments")


class FarmVisitAssignment(Base):
    """A one-day override of who visits a farm.

    The schedule (farm.visit_weekdays) says WHEN a farm is due; this says
    WHO covers it on a given date when that differs from the standing assignment
    — a relief technician, or another technician picking the day up. Absence of
    a row means the standing `farms.assigned_technician_id` applies.
    """

    __tablename__ = "farm_visit_assignments"
    __table_args__ = (UniqueConstraint("farm_id", "visit_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    visit_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # Who is covering. NULL means the visit is explicitly skipped that day.
    assigned_technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    reason: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    farm: Mapped["Farm"] = relationship("Farm", back_populates="visit_assignments")


class Bull(Base):
    """A bull on a farm's semen list.

    Per-farm, not global: the spec says the cow is inseminated "with semen
    selected by farmer", and semen is bought and held by the farm. Full
    inventory tracking is listed as a future enhancement, so this is only the
    pick list — no straw counts.

    Recording an insemination still accepts a free-text bull name, so a straw
    that is not on the list never blocks the technician mid-visit.
    """

    __tablename__ = "bulls"
    __table_args__ = (UniqueConstraint("farm_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Industry/stud code, e.g. "7HO14454"
    code: Mapped[Optional[str]] = mapped_column(String)
    semen_type: Mapped[Optional[SemenType]] = mapped_column(Enum(SemenType, name="semen_type"))
    # Retired bulls stay for history but drop off the picker.
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Cow(Base):
    __tablename__ = "cows"
    __table_args__ = (
        UniqueConstraint("farm_id", "ear_tag"),
        CheckConstraint("lactation_number >= 0", name="ck_cows_lactation_number_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ear_tag: Mapped[str] = mapped_column(String, nullable=False)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=False)
    breed: Mapped[Optional[str]] = mapped_column(String)
    date_of_birth: Mapped[Optional[date_type]] = mapped_column(Date)
    sex: Mapped[CalfSex] = mapped_column(Enum(CalfSex, name="calf_sex"), nullable=False, default=CalfSex.female)
    lactation_number: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[CowStatus] = mapped_column(Enum(CowStatus, name="cow_status"), nullable=False, default=CowStatus.calf)
    health_status: Mapped[Optional[HealthStatus]] = mapped_column(
        Enum(HealthStatus, name="health_status"), default=HealthStatus.healthy
    )
    # Set to today+7 when a cow is marked sick; cleared when marked healthy.
    recheck_due_date: Mapped[Optional[date_type]] = mapped_column(Date)
    current_program: Mapped[Optional[str]] = mapped_column(String)
    last_calving_date: Mapped[Optional[date_type]] = mapped_column(Date)
    last_insemination_date: Mapped[Optional[date_type]] = mapped_column(Date)
    last_insemination_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("inseminations.id"))
    due_date: Mapped[Optional[date_type]] = mapped_column(Date)
    dry_date: Mapped[Optional[date_type]] = mapped_column(Date)
    # Set when the technician confirms she was physically moved to the dry pen.
    # The Dry Report is work until this is recorded, then she drops off it.
    dry_off_confirmed_date: Mapped[Optional[date_type]] = mapped_column(Date)
    # Set when the cow leaves the herd (sold / dead)
    exit_date: Mapped[Optional[date_type]] = mapped_column(Date)
    exit_reason: Mapped[Optional[str]] = mapped_column(String)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    farm: Mapped["Farm"] = relationship("Farm", back_populates="cows", foreign_keys=[farm_id])
    inseminations: Mapped[List["Insemination"]] = relationship(
        "Insemination", back_populates="cow", foreign_keys="Insemination.cow_id"
    )
    needling_enrollments: Mapped[List["NeedlingEnrollment"]] = relationship("NeedlingEnrollment", back_populates="cow")
    heat_checks: Mapped[List["HeatCheck"]] = relationship("HeatCheck", back_populates="cow")
    pregnancy_checks: Mapped[List["PregnancyCheck"]] = relationship("PregnancyCheck", back_populates="cow")
    calving_records: Mapped[List["CalvingRecord"]] = relationship(
        "CalvingRecord", back_populates="cow", foreign_keys="CalvingRecord.cow_id"
    )
    vaccination_records: Mapped[List["VaccinationRecord"]] = relationship("VaccinationRecord", back_populates="cow")
    cull_records: Mapped[List["CullRecord"]] = relationship("CullRecord", back_populates="cow")


class Insemination(Base):
    __tablename__ = "inseminations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # Full date+time the insemination was performed (date column keeps the farm-local date).
    inseminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # bull_name is kept as the recorded text (and for straws off the list);
    # bull_id links to the farm's list when the technician picked from it.
    bull_name: Mapped[Optional[str]] = mapped_column(String)
    bull_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("bulls.id"))
    dose_id: Mapped[Optional[str]] = mapped_column(String)
    # "Insemination Code" (Programs.md). The spec gives no format, so it is a
    # free-text reference the technician records alongside the dose.
    insemination_code: Mapped[Optional[str]] = mapped_column(String)
    semen_type: Mapped[Optional[SemenType]] = mapped_column(Enum(SemenType, name="semen_type"))
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="inseminations", foreign_keys=[cow_id])
    heat_checks: Mapped[List["HeatCheck"]] = relationship("HeatCheck", back_populates="insemination")
    pregnancy_checks: Mapped[List["PregnancyCheck"]] = relationship("PregnancyCheck", back_populates="insemination")


class NeedlingEnrollment(Base):
    __tablename__ = "needling_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    protocol: Mapped[ProtocolType] = mapped_column(Enum(ProtocolType, name="protocol_type"), nullable=False)
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    current_day: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus, name="enrollment_status"), default=EnrollmentStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="needling_enrollments")
    records: Mapped[List["NeedlingRecord"]] = relationship("NeedlingRecord", back_populates="enrollment")


class NeedlingRecord(Base):
    __tablename__ = "needling_records"
    __table_args__ = (CheckConstraint("protocol_day > 0", name="ck_needling_records_day_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("needling_enrollments.id"), nullable=False)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    protocol_day: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    completed_date: Mapped[Optional[date_type]] = mapped_column(Date)
    treatment: Mapped[str] = mapped_column(String, nullable=False)
    # True on the protocol's final (AI) day record
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    bleeding_event: Mapped[bool] = mapped_column(Boolean, default=False)
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    enrollment: Mapped["NeedlingEnrollment"] = relationship("NeedlingEnrollment", back_populates="records")


class HeatCheck(Base):
    __tablename__ = "heat_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    insemination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inseminations.id"), nullable=False)
    check_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    days_since_insemination: Mapped[int] = mapped_column(Integer, nullable=False)
    heat_detected: Mapped[Optional[bool]] = mapped_column(Boolean)
    bleeding_event: Mapped[bool] = mapped_column(Boolean, default=False)
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="heat_checks")
    insemination: Mapped["Insemination"] = relationship("Insemination", back_populates="heat_checks")


class PregnancyCheck(Base):
    __tablename__ = "pregnancy_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    insemination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inseminations.id"), nullable=False)
    check_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # Only set when the acting user is a vet
    vet_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # Always the acting (authenticated) user
    performed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    result: Mapped[Optional[PregnancyResult]] = mapped_column(Enum(PregnancyResult, name="pregnancy_result"))
    has_infection: Mapped[bool] = mapped_column(Boolean, default=False)
    has_cysts: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="pregnancy_checks")
    insemination: Mapped["Insemination"] = relationship("Insemination", back_populates="pregnancy_checks")


class CalvingRecord(Base):
    __tablename__ = "calving_records"
    __table_args__ = (
        CheckConstraint("live_birth <> still_birth", name="ck_calving_live_still_exclusive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    calving_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    live_birth: Mapped[bool] = mapped_column(Boolean, default=True)
    still_birth: Mapped[bool] = mapped_column(Boolean, default=False)
    calf_sex: Mapped[Optional[CalfSex]] = mapped_column(Enum(CalfSex, name="calf_sex"))
    calf_ear_tag: Mapped[Optional[str]] = mapped_column(String)
    # For male calves (no herd Cow record) — sale/outcome details
    calf_sale_info: Mapped[Optional[str]] = mapped_column(String)
    calf_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"))
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="calving_records", foreign_keys=[cow_id])
    vaccination_records: Mapped[List["VaccinationRecord"]] = relationship("VaccinationRecord", back_populates="calving_record")


class VaccinationRecord(Base):
    __tablename__ = "vaccination_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    calving_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("calving_records.id"))
    scheduled_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    completed_date: Mapped[Optional[date_type]] = mapped_column(Date)
    # Full date+time the vaccine was administered
    administered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    vaccine_name: Mapped[Optional[str]] = mapped_column(String)
    lot_number: Mapped[Optional[str]] = mapped_column(String)
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="vaccination_records")
    calving_record: Mapped[Optional["CalvingRecord"]] = relationship("CalvingRecord", back_populates="vaccination_records")


class CullRecord(Base):
    __tablename__ = "cull_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"), nullable=False)
    cull_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String)
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    cow: Mapped["Cow"] = relationship("Cow", back_populates="cull_records")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=False)
    cow_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cows.id"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    # Legacy farm-wide flag. Read state is per reader now (NotificationRead);
    # this column is no longer written or trusted. See migration 0011.
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Did the farmer's email actually go out? sent | failed | no_email | disabled.
    # Written by the background sender after the fact, so a silent delivery
    # failure is auditable instead of living only in a log line.
    email_status: Mapped[Optional[str]] = mapped_column(String)
    emailed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    email_error: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class NotificationRead(Base):
    """One row per (notification, reader).

    A notification is addressed to a farm and several people can see it, so
    "read" is a fact about a reader, not about the notification. Absence of a
    row means unread.
    """

    __tablename__ = "notification_reads"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
