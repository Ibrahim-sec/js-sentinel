from flask import Blueprint, jsonify, request, send_file
from src.database import db
from src.models.monitor import MonitoredUrl, DiffFile
from src.services.scheduler_service import scheduler_service
import os
import tempfile
import json
from datetime import datetime

monitor_bp = Blueprint('monitor', __name__)

@monitor_bp.route('/urls', methods=['GET'])
def get_urls():
    """Get all monitored URLs"""
    urls = MonitoredUrl.query.all()
    return jsonify([url.to_dict() for url in urls])

@monitor_bp.route('/urls', methods=['POST'])
def add_url():
    """Add a new URL to monitor"""
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'message': 'URL is required'}), 400
    
    # Check if URL already exists
    existing_url = MonitoredUrl.query.filter_by(url=url).first()
    if existing_url:
        return jsonify({'message': 'URL already exists'}), 400
    
    monitored_url = MonitoredUrl(url=url, active=True)
    db.session.add(monitored_url)
    db.session.commit()
    
    return jsonify(monitored_url.to_dict()), 201

@monitor_bp.route('/urls/<int:url_id>', methods=['DELETE'])
def remove_url(url_id):
    """Remove a monitored URL"""
    url = MonitoredUrl.query.get_or_404(url_id)
    db.session.delete(url)
    db.session.commit()
    return '', 204

@monitor_bp.route('/status/monitoring', methods=['GET'])
def get_monitoring_status():
    """Get current monitoring status"""
    try:
        # Check if scheduler jobs are active
        jobs = scheduler_service.get_jobs()
        monitoring_active = any(job.get('id') == 'monitor_urls' for job in jobs)
        
        # Get monitoring details
        monitor_job = next((job for job in jobs if job.get('id') == 'monitor_urls'), None)
        
        return jsonify({
            'monitoring_active': monitoring_active,
            'next_run_time': monitor_job.get('next_run_time') if monitor_job else None,
            'job_details': monitor_job
        })
    except Exception as e:
        return jsonify({
            'monitoring_active': False,
            'error': str(e)
        }), 500



# Add this route to your monitor.py file if it doesn't exist already

@monitor_bp.route('/urls/<int:url_id>/toggle', methods=['PUT'])
def toggle_url(url_id):
    """Toggle URL active status"""
    try:
        url = MonitoredUrl.query.get_or_404(url_id)
        url.active = not url.active
        db.session.commit()
        
        status = "activated" if url.active else "paused"
        monitor_logger.info(f"URL {url.url} {status}", extra={
            "url_id": url_id,
            "url": url.url,
            "active": url.active,
            "event_type": "url_toggled"
        })
        
        return jsonify({
            'id': url.id,
            'url': url.url,
            'active': url.active,
            'message': f'URL {status} successfully'
        })
    except Exception as e:
        monitor_logger.error(f"Failed to toggle URL {url_id}: {e}", extra={
            "url_id": url_id,
            "error": str(e),
            "event_type": "url_toggle_failed"
        })
        return jsonify({'message': f'Failed to toggle URL: {str(e)}'}), 500

@monitor_bp.route('/monitor/check', methods=['POST'])
def check_now():
    """Manually trigger monitoring check"""
    try:
        # Import the monitoring functions
        from src.services.monitor_service import run_monitoring_check
        
        result = run_monitoring_check()
        
        return jsonify({
            'message': result['message'],
            'changes_detected': result['changes_detected'],
            'urls_checked': result['urls_checked']
        })
    except Exception as e:
        return jsonify({'message': f'Monitoring check failed: {str(e)}'}), 500

@monitor_bp.route('/schedule/reset', methods=['POST'])
def reset_monitoring():
    """Reset monitoring scheduler - for debugging"""
    try:
        # Get all jobs
        jobs = scheduler_service.get_jobs()
        
        # Remove all monitoring-related jobs
        for job in jobs:
            if 'monitor' in job.get('id', '').lower():
                scheduler_service.remove_job(job['id'])
        
        return jsonify({'message': 'Monitoring scheduler reset successfully'})
    except Exception as e:
        return jsonify({'message': f'Failed to reset scheduler: {str(e)}'}), 500

@monitor_bp.route('/diffs', methods=['GET'])
def get_diffs():
    """Get all diff files"""
    diffs = DiffFile.query.order_by(DiffFile.created_at.desc()).all()
    return jsonify([diff.to_dict() for diff in diffs])

@monitor_bp.route('/diffs/<int:diff_id>', methods=['GET'])
def get_diff(diff_id):
    """Get a specific diff file"""
    diff = DiffFile.query.get_or_404(diff_id)
    
    if not os.path.exists(diff.file_path):
        return jsonify({'message': 'Diff file not found'}), 404
    
    return send_file(diff.file_path, as_attachment=True, download_name=diff.filename)

