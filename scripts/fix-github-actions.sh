#!/bin/bash
# Fix GitHub Actions workflows for BedrockAgentCore Starter Toolkit
# This script backs up existing workflows and creates corrected ones

set -e

echo "=== Fixing GitHub Actions Workflows ==="
echo

# Check if we're in the repo root
if [ ! -f "pyproject.toml" ]; then
    echo "Error: This script must be run from the repository root"
    exit 1
fi

# Create backup directory
BACKUP_DIR=".github/workflows-backup-$(date +%Y%m%d-%H%M%S)"
if [ -d ".github/workflows" ]; then
    echo "Backing up existing workflows to $BACKUP_DIR"
    cp -r .github/workflows "$BACKUP_DIR"
fi

# Ensure workflows directory exists
mkdir -p .github/workflows

echo "Creating new workflows..."

# 1. Main CI Workflow (FIXED - installs wheelhouse, no || true)
cat > .github/workflows/ci.yml << 'EOF'
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

permissions:
  contents: read

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Install uv
      uses: astral-sh/setup-uv@v3
        
    - name: Create virtual environment
      run: uv venv
      
    - name: Install wheelhouse dependencies
      run: |
        source .venv/bin/activate
        pip install ./wheelhouse/botocore-*.whl
        pip install ./wheelhouse/boto3-*.whl
        pip install ./wheelhouse/bedrock_agentcore-*.whl
        
    - name: Install package with dev dependencies
      run: |
        source .venv/bin/activate
        pip install -e ".[dev]" --no-deps
        pip install pre-commit pytest mypy ruff
        
    - name: Run pre-commit hooks
      run: |
        source .venv/bin/activate
        pre-commit run --all-files
        
  test:
    name: Test Python ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.10', '3.11', '3.12', '3.13']
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
        
    - name: Install uv
      uses: astral-sh/setup-uv@v3
      
    - name: Create virtual environment
      run: uv venv --python ${{ matrix.python-version }}
      
    - name: Install wheelhouse dependencies
      run: |
        source .venv/bin/activate
        # Install in correct order
        pip install ./wheelhouse/botocore-*.whl
        pip install ./wheelhouse/boto3-*.whl
        pip install ./wheelhouse/bedrock_agentcore-*.whl
        
    - name: Install package and test dependencies
      run: |
        source .venv/bin/activate
        # Install package without wheelhouse deps
        pip install -e . --no-deps
        # Install remaining dependencies
        pip install pytest pytest-cov pytest-asyncio moto mock requests httpx \
                    jinja2 prompt-toolkit pydantic pyyaml rich toml typer \
                    typing-extensions uvicorn docstring_parser urllib3
        
    - name: Run tests with coverage
      run: |
        source .venv/bin/activate
        pytest tests/ \
          --cov=src \
          --cov-report=term-missing \
          --cov-report=xml \
          --cov-report=html \
          --cov-fail-under=80 \
          --cov-branch \
          -v
          
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v4
      if: matrix.python-version == '3.10'
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-${{ matrix.python-version }}
        token: ${{ secrets.CODECOV_TOKEN }}
        fail_ci_if_error: false
        
    - name: Upload coverage HTML
      uses: actions/upload-artifact@v4
      if: matrix.python-version == '3.10'
      with:
        name: coverage-html-${{ matrix.python-version }}
        path: htmlcov/
        
  build:
    name: Build Package
    runs-on: ubuntu-latest
    needs: [lint, test]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Install build tools
      run: |
        python -m pip install --upgrade pip
        pip install build twine wheel
        
    - name: Create release pyproject.toml (no wheelhouse)
      run: |
        cp pyproject.toml pyproject.toml.original
        python scripts/prepare-release.py
        
    - name: Build package
      run: python -m build
      
    - name: Restore original pyproject.toml
      run: mv pyproject.toml.original pyproject.toml
        
    - name: Check package
      run: |
        twine check dist/*
        echo "=== Checking wheel contents ==="
        python -m zipfile -l dist/*.whl | head -20
        echo "=== Verifying no wheelhouse ==="
        python -m zipfile -l dist/*.whl | grep wheelhouse && exit 1 || echo "✓ No wheelhouse in package"
        
    - name: Upload build artifacts
      uses: actions/upload-artifact@v4
      with:
        name: dist-packages
        path: dist/
        
    - name: Test wheel installation
      run: |
        python -m venv test-env
        source test-env/bin/activate
        pip install dist/*.whl
        python -c "from bedrock_agentcore_starter_toolkit import Runtime; print('✓ Import successful')"
        agentcore --help
EOF

# 2. Security Scanning (using the user's updated version)
cat > .github/workflows/security.yml << 'EOF'
name: Security Scanning

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 12 * * 1'  # Weekly on Monday

permissions:
  contents: read
  security-events: write

jobs:
  bandit:
    name: Bandit Security Scan
    runs-on: ubuntu-latest
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Install uv
      uses: astral-sh/setup-uv@v3
        
    - name: Create virtual environment
      run: uv venv
        
    - name: Install Bandit
      run: |
        source .venv/bin/activate
        uv pip install bandit[toml]
      
    - name: Run Bandit
      run: |
        source .venv/bin/activate
        bandit -r src/ -f json -o bandit-results.json
        
    - name: Upload Bandit results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: bandit-results
        path: bandit-results.json
        
  safety:
    name: Safety Dependency Check
    runs-on: ubuntu-latest
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Install uv
      uses: astral-sh/setup-uv@v3
        
    - name: Create virtual environment
      run: uv venv
        
    - name: Install safety
      run: |
        source .venv/bin/activate
        uv pip install safety
      
    - name: Generate requirements
      run: |
        source .venv/bin/activate
        uv pip compile pyproject.toml -o requirements.txt || echo "Failed to compile requirements"
        
    - name: Run safety check
      run: |
        source .venv/bin/activate
        safety check -r requirements.txt --json > safety-results.json || echo "No vulnerabilities found"
        
    - name: Upload safety results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: safety-results
        path: safety-results.json

  trufflehog:
    name: TruffleHog Secret Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: TruffleHog OSS
        uses: trufflesecurity/trufflehog@v3.82.3
        with:
          path: ./
          base: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.before }}
          head: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}
          extra_args: --debug --only-verified
EOF

# 3. Test PyPI Release Workflow
cat > .github/workflows/test-pypi-release.yml << 'EOF'
name: Test PyPI Release

on:
  workflow_dispatch:
    inputs:
      version_bump:
        description: 'Version bump type'
        required: true
        type: choice
        options:
          - patch
          - minor
          - major
          - prepatch
          - preminor
          - premajor

permissions:
  contents: write
  id-token: write

jobs:
  prepare-release:
    name: Prepare Release
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
    
    steps:
    - uses: actions/checkout@v4
      with:
        token: ${{ secrets.GITHUB_TOKEN }}
        
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Get current version
      id: version
      run: |
        CURRENT_VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
        echo "Current version: $CURRENT_VERSION"
        echo "version=$CURRENT_VERSION" >> $GITHUB_OUTPUT
        
    - name: Update version
      run: |
        python scripts/bump-version.py ${{ github.event.inputs.version_bump }}
        NEW_VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
        echo "New version: $NEW_VERSION"
        
  test-and-build:
    name: Test and Build
    needs: prepare-release
    uses: ./.github/workflows/ci.yml
    
  publish-test-pypi:
    name: Publish to Test PyPI
    needs: [prepare-release, test-and-build]
    runs-on: ubuntu-latest
    environment:
      name: testpypi
      url: https://test.pypi.org/p/bedrock-agentcore-starter-toolkit
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Download build artifacts
      uses: actions/download-artifact@v4
      with:
        name: dist-packages
        path: dist/
        
    - name: Publish to Test PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        repository-url: https://test.pypi.org/legacy/
        password: ${{ secrets.TEST_PYPI_API_TOKEN }}
        skip-existing: true
        
    - name: Wait for package availability
      run: sleep 60
      
    - name: Test installation from Test PyPI
      run: |
        python -m venv test-install
        source test-install/bin/activate
        pip install --index-url https://test.pypi.org/simple/ \
                    --extra-index-url https://pypi.org/simple/ \
                    bedrock-agentcore-starter-toolkit==${{ needs.prepare-release.outputs.version }}
        python -c "from bedrock_agentcore_starter_toolkit import Runtime; print('✓ Test PyPI install successful')"
        agentcore --version
EOF

# 4. Production Release Workflow
cat > .github/workflows/release.yml << 'EOF'
name: Production Release

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    inputs:
      confirm_release:
        description: 'Type "release" to confirm production release'
        required: true
        type: string

permissions:
  contents: write
  id-token: write

jobs:
  validate-release:
    name: Validate Release
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'push' || 
      (github.event_name == 'workflow_dispatch' && github.event.inputs.confirm_release == 'release')
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Validate version tag
      if: github.event_name == 'push'
      run: |
        VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
        TAG_VERSION="${GITHUB_REF_NAME#v}"
        if [[ "$VERSION" != "$TAG_VERSION" ]]; then
          echo "Error: Package version ($VERSION) does not match tag ($TAG_VERSION)"
          exit 1
        fi
        
  build-and-test:
    name: Build and Test
    needs: validate-release
    uses: ./.github/workflows/ci.yml
    
  publish-pypi:
    name: Publish to PyPI
    needs: [validate-release, build-and-test]
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/bedrock-agentcore-starter-toolkit
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Download build artifacts
      uses: actions/download-artifact@v4
      with:
        name: dist-packages
        path: dist/
        
    - name: Publish to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        password: ${{ secrets.PYPI_API_TOKEN }}
        
    - name: Create GitHub Release
      uses: softprops/action-gh-release@v2
      if: github.event_name == 'push'
      with:
        files: dist/*
        generate_release_notes: true
        draft: false
        prerelease: ${{ contains(github.ref_name, 'rc') || contains(github.ref_name, 'beta') }}
EOF

# 5. Create helper scripts
mkdir -p scripts

cat > scripts/prepare-release.py << 'EOF'
#!/usr/bin/env python3
"""Remove tool.uv.sources from pyproject.toml for release."""
import re

with open('pyproject.toml', 'r') as f:
    content = f.read()

# Remove [tool.uv.sources] section
content = re.sub(r'\[tool\.uv\.sources\].*?(?=\[|$)', '', content, flags=re.DOTALL)

# Clean up extra newlines
content = re.sub(r'\n{3,}', '\n\n', content)

with open('pyproject.toml', 'w') as f:
    f.write(content)

print("✓ Removed tool.uv.sources section for release")
EOF

cat > scripts/bump-version.py << 'EOF'
#!/usr/bin/env python3
"""Bump version in pyproject.toml."""
import sys
import re

def bump_version(version, bump_type):
    """Bump version based on type."""
    parts = version.split('.')
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2].split('-')[0])
    
    if bump_type == 'major':
        return f"{major + 1}.0.0"
    elif bump_type == 'minor':
        return f"{major}.{minor + 1}.0"
    elif bump_type == 'patch':
        return f"{major}.{minor}.{patch + 1}"
    elif bump_type == 'premajor':
        return f"{major + 1}.0.0-beta.1"
    elif bump_type == 'preminor':
        return f"{major}.{minor + 1}.0-beta.1"
    elif bump_type == 'prepatch':
        return f"{major}.{minor}.{patch + 1}-beta.1"
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")

if __name__ == "__main__":
    bump_type = sys.argv[1] if len(sys.argv) > 1 else 'patch'
    
    with open('pyproject.toml', 'r') as f:
        content = f.read()
    
    current_version = re.search(r'version = "([^"]+)"', content).group(1)
    new_version = bump_version(current_version, bump_type)
    
    content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content)
    
    with open('pyproject.toml', 'w') as f:
        f.write(content)
    
    print(f"Version bumped from {current_version} to {new_version}")
EOF

chmod +x scripts/*.py

echo
echo "=== Workflow Fix Complete ==="
echo
echo "Changes made:"
echo "✓ Backed up existing workflows to $BACKUP_DIR"
echo "✓ Created fixed CI workflow (installs wheelhouse, no || true)"
echo "✓ Created security scanning workflow"
echo "✓ Created Test PyPI release workflow"
echo "✓ Created production release workflow"
echo "✓ Created helper scripts"
echo
echo "Next steps:"
echo "1. Review the changes:"
echo "   git diff .github/workflows/"
echo
echo "2. Test locally first:"
echo "   act -j test  # If you have 'act' installed"
echo
echo "3. Commit and push:"
echo "   git add .github/workflows/ scripts/"
echo "   git commit -m 'fix: Update GitHub Actions workflows to properly handle wheelhouse dependencies'"
echo "   git push origin fix/github-actions"
echo
echo "4. Create PR and monitor CI results"
EOF

chmod +x scripts/fix-github-actions.sh
