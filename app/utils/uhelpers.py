def to_json_sqla(instance):
    """Convert SQLAlchemy object into JSON"""

    data = {}
    columns = list(instance.__table__.columns)
    for column in columns:
        data[column.name] = instance.__dict__[column.name]
    return data
