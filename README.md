# Snyk Organization Deleter

A Python script to safely delete Snyk organizations based on specified criteria. This tool provides comprehensive safety features to prevent accidental deletion of important organizations.

## ⚠️ **IMPORTANT WARNING**

**This script permanently deletes Snyk organizations and all associated data. This action cannot be undone. Use with extreme caution and always test with the `--dry-run` flag first.**

## Features

- 🔒 **Safe by Design**: Requires explicit confirmation and exclusion lists
- 🧪 **Dry Run Mode**: Preview what would be deleted without making changes
- 📝 **Comprehensive Logging**: Detailed logs of all operations
- 🛡️ **Exclusion Lists**: Protect important organizations from deletion
- 🌍 **Multi-Region Support**: Works with all Snyk regions
- ✅ **Error Handling**: Robust error handling and rollback capabilities
- 📊 **Progress Tracking**: Real-time progress updates during deletion

## Prerequisites

- Python 3.6 or higher
- Snyk API token with organization management permissions
- Snyk group ID
- List of organizations to exclude from deletion

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### 1. Create Exclusions File

Create a file (e.g., `exclusions.txt`) containing organization IDs or names that should **NOT** be deleted:

```txt
# Protected organizations
production-org
critical-infrastructure
main-company-org
abc12345-def6-7890-ghij-klmnopqrstuv
```

**Important**: 
- Lines starting with `#` are comments and ignored
- You can use either organization IDs or names
- Include ALL organizations you want to protect

### 2. Get Required Information

- **Snyk Token**: Generate from [Snyk Account Settings](https://app.snyk.io/account)
- **Group ID**: Found in Snyk UI or via API
- **Region**: Your Snyk region (default: SNYK-US-01)

## Usage

### Basic Usage

```bash
python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt
```

### Dry Run (Recommended First Step)

```bash
python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt --dry-run
```

### Advanced Options

```bash
python snyk_org_deleter.py \
  --token YOUR_TOKEN \
  --group-id GROUP_ID \
  --exclusions exclusions.txt \
  --region SNYK-EU-01 \
  --version 2024-10-15
```

## Command Line Arguments

| Argument | Required | Description | Default |
|----------|----------|-------------|---------|
| `--token` | Yes | Snyk API token | - |
| `--group-id` | Yes | Snyk group ID to filter organizations | - |
| `--exclusions` | Yes | File containing protected organizations | - |
| `--region` | No | Snyk region | SNYK-US-01 |
| `--dry-run` | No | Preview changes without deleting | False |
| `--version` | No | API version | 2024-10-15 |

### Supported Regions

- `SNYK-US-01` (default) - US East
- `SNYK-US-02` - US West  
- `SNYK-EU-01` - Europe
- `SNYK-AU-01` - Australia

## Workflow

### 1. **Preparation**
   - Create exclusions file with protected organizations
   - Verify your Snyk token has necessary permissions
   - Identify the group ID for organizations to process

### 2. **Testing (Always Do This First!)**
   ```bash
   python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt --dry-run
   ```
   - Review the output carefully
   - Verify protected organizations are correctly identified
   - Confirm the list of organizations to be deleted

### 3. **Execution**
   ```bash
   python snyk_org_deleter.py --token YOUR_TOKEN --group-id GROUP_ID --exclusions exclusions.txt
   ```
   - Script will show summary and ask for confirmation
   - Type the exact confirmation text to proceed
   - Monitor progress and logs

## Safety Features

### 1. **Exclusion Lists**
- Organizations in the exclusions file are never deleted
- Supports both organization IDs and names
- Comments and empty lines are ignored

### 2. **Group Filtering**
- Only processes organizations in the specified group
- Organizations in other groups are automatically protected

### 3. **Confirmation Prompts**
- Shows exactly what will be deleted
- Requires typing a specific confirmation text
- Cannot be bypassed accidentally

### 4. **Comprehensive Logging**
- All operations logged to timestamped files
- Console output for real-time monitoring
- Error details and rollback information

### 5. **Dry Run Mode**
- Preview all changes without making them
- Shows organization details and project counts
- Safe way to test configuration

## Output and Logging

### Console Output
- Real-time progress updates
- Organization analysis results
- Confirmation prompts
- Final results summary

### Log Files
- Stored in `logs/` directory
- Timestamped filenames (e.g., `org_deletion_20241201_143022.log`)
- Detailed information about all operations
- Error details and troubleshooting information

## Error Handling

The script handles various error scenarios:

- **API Errors**: Network issues, authentication failures, rate limits
- **File Errors**: Missing exclusions file, permission issues
- **Validation Errors**: Invalid tokens, group IDs, or API responses
- **Deletion Failures**: Individual organization deletion failures

Failed deletions are logged and reported, but don't stop the overall process.

## Examples

### Example 1: Dry Run for US Region
```bash
python snyk_org_deleter.py \
  --token "abc123-def456-ghi789" \
  --group-id "group-12345" \
  --exclusions "protected_orgs.txt" \
  --dry-run
```

### Example 2: Delete Organizations in EU Region
```bash
python snyk_org_deleter.py \
  --token "abc123-def456-ghi789" \
  --group-id "group-67890" \
  --exclusions "eu_exclusions.txt" \
  --region "SNYK-EU-01"
```

### Example 3: Use Custom API Version
```bash
python snyk_org_deleter.py \
  --token "abc123-def456-ghi789" \
  --group-id "group-11111" \
  --exclusions "exclusions.txt" \
  --version "2024-10-15"
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify your Snyk token is valid and has necessary permissions
   - Check if the token has expired

2. **Group ID Not Found**
   - Verify the group ID exists in your Snyk account
   - Ensure your token has access to the specified group

3. **No Organizations Found**
   - Check if the group ID is correct
   - Verify your token has access to organizations in the group

4. **Permission Denied**
   - Ensure your token has organization management permissions
   - Contact your Snyk administrator if needed

### Getting Help

- Check the log files in the `logs/` directory
- Review console output for error messages
- Verify all required parameters are provided
- Test with `--dry-run` first to identify issues

## Security Considerations

- **Token Security**: Never commit API tokens to version control
- **Exclusions File**: Keep your exclusions file secure and backed up
- **Permissions**: Use tokens with minimal necessary permissions
- **Audit Trail**: All operations are logged for audit purposes

## Contributing

This script is designed to be safe and reliable. If you find issues or have improvements:

1. Test thoroughly with `--dry-run` mode
2. Ensure safety features remain intact
3. Add comprehensive error handling
4. Update documentation as needed

## License

This project is provided as-is for educational and operational purposes. Use at your own risk and ensure compliance with your organization's policies.

## Disclaimer

The authors are not responsible for any data loss or unintended consequences from using this script. Always test thoroughly and maintain proper backups before running in production environments. 