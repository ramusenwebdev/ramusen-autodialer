from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Koneksi ke database PostgreSQL
DATABASE_URL = "postgresql://postgres:Ramusendbadmin@172.16.203.21/ramusenDB"

# If your PostgreSQL database has a username and password, replace "root" and "password" accordingly.

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