@monitor_bp.route('/diffs', methods=['DELETE'])
def clear_diffs():
    """Clear all diff files"""
    diffs = DiffFile.query.all()
    
    for diff in diffs:
        # Remove file from filesystem
        if os.path.exists(diff.file_path):
            os.remove(diff.file_path)
        # Remove from database
        db.session.delete(diff)
    
    db.session.commit()
    return jsonify({'message': 'All diffs cleared'})

@monitor_bp.route('/diffs/<int:diff_id>', methods=['DELETE'])
def delete_diff(diff_id):
    """Delete a specific diff file"""
    diff = DiffFile.query.get_or_404(diff_id)
    
    # Remove file from filesystem
    if os.path.exists(diff.file_path):
        os.remove(diff.file_path)
    
    # Remove from database
    db.session.delete(diff)
    db.session.commit()
    
    return '', 204

@monitor_bp.route('/status', methods=['GET'])
def get_status():
    """Get monitoring status"""
    total_urls = MonitoredUrl.query.count()
    active_urls = MonitoredUrl.query.filter_by(active=True).count()
    total_diffs = DiffFile.query.count()
    
    return jsonify({
        'total_urls': total_urls,
        'active_urls': active_urls,
        'total_diffs': total_diffs,
        'last_check': None  # TODO: Implement last check tracking
    })

# Scheduler endpoints
@monitor_bp.route('/schedule/add', methods=['POST'])
def add_schedule():
    """Add a scheduled monitoring job"""
    print(f"DEBUG: add_schedule route called")
    data = request.json
    print(f"DEBUG: Received data: {data}")
    
    interval_minutes = data.get('interval_minutes', 60)
    job_id = data.get('job_id', 'default_monitor_job')
    
    print(f"DEBUG: interval_minutes={interval_minutes}, job_id={job_id}")
    
    try:
        # Remove existing job first
        try:
            scheduler_service.remove_job(job_id)
            print(f"DEBUG: Removed existing job {job_id}")
        except:
            print(f"DEBUG: No existing job to remove")
        
        # Add new job
        print(f"DEBUG: Adding monitoring job...")
        success = scheduler_service.add_monitoring_job(job_id, interval_minutes)
        print(f"DEBUG: add_monitoring_job returned: {success}")
        
        if success:
            # Verify job was added
            jobs = scheduler_service.get_jobs()
            job_exists = any(job['id'] == job_id for job in jobs)
            print(f"DEBUG: Job verification - exists: {job_exists}")
            
            if job_exists:
                return jsonify({
                    'message': f'Background monitoring scheduled every {interval_minutes} minutes',
                    'job_id': job_id,
                    'type': 'backend_scheduler'
                }), 200
            else:
                return jsonify({'message': 'Job added but not found in list'}), 500
        else:
            return jsonify({'message': 'Failed to add scheduled job'}), 500
            
    except Exception as e:
        print(f"DEBUG: Exception in add_schedule: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Scheduler error: {str(e)}'}), 500



@monitor_bp.route('/schedule/remove/<job_id>', methods=['DELETE'])
def remove_schedule(job_id):
    """Remove a scheduled monitoring job"""
    try:
        success = scheduler_service.remove_job(job_id)
        if success:
            return jsonify({'message': f'Schedule with ID {job_id} removed'}), 200
        else:
            return jsonify({'message': f'Failed to remove schedule with ID {job_id}'}), 500
    except Exception as e:
        return jsonify({'message': f'Failed to remove schedule: {str(e)}'}), 500




@monitor_bp.route('/schedule/list', methods=['GET'])
def list_schedules():
    """List all scheduled monitoring jobs"""
    try:
        jobs = scheduler_service.get_jobs()
        return jsonify(jobs), 200
    except Exception as e:
        return jsonify({'message': f'Failed to list schedules: {str(e)}'}), 500

@monitor_bp.route('/schedule/pause/<job_id>', methods=['PUT'])
def pause_schedule(job_id):
    """Pause a scheduled monitoring job"""
    try:
        success = scheduler_service.pause_job(job_id)
        if success:
            return jsonify({'message': f'Schedule with ID {job_id} paused'}), 200
        else:
            return jsonify({'message': f'Failed to pause schedule with ID {job_id}'}), 500
    except Exception as e:
        return jsonify({'message': f'Failed to pause schedule: {str(e)}'}), 500

@monitor_bp.route('/schedule/resume/<job_id>', methods=['PUT'])
def resume_schedule(job_id):
    """Resume a paused monitoring job"""
    try:
        success = scheduler_service.resume_job(job_id)
        if success:
            return jsonify({'message': f'Schedule with ID {job_id} resumed'}), 200
        else:
            return jsonify({'message': f'Failed to resume schedule with ID {job_id}'}), 500
    except Exception as e:
        return jsonify({'message': f'Failed to resume schedule: {str(e)}'}), 500