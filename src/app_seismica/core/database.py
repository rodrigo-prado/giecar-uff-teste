from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import datetime

Base = declarative_base()

class DBDataset(Base):
    __tablename__ = 'datasets'
    
    id = Column(String, primary_key=True)
    name = Column(String)
    source_path = Column(String)
    n_inlines = Column(Integer)
    n_crosslines = Column(Integer)
    n_samples = Column(Integer)
    sample_rate_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    jobs = relationship("DBJob", back_populates="dataset")

class DBJob(Base):
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String, ForeignKey('datasets.id'))
    cutoff_hz = Column(Float)
    order = Column(Integer)
    n_workers = Column(Integer, default=1)
    status = Column(String)
    output_path = Column(String, nullable=True)
    duration_sec = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    dataset = relationship("DBDataset", back_populates="jobs")

def init_db(db_path="sqlite:///metadata.db"):
    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal
