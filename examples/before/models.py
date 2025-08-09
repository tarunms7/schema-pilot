from sqlalchemy import Column, Integer, BigInteger, Text, Numeric, ForeignKey, DateTime, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)