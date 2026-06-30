from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .models import User, Document, ChatHistory, Role, AuditLog

def get_dashboard_stats(db: Session) -> dict:
    """
    Computes summary KPI stats and chart data.
    """
    # 1. Total Documents
    total_docs = db.query(Document).count()

    # 2. Total Employees (Role = Employee)
    employee_role = db.query(Role).filter(Role.name == "Employee").first()
    total_employees = 0
    if employee_role:
        total_employees = db.query(User).filter(User.role_id == employee_role.id).count()
    else:
        total_employees = db.query(User).count()

    # 3. Total Queries
    total_queries = db.query(ChatHistory).count()

    # 4. Most Accessed Policy
    # We can infer the most accessed policy by counting doc_types or querying search history.
    # Let's count document types in documents table first, or audit log actions.
    most_accessed = "N/A"
    doc_type_counts = db.query(Document.doc_type, func.count(Document.id).label("cnt")) \
        .group_by(Document.doc_type) \
        .order_by(desc("cnt")) \
        .first()
    if doc_type_counts:
        most_accessed = doc_type_counts[0]

    # 5. Daily queries (Last 7 days)
    today = datetime.utcnow().date()
    daily_queries = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        count = db.query(ChatHistory).filter(ChatHistory.timestamp >= day_start, ChatHistory.timestamp <= day_end).count()
        daily_queries.append({
            "date": day.strftime("%b %d"),
            "count": count
        })

    # 6. Weekly queries (Last 4 weeks)
    weekly_queries = []
    for i in range(3, -1, -1):
        week_start = datetime.combine(today - timedelta(weeks=i+1), datetime.min.time())
        week_end = datetime.combine(today - timedelta(weeks=i), datetime.max.time())
        count = db.query(ChatHistory).filter(ChatHistory.timestamp >= week_start, ChatHistory.timestamp <= week_end).count()
        weekly_queries.append({
            "label": f"{4-i} weeks ago" if i > 0 else "This week",
            "count": count
        })

    # 7. Monthly queries (Last 6 months)
    monthly_queries = []
    current_month = datetime.utcnow().month
    for i in range(5, -1, -1):
        month_date = today - timedelta(days=i*30)
        # Approximate start and end of that month
        m_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            m_end = datetime(month_date.year + 1, 1, 1) - timedelta(seconds=1)
        else:
            m_end = datetime(month_date.year, month_date.month + 1, 1) - timedelta(seconds=1)
        
        count = db.query(ChatHistory).filter(ChatHistory.timestamp >= m_start, ChatHistory.timestamp <= m_end).count()
        monthly_queries.append({
            "month": m_start.strftime("%B"),
            "count": count
        })

    # 8. Document counts by category (for pie chart)
    category_counts = {}
    categories = db.query(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type).all()
    for cat, count in categories:
        category_counts[cat] = count

    # 9. Most Asked Questions (Top 5 based on keyword similarity or frequency)
    # Since questions might vary, we can just grab the 5 most recent questions as a fallback,
    # or simple frequency count of exact questions.
    most_asked = []
    common_questions = db.query(ChatHistory.question, func.count(ChatHistory.id).label("cnt")) \
        .group_by(ChatHistory.question) \
        .order_by(desc("cnt")) \
        .limit(5) \
        .all()
    for q, count in common_questions:
        most_asked.append({
            "question": q,
            "count": count
        })

    return {
        "kpi": {
            "total_documents": total_docs,
            "total_employees": total_employees,
            "total_queries": total_queries,
            "most_accessed_policy": most_accessed
        },
        "daily": daily_queries,
        "weekly": weekly_queries,
        "monthly": monthly_queries,
        "categories": category_counts,
        "most_asked": most_asked
    }
