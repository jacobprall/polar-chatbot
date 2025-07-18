"""Async Polar validator with session integration, caching, and history tracking."""

import asyncio
import logging
import tempfile
import os
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

from app.core.validator import PolarValidator, ValidationResult as CoreValidationResult
from app.models.policy import PolicyValidationRequest, PolicyValidationResult
from app.models.events import SessionEvent, EventType

logger = logging.getLogger(__name__)


@dataclass
class ValidationCacheEntry:
    """Cache entry for validation results."""
    policy_hash: str
    result: PolicyValidationResult
    timestamp: datetime
    session_id: str
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """Check if cache entry has expired."""
        return (datetime.utcnow() - self.timestamp).total_seconds() > ttl_seconds


@dataclass
class ValidationHistoryEntry:
    """History entry for validation tracking."""
    session_id: str
    policy_id: str
    policy_hash: str
    result: PolicyValidationResult
    timestamp: datetime
    retry_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "policy_id": self.policy_id,
            "policy_hash": self.policy_hash,
            "is_valid": self.result.is_valid,
            "error_message": self.result.error_message,
            "error_details": self.result.error_details,
            "validation_time": self.result.validation_time,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count
        }


class AsyncPolarValidator:
    """Async Polar validator with session integration and caching."""
    
    def __init__(self, cli_path: str = "oso-cloud", timeout: int = 30, 
                 cache_ttl: int = 3600, max_concurrent: int = 5):
        """Initialize the async validator.
        
        Args:
            cli_path: Path to oso-cloud CLI
            timeout: Timeout for validation operations
            cache_ttl: Cache time-to-live in seconds
            max_concurrent: Maximum concurrent validation operations
        """
        self.core_validator = PolarValidator(cli_path=cli_path, timeout=timeout)
        self.cache_ttl = cache_ttl
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        
        # In-memory cache and history
        self._validation_cache: Dict[str, ValidationCacheEntry] = {}
        self._validation_history: List[ValidationHistoryEntry] = []
        
        # Statistics tracking
        self._stats = {
            "total_validations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "average_validation_time": 0.0
        }
    
    async def validate_policy_async(self, request: PolicyValidationRequest) -> PolicyValidationResult:
        """Validate a policy asynchronously with caching and history tracking.
        
        Args:
            request: Policy validation request
            
        Returns:
            PolicyValidationResult with validation outcome
        """
        start_time = time.time()
        policy_hash = self._hash_policy_content(request.policy_content)
        
        # Check cache first
        cached_result = self._get_cached_result(policy_hash, request.session_id)
        if cached_result:
            logger.info(f"Cache hit for policy validation in session {request.session_id}")
            self._stats["cache_hits"] += 1
            return cached_result
        
        self._stats["cache_misses"] += 1
        
        try:
            # Run validation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            core_result = await loop.run_in_executor(
                self.executor, 
                self.core_validator.validate_policy, 
                request.policy_content
            )
            
            validation_time = time.time() - start_time
            
            # Convert core result to policy validation result
            result = PolicyValidationResult(
                is_valid=core_result.is_valid,
                error_message=core_result.error_message,
                error_details=core_result.errors.copy() if core_result.errors else [],
                validation_time=validation_time
            )
            
            # Update cache and history
            self._cache_result(policy_hash, result, request.session_id)
            self._add_to_history(request, result, policy_hash)
            
            # Update statistics
            self._update_stats(result, validation_time)
            
            logger.info(f"Validation completed for session {request.session_id}: "
                       f"valid={result.is_valid}, time={validation_time:.2f}s")
            
            return result
            
        except Exception as e:
            validation_time = time.time() - start_time
            error_msg = f"Validation error: {str(e)}"
            
            result = PolicyValidationResult(
                is_valid=False,
                error_message=error_msg,
                error_details=[str(e)],
                validation_time=validation_time
            )
            
            # Still cache and track failed validations
            self._cache_result(policy_hash, result, request.session_id)
            self._add_to_history(request, result, policy_hash)
            self._update_stats(result, validation_time)
            
            logger.error(f"Validation failed for session {request.session_id}: {error_msg}")
            return result
    
    async def validate_multiple_policies(self, requests: List[PolicyValidationRequest]) -> List[PolicyValidationResult]:
        """Validate multiple policies concurrently.
        
        Args:
            requests: List of validation requests
            
        Returns:
            List of validation results in the same order as requests
        """
        if not requests:
            return []
        
        # Create validation tasks
        tasks = [self.validate_policy_async(request) for request in requests]
        
        # Run all validations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions that occurred
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Validation task {i} failed with exception: {result}")
                final_results.append(PolicyValidationResult(
                    is_valid=False,
                    error_message=f"Validation task failed: {str(result)}",
                    error_details=[str(result)]
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    def get_validation_history(self, session_id: str, limit: Optional[int] = None) -> List[ValidationHistoryEntry]:
        """Get validation history for a session.
        
        Args:
            session_id: Session ID to get history for
            limit: Maximum number of entries to return
            
        Returns:
            List of validation history entries, most recent first
        """
        session_history = [
            entry for entry in self._validation_history 
            if entry.session_id == session_id
        ]
        
        # Sort by timestamp, most recent first
        session_history.sort(key=lambda x: x.timestamp, reverse=True)
        
        if limit:
            session_history = session_history[:limit]
        
        return session_history
    
    def get_validation_stats(self, session_id: Optional[str] = None) -> Dict:
        """Get validation statistics.
        
        Args:
            session_id: Optional session ID to filter stats
            
        Returns:
            Dictionary with validation statistics
        """
        if session_id:
            # Filter history for specific session
            session_history = [
                entry for entry in self._validation_history 
                if entry.session_id == session_id
            ]
            
            if not session_history:
                return {
                    "total_validations": 0,
                    "successful_validations": 0,
                    "failed_validations": 0,
                    "average_validation_time": 0.0,
                    "success_rate": 0.0
                }
            
            successful = sum(1 for entry in session_history if entry.result.is_valid)
            total = len(session_history)
            avg_time = sum(entry.result.validation_time for entry in session_history) / total
            
            return {
                "total_validations": total,
                "successful_validations": successful,
                "failed_validations": total - successful,
                "average_validation_time": avg_time,
                "success_rate": successful / total if total > 0 else 0.0
            }
        else:
            # Return global stats
            stats = self._stats.copy()
            total = stats["total_validations"]
            cache_total = stats["cache_hits"] + stats["cache_misses"]
            
            if total > 0:
                stats["success_rate"] = stats["successful_validations"] / total
            else:
                stats["success_rate"] = 0.0
                
            if cache_total > 0:
                stats["cache_hit_rate"] = stats["cache_hits"] / cache_total
            else:
                stats["cache_hit_rate"] = 0.0
            
            return stats
    
    def clear_cache(self, session_id: Optional[str] = None) -> int:
        """Clear validation cache.
        
        Args:
            session_id: Optional session ID to clear cache for specific session
            
        Returns:
            Number of cache entries cleared
        """
        if session_id:
            # Clear cache for specific session
            keys_to_remove = [
                key for key, entry in self._validation_cache.items()
                if entry.session_id == session_id
            ]
            for key in keys_to_remove:
                del self._validation_cache[key]
            return len(keys_to_remove)
        else:
            # Clear entire cache
            count = len(self._validation_cache)
            self._validation_cache.clear()
            return count
    
    def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries.
        
        Returns:
            Number of expired entries removed
        """
        expired_keys = [
            key for key, entry in self._validation_cache.items()
            if entry.is_expired(self.cache_ttl)
        ]
        
        for key in expired_keys:
            del self._validation_cache[key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    async def close(self):
        """Clean up resources."""
        self.executor.shutdown(wait=True)
    
    def _hash_policy_content(self, content: str) -> str:
        """Generate hash for policy content for caching."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _get_cached_result(self, policy_hash: str, session_id: str) -> Optional[PolicyValidationResult]:
        """Get cached validation result if available and not expired."""
        cache_key = f"{session_id}:{policy_hash}"
        
        if cache_key in self._validation_cache:
            entry = self._validation_cache[cache_key]
            if not entry.is_expired(self.cache_ttl):
                return entry.result
            else:
                # Remove expired entry
                del self._validation_cache[cache_key]
        
        return None
    
    def _cache_result(self, policy_hash: str, result: PolicyValidationResult, session_id: str):
        """Cache validation result."""
        cache_key = f"{session_id}:{policy_hash}"
        entry = ValidationCacheEntry(
            policy_hash=policy_hash,
            result=result,
            timestamp=datetime.utcnow(),
            session_id=session_id
        )
        self._validation_cache[cache_key] = entry
    
    def _add_to_history(self, request: PolicyValidationRequest, result: PolicyValidationResult, policy_hash: str):
        """Add validation to history."""
        # Check if this is a retry (same policy hash in recent history)
        retry_count = 0
        recent_entries = [
            entry for entry in self._validation_history
            if (entry.session_id == request.session_id and 
                entry.policy_hash == policy_hash and
                (datetime.utcnow() - entry.timestamp).total_seconds() < 3600)  # Within last hour
        ]
        if recent_entries:
            retry_count = max(entry.retry_count for entry in recent_entries) + 1
        
        history_entry = ValidationHistoryEntry(
            session_id=request.session_id,
            policy_id=request.policy_id,
            policy_hash=policy_hash,
            result=result,
            timestamp=datetime.utcnow(),
            retry_count=retry_count
        )
        
        self._validation_history.append(history_entry)
        
        # Keep history size manageable (keep last 1000 entries)
        if len(self._validation_history) > 1000:
            self._validation_history = self._validation_history[-1000:]
    
    def _update_stats(self, result: PolicyValidationResult, validation_time: float):
        """Update validation statistics."""
        self._stats["total_validations"] += 1
        
        if result.is_valid:
            self._stats["successful_validations"] += 1
        else:
            self._stats["failed_validations"] += 1
        
        # Update average validation time
        total = self._stats["total_validations"]
        current_avg = self._stats["average_validation_time"]
        self._stats["average_validation_time"] = ((current_avg * (total - 1)) + validation_time) / total


# Convenience function for creating validation events
def create_validation_event(session_id: str, policy_id: str, result: PolicyValidationResult, 
                          user_id: str = "default_user") -> SessionEvent:
    """Create a validation completed event from validation result."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.VALIDATION_COMPLETED,
        user_id=user_id,
        document_id=policy_id,
        data={
            "is_valid": result.is_valid,
            "error_message": result.error_message,
            "error_details": result.error_details,
            "validation_time": result.validation_time
        }
    )