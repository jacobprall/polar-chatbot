"""UI components for session recovery and data integrity management."""

import streamlit as st
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from ...services.session_recovery import (
    SessionRecoveryService, RecoveryResult, IntegrityReport, 
    RecoveryStatus, CorruptionType, CorruptionIssue
)
from ...services.session_manager import SessionManager
from ...services.event_logger import EventLogger
from ...storage.base import StorageBackend
from .error_handler import create_error_handler, error_boundary, ErrorContext


def create_recovery_service() -> SessionRecoveryService:
    """Create and cache session recovery service."""
    if "recovery_service" not in st.session_state:
        # Get required services from session state
        session_manager = st.session_state.get("session_manager")
        event_logger = st.session_state.get("event_logger")
        storage_backend = st.session_state.get("storage_backend")
        
        if not all([session_manager, event_logger, storage_backend]):
            st.error("❌ Required services not initialized for session recovery")
            return None
        
        st.session_state.recovery_service = SessionRecoveryService(
            session_manager=session_manager,
            event_logger=event_logger,
            storage_backend=storage_backend
        )
    
    return st.session_state.recovery_service


def render_session_recovery_dashboard():
    """Render the main session recovery dashboard."""
    st.subheader("🔧 Session Recovery & Data Integrity")
    
    recovery_service = create_recovery_service()
    if not recovery_service:
        return
    
    # Create tabs for different recovery functions
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Integrity Scan", 
        "🔧 Manual Recovery", 
        "💾 Backup Management", 
        "📊 Recovery History"
    ])
    
    with tab1:
        render_integrity_scan_tab(recovery_service)
    
    with tab2:
        render_manual_recovery_tab(recovery_service)
    
    with tab3:
        render_backup_management_tab(recovery_service)
    
    with tab4:
        render_recovery_history_tab()


