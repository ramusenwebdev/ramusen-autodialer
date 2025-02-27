from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, create_engine, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base, backref
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100))
    channel_account = Column(Text)
    def __init__(self, username, channel_account):
        self.username = username
        self.channel_account = channel_account

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    guard_name = Column(String(255))
    def __init__(self, name, guard_name):
        self.name = name
        self.guard_name = guard_name

class RoleUser(Base):
    __tablename__ = "model_has_roles"

    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)  # Set as part of composite PK
    model_id = Column(Integer, ForeignKey("users.id"), primary_key=True)  # Set as part of composite PK

    def __init__(self, role_id, model_id):
        self.role_id = role_id
        self.model_id = model_id

class AutoDialerCampaign(Base):
    __tablename__ = "autodialers"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    provider = Column(String(255))
    no_provider = Column(Integer)
    channel_group = Column(String(255))
    status = Column(String(255))
    contacts = relationship(
        "AutoDialerContact", backref=backref("campaign", lazy=True)
    )

    def __init__(self, name, start_date, end_date, provider, no_provider, channel_group, status):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.provider = provider
        self.no_provider = no_provider
        self.channel_group = channel_group
        self.status = status


class AutoDialerContact(Base):
    __tablename__ = "autodialer_contacts"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("autodialers.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    duration = Column(Integer)
    call_result = Column(String(255))
    last_contacted = Column(DateTime)
    contact_status = Column(String(255))
    number_of_attempts = Column(Integer)
    tele_id =  Column(Integer, ForeignKey("users.id"))
    def __init__(self, customer_id, last_contacted, contact_status, number_of_attempts, campaign_id):
        self.customer_id = customer_id
        self.last_contacted = last_contacted
        self.contact_status = contact_status
        self.number_of_attempts = number_of_attempts
        self.campaign_id = campaign_id


class RanablastCampaign(Base):
    __tablename__ = "ranablasts"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    provider = Column(String(255))
    no_provider = Column(Integer)
    status = Column(String(255))
    contacts = relationship(
        "RanablastContact", backref=backref("campaign", lazy=True)
    )

    def __init__(self, name, start_date, end_date, provider, no_provider, status):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.provider = provider
        self.no_provider = no_provider
        self.status = status


class RanablastContact(Base):
    __tablename__ = "ranablast_contacts"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("ranablasts.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    duration = Column(Integer)
    call_result = Column(String(255))
    last_contacted = Column(DateTime)
    contact_status = Column(String(255))
    number_of_attempts = Column(Integer)
    def __init__(self, customer_id, last_contacted, contact_status, number_of_attempts, campaign_id):
        self.customer_id = customer_id
        self.last_contacted = last_contacted
        self.contact_status = contact_status
        self.number_of_attempts = number_of_attempts
        self.campaign_id = campaign_id

class CustomerSheet(Base):
    __tablename__ = "customer_sheets"
    id = Column(Integer, primary_key=True)
    sheet_name = Column(String(150))

    def __init__(self, sheet_name):
        self.sheet_name = sheet_name

class CustomerCall(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    sheet_id = Column(Integer, ForeignKey("customer_sheets.id"))
    name = Column(String(150))
    dob = Column(String(100))
    hp = Column(String(100))
    company_name = Column(String(300))
    credit_card1 = Column(Integer)
    credit_card2 = Column(Integer)
    limit_cc = Column(Integer)
    status = Column(String(255))

    the_customer_name5 = relationship(
        "AutoDialerContact", backref=backref("CustomerCall5", lazy=True)
    )

    the_customer_name6 = relationship(
        "RanablastContact", backref=backref("CustomerCall6", lazy=True)
    )

    def __init__(self, sheet_id, name, dob, hp, company_name, credit_card1, credit_card2, limit_cc, status):
        self.sheet_id = sheet_id
        self.name = name
        self.dob = dob
        self.hp = hp
        self.company_name = company_name
        self.credit_card1 = credit_card1
        self.credit_card2 = credit_card2
        self.limit_cc = limit_cc
        self.status = status


class StatusCall(Base):
    __tablename__ = "status_calls"
    id = Column(Integer, primary_key=True)
    name = Column(String(15))
    color = Column(String(250))
    icon = Column(String(250))

    def __init__(self, name, color, icon):
        self.name = name
        self.color = color
        self.icon = icon

class StatusApplication(Base):
    __tablename__ = "status_applications"
    id = Column(Integer, primary_key=True)
    name = Column(String(15))
    color = Column(String(250))
    icon = Column(String(250))

    def __init__(self, name, color, icon):
        self.name = name
        self.color = color
        self.icon = icon

class TaskTele(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    status_call_id = Column(Integer, ForeignKey("status_calls.id"))
    status_application_id = Column(Integer, ForeignKey("status_applications.id"))
    batch_processed_at = Column(DateTime)
    loan = Column(Integer, default=0)
    notes = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    def __init__(self, user_id, customer_id, status_call_id, status_application_id, batch_processed_at, loan, notes, created_at, updated_at):
        self.user_id = user_id
        self.customer_id = customer_id
        self.status_call_id = status_call_id
        self.status_application_id = status_application_id
        self.batch_processed_at = batch_processed_at
        self.loan = loan
        self.notes = notes
        self.created_at = created_at
        self.updated_at = updated_at

