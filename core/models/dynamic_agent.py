from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, func

from models.base import Base


class DynamicAgent(Base):
    """
    ডাইনামিক এজেন্ট রেজিস্ট্রি মডেল।
    এআই দ্বারা জেনারেট করা ফ্রি লোকাল এজেন্টগুলোর কনফিগারেশন আজীবনের জন্য এখানে সেভ করা থাকবে।
    """

    __tablename__ = "dynamic_agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(500), nullable=True)
    execution_steps = Column(JSON, nullable=False)  # প্লেরাইট স্ক্রিপ্ট বা কনফিগারেশন স্টেপস
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
