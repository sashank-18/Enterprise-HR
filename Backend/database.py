import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "hr_assistant")

# SQLAlchemy setup
Base = declarative_base()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")

import urllib.parse

def get_db_url(include_db=True):
    # Use PyMySQL driver
    quoted_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    pwd_part = f":{quoted_password}" if quoted_password else ""
    db_part = f"/{DB_NAME}" if include_db else ""
    return f"mysql+pymysql://{DB_USER}{pwd_part}@{DB_HOST}:{DB_PORT}{db_part}"

def create_database_if_not_exists():
    try:
        # Connect to server without specifying database name first
        engine_no_db = create_engine(get_db_url(include_db=False))
        with engine_no_db.connect() as conn:
            # Commit-as-you-go / execute with autocommit behavior for CREATE DATABASE
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))
            logger.info(f"Database '{DB_NAME}' verified/created.")
        engine_no_db.dispose()
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        # Note: If database doesn't exist and we can't create it, SQLAlchemy engine creation below will fail gracefully.

# Verify database exists
create_database_if_not_exists()

# Initialize Engine and Session
DATABASE_URL = get_db_url(include_db=True)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db_and_seed():
    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized.")

    # Run ALTER TABLE to add user and chat columns if they don't exist
    from sqlalchemy import text
    from datetime import datetime
    db = SessionLocal()
    try:
        user_cols = {
            "department": "VARCHAR(100) NULL",
            "designation": "VARCHAR(100) NULL",
            "employment_type": "VARCHAR(50) NULL",
            "location": "VARCHAR(100) NULL",
            "joining_date": "DATETIME NULL",
            "temp_password": "VARCHAR(255) NULL"
        }
        for col, col_type in user_cols.items():
            try:
                db.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
                db.commit()
                logger.info(f"Added column '{col}' to users table.")
            except Exception:
                db.rollback()

        chat_cols = {
            "confidence_score": "INT NULL",
            "confidence_level": "VARCHAR(50) NULL",
            "session_id": "VARCHAR(255) NULL",
            "session_name": "VARCHAR(255) NULL"
        }
        for col, col_type in chat_cols.items():
            try:
                db.execute(text(f"ALTER TABLE chat_history ADD COLUMN {col} {col_type}"))
                db.commit()
                logger.info(f"Added column '{col}' to chat_history table.")
            except Exception:
                db.rollback()

        # Migrate existing chats without a session_id into a single default session per user
        try:
            distinct_users = db.execute(text("SELECT DISTINCT user_id FROM chat_history WHERE session_id IS NULL")).all()
            if distinct_users:
                import uuid
                for (uid,) in distinct_users:
                    new_session_id = str(uuid.uuid4())
                    # Get their first question asked to formulate the session name
                    first_chat = db.execute(text(
                        "SELECT question FROM chat_history WHERE user_id = :uid AND session_id IS NULL ORDER BY timestamp ASC LIMIT 1"
                    ), {"uid": uid}).first()
                    session_name = first_chat[0][:40] if first_chat else "Previous Conversation"
                    
                    db.execute(text(
                        "UPDATE chat_history SET session_id = :sid, session_name = :sname WHERE user_id = :uid AND session_id IS NULL"
                    ), {"sid": new_session_id, "sname": session_name, "uid": uid})
                    db.commit()
                    logger.info(f"Migrated previous chats for user ID {uid} into default session '{session_name}' ({new_session_id})")
        except Exception as e:
            db.rollback()
            logger.error(f"Error migrating existing chats to sessions: {e}")

    except Exception as e:
        logger.error(f"Error migrating database columns: {e}")
        db.rollback()
    finally:
        db.close()

    # Seed Roles
    from .models import Role, User
    from .auth import get_password_hash

    db = SessionLocal()
    try:
        roles_to_seed = ["Admin", "HR Manager", "Employee"]
        db_roles = {}
        for r_name in roles_to_seed:
            role = db.query(Role).filter(Role.name == r_name).first()
            if not role:
                role = Role(name=r_name)
                db.add(role)
                db.flush()
                logger.info(f"Seeded role: {r_name}")
            db_roles[r_name] = role
        db.commit()

        # Delete all existing users with the "Employee" role to clean the database
        from .models import ChatHistory, Session as UserSession, TicketComment, Ticket, Document
        employee_role = db_roles.get("Employee")
        if employee_role:
            employees = db.query(User).filter(User.role_id == employee_role.id).all()
            for emp in employees:
                db.query(ChatHistory).filter(ChatHistory.user_id == emp.id).delete()
                db.query(UserSession).filter(UserSession.user_id == emp.id).delete()
                db.query(TicketComment).filter(TicketComment.commented_by == emp.id).delete()
                db.query(Ticket).filter(Ticket.user_id == emp.id).delete()
                db.query(Document).filter(Document.uploaded_by == emp.id).delete()
                db.delete(emp)
            db.commit()
            logger.info("Cleared all employee credentials from the database.")

        # Seed Users (username, email, password, role_name, dept, desig, emp_type, loc, join_date)
        users_to_seed = [
            ("admin", "admin@company.com", "admin123", "Admin", "IT", "System Administrator", "Full-Time", "New York", datetime(2020, 1, 1)),
            ("hr_manager", "hr@company.com", "hr_manager123", "HR Manager", "Human Resources", "HR Manager", "Full-Time", "San Francisco", datetime(2021, 6, 1)),
        ]

        for username, email, password, role_name, dept, desig, emp_type, loc, join_date in users_to_seed:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                hashed_pwd = get_password_hash(password)
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=hashed_pwd,
                    role_id=db_roles[role_name].id,
                    department=dept,
                    designation=desig,
                    employment_type=emp_type,
                    location=loc,
                    joining_date=join_date
                )
                db.add(new_user)
                logger.info(f"Seeded user: {username} (Role: {role_name})")
            else:
                # Update existing user profile details in case they are null
                user.department = dept
                user.designation = desig
                user.employment_type = emp_type
                user.location = loc
                user.joining_date = join_date
        db.commit()
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()
