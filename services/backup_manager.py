import os
import shutil
import logging
import mimetypes
import zipfile
import tarfile
from datetime import datetime
from flask import current_app, send_file, abort
import glob

class BackupManager:
    """Service for managing server backup operations"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def get_available_backups(self):
        """Get list of available backup files"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path or not os.path.exists(backup_path):
                return []
            
            backups = []
            backup_extensions = ('.zip', '.tar.gz', '.tar.bz2', '.tar.xz', '.7z', '.rar')
            
            for file_path in glob.glob(f'{backup_path}/*'):
                if os.path.isfile(file_path) and file_path.lower().endswith(backup_extensions):
                    stat = os.stat(file_path)
                    filename = os.path.basename(file_path)
                    
                    # Try to parse date from filename
                    backup_date = self._extract_date_from_filename(filename)
                    
                    backups.append({
                        'filename': filename,
                        'path': file_path,
                        'size': stat.st_size,
                        'size_human': self._human_readable_size(stat.st_size),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'backup_date': backup_date,
                        'type': self._get_backup_type(filename)
                    })
            
            # Sort by modification time (newest first)
            return sorted(backups, key=lambda x: x['modified'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Error getting available backups: {e}")
            return []
    
    def _extract_date_from_filename(self, filename):
        """Try to extract date from backup filename"""
        import re
        
        # Common date patterns in backup filenames
        patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{4}_\d{2}_\d{2})',  # YYYY_MM_DD
            r'(\d{8})',              # YYYYMMDD
            r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})',  # YYYY-MM-DD_HH-MM-SS
            r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})',  # YYYY_MM_DD_HH_MM_SS
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                date_str = match.group(1)
                try:
                    # Try different date formats
                    for fmt in ['%Y-%m-%d', '%Y_%m_%d', '%Y%m%d', 
                               '%Y-%m-%d_%H-%M-%S', '%Y_%m_%d_%H_%M_%S']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            return parsed_date.isoformat()
                        except ValueError:
                            continue
                except:
                    pass
        
        return None
    
    def _get_backup_type(self, filename):
        """Determine backup type from filename"""
        if 'world' in filename.lower():
            return 'world'
        elif 'full' in filename.lower() or 'complete' in filename.lower():
            return 'full'
        elif 'config' in filename.lower():
            return 'config'
        elif 'mod' in filename.lower():
            return 'mods'
        else:
            return 'unknown'
    
    def _human_readable_size(self, size_bytes):
        """Convert bytes to human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def get_backup_info(self, backup_filename):
        """Get detailed information about a specific backup"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path:
                return {'success': False, 'error': 'Backup path not configured'}
            
            backup_file_path = os.path.join(backup_path, backup_filename)
            
            # Security check
            real_backup_path = os.path.realpath(backup_path)
            real_file_path = os.path.realpath(backup_file_path)
            
            if not real_file_path.startswith(real_backup_path):
                return {'success': False, 'error': 'Access denied: Path outside backup directory'}
            
            if not os.path.exists(backup_file_path):
                return {'success': False, 'error': 'Backup file not found'}
            
            stat = os.stat(backup_file_path)
            
            # Get archive contents if possible
            contents = self._get_archive_contents(backup_file_path)
            
            return {
                'success': True,
                'filename': backup_filename,
                'path': backup_file_path,
                'size': stat.st_size,
                'size_human': self._human_readable_size(stat.st_size),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'backup_date': self._extract_date_from_filename(backup_filename),
                'type': self._get_backup_type(backup_filename),
                'contents': contents
            }
            
        except Exception as e:
            self.logger.error(f"Error getting backup info: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_archive_contents(self, archive_path):
        """Get contents list of an archive file"""
        try:
            contents = []
            
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    for info in zf.infolist()[:50]:  # Limit to first 50 entries
                        contents.append({
                            'name': info.filename,
                            'size': info.file_size,
                            'is_dir': info.is_dir()
                        })
            elif archive_path.endswith(('.tar.gz', '.tar.bz2', '.tar.xz', '.tar')):
                with tarfile.open(archive_path, 'r') as tf:
                    for member in tf.getmembers()[:50]:  # Limit to first 50 entries
                        contents.append({
                            'name': member.name,
                            'size': member.size,
                            'is_dir': member.isdir()
                        })
            
            return contents
            
        except Exception as e:
            self.logger.debug(f"Could not read archive contents: {e}")
            return []
    
    def download_backup(self, backup_filename):
        """Prepare backup file for download"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path:
                abort(404, 'Backup path not configured')
            
            backup_file_path = os.path.join(backup_path, backup_filename)
            
            # Security check
            real_backup_path = os.path.realpath(backup_path)
            real_file_path = os.path.realpath(backup_file_path)
            
            if not real_file_path.startswith(real_backup_path):
                abort(403, 'Access denied')
            
            if not os.path.exists(backup_file_path):
                abort(404, 'Backup file not found')
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(backup_filename)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            return send_file(
                backup_file_path,
                as_attachment=True,
                download_name=backup_filename,
                mimetype=mime_type
            )
            
        except Exception as e:
            self.logger.error(f"Error downloading backup: {e}")
            abort(500, str(e))
    
    def delete_backup(self, backup_filename):
        """Delete a backup file"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path:
                return {'success': False, 'error': 'Backup path not configured'}
            
            backup_file_path = os.path.join(backup_path, backup_filename)
            
            # Security check
            real_backup_path = os.path.realpath(backup_path)
            real_file_path = os.path.realpath(backup_file_path)
            
            if not real_file_path.startswith(real_backup_path):
                return {'success': False, 'error': 'Access denied: Path outside backup directory'}
            
            if not os.path.exists(backup_file_path):
                return {'success': False, 'error': 'Backup file not found'}
            
            # Get file info before deletion
            stat = os.stat(backup_file_path)
            size_freed = self._human_readable_size(stat.st_size)
            
            # Delete the file
            os.unlink(backup_file_path)
            
            return {
                'success': True,
                'message': f'Backup {backup_filename} deleted successfully',
                'size_freed': size_freed
            }
            
        except PermissionError:
            return {'success': False, 'error': 'Permission denied deleting backup file'}
        except Exception as e:
            self.logger.error(f"Error deleting backup: {e}")
            return {'success': False, 'error': str(e)}
    
    def cleanup_old_backups(self, keep_count=10, keep_days=30):
        """Clean up old backup files based on count and age"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path or not os.path.exists(backup_path):
                return {'success': False, 'error': 'Backup path not configured or not found'}
            
            backups = self.get_available_backups()
            if not backups:
                return {'success': True, 'message': 'No backups found to clean up', 'deleted': []}
            
            deleted_backups = []
            total_size_freed = 0
            
            # Keep newest backups based on count
            if len(backups) > keep_count:
                for backup in backups[keep_count:]:
                    backup_file = backup['path']
                    try:
                        size = backup['size']
                        os.unlink(backup_file)
                        deleted_backups.append({
                            'filename': backup['filename'],
                            'reason': f'Exceeded keep count ({keep_count})',
                            'size': size
                        })
                        total_size_freed += size
                    except Exception as e:
                        self.logger.error(f"Error deleting backup {backup['filename']}: {e}")
            
            # Delete backups older than keep_days
            cutoff_date = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
            
            for backup in backups[:keep_count]:  # Check remaining backups
                modified_timestamp = datetime.fromisoformat(backup['modified'].replace('Z', '+00:00')).timestamp()
                if modified_timestamp < cutoff_date:
                    backup_file = backup['path']
                    try:
                        size = backup['size']
                        os.unlink(backup_file)
                        deleted_backups.append({
                            'filename': backup['filename'],
                            'reason': f'Older than {keep_days} days',
                            'size': size
                        })
                        total_size_freed += size
                    except Exception as e:
                        self.logger.error(f"Error deleting backup {backup['filename']}: {e}")
            
            return {
                'success': True,
                'message': f'Cleanup completed. Deleted {len(deleted_backups)} backups.',
                'deleted': deleted_backups,
                'total_size_freed': self._human_readable_size(total_size_freed)
            }
            
        except Exception as e:
            self.logger.error(f"Error cleaning up backups: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_backup_statistics(self):
        """Get backup directory statistics"""
        try:
            backup_path = current_app.config.get('BACKUP_PATH')
            if not backup_path or not os.path.exists(backup_path):
                return {
                    'total_backups': 0,
                    'total_size': 0,
                    'total_size_human': '0 B',
                    'oldest_backup': None,
                    'newest_backup': None,
                    'backup_types': {}
                }
            
            backups = self.get_available_backups()
            
            if not backups:
                return {
                    'total_backups': 0,
                    'total_size': 0,
                    'total_size_human': '0 B',
                    'oldest_backup': None,
                    'newest_backup': None,
                    'backup_types': {}
                }
            
            total_size = sum(backup['size'] for backup in backups)
            backup_types = {}
            
            for backup in backups:
                backup_type = backup['type']
                if backup_type not in backup_types:
                    backup_types[backup_type] = {'count': 0, 'size': 0}
                backup_types[backup_type]['count'] += 1
                backup_types[backup_type]['size'] += backup['size']
            
            # Convert sizes to human readable
            for backup_type in backup_types:
                backup_types[backup_type]['size_human'] = self._human_readable_size(backup_types[backup_type]['size'])
            
            return {
                'total_backups': len(backups),
                'total_size': total_size,
                'total_size_human': self._human_readable_size(total_size),
                'oldest_backup': backups[-1] if backups else None,
                'newest_backup': backups[0] if backups else None,
                'backup_types': backup_types
            }
            
        except Exception as e:
            self.logger.error(f"Error getting backup statistics: {e}")
            return {
                'total_backups': 0,
                'total_size': 0,
                'total_size_human': '0 B',
                'oldest_backup': None,
                'newest_backup': None,
                'backup_types': {},
                'error': str(e)
            }