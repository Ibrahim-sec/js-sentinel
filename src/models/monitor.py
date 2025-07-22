from datetime import datetime
from src.database import db

class MonitoredUrl(db.Model):
    __tablename__ = 'monitored_urls'
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False, unique=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime)
    last_hash = db.Column(db.String(32))  # MD5 hash of last content
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'active': self.active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'last_hash': self.last_hash
        }

class DiffFile(db.Model):
    __tablename__ = 'diff_files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    url_id = db.Column(db.Integer, db.ForeignKey('monitored_urls.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # Added created_at field
    file_size = db.Column(db.Integer)
    preview = db.Column(db.Text)  # First few lines of the diff for preview
    
    # Relationship
    url = db.relationship('MonitoredUrl', backref=db.backref('diffs', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_path': self.file_path,
            'url_id': self.url_id,
            'url': self.url.url if self.url else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'file_size': self.file_size,
            'preview': self.preview
        }