def render_integrity_scan_tab(recovery_service: SessionRecoveryService):
    """Render the integrity scan tab."""
    st.markdown("### 🔍 Session Integrity Scan")
    st.markdown("Scan all sessions for data corruption and integrity issues.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if st.button("🔍 Start Integrity Scan", type="primary"):
            run_integrity_scan(recovery_service)
    
    with col2:
        if st.button("🔄 Auto-Recover Sessions"):
            run_auto_recovery(recovery_service)
    
    # Display last scan results if available
    if "last_integrity_report" in st.session_state:
        display_integrity_report(st.session_state.last_integrity_report)


def render_manual_recovery_tab(recovery_service: SessionRecoveryService):
    """Render the manual recovery tab."""
    st.markdown("### 🔧 Manual Session Recovery")
    st.markdown("Manually recover specific sessions that have issues.")
    
    # Session selector
    try:
        session_manager = st.session_state.get("session_manager")
        if session_manager:
            sessions = session_manager.list_sessions()
            
            if not sessions:
                st.info("📝 No sessions found")
                return
            
            session_options = [(f"{s.name} ({s.id[:8]})", s.id) for s in sessions]
            
            selected_label = st.selectbox(
                "Select Session to Recover",
                options=[label for label, _ in session_options],
                help="Choose a session to analyze and potentially recover"
            )
            
            selected_session_id = next(sid for label, sid in session_options if label == selected_label)
            
            # Recovery options
            col1, col2 = st.columns(2)
            
            with col1:
                create_backup = st.checkbox("Create Backup Before Recovery", value=True)
                force_event_replay = st.checkbox("Force Event Replay Recovery", value=False)
            
            with col2:
                if st.button("🔧 Analyze Session", key="analyze_session"):
                    analyze_session(recovery_service, selected_session_id)
                
                if st.button("🚀 Recover Session", type="primary", key="recover_session"):
                    recover_session(recovery_service, selected_session_id, create_backup, force_event_replay)
            
            # Display analysis results
            if f"analysis_{selected_session_id}" in st.session_state:
                display_session_analysis(st.session_state[f"analysis_{selected_session_id}"])
    
    except Exception as e:
        st.error(f"❌ Error loading sessions: {str(e)}")


def render_backup_management_tab(recovery_service: SessionRecoveryService):
    """Render the backup management tab."""
    st.markdown("### 💾 Backup Management")
    st.markdown("Create and manage session backups.")
    
    # Session selector for backup
    try:
        session_manager = st.session_state.get("session_manager")
        if session_manager:
            sessions = session_manager.list_sessions()
            
            if sessions:
                session_options = [(f"{s.name} ({s.id[:8]})", s.id) for s in sessions]
                
                selected_label = st.selectbox(
                    "Select Session for Backup Operations",
                    options=[label for label, _ in session_options],
                    key="backup_session_selector"
                )
                
                selected_session_id = next(sid for label, sid in session_options if label == selected_label)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("💾 Create Backup", key="create_backup"):
                        create_session_backup(recovery_service, selected_session_id)
                
                with col2:
                    if st.button("📋 List Backups", key="list_backups"):
                        list_session_backups(recovery_service, selected_session_id)
                
                # Display backup list if available
                if f"backups_{selected_session_id}" in st.session_state:
                    display_backup_list(recovery_service, selected_session_id, 
                                      st.session_state[f"backups_{selected_session_id}"])
    
    except Exception as e:
        st.error(f"❌ Error in backup management: {str(e)}")


def render_recovery_history_tab():
    """Render the recovery history tab."""
    st.markdown("### 📊 Recovery History")
    st.markdown("View history of recovery operations.")
    
    if "recovery_history" not in st.session_state:
        st.session_state.recovery_history = []
    
    history = st.session_state.recovery_history
    
    if not history:
        st.info("📝 No recovery operations performed yet")
        return
    
    # Display recovery history
    for i, result in enumerate(reversed(history[-10:])):  # Show last 10
        with st.expander(
            f"🔧 {result.session_id[:8]} - {result.status.value.title()} "
            f"({datetime.fromisoformat(result.timestamp) if hasattr(result, 'timestamp') else 'Unknown time'})",
            expanded=False
        ):
            display_recovery_result(result)


def run_integrity_scan(recovery_service: SessionRecoveryService):
    """Run integrity scan and display results."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(component="IntegrityScan")):
        progress_placeholder = st.empty()
        progress_placeholder.info("🔍 Scanning sessions for integrity issues...")
        
        start_time = time.time()
        report = recovery_service.scan_all_sessions()
        scan_time = time.time() - start_time
        
        progress_placeholder.empty()
        
        # Store report for display
        st.session_state.last_integrity_report = report
        
        # Show summary
        if report.corrupted_sessions == 0:
            st.success(f"✅ All {report.total_sessions} sessions are healthy! (Scan took {scan_time:.1f}s)")
        else:
            st.warning(f"⚠️ Found {report.corrupted_sessions} corrupted sessions out of {report.total_sessions} total")
            if report.recoverable_sessions > 0:
                st.info(f"🔧 {report.recoverable_sessions} sessions can be automatically recovered")


def run_auto_recovery(recovery_service: SessionRecoveryService):
    """Run automatic recovery for recoverable sessions."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(component="AutoRecovery")):
        progress_placeholder = st.empty()
        progress_placeholder.info("🔄 Running automatic recovery...")
        
        results = recovery_service.auto_recover_sessions(max_sessions=5)
        
        progress_placeholder.empty()
        
        if not results:
            st.info("📝 No sessions needed automatic recovery")
            return
        
        # Store results in history
        if "recovery_history" not in st.session_state:
            st.session_state.recovery_history = []
        
        for result in results:
            result.timestamp = datetime.now().isoformat()
            st.session_state.recovery_history.append(result)
        
        # Display summary
        successful = len([r for r in results if r.status == RecoveryStatus.SUCCESS])
        partial = len([r for r in results if r.status == RecoveryStatus.PARTIAL])
        failed = len([r for r in results if r.status == RecoveryStatus.FAILED])
        
        if successful > 0:
            st.success(f"✅ Successfully recovered {successful} sessions")
        if partial > 0:
            st.warning(f"⚠️ Partially recovered {partial} sessions")
        if failed > 0:
            st.error(f"❌ Failed to recover {failed} sessions")


def analyze_session(recovery_service: SessionRecoveryService, session_id: str):
    """Analyze a specific session for issues."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(session_id=session_id, component="SessionAnalysis")):
        progress_placeholder = st.empty()
        progress_placeholder.info(f"🔍 Analyzing session {session_id[:8]}...")
        
        # This is a simplified analysis - in a real implementation,
        # we'd call a method on recovery_service to analyze without recovering
        issues = recovery_service._analyze_session_integrity(session_id)
        
        progress_placeholder.empty()
        
        # Store analysis results
        st.session_state[f"analysis_{session_id}"] = {
            "session_id": session_id,
            "issues": issues,
            "analyzed_at": datetime.now()
        }
        
        if not issues:
            st.success(f"✅ Session {session_id[:8]} appears healthy")
        else:
            st.warning(f"⚠️ Found {len(issues)} issues in session {session_id[:8]}")


def recover_session(recovery_service: SessionRecoveryService, session_id: str, 
                   create_backup: bool, force_event_replay: bool):
    """Recover a specific session."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(session_id=session_id, component="SessionRecovery")):
        progress_placeholder = st.empty()
        progress_placeholder.info(f"🔧 Recovering session {session_id[:8]}...")
        
        result = recovery_service.recover_session(
            session_id=session_id,
            create_backup=create_backup,
            force_event_replay=force_event_replay
        )
        
        progress_placeholder.empty()
        
        # Store result in history
        if "recovery_history" not in st.session_state:
            st.session_state.recovery_history = []
        
        result.timestamp = datetime.now().isoformat()
        st.session_state.recovery_history.append(result)
        
        # Display result
        if result.status == RecoveryStatus.SUCCESS:
            st.success(f"✅ Successfully recovered session {session_id[:8]}")
        elif result.status == RecoveryStatus.PARTIAL:
            st.warning(f"⚠️ Partially recovered session {session_id[:8]}")
        else:
            st.error(f"❌ Failed to recover session {session_id[:8]}")
            if result.error_message:
                st.code(result.error_message, language="text")


def create_session_backup(recovery_service: SessionRecoveryService, session_id: str):
    """Create a backup for a session."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(session_id=session_id, component="BackupCreation")):
        progress_placeholder = st.empty()
        progress_placeholder.info(f"💾 Creating backup for session {session_id[:8]}...")
        
        success = recovery_service.create_session_backup(session_id)
        
        progress_placeholder.empty()
        
        if success:
            st.success(f"✅ Backup created for session {session_id[:8]}")
        else:
            st.error(f"❌ Failed to create backup for session {session_id[:8]}")


def list_session_backups(recovery_service: SessionRecoveryService, session_id: str):
    """List backups for a session."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(session_id=session_id, component="BackupListing")):
        backups = recovery_service.list_session_backups(session_id)
        st.session_state[f"backups_{session_id}"] = backups
        
        if not backups:
            st.info(f"📝 No backups found for session {session_id[:8]}")
        else:
            st.success(f"✅ Found {len(backups)} backups for session {session_id[:8]}")


def display_integrity_report(report: IntegrityReport):
    """Display integrity scan report."""
    st.markdown("---")
    st.markdown("### 📊 Integrity Scan Results")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sessions", report.total_sessions)
    
    with col2:
        st.metric("Healthy Sessions", report.healthy_sessions, 
                 delta=report.healthy_sessions - report.corrupted_sessions)
    
    with col3:
        st.metric("Corrupted Sessions", report.corrupted_sessions,
                 delta=report.corrupted_sessions, delta_color="inverse")
    
    with col4:
        st.metric("Recoverable", report.recoverable_sessions)
    
    # Issues breakdown
    if report.issues_by_type:
        st.markdown("#### 🔍 Issues by Type")
        
        for issue_type, count in report.issues_by_type.items():
            severity_icon = {
                CorruptionType.MISSING_SESSION_FILE: "🚨",
                CorruptionType.INVALID_JSON: "🚨",
                CorruptionType.MISSING_EVENTS: "⚠️",
                CorruptionType.INCONSISTENT_TIMESTAMPS: "⚠️",
                CorruptionType.ORPHANED_FILES: "ℹ️",
                CorruptionType.INVALID_POLICY_CONTENT: "⚠️",
                CorruptionType.MISSING_VALIDATION_RESULTS: "ℹ️"
            }.get(issue_type, "❓")
            
            st.write(f"{severity_icon} **{issue_type.value.replace('_', ' ').title()}**: {count} sessions")
    
    # Recommendations
    if report.recommendations:
        st.markdown("#### 💡 Recommendations")
        for recommendation in report.recommendations:
            st.write(f"• {recommendation}")
    
    st.write(f"**Scan completed in {report.scan_time:.2f} seconds**")


def display_session_analysis(analysis: Dict[str, Any]):
    """Display session analysis results."""
    st.markdown("---")
    st.markdown(f"### 🔍 Analysis Results for Session {analysis['session_id'][:8]}")
    
    issues = analysis["issues"]
    
    if not issues:
        st.success("✅ No issues found - session appears healthy")
        return
    
    st.warning(f"⚠️ Found {len(issues)} issues:")
    
    for i, issue in enumerate(issues, 1):
        severity_color = {
            "low": "blue",
            "medium": "orange", 
            "high": "red",
            "critical": "red"
        }.get(issue.severity, "gray")
        
        with st.expander(f"Issue {i}: {issue.description}", expanded=False):
            st.write(f"**Type:** {issue.type.value.replace('_', ' ').title()}")
            st.write(f"**Severity:** :{severity_color}[{issue.severity.upper()}]")
            st.write(f"**Affected Files:** {', '.join(issue.affected_files)}")
            st.write(f"**Suggested Fix:** {issue.suggested_fix}")
            st.write(f"**Auto-fixable:** {'✅ Yes' if issue.auto_fixable else '❌ No'}")


def display_backup_list(recovery_service: SessionRecoveryService, session_id: str, backups: List[Dict[str, Any]]):
    """Display list of backups for a session."""
    st.markdown("---")
    st.markdown(f"### 💾 Backups for Session {session_id[:8]}")
    
    if not backups:
        st.info("📝 No backups found")
        return
    
    for backup in backups:
        with st.expander(
            f"Backup {backup['timestamp']} ({backup['size']} bytes)",
            expanded=False
        ):
            st.write(f"**Created:** {backup['created']}")
            st.write(f"**Size:** {backup['size']:,} bytes")
            st.write(f"**Key:** {backup['key']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button(f"🔄 Restore", key=f"restore_{backup['timestamp']}"):
                    restore_from_backup(recovery_service, session_id, backup['timestamp'])
            
            with col2:
                if st.button(f"🗑️ Delete", key=f"delete_{backup['timestamp']}"):
                    st.warning("⚠️ Backup deletion not implemented yet")


def restore_from_backup(recovery_service: SessionRecoveryService, session_id: str, timestamp: str):
    """Restore session from backup."""
    error_handler = create_error_handler()
    
    with error_boundary(error_handler, ErrorContext(session_id=session_id, component="BackupRestore")):
        progress_placeholder = st.empty()
        progress_placeholder.info(f"🔄 Restoring session {session_id[:8]} from backup...")
        
        success = recovery_service.restore_session_from_backup(session_id, timestamp)
        
        progress_placeholder.empty()
        
        if success:
            st.success(f"✅ Successfully restored session {session_id[:8]} from backup")
            st.info("💡 Please refresh the page to see the restored session")
        else:
            st.error(f"❌ Failed to restore session {session_id[:8]} from backup")


def display_recovery_result(result: RecoveryResult):
    """Display recovery operation result."""
    status_icons = {
        RecoveryStatus.SUCCESS: "✅",
        RecoveryStatus.PARTIAL: "⚠️",
        RecoveryStatus.FAILED: "❌",
        RecoveryStatus.SKIPPED: "⏭️"
    }
    
    icon = status_icons.get(result.status, "❓")
    st.write(f"**Status:** {icon} {result.status.value.title()}")
    st.write(f"**Recovery Time:** {result.recovery_time:.2f} seconds")
    st.write(f"**Backup Created:** {'✅ Yes' if result.backup_created else '❌ No'}")
    
    if result.issues_found:
        st.write(f"**Issues Found:** {len(result.issues_found)}")
        for issue in result.issues_found:
            st.write(f"  • {issue.description}")
    
    if result.issues_fixed:
        st.write(f"**Issues Fixed:** {len(result.issues_fixed)}")
        for issue in result.issues_fixed:
            st.write(f"  • {issue.description}")
    
    if result.error_message:
        st.write(f"**Error:** {result.error_message}")


def render_session_recovery_widget(session_id: str):
    """Render a compact session recovery widget for individual sessions."""
    recovery_service = create_recovery_service()
    if not recovery_service:
        return
    
    with st.expander("🔧 Session Recovery Options", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔍 Check Health", key=f"health_{session_id}"):
                analyze_session(recovery_service, session_id)
        
        with col2:
            if st.button("💾 Create Backup", key=f"backup_{session_id}"):
                create_session_backup(recovery_service, session_id)
        
        with col3:
            if st.button("🔧 Recover", key=f"recover_{session_id}"):
                recover_session(recovery_service, session_id, True, False)