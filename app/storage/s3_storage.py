"""
S3-compatible storage backend implementation using boto3
"""

import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse

from .base import (
    StorageBackend, StorageObject, StorageObjectInfo,
    StorageError, StorageNotFoundError, StoragePermissionError,
    StorageConnectionError, StorageConfigurationError
)


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend using boto3"""
    
    def __init__(self, bucket_name: str, region: str = "us-east-1", 
                 aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None,
                 endpoint_url: Optional[str] = None,
                 prefix: str = ""):
        """
        Initialize S3 storage backend
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region
            aws_access_key_id: AWS access key (optional, can use environment/IAM)
            aws_secret_access_key: AWS secret key (optional, can use environment/IAM)
            endpoint_url: Custom S3 endpoint URL (for S3-compatible services)
            prefix: Key prefix for all objects
        """
        self.bucket_name = bucket_name
        self.region = region
        self.prefix = prefix.rstrip('/') + '/' if prefix else ''
        
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            # Store exceptions for later use
            self.ClientError = ClientError
            self.NoCredentialsError = NoCredentialsError
            
            # Create S3 client
            session_kwargs = {}
            if aws_access_key_id and aws_secret_access_key:
                session_kwargs.update({
                    'aws_access_key_id': aws_access_key_id,
                    'aws_secret_access_key': aws_secret_access_key
                })
            
            session = boto3.Session(**session_kwargs)
            
            client_kwargs = {'region_name': region}
            if endpoint_url:
                client_kwargs['endpoint_url'] = endpoint_url
            
            self.s3_client = session.client('s3', **client_kwargs)
            
            # Verify bucket access
            self._verify_bucket_access()
            
        except ImportError:
            raise StorageConfigurationError(
                "boto3 is required for S3 storage. Install with: pip install boto3"
            )
        except NoCredentialsError:
            raise StorageConfigurationError(
                "AWS credentials not found. Configure credentials via environment variables, "
                "AWS credentials file, or IAM roles."
            )
        except Exception as e:
            raise StorageConnectionError(f"Failed to initialize S3 client: {e}")
    
    def _verify_bucket_access(self):
        """Verify that we can access the bucket"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise StorageConfigurationError(f"Bucket '{self.bucket_name}' does not exist")
            elif error_code == '403':
                raise StoragePermissionError(f"Access denied to bucket '{self.bucket_name}'")
            else:
                raise StorageConnectionError(f"Cannot access bucket '{self.bucket_name}': {e}")
    
    def _get_full_key(self, key: str) -> str:
        """Add prefix to key"""
        return self.prefix + key
    
    def _remove_prefix(self, key: str) -> str:
        """Remove prefix from key"""
        if key.startswith(self.prefix):
            return key[len(self.prefix):]
        return key
    
    def get_object(self, key: str, version_id: Optional[str] = None) -> StorageObject:
        """Retrieve an object from S3"""
        try:
            full_key = self._get_full_key(key)
            
            get_kwargs = {'Bucket': self.bucket_name, 'Key': full_key}
            if version_id:
                get_kwargs['VersionId'] = version_id
            
            response = self.s3_client.get_object(**get_kwargs)
            
            content = response['Body'].read().decode('utf-8')
            
            return StorageObject(
                key=key,
                content=content,
                content_type=response.get('ContentType', 'text/plain'),
                size=response.get('ContentLength', len(content.encode('utf-8'))),
                last_modified=response.get('LastModified'),
                etag=response.get('ETag', '').strip('"'),
                metadata=response.get('Metadata', {}),
                version_id=response.get('VersionId')
            )
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"Object not found: {key}")
            elif error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied to object: {key}")
            else:
                raise StorageError(f"Error retrieving object {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error retrieving object {key}: {e}")
    
    def put_object(self, key: str, content: str, content_type: str = "text/plain", 
                   metadata: Optional[Dict[str, str]] = None,
                   tags: Optional[Dict[str, str]] = None) -> bool:
        """Store an object in S3"""
        try:
            full_key = self._get_full_key(key)
            
            put_kwargs = {
                'Bucket': self.bucket_name,
                'Key': full_key,
                'Body': content.encode('utf-8'),
                'ContentType': content_type
            }
            
            if metadata:
                put_kwargs['Metadata'] = metadata
            
            self.s3_client.put_object(**put_kwargs)
            
            # Add tags if provided
            if tags:
                try:
                    tag_set = [{'Key': k, 'Value': v} for k, v in tags.items()]
                    self.s3_client.put_object_tagging(
                        Bucket=self.bucket_name,
                        Key=full_key,
                        Tagging={'TagSet': tag_set}
                    )
                except Exception:
                    # Tags are optional, don't fail the main operation
                    pass
            
            return True
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied writing object: {key}")
            else:
                raise StorageError(f"Error storing object {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error storing object {key}: {e}")
    
    def list_objects(self, prefix: str = "", max_keys: int = 1000, 
                    continuation_token: Optional[str] = None) -> Dict[str, Any]:
        """List objects in S3 with optional prefix"""
        try:
            full_prefix = self._get_full_key(prefix)
            
            list_kwargs = {
                'Bucket': self.bucket_name,
                'Prefix': full_prefix,
                'MaxKeys': max_keys
            }
            
            if continuation_token:
                list_kwargs['ContinuationToken'] = continuation_token
            
            response = self.s3_client.list_objects_v2(**list_kwargs)
            
            objects = []
            for obj in response.get('Contents', []):
                key = self._remove_prefix(obj['Key'])
                objects.append(StorageObjectInfo(
                    key=key,
                    size=obj['Size'],
                    last_modified=obj['LastModified'],
                    etag=obj.get('ETag', '').strip('"'),
                    content_type='text/plain'  # S3 doesn't return content type in list
                ))
            
            # Get common prefixes (directories)
            common_prefixes = []
            for prefix_info in response.get('CommonPrefixes', []):
                common_prefixes.append(self._remove_prefix(prefix_info['Prefix']))
            
            return {
                'objects': objects,
                'is_truncated': response.get('IsTruncated', False),
                'next_continuation_token': response.get('NextContinuationToken'),
                'common_prefixes': common_prefixes
            }
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied listing objects with prefix: {prefix}")
            else:
                raise StorageError(f"Error listing objects with prefix {prefix}: {e}")
        except Exception as e:
            raise StorageError(f"Error listing objects with prefix {prefix}: {e}")
    
    def delete_object(self, key: str, version_id: Optional[str] = None) -> bool:
        """Delete an object from S3"""
        try:
            full_key = self._get_full_key(key)
            
            delete_kwargs = {'Bucket': self.bucket_name, 'Key': full_key}
            if version_id:
                delete_kwargs['VersionId'] = version_id
            
            self.s3_client.delete_object(**delete_kwargs)
            return True
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                return True  # Already deleted
            elif error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied deleting object: {key}")
            else:
                raise StorageError(f"Error deleting object {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error deleting object {key}: {e}")
    
    def object_exists(self, key: str, version_id: Optional[str] = None) -> bool:
        """Check if an object exists in S3"""
        try:
            full_key = self._get_full_key(key)
            
            head_kwargs = {'Bucket': self.bucket_name, 'Key': full_key}
            if version_id:
                head_kwargs['VersionId'] = version_id
            
            self.s3_client.head_object(**head_kwargs)
            return True
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['NoSuchKey', '404']:
                return False
            else:
                raise StorageError(f"Error checking existence of {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error checking existence of {key}: {e}")
    
    def copy_object(self, source_key: str, dest_key: str, 
                   source_version_id: Optional[str] = None,
                   metadata: Optional[Dict[str, str]] = None) -> bool:
        """Copy an object within S3"""
        try:
            source_full_key = self._get_full_key(source_key)
            dest_full_key = self._get_full_key(dest_key)
            
            copy_source = {'Bucket': self.bucket_name, 'Key': source_full_key}
            if source_version_id:
                copy_source['VersionId'] = source_version_id
            
            copy_kwargs = {
                'CopySource': copy_source,
                'Bucket': self.bucket_name,
                'Key': dest_full_key
            }
            
            if metadata:
                copy_kwargs['Metadata'] = metadata
                copy_kwargs['MetadataDirective'] = 'REPLACE'
            
            self.s3_client.copy_object(**copy_kwargs)
            return True
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"Source object not found: {source_key}")
            elif error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied copying {source_key} to {dest_key}")
            else:
                raise StorageError(f"Error copying {source_key} to {dest_key}: {e}")
        except Exception as e:
            raise StorageError(f"Error copying {source_key} to {dest_key}: {e}")
    
    def get_object_metadata(self, key: str, version_id: Optional[str] = None) -> Dict[str, str]:
        """Get object metadata without downloading content"""
        try:
            full_key = self._get_full_key(key)
            
            head_kwargs = {'Bucket': self.bucket_name, 'Key': full_key}
            if version_id:
                head_kwargs['VersionId'] = version_id
            
            response = self.s3_client.head_object(**head_kwargs)
            return response.get('Metadata', {})
        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"Object not found: {key}")
            elif error_code == 'AccessDenied':
                raise StoragePermissionError(f"Access denied to object metadata: {key}")
            else:
                raise StorageError(f"Error getting metadata for {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error getting metadata for {key}: {e}")
    
    def get_presigned_url(self, key: str, expires_in: int = 3600, 
                         method: str = "GET") -> Optional[str]:
        """Generate a presigned URL for object access"""
        try:
            full_key = self._get_full_key(key)
            
            method_mapping = {
                'GET': 'get_object',
                'PUT': 'put_object',
                'DELETE': 'delete_object'
            }
            
            operation = method_mapping.get(method.upper(), 'get_object')
            
            url = self.s3_client.generate_presigned_url(
                operation,
                Params={'Bucket': self.bucket_name, 'Key': full_key},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            raise StorageError(f"Error generating presigned URL for {key}: {e}")
    
    def batch_delete(self, keys: List[str]) -> Dict[str, bool]:
        """Delete multiple objects in batch"""
        if not keys:
            return {}
        
        try:
            # S3 batch delete supports up to 1000 objects
            batch_size = 1000
            results = {}
            
            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]
                
                delete_objects = [
                    {'Key': self._get_full_key(key)} for key in batch_keys
                ]
                
                response = self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': delete_objects}
                )
                
                # Mark successful deletions
                for deleted in response.get('Deleted', []):
                    original_key = self._remove_prefix(deleted['Key'])
                    results[original_key] = True
                
                # Mark failed deletions
                for error in response.get('Errors', []):
                    original_key = self._remove_prefix(error['Key'])
                    results[original_key] = False
                
                # Mark any remaining keys as successful (not in response means success)
                for key in batch_keys:
                    if key not in results:
                        results[key] = True
            
            return results
        except Exception as e:
            # Fallback to individual deletions
            return super().batch_delete(keys)
    
    def list_object_versions(self, key: str) -> List[StorageObjectInfo]:
        """List all versions of an object"""
        try:
            full_key = self._get_full_key(key)
            
            response = self.s3_client.list_object_versions(
                Bucket=self.bucket_name,
                Prefix=full_key
            )
            
            versions = []
            for version in response.get('Versions', []):
                if version['Key'] == full_key:
                    versions.append(StorageObjectInfo(
                        key=key,
                        size=version['Size'],
                        last_modified=version['LastModified'],
                        etag=version.get('ETag', '').strip('"'),
                        version_id=version.get('VersionId'),
                        is_delete_marker=False
                    ))
            
            # Also include delete markers
            for marker in response.get('DeleteMarkers', []):
                if marker['Key'] == full_key:
                    versions.append(StorageObjectInfo(
                        key=key,
                        size=0,
                        last_modified=marker['LastModified'],
                        version_id=marker.get('VersionId'),
                        is_delete_marker=True
                    ))
            
            # Sort by last modified descending
            versions.sort(key=lambda v: v.last_modified, reverse=True)
            return versions
        except self.ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return []
            else:
                raise StorageError(f"Error listing versions for {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error listing versions for {key}: {e}")
    
    def get_object_tags(self, key: str, version_id: Optional[str] = None) -> Dict[str, str]:
        """Get object tags"""
        try:
            full_key = self._get_full_key(key)
            
            tag_kwargs = {'Bucket': self.bucket_name, 'Key': full_key}
            if version_id:
                tag_kwargs['VersionId'] = version_id
            
            response = self.s3_client.get_object_tagging(**tag_kwargs)
            
            tags = {}
            for tag in response.get('TagSet', []):
                tags[tag['Key']] = tag['Value']
            
            return tags
        except self.ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise StorageNotFoundError(f"Object not found: {key}")
            else:
                return {}  # Tags might not be supported or accessible
        except Exception:
            return {}  # Tags are optional
    
    def put_object_tags(self, key: str, tags: Dict[str, str], 
                       version_id: Optional[str] = None) -> bool:
        """Set object tags"""
        try:
            full_key = self._get_full_key(key)
            
            tag_set = [{'Key': k, 'Value': v} for k, v in tags.items()]
            
            tag_kwargs = {
                'Bucket': self.bucket_name,
                'Key': full_key,
                'Tagging': {'TagSet': tag_set}
            }
            if version_id:
                tag_kwargs['VersionId'] = version_id
            
            self.s3_client.put_object_tagging(**tag_kwargs)
            return True
        except Exception:
            return False  # Tags are optional
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage backend information and statistics"""
        try:
            # Get bucket location
            location_response = self.s3_client.get_bucket_location(Bucket=self.bucket_name)
            location = location_response.get('LocationConstraint') or 'us-east-1'
            
            # Check if versioning is enabled
            versioning_response = self.s3_client.get_bucket_versioning(Bucket=self.bucket_name)
            versioning_enabled = versioning_response.get('Status') == 'Enabled'
            
            return {
                "backend_type": "S3StorageBackend",
                "bucket_name": self.bucket_name,
                "region": location,
                "prefix": self.prefix,
                "supports_versioning": versioning_enabled,
                "supports_multipart": True,
                "supports_presigned_urls": True,
                "supports_tags": True
            }
        except Exception as e:
            return {
                "backend_type": "S3StorageBackend",
                "bucket_name": self.bucket_name,
                "error": str(e)
            }
    
    # Session-specific operations for S3
    def create_session_directory(self, session_id: str) -> bool:
        """Create session structure in S3 (by creating placeholder objects)"""
        try:
            # S3 doesn't have directories, but we can create placeholder objects
            placeholders = [
                f"sessions/{session_id}/policies/.placeholder",
                f"sessions/{session_id}/validation_results/.placeholder"
            ]
            
            for placeholder in placeholders:
                self.put_object(placeholder, "", "text/plain")
            
            return True
        except Exception as e:
            raise StorageError(f"Failed to create session structure for {session_id}: {e}")
    
    def cleanup_empty_sessions(self) -> int:
        """Remove sessions that only have metadata or placeholder files"""
        try:
            # List all sessions
            result = self.list_objects("sessions/")
            objects = result.get('objects', [])
            
            # Group objects by session
            sessions = {}
            for obj in objects:
                parts = obj.key.split('/')
                if len(parts) >= 2 and parts[0] == 'sessions':
                    session_id = parts[1]
                    if session_id not in sessions:
                        sessions[session_id] = []
                    sessions[session_id].append(obj.key)
            
            cleaned_count = 0
            for session_id, files in sessions.items():
                # Filter out metadata and placeholder files
                content_files = [f for f in files if not (
                    f.endswith('metadata.json') or 
                    f.endswith('.placeholder')
                )]
                
                # If no content files, delete the session
                if not content_files:
                    delete_keys = [f"sessions/{session_id}/{f.split('/')[-1]}" for f in files]
                    self.batch_delete(delete_keys)
                    cleaned_count += 1
            
            return cleaned_count
        except Exception as e:
            raise StorageError(f"Failed to cleanup empty sessions: {e}")
    
    def get_session_statistics(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a specific session"""
        try:
            result = self.list_objects(f"sessions/{session_id}/")
            objects = result.get('objects', [])
            
            if not objects:
                raise StorageNotFoundError(f"Session not found: {session_id}")
            
            total_size = sum(obj.size for obj in objects)
            file_count = len([obj for obj in objects if not obj.key.endswith('.placeholder')])
            
            # Get file types
            file_types = {}
            latest_modified = None
            
            for obj in objects:
                if not obj.key.endswith('.placeholder'):
                    ext = '.' + obj.key.split('.')[-1] if '.' in obj.key else 'no_extension'
                    file_types[ext] = file_types.get(ext, 0) + 1
                    
                    if latest_modified is None or obj.last_modified > latest_modified:
                        latest_modified = obj.last_modified
            
            return {
                "session_id": session_id,
                "total_size_bytes": total_size,
                "file_count": file_count,
                "file_types": file_types,
                "last_modified": latest_modified
            }
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get session statistics for {session_id}: {e}")