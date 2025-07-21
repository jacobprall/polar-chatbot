"""Session recovery and data integrity services."""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from ..models.session import Session, SessionMetadata
from ..models.events import SessionEvent, EventType
from ..services.session_manager import SessionManager, SessionManagerError
from ..services.event_logger import EventLogger, EventReplayError
from ..storage.base import StorageBackend, StorageError, StorageNotFoundError

logger = logging.getLogger(__name__)


class RecoveryStatus(Enum):
    """Status of recovery operations."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class CorruptionType(Enum):
    """Types of data corruption that can be detected."""
    MISSING_SESSION_FILE = "missing_session_file"
    INVALID_JSON = "invalid_json"
    MISSING_EVENTS = "missing_events"
    INCONSISTENT_TIMESTAMPS = "inconsistent_timestamps"
    ORPHANED_FILES = "orphaned_files"
    INVALID_POLICY_CONTENT = "invalid_policy_content"
    MISSING_VALIDATION_RESULTS = "missing_validation_results"


@dataclass
class CorruptionIssue:
    """Represents a data corruption issue."""
    type: CorruptionType
    severity: str  # "low", "medium", "high", "critical"
    description: str
    affected_files: List[str]
    suggested_fix: str
    auto_fixable: bool = False


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    status: RecoveryStatus
    session_id: str
    issues_found: List[CorruptionIssue]
    issues_fixed: List[CorruptionIssue]
    backup_created: bool = False
    recovery_time: float = 0.0
    error_message: Optional[str] = None


@dataclass
class IntegrityReport:
    """Comprehensive integrity report for sessions."""
    total_sessions: int
    healthy_sessions: int
    corrupted_sessions: int
    recoverable_sessions: int
    issues_by_type: Dict[CorruptionType, int]
    recommendations: List[str]
    scan_time: float = 0.0


class SessionRecoveryService:
    """Service for session recovery and data integrity management."""
    
    def __init__(self, session_manager: SessionManager, event_logger: EventLogger,
                 storage_backend: StorageBackend):
        self.session_manager = session_manager
        self.event_logger = event_logger
        self.storage = storage_backend
        self.backup_prefix = "backups/"
    
    def recover_session(self, session_id: str, 
                       create_backup: bool = True,
                       force_event_replay: bool = False) -> RecoveryResult:
        """
        Attempt to recover a corrupted or incomplete session.
        
        Args:
            session_id: ID of session to recover
            create_backup: Whether to create backup before recovery
            force_event_replay: Force recovery from events even if session loads
            
        Returns:
            RecoveryResult with recovery status and details
        """
        start_time = datetime.now()
        result = RecoveryResult(
            status=RecoveryStatus.FAILED,
            session_id=session_id,
            issues_found=[],
            issues_fixed=[]
        )
        
        try:
            logger.info(f"Starting recovery for session {session_id}")
            
            # Step 1: Analyze session integrity
            issues = self._analyze_session_integrity(session_id)
            result.issues_found = issues
            
            if not issues and not force_event_replay:
                # Session appears healthy
                try:
                    session = self.session_manager.load_session(session_id)
                    result.status = RecoveryStatus.SUCCESS
                    logger.info(f"Session {session_id} is healthy, no recovery needed")
                    return result
                except SessionManagerError:
                    # Session load failed despite no detected issues
                    logger.warning(f"Session {session_id} failed to load despite no detected issues")
            
            # Step 2: Create backup if requested
            if create_backup:
                backup_success = self._create_session_backup(session_id)
                result.backup_created = backup_success
                if backup_success:
                    logger.info(f"Backup created for session {session_id}")
            
            # Step 3: Attempt recovery strategies
            recovery_success = False
            
            # Strategy 1: Event replay recovery
            if self._has_events(session_id):
                try:
                    recovered_session = self._recover_from_events(session_id)
                    if recovered_session:
                        # Save recovered session
                        self.session_manager.save_session(recovered_session)
                        recovery_success = True
                        result.issues_fixed = [issue for issue in issues if issue.auto_fixable]
                        logger.info(f"Successfully recovered session {session_id} from events")
                except Exception as e:
                    logger.error(f"Event replay recovery failed for {session_id}: {e}")
            
            # Strategy 2: Partial file recovery
            if not recovery_success:
                try:
                    recovered_session = self._recover_from_partial_files(session_id)
                    if recovered_session:
                        self.session_manager.save_session(recovered_session)
                        recovery_success = True
                        result.issues_fixed = [issue for issue in issues 
                                             if issue.type != CorruptionType.MISSING_EVENTS]
                        logger.info(f"Partially recovered session {session_id} from files")
                except Exception as e:
                    logger.error(f"Partial file recovery failed for {session_id}: {e}")
            
            # Strategy 3: Create minimal session
            if not recovery_success:
                try:
                    minimal_session = self._create_minimal_session(session_id)
                    if minimal_session:
                        self.session_manager.save_session(minimal_session)
                        recovery_success = True
                        result.status = RecoveryStatus.PARTIAL
                        logger.info(f"Created minimal session for {session_id}")
                except Exception as e:
                    logger.error(f"Minimal session creation failed for {session_id}: {e}")
            
            if recovery_success:
                result.status = RecoveryStatus.SUCCESS if len(result.issues_fixed) == len(result.issues_found) else RecoveryStatus.PARTIAL
            else:
                result.status = RecoveryStatus.FAILED
                result.error_message = "All recovery strategies failed"
        
        except Exception as e:
            logger.error(f"Recovery failed for session {session_id}: {e}")
            result.status = RecoveryStatus.FAILED
            result.error_message = str(e)
        
        finally:
            result.recovery_time = (datetime.now() - start_time).total_seconds()
        
        return result
    
    def scan_all_sessions(self) -> IntegrityReport:
        """
        Scan all sessions for integrity issues.
        
        Returns:
            IntegrityReport with comprehensive analysis
        """
        start_time = datetime.now()
        
        try:
            # Get all session IDs
            session_metadatas = self.session_manager.list_sessions()
            session_ids = [meta.id for meta in session_metadatas]
            
            total_sessions = len(session_ids)
            healthy_sessions = 0
            corrupted_sessions = 0
            recoverable_sessions = 0
            issues_by_type = {}
            recommendations = []
            
            logger.info(f"Starting integrity scan of {total_sessions} sessions")
            
            for session_id in session_ids:
                try:
                    issues = self._analyze_session_integrity(session_id)
                    
                    if not issues:
                        healthy_sessions += 1
                    else:
                        corrupted_sessions += 1
                        
                        # Check if recoverable
                        if self._is_session_recoverable(issues):
                            recoverable_sessions += 1
                        
                        # Count issues by type
                        for issue in issues:
                            if issue.type not in issues_by_type:
                                issues_by_type[issue.type] = 0
                            issues_by_type[issue.type] += 1
                
                except Exception as e:
                    logger.error(f"Failed to analyze session {session_id}: {e}")
                    corrupted_sessions += 1
            
            # Generate recommendations
            recommendations = self._generate_recommendations(issues_by_type, 
                                                           corrupted_sessions, 
                                                           recoverable_sessions)
            
            scan_time = (datetime.now() - start_time).total_seconds()
            
            return IntegrityReport(
                total_sessions=total_sessions,
                healthy_sessions=healthy_sessions,
                corrupted_sessions=corrupted_sessions,
                recoverable_sessions=recoverable_sessions,
                issues_by_type=issues_by_type,
                recommendations=recommendations,
                scan_time=scan_time
            )
        
        except Exception as e:
            logger.error(f"Integrity scan failed: {e}")
            return IntegrityReport(
                total_sessions=0,
                healthy_sessions=0,
                corrupted_sessions=0,
                recoverable_sessions=0,
                issues_by_type={},
                recommendations=[f"Scan failed: {str(e)}"],
                scan_time=(datetime.now() - start_time).total_seconds()
            )
    
    def auto_recover_sessions(self, max_sessions: int = 10) -> List[RecoveryResult]:
        """
        Automatically recover sessions that can be safely auto-recovered.
        
        Args:
            max_sessions: Maximum number of sessions to recover in one operation
            
        Returns:
            List of recovery results
        """
        results = []
        
        try:
            # Get sessions that need recovery
            session_metadatas = self.session_manager.list_sessions()
            sessions_to_recover = []
            
            for metadata in session_metadatas:
                try:
                    # Try to load session
                    self.session_manager.load_session(metadata.id)
                except SessionManagerError:
                    # Session needs recovery
                    issues = self._analyze_session_integrity(metadata.id)
                    if self._is_auto_recoverable(issues):
                        sessions_to_recover.append(metadata.id)
                
                if len(sessions_to_recover) >= max_sessions:
                    break
            
            logger.info(f"Auto-recovering {len(sessions_to_recover)} sessions")
            
            for session_id in sessions_to_recover:
                try:
                    result = self.recover_session(session_id, create_backup=True)
                    results.append(result)
                    
                    if result.status == RecoveryStatus.SUCCESS:
                        logger.info(f"Auto-recovered session {session_id}")
                    else:
                        logger.warning(f"Auto-recovery failed for session {session_id}")
                
                except Exception as e:
                    logger.error(f"Auto-recovery error for session {session_id}: {e}")
                    results.append(RecoveryResult(
                        status=RecoveryStatus.FAILED,
                        session_id=session_id,
                        issues_found=[],
                        issues_fixed=[],
                        error_message=str(e)
                    ))
        
        except Exception as e:
            logger.error(f"Auto-recovery operation failed: {e}")
        
        return results
    
    def create_session_backup(self, session_id: str) -> bool:
        """
        Create a backup of a session.
        
        Args:
            session_id: Session ID to backup
            
        Returns:
            True if backup was successful
        """
        return self._create_session_backup(session_id)
    
    def restore_session_from_backup(self, session_id: str, 
                                  backup_timestamp: Optional[str] = None) -> bool:
        """
        Restore a session from backup.
        
        Args:
            session_id: Session ID to restore
            backup_timestamp: Specific backup timestamp (uses latest if None)
            
        Returns:
            True if restore was successful
        """
        try:
            # Find backup
            backup_key = self._get_backup_key(session_id, backup_timestamp)
            
            if not backup_key:
                logger.error(f"No backup found for session {session_id}")
                return False
            
            # Load backup data
            backup_obj = self.storage.get_object(backup_key)
            backup_data = json.loads(backup_obj.content)
            
            # Restore session files
            for file_path, file_content in backup_data.get("files", {}).items():
                self.storage.put_object(
                    key=file_path,
                    content=file_content,
                    content_type="application/octet-stream"
                )
            
            logger.info(f"Restored session {session_id} from backup {backup_key}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to restore session {session_id} from backup: {e}")
            return False
    
    def list_session_backups(self, session_id: str) -> List[Dict[str, Any]]:
        """
        List available backups for a session.
        
        Args:
            session_id: Session ID to list backups for
            
        Returns:
            List of backup information
        """
        try:
            prefix = f"{self.backup_prefix}{session_id}_"
            result = self.storage.list_objects(prefix=prefix)
            
            backups = []
            for obj_info in result['objects']:
                timestamp = obj_info.key.split('_')[-1].replace('.json', '')
                backups.append({
                    "key": obj_info.key,
                    "timestamp": timestamp,
                    "size": obj_info.size,
                    "created": obj_info.last_modified
                })
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda b: b['created'], reverse=True)
            return backups
        
        except Exception as e:
            logger.error(f"Failed to list backups for session {session_id}: {e}")
            return []
    
    # Private methods
    
    def _analyze_session_integrity(self, session_id: str) -> List[CorruptionIssue]:
        """Analyze a session for integrity issues."""
        issues = []
        
        try:
            # Check if session files exist
            session_files = self._get_expected_session_files(session_id)
            
            for file_path, file_info in session_files.items():
                try:
                    obj = self.storage.get_object(file_path)
                    
                    # Validate JSON files
                    if file_info["type"] == "json":
                        try:
                            json.loads(obj.content)
                        except json.JSONDecodeError:
                            issues.append(CorruptionIssue(
                                type=CorruptionType.INVALID_JSON,
                                severity="high",
                                description=f"Invalid JSON in {file_path}",
                                affected_files=[file_path],
                                suggested_fix="Restore from backup or regenerate file",
                                auto_fixable=False
                            ))
                
                except StorageNotFoundError:
                    if file_info["required"]:
                        issues.append(CorruptionIssue(
                            type=CorruptionType.MISSING_SESSION_FILE,
                            severity="critical" if file_path.endswith("session.json") else "medium",
                            description=f"Missing required file: {file_path}",
                            affected_files=[file_path],
                            suggested_fix="Recover from events or create minimal file",
                            auto_fixable=True
                        ))
            
            # Check event integrity
            if not self._has_events(session_id):
                issues.append(CorruptionIssue(
                    type=CorruptionType.MISSING_EVENTS,
                    severity="medium",
                    description="No events found for session",
                    affected_files=[f"events/{session_id}_events.jsonl"],
                    suggested_fix="Events cannot be recovered, but session may still be usable",
                    auto_fixable=False
                ))
            else:
                # Validate event integrity
                try:
                    validation_result = self.event_logger.validate_event_integrity(session_id)
                    if not validation_result["is_valid"]:
                        for issue_desc in validation_result["issues"]:
                            issues.append(CorruptionIssue(
                                type=CorruptionType.INCONSISTENT_TIMESTAMPS,
                                severity="medium",
                                description=f"Event integrity issue: {issue_desc}",
                                affected_files=[f"events/{session_id}_events.jsonl"],
                                suggested_fix="Attempt event replay recovery",
                                auto_fixable=True
                            ))
                except Exception as e:
                    logger.error(f"Event validation failed for {session_id}: {e}")
        
        except Exception as e:
            logger.error(f"Integrity analysis failed for session {session_id}: {e}")
            issues.append(CorruptionIssue(
                type=CorruptionType.MISSING_SESSION_FILE,
                severity="critical",
                description=f"Failed to analyze session: {str(e)}",
                affected_files=[],
                suggested_fix="Manual investigation required",
                auto_fixable=False
            ))
        
        return issues
    
    def _recover_from_events(self, session_id: str) -> Optional[Session]:
        """Recover session from event log."""
        try:
            return self.event_logger.replay_session(session_id)
        except EventReplayError as e:
            logger.error(f"Event replay failed for session {session_id}: {e}")
            return None
    
    def _recover_from_partial_files(self, session_id: str) -> Optional[Session]:
        """Recover session from partial files."""
        try:
            # Create basic session
            session = Session(
                id=session_id,
                name=f"Recovered Session {session_id[:8]}",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Try to load requirements
            try:
                requirements_key = f"sessions/{session_id}/requirements.txt"
                req_obj = self.storage.get_object(requirements_key)
                session.requirements_text = req_obj.content
            except StorageNotFoundError:
                pass
            
            # Try to load notes
            try:
                notes_key = f"sessions/{session_id}/notes.md"
                notes_obj = self.storage.get_object(notes_key)
                session.notes = notes_obj.content
            except StorageNotFoundError:
                pass
            
            # Try to load session metadata
            try:
                session_key = f"sessions/{session_id}/session.json"
                session_obj = self.storage.get_object(session_key)
                session_data = json.loads(session_obj.content)
                session.name = session_data.get("name", session.name)
                session.created_at = datetime.fromisoformat(session_data.get("created_at", session.created_at.isoformat()))
                session.metadata = session_data.get("metadata", {})
            except (StorageNotFoundError, json.JSONDecodeError, ValueError):
                pass
            
            return session
        
        except Exception as e:
            logger.error(f"Partial file recovery failed for session {session_id}: {e}")
            return None
    
    def _create_minimal_session(self, session_id: str) -> Optional[Session]:
        """Create a minimal session as last resort."""
        try:
            return Session(
                id=session_id,
                name=f"Recovered Session {session_id[:8]}",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                requirements_text="# Session recovered with minimal data\n# Please re-enter your requirements",
                notes="This session was recovered with minimal data due to corruption."
            )
        except Exception as e:
            logger.error(f"Minimal session creation failed for session {session_id}: {e}")
            return None
    
    def _create_session_backup(self, session_id: str) -> bool:
        """Create a backup of session files."""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_key = f"{self.backup_prefix}{session_id}_{timestamp}.json"
            
            # Collect all session files
            session_files = {}
            prefix = f"sessions/{session_id}/"
            
            try:
                result = self.storage.list_objects(prefix=prefix)
                for obj_info in result['objects']:
                    try:
                        obj = self.storage.get_object(obj_info.key)
                        session_files[obj_info.key] = obj.content
                    except Exception as e:
                        logger.warning(f"Failed to backup file {obj_info.key}: {e}")
            except Exception as e:
                logger.warning(f"Failed to list session files for backup: {e}")
            
            # Include events if they exist
            events_key = f"events/{session_id}_events.jsonl"
            try:
                events_obj = self.storage.get_object(events_key)
                session_files[events_key] = events_obj.content
            except StorageNotFoundError:
                pass
            
            # Create backup
            backup_data = {
                "session_id": session_id,
                "backup_timestamp": timestamp,
                "files": session_files
            }
            
            self.storage.put_object(
                key=backup_key,
                content=json.dumps(backup_data, indent=2),
                content_type="application/json",
                metadata={
                    "session_id": session_id,
                    "backup_type": "full",
                    "file_count": str(len(session_files))
                }
            )
            
            logger.info(f"Created backup {backup_key} with {len(session_files)} files")
            return True
        
        except Exception as e:
            logger.error(f"Failed to create backup for session {session_id}: {e}")
            return False
    
    def _get_expected_session_files(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Get expected session files and their properties."""
        return {
            f"sessions/{session_id}/session.json": {"type": "json", "required": True},
            f"sessions/{session_id}/requirements.txt": {"type": "text", "required": False},
            f"sessions/{session_id}/notes.md": {"type": "text", "required": False}
        }
    
    def _has_events(self, session_id: str) -> bool:
        """Check if session has events."""
        try:
            events = self.event_logger.get_all_events(session_id)
            return len(events) > 0
        except Exception:
            return False
    
    def _is_session_recoverable(self, issues: List[CorruptionIssue]) -> bool:
        """Check if session can be recovered."""
        critical_issues = [i for i in issues if i.severity == "critical"]
        auto_fixable_issues = [i for i in issues if i.auto_fixable]
        
        # Recoverable if no critical issues or if all issues are auto-fixable
        return len(critical_issues) == 0 or len(auto_fixable_issues) == len(issues)
    
    def _is_auto_recoverable(self, issues: List[CorruptionIssue]) -> bool:
        """Check if session can be auto-recovered safely."""
        return all(issue.auto_fixable for issue in issues)
    
    def _generate_recommendations(self, issues_by_type: Dict[CorruptionType, int],
                                corrupted_sessions: int, recoverable_sessions: int) -> List[str]:
        """Generate recommendations based on scan results."""
        recommendations = []
        
        if corrupted_sessions == 0:
            recommendations.append("✅ All sessions are healthy")
            return recommendations
        
        if recoverable_sessions > 0:
            recommendations.append(f"🔧 {recoverable_sessions} sessions can be automatically recovered")
        
        if CorruptionType.MISSING_EVENTS in issues_by_type:
            count = issues_by_type[CorruptionType.MISSING_EVENTS]
            recommendations.append(f"📝 {count} sessions missing event logs - consider enabling event logging")
        
        if CorruptionType.INVALID_JSON in issues_by_type:
            count = issues_by_type[CorruptionType.INVALID_JSON]
            recommendations.append(f"🚨 {count} sessions have corrupted JSON files - immediate attention required")
        
        if CorruptionType.MISSING_SESSION_FILE in issues_by_type:
            count = issues_by_type[CorruptionType.MISSING_SESSION_FILE]
            recommendations.append(f"📁 {count} sessions have missing files - recovery recommended")
        
        recommendations.append("💾 Consider implementing regular automated backups")
        recommendations.append("🔍 Run integrity scans regularly to detect issues early")
        
        return recommendations
    
    def _get_backup_key(self, session_id: str, timestamp: Optional[str] = None) -> Optional[str]:
        """Get backup key for session."""
        try:
            if timestamp:
                return f"{self.backup_prefix}{session_id}_{timestamp}.json"
            
            # Find latest backup
            backups = self.list_session_backups(session_id)
            if backups:
                return backups[0]["key"]  # Latest backup
            
            return None
        except Exception:
            return None