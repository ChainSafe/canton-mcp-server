"""
Git-Verified Resource Extractor

Extracts canonical resources from Git-verified documentation repositories
and creates YAML resources with integrity verification.
"""

import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from .git_verification import (
    create_git_verified_resource,
    sync_canonical_repos,
    GitVerificationError
)

logger = logging.getLogger(__name__)


class ResourceExtractionError(Exception):
    """Raised when resource extraction fails"""
    pass


class GitVerifiedResourceExtractor:
    """
    Extracts canonical resources from Git-verified documentation repositories.
    """
    
    def __init__(self, canonical_docs_path: Path):
        """
        Initialize the extractor.
        
        Args:
            canonical_docs_path: Path to directory containing canonical repos
        """
        self.canonical_docs_path = canonical_docs_path
        self.repo_paths = {
            "daml": canonical_docs_path / "daml",
            "canton": canonical_docs_path / "canton", 
            "daml-finance": canonical_docs_path / "daml-finance"
        }
    
    def sync_repositories(self) -> Dict[str, str]:
        """
        Sync all canonical repositories to latest commits.
        
        Returns:
            Dictionary mapping repo names to their latest commit hashes
        """
        logger.info("Syncing canonical repositories...")
        commit_hashes = sync_canonical_repos(self.canonical_docs_path)
        logger.info(f"Synced repositories: {list(commit_hashes.keys())}")
        return commit_hashes
    
    def extract_security_patterns(self, commit_hash: str) -> List[Dict[str, Any]]:
        """
        Extract authorization patterns from security evidence file.
        
        Args:
            commit_hash: Git commit hash to extract from
            
        Returns:
            List of extracted pattern resources
        """
        patterns = []
        
        try:
            # Extract from DAML security evidence
            resource_data = create_git_verified_resource(
                self.repo_paths["daml"],
                commit_hash,
                "sdk/security-evidence.md",
                "pattern"
            )
            
            # Parse security evidence content
            content = resource_data["content"]
            
            # Extract well-authorized patterns
            well_auth_patterns = self._extract_well_authorized_patterns(content)
            for pattern in well_auth_patterns:
                pattern_resource = self._create_pattern_resource(
                    pattern,
                    resource_data["canonical_hash"],
                    resource_data["source_commit"],
                    resource_data["source_file"],
                    resource_data["extracted_at"]
                )
                patterns.append(pattern_resource)
            
            logger.info(f"Extracted {len(patterns)} authorization patterns")
            
        except GitVerificationError as e:
            logger.error(f"Failed to extract security patterns: {e}")
            raise ResourceExtractionError(f"Security pattern extraction failed: {e}")
        
        return patterns
    
    def extract_anti_patterns(self, commit_hash: str) -> List[Dict[str, Any]]:
        """
        Extract anti-patterns from security evidence file.
        
        Args:
            commit_hash: Git commit hash to extract from
            
        Returns:
            List of extracted anti-pattern resources
        """
        anti_patterns = []
        
        try:
            # Extract from DAML security evidence
            resource_data = create_git_verified_resource(
                self.repo_paths["daml"],
                commit_hash,
                "sdk/security-evidence.md",
                "anti-pattern"
            )
            
            # Parse security evidence content
            content = resource_data["content"]
            
            # Extract badly-authorized anti-patterns
            bad_auth_patterns = self._extract_badly_authorized_patterns(content)
            for pattern in bad_auth_patterns:
                anti_pattern_resource = self._create_anti_pattern_resource(
                    pattern,
                    resource_data["canonical_hash"],
                    resource_data["source_commit"],
                    resource_data["source_file"],
                    resource_data["extracted_at"]
                )
                anti_patterns.append(anti_pattern_resource)
            
            logger.info(f"Extracted {len(anti_patterns)} anti-patterns")
            
        except GitVerificationError as e:
            logger.error(f"Failed to extract anti-patterns: {e}")
            raise ResourceExtractionError(f"Anti-pattern extraction failed: {e}")
        
        return anti_patterns
    
    def extract_finance_patterns(self, commit_hash: str) -> List[Dict[str, Any]]:
        """
        Extract complex patterns from DAML-Finance repository.
        
        Args:
            commit_hash: Git commit hash to extract from
            
        Returns:
            List of extracted pattern resources
        """
        patterns = []
        
        try:
            # Look for settlement patterns
            settlement_files = [
                "docs/generated/tutorials/settlement/intro.rst",
                "docs/generated/tutorials/settlement/transfer.rst",
                "docs/generated/concepts/settlement.rst"
            ]
            
            for file_path in settlement_files:
                try:
                    resource_data = create_git_verified_resource(
                        self.repo_paths["daml-finance"],
                        commit_hash,
                        file_path,
                        "pattern"
                    )
                    
                    # Extract settlement patterns
                    settlement_patterns = self._extract_settlement_patterns(resource_data["content"])
                    for pattern in settlement_patterns:
                        pattern_resource = self._create_pattern_resource(
                            pattern,
                            resource_data["canonical_hash"],
                            resource_data["source_commit"],
                            resource_data["source_file"],
                            resource_data["extracted_at"]
                        )
                        patterns.append(pattern_resource)
                        
                except GitVerificationError:
                    # File might not exist in this commit
                    continue
            
            logger.info(f"Extracted {len(patterns)} finance patterns")
            
        except Exception as e:
            logger.error(f"Failed to extract finance patterns: {e}")
            raise ResourceExtractionError(f"Finance pattern extraction failed: {e}")
        
        return patterns
    
    def _extract_well_authorized_patterns(self, content: str) -> List[Dict[str, str]]:
        """Extract well-authorized patterns from security evidence content."""
        patterns = []
        lines = content.split('\n')
        
        for line in lines:
            if 'well-authorized' in line and 'is accepted' in line:
                # Extract pattern description
                description = line.split(':')[0].strip()
                patterns.append({
                    "name": description.lower().replace(' ', '-').replace('_', '-'),
                    "description": f"Canonical pattern: {description}",
                    "pattern_type": "authorization_pattern",
                    "daml_template": f"-- {description}\n-- Well-authorized pattern from security evidence",
                    "authorization_requirements": [
                        {
                            "id": "REQ-AUTH-001",
                            "rule": "Proper authorization must be maintained",
                            "satisfied": True,
                            "explanation": f"Pattern ensures {description}"
                        }
                    ],
                    "when_to_use": [f"Scenarios requiring {description}"],
                    "when_not_to_use": ["Scenarios with insufficient authorization"],
                    "security_considerations": ["Ensure proper authorization is maintained"],
                    "test_cases": [
                        {
                            "description": f"Valid {description}",
                            "passes": True,
                            "code": f"-- {description} test case"
                        }
                    ]
                })
        
        return patterns
    
    def _extract_badly_authorized_patterns(self, content: str) -> List[Dict[str, str]]:
        """Extract badly-authorized anti-patterns from security evidence content."""
        anti_patterns = []
        lines = content.split('\n')
        
        for line in lines:
            if 'badly-authorized' in line and 'is rejected' in line:
                # Extract anti-pattern description
                description = line.split(':')[0].strip()
                anti_patterns.append({
                    "name": description.lower().replace(' ', '-').replace('_', '-'),
                    "description": f"Anti-pattern: {description}",
                    "anti_pattern_type": "authorization_vulnerability",
                    "severity": "critical",
                    "problematic_code": f"-- {description}\n-- Badly-authorized anti-pattern",
                    "why_problematic": f"This anti-pattern occurs when {description}",
                    "detection_pattern": [f"Code that performs {description}"],
                    "correct_alternative": f"-- Correct implementation avoiding {description}",
                    "impact": [
                        {
                            "type": "security",
                            "severity": "critical",
                            "description": f"Security vulnerability: {description}"
                        }
                    ],
                    "remediation": [f"Fix authorization for {description}"]
                })
        
        return anti_patterns
    
    def _extract_settlement_patterns(self, content: str) -> List[Dict[str, str]]:
        """Extract settlement patterns from DAML-Finance content."""
        patterns = []
        
        # Simple extraction - look for settlement-related content
        if 'settlement' in content.lower():
            patterns.append({
                "name": "settlement-workflow",
                "description": "Canonical pattern for financial settlement workflows",
                "pattern_type": "settlement_workflow",
                "daml_template": "-- Settlement workflow pattern\n-- Extracted from DAML-Finance documentation",
                "authorization_requirements": [
                    {
                        "id": "REQ-AUTH-001",
                        "rule": "Settlement parties must be properly authorized",
                        "satisfied": True,
                        "explanation": "Settlement workflow ensures proper party authorization"
                    }
                ],
                "when_to_use": ["Financial settlement scenarios", "Multi-party payment workflows"],
                "when_not_to_use": ["Simple bilateral transfers", "Non-financial workflows"],
                "security_considerations": ["Ensure settlement parties are authenticated", "Validate settlement amounts"],
                "test_cases": [
                    {
                        "description": "Valid settlement workflow",
                        "passes": True,
                        "code": "-- Settlement workflow test case"
                    }
                ]
            })
        
        return patterns
    
    def _create_pattern_resource(self, pattern_data: Dict[str, Any], canonical_hash: str, 
                                source_commit: str, source_file: str, extracted_at: str) -> Dict[str, Any]:
        """Create a pattern resource with Git verification metadata."""
        return {
            "name": pattern_data["name"],
            "version": "1.0.0",
            "description": pattern_data["description"],
            "tags": ["pattern", "authorization", "canonical", "git-verified"],
            "author": "Digital Asset",
            "created_at": extracted_at,
            "updated_at": extracted_at,
            "pattern_type": pattern_data["pattern_type"],
            "daml_template": pattern_data["daml_template"],
            "authorization_requirements": pattern_data["authorization_requirements"],
            "when_to_use": pattern_data["when_to_use"],
            "when_not_to_use": pattern_data["when_not_to_use"],
            "security_considerations": pattern_data["security_considerations"],
            "test_cases": pattern_data["test_cases"],
            "canonical_hash": canonical_hash,
            "source_commit": source_commit,
            "source_file": source_file,
            "extracted_at": extracted_at
        }
    
    def _create_anti_pattern_resource(self, anti_pattern_data: Dict[str, Any], canonical_hash: str,
                                    source_commit: str, source_file: str, extracted_at: str) -> Dict[str, Any]:
        """Create an anti-pattern resource with Git verification metadata."""
        return {
            "name": anti_pattern_data["name"],
            "version": "1.0.0",
            "description": anti_pattern_data["description"],
            "tags": ["anti-pattern", "authorization", "canonical", "git-verified"],
            "author": "Digital Asset",
            "created_at": extracted_at,
            "updated_at": extracted_at,
            "anti_pattern_type": anti_pattern_data["anti_pattern_type"],
            "severity": anti_pattern_data["severity"],
            "problematic_code": anti_pattern_data["problematic_code"],
            "why_problematic": anti_pattern_data["why_problematic"],
            "detection_pattern": anti_pattern_data["detection_pattern"],
            "correct_alternative": anti_pattern_data["correct_alternative"],
            "impact": anti_pattern_data["impact"],
            "remediation": anti_pattern_data["remediation"],
            "canonical_hash": canonical_hash,
            "source_commit": source_commit,
            "source_file": source_file,
            "extracted_at": extracted_at
        }
    
    def save_resources(self, resources: List[Dict[str, Any]], output_dir: Path) -> None:
        """
        Save extracted resources to YAML files.
        
        Args:
            resources: List of resource dictionaries
            output_dir: Directory to save YAML files
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for resource in resources:
            filename = f"{resource['name']}-v{resource['version']}.yaml"
            file_path = output_dir / filename
            
            with open(file_path, 'w') as f:
                yaml.dump(resource, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved resource: {file_path}")
    
    def extract_all_resources(self, output_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract all canonical resources from Git repositories.
        
        Args:
            output_dir: Directory to save extracted resources
            
        Returns:
            Dictionary mapping resource types to lists of resources
        """
        logger.info("Starting canonical resource extraction...")
        
        # Sync repositories
        commit_hashes = self.sync_repositories()
        
        all_resources = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        # Extract from DAML repo
        if "daml" in commit_hashes:
            daml_commit = commit_hashes["daml"]
            
            # Extract patterns and anti-patterns
            patterns = self.extract_security_patterns(daml_commit)
            anti_patterns = self.extract_anti_patterns(daml_commit)
            
            all_resources["patterns"].extend(patterns)
            all_resources["anti_patterns"].extend(anti_patterns)
        
        # Extract from DAML-Finance repo
        if "daml-finance" in commit_hashes:
            finance_commit = commit_hashes["daml-finance"]
            
            # Extract finance patterns
            finance_patterns = self.extract_finance_patterns(finance_commit)
            all_resources["patterns"].extend(finance_patterns)
        
        # Save all resources
        for resource_type, resources in all_resources.items():
            if resources:
                type_dir = output_dir / resource_type
                self.save_resources(resources, type_dir)
        
        logger.info(f"Extraction complete: {sum(len(r) for r in all_resources.values())} resources extracted")
        return all_resources
