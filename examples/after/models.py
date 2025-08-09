from sqlalchemy import Column, Integer, BigInteger, Text, Numeric, ForeignKey, DateTime, func
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.schema import ForeignKeyConstraint, CheckConstraint

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    # status = Column(Text, nullable=False, server_default="pending")
    # amount = Column(Numeric(12, 2), nullable=False, server_default="0")
    # __table_args__ = (
    #     ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_orders_user", ondelete="CASCADE"),
    #     CheckConstraint("amount >= 0", name="chk_orders_amount_pos"),
    # )