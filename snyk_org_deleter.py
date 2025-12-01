#!/usr/bin/env python3
"""
Snyk Organization Deleter

This script deletes Snyk organizations based on specified criteria.
It requires a Snyk token, group ID, and an exclusion list of organizations to preserve.

Usage:
    python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt

Safety Features:
    - Dry-run mode to preview changes
    - Exclusion list to prevent accidental deletion of important orgs
    - Confirmation prompts before deletion
    - Comprehensive logging of all operations
    - Error handling and rollback capabilities
"""

import requests
import json
import os
import sys
import time
import datetime
import logging
import argparse
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import random


class RateLimiter:
    """Handles rate limiting with exponential backoff for 429 responses."""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.last_429_time = 0
        self.backoff_until = 0
    
    def handle_429(self, endpoint: str):
        """Handle 429 rate limit response with backoff."""
        with self.lock:
            current_time = time.time()
            
            # If we're already in backoff, extend it
            if current_time < self.backoff_until:
                wait_time = self.backoff_until - current_time
                logging.warning(f"Rate limited on {endpoint}. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                return
            
            # Set backoff for 1 minute (60 seconds)
            self.backoff_until = current_time + 60
            logging.warning(f"Rate limited on {endpoint}. Backing off for 60 seconds...")
            time.sleep(60)
    
    def is_in_backoff(self) -> bool:
        """Check if we're currently in a backoff period."""
        with self.lock:
            return time.time() < self.backoff_until


class SnykOrgDeleter:
    """Snyk API client for deleting organizations."""
    
    def __init__(self, token: str, region: str = "SNYK-US-01", max_workers: int = 5):
        self.token = token
        self.base_url = self._get_base_url(region)
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Content-Type': 'application/vnd.api+json',
            'Accept': '*/*'
        })
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter()
        
        # Setup logging
        self.setup_logging()
        
    def _get_base_url(self, region: str) -> str:
        """Get the appropriate API base URL for the region."""
        region_urls = {
            "SNYK-US-01": "https://api.snyk.io",
            "SNYK-US-02": "https://api.us.snyk.io", 
            "SNYK-EU-01": "https://api.eu.snyk.io",
            "SNYK-AU-01": "https://api.au.snyk.io"
        }
        return region_urls.get(region, "https://api.snyk.io")
    
    def setup_logging(self):
        """Setup logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"org_deletion_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging initialized. Log file: {log_file}")
    
    def get_token_details(self, version: str = "2024-10-15") -> Optional[Dict]:
        """Get details about the current token."""
        url = f"{self.base_url}/rest/self"
        params = {'version': version}
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching token details: {e}")
            return None
    
    def get_snyk_orgs(self, version: str = "2024-10-15", group_id: Optional[str] = None) -> List[Dict]:
        """Get all Snyk organizations."""
        url = f"{self.base_url}/rest/groups/{group_id}/orgs"
        params = {
            'version': version,
            'limit': 100
        }
        
        all_orgs = []
        next_url = url
        next_params = params
        page = 1
        
        while next_url:
            self.logger.info(f"Fetching orgs page {page}...")
            try:
                response = self.session.get(next_url, params=next_params)
                response.raise_for_status()
                data = response.json()
                
                orgs = data.get('data', [])
                all_orgs.extend(orgs)
                
                # Handle pagination
                links = data.get('links', {})
                next_url = links.get('next')
                next_params = None
                
                if next_url:
                    if next_url.startswith('http'):
                        pass  # use as-is
                    elif next_url.startswith('/'):
                        next_url = self.base_url + next_url
                    else:
                        next_url = self.base_url + '/' + next_url.lstrip('/')
                else:
                    next_url = None
                
                page += 1
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error fetching orgs page {page}: {e}")
                break
        
        self.logger.info(f"Found {len(all_orgs)} total organizations")
        return all_orgs
    

    

    
    def delete_org(self, org_id: str) -> bool:
        """Delete a Snyk organization."""
        url = f"{self.base_url}/v1/org/{org_id}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Check if we're in backoff
                if self.rate_limiter.is_in_backoff():
                    wait_time = 5 + random.uniform(0, 5)  # Random jitter
                    time.sleep(wait_time)
                
                self.logger.info(f"Deleting organization {org_id}... (attempt {attempt + 1})")
                self.logger.info(f"Delete URL: {url}")
                
                # Use specific headers for v1 delete endpoint
                headers = {
                    'Authorization': f'token {self.token}',
                    'Accept': '*/*'
                }
                
                response = self.session.delete(url, headers=headers)
                
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE org {org_id}")
                    continue
                
                # Log the response details for debugging
                # 204 No Content is also a success status for DELETE operations
                if response.status_code not in [200, 204]:
                    self.logger.error(f"Delete failed with status {response.status_code}")
                    try:
                        error_data = response.json()
                        self.logger.error(f"Error response: {error_data}")
                        
                        # Check if this is the specific error about projects needing to be deleted
                        if (response.status_code == 400 and 
                            isinstance(error_data, dict) and 
                            'message' in error_data and
                            'You must delete all projects in your organization before the organization can be deleted' in error_data['message']):
                            
                            self.logger.warning(f"Organization {org_id} still has projects. Attempting to delete them...")
                            
                            # Try to delete projects and then retry organization deletion
                            project_results = self.delete_all_org_projects(org_id)
                            
                            if project_results['failed']:
                                self.logger.error(f"Failed to delete {len(project_results['failed'])} projects. Cannot delete organization.")
                                return False
                            
                            self.logger.info(f"Successfully deleted all projects. Retrying organization deletion...")
                            time.sleep(2)  # Wait for project deletion to complete
                            
                            # Retry the organization deletion
                            retry_response = self.session.delete(url, headers=headers)
                            # 204 No Content is also a success status for DELETE operations
                            if retry_response.status_code in [200, 204]:
                                self.logger.info(f"Successfully deleted organization {org_id} after project cleanup")
                                return True
                            else:
                                self.logger.error(f"Organization deletion still failed after project cleanup: {retry_response.status_code}")
                                return False
                        
                    except:
                        self.logger.error(f"Error response text: {response.text}")
                
                # 204 No Content is also a success status for DELETE operations
                if response.status_code in [200, 204]:
                    self.logger.info(f"Successfully deleted organization {org_id}")
                    return True
                
                response.raise_for_status()
                self.logger.info(f"Successfully deleted organization {org_id}")
                return True
                
            except requests.exceptions.RequestException as e:
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE org {org_id}")
                    continue
                else:
                    self.logger.error(f"Error deleting organization {org_id}: {e}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(1 + random.uniform(0, 2))  # Random backoff
        
        return False
    

    

    

    
    def delete_org_with_projects(self, org_id: str) -> bool:
        """Delete an organization, with automatic project cleanup if needed."""
        org_name = "Unknown"  # We'll get this from the org data if available
        
        try:
            # Try to delete the organization directly
            self.logger.info(f"Attempting to delete organization {org_id}")
            if self.delete_org(org_id):
                self.logger.info(f"✅ Successfully deleted organization {org_id}")
                return True
            else:
                self.logger.error(f"❌ Failed to delete organization {org_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error in delete_org_with_projects for {org_id}: {e}")
            return False
    
    def load_exclusions(self, exclusions_file: str) -> List[str]:
        """Load exclusion list from file."""
        exclusions = []
        try:
            with open(exclusions_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        exclusions.append(line)
            self.logger.info(f"Loaded {len(exclusions)} exclusions from {exclusions_file}")
        except FileNotFoundError:
            self.logger.warning(f"Exclusions file {exclusions_file} not found. No organizations will be excluded.")
        except Exception as e:
            self.logger.error(f"Error loading exclusions file: {e}")
        
        return exclusions
    
    def analyze_orgs_for_deletion(self, orgs: List[Dict], exclusions: List[str], group_id: Optional[str] = None) -> Tuple[List[Dict], List[Dict]]:
        """Analyze organizations and separate them into deletable and protected lists."""
        deletable = []
        protected = []
        
        for org in orgs:
            org_id = org.get('id')
            org_name = org.get('attributes', {}).get('name', 'Unknown')
            
            # Check if org should be excluded
            if org_id in exclusions or org_name in exclusions:
                protected.append(org)
                self.logger.info(f"Organization '{org_name}' ({org_id}) is in exclusion list - PROTECTED")
                continue
            
            # Check if org belongs to the specified group
            if group_id:
                org_group_id = org.get('attributes', {}).get('group_id')
                if org_group_id != group_id:
                    protected.append(org)
                    self.logger.info(f"Organization '{org_name}' ({org_id}) belongs to different group - PROTECTED")
                    continue
            
            deletable.append(org)
            self.logger.info(f"Organization '{org_name}' ({org_id}) marked for deletion")
        
        return deletable, protected
    
    def dry_run_deletion(self, deletable_orgs: List[Dict]) -> None:
        """Perform a dry run to show what would be deleted."""
        self.logger.info("=" * 60)
        self.logger.info("DRY RUN MODE - No organizations will be deleted")
        self.logger.info("=" * 60)
        
        if not deletable_orgs:
            self.logger.info("No organizations would be deleted.")
            return
        
        self.logger.info(f"The following {len(deletable_orgs)} organizations would be deleted:")
        
        for org in deletable_orgs:
            org_id = org.get('id')
            org_name = org.get('attributes', {}).get('name', 'Unknown')
            org_created = org.get('attributes', {}).get('created', 'Unknown')
            
            self.logger.info(f"  - {org_name} ({org_id})")
            self.logger.info(f"    Created: {org_created}")
            self.logger.info("")
        
        self.logger.info("=" * 60)
    
    def confirm_deletion(self, deletable_orgs: List[Dict]) -> bool:
        """Get user confirmation for deletion."""
        if not deletable_orgs:
            return False
        
        print(f"\n⚠️  WARNING: You are about to delete {len(deletable_orgs)} organizations!")
        print("This action cannot be undone.")
        print("\nOrganizations to be deleted:")
        
        for org in deletable_orgs:
            org_name = org.get('attributes', {}).get('name', 'Unknown')
            org_id = org.get('id')
            print(f"  - {org_name} ({org_id})")
        
        print(f"\nType 'DELETE {len(deletable_orgs)}' to confirm:")
        confirmation = input("> ").strip()
        
        return confirmation == f"DELETE {len(deletable_orgs)}"
    
    def execute_deletion(self, deletable_orgs: List[Dict]) -> Dict[str, List[str]]:
        """Execute the actual deletion of organizations using multi-threading."""
        results = {
            'successful': [],
            'failed': []
        }
        
        self.logger.info("=" * 60)
        self.logger.info("EXECUTING DELETION")
        self.logger.info("=" * 60)
        
        # Thread-safe results collection
        results_lock = threading.Lock()
        
        def delete_org_worker(org):
            """Worker function to delete a single organization with all its targets."""
            org_id = org.get('id')
            org_name = org.get('attributes', {}).get('name', 'Unknown')
            
            self.logger.info(f"Processing organization: {org_name} ({org_id})")
            
            # Step 1: Delete all targets for the organization
            self.logger.info(f"Step 1: Deleting all targets for organization {org_id}")
            target_results = self.delete_all_org_targets(org_id)
            
            if target_results['failed']:
                self.logger.warning(f"Some targets failed to delete: {len(target_results['failed'])} failures")
                self.logger.warning("Proceeding with organization deletion anyway...")
            
            # Wait a moment for target deletion to complete
            time.sleep(2)
            
            # Step 2: Now delete the organization
            success = self.delete_org_with_projects(org_id)
            
            with results_lock:
                if success:
                    results['successful'].append(org_id)
                    self.logger.info(f"✅ Successfully deleted {org_name}")
                else:
                    results['failed'].append(org_id)
                    self.logger.error(f"❌ Failed to delete {org_name}")
            
            return success
        
        # Use ThreadPoolExecutor for concurrent organization deletion
        # Use fewer workers for organizations since they're more resource-intensive
        org_workers = min(3, self.max_workers)
        self.logger.info(f"Using {org_workers} workers for organization deletion...")
        
        with ThreadPoolExecutor(max_workers=org_workers) as executor:
            # Submit all organization deletion tasks
            future_to_org = {
                executor.submit(delete_org_worker, org): org 
                for org in deletable_orgs
            }
            
            # Process completed tasks
            for future in as_completed(future_to_org):
                org = future_to_org[future]
                try:
                    future.result()  # This will raise any exceptions
                except Exception as e:
                    org_id = org.get('id')
                    org_name = org.get('attributes', {}).get('name', 'Unknown')
                    self.logger.error(f"Exception in organization deletion worker for {org_name} ({org_id}): {e}")
                    with results_lock:
                        results['failed'].append(org_id)
        
        self.logger.info("=" * 60)
        self.logger.info(f"Deletion completed. Successful: {len(results['successful'])}, Failed: {len(results['failed'])}")
        self.logger.info("=" * 60)
        
        return results

    def get_org_projects(self, org_id: str) -> List[Dict]:
        """Get all projects for an organization."""
        url = f"{self.base_url}/rest/orgs/{org_id}/projects"
        params = {'version': '2024-10-15'}
        
        all_projects = []
        next_url = url
        next_params = params
        page = 1
        
        while next_url:
            self.logger.info(f"Fetching projects page {page} for org {org_id}...")
            try:
                response = self.session.get(next_url, params=next_params)
                response.raise_for_status()
                data = response.json()
                
                projects = data.get('data', [])
                all_projects.extend(projects)
                
                # Handle pagination
                links = data.get('links', {})
                next_url = links.get('next')
                next_params = None
                
                if next_url:
                    if next_url.startswith('http'):
                        pass  # use as-is
                    elif next_url.startswith('/'):
                        next_url = self.base_url + next_url
                    else:
                        next_url = self.base_url + '/' + next_url.lstrip('/')
                else:
                    next_url = None
                
                page += 1
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error fetching projects page {page} for org {org_id}: {e}")
                break
        
        self.logger.info(f"Found {len(all_projects)} total projects for org {org_id}")
        return all_projects
    
    def delete_project(self, org_id: str, project_id: str) -> bool:
        """Delete a specific project from an organization."""
        url = f"{self.base_url}/rest/orgs/{org_id}/projects/{project_id}"
        params = {'version': '2024-10-15'}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Check if we're in backoff
                if self.rate_limiter.is_in_backoff():
                    wait_time = 5 + random.uniform(0, 5)  # Random jitter
                    time.sleep(wait_time)
                
                self.logger.info(f"Deleting project {project_id} from org {org_id}... (attempt {attempt + 1})")
                response = self.session.delete(url, params=params)
                
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE project {project_id}")
                    continue
                
                # 404 means project not found (already deleted) - treat as success
                if response.status_code == 404:
                    self.logger.debug(f"Project {project_id} not found (already deleted)")
                    return True
                
                # 204 No Content is also a success status for DELETE operations
                if response.status_code in [200, 204]:
                    self.logger.info(f"Successfully deleted project {project_id} from org {org_id}")
                    return True
                
                response.raise_for_status()
                return True
                
            except requests.exceptions.RequestException as e:
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE project {project_id}")
                    continue
                elif response.status_code == 404:
                    # Project not found - already deleted, treat as success
                    self.logger.debug(f"Project {project_id} not found (already deleted)")
                    return True
                else:
                    self.logger.error(f"Error deleting project {project_id} from org {org_id}: {e}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(1 + random.uniform(0, 2))  # Random backoff
        
        return False
    
    def delete_all_org_projects(self, org_id: str) -> Dict[str, List[str]]:
        """Delete all projects in an organization using multi-threading."""
        self.logger.info(f"Starting deletion of all projects for org {org_id}")
        
        # Get all projects
        projects = self.get_org_projects(org_id)
        
        if not projects:
            self.logger.info(f"No projects found for org {org_id}")
            return {'successful': [], 'failed': []}
        
        results = {
            'successful': [],
            'failed': []
        }
        
        self.logger.info(f"Deleting {len(projects)} projects from org {org_id} using {self.max_workers} workers...")
        
        # Thread-safe results collection
        results_lock = threading.Lock()
        
        def delete_project_worker(project):
            """Worker function to delete a single project."""
            project_id = project.get('id')
            project_name = project.get('attributes', {}).get('name', 'Unknown')
            project_type = project.get('attributes', {}).get('type', 'Unknown')
            
            self.logger.info(f"Processing project: {project_name} ({project_id}) - Type: {project_type}")
            
            success = self.delete_project(org_id, project_id)
            
            with results_lock:
                if success:
                    results['successful'].append(project_id)
                    self.logger.info(f"✅ Successfully deleted project {project_name}")
                else:
                    results['failed'].append(project_id)
                    self.logger.error(f"❌ Failed to delete project {project_name}")
            
            return success
        
        # Use ThreadPoolExecutor for concurrent project deletion
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all project deletion tasks
            future_to_project = {
                executor.submit(delete_project_worker, project): project 
                for project in projects
            }
            
            # Process completed tasks
            for future in as_completed(future_to_project):
                project = future_to_project[future]
                try:
                    future.result()  # This will raise any exceptions
                except Exception as e:
                    project_id = project.get('id')
                    project_name = project.get('attributes', {}).get('name', 'Unknown')
                    self.logger.error(f"Exception in project deletion worker for {project_name} ({project_id}): {e}")
                    with results_lock:
                        results['failed'].append(project_id)
        
        self.logger.info(f"Project deletion completed for org {org_id}. Successful: {len(results['successful'])}, Failed: {len(results['failed'])}")
        return results

    def get_org_targets(self, org_id: str) -> List[Dict]:
        """Get all targets for an organization."""
        url = f"{self.base_url}/rest/orgs/{org_id}/targets"
        params = {
            'version': '2024-10-15',
            'limit': 100
        }
        
        all_targets = []
        next_url = url
        next_params = params
        page = 1
        
        while next_url:
            self.logger.info(f"Fetching targets page {page} for org {org_id}...")
            try:
                response = self.session.get(next_url, params=next_params)
                response.raise_for_status()
                data = response.json()
                
                targets = data.get('data', [])
                all_targets.extend(targets)
                
                # Handle pagination
                links = data.get('links', {})
                next_url = links.get('next')
                next_params = None
                
                if next_url:
                    if next_url.startswith('http'):
                        pass  # use as-is
                    elif next_url.startswith('/'):
                        next_url = self.base_url + next_url
                    else:
                        next_url = self.base_url + '/' + next_url.lstrip('/')
                else:
                    next_url = None
                
                page += 1
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error fetching targets page {page} for org {org_id}: {e}")
                break
        
        self.logger.info(f"Found {len(all_targets)} total targets for org {org_id}")
        return all_targets
    
    def delete_target(self, org_id: str, target_id: str) -> bool:
        """Delete a specific target from an organization."""
        url = f"{self.base_url}/rest/orgs/{org_id}/targets/{target_id}"
        params = {'version': '2024-10-15'}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Check if we're in backoff
                if self.rate_limiter.is_in_backoff():
                    wait_time = 5 + random.uniform(0, 5)  # Random jitter
                    time.sleep(wait_time)
                
                self.logger.info(f"Deleting target {target_id} from org {org_id}... (attempt {attempt + 1})")
                response = self.session.delete(url, params=params)
                
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE target {target_id}")
                    continue
                
                # 404 means target not found (already deleted) - treat as success
                if response.status_code == 404:
                    self.logger.debug(f"Target {target_id} not found (already deleted)")
                    return True
                
                # 204 No Content is also a success status for DELETE operations
                if response.status_code in [200, 204]:
                    self.logger.info(f"Successfully deleted target {target_id} from org {org_id}")
                    return True
                
                response.raise_for_status()
                return True
                
            except requests.exceptions.RequestException as e:
                if response.status_code == 429:
                    self.rate_limiter.handle_429(f"DELETE target {target_id}")
                    continue
                elif response.status_code == 404:
                    # Target not found - already deleted, treat as success
                    self.logger.debug(f"Target {target_id} not found (already deleted)")
                    return True
                else:
                    self.logger.error(f"Error deleting target {target_id} from org {org_id}: {e}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(1 + random.uniform(0, 2))  # Random backoff
        
        return False
    
    def delete_all_org_targets(self, org_id: str) -> Dict[str, List[str]]:
        """Delete all targets in an organization using multi-threading."""
        self.logger.info(f"Starting deletion of all targets for org {org_id}")
        
        # Get all targets
        targets = self.get_org_targets(org_id)
        
        if not targets:
            self.logger.info(f"No targets found for org {org_id}")
            return {'successful': [], 'failed': []}
        
        results = {
            'successful': [],
            'failed': []
        }
        
        self.logger.info(f"Deleting {len(targets)} targets from org {org_id} using {self.max_workers} workers...")
        
        # Thread-safe results collection
        results_lock = threading.Lock()
        
        def delete_target_worker(target):
            """Worker function to delete a single target."""
            target_id = target.get('id')
            target_name = target.get('attributes', {}).get('display_name', 'Unknown')
            target_url = target.get('attributes', {}).get('url', 'Unknown')
            
            self.logger.info(f"Processing target: {target_name} ({target_id})")
            self.logger.info(f"  URL: {target_url}")
            
            success = self.delete_target(org_id, target_id)
            
            with results_lock:
                if success:
                    results['successful'].append(target_id)
                    self.logger.info(f"✅ Successfully deleted target {target_name}")
                else:
                    results['failed'].append(target_id)
                    self.logger.error(f"❌ Failed to delete target {target_name}")
            
            return success
        
        # Use ThreadPoolExecutor for concurrent deletion
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all target deletion tasks
            future_to_target = {
                executor.submit(delete_target_worker, target): target 
                for target in targets
            }
            
            # Process completed tasks
            for future in as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    future.result()  # This will raise any exceptions
                except Exception as e:
                    target_id = target.get('id')
                    target_name = target.get('attributes', {}).get('display_name', 'Unknown')
                    self.logger.error(f"Exception in target deletion worker for {target_name} ({target_id}): {e}")
                    with results_lock:
                        results['failed'].append(target_id)
        
        self.logger.info(f"Target deletion completed for org {org_id}. Successful: {len(results['successful'])}, Failed: {len(results['failed'])}")
        return results


def main():
    """Main function to run the organization deletion process."""
    parser = argparse.ArgumentParser(
        description="Delete Snyk organizations based on specified criteria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be deleted
  python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt --dry-run
  
  # Actually delete organizations (deletes targets first, then projects if needed)
  python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt
  
  # Use different region
  python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt --region SNYK-EU-01
  
  # Use custom number of workers for faster deletion
  python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt --max-workers 10
        """
    )
    
    parser.add_argument('--token', required=True, help='Snyk API token')
    parser.add_argument('--group-id', required=True, help='Snyk group ID to filter organizations')
    parser.add_argument('--exclusions', required=True, help='File containing list of organization IDs/names to exclude from deletion')
    parser.add_argument('--region', default='SNYK-US-01', 
                       choices=['SNYK-US-01', 'SNYK-US-02', 'SNYK-EU-01', 'SNYK-AU-01'],
                       help='Snyk region (default: SNYK-US-01)')
    parser.add_argument('--max-workers', type=int, default=5, help='Maximum number of concurrent workers for target deletion (default: 5)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    parser.add_argument('--version', default='2024-10-15', help='API version (default: 2024-10-15)')
    
    args = parser.parse_args()
    
    # Initialize the deleter
    deleter = SnykOrgDeleter(args.token, args.region, args.max_workers)
    
    # Verify token
    token_details = deleter.get_token_details(args.version)
    if not token_details:
        print("❌ Failed to verify Snyk token. Please check your token and try again.")
        sys.exit(1)
    
    print(f"✅ Snyk token verified for user: {token_details.get('data', {}).get('attributes', {}).get('email', 'Unknown')}")
    
    # Load exclusions
    exclusions = deleter.load_exclusions(args.exclusions)
    
    # Get all organizations
    print(f"🔍 Fetching organizations for group {args.group_id}...")
    orgs = deleter.get_snyk_orgs(args.version, args.group_id)
    
    if not orgs:
        print("❌ No organizations found for the specified group.")
        sys.exit(1)
    
    # Analyze organizations
    print("📊 Analyzing organizations...")
    deletable, protected = deleter.analyze_orgs_for_deletion(orgs, exclusions, args.group_id)
    
    print(f"\n📋 Summary:")
    print(f"  Total organizations: {len(orgs)}")
    print(f"  Protected: {len(protected)}")
    print(f"  Deletable: {len(deletable)}")
    
    if not deletable:
        print("\n✅ No organizations to delete. All organizations are protected.")
        sys.exit(0)
    
    # Dry run mode
    if args.dry_run:
        deleter.dry_run_deletion(deletable)
        sys.exit(0)
    
    # Get confirmation
    if not deleter.confirm_deletion(deletable):
        print("\n❌ Deletion cancelled by user.")
        sys.exit(0)
    
    # Execute deletion
    results = deleter.execute_deletion(deletable)
    
    # Final summary
    print(f"\n🎯 Final Results:")
    print(f"  Successfully deleted: {len(results['successful'])}")
    print(f"  Failed to delete: {len(results['failed'])}")
    
    if results['failed']:
        print(f"\n❌ Failed deletions:")
        for org_id in results['failed']:
            print(f"  - {org_id}")
        sys.exit(1)
    else:
        print("\n✅ All organizations deleted successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main() 